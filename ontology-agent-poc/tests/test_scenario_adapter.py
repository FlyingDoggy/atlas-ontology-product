from __future__ import annotations

from pathlib import Path

import pytest

from ontology_agent.adt_scenario import (
    ADT_CERTIFICATION_PROFILE,
    ADT_EVALUATION_SUITE,
    AdtScenarioAdapter,
    adt_golden_certification,
    adt_synthetic_binding,
)
from ontology_agent.contracts import RuntimePreparationError
from ontology_agent.lifecycle import (
    AgentRuntime,
    FileResourceResolver,
)
from ontology_agent.models import AnalysisResponse, OntologyPackage
from ontology_agent.release import StudioReleases
from ontology_agent.runtime import analyze_snapshot
from ontology_agent.scenario import (
    ScenarioAdapterError,
    ScenarioAdapterRegistry,
    ScenarioEvaluation,
    ScenarioValidation,
)


class RecordingAdtAdapter(AdtScenarioAdapter):
    def __init__(self) -> None:
        self.validation_calls = 0
        self.evaluation_calls = 0
        self.analysis_calls = 0

    def validate(self, *args: object, **kwargs: object) -> ScenarioValidation:
        self.validation_calls += 1
        return super().validate(*args, **kwargs)

    def evaluate(self, *args: object, **kwargs: object) -> ScenarioEvaluation:
        self.evaluation_calls += 1
        return super().evaluate(*args, **kwargs)

    def analyze(self, *args: object, **kwargs: object) -> AnalysisResponse:
        self.analysis_calls += 1
        return super().analyze(*args, **kwargs)


class MalformedEvidenceAdapter(AdtScenarioAdapter):
    def evaluate(self, *args: object, **kwargs: object) -> ScenarioEvaluation:
        return ScenarioEvaluation(
            checks=(),
            suite={
                "suite_id": ADT_EVALUATION_SUITE,
                "status": "PASS",
                "case_count": 0,
                "cases": [],
                "oracle": "invalid empty evidence",
                "oracle_defects": {},
            },
        )


def _composition(
    tmp_path: Path,
    scenario_dir: Path,
    adapter: AdtScenarioAdapter,
) -> tuple[StudioReleases, AgentRuntime]:
    releases = tmp_path / "releases"
    return (
        StudioReleases(releases),
        AgentRuntime(
            release_root=releases,
            runtime_root=tmp_path / "runtime",
            resources=FileResourceResolver({"adt-scenario": scenario_dir}),
            adapters=ScenarioAdapterRegistry((adapter,)),
        ),
    )


def test_registry_selects_exact_identity_and_rejects_unknown() -> None:
    adapter = AdtScenarioAdapter()
    registry = ScenarioAdapterRegistry((adapter,))
    assert registry.resolve("adt-reference", "1.0.0") is adapter
    with pytest.raises(ScenarioAdapterError, match="No installed scenario adapter"):
        registry.resolve("adt-reference", "2.0.0")
    with pytest.raises(ValueError, match="Duplicate scenario adapter"):
        ScenarioAdapterRegistry((adapter, AdtScenarioAdapter()))


def test_unknown_adapter_fails_before_runtime_resource_binding(
    package: OntologyPackage,
    scenario_dir: Path,
    tmp_path: Path,
) -> None:
    studio, agent = _composition(tmp_path, scenario_dir, AdtScenarioAdapter())
    release = studio.publish(package)
    unsupported = adt_synthetic_binding(resource_root_id="missing-root").model_copy(
        update={"adapter_id": "not-installed"}
    )
    with pytest.raises(RuntimePreparationError, match="No installed scenario adapter"):
        agent.prepare(release.ref, binding=unsupported)


def test_lifecycle_and_analysis_use_the_exact_bound_adapter(
    package: OntologyPackage,
    scenario_dir: Path,
    tmp_path: Path,
) -> None:
    adapter = RecordingAdtAdapter()
    studio, agent = _composition(tmp_path, scenario_dir, adapter)
    release = studio.publish(package)
    prepared = agent.prepare(
        release.ref,
        binding=adt_synthetic_binding(resource_root_id="adt-scenario"),
        certification=adt_golden_certification(resource_root_id="adt-scenario"),
    )
    agent.activate(
        prepared.ref,
        require_certification=ADT_CERTIFICATION_PROFILE,
    )
    snapshot = agent.open_active("adt-poc", package.package_id).snapshot
    assert snapshot.scenario_adapter is adapter

    response = analyze_snapshot(
        snapshot,
        question="Compare Q4 ADT with Q3 in 2025.",
        role="MarketAnalyst",
        execution_dir=tmp_path / "executions",
    )
    verification = agent.verify_active(
        "adt-poc",
        package.package_id,
        expected_snapshot=prepared.ref,
        execution_dir=tmp_path / "verification",
    )

    assert response.status == "ANSWERED"
    assert verification.status == "PASS"
    assert adapter.validation_calls == 1
    assert adapter.evaluation_calls == 2
    assert adapter.analysis_calls == 17


def test_lifecycle_rejects_adapter_pass_without_required_evidence(
    package: OntologyPackage,
    scenario_dir: Path,
    tmp_path: Path,
) -> None:
    studio, agent = _composition(tmp_path, scenario_dir, MalformedEvidenceAdapter())
    release = studio.publish(package)
    with pytest.raises(
        RuntimePreparationError,
        match="Scenario certification evidence is invalid",
    ):
        agent.prepare(
            release.ref,
            binding=adt_synthetic_binding(resource_root_id="adt-scenario"),
            certification=adt_golden_certification(resource_root_id="adt-scenario"),
        )


def test_common_lifecycle_has_no_direct_adt_execution_dependencies() -> None:
    source = (
        Path(__file__).parents[1]
        / "src"
        / "ontology_agent"
        / "lifecycle.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "validate_adt_capability",
        "run_binding_checks",
        "run_certification_checks",
        "run_golden_suite",
    ):
        assert forbidden not in source
