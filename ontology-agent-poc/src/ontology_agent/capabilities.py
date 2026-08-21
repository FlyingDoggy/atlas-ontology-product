from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .io import sha256_value
from .models import AnalysisPattern, FormulaNode, Metric, OntologyPackage


OPERATOR_VERSION = "1.0.0"


@dataclass(frozen=True)
class OperatorSpec:
    operation: str
    intent: str
    required_metrics: tuple[str, ...]
    required_dimensions: tuple[str, ...]
    required_outputs: tuple[str, ...]
    exactly_two_periods: bool


OPERATORS = {
    spec.operation: spec
    for spec in (
        OperatorSpec(
            "MetricFact",
            "metric_fact",
            ("metric.average_daily_turnover",),
            ("dimension.period",),
            ("period", "turnover", "trading_days", "adt"),
            False,
        ),
        OperatorSpec(
            "ExactPeriodCompare",
            "period_compare",
            ("metric.average_daily_turnover",),
            ("dimension.period",),
            ("current", "previous", "delta", "delta_pct"),
            True,
        ),
        OperatorSpec(
            "SegmentNetChangeShare",
            "segment_contribution",
            ("metric.eligible_turnover",),
            ("dimension.segment", "dimension.period"),
            ("segment", "previous", "current", "delta", "contribution_share"),
            True,
        ),
        OperatorSpec(
            "SequentialCalendarFirst",
            "sequential_decomposition",
            (
                "metric.eligible_turnover",
                "metric.trading_day_count",
                "metric.average_daily_turnover",
            ),
            ("dimension.period",),
            ("calendar_effect", "activity_effect", "residual"),
            True,
        ),
        OperatorSpec(
            "EvidenceAudit",
            "evidence_audit",
            ("metric.average_daily_turnover",),
            (),
            ("definition", "formula", "mappings", "validation", "execution"),
            False,
        ),
        OperatorSpec(
            "TurnoverDriverAnalysis",
            "turnover_driver",
            (
                "metric.eligible_turnover",
                "metric.trading_day_count",
                "metric.average_daily_turnover",
            ),
            ("dimension.period", "dimension.segment"),
            (
                "period_facts",
                "turnover_change",
                "segment_contribution",
                "calendar_effect",
                "activity_effect",
                "residual",
            ),
            True,
        ),
    )
}


INTERNAL_OPERATORS = {
    "EligibleTurnover": OPERATOR_VERSION,
    "SegmentTurnover": OPERATOR_VERSION,
    "TradingDayCount": OPERATOR_VERSION,
    "DeriveADT": OPERATOR_VERSION,
    **{name: OPERATOR_VERSION for name in OPERATORS},
}


UNIT_DIMENSIONS: dict[str, dict[str, int]] = {
    "HKD_MN": {"HKD": 1},
    "TRADING_DAY_COUNT": {"TRADING_DAY": 1},
    "HKD_MN_PER_TRADING_DAY": {"HKD": 1, "TRADING_DAY": -1},
}


def capability_manifest() -> dict[str, Any]:
    return {
        "adapter": "adt-reference",
        "version": OPERATOR_VERSION,
        "base_formula_shapes": ["sum(field_ref)", "count_distinct(field_ref)"],
        "derived_formula_shapes": ["divide(metric_ref,metric_ref)"],
        "operators": {name: asdict(spec) for name, spec in sorted(OPERATORS.items())},
        "internal_operators": dict(sorted(INTERNAL_OPERATORS.items())),
        "source_protocols": ["tabular/v1"],
        "binding_transformations": ["identity"],
        "join_topology": "one-hop-from-base",
        "time_semantics": "date-only",
    }


def capability_checksum() -> str:
    return sha256_value(capability_manifest())


def operator_spec(operation: str) -> OperatorSpec:
    try:
        return OPERATORS[operation]
    except KeyError as exc:
        raise ValueError(f"Unregistered analysis operator: {operation}") from exc


def pattern_for_intent(package: OntologyPackage, intent: str) -> AnalysisPattern:
    matches = [pattern for pattern in package.analysis_patterns if pattern.intent == intent]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one analysis pattern for {intent}; found {len(matches)}")
    pattern = matches[0]
    operator_spec(pattern.operation)
    return pattern


def _metric_ref_pair(node: FormulaNode) -> tuple[str, str] | None:
    if node.op != "divide" or len(node.args) != 2:
        return None
    left, right = node.args
    if left.op != "metric_ref" or right.op != "metric_ref" or not left.ref or not right.ref:
        return None
    return left.ref, right.ref


def _base_formula_field(metric: Metric, expected_op: str) -> str | None:
    if metric.formula.op != expected_op or len(metric.formula.args) != 1:
        return None
    child = metric.formula.args[0]
    return child.ref if child.op == "field_ref" else None


def _unit_divide(numerator: str, denominator: str) -> dict[str, int] | None:
    if numerator not in UNIT_DIMENSIONS or denominator not in UNIT_DIMENSIONS:
        return None
    value = dict(UNIT_DIMENSIONS[numerator])
    for dimension, power in UNIT_DIMENSIONS[denominator].items():
        value[dimension] = value.get(dimension, 0) - power
        if value[dimension] == 0:
            del value[dimension]
    return value


def validate_adt_capability(package: OntologyPackage) -> dict[str, list[str]]:
    errors: dict[str, list[str]] = {}
    metrics = {metric.id: metric for metric in package.metrics}
    properties = {prop.id: prop for prop in package.properties}

    required_metrics = {
        "metric.eligible_turnover",
        "metric.trading_day_count",
        "metric.average_daily_turnover",
    }
    missing_metrics = sorted(required_metrics - set(metrics))
    if missing_metrics:
        errors["metrics"] = [f"missing required metric {metric_id}" for metric_id in missing_metrics]
        return errors

    turnover = metrics["metric.eligible_turnover"]
    turnover_field = _base_formula_field(turnover, "sum")
    turnover_issues: list[str] = []
    if turnover_field != turnover.query.measure_property:
        turnover_issues.append("formula must be sum(query.measure_property)")
    prop = properties.get(turnover_field or "")
    if not prop or prop.unit != turnover.unit or turnover.unit != "HKD_MN":
        turnover_issues.append("turnover formula/property/metric units must resolve to HKD_MN")
    if turnover.aggregation_semantics != "additive":
        turnover_issues.append("turnover must be additive")
    if turnover.null_policy != "fail_validation":
        turnover_issues.append("only fail_validation null policy is supported")
    if turnover.result_grain != ("dimension.period",):
        turnover_issues.append("turnover result grain must be dimension.period")
    if turnover.query.base_source != "source.trade_fact":
        turnover_issues.append("turnover must bind to source.trade_fact")
    if turnover.query.required_joins != ("join.trade_calendar",):
        turnover_issues.append("turnover requires exactly the governed trade-calendar join")
    if turnover.query.filters != ("rule.eligible_trade",):
        turnover_issues.append("turnover requires exactly the eligible-trade rule")
    if (
        turnover.query.period_property != "property.calendar.period_id"
        or turnover.query.date_property != "property.calendar.calendar_date"
        or turnover.query.population_property != "property.calendar.market_id"
    ):
        turnover_issues.append("turnover period, date and population semantics are unsupported")
    if turnover_issues:
        errors[turnover.id] = turnover_issues

    days = metrics["metric.trading_day_count"]
    days_field = _base_formula_field(days, "count_distinct")
    day_issues: list[str] = []
    if days_field != days.query.measure_property:
        day_issues.append("formula must be count_distinct(query.measure_property)")
    if days.unit != "TRADING_DAY_COUNT" or days.aggregation_semantics != "semi_additive":
        day_issues.append("trading-day metric must be semi_additive TRADING_DAY_COUNT")
    if days.result_grain != ("dimension.period",):
        day_issues.append("trading-day result grain must be dimension.period")
    if days.query.base_source != "source.trading_calendar" or days.query.required_joins:
        day_issues.append("trading-day count must bind directly to source.trading_calendar")
    if days.query.filters != ("rule.trading_day",):
        day_issues.append("trading-day count requires exactly the trading-day rule")
    if (
        days.query.period_property != "property.calendar.period_id"
        or days.query.date_property != "property.calendar.calendar_date"
        or days.query.population_property != "property.calendar.market_id"
    ):
        day_issues.append("trading-day period, date and population semantics are unsupported")
    if day_issues:
        errors[days.id] = day_issues

    adt = metrics["metric.average_daily_turnover"]
    adt_issues: list[str] = []
    if _metric_ref_pair(adt.formula) != (turnover.id, days.id):
        adt_issues.append("formula must divide eligible turnover by trading-day count")
    expected_dimension = _unit_divide(turnover.unit, days.unit)
    if adt.unit not in UNIT_DIMENSIONS or UNIT_DIMENSIONS[adt.unit] != expected_dimension:
        adt_issues.append("ADT unit must equal turnover unit divided by trading-day unit")
    if adt.aggregation_semantics != "derived_non_additive":
        adt_issues.append("ADT must be derived_non_additive")
    if adt.zero_denominator_policy != "refuse":
        adt_issues.append("only refuse zero-denominator policy is supported")
    if not (turnover.result_grain == days.result_grain == adt.result_grain):
        adt_issues.append("numerator, denominator and ADT result grains must match")
    if adt.query != adt.query.__class__():
        adt_issues.append("derived ADT must not contain a physical query contract")
    if adt_issues:
        errors[adt.id] = adt_issues

    for metric in (turnover, days):
        missing_query = [
            name
            for name, value in {
                "base_source": metric.query.base_source,
                "measure_property": metric.query.measure_property,
                "period_property": metric.query.period_property,
                "date_property": metric.query.date_property,
                "population_property": metric.query.population_property,
            }.items()
            if not value
        ]
        if missing_query:
            errors.setdefault(metric.id, []).append(
                "missing query contract fields: " + ", ".join(missing_query)
            )
        date_property = properties.get(metric.query.date_property or "")
        if not date_property or date_property.data_type != "date":
            errors.setdefault(metric.id, []).append(
                "ADT adapter supports date-only time semantics; datetime is not supported"
            )

    for binding in package.bindings:
        if binding.transformation != "identity":
            errors.setdefault(binding.id, []).append("only identity transformation is supported")
    for source in package.data_sources:
        if source.protocol != "tabular/v1":
            errors.setdefault(source.id, []).append(
                "only the tabular/v1 source contract is supported by the ADT adapter"
            )

    supported_joins = {"join.trade_calendar", "join.trade_instrument"}
    for join in package.joins:
        if join.id not in supported_joins or join.left_source != "source.trade_fact":
            errors.setdefault(join.id, []).append(
                "only registered one-hop joins from source.trade_fact are supported"
            )

    for pattern in package.analysis_patterns:
        spec = OPERATORS.get(pattern.operation)
        issues: list[str] = []
        if spec is None:
            issues.append(f"unregistered operation {pattern.operation}")
        else:
            if pattern.intent != spec.intent:
                issues.append(f"intent must be {spec.intent}")
            if set(pattern.required_metrics) != set(spec.required_metrics):
                issues.append("required_metrics do not match operator signature")
            if set(pattern.required_dimensions) != set(spec.required_dimensions):
                issues.append("required_dimensions do not match operator signature")
            if not set(spec.required_outputs).issubset(pattern.output_fields):
                issues.append("output_fields do not satisfy operator signature")
            if pattern.exactly_two_periods != spec.exactly_two_periods:
                issues.append("period cardinality does not match operator signature")
        if issues:
            errors[pattern.id] = issues

    if len(package.policies) != 1:
        errors["policies"] = ["ADT adapter requires exactly one policy"]
    else:
        policy = package.policies[0]
        if not {"market-period", "segment-period"}.issubset(policy.allowed_grains):
            errors[policy.id] = ["policy must allow market-period and segment-period only"]

    expected_intents = {spec.intent for spec in OPERATORS.values()}
    actual_intents = {pattern.intent for pattern in package.analysis_patterns}
    if actual_intents != expected_intents:
        errors["analysis_patterns"] = [
            "published adapter must contain exactly the registered intent set"
        ]

    return errors
