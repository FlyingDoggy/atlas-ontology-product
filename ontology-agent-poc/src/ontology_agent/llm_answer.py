from __future__ import annotations

from decimal import Decimal

from .io import sha256_value
from .llm_contracts import (
    AnswerObligationManifest,
    BoundGoalCandidate,
    EngineeringDemoResult,
    RenderedClosedAnswer,
    SafeComparisonResult,
    SafeContributorResult,
    SafeDecompositionResult,
)


class AnswerObligationError(RuntimeError):
    """A closed answer is missing or exceeds the trusted request denominator."""


def _manifest(goal: BoundGoalCandidate) -> AnswerObligationManifest:
    if goal.intent == "period_compare":
        tools = ("compare_periods",)
        clauses = (
            "clause.adt.period-comparison",
            "clause.adt.synthetic-limitation",
            "clause.adt.non-causal-limitation",
        )
    elif goal.intent == "turnover_driver":
        tools = ("compare_periods", "rank_contributors")
        clauses = (
            "clause.adt.period-comparison",
            "clause.adt.leading-contributor",
            "clause.adt.synthetic-limitation",
            "clause.adt.non-causal-limitation",
        )
    else:
        tools = ("compare_periods", "decompose_change")
        clauses = (
            "clause.adt.period-comparison",
            "clause.adt.calendar-first-decomposition",
            "clause.adt.synthetic-limitation",
            "clause.adt.non-causal-limitation",
        )
    return AnswerObligationManifest(
        contract="answer-obligation-manifest/v1",
        intent=goal.intent,
        language=goal.language,
        metric_id=goal.metric_id,
        previous_period_id=goal.previous_period_id,
        current_period_id=goal.current_period_id,
        population_id=goal.population_id,
        required_tool_ids=tools,
        required_clause_ids=clauses,
    )


def _number(value: Decimal, places: int = 2) -> str:
    return f"{value:,.{places}f}"


def render_closed_answer(
    *,
    goal: BoundGoalCandidate,
    comparison: SafeComparisonResult,
    contributor: SafeContributorResult | None,
    decomposition: SafeDecompositionResult | None,
) -> RenderedClosedAnswer:
    manifest = _manifest(goal)
    if comparison.previous.period_id != goal.previous_period_id or (
        comparison.current.period_id != goal.current_period_id
    ):
        raise AnswerObligationError("Comparison periods do not satisfy the goal")
    if goal.intent == "period_compare" and (contributor or decomposition):
        raise AnswerObligationError("Comparison answer contains unrequested analysis")
    if goal.intent == "turnover_driver" and (contributor is None or decomposition):
        raise AnswerObligationError("Driver answer is incomplete or over-scoped")
    if goal.intent == "sequential_decomposition" and (
        decomposition is None or contributor
    ):
        raise AnswerObligationError("Decomposition answer is incomplete or over-scoped")

    direction_en = {
        "increase": "increased",
        "decrease": "decreased",
        "no_change": "did not change",
    }[comparison.adt_direction]
    direction_zh = {
        "increase": "上升",
        "decrease": "下降",
        "no_change": "没有变化",
    }[comparison.adt_direction]
    percent = _number(abs(comparison.adt_delta_pct))
    if goal.language == "zh":
        answer = (
            f"Average Daily Turnover 从 {goal.previous_period_id} 的每交易日 HKD "
            f"{_number(comparison.previous.adt_hkd_mn_per_trading_day)} mn，变为 "
            f"{goal.current_period_id} 的 HKD "
            f"{_number(comparison.current.adt_hkd_mn_per_trading_day)} mn，"
            f"{direction_zh} {percent}%。"
        )
        if contributor:
            answer += (
                f"{contributor.segment_name} 排名第一，其成交额变化为 HKD "
                f"{_number(contributor.delta_hkd_mn)} mn，对净变化的描述性贡献为 "
                f"{_number(contributor.net_change_contribution_pct)}%。"
            )
        if decomposition:
            answer += (
                f"按交易日优先分解，交易日效应为 HKD "
                f"{_number(decomposition.calendar_effect_hkd_mn)} mn，日均活跃度效应为 "
                f"HKD {_number(decomposition.activity_effect_hkd_mn)} mn，残差为 "
                f"HKD {_number(decomposition.residual_hkd_mn)} mn。"
            )
        answer += "这是构造的合成 ADT 参考案例，仅为描述性、非因果分析。"
    else:
        answer = (
            f"Average Daily Turnover {direction_en} from HKD "
            f"{_number(comparison.previous.adt_hkd_mn_per_trading_day)} mn per trading "
            f"day in {goal.previous_period_id} to HKD "
            f"{_number(comparison.current.adt_hkd_mn_per_trading_day)} mn in "
            f"{goal.current_period_id}, a {percent}% "
            f"{'increase' if comparison.adt_direction == 'increase' else 'decrease' if comparison.adt_direction == 'decrease' else 'change'}."
        )
        if contributor:
            answer += (
                f" {contributor.segment_name} ranked first, contributing "
                f"{_number(contributor.net_change_contribution_pct)}% of the net turnover "
                f"{'increase' if comparison.adt_direction == 'increase' else 'decrease'} "
                f"with a change of HKD {_number(contributor.delta_hkd_mn)} mn."
            )
        if decomposition:
            answer += (
                f" The calendar-first decomposition attributes HKD "
                f"{_number(decomposition.calendar_effect_hkd_mn)} mn to trading days and "
                f"HKD {_number(decomposition.activity_effect_hkd_mn)} mn to daily activity, "
                f"with a residual of HKD {_number(decomposition.residual_hkd_mn)} mn."
            )
        answer += (
            " This is a constructed-synthetic ADT reference case and a descriptive, "
            "non-causal analysis."
        )

    result = EngineeringDemoResult(
        comparison=comparison,
        leading_contributor=contributor,
        decomposition=decomposition,
        clause_ids=manifest.required_clause_ids,
    )
    return RenderedClosedAnswer(
        answer=answer,
        result=result,
        obligation_digest=sha256_value(manifest),
    )
