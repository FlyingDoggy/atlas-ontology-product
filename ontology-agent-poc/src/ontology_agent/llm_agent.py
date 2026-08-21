from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from .contracts import VerifiedSnapshot
from .io import canonical_bytes, sha256_value
from .llm_commit import EngineeringCommitConflict, EngineeringDemoCommitStore
from .llm_answer import AnswerObligationError, render_closed_answer
from .llm_contracts import (
    EngineeringDemoResponse,
    EngineeringDemoStatus,
    EngineeringRunProfile,
    ModelEgressDecision,
    ModelGroundingRequest,
    ModelGroundingResponse,
    ModelEvidenceProjection,
    ModelNextToolRequest,
    ModelNextToolResponse,
    RegisteredQuestionCase,
    RegisteredQuestionFamily,
    TaskRolloutRecord,
    build_question_projection,
)
from .llm_tools import ADTAnalyticTools, ADTToolError


class EngineeringGatewayError(OSError):
    def __init__(
        self,
        message: str,
        *,
        automatic_off_trigger: str | None = None,
    ):
        super().__init__(message)
        self.automatic_off_trigger = automatic_off_trigger


def run_engineering_demo_grounding(
    *,
    status: EngineeringDemoStatus,
    family: RegisteredQuestionFamily,
    case: RegisteredQuestionCase,
    egress: ModelEgressDecision,
    profile: EngineeringRunProfile,
    rollout: TaskRolloutRecord,
    snapshot: VerifiedSnapshot,
    state_path: Path,
    gateway_url: str,
) -> EngineeringDemoResponse:
    store = EngineeringDemoCommitStore(state_path)
    try:
        store.install_rollout(rollout)
        run_id = "run." + uuid.uuid4().hex
        capability = store.begin_run(
            rollout=rollout,
            run_id=run_id,
            snapshot_checksum=snapshot.snapshot_checksum,
            question_case_id=case.case_id,
            principal="demo.shared-account",
            purpose="constructed-synthetic-adt-analysis",
        )
    except EngineeringCommitConflict:
        return _failure(
            "FAILED_PRECONDITION",
            "ROLLOUT_STATE_CONFLICT",
            profile_digest=sha256_value(profile),
        )

    projection = build_question_projection(family, case)
    grounding_request = ModelGroundingRequest(
        contract="model-grounding-request/v1",
        capability=capability,
        profile_digest=sha256_value(profile),
        egress_decision_digest=sha256_value(egress),
        projection_digest=sha256_value(projection),
        deadline_at=capability.expires_at,
        projection=projection,
    )
    try:
        raw = _gateway_transport(
            gateway_url.rstrip("/") + "/model/v1/ground",
            grounding_request.model_dump(mode="json"),
            profile.budgets.provider_timeout_ms / 1000,
        )
    except EngineeringGatewayError as exc:
        if exc.automatic_off_trigger:
            _trip_automatic_off(store, rollout, exc.automatic_off_trigger)
        return _failure(
            "FAILED_PRECONDITION",
            "MODEL_GROUNDING_FAILED",
            run_id=capability.run_id,
            snapshot_checksum=snapshot.snapshot_checksum,
            profile_digest=sha256_value(profile),
            model_called=True,
            provider_call_count=1,
        )
    except OSError:
        return _failure(
            "FAILED_PRECONDITION",
            "MODEL_GROUNDING_FAILED",
            run_id=capability.run_id,
            snapshot_checksum=snapshot.snapshot_checksum,
            profile_digest=sha256_value(profile),
            model_called=True,
            provider_call_count=1,
        )
    if (
        raw.get("requested_model") is not None
        and raw.get("requested_model") != profile.requested_model
    ) or (
        raw.get("response_model") is not None
        and raw.get("response_model") not in profile.accepted_response_models
    ):
        _trip_automatic_off(store, rollout, "MODEL_IDENTITY_MISMATCH")
        return _failure(
            "FAILED_PRECONDITION",
            "MODEL_IDENTITY_MISMATCH",
            run_id=capability.run_id,
            snapshot_checksum=snapshot.snapshot_checksum,
            profile_digest=sha256_value(profile),
            model_called=True,
            provider_call_count=1,
        )
    try:
        grounded = ModelGroundingResponse.model_validate(raw)
    except ValueError:
        _trip_automatic_off(store, rollout, "SCHEMA_FAILURE")
        return _failure(
            "FAILED_PRECONDITION",
            "MODEL_SCHEMA_FAILURE",
            run_id=capability.run_id,
            snapshot_checksum=snapshot.snapshot_checksum,
            profile_digest=sha256_value(profile),
            model_called=True,
            provider_call_count=1,
        )
    if (
        grounded.requested_model != profile.requested_model
        or grounded.response_model not in profile.accepted_response_models
    ):
        _trip_automatic_off(store, rollout, "MODEL_IDENTITY_MISMATCH")
        return _failure(
            "FAILED_PRECONDITION",
            "MODEL_IDENTITY_MISMATCH",
            run_id=capability.run_id,
            snapshot_checksum=snapshot.snapshot_checksum,
            profile_digest=sha256_value(profile),
            model_called=True,
            provider_call_count=1,
        )
    if (
        grounded.run_id != capability.run_id
        or grounded.output_digest != sha256_value(grounded.goal)
        or grounded.goal.intent != case.expected_intent
        or grounded.goal.language != case.language
        or grounded.goal.requested_analyses != case.required_tools
        or grounded.goal.first_tool != "compare_periods"
    ):
        _trip_automatic_off(store, rollout, "SCHEMA_FAILURE")
        return _failure(
            "FAILED_PRECONDITION",
            "MODEL_SCHEMA_FAILURE",
            run_id=capability.run_id,
            snapshot_checksum=snapshot.snapshot_checksum,
            profile_digest=sha256_value(profile),
            model_called=True,
            provider_call_count=1,
        )

    if status.mode == "shadow":
        return _failure(
            "FAILED_PRECONDITION",
            "SHADOW_RESULT_NOT_RELEASED",
            run_id=capability.run_id,
            snapshot_checksum=snapshot.snapshot_checksum,
            profile_digest=sha256_value(profile),
            model_called=True,
            provider_call_count=1,
        )

    tool_count = 0
    provider_count = 1
    try:
        tools = ADTAnalyticTools(snapshot, role="MarketAnalyst")
        comparison = tools.compare_periods(
            metric_id=grounded.goal.metric_id,
            previous_period_id=grounded.goal.previous_period_id,
            current_period_id=grounded.goal.current_period_id,
            population_id=grounded.goal.population_id,
        )
        tool_count = 1
        projection = ModelEvidenceProjection(
            contract="model-evidence-projection/v1",
            run_id=capability.run_id,
            step_id="step.compare-periods",
            tool_id="compare_periods",
            result_contract="safe-period-comparison/v1",
            aggregate_values=comparison,
            claim_handles=("claim.adt.compare",),
            mandatory_limitations=(
                "constructed-synthetic",
                "descriptive-non-causal",
            ),
        )
        allowed_actions = {
            "period_compare": ("finish",),
            "turnover_driver": ("rank_contributors", "finish"),
            "sequential_decomposition": ("decompose_change", "finish"),
        }[grounded.goal.intent]
        next_request = ModelNextToolRequest(
            contract="model-next-tool-request/v1",
            capability=capability,
            profile_digest=sha256_value(profile),
            egress_decision_digest=sha256_value(egress),
            projection_digest=sha256_value(projection),
            deadline_at=capability.expires_at,
            goal=grounded.goal,
            projection=projection,
            allowed_next_actions=allowed_actions,
        )
        provider_count = 2
        raw_next = _gateway_transport(
            gateway_url.rstrip("/") + "/model/v1/next-tool",
            next_request.model_dump(mode="json"),
            profile.budgets.provider_timeout_ms / 1000,
        )
        selected = ModelNextToolResponse.model_validate(raw_next)
        if (
            selected.run_id != capability.run_id
            or selected.requested_model != profile.requested_model
            or selected.response_model not in profile.accepted_response_models
            or selected.output_digest != sha256_value(selected.selection)
        ):
            raise ValueError("Next-tool response identity mismatch")
        action = selected.selection.next_tool or "finish"
        if action not in allowed_actions:
            raise AnswerObligationError("Selected action is outside the bound goal")

        contributor = None
        decomposition = None
        if action == "rank_contributors":
            contributor = tools.rank_contributors(
                previous_period_id=grounded.goal.previous_period_id,
                current_period_id=grounded.goal.current_period_id,
                dimension_id="dimension.segment",
                population_id=grounded.goal.population_id,
            )
            tool_count = 2
        elif action == "decompose_change":
            decomposition = tools.decompose_change(
                previous_period_id=grounded.goal.previous_period_id,
                current_period_id=grounded.goal.current_period_id,
                method_id="sequential_calendar_first",
                population_id=grounded.goal.population_id,
            )
            tool_count = 2

        executed_tools = (
            ("compare_periods",)
            if action == "finish"
            else ("compare_periods", action)
        )
        if executed_tools != case.required_tools:
            raise AnswerObligationError("Required tool denominator is incomplete")
        rendered = render_closed_answer(
            goal=grounded.goal,
            comparison=comparison,
            contributor=contributor,
            decomposition=decomposition,
        )
        candidate = EngineeringDemoResponse(
            outcome="ANSWERED",
            answer=rendered.answer,
            run_id=capability.run_id,
            snapshot_checksum=snapshot.snapshot_checksum,
            model_called=True,
            provider_call_count=provider_count,
            tool_call_count=tool_count,
            fallback_used=False,
            committed=False,
            profile_digest=sha256_value(profile),
            obligation_digest=rendered.obligation_digest,
            result=rendered.result,
        )
        store.commit(capability, candidate)
        return store.read_response(capability.run_id)
    except EngineeringGatewayError as exc:
        if exc.automatic_off_trigger:
            _trip_automatic_off(store, rollout, exc.automatic_off_trigger)
        return _failure(
            "FAILED_EXECUTION",
            "LLM_ADAPTIVE_EXECUTION_FAILED",
            run_id=capability.run_id,
            snapshot_checksum=snapshot.snapshot_checksum,
            profile_digest=sha256_value(profile),
            model_called=True,
            provider_call_count=provider_count,
            tool_call_count=tool_count,
        )
    except (ADTToolError, AnswerObligationError, EngineeringCommitConflict, OSError, ValueError):
        return _failure(
            "FAILED_EXECUTION",
            "LLM_ADAPTIVE_EXECUTION_FAILED",
            run_id=capability.run_id,
            snapshot_checksum=snapshot.snapshot_checksum,
            profile_digest=sha256_value(profile),
            model_called=True,
            provider_call_count=provider_count,
            tool_call_count=tool_count,
        )


def _failure(
    outcome: str,
    reason_code: str,
    *,
    run_id: str | None = None,
    snapshot_checksum: str | None = None,
    profile_digest: str | None = None,
    model_called: bool = False,
    provider_call_count: int = 0,
    tool_call_count: int = 0,
) -> EngineeringDemoResponse:
    return EngineeringDemoResponse(
        outcome=outcome,
        answer="",
        run_id=run_id,
        snapshot_checksum=snapshot_checksum,
        model_called=model_called,
        provider_call_count=provider_call_count,
        tool_call_count=tool_call_count,
        fallback_used=False,
        committed=False,
        reason_code=reason_code,
        profile_digest=profile_digest,
        result=None,
    )


def _trip_automatic_off(
    store: EngineeringDemoCommitStore,
    rollout: TaskRolloutRecord,
    trigger: str,
) -> None:
    try:
        store.trip_automatic_off(rollout, trigger)
    except EngineeringCommitConflict:
        # A concurrent rollout/off transition already prevents release.
        return


def _gateway_transport(
    url: str,
    body: dict[str, object],
    timeout: float,
) -> dict[str, object]:
    request = urllib.request.Request(
        url,
        data=canonical_bytes(body),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            error_payload = json.loads(exc.read().decode("utf-8"))
            detail = str(error_payload.get("detail", ""))
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        lowered = detail.lower()
        trigger = None
        if exc.code == 409:
            trigger = "LEAK_DETECTED" if "projection" in lowered else "PROFILE_MISMATCH"
        elif exc.code == 502:
            trigger = "SCHEMA_FAILURE"
        elif exc.code == 504:
            trigger = "DEADLINE_EXCEEDED"
        raise EngineeringGatewayError(
            "Internal model gateway rejected the request",
            automatic_off_trigger=trigger,
        ) from exc
    except (TimeoutError, socket.timeout) as exc:
        raise EngineeringGatewayError(
            "Internal model gateway deadline exceeded",
            automatic_off_trigger="DEADLINE_EXCEEDED",
        ) from exc
    except urllib.error.URLError as exc:
        trigger = (
            "DEADLINE_EXCEEDED"
            if isinstance(exc.reason, (TimeoutError, socket.timeout))
            else None
        )
        raise EngineeringGatewayError(
            "Internal model gateway call failed",
            automatic_off_trigger=trigger,
        ) from exc
    except json.JSONDecodeError as exc:
        raise EngineeringGatewayError(
            "Internal model gateway returned invalid JSON",
            automatic_off_trigger="SCHEMA_FAILURE",
        ) from exc
    if not isinstance(payload, dict):
        raise EngineeringGatewayError(
            "Internal model gateway returned a non-object response",
            automatic_off_trigger="SCHEMA_FAILURE",
        )
    return payload
