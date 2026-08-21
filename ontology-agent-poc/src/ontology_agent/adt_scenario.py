from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .capabilities import OPERATOR_VERSION, capability_manifest, validate_adt_capability
from .contracts import (
    CertificationSpec,
    DataResourceBinding,
    RuntimeBindingSpec,
    VerifiedSnapshot,
)
from .data_validation import run_binding_checks, run_certification_checks
from .io import DEFAULT_PROJECT_ROOT, file_checksum
from .models import AnalysisResponse, OntologyPackage, ValidationCheck
from .scenario import (
    BoundAnalysisGoal,
    ScenarioAdapterDescriptor,
    ScenarioAdapterError,
    ScenarioEvaluation,
    ScenarioValidation,
)


ADT_CERTIFICATION_PROFILE = "adt-golden-v1"
ADT_ADAPTER_VERSION = OPERATOR_VERSION
ADT_EVALUATION_SUITE = "adt.tracer.v1.suite"
ADT_EVALUATION_CASE_IDS = (
    "golden.fact.zh",
    "golden.compare.en",
    "golden.driver.zh",
    "golden.evidence.en",
    "boundary.missing_period",
    "boundary.prediction",
    "boundary.raw_detail",
    "boundary.role",
)

_IMPLEMENTATION_FILES = (
    "adt_scenario.py",
    "capabilities.py",
    "data_validation.py",
    "evaluation.py",
    "formula.py",
    "planning.py",
    "runtime.py",
    "scenario.py",
    "sql_compiler.py",
)


def adt_synthetic_binding(*, resource_root_id: str) -> RuntimeBindingSpec:
    return RuntimeBindingSpec(
        environment_id="adt-poc",
        resource_root_id=resource_root_id,
        adapter_id="adt-reference",
        adapter_version=ADT_ADAPTER_VERSION,
        query_engine_id="duckdb.local",
        query_engine_version="1",
        dataset_manifest_ref="data/manifest.json",
        expected_dataset_id="adt-fixture-v1",
        data_resources=(
            DataResourceBinding(
                source_id="source.trade_fact",
                resource_ref="data/trade_fact.csv",
            ),
            DataResourceBinding(
                source_id="source.instrument_dim",
                resource_ref="data/instrument_dim.csv",
            ),
            DataResourceBinding(
                source_id="source.trading_calendar",
                resource_ref="data/trading_calendar.csv",
            ),
        ),
    )


def adt_golden_certification(*, resource_root_id: str) -> CertificationSpec:
    return CertificationSpec(
        profile_id=ADT_CERTIFICATION_PROFILE,
        profile_version="1.0.0",
        resource_root_id=resource_root_id,
        controls_ref="golden",
    )


def _capability_check(package: OntologyPackage) -> ValidationCheck:
    errors = validate_adt_capability(package)
    return ValidationCheck(
        check_id="ADT_CAPABILITY_CONTRACT",
        category="semantic",
        status="PASS" if not errors else "FAIL",
        message="Executable fields match the closed ADT adapter capability set",
        details={"invalid": errors},
    )


class AdtScenarioAdapter:
    """One fixed constructed-synthetic ADT implementation behind the common seam."""

    @property
    def descriptor(self) -> ScenarioAdapterDescriptor:
        return ScenarioAdapterDescriptor(
            adapter_id="adt-reference",
            adapter_version=OPERATOR_VERSION,
            query_engine_id="duckdb.local",
            query_engine_version="1",
            certification_profiles={ADT_CERTIFICATION_PROFILE: "1.0.0"},
            evaluation_suite_id=ADT_EVALUATION_SUITE,
            evaluation_case_ids=ADT_EVALUATION_CASE_IDS,
        )

    def build_manifest(self, project_root: Path = DEFAULT_PROJECT_ROOT) -> dict[str, object]:
        source_root = Path(__file__).resolve().parent
        files = {
            f"src/ontology_agent/{name}": file_checksum(source_root / name)
            for name in _IMPLEMENTATION_FILES
            if (source_root / name).is_file()
        }
        for relative in ("pyproject.toml", "uv.lock"):
            path = project_root / relative
            if path.is_file():
                files[relative] = file_checksum(path)
        return {
            "contract": "scenario-adapter-build/v1",
            "adapter_id": self.descriptor.adapter_id,
            "adapter_version": self.descriptor.adapter_version,
            "evaluation_suite": {
                "suite_id": self.descriptor.evaluation_suite_id,
                "case_ids": list(self.descriptor.evaluation_case_ids),
            },
            "implementation": capability_manifest(),
            "files": dict(sorted(files.items())),
        }

    def validate(
        self,
        package: OntologyPackage,
        *,
        binding: RuntimeBindingSpec | None = None,
        resource_paths: Mapping[str, Path] | None = None,
        dataset_manifest_path: Path | None = None,
    ) -> ScenarioValidation:
        checks: list[ValidationCheck] = [_capability_check(package)]
        if binding is None:
            return ScenarioValidation(checks=tuple(checks))

        descriptor = self.descriptor
        if (
            binding.query_engine_id != descriptor.query_engine_id
            or binding.query_engine_version != descriptor.query_engine_version
        ):
            raise ScenarioAdapterError(
                "The ADT reference adapter requires DuckDB contract v1"
            )
        if resource_paths is None or dataset_manifest_path is None:
            raise ScenarioAdapterError(
                "Runtime resources and dataset manifest are required for binding validation"
            )
        checks.extend(
            run_binding_checks(
                package,
                resource_paths,
                dataset_manifest_path=dataset_manifest_path,
                expected_dataset_id=binding.expected_dataset_id,
            )
        )
        return ScenarioValidation(checks=tuple(checks))

    def evaluate(
        self,
        snapshot: VerifiedSnapshot,
        *,
        control_dir: Path | None,
        execution_dir: Path,
    ) -> ScenarioEvaluation:
        checks: tuple[ValidationCheck, ...] = ()
        if control_dir is not None:
            checks = tuple(
                run_certification_checks(
                    snapshot.package,
                    snapshot.resource_paths,
                    control_dir=control_dir,
                )
            )
        from .evaluation import run_golden_suite

        suite = {
            "suite_id": self.descriptor.evaluation_suite_id,
            **run_golden_suite(snapshot, execution_dir=execution_dir),
        }
        return ScenarioEvaluation(checks=checks, suite=suite)

    def analyze(
        self,
        snapshot: VerifiedSnapshot,
        *,
        question: str,
        role: str,
        execution_dir: Path,
        bound_goal: BoundAnalysisGoal | None = None,
    ) -> AnalysisResponse:
        expected_tools = {
            "period_compare": ("compare_periods",),
            "turnover_driver": ("compare_periods", "rank_contributors"),
            "sequential_decomposition": ("compare_periods", "decompose_change"),
        }
        if bound_goal is not None and expected_tools.get(bound_goal.intent) != bound_goal.tool_ids:
            return AnalysisResponse(
                status="REFUSED",
                answer="The grounded goal does not match the installed ADT capability set.",
                snapshot_checksum=snapshot.snapshot_checksum,
                boundary_code="BOUND_GOAL_CAPABILITY_MISMATCH",
            )
        from .runtime import _analyze_adt_snapshot

        return _analyze_adt_snapshot(
            snapshot,
            question=question,
            role=role,
            execution_dir=execution_dir,
            bound_goal=bound_goal,
        )
