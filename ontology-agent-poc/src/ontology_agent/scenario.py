from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol

from .contracts import RuntimeBindingSpec, VerifiedSnapshot
from .models import AnalysisResponse, OntologyPackage, ValidationCheck


class ScenarioAdapterError(RuntimeError):
    """A selected scenario adapter cannot safely handle the requested operation."""


@dataclass(frozen=True, slots=True)
class BoundAnalysisGoal:
    """Model-neutral, closed goal handed from grounding to a scenario adapter."""

    intent: str
    tool_ids: tuple[str, ...]
    language: str


@dataclass(frozen=True, slots=True)
class ScenarioAdapterDescriptor:
    adapter_id: str
    adapter_version: str
    query_engine_id: str
    query_engine_version: str
    certification_profiles: Mapping[str, str]
    evaluation_suite_id: str
    evaluation_case_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScenarioValidation:
    checks: tuple[ValidationCheck, ...]

    @property
    def failed_check_ids(self) -> tuple[str, ...]:
        return tuple(check.check_id for check in self.checks if check.status == "FAIL")


@dataclass(frozen=True, slots=True)
class ScenarioEvaluation:
    checks: tuple[ValidationCheck, ...]
    suite: Mapping[str, object]

    def validated_suite(
        self, descriptor: ScenarioAdapterDescriptor
    ) -> Mapping[str, object]:
        cases = self.suite.get("cases")
        if not isinstance(cases, list) or not all(
            isinstance(case, dict) for case in cases
        ):
            raise ScenarioAdapterError("Scenario evaluation returned malformed cases")
        case_ids = tuple(case.get("id") for case in cases)
        if self.suite.get("suite_id") != descriptor.evaluation_suite_id:
            raise ScenarioAdapterError("Scenario evaluation suite identity mismatch")
        if (
            self.suite.get("case_count") != len(cases)
            or case_ids != descriptor.evaluation_case_ids
        ):
            raise ScenarioAdapterError(
                "Scenario evaluation does not match the fixed case manifest"
            )
        status = self.suite.get("status")
        if status not in {"PASS", "FAIL"}:
            raise ScenarioAdapterError("Scenario evaluation status is invalid")
        if any(case.get("status") not in {"PASS", "FAIL"} for case in cases):
            raise ScenarioAdapterError("Scenario evaluation case status is invalid")
        if status == "PASS" and (
            any(case.get("status") != "PASS" for case in cases)
            or bool(self.suite.get("oracle_defects"))
        ):
            raise ScenarioAdapterError(
                "Scenario evaluation PASS is inconsistent with its evidence"
            )
        return self.suite


class ScenarioAdapter(Protocol):
    """The narrow seam between common product flow and one scenario implementation.

    The adapter owns scenario capability rules, binding/data checks, certification
    evaluation, request planning/execution and answer/evidence construction. The
    common lifecycle owns artifact persistence, checksums, activation and CAS.
    """

    @property
    def descriptor(self) -> ScenarioAdapterDescriptor: ...

    def build_manifest(self, project_root: Path) -> dict[str, object]: ...

    def validate(
        self,
        package: OntologyPackage,
        *,
        binding: RuntimeBindingSpec | None = None,
        resource_paths: Mapping[str, Path] | None = None,
        dataset_manifest_path: Path | None = None,
    ) -> ScenarioValidation: ...

    def evaluate(
        self,
        snapshot: VerifiedSnapshot,
        *,
        control_dir: Path | None,
        execution_dir: Path,
    ) -> ScenarioEvaluation: ...

    def analyze(
        self,
        snapshot: VerifiedSnapshot,
        *,
        question: str,
        role: str,
        execution_dir: Path,
        bound_goal: BoundAnalysisGoal | None = None,
    ) -> AnalysisResponse: ...


class ScenarioAdapterRegistry:
    """Exact, fail-closed selection; this is not a dynamic plugin platform."""

    def __init__(self, adapters: tuple[ScenarioAdapter, ...]):
        indexed: dict[tuple[str, str], ScenarioAdapter] = {}
        for adapter in adapters:
            descriptor = adapter.descriptor
            key = (descriptor.adapter_id, descriptor.adapter_version)
            if key in indexed:
                raise ValueError(f"Duplicate scenario adapter registration: {key}")
            indexed[key] = adapter
        self._adapters = indexed

    def resolve(self, adapter_id: str, adapter_version: str) -> ScenarioAdapter:
        try:
            return self._adapters[(adapter_id, adapter_version)]
        except KeyError as exc:
            raise ScenarioAdapterError(
                f"No installed scenario adapter matches {adapter_id}@{adapter_version}"
            ) from exc


_DEFAULT_REGISTRY: ScenarioAdapterRegistry | None = None


def default_scenario_adapters() -> ScenarioAdapterRegistry:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        from .adt_scenario import AdtScenarioAdapter
        from .cash_trading_scenario import CashTradingScenarioAdapter

        _DEFAULT_REGISTRY = ScenarioAdapterRegistry(
            (AdtScenarioAdapter(), CashTradingScenarioAdapter())
        )
    return _DEFAULT_REGISTRY
