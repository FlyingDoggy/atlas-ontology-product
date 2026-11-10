from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from ontology_agent.adt_scenario import (
    ADT_CERTIFICATION_PROFILE,
    ADT_EVALUATION_CASE_IDS,
    ADT_EVALUATION_SUITE,
    adt_golden_certification,
    adt_synthetic_binding,
)
from ontology_agent.contracts import (
    ActivationConflictError,
    PublicationError,
    RuntimePreparationError,
)
from ontology_agent.lifecycle import (
    AgentRuntime,
    FileResourceResolver,
)
from ontology_agent.models import OntologyPackage
from ontology_agent.release import StudioReleases
from ontology_agent.runtime import analyze_snapshot
from ontology_agent.scenario import ScenarioEvaluation


def _services(
    tmp_path: Path,
    scenario_dir: Path,
) -> tuple[StudioReleases, AgentRuntime]:
    releases = tmp_path / "registry" / "releases"
    runtime = tmp_path / "registry" / "runtime"
    return (
        StudioReleases(releases),
        AgentRuntime(
            release_root=releases,
            runtime_root=runtime,
            resources=FileResourceResolver({"adt-scenario": scenario_dir}),
        ),
    )


def _prepare_certified(
    studio: StudioReleases,
    agent: AgentRuntime,
    package: OntologyPackage,
):
    published = studio.publish(
        package,
        limitations=("constructed synthetic; not customer validated",),
    )
    prepared = agent.prepare(
        published.ref,
        binding=adt_synthetic_binding(resource_root_id="adt-scenario"),
        certification=adt_golden_certification(resource_root_id="adt-scenario"),
    )
    return published, prepared


def test_release_is_portable_semantic_only_and_producer_independent(
    package: OntologyPackage,
    tmp_path: Path,
) -> None:
    first = StudioReleases(tmp_path / "producer-a").publish(
        package,
        limitations=("constructed synthetic",),
    )
    second = StudioReleases(tmp_path / "producer-b").publish(
        package,
        limitations=("constructed synthetic",),
    )

    assert first.ref == second.ref
    assert first.idempotent is False
    assert StudioReleases(tmp_path / "producer-a").publish(
        package,
        limitations=("constructed synthetic",),
    ).idempotent is True

    names = {
        path.relative_to(first.path).as_posix()
        for path in first.path.rglob("*")
        if path.is_file()
    }
    assert {
        "manifest.json",
        "package.json",
        "semantic-validation.json",
        "capability-requirements.json",
        "artifact-inventory.json",
    }.issubset(names)
    assert not {
        "dataset-manifest.json",
        "control-manifest.json",
        "runtime-identity.json",
        "toolchain-manifest.json",
    } & names

    serialized = "\n".join(
        path.read_text(encoding="utf-8")
        for path in first.path.rglob("*")
        if path.is_file() and path.suffix in {".json", ".ttl", ".txt"}
    )
    assert "data/trade_fact.csv" not in serialized
    assert "adt-fixture-v1" not in serialized
    assert "runtime_identity" not in serialized
    assert "toolchain" not in serialized


def test_publish_prepare_and_activate_are_separate_actions(
    package: OntologyPackage,
    scenario_dir: Path,
    tmp_path: Path,
) -> None:
    studio, agent = _services(tmp_path, scenario_dir)
    published, prepared = _prepare_certified(studio, agent, package)

    assert published.ref.checksum != prepared.ref.checksum
    assert agent.active_ref("adt-poc", package.package_id) is None

    receipt = agent.activate(
        prepared.ref,
        require_certification=ADT_CERTIFICATION_PROFILE,
    )
    assert receipt.previous is None
    assert receipt.active == prepared.ref

    active = agent.open_active("adt-poc", package.package_id)
    assert active.snapshot.package == package
    assert active.snapshot.release_checksum == published.ref.checksum
    assert active.snapshot.snapshot_checksum == prepared.ref.checksum


def test_wrong_business_mapping_is_released_but_certification_blocks_activation(
    package: OntologyPackage,
    scenario_dir: Path,
    tmp_path: Path,
) -> None:
    studio, agent = _services(tmp_path, scenario_dir)
    _, good = _prepare_certified(studio, agent, package)
    agent.activate(good.ref, require_certification=ADT_CERTIFICATION_PROFILE)

    bindings = tuple(
        binding.model_copy(update={"column": "order_value_hkd_mn"})
        if binding.id == "binding.trade.executed_value"
        else binding
        for binding in package.bindings
    )
    changed = package.model_copy(update={"version": "1.2.1", "bindings": bindings})
    release = studio.publish(changed, limitations=("constructed synthetic",))
    assert release.validation_status == "PASS"

    with pytest.raises(RuntimePreparationError, match="certification"):
        agent.prepare(
            release.ref,
            binding=adt_synthetic_binding(resource_root_id="adt-scenario"),
            certification=adt_golden_certification(resource_root_id="adt-scenario"),
        )

    assert agent.active_ref("adt-poc", package.package_id) == good.ref


def test_uncertified_snapshot_cannot_enter_adt_demo_channel(
    package: OntologyPackage,
    scenario_dir: Path,
    tmp_path: Path,
) -> None:
    studio, agent = _services(tmp_path, scenario_dir)
    release = studio.publish(package)
    prepared = agent.prepare(
        release.ref,
        binding=adt_synthetic_binding(resource_root_id="adt-scenario"),
    )

    with pytest.raises(PublicationError, match="certification"):
        agent.activate(
            prepared.ref,
            require_certification=ADT_CERTIFICATION_PROFILE,
        )
    assert agent.active_ref("adt-poc", package.package_id) is None


def test_data_change_invalidates_runtime_not_portable_release(
    package: OntologyPackage,
    scenario_dir: Path,
    tmp_path: Path,
) -> None:
    studio, agent = _services(tmp_path, scenario_dir)
    release, prepared = _prepare_certified(studio, agent, package)
    agent.activate(prepared.ref, require_certification=ADT_CERTIFICATION_PROFILE)

    trade_path = scenario_dir / "data" / "trade_fact.csv"
    trade_path.write_text(
        trade_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    with pytest.raises(PublicationError, match="dataset"):
        agent.open_active("adt-poc", package.package_id)
    assert studio.load(release.ref).package == package


def test_release_artifact_tamper_fails_before_runtime_binding(
    package: OntologyPackage,
    scenario_dir: Path,
    tmp_path: Path,
) -> None:
    studio, agent = _services(tmp_path, scenario_dir)
    release = studio.publish(package)
    package_path = release.path / "package.json"
    payload = json.loads(package_path.read_text(encoding="utf-8"))
    payload["version"] = "9.9.9"
    package_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(PublicationError, match="artifact checksum"):
        agent.prepare(
            release.ref,
            binding=adt_synthetic_binding(resource_root_id="adt-scenario"),
        )


def test_bound_snapshot_runs_after_producer_release_is_unavailable(
    package: OntologyPackage,
    scenario_dir: Path,
    tmp_path: Path,
) -> None:
    studio, agent = _services(tmp_path, scenario_dir)
    release, prepared = _prepare_certified(studio, agent, package)
    agent.activate(prepared.ref, require_certification=ADT_CERTIFICATION_PROFILE)
    shutil.move(release.path, tmp_path / "producer-release-offline")

    active = agent.open_active("adt-poc", package.package_id)
    assert active.snapshot.release_checksum == release.ref.checksum


def test_analysis_request_does_not_rerun_certification(
    package: OntologyPackage,
    scenario_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ontology_agent.data_validation as data_validation_module
    import ontology_agent.evaluation as evaluation_module

    studio, agent = _services(tmp_path, scenario_dir)
    _, prepared = _prepare_certified(studio, agent, package)
    agent.activate(prepared.ref, require_certification=ADT_CERTIFICATION_PROFILE)
    active = agent.open_active("adt-poc", package.package_id)

    def forbidden(*_: object, **__: object) -> None:
        raise AssertionError("request path must not rerun certification")

    monkeypatch.setattr(data_validation_module, "run_certification_checks", forbidden)
    monkeypatch.setattr(evaluation_module, "run_golden_suite", forbidden)
    response = analyze_snapshot(
        active.snapshot,
        question="Compare Q4 ADT with Q3 in 2025.",
        role="MarketAnalyst",
        execution_dir=tmp_path / "executions",
    )
    assert response.status == "ANSWERED"


def test_activation_supports_cas_and_explicit_rollback(
    package: OntologyPackage,
    scenario_dir: Path,
    tmp_path: Path,
) -> None:
    studio, agent = _services(tmp_path, scenario_dir)
    _, first = _prepare_certified(studio, agent, package)
    first_activation = agent.activate(
        first.ref,
        require_certification=ADT_CERTIFICATION_PROFILE,
    )
    next_package = package.model_copy(update={"version": "1.2.1"})
    _, second = _prepare_certified(studio, agent, next_package)
    agent.activate(
        second.ref,
        expected_current=first_activation.active,
        require_certification=ADT_CERTIFICATION_PROFILE,
    )

    with pytest.raises(ActivationConflictError):
        agent.activate(first.ref, expected_current=first_activation.active)

    rollback = agent.activate(
        first.ref,
        expected_current=second.ref,
        require_certification=ADT_CERTIFICATION_PROFILE,
    )
    assert rollback.previous == second.ref
    assert agent.active_ref("adt-poc", package.package_id) == first.ref


def test_rollback_target_survives_runtime_service_recreation(
    package: OntologyPackage,
    scenario_dir: Path,
    tmp_path: Path,
) -> None:
    studio, agent = _services(tmp_path, scenario_dir)
    _, first = _prepare_certified(studio, agent, package)
    agent.activate(first.ref, require_certification=ADT_CERTIFICATION_PROFILE)
    next_package = package.model_copy(update={"version": "1.2.1"})
    _, second = _prepare_certified(studio, agent, next_package)
    agent.activate(
        second.ref,
        expected_current=first.ref,
        require_certification=ADT_CERTIFICATION_PROFILE,
    )

    recreated = AgentRuntime(
        release_root=tmp_path / "registry" / "releases",
        runtime_root=tmp_path / "registry" / "runtime",
        resources=FileResourceResolver({"adt-scenario": scenario_dir}),
    )

    assert recreated.active_ref("adt-poc", package.package_id) == second.ref
    assert recreated.rollback_target("adt-poc", package.package_id) == first.ref


def test_active_verification_binds_the_exact_snapshot_and_eight_cases(
    package: OntologyPackage,
    scenario_dir: Path,
    tmp_path: Path,
) -> None:
    studio, agent = _services(tmp_path, scenario_dir)
    _, prepared = _prepare_certified(studio, agent, package)
    agent.activate(prepared.ref, require_certification=ADT_CERTIFICATION_PROFILE)

    verification = agent.verify_active(
        "adt-poc",
        package.package_id,
        expected_snapshot=prepared.ref,
        execution_dir=tmp_path / "verification-executions",
    )

    assert verification.status == "PASS"
    assert verification.snapshot == prepared.ref
    assert verification.case_count == 8
    assert len(verification.cases) == 8
    assert all(case.status == "PASS" for case in verification.cases)
    assert verification.oracle_defects == {}


def test_active_verification_rejects_a_stale_expected_snapshot(
    package: OntologyPackage,
    scenario_dir: Path,
    tmp_path: Path,
) -> None:
    studio, agent = _services(tmp_path, scenario_dir)
    _, first = _prepare_certified(studio, agent, package)
    agent.activate(first.ref, require_certification=ADT_CERTIFICATION_PROFILE)
    second_package = package.model_copy(update={"version": "1.2.1"})
    _, second = _prepare_certified(studio, agent, second_package)
    agent.activate(
        second.ref,
        expected_current=first.ref,
        require_certification=ADT_CERTIFICATION_PROFILE,
    )

    with pytest.raises(ActivationConflictError, match="does not match"):
        agent.verify_active(
            "adt-poc",
            package.package_id,
            expected_snapshot=first.ref,
            execution_dir=tmp_path / "verification-executions",
        )


def test_active_verification_rejects_pointer_change_during_suite(
    package: OntologyPackage,
    scenario_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    studio, agent = _services(tmp_path, scenario_dir)
    _, first = _prepare_certified(studio, agent, package)
    agent.activate(first.ref, require_certification=ADT_CERTIFICATION_PROFILE)
    second_package = package.model_copy(update={"version": "1.2.1"})
    _, second = _prepare_certified(studio, agent, second_package)

    def switch_active(*_: object, **__: object) -> ScenarioEvaluation:
        agent.activate(
            second.ref,
            expected_current=first.ref,
            require_certification=ADT_CERTIFICATION_PROFILE,
        )
        return ScenarioEvaluation(
            checks=(),
            suite={
                "suite_id": ADT_EVALUATION_SUITE,
                "status": "PASS",
                "case_count": len(ADT_EVALUATION_CASE_IDS),
                "cases": [
                    {"id": case_id, "status": "PASS", "defects": []}
                    for case_id in ADT_EVALUATION_CASE_IDS
                ],
                "oracle": "constructed synthetic control oracle",
                "oracle_defects": {},
            },
        )

    adapter = agent.adapters.resolve("adt-reference", "1.0.0")
    monkeypatch.setattr(adapter, "evaluate", switch_active)
    with pytest.raises(ActivationConflictError, match="changed during"):
        agent.verify_active(
            "adt-poc",
            package.package_id,
            expected_snapshot=first.ref,
            execution_dir=tmp_path / "verification-executions",
        )
