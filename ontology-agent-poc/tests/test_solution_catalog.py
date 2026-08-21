from __future__ import annotations

import hashlib
import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from ontology_agent.io import canonical_bytes, load_package
from ontology_agent.models import Status
from ontology_agent.product_context import ExactStoredArtifactRef
from ontology_agent.studio.solutions import (
    SolutionBundleRecordV1,
    SolutionCatalogError,
    SolutionCatalogService,
    SolutionDisplayName,
    SolutionRegistrationRecordV1,
    SolutionRegistrationSubjectV1,
    load_solution_registration,
    verify_solution_components,
)


class MemorySolutionRepository:
    persistence = "postgresql-s3"

    def __init__(self) -> None:
        self.records: dict[tuple[str, str], SolutionRegistrationRecordV1] = {}

    def register(
        self,
        subject: SolutionRegistrationSubjectV1,
        artifact: ExactStoredArtifactRef,
        bundle: SolutionBundleRecordV1,
    ) -> None:
        key = (subject.solution_id, subject.solution_version)
        record = SolutionRegistrationRecordV1(
            persistence="postgresql-s3",
            subject_checksum=artifact.sha256,
            subject=subject,
            artifact=artifact,
            bundle=bundle,
        )
        existing = self.records.setdefault(key, record)
        if existing != record:
            raise SolutionCatalogError("test alias conflict")

    def get(
        self, solution_id: str, solution_version: str
    ) -> SolutionRegistrationRecordV1:
        return self.records[(solution_id, solution_version)]

    def list(self) -> tuple[SolutionRegistrationRecordV1, ...]:
        return tuple(self.records.values())


class MemorySolutionArtifacts:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str, str], bytes] = {}

    def publish_blob(
        self,
        body: bytes,
        *,
        namespace: str,
        media_type: str,
        suffix: str,
    ) -> ExactStoredArtifactRef:
        digest = hashlib.sha256(body).hexdigest()
        ref = ExactStoredArtifactRef(
            bucket="test-solutions",
            key=f"{namespace}/sha256/{digest}.{suffix}",
            version_id=f"version-{digest[:12]}",
            sha256=digest,
            size_bytes=len(body),
            media_type=media_type,
        )
        self.objects[(ref.bucket, ref.key, ref.version_id)] = body
        return ref

    def get_exact(self, ref: ExactStoredArtifactRef) -> bytes:
        return self.objects[(ref.bucket, ref.key, ref.version_id)]


def test_adt_solution_registration_closes_exact_component_inventory(
    scenario_dir: Path,
) -> None:
    subject = load_solution_registration(scenario_dir / "solution-registration.json")

    verify_solution_components(subject, scenario_dir)

    assert subject.solution_id == "ontology.exchange_analytics.adt"
    assert subject.studio_adapter_id == "studio-adapter.adt.reference@1"
    assert {item.kind for item in subject.components} == {
        "authoring_profile",
        "semantic_source",
        "agent_experience",
        "reference_evaluation",
    }


def test_solution_registration_rejects_changed_component_bytes(
    scenario_dir: Path,
) -> None:
    subject = load_solution_registration(scenario_dir / "solution-registration.json")
    (scenario_dir / "ontology" / "package.yaml").write_text(
        "changed: true\n", encoding="utf-8"
    )

    with pytest.raises(SolutionCatalogError, match="digest mismatch"):
        verify_solution_components(subject, scenario_dir)


def test_solution_registration_rejects_cross_component_identity_mismatch(
    scenario_dir: Path,
) -> None:
    subject = load_solution_registration(scenario_dir / "solution-registration.json")
    mismatched = subject.model_copy(update={"scenario_id": "scenario.wrong"})

    with pytest.raises(SolutionCatalogError, match="identity does not match"):
        verify_solution_components(mismatched, scenario_dir)


def test_solution_registration_rejects_an_undeclared_package_file(
    scenario_dir: Path,
) -> None:
    subject = load_solution_registration(scenario_dir / "solution-registration.json")
    (scenario_dir / "input" / "undeclared.md").write_text(
        "not in the exact package inventory\n", encoding="utf-8"
    )

    with pytest.raises(SolutionCatalogError, match="inventory"):
        verify_solution_components(subject, scenario_dir)


def test_durable_solution_bootstrap_is_idempotent_and_exact(
    scenario_dir: Path,
) -> None:
    repository = MemorySolutionRepository()
    artifacts = MemorySolutionArtifacts()
    service = SolutionCatalogService(
        repository,
        artifacts,  # type: ignore[arg-type]
        manifest_path=scenario_dir / "solution-registration.json",
        component_root=scenario_dir,
    )

    first = service.bootstrap()
    second = service.bootstrap()

    assert first == second
    assert first.persistence == "postgresql-s3"
    assert first.artifact is not None
    assert first.bundle is not None
    assert len(first.bundle.resource_artifacts) == len(first.subject.resources) == 23
    assert artifacts.get_exact(first.artifact) == canonical_bytes(first.subject)

    expected_semantic_source = (scenario_dir / "ontology" / "package.yaml").read_bytes()
    shutil.rmtree(scenario_dir)
    installed = service.materialize(first, scenario_dir.parent / "installed")
    assert installed != scenario_dir
    assert (installed / "ontology" / "package.yaml").read_bytes() == expected_semantic_source
    assert service.materialize(first, scenario_dir.parent / "installed") == installed

    artifacts.objects[
        (first.artifact.bucket, first.artifact.key, first.artifact.version_id)
    ] = b"{}"
    with pytest.raises(SolutionCatalogError, match="artifact mismatch"):
        service.get(first.subject.solution_id, first.subject.solution_version)


def test_solution_bundle_materialization_is_safe_under_concurrent_first_open(
    scenario_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = MemorySolutionRepository()
    artifacts = MemorySolutionArtifacts()
    service = SolutionCatalogService(
        repository,
        artifacts,  # type: ignore[arg-type]
        manifest_path=scenario_dir / "solution-registration.json",
        component_root=scenario_dir,
    )
    record = service.bootstrap()
    install_root = scenario_dir.parent / "installed"
    original_rename = os.rename
    competing_renames = threading.Barrier(2)

    def racing_rename(source: str | bytes | os.PathLike[str] | os.PathLike[bytes], target: str | bytes | os.PathLike[str] | os.PathLike[bytes]) -> None:
        try:
            competing_renames.wait(timeout=0.2)
        except threading.BrokenBarrierError:
            pass
        original_rename(source, target)

    monkeypatch.setattr("ontology_agent.studio.solutions.os.rename", racing_rename)

    with ThreadPoolExecutor(max_workers=2) as pool:
        installed = tuple(pool.map(lambda _: service.materialize(record, install_root), range(2)))

    assert installed[0] == installed[1]
    assert (installed[0] / ".solution-bundle.json").is_file()


def test_template_clone_has_independent_solution_scenario_and_workspace_identity(
    scenario_dir: Path, tmp_path: Path
) -> None:
    repository = MemorySolutionRepository()
    artifacts = MemorySolutionArtifacts()
    service = SolutionCatalogService(
        repository,
        artifacts,  # type: ignore[arg-type]
        manifest_path=scenario_dir / "solution-registration.json",
        component_root=scenario_dir,
    )
    template = service.bootstrap()

    created = service.clone_template(
        template,
        solution_id="ontology.custom.market_activity",
        scenario_id="scenario.custom.market_activity",
        workspace_id="workspace.custom.market_activity",
        display_name=SolutionDisplayName(
            en="Market Activity Review", zh="市场活动分析"
        ),
        description="A separately governed market activity analysis solution.",
    )
    installed = service.materialize(created, tmp_path / "created")

    assert created.subject.solution_id == "ontology.custom.market_activity"
    assert created.subject.scenario_id == "scenario.custom.market_activity"
    assert created.subject.workspace_id == "workspace.custom.market_activity"
    assert created.subject.solution_version == "1.0.0"
    assert created.subject.semantic_source_version == "1.0.0"
    cloned_package = (installed / "ontology" / "package.yaml").read_text(
        encoding="utf-8"
    )
    cloned_descriptor = (installed / "authoring" / "editor-descriptor.json").read_text(
        encoding="utf-8"
    )
    assert "package_id: ontology.custom.market_activity" in cloned_package
    assert "id: scenario.custom.market_activity" in cloned_package
    assert '"workspace_id": "workspace.custom.market_activity"' in cloned_descriptor
    assert created.subject_checksum != template.subject_checksum


def test_blank_solution_contains_only_a_generic_draft_envelope(
    scenario_dir: Path, tmp_path: Path
) -> None:
    repository = MemorySolutionRepository()
    artifacts = MemorySolutionArtifacts()
    service = SolutionCatalogService(
        repository,
        artifacts,  # type: ignore[arg-type]
        manifest_path=scenario_dir / "solution-registration.json",
        component_root=scenario_dir,
    )

    created = service.create_blank(
        solution_id="ontology.custom.blank_case",
        scenario_id="scenario.custom.blank_case",
        workspace_id="workspace.custom.blank_case",
        display_name=SolutionDisplayName(en="Blank Case", zh="空白案例"),
        description="Build a governed ontology from newly registered evidence.",
        owner="ontology.author",
    )
    installed = service.materialize(created, tmp_path / "blank")
    package = load_package(installed / "ontology" / "package.yaml")

    assert created.subject.studio_adapter_id == "studio-adapter.generic@1"
    assert created.subject.semantic_source_version == "0.1.0"
    assert package.package_id == "ontology.custom.blank_case"
    assert package.scenario.definition == (
        "Build a governed ontology from newly registered evidence."
    )
    assert package.scenario.tags == ("solution:blank", "authority:draft")
    assert package.status is Status.CONFIRMED
    assert package.scenario.status is Status.CONFIRMED
    assert package.scenario.market_id is None
    assert package.scenario.timezone is None
    assert package.scenario.data_window_start is None
    assert package.scenario.data_window_end is None
    assert package.sources[0].trust == "assumption"
    assert all(
        not getattr(package, collection)
        for collection in (
            "actors",
            "processes",
            "entities",
            "properties",
            "relationships",
            "dimensions",
            "rules",
            "metrics",
            "data_sources",
            "bindings",
            "joins",
            "sql_contracts",
            "analysis_patterns",
            "policies",
            "questions",
        )
    )
    assert not any(
        token in (installed / "ontology" / "package.yaml").read_text(
            encoding="utf-8"
        ).casefold()
        for token in (
            "average daily turnover",
            "cash trading",
            "market_id:",
            "1970-01-01",
            "ontology_author",
        )
    )
