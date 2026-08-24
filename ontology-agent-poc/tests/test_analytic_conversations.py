from __future__ import annotations

from datetime import datetime, timezone

import pytest
from ontology_agent.analytic_conversations import (
    AnalyticConversationConflict,
    AnalyticConversationContextV1,
    InMemoryAnalyticConversationStore,
)

CHECKSUM = "a" * 64


def test_conversation_carries_only_governed_analysis_parameters_between_turns() -> None:
    store = InMemoryAnalyticConversationStore(
        clock=lambda: datetime(2026, 8, 25, tzinfo=timezone.utc)
    )
    first = store.begin_turn(
        conversation_id="conversation." + "1" * 32,
        solution_id="ontology.exchange_analytics.cash_trading",
        role="MarketSurveillanceDemo",
        snapshot_checksum=CHECKSUM,
        question="What was the rejection rate for the sample week?",
    )
    first_context = AnalyticConversationContextV1(
        metric_id="metric.order_rejection_rate",
        start_date="2026-08-03",
        end_date="2026-08-07",
        dimensions=(),
        filters={},
        role="MarketSurveillanceDemo",
        last_execution_id="exec." + "2" * 32,
    )
    store.complete_turn(
        first,
        status="ANSWERED",
        execution_id=first_context.last_execution_id,
        context_after=first_context,
    )

    second = store.begin_turn(
        conversation_id=first.conversation_id,
        solution_id=first.solution_id,
        role="MarketSurveillanceDemo",
        snapshot_checksum=CHECKSUM,
        question="Break that down by participant.",
    )

    assert second.turn_index == 2
    assert second.parent_execution_id == first_context.last_execution_id
    assert second.context_before == first_context
    assert second.context_before.model_dump().keys() == {
        "contract",
        "metric_id",
        "start_date",
        "end_date",
        "dimensions",
        "filters",
        "role",
        "last_execution_id",
    }


def test_conversation_id_cannot_cross_solution_boundaries() -> None:
    store = InMemoryAnalyticConversationStore()
    conversation_id = "conversation." + "3" * 32
    store.begin_turn(
        conversation_id=conversation_id,
        solution_id="ontology.solution.one",
        role="Analyst",
        snapshot_checksum=CHECKSUM,
        question="First question",
    )

    with pytest.raises(
        AnalyticConversationConflict, match="different ontology solution"
    ):
        store.begin_turn(
            conversation_id=conversation_id,
            solution_id="ontology.solution.two",
            role="Analyst",
            snapshot_checksum=CHECKSUM,
            question="Second question",
        )
