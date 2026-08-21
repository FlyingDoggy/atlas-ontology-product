from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ontology_agent import api as api_module
from ontology_agent import solution_llm as solution_llm_module
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
from ontology_agent.io import file_checksum, load_package, sha256_value
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


def _install_cash_llm_activation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    solution_id: str,
) -> dict[str, object]:
    llm_root = CASH_SCENARIO / "llm"
    activation_dir = tmp_path / "activations"
    activation_dir.mkdir()
    activation: dict[str, object] = {
        "contract": "solution-llm-activation/v1",
        "activation_id": "activation.cash-trading.qwen.v1",
        "solution_id": solution_id,
        "mode": "ACTIVE",
        "decision": "ALLOW",
        "provider": "qwen",
        "requested_model": "qwen3.8-max",
        "profile_checksum": file_checksum(llm_root / "engineering-profile.json"),
        "question_family_checksum": file_checksum(llm_root / "question-family.json"),
        "prompt_manifest_checksum": file_checksum(llm_root / "prompts.json"),
        "projection_policy_checksum": file_checksum(llm_root / "projection-policy.json"),
        "issued_at": "2026-08-01T00:00:00Z",
        "expires_at": "2027-08-01T00:00:00Z",
        "approved_by": "PoC Product & Delivery DRI",
    }
    (activation_dir / f"{solution_id}.json").write_text(
        json.dumps(activation), encoding="utf-8"
    )
    monkeypatch.setenv("ONTOLOGY_SOLUTION_LLM_ACTIVATION_DIR", str(activation_dir))
    monkeypatch.setenv("ONTOLOGY_MODEL_GATEWAY_URL", "http://model-gateway:8794")
    return activation


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

    assert package.version == "0.2.0"
    assert set(source_metrics) == {f"M-{index:02d}" for index in range(1, 9)}
    assert {
        source_metrics["M-03"].id,
        source_metrics["M-08"].id,
    } <= runtime_metrics
    assert all(
        source_metrics[source_id].id not in runtime_metrics
        for source_id in ("M-01", "M-02", "M-04", "M-05", "M-06", "M-07")
    )


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
    assert response.json()["facts"]["summary"]["candidate_trade_count"] == 20
    assert response.json()["llm"] == {
        "contract": "solution-llm-execution/v1",
        "mode": "OFF",
        "status": "DETERMINISTIC_ONLY",
        "provider": "qwen",
        "requested_model": "qwen3.8-max",
        "model_called": False,
        "provider_call_count": 0,
        "fallback_used": False,
        "reason_code": "ACTIVATION_NOT_AVAILABLE",
        "profile_checksum": None,
        "activation_id": None,
    }
    assert ontology.status_code == 200
    assert ontology.json()["package_id"] == package.package_id
    assert questions.status_code == 200
    assert questions.json()["family_id"] == "cash-trading.synthetic.analysis.v1"
    assert len(questions.json()["cases"]) == 4
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


def test_registered_cash_question_is_grounded_by_the_solution_model_profile(
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

    llm_root = CASH_SCENARIO / "llm"
    activation_dir = tmp_path / "activations"
    activation_dir.mkdir()
    activation = {
        "contract": "solution-llm-activation/v1",
        "activation_id": "activation.cash-trading.qwen.v1",
        "solution_id": package.package_id,
        "mode": "ACTIVE",
        "decision": "ALLOW",
        "provider": "qwen",
        "requested_model": "qwen3.8-max",
        "profile_checksum": file_checksum(llm_root / "engineering-profile.json"),
        "question_family_checksum": file_checksum(llm_root / "question-family.json"),
        "prompt_manifest_checksum": file_checksum(llm_root / "prompts.json"),
        "projection_policy_checksum": file_checksum(llm_root / "projection-policy.json"),
        "issued_at": "2026-08-01T00:00:00Z",
        "expires_at": "2027-08-01T00:00:00Z",
        "approved_by": "PoC Product & Delivery DRI",
    }
    activation_path = activation_dir / f"{package.package_id}.json"
    activation_path.write_text(json.dumps(activation), encoding="utf-8")
    monkeypatch.setenv("ONTOLOGY_SOLUTION_LLM_ACTIVATION_DIR", str(activation_dir))
    monkeypatch.setenv("ONTOLOGY_MODEL_GATEWAY_URL", "http://model-gateway:8794")
    captured: dict[str, object] = {}

    def fake_gateway(
        url: str, body: dict[str, object], timeout: float
    ) -> dict[str, object]:
        captured.update(url=url, body=body, timeout=timeout)
        candidate = {
            "contract": "solution-bound-goal/v1",
            "intent": "anomaly_triage",
            "tool_ids": ["self_trade_summary"],
            "language": "en",
        }
        return {
            "contract": "solution-model-grounding-response/v1",
            "solution_id": package.package_id,
            "snapshot_checksum": body["snapshot_checksum"],
            "requested_model": "qwen3.8-max",
            "response_model": "qwen3.8-max",
            "provider_request_id": "provider.cash.synthetic.1",
            "candidate": candidate,
            "candidate_checksum": sha256_value(candidate),
        }

    monkeypatch.setattr(solution_llm_module, "_gateway_transport", fake_gateway)
    question = "Analyze potential self-trades for 2026-08-03 to 2026-08-07."
    response = agent_client.post(
        f"/api/solutions/{package.package_id}/analyze",
        json={
            "question_case_id": "cash.self-trade.summary.en.v1",
            "question": question,
            "role": "MarketSurveillanceDemo",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ANSWERED"
    assert payload["facts"]["summary"]["candidate_trade_count"] == 20
    assert payload["llm"]["mode"] == "ACTIVE"
    assert payload["llm"]["status"] == "GROUNDED"
    assert payload["llm"]["model_called"] is True
    assert payload["llm"]["provider_call_count"] == 1
    assert payload["llm"]["fallback_used"] is False
    assert payload["llm"]["activation_id"] == activation["activation_id"]
    assert str(captured["url"]).endswith("/model/v1/solution-ground")
    serialized = json.dumps(captured["body"]).lower()
    assert question.lower() in serialized
    for denied in ("trading_activity", "filesystem", "select ", "api_key"):
        assert denied not in serialized


def test_cash_model_failure_restarts_the_original_trusted_request_without_partial_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _activate_cash_common_api(monkeypatch, tmp_path)
    _install_cash_llm_activation(monkeypatch, tmp_path, package.package_id)

    def failing_gateway(
        url: str, body: dict[str, object], timeout: float
    ) -> dict[str, object]:
        raise OSError("synthetic provider outage")

    monkeypatch.setattr(solution_llm_module, "_gateway_transport", failing_gateway)
    response = agent_client.post(
        f"/api/solutions/{package.package_id}/analyze",
        json={
            "question_case_id": "cash.self-trade.summary.en.v1",
            "question": "Analyze potential self-trades for 2026-08-03 to 2026-08-07.",
            "role": "MarketSurveillanceDemo",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ANSWERED"
    assert payload["facts"]["summary"]["candidate_trade_count"] == 20
    assert payload["llm"]["status"] == "FALLBACK"
    assert payload["llm"]["model_called"] is True
    assert payload["llm"]["provider_call_count"] == 1
    assert payload["llm"]["fallback_used"] is True
    assert payload["llm"]["reason_code"] == "MODEL_GROUNDING_FAILED"
    assert payload["plan"]["intent"] == "anomaly_triage"


def test_modified_cash_question_never_leaves_the_service_for_model_grounding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _activate_cash_common_api(monkeypatch, tmp_path)
    _install_cash_llm_activation(monkeypatch, tmp_path, package.package_id)
    calls: list[object] = []

    def forbidden_gateway(
        url: str, body: dict[str, object], timeout: float
    ) -> dict[str, object]:
        calls.append(body)
        raise AssertionError("unregistered text must not reach the model gateway")

    monkeypatch.setattr(solution_llm_module, "_gateway_transport", forbidden_gateway)
    response = agent_client.post(
        f"/api/solutions/{package.package_id}/analyze",
        json={
            "question_case_id": "cash.self-trade.summary.en.v1",
            "question": "Please analyze potential self-trades for 2026-08-03 to 2026-08-07.",
            "role": "MarketSurveillanceDemo",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ANSWERED"
    assert payload["llm"]["status"] == "DETERMINISTIC_ONLY"
    assert payload["llm"]["reason_code"] == "QUESTION_NOT_REGISTERED"
    assert payload["llm"]["model_called"] is False
    assert payload["llm"]["provider_call_count"] == 0
    assert calls == []
