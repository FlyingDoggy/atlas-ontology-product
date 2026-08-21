from __future__ import annotations

import json
from decimal import Decimal

from ontology_agent.llm_tools import ADTAnalyticTools
from ontology_agent.publisher import VerifiedSnapshot


def test_compare_periods_returns_only_closed_aggregate_values(
    snapshot: VerifiedSnapshot,
) -> None:
    tools = ADTAnalyticTools(snapshot, role="MarketAnalyst")

    result = tools.compare_periods(
        metric_id="metric.average_daily_turnover",
        previous_period_id="2025-Q3",
        current_period_id="2025-Q4",
        population_id="scenario.adt_reference:SYNTH-CASH",
    )

    assert result.previous.adt_hkd_mn_per_trading_day == Decimal(
        "130317.4603174603174603174603"
    )
    assert result.current.adt_hkd_mn_per_trading_day == Decimal(
        "110491.8032786885245901639344"
    )
    assert result.adt_direction == "decrease"
    assert result.adt_delta_pct == Decimal(
        "-15.21335436592719793933827201"
    )
    serialized = json.dumps(result.model_dump(mode="json")).lower()
    for denied in (
        "table",
        "column",
        "mapping_id",
        "source_id",
        "select ",
        "trade_fact",
        "instrument_id",
    ):
        assert denied not in serialized


def test_rank_contributors_returns_the_reconciled_leading_segment(
    snapshot: VerifiedSnapshot,
) -> None:
    tools = ADTAnalyticTools(snapshot, role="MarketAnalyst")

    result = tools.rank_contributors(
        previous_period_id="2025-Q3",
        current_period_id="2025-Q4",
        dimension_id="dimension.segment",
        population_id="scenario.adt_reference:SYNTH-CASH",
    )

    assert result.segment_id == "MB"
    assert result.segment_name == "Main Board"
    assert result.rank == 1
    assert result.delta_hkd_mn == Decimal("-1200000.000000")
    assert result.net_change_contribution_pct == Decimal(
        "81.63265306122448979591836735"
    )


def test_decompose_change_is_closed_non_causal_and_reconciled(
    snapshot: VerifiedSnapshot,
) -> None:
    tools = ADTAnalyticTools(snapshot, role="MarketAnalyst")

    result = tools.decompose_change(
        previous_period_id="2025-Q3",
        current_period_id="2025-Q4",
        method_id="sequential_calendar_first",
        population_id="scenario.adt_reference:SYNTH-CASH",
    )

    assert result.method == "sequential_calendar_first"
    assert result.calendar_effect_hkd_mn == Decimal(
        "-260634.9206349206349206349206"
    )
    assert result.activity_effect_hkd_mn == Decimal(
        "-1209365.079365079365079365080"
    )
    assert result.residual_hkd_mn == Decimal("0")
    assert result.causal_claim is False
    assert result.order_dependent is True
