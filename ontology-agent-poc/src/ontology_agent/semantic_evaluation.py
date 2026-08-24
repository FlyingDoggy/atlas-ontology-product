from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import Field

from .metric_semantics import canonical_unit, expanded_formula_facts
from .models import OntologyPackage, StrictModel


class MetricSignatureExpectationV1(StrictModel):
    metric_ids: tuple[str, ...] = Field(min_length=1)
    metric_type: Literal["base", "derived"] | None = None
    value_type: Literal["integer", "decimal", "percentage"] | None = None
    unit: str | None = None
    formula_root: str | None = None
    required_operations: tuple[str, ...] = ()
    required_literals: tuple[Decimal, ...] = ()
    required_referenced_units: tuple[str, ...] = ()
    forbidden_referenced_units: tuple[str, ...] = ()


class SemanticAcceptanceProfileV1(StrictModel):
    contract: Literal["semantic-acceptance-profile/v1"] = (
        "semantic-acceptance-profile/v1"
    )
    profile_id: str
    metrics: tuple[MetricSignatureExpectationV1, ...] = Field(min_length=1)


class MetricSignatureResultV1(StrictModel):
    expected_metric_ids: tuple[str, ...]
    resolved_metric_id: str | None
    passed: bool
    defects: tuple[str, ...]


class SemanticAcceptanceReportV1(StrictModel):
    contract: Literal["semantic-acceptance-report/v1"] = (
        "semantic-acceptance-report/v1"
    )
    profile_id: str
    passed: bool
    results: tuple[MetricSignatureResultV1, ...]


def load_semantic_acceptance_profile(path: Path) -> SemanticAcceptanceProfileV1:
    return SemanticAcceptanceProfileV1.model_validate_json(path.read_text(encoding="utf-8"))


def evaluate_semantic_acceptance(
    package: OntologyPackage,
    profile: SemanticAcceptanceProfileV1,
) -> SemanticAcceptanceReportV1:
    """Evaluate a package against an external, non-authoring acceptance profile.

    Profiles are evaluation inputs, never Builder evidence.  The common evaluator
    contains no domain or case branches and grants no publication authority.
    """

    metric_map = {item.id: item for item in package.metrics}
    results: list[MetricSignatureResultV1] = []
    for expectation in profile.metrics:
        metric = next(
            (metric_map[item] for item in expectation.metric_ids if item in metric_map),
            None,
        )
        defects: list[str] = []
        if metric is None:
            defects.append("none of the expected metric identities exists")
        else:
            if expectation.metric_type and metric.metric_type != expectation.metric_type:
                defects.append(
                    f"metric_type {metric.metric_type} != {expectation.metric_type}"
                )
            if expectation.value_type and metric.value_type != expectation.value_type:
                defects.append(
                    f"value_type {metric.value_type} != {expectation.value_type}"
                )
            if expectation.unit and canonical_unit(metric.unit) != canonical_unit(
                expectation.unit
            ):
                defects.append(f"unit {metric.unit} != {expectation.unit}")
            if expectation.formula_root and metric.formula.op != expectation.formula_root:
                defects.append(
                    f"formula root {metric.formula.op} != {expectation.formula_root}"
                )
            operations, literals, referenced_units = expanded_formula_facts(
                metric, metrics=metric_map
            )
            missing_operations = sorted(
                set(expectation.required_operations) - operations
            )
            if missing_operations:
                defects.append(
                    "missing formula operations: " + ", ".join(missing_operations)
                )
            missing_literals = [
                str(value)
                for value in expectation.required_literals
                if value not in literals
            ]
            if missing_literals:
                defects.append(
                    "missing formula literals: " + ", ".join(missing_literals)
                )
            required_units = {
                canonical_unit(item) for item in expectation.required_referenced_units
            }
            missing_units = sorted(
                item for item in required_units if item and item not in referenced_units
            )
            if missing_units:
                defects.append(
                    "missing referenced metric units: " + ", ".join(missing_units)
                )
            forbidden_units = {
                canonical_unit(item) for item in expectation.forbidden_referenced_units
            }
            present_forbidden = sorted(
                item for item in forbidden_units if item and item in referenced_units
            )
            if present_forbidden:
                defects.append(
                    "forbidden referenced metric units: "
                    + ", ".join(present_forbidden)
                )
        results.append(
            MetricSignatureResultV1(
                expected_metric_ids=expectation.metric_ids,
                resolved_metric_id=metric.id if metric else None,
                passed=not defects,
                defects=tuple(defects),
            )
        )
    return SemanticAcceptanceReportV1(
        profile_id=profile.profile_id,
        passed=all(item.passed for item in results),
        results=tuple(results),
    )


def semantic_acceptance_report_json(report: SemanticAcceptanceReportV1) -> str:
    return json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)
