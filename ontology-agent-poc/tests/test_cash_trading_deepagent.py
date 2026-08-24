from __future__ import annotations

from pathlib import Path

import pytest

from ontology_agent.cash_trading_deepagent import (
    CashTradingSemanticEngine,
    _agent_run,
    _deepagent_tools,
)
from ontology_agent.analytic_conversations import AnalyticConversationContextV1
from langchain_core.messages import AIMessage
from ontology_agent.io import load_package


PROJECT_ROOT = Path(__file__).parents[1]
CASH_SCENARIO = PROJECT_ROOT / "scenarios" / "cash_trading"


@pytest.fixture(scope="module")
def semantic_engine() -> CashTradingSemanticEngine:
    package = load_package(CASH_SCENARIO / "ontology" / "package.yaml")
    resource_paths = {
        f"source.{path.stem}": path
        for path in (CASH_SCENARIO / "data").glob("*.parquet")
    }
    return CashTradingSemanticEngine(
        package=package,
        resource_paths=resource_paths,
        role="MarketSurveillanceDemo",
    )


@pytest.mark.parametrize(
    ("metric", "expected"),
    (
        (
            "M-01",
            {
                "rejected_order_count": 200,
                "submitted_order_count": 1200,
                "value": pytest.approx(16.666667),
            },
        ),
        (
            "M-02",
            {
                "executed_order_quantity": 0,
                "submitted_order_quantity": 5_064_000,
                "value": pytest.approx(0.0),
            },
        ),
        (
            "M-03",
            {
                "eligible_latency_count": 200,
                "minimum_ms": 3,
                "p50_ms": 9,
                "p95_ms": 15,
                "p99_ms": 15,
                "maximum_ms": 15,
                "negative_latency_count": 0,
                "value": 15,
            },
        ),
        (
            "M-04",
            {
                "active_client_trade_quantity": 1500,
                "active_client_trade_notional_hkd": pytest.approx(52_235.0),
                "active_client_trade_notional_usd_pre_haircut": pytest.approx(
                    6678.36426
                ),
                "active_client_count": 3,
                "value": pytest.approx(0.052235),
            },
        ),
        (
            "M-05",
            {
                "fully_filled_client_order_count": 0,
                "eligible_client_order_count": 150,
                "value": pytest.approx(0.0),
            },
        ),
        (
            "M-06",
            {
                "canceled_order_count": 300,
                "eligible_trade_count": 200,
                "value": pytest.approx(150.0),
            },
        ),
        (
            "M-07",
            {
                "submitted_order_count": 1200,
                "eligible_trade_count": 200,
                "value": pytest.approx(300.0),
            },
        ),
        (
            "M-08",
            {
                "potential_self_trade_count": 20,
                "self_trade_eligible_trade_count": 200,
                "value": pytest.approx(10.0),
            },
        ),
    ),
)
def test_all_primary_metrics_have_reproducible_deterministic_results(
    semantic_engine: CashTradingSemanticEngine,
    metric: str,
    expected: dict[str, object],
) -> None:
    result = semantic_engine.query_metric(metric)

    assert result["metric_code"] == metric
    assert len(result["rows"]) == 1
    for key, value in expected.items():
        assert result["rows"][0][key] == value
    assert result["evidence"]["sources"]
    assert result["evidence"]["decisions"]
    assert result["evidence"]["query_hash"]


def test_self_trade_daily_trend_uses_business_date_dimension(
    semantic_engine: CashTradingSemanticEngine,
) -> None:
    result = semantic_engine.query_metric("M-08", group_by=["business_date"])

    assert result["dimensions"] == ["dimension.business_date"]
    assert [row["business_date"] for row in result["rows"]] == [
        "2026-08-03",
        "2026-08-04",
        "2026-08-06",
        "2026-08-07",
    ]
    assert all(row["value"] == pytest.approx(10.0) for row in result["rows"])


def test_metric_tool_accepts_json_encoded_collection_arguments(
    semantic_engine: CashTradingSemanticEngine,
) -> None:
    metric_tool = next(
        item for item in _deepagent_tools(semantic_engine) if item.name == "query_cash_metric"
    )

    result = metric_tool.invoke(
        {
            "metric": "M-08",
            "start_date": "2026-08-03",
            "end_date": "2026-08-07",
            "group_by": '["business_date"]',
            "filters": '{"venue": "XHKG"}',
        }
    )

    assert '"dimensions": ["dimension.business_date"]' in result
    assert '"filters": {"venue": "XHKG"}' in result


def test_order_lifecycle_keeps_cancel_events_that_reference_the_original_order(
    semantic_engine: CashTradingSemanticEngine,
) -> None:
    result = semantic_engine.query_metric("M-06")

    assert result["rows"][0]["canceled_order_count"] == 300


@pytest.mark.parametrize("metric", ("M-02", "M-05"))
def test_zero_completion_metrics_disclose_the_execute_to_new_linkage_gap(
    semantic_engine: CashTradingSemanticEngine,
    metric: str,
) -> None:
    result = semantic_engine.query_metric(metric)

    assert result["rows"][0]["value"] == 0
    assert "cannot be reliably linked" in result["limitations"][0]


def test_self_trade_metric_is_explicitly_a_triage_candidate(
    semantic_engine: CashTradingSemanticEngine,
) -> None:
    result = semantic_engine.query_metric("M-08")

    assert "not a misconduct" in result["limitations"][0]


def test_markets_role_cannot_request_participant_level_results() -> None:
    package = load_package(CASH_SCENARIO / "ontology" / "package.yaml")
    resource_paths = {
        f"source.{path.stem}": path
        for path in (CASH_SCENARIO / "data").glob("*.parquet")
    }
    engine = CashTradingSemanticEngine(package, resource_paths, "MarketsDemo")

    with pytest.raises(ValueError, match="participant-level"):
        engine.query_metric("M-04", group_by=["participant"])


def test_deepagent_uses_conversation_id_as_its_checkpoint_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = load_package(CASH_SCENARIO / "ontology" / "package.yaml")
    resource_paths = {
        f"source.{path.stem}": path
        for path in (CASH_SCENARIO / "data").glob("*.parquet")
    }
    context = AnalyticConversationContextV1(
        metric_id="metric.order_rejection_rate",
        start_date="2026-08-03",
        end_date="2026-08-07",
        role="MarketSurveillanceDemo",
        last_execution_id="exec." + "1" * 32,
    )
    engine = CashTradingSemanticEngine(
        package,
        resource_paths,
        "MarketSurveillanceDemo",
        conversation_id="conversation." + "2" * 32,
        conversation_context=context,
    )
    captured: dict[str, object] = {}

    class FakeGraph:
        def invoke(self, payload, *, config):
            captured.update(payload=payload, config=config)
            return {"messages": [AIMessage(content="Grounded follow-up answer.")]}

    def fake_create_deep_agent(**kwargs):
        captured.update(kwargs=kwargs)
        return FakeGraph()

    monkeypatch.setattr(
        "ontology_agent.cash_trading_deepagent.create_deep_agent",
        fake_create_deep_agent,
    )

    answer, model_calls = _agent_run(
        engine=engine,
        question="Break that down by participant.",
        model=object(),
    )

    assert answer == "Grounded follow-up answer."
    assert model_calls == 1
    assert captured["config"] == {
        "recursion_limit": 18,
        "configurable": {"thread_id": engine.conversation_id},
    }
    kwargs = captured["kwargs"]
    assert kwargs["checkpointer"] is not None
    assert "metric.order_rejection_rate" in kwargs["system_prompt"]
    assert "Do not repeat those rows as a Markdown table" in kwargs["system_prompt"]
