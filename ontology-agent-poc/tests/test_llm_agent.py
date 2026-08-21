from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

import ontology_agent.llm_agent as agent_module
from ontology_agent.io import DEFAULT_SCENARIO_DIR, sha256_value
from ontology_agent.llm_agent import EngineeringGatewayError, run_engineering_demo_grounding
from ontology_agent.llm_commit import EngineeringDemoCommitStore
from ontology_agent.llm_contracts import (
    DEMO_LABEL,
    EngineeringDemoStatus,
    ModelEgressDecision,
    TaskRolloutRecord,
    load_question_family,
    load_run_profile,
)
from ontology_agent.publisher import VerifiedSnapshot


def _authority() -> tuple:
    family = load_question_family(DEFAULT_SCENARIO_DIR / "llm" / "question-family.json")
    profile = load_run_profile(DEFAULT_SCENARIO_DIR / "llm" / "engineering-profile.json")
    egress = ModelEgressDecision(
        contract="model-egress-decision/v1",
        decision_id="egress.adt.qwen.demo.v1",
        decision="ALLOW",
        product="ontology-analytic-agent",
        task="adt-engineering-demo",
        provider="qwen",
        provider_account_ref=profile.provider_account_ref,
        endpoint_ref=profile.endpoint_ref,
        region=profile.region,
        classification="constructed_synthetic",
        question_family_id=family.family_id,
        question_family_checksum=sha256_value(family),
        allowed_projection_contracts=(
            "model-question-projection/v1",
            "model-evidence-projection/v1",
        ),
        retention_profile="provider-default-demo",
        approved_by="decision-owner",
        issued_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
        expires_at=datetime(2030, 8, 19, tzinfo=timezone.utc),
    )
    rollout = TaskRolloutRecord(
        contract="task-rollout-record/v1",
        rollout_id="rollout.adt.qwen.demo.v1",
        task="adt-engineering-demo",
        mode="active-question-family-canary",
        epoch=1,
        status="ACTIVE",
        profile_digest=sha256_value(profile),
        question_family_checksum=sha256_value(family),
        egress_decision_digest=sha256_value(egress),
        evaluation_manifest_ref="eval-manifest.adt.llm.v1",
        evaluation_manifest_checksum="6" * 64,
        label_digest=sha256_value(DEMO_LABEL),
        auto_off_triggers=(
            "PROFILE_MISMATCH",
            "MODEL_IDENTITY_MISMATCH",
            "SCHEMA_FAILURE",
            "LEAK_DETECTED",
            "DEADLINE_EXCEEDED",
        ),
        approved_by="decision-owner",
        issued_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
        expires_at=datetime(2030, 8, 19, tzinfo=timezone.utc),
    )
    return family, profile, egress, rollout


def _grounding(body: dict[str, object], *, intent: str, analyses: list[str]) -> dict[str, object]:
    goal = {
        "contract": "bound-goal-candidate/v1",
        "intent": intent,
        "metric_id": "metric.average_daily_turnover",
        "previous_period_id": "2025-Q3",
        "current_period_id": "2025-Q4",
        "population_id": "scenario.adt_reference:SYNTH-CASH",
        "requested_analyses": analyses,
        "first_tool": "compare_periods",
        "language": "en",
    }
    return {
        "contract": "model-grounding-response/v1",
        "run_id": body["capability"]["run_id"],
        "requested_model": "qwen3.8-max",
        "response_model": "qwen3.8-max",
        "provider_request_id": "provider-request.ground",
        "goal": goal,
        "output_digest": sha256_value(goal),
    }


def test_driver_cannot_finish_early_or_release_the_verified_comparison(
    monkeypatch: pytest.MonkeyPatch,
    snapshot: VerifiedSnapshot,
    tmp_path: Path,
) -> None:
    family, profile, egress, rollout = _authority()
    case = next(item for item in family.cases if item.case_id == "adt.driver.en.v1")
    state_path = tmp_path / "llm-demo.sqlite3"

    def fake_gateway(url: str, body: dict[str, object], timeout: float) -> dict[str, object]:
        if url.endswith("/ground"):
            return _grounding(
                body, intent="turnover_driver", analyses=["compare_periods", "rank_contributors"]
            )
        selection = {
            "contract": "next-tool-selection/v1",
            "action": "FINISH",
            "next_tool": None,
            "reason_code": "COMPARISON_COMPLETE",
        }
        return {
            "contract": "model-next-tool-response/v1",
            "run_id": body["capability"]["run_id"],
            "requested_model": "qwen3.8-max",
            "response_model": "qwen3.8-max",
            "provider_request_id": "provider-request.next",
            "selection": selection,
            "output_digest": sha256_value(selection),
        }

    monkeypatch.setattr(agent_module, "_gateway_transport", fake_gateway)

    response = run_engineering_demo_grounding(
        status=EngineeringDemoStatus(mode="active-question-family-canary"),
        family=family,
        case=case,
        egress=egress,
        profile=profile,
        rollout=rollout,
        snapshot=snapshot,
        state_path=state_path,
        gateway_url="http://model-gateway:8794",
    )

    assert response.outcome == "FAILED_EXECUTION"
    assert response.reason_code == "LLM_ADAPTIVE_EXECUTION_FAILED"
    assert response.model_called is True
    assert response.provider_call_count == 2
    assert response.tool_call_count == 1
    assert response.answer == ""
    assert response.result is None
    assert response.committed is False
    assert EngineeringDemoCommitStore(state_path).commit_count(response.run_id) == 0


def test_rollout_off_during_model_loop_blocks_final_answer_and_all_partial_values(
    monkeypatch: pytest.MonkeyPatch,
    snapshot: VerifiedSnapshot,
    tmp_path: Path,
) -> None:
    family, profile, egress, rollout = _authority()
    case = next(item for item in family.cases if item.case_id == "adt.driver.en.v1")
    state_path = tmp_path / "llm-demo.sqlite3"

    def fake_gateway(url: str, body: dict[str, object], timeout: float) -> dict[str, object]:
        if url.endswith("/ground"):
            return _grounding(
                body, intent="turnover_driver", analyses=["compare_periods", "rank_contributors"]
            )
        EngineeringDemoCommitStore(state_path).install_rollout(
            rollout.model_copy(update={"epoch": 2, "status": "OFF"})
        )
        selection = {
            "contract": "next-tool-selection/v1",
            "action": "CALL_TOOL",
            "next_tool": "rank_contributors",
            "reason_code": "DRIVER_DETAIL_REQUIRED",
        }
        return {
            "contract": "model-next-tool-response/v1",
            "run_id": body["capability"]["run_id"],
            "requested_model": "qwen3.8-max",
            "response_model": "qwen3.8-max",
            "provider_request_id": "provider-request.next",
            "selection": selection,
            "output_digest": sha256_value(selection),
        }

    monkeypatch.setattr(agent_module, "_gateway_transport", fake_gateway)

    response = run_engineering_demo_grounding(
        status=EngineeringDemoStatus(mode="active-question-family-canary"),
        family=family,
        case=case,
        egress=egress,
        profile=profile,
        rollout=rollout,
        snapshot=snapshot,
        state_path=state_path,
        gateway_url="http://model-gateway:8794",
    )

    assert response.outcome == "FAILED_EXECUTION"
    assert response.reason_code == "LLM_ADAPTIVE_EXECUTION_FAILED"
    assert response.provider_call_count == 2
    assert response.tool_call_count == 2
    assert response.answer == ""
    assert response.result is None
    assert response.obligation_digest is None
    assert response.commit_digest is None
    assert response.committed is False
    assert EngineeringDemoCommitStore(state_path).commit_count(response.run_id) == 0


def test_model_identity_drift_trips_a_persistent_automatic_off_latch(
    monkeypatch: pytest.MonkeyPatch,
    snapshot: VerifiedSnapshot,
    tmp_path: Path,
) -> None:
    family, profile, egress, rollout = _authority()
    case = next(item for item in family.cases if item.case_id == "adt.compare.en.v1")
    state_path = tmp_path / "llm-demo.sqlite3"

    def drifted_gateway(
        url: str, body: dict[str, object], timeout: float
    ) -> dict[str, object]:
        response = _grounding(
            body,
            intent="period_compare",
            analyses=["compare_periods"],
        )
        response["response_model"] = "qwen-unapproved-alias"
        return response

    monkeypatch.setattr(agent_module, "_gateway_transport", drifted_gateway)

    response = run_engineering_demo_grounding(
        status=EngineeringDemoStatus(mode="active-question-family-canary"),
        family=family,
        case=case,
        egress=egress,
        profile=profile,
        rollout=rollout,
        snapshot=snapshot,
        state_path=state_path,
        gateway_url="http://model-gateway:8794",
    )

    assert response.outcome == "FAILED_PRECONDITION"
    assert response.answer == ""
    assert response.committed is False
    latch = EngineeringDemoCommitStore(state_path).automatic_off_latch(rollout)
    assert latch is not None
    assert latch.trigger == "MODEL_IDENTITY_MISMATCH"


@pytest.mark.parametrize(
    "trigger",
    ("PROFILE_MISMATCH", "LEAK_DETECTED", "DEADLINE_EXCEEDED", "SCHEMA_FAILURE"),
)
def test_gateway_safety_failure_trips_the_exact_persistent_rollout_latch(
    trigger: str,
    monkeypatch: pytest.MonkeyPatch,
    snapshot: VerifiedSnapshot,
    tmp_path: Path,
) -> None:
    family, profile, egress, rollout = _authority()
    case = next(item for item in family.cases if item.case_id == "adt.compare.en.v1")
    state_path = tmp_path / "llm-demo.sqlite3"

    def failed_gateway(
        url: str, body: dict[str, object], timeout: float
    ) -> dict[str, object]:
        raise EngineeringGatewayError("closed", automatic_off_trigger=trigger)

    monkeypatch.setattr(agent_module, "_gateway_transport", failed_gateway)

    response = run_engineering_demo_grounding(
        status=EngineeringDemoStatus(mode="active-question-family-canary"),
        family=family,
        case=case,
        egress=egress,
        profile=profile,
        rollout=rollout,
        snapshot=snapshot,
        state_path=state_path,
        gateway_url="http://model-gateway:8794",
    )

    assert response.outcome == "FAILED_PRECONDITION"
    assert response.committed is False
    latch = EngineeringDemoCommitStore(state_path).automatic_off_latch(rollout)
    assert latch is not None
    assert latch.trigger == trigger
