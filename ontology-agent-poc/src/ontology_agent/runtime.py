from __future__ import annotations

import json
import re
import uuid
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from .contracts import PublicationError, VerifiedSnapshot
from .formula import evaluate_scalar_formula
from .io import DEFAULT_PROJECT_ROOT, DEFAULT_PUBLISHED_DIR, sha256_value, write_json
from .models import (
    AnalysisPlan,
    AnalysisResponse,
    EvidenceRecord,
    OntologyPackage,
    StepExecution,
)
from .planning import ResolvedRequest, build_plan, resolve_request
from .runtime_snapshot import verify_snapshot_handle
from .scenario import BoundAnalysisGoal
from .sql_compiler import CompiledQuery, DuckDBContext, compile_trading_days, compile_turnover


DEFAULT_EXECUTION_DIR = DEFAULT_PROJECT_ROOT / "outputs" / "executions"


class AnalysisFailure(RuntimeError):
    pass


def _step(step_id: str, query: CompiledQuery, rows: list[dict[str, Any]]) -> StepExecution:
    return StepExecution(
        step_id=step_id,
        status="PASS",
        sql=query.sql,
        params=query.params,
        sql_hash=sha256_value({"sql": query.sql, "params": query.params}),
        rows=tuple(rows),
    )


def _is_chinese(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", text))


def _direction(value: Decimal) -> Literal["increase", "decrease", "no_change"]:
    if value > 0:
        return "increase"
    if value < 0:
        return "decrease"
    return "no_change"


def _format_number(value: Decimal | int, places: int = 2, *, absolute: bool = False) -> str:
    numeric = abs(value) if absolute else value
    return f"{numeric:,.{places}f}" if places else f"{numeric:,}"


def _metric_sources(package: OntologyPackage, metric_ids: tuple[str, ...]) -> tuple[str, ...]:
    metrics = {metric.id: metric for metric in package.metrics}
    return tuple(
        dict.fromkeys(
            source
            for metric_id in metric_ids
            if metric_id in metrics
            for source in metrics[metric_id].sources
        )
    )


def _period_facts(
    package: OntologyPackage,
    turnover_rows: list[dict[str, Any]],
    day_rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    turnover = {
        str(row["period_id"]): Decimal(str(row["turnover_hkd_mn"]))
        for row in turnover_rows
    }
    days = {
        str(row["period_id"]): Decimal(str(row["trading_day_count"]))
        for row in day_rows
    }
    if set(turnover) != set(days):
        raise AnalysisFailure("Turnover and trading-day period sets do not reconcile")
    adt_metric = next(
        metric for metric in package.metrics if metric.id == "metric.average_daily_turnover"
    )
    result: dict[str, dict[str, Any]] = {}
    for period_id in turnover:
        adt = evaluate_scalar_formula(
            adt_metric.formula,
            {
                "metric.eligible_turnover": turnover[period_id],
                "metric.trading_day_count": days[period_id],
            },
            zero_denominator_policy=adt_metric.zero_denominator_policy,
        )
        result[period_id] = {
            "eligible_turnover_hkd_mn": turnover[period_id],
            "trading_day_count": int(days[period_id]),
            "adt_hkd_mn_per_trading_day": adt,
        }
    return result


def _comparison(periods: tuple[str, ...], facts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    previous_id, current_id = periods
    previous = facts[previous_id]
    current = facts[current_id]
    previous_turnover = Decimal(previous["eligible_turnover_hkd_mn"])
    current_turnover = Decimal(current["eligible_turnover_hkd_mn"])
    previous_adt = Decimal(previous["adt_hkd_mn_per_trading_day"])
    current_adt = Decimal(current["adt_hkd_mn_per_trading_day"])
    if previous_turnover == 0 or previous_adt == 0:
        raise AnalysisFailure("A percentage comparison has a zero baseline")
    turnover_delta = current_turnover - previous_turnover
    adt_delta = current_adt - previous_adt
    return {
        "previous_period": previous_id,
        "current_period": current_id,
        "turnover_direction": _direction(turnover_delta),
        "turnover_delta_hkd_mn": turnover_delta,
        "turnover_delta_pct": turnover_delta / previous_turnover * Decimal("100"),
        "adt_direction": _direction(adt_delta),
        "adt_delta_hkd_mn_per_trading_day": adt_delta,
        "adt_delta_pct": adt_delta / previous_adt * Decimal("100"),
    }


def _sequential_decomposition(
    periods: tuple[str, ...], period_facts: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    previous_id, current_id = periods
    previous = period_facts[previous_id]
    current = period_facts[current_id]
    previous_turnover = Decimal(previous["eligible_turnover_hkd_mn"])
    current_turnover = Decimal(current["eligible_turnover_hkd_mn"])
    previous_days = Decimal(previous["trading_day_count"])
    current_days = Decimal(current["trading_day_count"])
    previous_adt = Decimal(previous["adt_hkd_mn_per_trading_day"])
    current_adt = Decimal(current["adt_hkd_mn_per_trading_day"])
    total_delta = current_turnover - previous_turnover
    calendar_effect = (current_days - previous_days) * previous_adt
    activity_effect = (current_adt - previous_adt) * current_days
    residual = total_delta - calendar_effect - activity_effect
    if abs(residual) > Decimal("0.000001"):
        raise AnalysisFailure("Sequential decomposition does not close")
    return {
        "method": "sequential_calendar_first",
        "calendar_effect_hkd_mn": calendar_effect,
        "activity_effect_hkd_mn": activity_effect,
        "residual_hkd_mn": Decimal("0"),
        "causal_claim": False,
        "order_dependent": True,
    }


def _driver_facts(
    package: OntologyPackage,
    periods: tuple[str, ...],
    period_facts: dict[str, dict[str, Any]],
    segment_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    previous_id, current_id = periods
    by_segment: dict[str, dict[str, Decimal]] = defaultdict(dict)
    names: dict[str, str] = {}
    group_sizes: dict[str, int] = {}
    for row in segment_rows:
        segment_id = str(row["segment_id"])
        by_segment[segment_id][str(row["period_id"])] = Decimal(
            str(row["turnover_hkd_mn"])
        )
        names[segment_id] = str(row["segment_name"])
        group_sizes[f'{row["period_id"]}/{segment_id}'] = int(
            row["contributing_entity_count"]
        )

    policy = package.policies[0]
    undersized = {
        key: value for key, value in group_sizes.items() if value < policy.minimum_group_size
    }
    if undersized:
        raise AnalysisFailure("Minimum group-size policy failed")

    total_delta = Decimal(period_facts[current_id]["eligible_turnover_hkd_mn"]) - Decimal(
        period_facts[previous_id]["eligible_turnover_hkd_mn"]
    )
    if total_delta == 0:
        raise AnalysisFailure("Segment contribution is undefined when total turnover change is zero")
    segments: list[dict[str, Any]] = []
    for segment_id, values in by_segment.items():
        if set(values) != {previous_id, current_id}:
            raise AnalysisFailure(f"Segment {segment_id} is missing a comparison period")
        delta = values[current_id] - values[previous_id]
        segments.append(
            {
                "segment_id": segment_id,
                "segment_name": names[segment_id],
                "previous_turnover_hkd_mn": values[previous_id],
                "current_turnover_hkd_mn": values[current_id],
                "delta_hkd_mn": delta,
                "net_change_contribution_pct": delta / total_delta * Decimal("100"),
            }
        )
    segment_delta = sum((item["delta_hkd_mn"] for item in segments), Decimal("0"))
    if abs(segment_delta - total_delta) > Decimal("0.000001"):
        raise AnalysisFailure("Segment changes do not reconcile to total turnover change")
    segments.sort(key=lambda item: item["delta_hkd_mn"], reverse=total_delta > 0)
    for rank, item in enumerate(segments, start=1):
        item["rank"] = rank
    leading = segments[0]

    return {
        "segments": segments,
        "leading_segment": leading,
        "leading_direction": _direction(total_delta),
        "decomposition": _sequential_decomposition(periods, period_facts),
    }


def _result_at(facts: dict[str, Any], result_path: str) -> Any:
    if not result_path.startswith("/facts/"):
        raise AnalysisFailure(f"Evidence path must point into facts: {result_path}")
    current: Any = facts
    for token in result_path.removeprefix("/facts/").split("/"):
        key = token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            current = current[int(key)]
        else:
            current = current[key]
    return current


def _claim(
    *,
    claim_id: str,
    claim_type: Literal["numeric", "direction", "ranking", "limitation", "definition"],
    claim: str,
    result_path: str,
    display_value: str,
    unit: str | None,
    metric_ids: tuple[str, ...],
    mapping_ids: tuple[str, ...],
    source_ids: tuple[str, ...],
    step_ids: tuple[str, ...],
    facts: dict[str, Any],
    package: OntologyPackage,
    snapshot: VerifiedSnapshot,
    plan: AnalysisPlan,
    executions: list[StepExecution],
    execution_id: str,
) -> EvidenceRecord:
    value = _result_at(facts, result_path)
    execution_by_id = {step.step_id: step for step in executions}
    plan_by_id = {step.step_id: step for step in plan.steps}
    hashes: list[str] = []
    for step_id in step_ids:
        execution = execution_by_id.get(step_id)
        if execution and execution.sql_hash:
            hashes.append(execution.sql_hash)
        plan_step = plan_by_id.get(step_id)
        if plan_step:
            hashes.append(
                sha256_value(
                    {
                        "operation": plan_step.operation,
                        "operator_version": plan_step.contract.operator_version,
                        "contract": plan_step.contract.model_dump(mode="json"),
                    }
                )
            )
    hashes = list(dict.fromkeys(hashes))
    if not hashes:
        raise AnalysisFailure(f"Claim {claim_id} has no query or operator identity")
    contract = plan_by_id[step_ids[-1]].contract
    metrics = {metric.id: metric for metric in package.metrics}
    return EvidenceRecord(
        claim_id=claim_id,
        claim_type=claim_type,
        claim=claim,
        result_path=result_path,
        value=str(value),
        display_value=display_value,
        unit=unit,
        execution_id=execution_id,
        snapshot_checksum=snapshot.snapshot_checksum,
        plan_hash=plan.plan_hash,
        dataset_checksum=snapshot.dataset_checksum,
        policy_id=contract.policy_id,
        policy_decision_id=contract.policy_decision_id,
        query_or_operator_hashes=tuple(hashes),
        metric_ids=metric_ids,
        metric_versions=tuple(metrics[metric_id].version for metric_id in metric_ids),
        mapping_ids=mapping_ids,
        source_ids=source_ids,
        step_ids=step_ids,
    )


def _build_evidence(
    *,
    intent: str,
    periods: tuple[str, ...],
    facts: dict[str, Any],
    package: OntologyPackage,
    snapshot: VerifiedSnapshot,
    plan: AnalysisPlan,
    executions: list[StepExecution],
    execution_id: str,
    queries: dict[str, CompiledQuery],
) -> tuple[EvidenceRecord, ...]:
    evidence: list[EvidenceRecord] = []

    def add(
        claim_id: str,
        claim_type: Literal["numeric", "direction", "ranking", "limitation", "definition"],
        claim: str,
        path: str,
        display: str,
        unit: str | None,
        metric_ids: tuple[str, ...],
        step_ids: tuple[str, ...],
        mapping_ids_override: tuple[str, ...] = (),
        source_ids_override: tuple[str, ...] = (),
    ) -> None:
        selected = [queries[step] for step in step_ids if step in queries]
        mapping_ids = tuple(
            dict.fromkeys(
                [mapping for query in selected for mapping in query.mapping_ids]
                + list(mapping_ids_override)
            )
        )
        source_ids = tuple(
            dict.fromkeys(
                [source for query in selected for source in query.source_ids]
                + list(_metric_sources(package, metric_ids))
                + list(source_ids_override)
            )
        )
        evidence.append(
            _claim(
                claim_id=claim_id,
                claim_type=claim_type,
                claim=claim,
                result_path=path,
                display_value=display,
                unit=unit,
                metric_ids=metric_ids,
                mapping_ids=mapping_ids,
                source_ids=source_ids,
                step_ids=step_ids,
                facts=facts,
                package=package,
                snapshot=snapshot,
                plan=plan,
                executions=executions,
                execution_id=execution_id,
            )
        )

    if intent == "evidence_audit":
        add(
            "claim.adt.definition",
            "definition",
            "Published ADT definition",
            "/facts/metric/definition",
            str(facts["metric"]["definition"]),
            None,
            ("metric.average_daily_turnover",),
            ("evidence",),
            tuple(binding["id"] for binding in facts["bindings"]),
            tuple(binding["source"] for binding in facts["bindings"]),
        )
        return tuple(evidence)

    adt_metrics = (
        "metric.eligible_turnover",
        "metric.trading_day_count",
        "metric.average_daily_turnover",
    )
    for period_id in periods:
        values = facts["periods"][period_id]
        prefix = f"/facts/periods/{period_id}"
        add(
            f"claim.period.{period_id}.turnover",
            "numeric",
            f"Eligible turnover for {period_id}",
            f"{prefix}/eligible_turnover_hkd_mn",
            _format_number(values["eligible_turnover_hkd_mn"]),
            "HKD_MN",
            ("metric.eligible_turnover",),
            ("turnover",),
        )
        add(
            f"claim.period.{period_id}.days",
            "numeric",
            f"Trading-day count for {period_id}",
            f"{prefix}/trading_day_count",
            _format_number(values["trading_day_count"], places=0),
            "TRADING_DAY_COUNT",
            ("metric.trading_day_count",),
            ("trading_days",),
        )
        add(
            f"claim.period.{period_id}.adt",
            "numeric",
            f"ADT for {period_id}",
            f"{prefix}/adt_hkd_mn_per_trading_day",
            _format_number(values["adt_hkd_mn_per_trading_day"]),
            "HKD_MN_PER_TRADING_DAY",
            adt_metrics,
            ("turnover", "trading_days", "derive"),
        )

    if intent in {"period_compare", "turnover_driver"}:
        comparison = facts["comparison"]
        for name, unit, metrics in (
            ("turnover_delta_hkd_mn", "HKD_MN", ("metric.eligible_turnover",)),
            ("turnover_delta_pct", "PERCENT", ("metric.eligible_turnover",)),
            (
                "adt_delta_hkd_mn_per_trading_day",
                "HKD_MN_PER_TRADING_DAY",
                adt_metrics,
            ),
            ("adt_delta_pct", "PERCENT", adt_metrics),
        ):
            add(
                f"claim.comparison.{name}",
                "numeric",
                name,
                f"/facts/comparison/{name}",
                _format_number(comparison[name], absolute=True),
                unit,
                metrics,
                ("turnover", "trading_days", "derive"),
            )
        for name, metrics in (
            ("turnover_direction", ("metric.eligible_turnover",)),
            ("adt_direction", adt_metrics),
        ):
            add(
                f"claim.comparison.{name}",
                "direction",
                name,
                f"/facts/comparison/{name}",
                str(comparison[name]),
                None,
                metrics,
                ("turnover", "trading_days", "derive"),
            )

    if intent == "sequential_decomposition":
        decomposition = facts["decomposition"]
        for name in (
            "calendar_effect_hkd_mn",
            "activity_effect_hkd_mn",
            "residual_hkd_mn",
        ):
            add(
                f"claim.decomposition.{name}",
                "numeric",
                name,
                f"/facts/decomposition/{name}",
                _format_number(decomposition[name]),
                "HKD_MN",
                adt_metrics,
                ("turnover", "trading_days", "derive"),
            )
        add(
            "claim.decomposition.order_dependent",
            "limitation",
            "Sequential decomposition is order-dependent",
            "/facts/decomposition/order_dependent",
            "order-dependent",
            None,
            adt_metrics,
            ("turnover", "trading_days", "derive"),
        )
        add(
            "claim.decomposition.non_causal",
            "limitation",
            "Sequential decomposition is not a causal attribution",
            "/facts/decomposition/causal_claim",
            "non-causal",
            None,
            adt_metrics,
            ("turnover", "trading_days", "derive"),
        )

    if intent == "turnover_driver":
        leading = facts["drivers"]["leading_segment"]
        decomposition = facts["drivers"]["decomposition"]
        add(
            "claim.driver.leading_segment",
            "ranking",
            "Leading segment in the direction of total change",
            "/facts/drivers/leading_segment/segment_name",
            str(leading["segment_name"]),
            None,
            ("metric.eligible_turnover",),
            ("segments", "derive"),
        )
        add(
            "claim.driver.leading_rank",
            "ranking",
            "Leading segment rank",
            "/facts/drivers/leading_segment/rank",
            _format_number(leading["rank"], places=0),
            None,
            ("metric.eligible_turnover",),
            ("segments", "derive"),
        )
        add(
            "claim.driver.leading_delta",
            "numeric",
            "Leading segment turnover change",
            "/facts/drivers/leading_segment/delta_hkd_mn",
            _format_number(leading["delta_hkd_mn"], absolute=True),
            "HKD_MN",
            ("metric.eligible_turnover",),
            ("segments", "derive"),
        )
        add(
            "claim.driver.leading_contribution",
            "numeric",
            "Leading segment share of net turnover change",
            "/facts/drivers/leading_segment/net_change_contribution_pct",
            _format_number(leading["net_change_contribution_pct"], absolute=True),
            "PERCENT",
            ("metric.eligible_turnover",),
            ("segments", "derive"),
        )
        for name in (
            "calendar_effect_hkd_mn",
            "activity_effect_hkd_mn",
            "residual_hkd_mn",
        ):
            add(
                f"claim.driver.{name}",
                "numeric",
                name,
                f"/facts/drivers/decomposition/{name}",
                _format_number(decomposition[name]),
                "HKD_MN",
                adt_metrics,
                ("turnover", "trading_days", "derive"),
            )
        add(
            "claim.driver.order_dependent",
            "limitation",
            "Sequential decomposition is order-dependent",
            "/facts/drivers/decomposition/order_dependent",
            "order-dependent",
            None,
            adt_metrics,
            ("turnover", "trading_days", "derive"),
        )
        add(
            "claim.driver.non_causal",
            "limitation",
            "Sequential decomposition is not a causal attribution",
            "/facts/drivers/decomposition/causal_claim",
            "non-causal",
            None,
            adt_metrics,
            ("turnover", "trading_days", "derive"),
        )
    return tuple(evidence)


def _answer_text(
    intent: str,
    question: str,
    periods: tuple[str, ...],
    evidence: tuple[EvidenceRecord, ...],
) -> str:
    claims = {record.claim_id: record for record in evidence}

    def display(claim_id: str) -> str:
        try:
            return claims[claim_id].display_value
        except KeyError as exc:
            raise AnalysisFailure(f"Renderer requested an ungoverned claim: {claim_id}") from exc

    zh = _is_chinese(question)
    if intent == "evidence_audit":
        definition = display("claim.adt.definition")
        return (
            f"已发布的 ADT 定义是：{definition} 本次同时返回其映射、版本和执行证据。"
            if zh
            else f"Published ADT is defined as: {definition} Mapping, version and execution evidence are included."
        )
    if intent == "metric_fact":
        parts = []
        for period_id in periods:
            adt = display(f"claim.period.{period_id}.adt")
            turnover = display(f"claim.period.{period_id}.turnover")
            days = display(f"claim.period.{period_id}.days")
            if zh:
                parts.append(
                    f"{period_id}：ADT 为 {adt} 百万港元/交易日（合资格成交额 {turnover} 百万港元，{days} 个交易日）"
                )
            else:
                parts.append(
                    f"{period_id}: ADT {adt} HKD mn/trading day (eligible turnover {turnover} HKD mn; {days} trading days)"
                )
        return ("；" if zh else "; ").join(parts) + ("。" if zh else ".")

    previous_id, current_id = periods
    if intent == "period_compare":
        direction = display("claim.comparison.adt_direction")
        delta = display("claim.comparison.adt_delta_hkd_mn_per_trading_day")
        percent = display("claim.comparison.adt_delta_pct")
        turnover = display("claim.comparison.turnover_delta_hkd_mn")
        if zh:
            verb = {"increase": "上升", "decrease": "下降", "no_change": "没有变化"}[direction]
            return (
                f"{current_id} ADT 较 {previous_id}{verb} {delta} 百万港元/交易日（{percent}%）；"
                f"合资格成交额变动 {turnover} 百万港元。"
            )
        verb = {"increase": "rose", "decrease": "fell", "no_change": "was unchanged"}[direction]
        return (
            f"{current_id} ADT {verb} by {delta} HKD mn/trading day ({percent}%) versus {previous_id}; "
            f"the absolute eligible-turnover change was {turnover} HKD mn."
        )

    if intent == "sequential_decomposition":
        calendar = display("claim.decomposition.calendar_effect_hkd_mn")
        activity = display("claim.decomposition.activity_effect_hkd_mn")
        residual = display("claim.decomposition.residual_hkd_mn")
        if zh:
            return (
                f"按交易日优先的顺序分解，交易日效应为 {calendar} 百万港元，"
                f"日均活跃度效应为 {activity} 百万港元，残差为 {residual}；"
                "该结果顺序相关且仅为非因果解释。"
            )
        return (
            f"Under the calendar-first sequential decomposition, the trading-calendar effect is {calendar} HKD mn, "
            f"the daily-activity effect is {activity} HKD mn, and the residual is {residual} HKD mn; "
            "the result is order-dependent and non-causal."
        )

    direction = display("claim.comparison.turnover_direction")
    turnover_delta = display("claim.comparison.turnover_delta_hkd_mn")
    turnover_pct = display("claim.comparison.turnover_delta_pct")
    segment = display("claim.driver.leading_segment")
    segment_rank = display("claim.driver.leading_rank")
    segment_delta = display("claim.driver.leading_delta")
    contribution = display("claim.driver.leading_contribution")
    calendar = display("claim.driver.calendar_effect_hkd_mn")
    activity = display("claim.driver.activity_effect_hkd_mn")
    order_limit = display("claim.driver.order_dependent")
    causal_limit = display("claim.driver.non_causal")
    if zh:
        verb = {"increase": "上升", "decrease": "下降", "no_change": "没有变化"}[direction]
        order_limit_zh = "顺序相关的" if order_limit == "order-dependent" else order_limit
        causal_limit_zh = "非因果解释" if causal_limit == "non-causal" else causal_limit
        return (
            f"{current_id} 合资格成交额较 {previous_id} {verb} {turnover_delta} 百万港元（{turnover_pct}%）。"
            f"{segment} 的同向净变动为 {segment_delta} 百万港元，占总体净变动 {contribution}%，排名第 {segment_rank}。"
            f"按交易日优先分解，交易日效应为 {calendar}、日均活跃度效应为 {activity} 百万港元；"
            f"该分解是{order_limit_zh}，且仅为{causal_limit_zh}。"
        )
    verb = {"increase": "rose", "decrease": "fell", "no_change": "was unchanged"}[direction]
    return (
        f"Eligible turnover in {current_id} {verb} by {turnover_delta} HKD mn ({turnover_pct}%) versus {previous_id}. "
        f"{segment} ranked number {segment_rank} in the same direction, changing by {segment_delta} HKD mn and representing "
        f"{contribution}% of the net change. The calendar-first decomposition yields {calendar} HKD mn for "
        f"trading days and {activity} HKD mn for daily activity; it is {order_limit} and {causal_limit}."
    )


def _persist(response: AnalysisResponse, execution_dir: Path) -> None:
    if response.execution_id:
        write_json(
            execution_dir / f"{response.execution_id}.json",
            response.model_dump(mode="json"),
        )


def _analyze_adt_snapshot(
    snapshot: VerifiedSnapshot,
    *,
    question: str,
    role: str,
    execution_dir: Path = DEFAULT_EXECUTION_DIR,
    bound_goal: BoundAnalysisGoal | None = None,
) -> AnalysisResponse:
    try:
        verify_snapshot_handle(snapshot)
    except PublicationError:
        return AnalysisResponse(
            status="FAILED",
            answer="The governed analysis snapshot failed integrity or compatibility verification.",
            boundary_code="SNAPSHOT_VERIFICATION_FAILED",
        )

    package = snapshot.package
    resolved = resolve_request(
        package,
        question,
        role,
        bound_intent=bound_goal.intent if bound_goal is not None else None,
    )
    if isinstance(resolved, AnalysisResponse):
        return resolved.model_copy(update={"snapshot_checksum": snapshot.snapshot_checksum})

    plan = build_plan(package, resolved, question, role, snapshot.snapshot_checksum)
    execution_id = "exec." + uuid.uuid4().hex
    validation_status = "PASS"

    facts: dict[str, Any] = {}
    executions: list[StepExecution] = []
    queries: dict[str, CompiledQuery] = {}
    try:
        if resolved.intent == "evidence_audit":
            metric = next(
                item for item in package.metrics if item.id == "metric.average_daily_turnover"
            )
            bindings = [
                {
                    "id": binding.id,
                    "logical_target": binding.logical_target,
                    "source": binding.source,
                    "table": binding.table,
                    "column": binding.column,
                }
                for binding in package.bindings
                if binding.logical_target
                in {
                    "property.trade.executed_value_hkd_mn",
                    "property.calendar.calendar_date",
                    "property.calendar.period_id",
                    "property.trade.status",
                    "property.trade.cancellation_flag",
                }
            ]
            facts = {
                "snapshot": {
                    "package_id": package.package_id,
                    "version": package.version,
                    "checksum": snapshot.snapshot_checksum,
                    "validation_status": validation_status,
                },
                "metric": {
                    "id": metric.id,
                    "version": metric.version,
                    "definition": metric.definition,
                    "unit": metric.unit,
                    "formula": metric.formula.model_dump(mode="json"),
                },
                "bindings": bindings,
            }
            executions.append(
                StepExecution(
                    step_id="evidence",
                    status="PASS",
                    rows=({"validation_status": validation_status, "binding_count": len(bindings)},),
                )
            )
        else:
            turnover_query = compile_turnover(package, resolved.periods)
            days_query = compile_trading_days(package, resolved.periods)
            queries.update(turnover=turnover_query, trading_days=days_query)
            with DuckDBContext(package, snapshot.resource_paths) as context:
                turnover_rows = context.execute(turnover_query)
                day_rows = context.execute(days_query)
                executions.extend(
                    [
                        _step("turnover", turnover_query, turnover_rows),
                        _step("trading_days", days_query, day_rows),
                    ]
                )
                period_facts = _period_facts(package, turnover_rows, day_rows)
                if set(period_facts) != set(resolved.periods):
                    raise AnalysisFailure("Not every requested governed period produced a result")
                facts["periods"] = period_facts
                if resolved.intent in {"period_compare", "turnover_driver"}:
                    facts["comparison"] = _comparison(resolved.periods, period_facts)
                if resolved.intent == "turnover_driver":
                    segment_query = compile_turnover(package, resolved.periods, by_segment=True)
                    queries["segments"] = segment_query
                    segment_rows = context.execute(segment_query)
                    executions.append(_step("segments", segment_query, segment_rows))
                    facts["drivers"] = _driver_facts(
                        package, resolved.periods, period_facts, segment_rows
                    )
                if resolved.intent == "sequential_decomposition":
                    facts["decomposition"] = _sequential_decomposition(
                        resolved.periods, period_facts
                    )
            executions.append(
                StepExecution(
                    step_id="derive",
                    status="PASS",
                    rows=({"result_paths": sorted(facts)},),
                )
            )

        evidence = _build_evidence(
            intent=resolved.intent,
            periods=resolved.periods,
            facts=facts,
            package=package,
            snapshot=snapshot,
            plan=plan,
            executions=executions,
            execution_id=execution_id,
            queries=queries,
        )
        answer = _answer_text(resolved.intent, question, resolved.periods, evidence)
        response = AnalysisResponse(
            status="ANSWERED",
            answer=answer,
            execution_id=execution_id,
            snapshot_checksum=snapshot.snapshot_checksum,
            plan=plan,
            steps=tuple(executions),
            facts=facts,
            evidence=evidence,
        )
    except Exception as exc:
        executions.append(
            StepExecution(
                step_id="failure",
                status="FAIL",
                error=f"{type(exc).__name__}: {exc}",
            )
        )
        response = AnalysisResponse(
            status="FAILED",
            answer="The governed analysis could not be completed; execution stopped without a partial answer.",
            execution_id=execution_id,
            snapshot_checksum=snapshot.snapshot_checksum,
            plan=plan,
            steps=tuple(executions),
            boundary_code="EXECUTION_FAILED",
        )
    _persist(response, execution_dir)
    return response


def analyze_snapshot(
    snapshot: VerifiedSnapshot,
    *,
    question: str,
    role: str,
    execution_dir: Path = DEFAULT_EXECUTION_DIR,
    bound_goal: BoundAnalysisGoal | None = None,
) -> AnalysisResponse:
    """Dispatch one request through the adapter bound into the verified snapshot."""

    return snapshot.scenario_adapter.analyze(
        snapshot,
        question=question,
        role=role,
        execution_dir=execution_dir,
        bound_goal=bound_goal,
    )


def analyze_latest(
    *,
    question: str,
    role: str,
    package_id: str = "ontology.exchange_analytics.adt",
    version: str | None = None,
    scenario_dir: Path = DEFAULT_PROJECT_ROOT / "scenarios" / "adt",
    published_root: Path = DEFAULT_PUBLISHED_DIR,
    execution_dir: Path = DEFAULT_EXECUTION_DIR,
) -> AnalysisResponse:
    from .publisher import load_verified_snapshot

    try:
        snapshot = load_verified_snapshot(
            package_id,
            version=version,
            scenario_dir=scenario_dir,
            published_root=published_root,
        )
    except PublicationError:
        return AnalysisResponse(
            status="FAILED",
            answer="No compatible governed snapshot is ready for analysis.",
            boundary_code="NO_COMPATIBLE_SNAPSHOT",
        )
    return analyze_snapshot(
        snapshot,
        question=question,
        role=role,
        execution_dir=execution_dir,
    )


def load_execution(execution_id: str, execution_dir: Path = DEFAULT_EXECUTION_DIR) -> dict[str, Any]:
    if not re.fullmatch(r"exec\.[0-9a-f]{32}", execution_id):
        raise ValueError("Invalid execution ID")
    path = execution_dir / f"{execution_id}.json"
    if not path.is_file():
        raise FileNotFoundError(execution_id)
    return json.loads(path.read_text(encoding="utf-8"))
