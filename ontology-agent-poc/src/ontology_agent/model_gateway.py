from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException

from .io import (
    DEFAULT_CASH_TRADING_SCENARIO_DIR,
    DEFAULT_SCENARIO_DIR,
    canonical_bytes,
    file_checksum,
    sha256_value,
)
from .llm_contracts import (
    DEMO_PROVIDER,
    DEMO_REQUESTED_MODEL,
    BoundGoalCandidate,
    ModelGroundingRequest,
    ModelGroundingResponse,
    ModelNextToolRequest,
    ModelNextToolResponse,
    NextToolSelection,
    build_question_projection,
    load_egress_decision,
    load_question_family,
    load_run_profile,
)
from .studio.llm import (
    StudioObservationCandidateSet,
    StudioObservationPayload,
    StudioObservationRequest,
    load_semantic_slot_manifest,
    load_studio_egress_decision,
    load_studio_run_profile,
)
from .studio.builder import (
    BuilderPhaseOutputV1,
    BuilderPhaseRequestV1,
    BuilderPhaseResponseV1,
)
from .studio.reviewer import (
    ReviewerOutputV1,
    ReviewerRequestV1,
    ReviewerResponseV1,
)
from .studio.skill_packages import SkillPackageError, load_skill_package
from .solution_llm import (
    SolutionBoundGoal,
    SolutionLlmActivation,
    SolutionModelGroundingRequest,
    SolutionModelGroundingResponse,
    SolutionQuestionProjection,
    load_solution_llm_profile,
    load_solution_question_family,
)


app = FastAPI(
    title="Ontology Engineering Demo Model Gateway",
    description=(
        "Internal-only Qwen transport. This service owns the provider secret and is not "
        "an Ontology Studio or Analytic Agent product surface."
    ),
)


@app.get("/model/healthz")
def health() -> dict[str, str]:
    return {
        "status": "alive",
        "provider": DEMO_PROVIDER,
        "requested_model": DEMO_REQUESTED_MODEL,
    }


@app.post("/model/v1/ontology-build", response_model=BuilderPhaseResponseV1)
def ontology_build(request: BuilderPhaseRequestV1) -> BuilderPhaseResponseV1:
    """Execute one bounded Build Skill phase through the internal model gateway."""
    if os.environ.get("ONTOLOGY_BUILDER_LLM_ENABLED", "").strip().lower() not in {
        "1",
        "true",
        "yes",
    }:
        raise HTTPException(status_code=503, detail="Ontology Builder is disabled")
    key = os.environ.get("ONTOLOGY_QWEN_API_KEY")
    base_url = os.environ.get("ONTOLOGY_QWEN_BASE_URL")
    if not key or not base_url:
        raise HTTPException(status_code=503, detail="Ontology Builder model is not configured")
    skill_root_raw = os.environ.get("ONTOLOGY_SKILL_ROOT")
    try:
        skill = load_skill_package(
            request.skill_id,
            request.skill_version,
            root=Path(skill_root_raw) if skill_root_raw else None,
        )
    except SkillPackageError as exc:
        raise HTTPException(status_code=503, detail="Ontology Build Skill is unavailable") from exc
    if (
        skill.manifest.role != "BUILDER"
        or skill.package_checksum != request.skill_checksum
        or request.allowed_collections
        != tuple(
            {
                "SEMANTIC": ("actors", "processes", "entities", "properties", "relationships"),
                "ANALYTICS": (
                    "dimensions", "rules", "metrics", "analysis_patterns", "policies", "questions"
                ),
                "DATA": ("data_sources", "bindings", "joins", "sql_contracts"),
            }[request.phase]
        )
    ):
        raise HTTPException(status_code=409, detail="Ontology Builder authority mismatch")

    requested_model = os.environ.get("ONTOLOGY_BUILDER_MODEL", "qwen3.8-max").strip()
    if not requested_model:
        raise HTTPException(status_code=503, detail="Ontology Builder model is invalid")
    schema = BuilderPhaseOutputV1.model_json_schema()
    schema["properties"]["phase"] = {"const": request.phase, "type": "string"}
    schema["properties"]["request_digest"] = {
        "const": request.request_digest,
        "type": "string",
    }
    reference_rules = "\n\n".join(skill.reference_texts.values())
    system_prompt = (
        skill.instructions
        + "\n\n"
        + reference_rules
        + "\n\nThe request contains the only allowed evidence and exact typed asset schemas. "
        "Return one closed phase result."
    )
    provider_body: dict[str, Any] = {
        "model": requested_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            _closed_output_contract_message(schema),
            {
                "role": "user",
                "content": canonical_bytes(request).decode("utf-8"),
            },
        ],
        "temperature": 0,
        "max_tokens": int(os.environ.get("ONTOLOGY_BUILDER_MAX_OUTPUT_TOKENS", "8000")),
        "response_format": {"type": "json_object"},
        "enable_thinking": False,
        "stream": False,
    }
    timeout = float(os.environ.get("ONTOLOGY_BUILDER_PROVIDER_TIMEOUT_SECONDS", "60"))
    try:
        raw = _provider_transport(
            str(base_url).rstrip("/") + "/chat/completions",
            {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            provider_body,
            timeout,
        )
        response_model = raw["model"]
        provider_request_id = raw["id"]
        content = raw["choices"][0]["message"]["content"]
        if (
            not isinstance(response_model, str)
            or not response_model
            or not isinstance(provider_request_id, str)
            or not provider_request_id
            or not isinstance(content, str)
        ):
            raise ValueError("Provider response identity is invalid")
        raw_output = json.loads(content)
        if not isinstance(raw_output, dict):
            raise ValueError("Builder output must be a JSON object")
        # Request identity and loop closure are control-plane facts. The model
        # proposes domain content; it does not get authority to declare which
        # request it answered or whether the bounded phase is complete.
        raw_output.update(
            {
                "contract": "builder-phase-output/v1",
                "phase": request.phase,
                "request_digest": request.request_digest,
                "done": True,
            }
        )
        output = BuilderPhaseOutputV1.model_validate(raw_output)
        if len(output.proposals) > request.max_proposals:
            raise ValueError("Builder output escaped its exact request")
    except (KeyError, IndexError, TypeError, ValueError, OSError) as exc:
        raise HTTPException(status_code=502, detail="Ontology Builder provider request failed") from exc
    return BuilderPhaseResponseV1(
        requested_model=requested_model,
        response_model=response_model,
        provider_request_id=provider_request_id,
        output=output,
        output_digest=sha256_value(output),
    )


@app.post("/model/v1/ontology-review", response_model=ReviewerResponseV1)
def ontology_review(request: ReviewerRequestV1) -> ReviewerResponseV1:
    """Run an independent Review Skill that can emit findings, never decisions."""
    if os.environ.get("ONTOLOGY_REVIEWER_LLM_ENABLED", "").strip().lower() not in {
        "1",
        "true",
        "yes",
    }:
        raise HTTPException(status_code=503, detail="Ontology Reviewer is disabled")
    key = os.environ.get("ONTOLOGY_QWEN_API_KEY")
    base_url = os.environ.get("ONTOLOGY_QWEN_BASE_URL")
    if not key or not base_url:
        raise HTTPException(status_code=503, detail="Ontology Reviewer model is not configured")
    skill_root_raw = os.environ.get("ONTOLOGY_SKILL_ROOT")
    try:
        skill = load_skill_package(
            request.skill_id,
            request.skill_version,
            root=Path(skill_root_raw) if skill_root_raw else None,
        )
    except SkillPackageError as exc:
        raise HTTPException(status_code=503, detail="Ontology Review Skill is unavailable") from exc
    if (
        skill.manifest.role != "REVIEWER"
        or skill.package_checksum != request.skill_checksum
        or skill.manifest.direct_draft_write
        or not skill.manifest.human_review_required
    ):
        raise HTTPException(status_code=409, detail="Ontology Reviewer authority mismatch")

    requested_model = os.environ.get("ONTOLOGY_REVIEWER_MODEL", "qwen3.8-max").strip()
    if not requested_model:
        raise HTTPException(status_code=503, detail="Ontology Reviewer model is invalid")
    schema = ReviewerOutputV1.model_json_schema()
    schema["properties"]["request_digest"] = {
        "const": request.request_digest,
        "type": "string",
    }
    reference_rules = "\n\n".join(skill.reference_texts.values())
    system_prompt = (
        skill.instructions
        + "\n\n"
        + reference_rules
        + "\n\nThis is a fresh review context. Candidate projections intentionally omit "
        "Builder rationale and private reasoning. Return findings only; never return "
        "approval, disposition, Draft operations, publication or activation actions."
    )
    provider_body: dict[str, Any] = {
        "model": requested_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            _closed_output_contract_message(schema),
            {"role": "user", "content": canonical_bytes(request).decode("utf-8")},
        ],
        "temperature": 0,
        "max_tokens": int(
            os.environ.get("ONTOLOGY_REVIEWER_MAX_OUTPUT_TOKENS", "8000")
        ),
        "response_format": {"type": "json_object"},
        "enable_thinking": False,
        "stream": False,
    }
    timeout = float(
        os.environ.get("ONTOLOGY_REVIEWER_PROVIDER_TIMEOUT_SECONDS", "60")
    )
    try:
        raw = _provider_transport(
            str(base_url).rstrip("/") + "/chat/completions",
            {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            provider_body,
            timeout,
        )
        response_model = raw["model"]
        provider_request_id = raw["id"]
        content = raw["choices"][0]["message"]["content"]
        if (
            not isinstance(response_model, str)
            or not response_model
            or not isinstance(provider_request_id, str)
            or not provider_request_id
            or not isinstance(content, str)
        ):
            raise ValueError("Provider response identity is invalid")
        output = ReviewerOutputV1.model_validate_json(content)
        candidate_ids = {item.candidate_id for item in request.candidates}
        evidence_ids = {item.fragment_id for item in request.evidence_fragments}
        if (
            output.request_digest != request.request_digest
            or not output.done
            or len(output.findings) > request.max_findings
            or any(
                not set(item.candidate_ids).issubset(candidate_ids)
                or not set(item.evidence_fragment_ids).issubset(evidence_ids)
                for item in output.findings
            )
        ):
            raise ValueError("Reviewer output escaped its exact request")
    except (KeyError, IndexError, TypeError, ValueError, OSError) as exc:
        raise HTTPException(status_code=502, detail="Ontology Reviewer provider request failed") from exc
    return ReviewerResponseV1(
        requested_model=requested_model,
        response_model=response_model,
        provider_request_id=provider_request_id,
        output=output,
        output_digest=sha256_value(output),
    )


def _solution_scenario_dir(solution_id: str) -> Path:
    installed = {
        "ontology.exchange_analytics.adt": DEFAULT_SCENARIO_DIR,
        "ontology.exchange_analytics.cash_trading": DEFAULT_CASH_TRADING_SCENARIO_DIR,
    }
    try:
        return installed[solution_id]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Solution model profile is not installed") from exc


@app.post("/model/v1/solution-ground")
def solution_ground(request: SolutionModelGroundingRequest) -> dict[str, Any]:
    key = os.environ.get("ONTOLOGY_QWEN_API_KEY")
    base_url = os.environ.get("ONTOLOGY_QWEN_BASE_URL")
    activation_root = os.environ.get("ONTOLOGY_SOLUTION_LLM_ACTIVATION_DIR")
    if not all((key, base_url, activation_root)):
        raise HTTPException(status_code=503, detail="Solution model gateway is not configured")
    scenario_dir = _solution_scenario_dir(request.solution_id)
    llm_root = scenario_dir / "llm"
    activation_path = Path(str(activation_root)) / f"{request.solution_id}.json"
    try:
        activation = SolutionLlmActivation.model_validate(
            json.loads(activation_path.read_text(encoding="utf-8"))
        )
        profile = load_solution_llm_profile(llm_root)
        family = load_solution_question_family(llm_root)
        projection_policy = json.loads(
            (llm_root / "projection-policy.json").read_text(encoding="utf-8")
        )
        prompt_manifest = json.loads(
            (llm_root / "prompts.json").read_text(encoding="utf-8")
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail="Solution model gateway is not ready") from exc

    now = datetime.now(timezone.utc)
    case = family.resolve(request.projection.case_id, request.projection.question)
    expected_projection = (
        SolutionQuestionProjection(
            contract="model-question-projection/v1",
            family_id=family.family_id,
            family_checksum=file_checksum(llm_root / "question-family.json"),
            case_id=case.case_id,
            language=case.language,
            question=case.question,
            allowed_intents=(case.expected_intent,),
        )
        if case is not None
        else None
    )
    if (
        not activation.permits(
            solution_id=request.solution_id,
            llm_root=llm_root,
            now=now,
        )
        or activation.mode not in {"SHADOW", "ACTIVE"}
        or request.profile_checksum != activation.profile_checksum
        or request.profile_checksum != file_checksum(llm_root / "engineering-profile.json")
        or request.activation_checksum != file_checksum(activation_path)
        or request.projection_checksum != sha256_value(request.projection)
        or expected_projection is None
        or request.projection != expected_projection
        or not (now < request.deadline_at <= now + timedelta(milliseconds=profile.budgets.absolute_timeout_ms + 1000))
        or any(tool not in profile.tool_ids for tool in case.required_tools)
    ):
        raise HTTPException(status_code=409, detail="Solution model request authority mismatch")

    allowed_fields = projection_policy.get("question_projection_fields")
    if not isinstance(allowed_fields, list) or not set(
        request.projection.model_dump(mode="json")
    ).issubset(set(allowed_fields)):
        raise HTTPException(status_code=409, detail="Solution model projection is not allowed")
    try:
        prompt = next(
            item["text"]
            for item in prompt_manifest["prompts"]
            if item["task"] == "goal_grounding"
        )
    except (KeyError, StopIteration, TypeError) as exc:
        raise HTTPException(status_code=503, detail="Solution model profile is not ready") from exc

    output_schema = SolutionBoundGoal.model_json_schema()
    output_schema["properties"]["intent"] = {"const": case.expected_intent}
    output_schema["properties"]["tool_ids"] = {"const": list(case.required_tools)}
    output_schema["properties"]["language"] = {"const": case.language}
    provider_body: dict[str, Any] = {
        "model": profile.requested_model,
        "messages": [
            {"role": "system", "content": prompt},
            _closed_output_contract_message(output_schema),
            {
                "role": "user",
                "content": canonical_bytes(request.projection).decode("utf-8"),
            },
        ],
        "temperature": profile.temperature,
        "max_tokens": profile.budgets.max_output_tokens,
        "response_format": {"type": "json_object"},
        "enable_thinking": profile.thinking,
        "stream": False,
    }
    serialized_body = canonical_bytes(provider_body).decode("utf-8").lower()
    denied_tokens = projection_policy.get("denied_field_tokens")
    if not isinstance(denied_tokens, list) or any(
        not isinstance(token, str) or token.lower() in serialized_body
        for token in denied_tokens
    ):
        raise HTTPException(status_code=409, detail="Solution model projection is not allowed")

    remaining = (request.deadline_at - now).total_seconds()
    timeout = min(profile.budgets.provider_timeout_ms / 1000, remaining)
    try:
        raw = _provider_transport(
            str(base_url).rstrip("/") + "/chat/completions",
            {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            provider_body,
            timeout,
        )
        response_model = raw["model"]
        request_id = raw["id"]
        content = raw["choices"][0]["message"]["content"]
        candidate = SolutionBoundGoal.model_validate_json(content)
        if (
            response_model not in profile.accepted_response_models
            or not isinstance(request_id, str)
            or not request_id
            or candidate.intent != case.expected_intent
            or candidate.tool_ids != case.required_tools
            or candidate.language != case.language
        ):
            raise ValueError("Solution model candidate escaped its registered case")
    except (KeyError, IndexError, TypeError, ValueError, OSError) as exc:
        raise HTTPException(status_code=502, detail="Model provider request failed") from exc

    response = SolutionModelGroundingResponse(
        contract="solution-model-grounding-response/v1",
        solution_id=request.solution_id,
        snapshot_checksum=request.snapshot_checksum,
        requested_model=profile.requested_model,
        response_model=response_model,
        provider_request_id=request_id,
        candidate=candidate,
        candidate_checksum=sha256_value(candidate),
    )
    return response.model_dump(mode="json")


@app.post("/model/v1/ground")
def ground(request: ModelGroundingRequest) -> dict[str, Any]:
    key = os.environ.get("ONTOLOGY_QWEN_API_KEY")
    base_url = os.environ.get("ONTOLOGY_QWEN_BASE_URL")
    egress_path = os.environ.get("ONTOLOGY_LLM_EGRESS_DECISION_PATH")
    profile_path = os.environ.get("ONTOLOGY_LLM_PROFILE_PATH")
    family_path = os.environ.get("ONTOLOGY_LLM_QUESTION_FAMILY_PATH")
    if not all((key, base_url, egress_path, profile_path, family_path)):
        raise HTTPException(status_code=503, detail="Model gateway is not configured")
    try:
        egress = load_egress_decision(Path(egress_path))
        profile = load_run_profile(Path(profile_path))
        family = load_question_family(Path(family_path))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Model gateway is not ready") from exc

    now = datetime.now(timezone.utc)
    case = family.resolve(request.projection.case_id, request.projection.question)
    expected_projection = build_question_projection(family, case) if case else None
    if (
        not egress.permits(family, now=now)
        or not profile.matches(egress)
        or request.profile_digest != sha256_value(profile)
        or request.profile_digest != request.capability.profile_digest
        or request.egress_decision_digest != sha256_value(egress)
        or request.egress_decision_digest
        != request.capability.egress_decision_digest
        or request.capability.question_family_checksum != sha256_value(family)
        or request.capability.question_case_id != request.projection.case_id
        or request.capability.tool_ids != profile.tool_ids
        or expected_projection is None
        or request.projection != expected_projection
        or request.projection_digest != sha256_value(request.projection)
        or not (
            request.capability.issued_at
            <= now
            < request.deadline_at
            <= request.capability.expires_at
        )
    ):
        raise HTTPException(status_code=409, detail="Model request authority mismatch")

    try:
        prompt_manifest = json.loads(
            (Path(profile_path).parent / "prompts.json").read_text(encoding="utf-8")
        )
        projection_policy = json.loads(
            (Path(profile_path).parent / "projection-policy.json").read_text(
                encoding="utf-8"
            )
        )
        prompt = next(
            item["text"]
            for item in prompt_manifest["prompts"]
            if item["task"] == "goal_grounding"
        )
    except (OSError, KeyError, StopIteration, TypeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Model gateway is not ready") from exc

    provider_body: dict[str, Any] = {
        "model": profile.requested_model,
        "messages": [
            {"role": "system", "content": prompt},
            _closed_output_contract_message(_bound_goal_schema(case)),
            {
                "role": "user",
                "content": canonical_bytes(request.projection).decode("utf-8"),
            },
        ],
        "temperature": profile.temperature,
        "max_tokens": profile.budgets.max_output_tokens,
        "response_format": {"type": "json_object"},
        "enable_thinking": profile.thinking,
        "stream": False,
    }
    serialized_body = canonical_bytes(provider_body).decode("utf-8").lower()
    denied_tokens = projection_policy.get("denied_field_tokens")
    if not isinstance(denied_tokens, list) or any(
        not isinstance(token, str) or token.lower() in serialized_body
        for token in denied_tokens
    ):
        raise HTTPException(status_code=409, detail="Model projection is not allowed")

    remaining = (request.deadline_at - now).total_seconds()
    timeout = min(profile.budgets.provider_timeout_ms / 1000, remaining)
    try:
        raw = _provider_transport(
            str(base_url).rstrip("/") + "/chat/completions",
            {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            provider_body,
            timeout,
        )
        response_model = raw["model"]
        request_id = raw["id"]
        content = raw["choices"][0]["message"]["content"]
        if response_model not in profile.accepted_response_models:
            raise ValueError("Provider model identity mismatch")
        if not isinstance(request_id, str) or not request_id:
            raise ValueError("Provider request id is missing")
        goal = BoundGoalCandidate.model_validate_json(content)
        if (
            goal.language != request.projection.language
            or goal.intent != case.expected_intent
            or goal.requested_analyses != case.required_tools
            or any(
                analysis not in request.capability.tool_ids
                for analysis in goal.requested_analyses
            )
        ):
            raise ValueError("Grounded goal escaped the closed projection")
    except (KeyError, IndexError, TypeError, ValueError, OSError) as exc:
        raise HTTPException(status_code=502, detail="Model provider request failed") from exc

    response = ModelGroundingResponse(
        contract="model-grounding-response/v1",
        run_id=request.capability.run_id,
        requested_model=profile.requested_model,
        response_model=response_model,
        provider_request_id=request_id,
        goal=goal,
        output_digest=sha256_value(goal),
    )
    return response.model_dump(mode="json")


@app.post("/model/v1/next-tool")
def next_tool(request: ModelNextToolRequest) -> dict[str, Any]:
    key = os.environ.get("ONTOLOGY_QWEN_API_KEY")
    base_url = os.environ.get("ONTOLOGY_QWEN_BASE_URL")
    egress_path = os.environ.get("ONTOLOGY_LLM_EGRESS_DECISION_PATH")
    profile_path = os.environ.get("ONTOLOGY_LLM_PROFILE_PATH")
    family_path = os.environ.get("ONTOLOGY_LLM_QUESTION_FAMILY_PATH")
    if not all((key, base_url, egress_path, profile_path, family_path)):
        raise HTTPException(status_code=503, detail="Model gateway is not configured")
    try:
        egress = load_egress_decision(Path(egress_path))
        profile = load_run_profile(Path(profile_path))
        family = load_question_family(Path(family_path))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Model gateway is not ready") from exc

    now = datetime.now(timezone.utc)
    case = next(
        (
            item
            for item in family.cases
            if item.case_id == request.capability.question_case_id
        ),
        None,
    )
    if (
        not egress.permits(family, now=now)
        or "model-evidence-projection/v1"
        not in egress.allowed_projection_contracts
        or not profile.matches(egress)
        or request.profile_digest != sha256_value(profile)
        or request.profile_digest != request.capability.profile_digest
        or request.egress_decision_digest != sha256_value(egress)
        or request.egress_decision_digest
        != request.capability.egress_decision_digest
        or request.capability.question_family_checksum != sha256_value(family)
        or request.capability.tool_ids != profile.tool_ids
        or request.projection.run_id != request.capability.run_id
        or request.projection_digest != sha256_value(request.projection)
        or case is None
        or request.goal.intent != case.expected_intent
        or request.goal.language != case.language
        or request.goal.requested_analyses != case.required_tools
        or any(
            action != "finish" and action not in request.capability.tool_ids
            for action in request.allowed_next_actions
        )
        or not (
            request.capability.issued_at
            <= now
            < request.deadline_at
            <= request.capability.expires_at
        )
    ):
        raise HTTPException(status_code=409, detail="Model request authority mismatch")

    try:
        prompt_manifest = json.loads(
            (Path(profile_path).parent / "prompts.json").read_text(encoding="utf-8")
        )
        projection_policy = json.loads(
            (Path(profile_path).parent / "projection-policy.json").read_text(
                encoding="utf-8"
            )
        )
        prompt = next(
            item["text"]
            for item in prompt_manifest["prompts"]
            if item["task"] == "next_tool_selection"
        )
    except (OSError, KeyError, StopIteration, TypeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Model gateway is not ready") from exc

    model_input = {
        "goal": request.goal.model_dump(mode="json"),
        "verified_result": request.projection.model_dump(mode="json"),
        "allowed_next_actions": list(request.allowed_next_actions),
    }
    provider_body: dict[str, Any] = {
        "model": profile.requested_model,
        "messages": [
            {"role": "system", "content": prompt},
            _closed_output_contract_message(NextToolSelection.model_json_schema()),
            {"role": "user", "content": canonical_bytes(model_input).decode("utf-8")},
        ],
        "temperature": profile.temperature,
        "max_tokens": profile.budgets.max_output_tokens,
        "response_format": {"type": "json_object"},
        "enable_thinking": profile.thinking,
        "stream": False,
    }
    serialized_body = canonical_bytes(provider_body).decode("utf-8").lower()
    denied_tokens = projection_policy.get("denied_field_tokens")
    if not isinstance(denied_tokens, list) or any(
        not isinstance(token, str) or token.lower() in serialized_body
        for token in denied_tokens
    ):
        raise HTTPException(status_code=409, detail="Model projection is not allowed")

    remaining = (request.deadline_at - now).total_seconds()
    timeout = min(profile.budgets.provider_timeout_ms / 1000, remaining)
    try:
        raw = _provider_transport(
            str(base_url).rstrip("/") + "/chat/completions",
            {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            provider_body,
            timeout,
        )
        response_model = raw["model"]
        request_id = raw["id"]
        content = raw["choices"][0]["message"]["content"]
        if response_model not in profile.accepted_response_models:
            raise ValueError("Provider model identity mismatch")
        if not isinstance(request_id, str) or not request_id:
            raise ValueError("Provider request id is missing")
        selection = NextToolSelection.model_validate_json(content)
        selected_action = selection.next_tool or "finish"
        if selected_action not in request.allowed_next_actions:
            raise ValueError("Model selected an action outside the closed allowlist")
    except (KeyError, IndexError, TypeError, ValueError, OSError) as exc:
        raise HTTPException(status_code=502, detail="Model provider request failed") from exc

    response = ModelNextToolResponse(
        contract="model-next-tool-response/v1",
        run_id=request.capability.run_id,
        requested_model=profile.requested_model,
        response_model=response_model,
        provider_request_id=request_id,
        selection=selection,
        output_digest=sha256_value(selection),
    )
    return response.model_dump(mode="json")


@app.post("/model/v1/studio-observe")
def studio_observe(request: StudioObservationRequest) -> dict[str, Any]:
    key = os.environ.get("ONTOLOGY_QWEN_API_KEY")
    base_url = os.environ.get("ONTOLOGY_QWEN_BASE_URL")
    egress_path = os.environ.get("ONTOLOGY_STUDIO_LLM_EGRESS_DECISION_PATH")
    profile_path = os.environ.get("ONTOLOGY_STUDIO_LLM_PROFILE_PATH")
    slot_manifest_path = os.environ.get("ONTOLOGY_STUDIO_LLM_SLOT_MANIFEST_PATH")
    if not all((key, base_url, egress_path, profile_path, slot_manifest_path)):
        raise HTTPException(status_code=503, detail="Studio model gateway is not configured")
    try:
        egress = load_studio_egress_decision(Path(str(egress_path)))
        profile = load_studio_run_profile(Path(str(profile_path)))
        manifest = load_semantic_slot_manifest(Path(str(slot_manifest_path)))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Studio model gateway is not ready") from exc

    now = datetime.now(timezone.utc)
    projection = request.projection
    if (
        not egress.permits(
            profile=profile,
            slot_manifest=manifest,
            intake_submission_id=projection.intake_submission_id,
            now=now,
        )
        or request.profile_digest != sha256_value(profile)
        or request.slot_manifest_digest != sha256_value(manifest)
        or request.egress_decision_digest != sha256_value(egress)
        or request.projection_digest != sha256_value(projection)
        or tuple(item.slot_id for item in projection.slots)
        != tuple(item.slot_id for item in manifest.slots)
        or not (now < request.deadline_at)
    ):
        raise HTTPException(status_code=409, detail="Studio model request authority mismatch")

    for slot, definition in zip(projection.slots, manifest.slots, strict=True):
        if (
            slot.draft_path != definition.draft_path
            or slot.value_kind != definition.value_kind
            or slot.required != definition.required
            or slot.allowed_values != definition.allowed_values
        ):
            raise HTTPException(status_code=409, detail="Studio slot projection mismatch")
        if slot.source_fragment is not None:
            unsigned_fragment = {
                "asset_id": slot.source_fragment.asset_id,
                "locator": slot.source_fragment.locator,
                "text": slot.source_fragment.text,
            }
            if sha256_value(unsigned_fragment) != slot.source_fragment.checksum:
                raise HTTPException(status_code=409, detail="Studio source fragment mismatch")

    try:
        profile_root = Path(str(profile_path)).parent
        prompt_manifest = json.loads(
            (profile_root / profile.prompt_manifest_path).read_text(encoding="utf-8")
        )
        projection_policy = json.loads(
            (profile_root / profile.projection_policy_path).read_text(encoding="utf-8")
        )
        prompt = next(
            item["text"]
            for item in prompt_manifest["prompts"]
            if item["task"] == "adt_observation_extraction"
        )
    except (OSError, KeyError, StopIteration, TypeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Studio model profile is not ready") from exc

    provider_body: dict[str, Any] = {
        "model": profile.requested_model,
        "messages": [
            {"role": "system", "content": prompt},
            _closed_output_contract_message(StudioObservationPayload.model_json_schema()),
            {
                "role": "user",
                "content": canonical_bytes(projection).decode("utf-8"),
            },
        ],
        "temperature": profile.temperature,
        "max_tokens": profile.max_output_tokens,
        "response_format": {"type": "json_object"},
        "enable_thinking": profile.thinking,
        "stream": False,
    }
    serialized_body = canonical_bytes(provider_body).decode("utf-8").lower()
    denied_tokens = projection_policy.get("denied_field_tokens")
    if not isinstance(denied_tokens, list) or any(
        not isinstance(token, str) or token.lower() in serialized_body
        for token in denied_tokens
    ):
        raise HTTPException(status_code=409, detail="Studio model projection is not allowed")

    remaining = (request.deadline_at - now).total_seconds()
    timeout = min(profile.provider_timeout_ms / 1000, remaining)
    try:
        raw = _provider_transport(
            str(base_url).rstrip("/") + "/chat/completions",
            {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            provider_body,
            timeout,
        )
        response_model = raw["model"]
        request_id = raw["id"]
        content = raw["choices"][0]["message"]["content"]
        if response_model not in profile.accepted_response_models:
            raise ValueError("Provider model identity mismatch")
        if not isinstance(request_id, str) or not request_id:
            raise ValueError("Provider request id is missing")
        raw_payload = json.loads(content)
        if isinstance(raw_payload, dict) and isinstance(
            raw_payload.get("observations"), list
        ):
            for candidate in raw_payload["observations"]:
                if isinstance(candidate, dict) and candidate.get("status") == "MISSING":
                    # A fail-safe canonicalization may only remove unsupported claims.
                    candidate["support_code"] = "MISSING_SOURCE"
                    candidate["source_fragment_checksum"] = None
                    candidate["value"] = None
        payload = StudioObservationPayload.model_validate(raw_payload)
    except (KeyError, IndexError, TypeError, ValueError, OSError) as exc:
        raise HTTPException(status_code=502, detail="Studio model provider request failed") from exc

    if tuple(item.slot_id for item in payload.observations) != tuple(
        item.slot_id for item in manifest.slots
    ):
        raise HTTPException(status_code=502, detail="Studio observation denominator mismatch")
    for candidate, projected, definition in zip(
        payload.observations, projection.slots, manifest.slots, strict=True
    ):
        fragment = projected.source_fragment
        if fragment is None:
            if candidate.status != "MISSING":
                raise HTTPException(status_code=502, detail="Unsupported Studio observation")
            continue
        if (
            candidate.status == "PROPOSED"
            and candidate.source_fragment_checksum != fragment.checksum
        ):
            raise HTTPException(status_code=502, detail="Studio observation anchor mismatch")
        if candidate.value is not None:
            if candidate.value.kind != definition.value_kind:
                raise HTTPException(status_code=502, detail="Studio observation type mismatch")
            value = candidate.value.python_value()
            values = value if isinstance(value, tuple) else (value,)
            if definition.allowed_values and any(
                item not in definition.allowed_values for item in values
            ):
                raise HTTPException(status_code=502, detail="Studio observation value mismatch")

    response = StudioObservationCandidateSet(
        contract="studio-observation-candidate-set/v1",
        run_id=request.run_id,
        requested_model=profile.requested_model,
        response_model=response_model,
        provider_request_id=request_id,
        observations=payload.observations,
    )
    return response.model_dump(mode="json")


def _closed_output_contract_message(schema: dict[str, Any]) -> dict[str, str]:
    return {
        "role": "system",
        "content": (
            "Return exactly one JSON object and no prose. The object must validate "
            "against this closed JSON Schema: "
            + canonical_bytes(schema).decode("utf-8")
        ),
    }


def _bound_goal_schema(case: Any) -> dict[str, Any]:
    schema = BoundGoalCandidate.model_json_schema()
    properties = schema["properties"]
    properties["intent"] = {"const": case.expected_intent, "type": "string"}
    properties["requested_analyses"] = {
        "const": list(case.required_tools),
        "type": "array",
        "items": {"type": "string"},
    }
    properties["language"] = {"const": case.language, "type": "string"}
    return schema


def _provider_transport(
    url: str,
    headers: dict[str, str],
    body: dict[str, object],
    timeout: float,
) -> dict[str, object]:
    request = urllib.request.Request(
        url,
        data=canonical_bytes(body),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise OSError("Provider transport failed") from exc
    if not isinstance(payload, dict):
        raise OSError("Provider returned a non-object response")
    return payload
