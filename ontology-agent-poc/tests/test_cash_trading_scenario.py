from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ontology_agent import api as api_module
from ontology_agent import cash_trading_deepagent as cash_deepagent_module
from ontology_agent.api import app
from ontology_agent.cash_trading_scenario import (
    CASH_CERTIFICATION_PROFILE,
    CASH_EVALUATION_CASE_IDS,
    CashTradingScenarioAdapter,
    cash_trading_golden_certification,
    cash_trading_synthetic_binding,
)
from ontology_agent.cash_trading_runtime import CashTradingDuckDB
from ontology_agent.contracts import RuntimePreparationError
from ontology_agent.io import load_package
from ontology_agent.lifecycle import AgentRuntime, FileResourceResolver
from ontology_agent.release import StudioReleases
from ontology_agent.runtime import analyze_snapshot
from ontology_agent.scenario import default_scenario_adapters


PROJECT_ROOT = Path(__file__).parents[1]
CASH_SCENARIO = PROJECT_ROOT / "scenarios" / "cash_trading"
agent_client = TestClient(app)


def _services(tmp_path: Path, scenario_dir: Path = CASH_SCENARIO):
    release_root = tmp_path / "releases"
    return (
        StudioReleases(release_root),
        AgentRuntime(
            release_root=release_root,
            runtime_root=tmp_path / "runtime",
            resources=FileResourceResolver({"cash-scenario": scenario_dir}),
        ),
    )


def _activate_cash_common_api(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    package = load_package(CASH_SCENARIO / "ontology" / "package.yaml")
    published_root = tmp_path / "published"
    studio = StudioReleases(published_root / "releases")
    agent = AgentRuntime(
        release_root=published_root / "releases",
        runtime_root=published_root / "runtime",
        resources=FileResourceResolver(
            {"cash-trading-scenario": CASH_SCENARIO}
        ),
    )
    release = studio.publish(package)
    prepared = agent.prepare(
        release.ref,
        binding=cash_trading_synthetic_binding(
            resource_root_id="cash-trading-scenario"
        ),
        certification=cash_trading_golden_certification(
            resource_root_id="cash-trading-scenario"
        ),
    )
    agent.activate(prepared.ref, require_certification=CASH_CERTIFICATION_PROFILE)
    monkeypatch.delenv("ONTOLOGY_PRODUCT_STATE_MODE", raising=False)
    monkeypatch.setattr(api_module, "DEFAULT_PUBLISHED_DIR", published_root)
    monkeypatch.setattr(
        api_module, "DEFAULT_CASH_TRADING_SCENARIO_DIR", CASH_SCENARIO
    )
    monkeypatch.setattr(
        api_module, "DEFAULT_EXECUTION_DIR", tmp_path / "executions"
    )
    monkeypatch.setattr(api_module, "DEFAULT_STUDIO_DIR", tmp_path / "studio")
    return package


def test_cash_package_matches_the_installed_adapter_contract() -> None:
    package = load_package(CASH_SCENARIO / "ontology" / "package.yaml")
    adapter = default_scenario_adapters().resolve("cash-trading-reference", "1.0.0")

    validation = adapter.validate(package)

    assert isinstance(adapter, CashTradingScenarioAdapter)
    assert validation.failed_check_ids == ()


def test_cash_reviewed_package_covers_all_eight_source_metrics_without_overclaiming_runtime() -> None:
    package = load_package(CASH_SCENARIO / "ontology" / "package.yaml")
    source_metrics = {
        tag.split(":", 1)[1]: metric
        for metric in package.metrics
        for tag in metric.tags
        if tag.startswith("source_metric:")
    }
    runtime_metrics = {
        metric_id
        for pattern in package.analysis_patterns
        for metric_id in pattern.required_metrics
    }

    assert package.version == "0.2.1"
    assert set(source_metrics) == {f"M-{index:02d}" for index in range(1, 9)}
    assert {metric.id for metric in source_metrics.values()} <= runtime_metrics


def test_cash_runtime_materializes_trade_and_order_lifecycle_views() -> None:
    resource_paths = {
        f"source.{path.stem}": path
        for path in (CASH_SCENARIO / "data").glob("*.parquet")
    }
    with CashTradingDuckDB(resource_paths) as runtime:
        trade = runtime.connection.execute(
            "SELECT count(*) AS count, count(*) FILTER (WHERE is_active_client) AS clients "
            "FROM cash_trade_analytics"
        ).fetchone()
        order = runtime.connection.execute(
            "SELECT count(*) AS count, count(*) FILTER (WHERE is_submitted) AS submitted "
            "FROM cash_order_lifecycle_analytics"
        ).fetchone()

    assert trade is not None and trade[0] > 0 and trade[1] > 0
    assert order is not None and order[0] > 0 and order[1] > 0


def test_cash_trading_publish_prepare_activate_analyze_and_verify(
    tmp_path: Path,
) -> None:
    package = load_package(CASH_SCENARIO / "ontology" / "package.yaml")
    studio, agent = _services(tmp_path)
    release = studio.publish(
        package,
        limitations=("constructed synthetic; not HKEX validated",),
    )
    prepared = agent.prepare(
        release.ref,
        binding=cash_trading_synthetic_binding(resource_root_id="cash-scenario"),
        certification=cash_trading_golden_certification(
            resource_root_id="cash-scenario"
        ),
    )
    agent.activate(
        prepared.ref,
        require_certification=CASH_CERTIFICATION_PROFILE,
    )
    snapshot = agent.open_active(
        "cash-trading-poc", package.package_id
    ).snapshot

    summary = analyze_snapshot(
        snapshot,
        question="Analyze potential self-trades for 2026-08-03 to 2026-08-07.",
        role="MarketSurveillanceDemo",
        execution_dir=tmp_path / "executions",
    )
    timeline = analyze_snapshot(
        snapshot,
        question="Show the potential self-trade evidence timeline for PART001 on 2026-08-03.",
        role="MarketSurveillanceDemo",
        execution_dir=tmp_path / "executions",
    )
    verification = agent.verify_active(
        "cash-trading-poc",
        package.package_id,
        expected_snapshot=prepared.ref,
        execution_dir=tmp_path / "verification",
    )

    assert summary.status == "ANSWERED"
    assert summary.facts["summary"]["eligible_trade_count"] == 200
    assert summary.facts["summary"]["candidate_trade_count"] == 20
    assert len(summary.evidence) == 3
    assert "not a misconduct conclusion" in summary.answer
    assert timeline.status == "ANSWERED"
    assert timeline.facts["timeline_quality"]["candidate_trade_count"] == 1
    assert timeline.facts["timeline_quality"]["events_are_observed_only"] is True
    assert verification.status == "PASS"
    assert verification.case_count == len(CASH_EVALUATION_CASE_IDS)
    assert tuple(case.case_id for case in verification.cases) == CASH_EVALUATION_CASE_IDS


def test_cash_boundaries_do_not_release_partial_or_unauthorized_results(
    tmp_path: Path,
) -> None:
    package = load_package(CASH_SCENARIO / "ontology" / "package.yaml")
    studio, agent = _services(tmp_path)
    release = studio.publish(package)
    prepared = agent.prepare(
        release.ref,
        binding=cash_trading_synthetic_binding(resource_root_id="cash-scenario"),
        certification=cash_trading_golden_certification(
            resource_root_id="cash-scenario"
        ),
    )
    agent.activate(prepared.ref, require_certification=CASH_CERTIFICATION_PROFILE)
    snapshot = agent.open_active("cash-trading-poc", package.package_id).snapshot

    missing_time = analyze_snapshot(
        snapshot,
        question="What is the potential self-trade rate?",
        role="MarketSurveillanceDemo",
        execution_dir=tmp_path / "executions",
    )
    misconduct = analyze_snapshot(
        snapshot,
        question="Prove that PART001 committed market abuse.",
        role="MarketSurveillanceDemo",
        execution_dir=tmp_path / "executions",
    )
    aggregate_detail = analyze_snapshot(
        snapshot,
        question="Show the potential self-trade evidence timeline for PART001 on 2026-08-03.",
        role="MarketsDemo",
        execution_dir=tmp_path / "executions",
    )

    assert (missing_time.status, missing_time.boundary_code) == (
        "CLARIFY",
        "MISSING_TIME_RANGE",
    )
    assert (misconduct.status, misconduct.boundary_code) == (
        "REFUSED",
        "UNSUPPORTED_MISCONDUCT_CONCLUSION",
    )
    assert (aggregate_detail.status, aggregate_detail.boundary_code) == (
        "REFUSED",
        "DETAIL_GRAIN_DENIED",
    )
    assert missing_time.facts == misconduct.facts == aggregate_detail.facts == {}


def test_cash_prepare_rejects_parquet_tamper_before_certification(
    tmp_path: Path,
) -> None:
    copied = tmp_path / "cash-scenario"
    shutil.copytree(CASH_SCENARIO, copied)
    parquet = copied / "data" / "trading_activity.parquet"
    parquet.write_bytes(parquet.read_bytes() + b"tamper")

    package = load_package(copied / "ontology" / "package.yaml")
    studio, agent = _services(tmp_path / "services", copied)
    release = studio.publish(package)
    with pytest.raises(RuntimePreparationError, match="CASH_PARQUET_IDENTITY"):
        agent.prepare(
            release.ref,
            binding=cash_trading_synthetic_binding(resource_root_id="cash-scenario"),
            certification=cash_trading_golden_certification(
                resource_root_id="cash-scenario"
            ),
        )


def test_cash_solution_is_reachable_through_the_common_agent_api(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = load_package(CASH_SCENARIO / "ontology" / "package.yaml")
    published_root = tmp_path / "published"
    studio = StudioReleases(published_root / "releases")
    agent = AgentRuntime(
        release_root=published_root / "releases",
        runtime_root=published_root / "runtime",
        resources=FileResourceResolver(
            {"cash-trading-scenario": CASH_SCENARIO}
        ),
    )
    release = studio.publish(package)
    prepared = agent.prepare(
        release.ref,
        binding=cash_trading_synthetic_binding(
            resource_root_id="cash-trading-scenario"
        ),
        certification=cash_trading_golden_certification(
            resource_root_id="cash-trading-scenario"
        ),
    )
    agent.activate(prepared.ref, require_certification=CASH_CERTIFICATION_PROFILE)
    monkeypatch.delenv("ONTOLOGY_PRODUCT_STATE_MODE", raising=False)
    monkeypatch.setattr(api_module, "DEFAULT_PUBLISHED_DIR", published_root)
    monkeypatch.setattr(
        api_module, "DEFAULT_CASH_TRADING_SCENARIO_DIR", CASH_SCENARIO
    )
    monkeypatch.setattr(
        api_module, "DEFAULT_EXECUTION_DIR", tmp_path / "executions"
    )
    monkeypatch.setattr(api_module, "DEFAULT_STUDIO_DIR", tmp_path / "studio")

    response = agent_client.post(
        "/api/solutions/ontology.exchange_analytics.cash_trading/analyze",
        json={
            "question": "Analyze potential self-trades for 2026-08-03 to 2026-08-07.",
            "role": "MarketSurveillanceDemo",
        },
    )
    ontology = agent_client.get(
        "/api/solutions/ontology.exchange_analytics.cash_trading/ontology"
    )
    questions = agent_client.get(
        "/api/solutions/ontology.exchange_analytics.cash_trading/questions"
    )
    runtime = agent_client.get(
        "/api/solutions/ontology.exchange_analytics.cash_trading/runtime/active"
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ANSWERED"
    assert response.json()["facts"]["queries"][0]["metric_code"] == "M-08"
    assert response.json()["facts"]["queries"][0]["rows"][0] == {
        "potential_self_trade_count": 20,
        "self_trade_eligible_trade_count": 200,
        "value": 10.0,
    }
    assert response.json()["llm"] == {
        "contract": "solution-llm-execution/v1",
        "mode": "OFF",
        "status": "DETERMINISTIC_ONLY",
        "provider": "qwen",
        "requested_model": "qwen3.8-max",
        "model_called": False,
        "provider_call_count": 0,
        "fallback_used": False,
        "reason_code": "MODEL_NOT_CONFIGURED",
        "profile_checksum": None,
        "activation_id": None,
    }
    assert ontology.status_code == 200
    assert ontology.json()["package_id"] == package.package_id
    assert questions.status_code == 200
    assert questions.json()["family_id"] == "cash-trading.demo.analysis.v2"
    assert len(questions.json()["cases"]) == 8
    assert runtime.status_code == 200
    assert runtime.json()["default_role"] == "MarketSurveillanceDemo"
    assert runtime.json()["roles"] == [
        {
            "role_id": "MarketSurveillanceDemo",
            "name": {"en": "Market Surveillance User", "zh": "市场监察用户"},
            "access": "ALLOWED",
        },
        {
            "role_id": "TradingDemo",
            "name": {"en": "Trading User", "zh": "交易用户"},
            "access": "ALLOWED",
        },
        {
            "role_id": "MarketsDemo",
            "name": {"en": "Markets User", "zh": "市场业务用户"},
            "access": "ALLOWED",
        },
        {
            "role_id": "ExternalUser",
            "name": {"en": "External User", "zh": "外部用户"},
            "access": "DENIED",
        },
    ]

    analysis = response.json()
    semantic_request = agent_client.post(
        "/api/solutions/ontology.exchange_analytics.cash_trading/semantic-change-requests",
        json={
            "contract": "semantic-change-request-create/v1",
            "execution_id": analysis["execution_id"],
            "snapshot_checksum": analysis["snapshot_checksum"],
            "request_type": "ANALYSIS_CAPABILITY",
            "title": "Add venue concentration exploration",
            "observation": "The current result does not continue into venue concentration.",
            "proposed_change": "Review a governed venue concentration analysis pattern.",
            "claim_refs": [analysis["evidence"][0]["claim_id"]],
        },
    )
    assert semantic_request.status_code == 200
    assert semantic_request.json()["status"] == "PROPOSED_UNTRIAGED"
    assert semantic_request.json()["execution_id"] == analysis["execution_id"]
    assert list(
        (
            tmp_path
            / "studio"
            / "semantic-change-requests"
            / package.package_id
        ).glob("scr.*.json")
    )


def test_cash_question_uses_deepagent_and_governed_metric_tool(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _activate_cash_common_api(monkeypatch, tmp_path)
    sentinel_model = object()
    captured: dict[str, object] = {}

    def fake_agent_run(*, engine, question: str, model):
        captured.update(question=question, model=model)
        result = engine.query_metric(
            "M-08", "2026-08-03", "2026-08-07", ["business_date"], None
        )
        return f"Potential self-trade trend has {len(result['rows'])} days.", 2

    monkeypatch.setattr(cash_deepagent_module, "_configured_model", lambda: sentinel_model)
    monkeypatch.setattr(cash_deepagent_module, "_agent_run", fake_agent_run)
    question = "Show me the daily potential self-trade trend for the sample week."
    response = agent_client.post(
        f"/api/solutions/{package.package_id}/analyze",
        json={
            "question": question,
            "role": "MarketSurveillanceDemo",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ANSWERED"
    assert payload["facts"]["queries"][0]["metric_code"] == "M-08"
    assert len(payload["facts"]["queries"][0]["rows"]) == 4
    assert payload["llm"]["mode"] == "ACTIVE"
    assert payload["llm"]["status"] == "GROUNDED"
    assert payload["llm"]["model_called"] is True
    assert payload["llm"]["provider_call_count"] == 2
    assert payload["llm"]["fallback_used"] is False
    assert payload["llm"]["activation_id"] == "cash-trading.deepagent.v1"
    assert captured == {"question": question, "model": sentinel_model}


def test_cash_model_failure_falls_back_to_the_same_semantic_metric_engine(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _activate_cash_common_api(monkeypatch, tmp_path)
    monkeypatch.setattr(cash_deepagent_module, "_configured_model", lambda: object())

    def failing_agent_run(**_: object):
        raise OSError("synthetic provider outage")

    monkeypatch.setattr(cash_deepagent_module, "_agent_run", failing_agent_run)
    response = agent_client.post(
        f"/api/solutions/{package.package_id}/analyze",
        json={
            "question": "Analyze potential self-trades for 2026-08-03 to 2026-08-07.",
            "role": "MarketSurveillanceDemo",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ANSWERED"
    assert payload["facts"]["queries"][0]["rows"][0]["potential_self_trade_count"] == 20
    assert payload["llm"]["status"] == "FALLBACK"
    assert payload["llm"]["model_called"] is True
    assert payload["llm"]["provider_call_count"] == 1
    assert payload["llm"]["fallback_used"] is True
    assert payload["llm"]["reason_code"] == "DEEPAGENT_OSERROR"
    assert payload["plan"]["intent"] == "cash_metric_analysis"


def test_open_cash_question_is_available_to_deepagent_without_registration_gate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _activate_cash_common_api(monkeypatch, tmp_path)
    seen: list[str] = []

    def fake_agent_run(*, engine, question: str, model):
        seen.append(question)
        engine.query_metric("M-06")
        return "The cancel-to-trade ratio is 150% for the sample period.", 1

    monkeypatch.setattr(cash_deepagent_module, "_configured_model", lambda: object())
    monkeypatch.setattr(cash_deepagent_module, "_agent_run", fake_agent_run)
    question = "Please compare how many cancellation events we saw for each execution."
    response = agent_client.post(
        f"/api/solutions/{package.package_id}/analyze",
        json={
            "question": question,
            "role": "MarketSurveillanceDemo",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ANSWERED"
    assert payload["facts"]["queries"][0]["metric_code"] == "M-06"
    assert payload["llm"]["status"] == "GROUNDED"
    assert payload["llm"]["model_called"] is True
    assert payload["llm"]["provider_call_count"] == 1
    assert seen == [question]


def test_cash_agent_can_explain_its_package_derived_capabilities_without_a_model(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _activate_cash_common_api(monkeypatch, tmp_path)
    monkeypatch.setattr(cash_deepagent_module, "_configured_model", lambda: None)

    response = agent_client.post(
        f"/api/solutions/{package.package_id}/analyze",
        json={
            "question": "What questions can you answer?",
            "role": "MarketSurveillanceDemo",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ANSWERED"
    assert payload["plan"]["intent"] == "ontology_assistance"
    assert payload["facts"]["semantic"]["operation"] == "describe_capabilities"
    assert len(payload["facts"]["semantic"]["result"]["metrics"]) == 8
    assert "M-01" in payload["answer"]
    assert payload["evidence"][0]["claim_type"] == "definition"


def test_cash_agent_accepts_a_grounded_ontology_definition_answer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _activate_cash_common_api(monkeypatch, tmp_path)

    def fake_agent_run(*, engine, question: str, model):
        catalog = engine.ontology_catalog("order rejection rate")
        assert catalog["assets"]["metrics"]
        return "Order rejection rate is defined by the active ontology package.", 1

    monkeypatch.setattr(cash_deepagent_module, "_configured_model", lambda: object())
    monkeypatch.setattr(cash_deepagent_module, "_agent_run", fake_agent_run)
    response = agent_client.post(
        f"/api/solutions/{package.package_id}/analyze",
        json={
            "question": "How is the order rejection rate defined?",
            "role": "MarketSurveillanceDemo",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ANSWERED"
    assert payload["facts"]["semantic"]["operation"] == "inspect_ontology"
    assert payload["llm"]["status"] == "GROUNDED"
    assert payload["evidence"][0]["source_ids"]


def test_cash_agent_refuses_misconduct_conclusions_before_calling_the_model(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _activate_cash_common_api(monkeypatch, tmp_path)

    def should_not_run(**_: object):
        raise AssertionError("the model must not receive a prohibited conclusion request")

    monkeypatch.setattr(cash_deepagent_module, "_configured_model", lambda: object())
    monkeypatch.setattr(cash_deepagent_module, "_agent_run", should_not_run)
    response = agent_client.post(
        f"/api/solutions/{package.package_id}/analyze",
        json={
            "question": "Prove that PART001 committed market manipulation.",
            "role": "MarketSurveillanceDemo",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REFUSED"
    assert response.json()["boundary_code"] == "UNSUPPORTED_MISCONDUCT_CONCLUSION"


def test_cash_agent_clarifies_dates_outside_the_bound_sample_period(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _activate_cash_common_api(monkeypatch, tmp_path)
    monkeypatch.setattr(cash_deepagent_module, "_configured_model", lambda: None)

    response = agent_client.post(
        f"/api/solutions/{package.package_id}/analyze",
        json={
            "question": "What was the order rejection rate on 2026-07-31?",
            "role": "MarketSurveillanceDemo",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "CLARIFY"
    assert response.json()["boundary_code"] == "DATE_OUT_OF_RANGE"
    assert "2026-08-03" in response.json()["answer"]


def test_cash_agent_uses_no_data_instead_of_returning_a_null_metric(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _activate_cash_common_api(monkeypatch, tmp_path)

    def fake_agent_run(*, engine, question: str, model):
        engine.query_metric("M-01", filters={"venue": "NOT_A_VENUE"})
        return "There is no matching data.", 1

    monkeypatch.setattr(cash_deepagent_module, "_configured_model", lambda: object())
    monkeypatch.setattr(cash_deepagent_module, "_agent_run", fake_agent_run)
    response = agent_client.post(
        f"/api/solutions/{package.package_id}/analyze",
        json={
            "question": "What was the rejection rate for the unavailable venue?",
            "role": "MarketSurveillanceDemo",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "NO_DATA"
    assert response.json()["boundary_code"] == "NO_MATCHING_DATA"
