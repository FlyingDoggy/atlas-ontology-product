from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ontology_agent.adt_scenario import (
    adt_golden_certification,
    adt_synthetic_binding,
)
from ontology_agent.contracts import RuntimePreparationError
from ontology_agent.lifecycle import (
    AgentRuntime,
    FileResourceResolver,
)
from ontology_agent.release import StudioReleases
from ontology_agent.studio.workspace import (
    DraftUpdate,
    DraftWorkspaceService,
    WorkspaceConflictError,
    WorkspaceStateError,
)
from ontology_agent.studio.workspace_store import (
    WorkspaceIdentity,
    WorkspaceRevisionSubjectV1,
    _same_revision_content,
)


class CapturingWorkspaceStore:
    def __init__(self) -> None:
        self.payload: dict[str, object] | None = None

    def load(self, identity: WorkspaceIdentity) -> None:
        return None

    def commit(self, identity: WorkspaceIdentity, **kwargs: object) -> SimpleNamespace:
        self.payload = kwargs["payload"]  # type: ignore[assignment]
        return SimpleNamespace(token="captured")

    def list_revisions(self, identity: WorkspaceIdentity) -> tuple[()]:
        return ()


def test_revision_identity_treats_legacy_missing_optional_operations_as_null() -> None:
    identity = WorkspaceIdentity(
        solution_id="atlas.adt.reference",
        solution_version="1.2.0",
        workspace_id="workspace.adt.reference",
        studio_adapter_id="studio.adapter.adt@1",
    )
    payload = {
        "workspace_id": identity.workspace_id,
        "revision": 1,
        "draft_checksum": "a" * 64,
        "record_checksum": "b" * 64,
    }
    legacy = WorkspaceRevisionSubjectV1(
        identity=identity,
        revision=1,
        draft_checksum="a" * 64,
        record_checksum="b" * 64,
        payload=payload,
    )
    current = WorkspaceRevisionSubjectV1(
        identity=identity,
        revision=1,
        draft_checksum="a" * 64,
        record_checksum="b" * 64,
        payload={**payload, "package_operations": None},
    )

    assert _same_revision_content(legacy, current)
    changed = current.model_copy(
        update={"payload": {**payload, "package_operations": [{"path": "metrics"}]}}
    )
    assert not _same_revision_content(legacy, changed)


def _service(
    tmp_path: Path, scenario_dir: Path
) -> tuple[DraftWorkspaceService, StudioReleases]:
    releases = StudioReleases(tmp_path / "registry" / "releases")
    return (
        DraftWorkspaceService(
            tmp_path / "studio" / "workspaces",
            scenario_dir,
            releases,
        ),
        releases,
    )


def test_intake_creates_a_traced_fixed_adt_draft(
    scenario_dir: Path, tmp_path: Path
) -> None:
    service, _ = _service(tmp_path, scenario_dir)

    workspace = service.get()
    intake = service.get_intake()

    assert workspace.revision == 1
    assert workspace.target_version == "1.2.1"
    assert workspace.validation.status == "NOT_RUN"
    assert workspace.draft.amount_mapping == "executed_value_hkd_mn"
    assert workspace.draft.eligibility_rule.include_status == "EXECUTED"
    assert workspace.draft.eligibility_rule.exclude_cancelled is True
    assert workspace.draft.allowed_dimensions == (
        "dimension.period",
        "dimension.segment",
    )
    assert len(intake.assets) == 5
    assert len(intake.anchors) == 4
    assert {anchor.field for anchor in intake.anchors} == {
        "metric_definition",
        "eligibility_rule",
        "allowed_dimensions",
        "amount_mapping",
    }
    sql = next(asset for asset in intake.assets if asset.kind == "sql")
    assert sql.processing_mode == "REGISTERED_NOT_PARSED"
    assert intake.claim_ceiling == "CONSTRUCTED_SYNTHETIC_NOT_CUSTOMER_VALIDATED"
    assert all(len(asset.checksum) == 64 for asset in intake.assets)
    assert all(gap.status == "OPEN" for gap in intake.gaps)
    assert workspace.modified_fields == ()
    assert len(service.list_revisions()) == 1


def test_template_workspace_uses_the_registered_custom_identity(
    scenario_dir: Path, tmp_path: Path
) -> None:
    store = CapturingWorkspaceStore()
    identity = WorkspaceIdentity(
        solution_id="ontology.exchange_analytics.adt",
        solution_version="1.2.0",
        workspace_id="workspace.custom.adt_copy",
        studio_adapter_id="studio-adapter.adt.reference@1",
    )
    service = DraftWorkspaceService(
        tmp_path / "studio" / "workspaces",
        scenario_dir,
        StudioReleases(tmp_path / "registry" / "releases"),
        state_store=store,  # type: ignore[arg-type]
        identity=identity,
    )

    # A durable service instance is already bound to one registered identity.
    # Callers such as the async construction worker therefore must be able to
    # resolve that identity without falling back to the bundled ADT workspace.
    workspace = service.get()

    assert workspace.workspace_id == identity.workspace_id
    assert store.payload is not None
    assert store.payload["workspace_id"] == identity.workspace_id


def test_revision_validation_and_publication_are_exact_and_separate(
    scenario_dir: Path, tmp_path: Path
) -> None:
    service, releases = _service(tmp_path, scenario_dir)
    initial = service.get()

    changed = service.patch(
        DraftUpdate(metric_definition="Reviewed synthetic ADT definition."),
        expected_revision=initial.revision,
    )
    assert changed.revision == 2
    assert changed.validation.status == "STALE"
    assert changed.draft_checksum != initial.draft_checksum
    assert changed.modified_fields == ("metric_definition",)
    revisions = service.list_revisions()
    assert [record.revision for record in revisions] == [1, 2]
    assert revisions[0].draft_checksum == initial.draft_checksum
    assert revisions[1].draft_checksum == changed.draft_checksum

    with pytest.raises(WorkspaceConflictError):
        service.patch(
            DraftUpdate(metric_definition="Lost update"),
            expected_revision=initial.revision,
        )
    with pytest.raises(WorkspaceStateError, match="must pass validation"):
        service.publish(expected_revision=changed.revision)

    validated = service.validate(expected_revision=changed.revision)
    assert validated.validation.status == "PASS"
    assert validated.validation.revision == changed.revision
    assert validated.validation.draft_checksum == changed.draft_checksum
    assert service.list_revisions() == revisions

    published_workspace, publication = service.publish(
        expected_revision=validated.revision
    )
    assert publication.ref.version == "1.2.1"
    assert published_workspace.last_published == publication.ref
    assert not (tmp_path / "registry" / "runtime" / "active").exists()
    released = releases.load(publication.ref)
    adt = next(
        metric
        for metric in released.package.metrics
        if metric.id == "metric.average_daily_turnover"
    )
    assert adt.definition == "Reviewed synthetic ADT definition."

    manifest_before = (publication.path / "manifest.json").read_bytes()
    next_draft = service.patch(
        DraftUpdate(metric_definition="Another reviewed definition."),
        expected_revision=published_workspace.revision,
    )
    assert next_draft.target_version == "1.2.2"
    assert next_draft.validation.status == "STALE"
    assert (publication.path / "manifest.json").read_bytes() == manifest_before


def test_semantically_valid_wrong_amount_mapping_is_stopped_by_certification(
    scenario_dir: Path, tmp_path: Path
) -> None:
    service, releases = _service(tmp_path, scenario_dir)
    initial = service.get()
    changed = service.patch(
        DraftUpdate(amount_mapping="order_value_hkd_mn"),
        expected_revision=initial.revision,
    )
    validated = service.validate(expected_revision=changed.revision)
    assert validated.validation.status == "PASS"
    _, publication = service.publish(expected_revision=validated.revision)

    agent = AgentRuntime(
        release_root=releases.root,
        runtime_root=tmp_path / "registry" / "runtime",
        resources=FileResourceResolver({"adt-scenario": scenario_dir}),
    )
    with pytest.raises(RuntimePreparationError, match="certification"):
        agent.prepare(
            publication.ref,
            binding=adt_synthetic_binding(resource_root_id="adt-scenario"),
            certification=adt_golden_certification(resource_root_id="adt-scenario"),
        )


def test_revision_record_tamper_is_detected(
    scenario_dir: Path, tmp_path: Path
) -> None:
    service, _ = _service(tmp_path, scenario_dir)
    service.get()
    record_path = (
        tmp_path
        / "studio"
        / "workspaces"
        / "workspace.adt.reference"
        / "revisions"
        / "r000001.json"
    )
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    payload["draft"]["metric_definition"] = "tampered"
    record_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(WorkspaceStateError, match="checksum"):
        service.list_revisions()
