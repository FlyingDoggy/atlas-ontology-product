from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .io import canonical_bytes, file_checksum, sha256_value
from .models import StrictModel
from .scenario import BoundAnalysisGoal


class SolutionLlmExecution(StrictModel):
    """Safe, user-visible metadata for one solution-aware model attempt."""

    contract: Literal["solution-llm-execution/v1"] = "solution-llm-execution/v1"
    mode: Literal["OFF", "SHADOW", "ACTIVE"]
    status: Literal[
        "DETERMINISTIC_ONLY",
        "SHADOW_VERIFIED",
        "GROUNDED",
        "FALLBACK",
    ]
    provider: Literal["qwen"] = "qwen"
    requested_model: Literal["qwen3.8-max"] = "qwen3.8-max"
    model_called: bool
    provider_call_count: int = Field(ge=0, le=12)
    fallback_used: bool
    reason_code: str | None = None
    profile_checksum: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    activation_id: str | None = None


def deterministic_only(reason_code: str) -> SolutionLlmExecution:
    return SolutionLlmExecution(
        mode="OFF",
        status="DETERMINISTIC_ONLY",
        model_called=False,
        provider_call_count=0,
        fallback_used=False,
        reason_code=reason_code,
    )


class SolutionQuestionCase(StrictModel):
    case_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]+$")
    language: Literal["en", "zh"]
    question: str = Field(min_length=1, max_length=2000)
    expected_intent: str = Field(pattern=r"^[a-z][a-z0-9_]+$")
    required_tools: tuple[str, ...] = Field(min_length=1, max_length=12)


class SolutionQuestionFamily(StrictModel):
    contract: Literal["registered-question-family/v1"]
    family_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]+$")
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    classification: Literal["constructed_synthetic"]
    cases: tuple[SolutionQuestionCase, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def unique_cases(self) -> SolutionQuestionFamily:
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("Solution question case IDs must be unique")
        return self

    def resolve(self, case_id: str, question: str) -> SolutionQuestionCase | None:
        matches = [
            case
            for case in self.cases
            if case.case_id == case_id and case.question == question
        ]
        return matches[0] if len(matches) == 1 else None


class ProfileArtifactPin(StrictModel):
    artifact_id: Literal[
        "prompt-manifest", "tool-registry", "projection-policy", "question-family"
    ]
    relative_path: str = Field(min_length=1, max_length=200)
    checksum: str = Field(pattern=r"^[0-9a-f]{64}$")


class SolutionLlmBudgets(StrictModel):
    absolute_timeout_ms: int = Field(ge=1000, le=15000)
    provider_timeout_ms: int = Field(ge=500, le=10000)
    max_provider_calls: int = Field(ge=1, le=12)
    max_tool_calls: int = Field(ge=1, le=12)
    max_iterations: int = Field(ge=1, le=12)
    max_input_tokens: int = Field(ge=1, le=10000)
    max_output_tokens: int = Field(ge=1, le=2000)


class SolutionLlmProfile(StrictModel):
    contract: Literal["engineering-run-profile/v1"]
    profile_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]+$")
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    provider: Literal["qwen"]
    requested_model: Literal["qwen3.8-max"]
    accepted_response_models: tuple[Literal["qwen3.8-max"], ...] = Field(
        min_length=1
    )
    provider_account_ref: str = Field(min_length=1)
    endpoint_ref: str = Field(min_length=1)
    region: str = Field(min_length=1)
    artifact_pins: tuple[ProfileArtifactPin, ...] = Field(min_length=4, max_length=4)
    input_contracts: tuple[str, ...] = Field(min_length=1)
    output_contracts: tuple[str, ...] = Field(min_length=1)
    tool_ids: tuple[str, ...] = Field(min_length=1, max_length=12)
    budgets: SolutionLlmBudgets
    temperature: Literal[0]
    thinking: Literal[False]
    fallback_policy: Literal[
        "restart-original-trusted-request/v1",
        "deterministic-semantic-engine/v1",
    ]
    outcome_contract: Literal[
        "engineering-demo-five-outcome/v1",
        "analysis-response/v1",
    ]
    renderer_policy: Literal[
        "closed-answer-clause-deterministic-renderer/v1",
        "deepagent-natural-language/v1",
    ]
    trace_policy: Literal["safe-metadata-no-raw-content/v1"]

    @model_validator(mode="after")
    def unique_tools_and_pins(self) -> SolutionLlmProfile:
        if len(self.tool_ids) != len(set(self.tool_ids)):
            raise ValueError("Solution LLM tools must be unique")
        pin_ids = [pin.artifact_id for pin in self.artifact_pins]
        if len(pin_ids) != len(set(pin_ids)) or set(pin_ids) != {
            "prompt-manifest",
            "tool-registry",
            "projection-policy",
            "question-family",
        }:
            raise ValueError("Solution LLM artifact pin set is incomplete")
        return self


class SolutionLlmActivation(StrictModel):
    contract: Literal["solution-llm-activation/v1"]
    activation_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]+$")
    solution_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]+$")
    mode: Literal["SHADOW", "ACTIVE"]
    decision: Literal["ALLOW", "DENY"]
    provider: Literal["qwen"]
    requested_model: Literal["qwen3.8-max"]
    profile_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    question_family_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_manifest_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    projection_policy_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    issued_at: datetime
    expires_at: datetime
    approved_by: str = Field(min_length=1)

    def permits(
        self,
        *,
        solution_id: str,
        llm_root: Path,
        now: datetime,
    ) -> bool:
        return (
            self.decision == "ALLOW"
            and self.solution_id == solution_id
            and self.provider == "qwen"
            and self.requested_model == "qwen3.8-max"
            and self.profile_checksum
            == file_checksum(llm_root / "engineering-profile.json")
            and self.question_family_checksum
            == file_checksum(llm_root / "question-family.json")
            and self.prompt_manifest_checksum
            == file_checksum(llm_root / "prompts.json")
            and self.projection_policy_checksum
            == file_checksum(llm_root / "projection-policy.json")
            and self.issued_at <= now < self.expires_at
        )


class SolutionQuestionProjection(StrictModel):
    contract: Literal["model-question-projection/v1"]
    family_id: str
    family_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    case_id: str
    language: Literal["en", "zh"]
    question: str = Field(min_length=1, max_length=2000)
    allowed_intents: tuple[str, ...] = Field(min_length=1, max_length=1)


class SolutionModelGroundingRequest(StrictModel):
    contract: Literal["solution-model-grounding-request/v1"]
    solution_id: str
    snapshot_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    activation_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    projection_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    deadline_at: datetime
    projection: SolutionQuestionProjection


class SolutionBoundGoal(StrictModel):
    contract: Literal["solution-bound-goal/v1"]
    intent: str = Field(pattern=r"^[a-z][a-z0-9_]+$")
    tool_ids: tuple[str, ...] = Field(min_length=1, max_length=12)
    language: Literal["en", "zh"]


@dataclass(frozen=True, slots=True)
class SolutionGroundingOutcome:
    execution: SolutionLlmExecution
    bound_goal: BoundAnalysisGoal | None = None


class SolutionModelGroundingResponse(StrictModel):
    contract: Literal["solution-model-grounding-response/v1"]
    solution_id: str
    snapshot_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    requested_model: Literal["qwen3.8-max"]
    response_model: Literal["qwen3.8-max"]
    provider_request_id: str = Field(min_length=1)
    candidate: SolutionBoundGoal
    candidate_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object")
    return payload


def load_solution_question_family(llm_root: Path) -> SolutionQuestionFamily:
    return SolutionQuestionFamily.model_validate(
        _load_json(llm_root / "question-family.json")
    )


def load_solution_llm_profile(llm_root: Path) -> SolutionLlmProfile:
    path = llm_root / "engineering-profile.json"
    profile = SolutionLlmProfile.model_validate(_load_json(path))
    for pin in profile.artifact_pins:
        relative = Path(pin.relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Solution LLM profile artifact path is unsafe")
        artifact = (llm_root / relative).resolve()
        if not artifact.is_relative_to(llm_root.resolve()):
            raise ValueError("Solution LLM profile artifact escaped its package")
        if file_checksum(artifact) != pin.checksum:
            raise ValueError("Solution LLM profile artifact pin failed")
    return profile


def _activation_path(solution_id: str) -> Path | None:
    root_text = os.environ.get("ONTOLOGY_SOLUTION_LLM_ACTIVATION_DIR")
    if not root_text:
        return None
    if not solution_id or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for character in solution_id):
        return None
    return Path(root_text) / f"{solution_id}.json"


def attempt_solution_grounding(
    *,
    solution_id: str,
    scenario_dir: Path,
    snapshot_checksum: str,
    question_case_id: str | None,
    question: str,
    role_allowed: bool,
) -> SolutionGroundingOutcome:
    activation_path = _activation_path(solution_id)
    if activation_path is None or not activation_path.is_file():
        return SolutionGroundingOutcome(deterministic_only("ACTIVATION_NOT_AVAILABLE"))
    if not role_allowed:
        return SolutionGroundingOutcome(deterministic_only("ROLE_NOT_ELIGIBLE_FOR_MODEL"))
    llm_root = scenario_dir / "llm"
    try:
        activation = SolutionLlmActivation.model_validate(_load_json(activation_path))
        profile = load_solution_llm_profile(llm_root)
        family = load_solution_question_family(llm_root)
        now = datetime.now(timezone.utc)
        if not activation.permits(
            solution_id=solution_id,
            llm_root=llm_root,
            now=now,
        ):
            raise ValueError("Solution LLM activation is not eligible")
        if profile.tool_ids != tuple(
            dict.fromkeys(tool for case in family.cases for tool in case.required_tools)
        ):
            raise ValueError("Question-family tools do not match the exact run profile")
    except (OSError, ValueError):
        return SolutionGroundingOutcome(
            SolutionLlmExecution(
                mode="OFF",
                status="FALLBACK",
                model_called=False,
                provider_call_count=0,
                fallback_used=True,
                reason_code="ACTIVATION_INVALID",
            )
        )
    case = (
        family.resolve(question_case_id, question)
        if question_case_id is not None
        else None
    )
    if case is None:
        return SolutionGroundingOutcome(
            SolutionLlmExecution(
                mode=activation.mode,
                status="DETERMINISTIC_ONLY",
                model_called=False,
                provider_call_count=0,
                fallback_used=False,
                reason_code="QUESTION_NOT_REGISTERED",
                profile_checksum=activation.profile_checksum,
                activation_id=activation.activation_id,
            )
        )
    trusted_case_goal = BoundAnalysisGoal(
        intent=case.expected_intent,
        tool_ids=case.required_tools,
        language=case.language,
    )
    gateway_url = os.environ.get("ONTOLOGY_MODEL_GATEWAY_URL")
    if not gateway_url:
        return SolutionGroundingOutcome(
            SolutionLlmExecution(
                mode=activation.mode,
                status="FALLBACK",
                model_called=False,
                provider_call_count=0,
                fallback_used=True,
                reason_code="MODEL_GATEWAY_NOT_AVAILABLE",
                profile_checksum=activation.profile_checksum,
                activation_id=activation.activation_id,
            ),
            bound_goal=trusted_case_goal,
        )
    projection = SolutionQuestionProjection(
        contract="model-question-projection/v1",
        family_id=family.family_id,
        family_checksum=file_checksum(llm_root / "question-family.json"),
        case_id=case.case_id,
        language=case.language,
        question=case.question,
        allowed_intents=(case.expected_intent,),
    )
    request = SolutionModelGroundingRequest(
        contract="solution-model-grounding-request/v1",
        solution_id=solution_id,
        snapshot_checksum=snapshot_checksum,
        profile_checksum=activation.profile_checksum,
        activation_checksum=file_checksum(activation_path),
        projection_checksum=sha256_value(projection),
        deadline_at=now + timedelta(milliseconds=profile.budgets.absolute_timeout_ms),
        projection=projection,
    )
    try:
        raw = _gateway_transport(
            gateway_url.rstrip("/") + "/model/v1/solution-ground",
            request.model_dump(mode="json"),
            profile.budgets.provider_timeout_ms / 1000,
        )
        grounded = SolutionModelGroundingResponse.model_validate(raw)
        if (
            grounded.solution_id != solution_id
            or grounded.snapshot_checksum != snapshot_checksum
            or grounded.requested_model != profile.requested_model
            or grounded.response_model not in profile.accepted_response_models
            or grounded.candidate_checksum != sha256_value(grounded.candidate)
            or grounded.candidate.intent != case.expected_intent
            or grounded.candidate.tool_ids != case.required_tools
            or grounded.candidate.language != case.language
        ):
            raise ValueError("Solution model grounding escaped its registered case")
    except (OSError, ValueError):
        return SolutionGroundingOutcome(
            SolutionLlmExecution(
                mode=activation.mode,
                status="FALLBACK",
                model_called=True,
                provider_call_count=1,
                fallback_used=True,
                reason_code="MODEL_GROUNDING_FAILED",
                profile_checksum=activation.profile_checksum,
                activation_id=activation.activation_id,
            ),
            bound_goal=trusted_case_goal,
        )
    execution = SolutionLlmExecution(
        mode=activation.mode,
        status=("SHADOW_VERIFIED" if activation.mode == "SHADOW" else "GROUNDED"),
        model_called=True,
        provider_call_count=1,
        fallback_used=False,
        profile_checksum=activation.profile_checksum,
        activation_id=activation.activation_id,
    )
    return SolutionGroundingOutcome(
        execution=execution,
        bound_goal=(
            BoundAnalysisGoal(
                intent=grounded.candidate.intent,
                tool_ids=grounded.candidate.tool_ids,
                language=grounded.candidate.language,
            )
            if activation.mode == "ACTIVE"
            else None
        ),
    )


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
            raw = response.read(256_001)
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        raise OSError("Solution model gateway request failed") from exc
    if len(raw) > 256_000:
        raise OSError("Solution model gateway response is too large")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OSError("Solution model gateway returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise OSError("Solution model gateway returned an invalid object")
    return payload
