from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from ontology_agent.io import (
    DEFAULT_CASH_TRADING_SCENARIO_DIR,
    DEFAULT_SCENARIO_DIR,
    file_checksum,
    sha256_value,
)
from ontology_agent.llm_contracts import (
    BoundGoalCandidate,
    ModelEvidenceProjection,
    ModelGroundingRequest,
    ModelNextToolRequest,
    RunCapability,
    SafeComparisonResult,
    SafePeriodResult,
    build_question_projection,
    load_egress_decision,
    load_question_family,
    load_run_profile,
)
import ontology_agent.model_gateway as gateway_module
from ontology_agent.model_gateway import app
from ontology_agent.solution_llm import (
    SolutionModelGroundingRequest,
    SolutionQuestionProjection,
)
from ontology_agent.release import StudioReleases
from ontology_agent.studio.llm import (
    StudioEgressDecision,
    StudioObservationService,
    StudioRolloutRecord,
    load_semantic_slot_manifest,
    load_studio_run_profile,
)
from ontology_agent.studio.workspace import DraftWorkspaceService


client = TestClient(app)


def test_model_gateway_health_reports_capability_without_secret_or_endpoint() -> None:
    response = client.get("/model/healthz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "alive",
        "provider": "qwen",
        "requested_model": "qwen3.8-max",
    }
    serialized = response.text.lower()
    assert "key" not in serialized
    assert "authorization" not in serialized
    assert "dashscope" not in serialized


def test_grounding_fails_closed_when_the_dedicated_gateway_has_no_secret(
    monkeypatch,
) -> None:
    monkeypatch.delenv("ONTOLOGY_QWEN_API_KEY", raising=False)
    family = load_question_family(DEFAULT_SCENARIO_DIR / "llm" / "question-family.json")
    case = family.cases[0]
    projection = build_question_projection(family, case)
    capability = RunCapability(
        contract="engineering-run-capability/v1",
        run_id="run." + "a" * 32,
        rollout_id="rollout.adt.qwen.demo.v1",
        rollout_epoch=1,
        snapshot_checksum="1" * 64,
        profile_digest="2" * 64,
        question_family_checksum=sha256_value(family),
        egress_decision_digest="3" * 64,
        question_case_id=case.case_id,
        principal="demo.shared-account",
        purpose="constructed-synthetic-adt-analysis",
        tool_ids=("compare_periods", "rank_contributors", "decompose_change"),
        issued_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
        expires_at=datetime(2030, 8, 19, tzinfo=timezone.utc),
    )
    request = ModelGroundingRequest(
        contract="model-grounding-request/v1",
        capability=capability,
        profile_digest=capability.profile_digest,
        egress_decision_digest=capability.egress_decision_digest,
        projection_digest=sha256_value(projection),
        deadline_at=capability.expires_at,
        projection=projection,
    )

    response = client.post(
        "/model/v1/ground", json=request.model_dump(mode="json")
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Model gateway is not configured"}
    serialized = response.text.lower()
    assert "api_key" not in serialized
    assert "authorization" not in serialized


def test_grounding_sends_only_the_closed_question_projection_to_qwen(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    family_path = DEFAULT_SCENARIO_DIR / "llm" / "question-family.json"
    profile_path = DEFAULT_SCENARIO_DIR / "llm" / "engineering-profile.json"
    family = load_question_family(family_path)
    profile = load_run_profile(profile_path)
    case = family.cases[1]
    projection = build_question_projection(family, case)
    egress_path = tmp_path / "egress.json"
    egress_path.write_text(
        json.dumps(
            {
                "contract": "model-egress-decision/v1",
                "decision_id": "egress.adt.qwen.demo.v1",
                "decision": "ALLOW",
                "product": "ontology-analytic-agent",
                "task": "adt-engineering-demo",
                "provider": "qwen",
                "provider_account_ref": profile.provider_account_ref,
                "endpoint_ref": profile.endpoint_ref,
                "region": profile.region,
                "classification": "constructed_synthetic",
                "question_family_id": family.family_id,
                "question_family_checksum": sha256_value(family),
                "allowed_projection_contracts": [
                    "model-question-projection/v1",
                    "model-evidence-projection/v1"
                ],
                "retention_profile": "provider-default-demo",
                "approved_by": "decision-owner",
                "issued_at": "2026-08-19T00:00:00Z",
                "expires_at": "2030-09-19T00:00:00Z"
            }
        ),
        encoding="utf-8",
    )
    egress = load_egress_decision(egress_path)
    now = datetime.now(timezone.utc)
    capability = RunCapability(
        contract="engineering-run-capability/v1",
        run_id="run." + "b" * 32,
        rollout_id="rollout.adt.qwen.demo.v1",
        rollout_epoch=1,
        snapshot_checksum="1" * 64,
        profile_digest=sha256_value(profile),
        question_family_checksum=sha256_value(family),
        egress_decision_digest=sha256_value(egress),
        question_case_id=case.case_id,
        principal="demo.shared-account",
        purpose="constructed-synthetic-adt-analysis",
        tool_ids=("compare_periods", "rank_contributors", "decompose_change"),
        issued_at=now,
        expires_at=now.replace(microsecond=0) + timedelta(seconds=10),
    )
    request = ModelGroundingRequest(
        contract="model-grounding-request/v1",
        capability=capability,
        profile_digest=capability.profile_digest,
        egress_decision_digest=capability.egress_decision_digest,
        projection_digest=sha256_value(projection),
        deadline_at=capability.expires_at,
        projection=projection,
    )
    captured: dict[str, object] = {}

    def fake_transport(
        url: str, headers: dict[str, str], body: dict[str, object], timeout: float
    ) -> dict[str, object]:
        captured.update(url=url, headers=headers, body=body, timeout=timeout)
        return {
            "id": "provider-request.synthetic-1",
            "model": "qwen3.8-max",
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "contract": "bound-goal-candidate/v1",
                                "intent": "turnover_driver",
                                "metric_id": "metric.average_daily_turnover",
                                "previous_period_id": "2025-Q3",
                                "current_period_id": "2025-Q4",
                                "population_id": "scenario.adt_reference:SYNTH-CASH",
                                "requested_analyses": [
                                    "compare_periods",
                                    "rank_contributors"
                                ],
                                "first_tool": "compare_periods",
                                "language": "en"
                            }
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(gateway_module, "_provider_transport", fake_transport)
    monkeypatch.setenv("ONTOLOGY_QWEN_API_KEY", "test-only-secret")
    monkeypatch.setenv(
        "ONTOLOGY_QWEN_BASE_URL", "https://dashscope.example/compatible-mode/v1"
    )
    monkeypatch.setenv("ONTOLOGY_LLM_EGRESS_DECISION_PATH", str(egress_path))
    monkeypatch.setenv("ONTOLOGY_LLM_PROFILE_PATH", str(profile_path))
    monkeypatch.setenv("ONTOLOGY_LLM_QUESTION_FAMILY_PATH", str(family_path))

    response = client.post(
        "/model/v1/ground", json=request.model_dump(mode="json")
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["goal"]["intent"] == "turnover_driver"
    assert payload["goal"]["first_tool"] == "compare_periods"
    assert payload["response_model"] == "qwen3.8-max"
    assert len(payload["output_digest"]) == 64
    provider_body = captured["body"]
    serialized = json.dumps(provider_body).lower()
    assert case.question.lower() in serialized
    assert "test-only-secret" not in serialized
    for denied in (
        "mapping_id",
        "source_id",
        "trade_fact",
        "column",
        "select ",
        "filesystem",
        "credential",
    ):
        assert denied not in serialized
    assert provider_body["model"] == "qwen3.8-max"
    assert provider_body["enable_thinking"] is False
    assert provider_body["response_format"] == {"type": "json_object"}
    assert len(provider_body["messages"]) == 3
    output_contract = provider_body["messages"][1]
    assert output_contract["role"] == "system"
    assert "bound-goal-candidate/v1" in output_contract["content"]
    assert "population_id" in output_contract["content"]
    assert '"const":"turnover_driver"' in output_contract["content"]
    assert (
        '"const":["compare_periods","rank_contributors"]'
        in output_contract["content"]
    )


def test_solution_gateway_independently_verifies_cash_activation_and_projection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    llm_root = DEFAULT_CASH_TRADING_SCENARIO_DIR / "llm"
    family_payload = json.loads(
        (llm_root / "question-family.json").read_text(encoding="utf-8")
    )
    case = family_payload["cases"][0]
    activation_dir = tmp_path / "activations"
    activation_dir.mkdir()
    solution_id = "ontology.exchange_analytics.cash_trading"
    activation_path = activation_dir / f"{solution_id}.json"
    activation_path.write_text(
        json.dumps(
            {
                "contract": "solution-llm-activation/v1",
                "activation_id": "activation.cash-trading.qwen.v1",
                "solution_id": solution_id,
                "mode": "ACTIVE",
                "decision": "ALLOW",
                "provider": "qwen",
                "requested_model": "qwen3.8-max",
                "profile_checksum": file_checksum(
                    llm_root / "engineering-profile.json"
                ),
                "question_family_checksum": file_checksum(
                    llm_root / "question-family.json"
                ),
                "prompt_manifest_checksum": file_checksum(llm_root / "prompts.json"),
                "projection_policy_checksum": file_checksum(
                    llm_root / "projection-policy.json"
                ),
                "issued_at": "2026-08-01T00:00:00Z",
                "expires_at": "2027-08-01T00:00:00Z",
                "approved_by": "PoC Product & Delivery DRI",
            }
        ),
        encoding="utf-8",
    )
    projection = SolutionQuestionProjection(
        contract="model-question-projection/v1",
        family_id=family_payload["family_id"],
        family_checksum=file_checksum(llm_root / "question-family.json"),
        case_id=case["case_id"],
        language=case["language"],
        question=case["question"],
        allowed_intents=(case["expected_intent"],),
    )
    request = SolutionModelGroundingRequest(
        contract="solution-model-grounding-request/v1",
        solution_id=solution_id,
        snapshot_checksum="1" * 64,
        profile_checksum=file_checksum(llm_root / "engineering-profile.json"),
        activation_checksum=file_checksum(activation_path),
        projection_checksum=sha256_value(projection),
        deadline_at=datetime.now(timezone.utc) + timedelta(seconds=8),
        projection=projection,
    )
    captured: dict[str, object] = {}

    def fake_transport(
        url: str, headers: dict[str, str], body: dict[str, object], timeout: float
    ) -> dict[str, object]:
        captured.update(url=url, headers=headers, body=body, timeout=timeout)
        return {
            "id": "provider-request.cash-ground",
            "model": "qwen3.8-max",
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "contract": "solution-bound-goal/v1",
                                "intent": "anomaly_triage",
                                "tool_ids": ["self_trade_summary"],
                                "language": "en",
                            }
                        )
                    }
                }
            ],
        }

    monkeypatch.setattr(gateway_module, "_provider_transport", fake_transport)
    monkeypatch.setenv("ONTOLOGY_QWEN_API_KEY", "test-only-secret")
    monkeypatch.setenv(
        "ONTOLOGY_QWEN_BASE_URL", "https://dashscope.example/compatible-mode/v1"
    )
    monkeypatch.setenv("ONTOLOGY_SOLUTION_LLM_ACTIVATION_DIR", str(activation_dir))

    response = client.post(
        "/model/v1/solution-ground", json=request.model_dump(mode="json")
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["solution_id"] == solution_id
    assert payload["snapshot_checksum"] == "1" * 64
    assert payload["candidate"] == {
        "contract": "solution-bound-goal/v1",
        "intent": "anomaly_triage",
        "tool_ids": ["self_trade_summary"],
        "language": "en",
    }
    assert len(payload["candidate_checksum"]) == 64
    provider_body = captured["body"]
    serialized = json.dumps(provider_body).lower()
    assert case["question"].lower() in serialized
    assert "test-only-secret" not in serialized
    for denied in ("trading_activity", "filesystem_path", "unapproved_sql", "api_key"):
        assert denied not in serialized


def test_next_tool_selection_consumes_only_verified_aggregate_projection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    family_path = DEFAULT_SCENARIO_DIR / "llm" / "question-family.json"
    profile_path = DEFAULT_SCENARIO_DIR / "llm" / "engineering-profile.json"
    family = load_question_family(family_path)
    profile = load_run_profile(profile_path)
    case = family.cases[1]
    egress_path = tmp_path / "egress.json"
    egress_path.write_text(
        json.dumps(
            {
                "contract": "model-egress-decision/v1",
                "decision_id": "egress.adt.qwen.demo.v1",
                "decision": "ALLOW",
                "product": "ontology-analytic-agent",
                "task": "adt-engineering-demo",
                "provider": "qwen",
                "provider_account_ref": profile.provider_account_ref,
                "endpoint_ref": profile.endpoint_ref,
                "region": profile.region,
                "classification": "constructed_synthetic",
                "question_family_id": family.family_id,
                "question_family_checksum": sha256_value(family),
                "allowed_projection_contracts": [
                    "model-question-projection/v1",
                    "model-evidence-projection/v1"
                ],
                "retention_profile": "provider-default-demo",
                "approved_by": "decision-owner",
                "issued_at": "2026-08-19T00:00:00Z",
                "expires_at": "2030-09-19T00:00:00Z"
            }
        ),
        encoding="utf-8",
    )
    egress = load_egress_decision(egress_path)
    now = datetime.now(timezone.utc)
    capability = RunCapability(
        contract="engineering-run-capability/v1",
        run_id="run." + "c" * 32,
        rollout_id="rollout.adt.qwen.demo.v1",
        rollout_epoch=1,
        snapshot_checksum="1" * 64,
        profile_digest=sha256_value(profile),
        question_family_checksum=sha256_value(family),
        egress_decision_digest=sha256_value(egress),
        question_case_id=case.case_id,
        principal="demo.shared-account",
        purpose="constructed-synthetic-adt-analysis",
        tool_ids=("compare_periods", "rank_contributors", "decompose_change"),
        issued_at=now,
        expires_at=now.replace(microsecond=0) + timedelta(seconds=10),
    )
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
            adt_hkd_mn_per_trading_day="130317.46",
            eligible_turnover_hkd_mn="8210000",
            trading_day_count=63,
        ),
        current=SafePeriodResult(
            period_id="2025-Q4",
            adt_hkd_mn_per_trading_day="110491.80",
            eligible_turnover_hkd_mn="6740000",
            trading_day_count=61,
        ),
        adt_direction="decrease",
        adt_delta_hkd_mn_per_trading_day="-19825.66",
        adt_delta_pct="-15.21",
    )
    projection = ModelEvidenceProjection(
        contract="model-evidence-projection/v1",
        run_id=capability.run_id,
        step_id="step.compare-periods",
        tool_id="compare_periods",
        result_contract="safe-period-comparison/v1",
        aggregate_values=comparison,
        claim_handles=("claim.adt.compare",),
        mandatory_limitations=("constructed-synthetic", "descriptive-non-causal"),
    )
    request = ModelNextToolRequest(
        contract="model-next-tool-request/v1",
        capability=capability,
        profile_digest=capability.profile_digest,
        egress_decision_digest=capability.egress_decision_digest,
        projection_digest=sha256_value(projection),
        deadline_at=capability.expires_at,
        goal=goal,
        projection=projection,
        allowed_next_actions=("rank_contributors", "finish"),
    )
    captured: dict[str, object] = {}

    def fake_transport(
        url: str, headers: dict[str, str], body: dict[str, object], timeout: float
    ) -> dict[str, object]:
        captured.update(body=body)
        return {
            "id": "provider-request.synthetic-next",
            "model": "qwen3.8-max",
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "contract": "next-tool-selection/v1",
                                "action": "CALL_TOOL",
                                "next_tool": "rank_contributors",
                                "reason_code": "DRIVER_DETAIL_REQUIRED"
                            }
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(gateway_module, "_provider_transport", fake_transport)
    monkeypatch.setenv("ONTOLOGY_QWEN_API_KEY", "test-only-secret")
    monkeypatch.setenv(
        "ONTOLOGY_QWEN_BASE_URL", "https://dashscope.example/compatible-mode/v1"
    )
    monkeypatch.setenv("ONTOLOGY_LLM_EGRESS_DECISION_PATH", str(egress_path))
    monkeypatch.setenv("ONTOLOGY_LLM_PROFILE_PATH", str(profile_path))
    monkeypatch.setenv("ONTOLOGY_LLM_QUESTION_FAMILY_PATH", str(family_path))

    response = client.post(
        "/model/v1/next-tool", json=request.model_dump(mode="json")
    )

    assert response.status_code == 200
    assert response.json()["selection"] == {
        "contract": "next-tool-selection/v1",
        "action": "CALL_TOOL",
        "next_tool": "rank_contributors",
        "reason_code": "DRIVER_DETAIL_REQUIRED",
    }
    serialized = json.dumps(captured["body"]).lower()
    assert "-15.21" in serialized
    output_contract = captured["body"]["messages"][1]
    assert output_contract["role"] == "system"
    assert "next-tool-selection/v1" in output_contract["content"]
    assert "reason_code" in output_contract["content"]
    for denied in ("mapping_id", "source_id", "trade_fact", "column", "select "):
        assert denied not in serialized


def test_studio_gateway_receives_only_the_closed_cleared_input_projection(
    monkeypatch: pytest.MonkeyPatch,
    scenario_dir: Path,
    tmp_path: Path,
) -> None:
    studio_root = DEFAULT_SCENARIO_DIR / "llm" / "studio"
    profile_path = studio_root / "engineering-profile.json"
    manifest_path = studio_root / "semantic-slot-manifest.json"
    profile = load_studio_run_profile(profile_path)
    manifest = load_semantic_slot_manifest(manifest_path)
    egress = StudioEgressDecision(
        contract="studio-model-egress-decision/v1",
        decision_id="egress.studio.adt.qwen.demo.v1",
        decision="ALLOW",
        product="ontology-studio",
        task="adt-observation-tracer",
        provider="qwen",
        provider_account_ref=profile.provider_account_ref,
        endpoint_ref=profile.endpoint_ref,
        region=profile.region,
        classification="constructed_synthetic",
        intake_submission_id="submission.reference.adt.v1",
        profile_digest=sha256_value(profile),
        slot_manifest_digest=sha256_value(manifest),
        allowed_projection_contract="studio-cleared-input-projection/v1",
        approved_by="decision-owner",
        issued_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
        expires_at=datetime(2030, 8, 19, tzinfo=timezone.utc),
    )
    egress_path = tmp_path / "studio-egress.json"
    egress_path.write_text(egress.model_dump_json(), encoding="utf-8")
    rollout = StudioRolloutRecord(
        contract="studio-task-rollout-record/v1",
        rollout_id="rollout.studio.adt.qwen.demo.v1",
        task="adt-observation-tracer",
        mode="shadow",
        epoch=1,
        status="ACTIVE",
        profile_digest=sha256_value(profile),
        slot_manifest_digest=sha256_value(manifest),
        egress_decision_digest=sha256_value(egress),
        approved_by="decision-owner",
        issued_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
        expires_at=datetime(2030, 8, 19, tzinfo=timezone.utc),
    )
    captured: dict[str, object] = {}

    def fake_provider(
        url: str, headers: dict[str, str], body: dict[str, object], timeout: float
    ) -> dict[str, object]:
        captured["body"] = body
        messages = body["messages"]
        projection = json.loads(messages[2]["content"])
        observations = []
        for slot in projection["slots"]:
            observation = {
                "slot_id": slot["slot_id"],
                "status": "PROPOSED",
                "support_code": "DIRECT_SOURCE",
                "source_fragment_checksum": slot["source_fragment"]["checksum"],
                "value": slot["current_value"],
            }
            if slot["slot_id"] == "metric.allowed_dimensions":
                # Qwen may repeat stale fields while explicitly declining a claim.
                # The gateway is allowed to canonicalize only by removing that claim.
                observation["status"] = "MISSING"
            observations.append(observation)
        return {
            "id": "provider-request.studio",
            "model": "qwen3.8-max",
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "contract": "studio-observation-payload/v1",
                                "observations": observations,
                            },
                            ensure_ascii=False,
                        )
                    }
                }
            ],
        }

    monkeypatch.setattr(gateway_module, "_provider_transport", fake_provider)
    monkeypatch.setenv("ONTOLOGY_QWEN_API_KEY", "test-only-secret")
    monkeypatch.setenv(
        "ONTOLOGY_QWEN_BASE_URL", "https://dashscope.example/compatible-mode/v1"
    )
    monkeypatch.setenv("ONTOLOGY_STUDIO_LLM_EGRESS_DECISION_PATH", str(egress_path))
    monkeypatch.setenv("ONTOLOGY_STUDIO_LLM_PROFILE_PATH", str(profile_path))
    monkeypatch.setenv("ONTOLOGY_STUDIO_LLM_SLOT_MANIFEST_PATH", str(manifest_path))

    releases = StudioReleases(tmp_path / "registry" / "releases")
    workspace = DraftWorkspaceService(
        tmp_path / "studio" / "workspaces",
        scenario_dir,
        releases,
    )

    def gateway_boundary(
        request: dict[str, object], timeout: float
    ) -> dict[str, object]:
        response = client.post("/model/v1/studio-observe", json=request)
        assert response.status_code == 200, response.text
        return response.json()

    service = StudioObservationService(
        root=tmp_path / "studio" / "llm",
        workspace=workspace,
        profile=profile,
        slot_manifest=manifest,
        egress=egress,
        rollout=rollout,
        evaluation=None,
        model_boundary=gateway_boundary,
    )
    observation_set = service.generate(expected_revision=workspace.get().revision)

    assert len(observation_set.observations) == 5
    missing = next(
        item
        for item in observation_set.observations
        if item.slot_id == "metric.allowed_dimensions"
    )
    assert missing.status == "MISSING"
    assert missing.value is None
    assert missing.source_fragment_checksum is None
    serialized = json.dumps(captured["body"], ensure_ascii=False).lower()
    assert "submission.reference.adt.v1" in serialized
    assert "row=m-03" in serialized
    for denied in (
        "test-only-secret",
        "existing_adt.sql",
        "data_dictionary.csv",
        "authorization",
        "private_key",
        "publish_authority",
    ):
        assert denied not in serialized
