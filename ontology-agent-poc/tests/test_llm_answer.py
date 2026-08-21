from __future__ import annotations

from decimal import Decimal

from ontology_agent.llm_answer import render_closed_answer
from ontology_agent.llm_contracts import (
    BoundGoalCandidate,
    SafeComparisonResult,
    SafeContributorResult,
    SafePeriodResult,
)


def test_driver_answer_is_deterministically_rendered_from_complete_closed_clauses() -> None:
    goal = BoundGoalCandidate(
        contract="bound-goal-candidate/v1",
        intent="turnover_driver",
        metric_id="metric.average_daily_turnover",
        previous_period_id="2025-Q3",
        current_period_id="2025-Q4",
        population_id="scenario.adt_reference:SYNTH-CASH",
        requested_analyses=("compare_periods", "rank_contributors"),
        first_tool="compare_periods",
        language="en",
    )
    comparison = SafeComparisonResult(
        previous=SafePeriodResult(
            period_id="2025-Q3",
            adt_hkd_mn_per_trading_day=Decimal("130317.4603"),
            eligible_turnover_hkd_mn=Decimal("8210000"),
            trading_day_count=63,
        ),
        current=SafePeriodResult(
            period_id="2025-Q4",
            adt_hkd_mn_per_trading_day=Decimal("110491.8033"),
            eligible_turnover_hkd_mn=Decimal("6740000"),
            trading_day_count=61,
        ),
        adt_direction="decrease",
        adt_delta_hkd_mn_per_trading_day=Decimal("-19825.6570"),
        adt_delta_pct=Decimal("-15.213354"),
    )
    contributor = SafeContributorResult(
        segment_id="MB",
        segment_name="Main Board",
        rank=1,
        delta_hkd_mn=Decimal("-1200000"),
        net_change_contribution_pct=Decimal("81.632653"),
    )

    rendered = render_closed_answer(
        goal=goal,
        comparison=comparison,
        contributor=contributor,
        decomposition=None,
    )

    assert rendered.answer == (
        "Average Daily Turnover decreased from HKD 130,317.46 mn per trading day in "
        "2025-Q3 to HKD 110,491.80 mn in 2025-Q4, a 15.21% decrease. Main Board "
        "ranked first, contributing 81.63% of the net turnover decrease with a change "
        "of HKD -1,200,000.00 mn. This is a constructed-synthetic ADT reference case "
        "and a descriptive, non-causal analysis."
    )
    assert rendered.result.clause_ids == (
        "clause.adt.period-comparison",
        "clause.adt.leading-contributor",
        "clause.adt.synthetic-limitation",
        "clause.adt.non-causal-limitation",
    )
    assert len(rendered.obligation_digest) == 64
