from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from .capabilities import INTERNAL_OPERATORS, pattern_for_intent
from .io import sha256_value
from .models import (
    AnalysisPlan,
    AnalysisResponse,
    AtomicQueryContract,
    OntologyPackage,
    PlanStep,
)


@dataclass(frozen=True)
class ResolvedRequest:
    intent: str
    periods: tuple[str, ...]


def _boundary(
    status: Literal["CLARIFY", "REFUSED"], answer: str, code: str
) -> AnalysisResponse:
    return AnalysisResponse(status=status, answer=answer, boundary_code=code)


def _extract_periods(question: str, package: OntologyPackage) -> tuple[tuple[str, ...], tuple[str, ...]]:
    available = {period.id for period in package.scenario.periods}
    found: set[str] = set()
    unknown: set[str] = set()
    for explicit in re.findall(r"20\d{2}-Q[1-4]", question.upper()):
        (found if explicit in available else unknown).add(explicit)

    lower = question.lower()
    chinese_quarters = {"一": 1, "二": 2, "三": 3, "四": 4}
    for left, right in re.findall(
        r"第?([一二三四])(?:季度|季)?(?:和|、|及|与)第?([一二三四])(?:季度|季)",
        question,
    ):
        for quarter in (chinese_quarters[left], chinese_quarters[right]):
            candidates = sorted(
                period for period in available if period.endswith(f"-Q{quarter}")
            )
            if len(candidates) == 1:
                found.add(candidates[0])
    quarter_patterns = {
        1: [r"\bq1\b", "第一季度", "一季度", "第一季"],
        2: [r"\bq2\b", "第二季度", "二季度", "第二季"],
        3: [r"\bq3\b", "第三季度", "三季度", "第三季"],
        4: [r"\bq4\b", "第四季度", "四季度", "第四季"],
    }
    for quarter, patterns in quarter_patterns.items():
        if not any(re.search(pattern, lower) for pattern in patterns):
            continue
        candidates = sorted(period for period in available if period.endswith(f"-Q{quarter}"))
        if len(candidates) == 1:
            found.add(candidates[0])

    ordered = tuple(
        period.id
        for period in sorted(package.scenario.periods, key=lambda item: item.start)
        if period.id in found
    )
    return ordered, tuple(sorted(unknown))


def resolve_request(
    package: OntologyPackage,
    question: str,
    role: str,
    bound_intent: str | None = None,
) -> ResolvedRequest | AnalysisResponse:
    policy = package.policies[0]
    if role in policy.denied_roles or role not in policy.allowed_roles:
        return _boundary(
            "REFUSED",
            f"Role {role} is not permitted to use this aggregate analytics scenario.",
            "ROLE_DENIED",
        )

    lower = question.lower()
    if any(token in lower for token in ["predict", "forecast", "预测", "预估", "next quarter"]):
        return _boundary(
            "REFUSED",
            "This ontology snapshot supports governed historical analysis, not prediction.",
            "UNSUPPORTED_PREDICTION",
        )
    if any(
        token in lower
        for token in [
            "every trade",
            "trade id",
            "trade_id",
            "instrument id",
            "instrument_id",
            "raw row",
            "raw detail",
            "逐笔",
            "成交明细",
            "交易明细",
        ]
    ):
        return _boundary(
            "REFUSED",
            "Raw trade-level data and denied identifiers are outside the approved aggregate grain.",
            "RAW_DETAIL_DENIED",
        )

    periods, unknown = _extract_periods(question, package)
    if unknown:
        return _boundary(
            "CLARIFY",
            f"The requested period is not defined in this published scenario: {', '.join(unknown)}.",
            "UNKNOWN_PERIOD",
        )

    registered_intents = {pattern.intent for pattern in package.analysis_patterns}
    if bound_intent is not None and (
        bound_intent not in registered_intents
        or bound_intent
        not in {"period_compare", "turnover_driver", "sequential_decomposition"}
    ):
        return _boundary(
            "REFUSED",
            "The grounded goal does not match an executable analysis pattern in this snapshot.",
            "BOUND_GOAL_DENIED",
        )

    evidence_terms = ["evidence", "lineage", "definition", "mapping", "证据", "血缘", "定义", "映射"]
    if bound_intent is None and any(term in lower for term in evidence_terms):
        return ResolvedRequest(intent="evidence_audit", periods=periods)

    driver_terms = ["why", "driver", "contribut", "segment", "为什么", "原因", "驱动", "贡献", "板块"]
    compare_terms = ["compare", "versus", " vs ", "change", "delta", "变化", "较", "相比"]
    is_metric = any(term in lower for term in ["adt", "turnover", "成交额", "平均每日"])
    if bound_intent is not None:
        intent = bound_intent
        required_periods = 2
    elif any(term in lower for term in driver_terms):
        intent = "turnover_driver"
        required_periods = 2
    elif any(term in lower for term in compare_terms):
        intent = "period_compare"
        required_periods = 2
    elif is_metric:
        intent = "metric_fact"
        required_periods = 1
    else:
        return _boundary(
            "REFUSED",
            "The question does not match a registered analysis pattern in this snapshot.",
            "UNSUPPORTED_INTENT",
        )

    if not periods and required_periods == 2 and len(package.scenario.periods) == 2:
        periods = tuple(
            period.id
            for period in sorted(package.scenario.periods, key=lambda item: item.start)
        )
    if len(periods) < required_periods:
        return _boundary(
            "CLARIFY",
            "Please specify the reporting period" + ("s to compare." if required_periods == 2 else "."),
            "MISSING_PERIOD",
        )
    if required_periods == 2 and len(periods) != 2:
        return _boundary(
            "CLARIFY",
            "This registered comparison requires exactly two governed periods.",
            "PERIOD_CARDINALITY",
        )
    return ResolvedRequest(intent=intent, periods=periods)


def _contract(
    package: OntologyPackage,
    analysis_pattern: str,
    operation: str,
    metric: str,
    periods: tuple[str, ...],
    dimensions: tuple[str, ...],
    filters: tuple[str, ...],
    role: str,
    snapshot_checksum: str,
) -> AtomicQueryContract:
    pattern = next(item for item in package.analysis_patterns if item.id == analysis_pattern)
    policy = package.policies[0]
    metric_object = next(item for item in package.metrics if item.id == metric)
    joins = {join.id: join for join in package.joins}
    source_ids: list[str] = []
    if metric_object.query.base_source:
        source_ids.append(metric_object.query.base_source)
        source_ids.extend(
            joins[join_id].right_source for join_id in metric_object.query.required_joins
        )
    period_bounds = tuple(
        period for period in package.scenario.periods if period.id in periods
    )
    result_grain = (
        ("segment-period",)
        if "dimension.segment" in dimensions
        else ("market-period",)
    )
    if operation != "EvidenceAudit" and any(
        grain not in policy.allowed_grains for grain in result_grain
    ):
        raise ValueError(
            f"Policy {policy.id} does not allow result grain {result_grain}"
        )
    policy_decision_id = "policy-decision." + sha256_value(
        {
            "policy": policy.id,
            "role": role,
            "operation": operation,
            "dimensions": dimensions,
            "result_grain": result_grain,
            "periods": periods,
            "snapshot": snapshot_checksum,
        }
    )[:16]
    payload = {
        "operation": operation,
        "operator_version": INTERNAL_OPERATORS[operation],
        "analysis_pattern": pattern.id,
        "scenario_id": package.scenario.id,
        "metric": metric,
        "periods": periods,
        "period_bounds": period_bounds,
        "dimensions": dimensions,
        "result_grain": result_grain,
        "filters": filters,
        "source_ids": tuple(dict.fromkeys(source_ids)),
        "population_id": f"{package.scenario.id}:{package.scenario.market_id}",
        "market_id": package.scenario.market_id,
        "timezone": package.scenario.timezone,
        "policy_id": policy.id,
        "policy_decision_id": policy_decision_id,
        "role": role,
        "snapshot_checksum": snapshot_checksum,
    }
    hash_payload = {
        **payload,
        "period_bounds": [period.model_dump(mode="json") for period in period_bounds],
    }
    return AtomicQueryContract(
        contract_id="aqc." + sha256_value(hash_payload)[:16],
        **payload,
    )


def build_plan(
    package: OntologyPackage,
    request: ResolvedRequest,
    question: str,
    role: str,
    snapshot_checksum: str,
) -> AnalysisPlan:
    steps: list[PlanStep] = []
    pattern = pattern_for_intent(package, request.intent)
    if request.intent == "evidence_audit":
        contract = _contract(
            package,
            pattern.id,
            "EvidenceAudit",
            "metric.average_daily_turnover",
            request.periods,
            (),
            (),
            role,
            snapshot_checksum,
        )
        steps.append(PlanStep(step_id="evidence", operation="EvidenceAudit", contract=contract))
    else:
        turnover = _contract(
            package,
            pattern.id,
            "EligibleTurnover",
            "metric.eligible_turnover",
            request.periods,
            ("dimension.period",),
            ("rule.eligible_trade",),
            role,
            snapshot_checksum,
        )
        days = _contract(
            package,
            pattern.id,
            "TradingDayCount",
            "metric.trading_day_count",
            request.periods,
            ("dimension.period",),
            ("rule.trading_day",),
            role,
            snapshot_checksum,
        )
        steps.extend(
            [
                PlanStep(step_id="turnover", operation="EligibleTurnover", contract=turnover),
                PlanStep(step_id="trading_days", operation="TradingDayCount", contract=days),
            ]
        )
        if request.intent == "turnover_driver":
            segment = _contract(
                package,
                pattern.id,
                "SegmentTurnover",
                "metric.eligible_turnover",
                request.periods,
                ("dimension.period", "dimension.segment"),
                ("rule.eligible_trade",),
                role,
                snapshot_checksum,
            )
            steps.append(
                PlanStep(step_id="segments", operation="SegmentTurnover", contract=segment)
            )
        derived_operation = pattern.operation
        derived = _contract(
            package,
            pattern.id,
            derived_operation,
            "metric.average_daily_turnover",
            request.periods,
            ("dimension.period",),
            (),
            role,
            snapshot_checksum,
        )
        steps.append(
            PlanStep(
                step_id="derive",
                operation=derived_operation,
                contract=derived,
                depends_on=tuple(step.step_id for step in steps),
            )
        )

    payload = {
        "intent": request.intent,
        "question": question,
        "snapshot_checksum": snapshot_checksum,
        "steps": [step.model_dump(mode="json") for step in steps],
    }
    plan_hash = sha256_value(payload)
    return AnalysisPlan(
        plan_id="plan." + plan_hash[:16],
        plan_hash=plan_hash,
        **payload,
    )
