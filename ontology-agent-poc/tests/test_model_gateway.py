from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
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
from ontology_agent.models import OntologyPackage
from ontology_agent.studio.builder import _phase_request
from ontology_agent.studio.agentic_contracts import AgentTurnRequestV1
from ontology_agent.studio.construction import (
    CandidateDraftDiffV1,
    ConstructionCandidateV1,
)
from ontology_agent.studio.evidence import normalize_evidence
from ontology_agent.studio.reviewer import reviewer_request
from ontology_agent.studio.skill_packages import load_skill_package


client = TestClient(app)


def _agent_turn_request() -> AgentTurnRequestV1:
    raw: dict[str, object] = {
        "contract": "studio-agent-turn-request/v1",
        "engine_checksum": "1" * 64,
        "provider": "qwen",
        "requested_model": "qwen3.8-max",
        "messages": [
            {
                "role": "system",
                "content": "Use structured tools.",
                "tool_calls": [],
                "tool_call_id": None,
                "name": None,
            },
            {
                "role": "user",
                "content": "Inspect the frozen evidence.",
                "tool_calls": [],
                "tool_call_id": None,
                "name": None,
            },
        ],
        "tools": [
            {
                "name": "evidence.search",
                "description": "Search exact evidence.",
                "input_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                    "additionalProperties": False,
                },
                "mutating": False,
            }
        ],
        "remaining_output_tokens": 1000,
    }
    raw["request_digest"] = sha256_value(raw)
    return AgentTurnRequestV1.model_validate(raw)


def test_agent_turn_gateway_preserves_structured_tool_calls_and_serial_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _agent_turn_request()
    captured: dict[str, object] = {}

    def fake_transport(
        url: str, headers: dict[str, str], body: dict[str, object], timeout: float
    ) -> dict[str, object]:
        captured.update(url=url, headers=headers, body=body, timeout=timeout)
        return {
            "id": "provider-request.agent-turn-1",
            "model": "qwen3.8-max",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call-search-1",
                                "type": "function",
                                "function": {
                                    "name": "evidence.search",
                                    "arguments": json.dumps({"query": "service request"}),
                                },
                            }
                        ],
                    },
                }
            ],
            "usage": {"prompt_tokens": 120, "completion_tokens": 20},
        }

    monkeypatch.setattr(gateway_module, "_provider_transport", fake_transport)
    monkeypatch.setenv("ONTOLOGY_AGENTIC_BUILDER_ENABLED", "true")
    monkeypatch.setenv("ONTOLOGY_QWEN_API_KEY", "test-only-agent-secret")
    monkeypatch.setenv("ONTOLOGY_QWEN_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("ONTOLOGY_BUILDER_PROVIDER", "qwen")
    monkeypatch.setenv("ONTOLOGY_BUILDER_MODEL", "qwen3.8-max")

    response = client.post(
        "/model/v1/agent-turn", json=request.model_dump(mode="json")
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["tool_calls"] == [
        {
            "tool_call_id": "call-search-1",
            "name": "evidence.search",
            "arguments": {"query": "service request"},
        }
    ]
    assert payload["request_digest"] == request.request_digest
    provider_body = captured["body"]
    assert provider_body["parallel_tool_calls"] is False
    assert provider_body["tool_choice"] == "auto"
    assert "test-only-agent-secret" not in json.dumps(provider_body)


def test_agent_turn_gateway_retries_transport_without_replaying_a_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _agent_turn_request()
    calls = 0

    def flaky_transport(*_args: object, **_kwargs: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise OSError("temporary provider transport failure")
        return {
            "id": "provider-request.agent-turn-after-retry",
            "model": "qwen3.8-max",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call-search-after-retry",
                                "type": "function",
                                "function": {
                                    "name": "evidence.search",
                                    "arguments": json.dumps({"query": "cash trade"}),
                                },
                            }
                        ],
                    },
                }
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 4},
        }

    monkeypatch.setattr(gateway_module, "_provider_transport", flaky_transport)
    monkeypatch.setattr(gateway_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setenv("ONTOLOGY_AGENTIC_BUILDER_ENABLED", "true")
    monkeypatch.setenv("ONTOLOGY_QWEN_API_KEY", "test-only-agent-secret")
    monkeypatch.setenv("ONTOLOGY_QWEN_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("ONTOLOGY_BUILDER_PROVIDER", "qwen")
    monkeypatch.setenv("ONTOLOGY_BUILDER_MODEL", "qwen3.8-max")
    monkeypatch.setenv("ONTOLOGY_BUILDER_PROVIDER_RETRY_ATTEMPTS", "3")

    response = client.post(
        "/model/v1/agent-turn", json=request.model_dump(mode="json")
    )

    assert response.status_code == 200
    assert calls == 3
    assert response.json()["tool_calls"][0]["tool_call_id"] == (
        "call-search-after-retry"
    )


def test_agent_turn_gateway_rejects_provider_tool_registry_escape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _agent_turn_request()

    def fake_transport(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            "id": "provider-request.agent-turn-escape",
            "model": "qwen3.8-max",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call-escape",
                                "type": "function",
                                "function": {
                                    "name": "draft.publish",
                                    "arguments": "{}",
                                },
                            }
                        ],
                    },
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }

    monkeypatch.setattr(gateway_module, "_provider_transport", fake_transport)
    monkeypatch.setenv("ONTOLOGY_AGENTIC_BUILDER_ENABLED", "true")
    monkeypatch.setenv("ONTOLOGY_QWEN_API_KEY", "test-only-agent-secret")
    monkeypatch.setenv("ONTOLOGY_QWEN_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("ONTOLOGY_BUILDER_PROVIDER", "qwen")
    monkeypatch.setenv("ONTOLOGY_BUILDER_MODEL", "qwen3.8-max")

    response = client.post(
        "/model/v1/agent-turn", json=request.model_dump(mode="json")
    )
    assert response.status_code == 502
    assert response.json()["detail"] == "Agentic Builder provider turn failed"


def test_ontology_builder_gateway_executes_one_closed_versioned_skill_phase(
    monkeypatch: pytest.MonkeyPatch,
    package: OntologyPackage,
) -> None:
    text = "A service request is received and assigned a unique request identifier."
    intake = {
        "assets": [
            {
                "asset_id": "source.request",
                "kind": "requirement_transcription",
                "locator": "source-library:source-version.00000000000000000000000000000000",
                "source_version_id": "source-version.00000000000000000000000000000000",
                "checksum": hashlib.sha256(text.encode()).hexdigest(),
                "content_text": text,
            }
        ]
    }
    skill = load_skill_package("ontology-build", "1.0.0")
    bundle = normalize_evidence(intake, workspace_id="workspace.generic")
    request = _phase_request(
        run_id="construction-run." + "4" * 32,
        workspace_id="workspace.generic",
        phase="SEMANTIC",
        skill=skill,
        bundle=bundle,
        package=package,
        prior_operations=(),
    )
    captured: dict[str, object] = {}

    def fake_transport(
        url: str, headers: dict[str, str], body: dict[str, object], timeout: float
    ) -> dict[str, object]:
        captured.update(url=url, headers=headers, body=body, timeout=timeout)
        return {
            "id": "provider-request.builder-1",
            "model": "qwen3.8-max",
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "contract": "builder-phase-output/v1",
                                # These are control-plane fields. The provider may
                                # echo them incorrectly; the gateway must bind them
                                # to the exact request rather than trust the model.
                                "phase": "ANALYTICS",
                                "request_digest": "0" * 64,
                                "proposals": [],
                                "gaps": [],
                                "done": False,
                            }
                        )
                    }
                }
            ],
        }

    monkeypatch.setattr(gateway_module, "_provider_transport", fake_transport)
    monkeypatch.setenv("ONTOLOGY_BUILDER_LLM_ENABLED", "true")
    monkeypatch.setenv("ONTOLOGY_QWEN_API_KEY", "test-only-builder-secret")
    monkeypatch.setenv("ONTOLOGY_QWEN_BASE_URL", "https://provider.example/v1")

    response = client.post(
        "/model/v1/ontology-build", json=request.model_dump(mode="json")
    )

    assert response.status_code == 200
    assert response.json()["output"]["phase"] == request.phase
    assert response.json()["output"]["request_digest"] == request.request_digest
    assert response.json()["output"]["done"] is True
    provider_body = captured["body"]
    serialized = json.dumps(provider_body)
    assert "Ontology Build Skill" in serialized
    assert request.evidence_fragments[0].fragment_id in serialized
    assert "test-only-builder-secret" not in serialized
    assert provider_body["model"] == "qwen3.8-max"
    assert provider_body["enable_thinking"] is False
    assert f'"maxItems":{request.max_proposals}' in provider_body["messages"][1][
        "content"
    ]


def test_ontology_builder_gateway_canonicalizes_unary_formula_shorthand(
    monkeypatch: pytest.MonkeyPatch,
    package: OntologyPackage,
) -> None:
    text = "Each request has a unique request identifier."
    intake = {
        "assets": [
            {
                "asset_id": "source.request",
                "kind": "metric_transcription",
                "checksum": hashlib.sha256(text.encode()).hexdigest(),
                "content_text": text,
            }
        ]
    }
    skill = load_skill_package("ontology-build", "1.2.0")
    bundle = normalize_evidence(intake, workspace_id="workspace.generic")
    request = _phase_request(
        run_id="construction-run." + "b" * 32,
        workspace_id="workspace.generic",
        phase="ANALYTICS",
        skill=skill,
        bundle=bundle,
        package=package,
        prior_operations=(),
    )
    fragment_id = request.evidence_fragments[0].fragment_id

    def fake_transport(
        url: str, headers: dict[str, str], body: dict[str, object], timeout: float
    ) -> dict[str, object]:
        return {
            "id": "provider-request.builder-formula",
            "model": "qwen3.8-max",
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "proposals": [
                                    {
                                        "contract": "builder-proposal/v1",
                                        "proposal_id": "proposal.request_count",
                                        "operation": {
                                            "action": "UPSERT",
                                            "collection": "metrics",
                                            "object_id": "metric.request_count",
                                            "payload": {
                                                "id": "metric.request_count",
                                                "version": "1.0.0",
                                                "status": "proposed",
                                                "name": {"en": "Request count"},
                                                "definition": "Count of requests.",
                                                "owner": "Business Owner",
                                                "sources": ["source.request"],
                                                "decisions": [],
                                                "tags": [],
                                                "metric_type": "base",
                                                "base_entity": "entity.request",
                                                "result_grain": [],
                                                "value_type": "integer",
                                                "unit": "request",
                                                "aggregation_semantics": "additive",
                                                "formula": {
                                                    "op": "count_distinct",
                                                    "ref": "property.request.id",
                                                },
                                                "allowed_dimensions": [],
                                                "null_policy": "fail_validation",
                                                "zero_denominator_policy": "refuse",
                                            },
                                        },
                                        "evidence_fragment_ids": [fragment_id],
                                        "rationale": "The metric is explicitly defined.",
                                        "assumptions": [],
                                        "confidence": 0.9,
                                    }
                                ],
                                "gaps": [],
                            }
                        )
                    }
                }
            ],
        }

    monkeypatch.setattr(gateway_module, "_provider_transport", fake_transport)
    monkeypatch.setenv("ONTOLOGY_BUILDER_LLM_ENABLED", "true")
    monkeypatch.setenv("ONTOLOGY_QWEN_API_KEY", "test-only-builder-secret")
    monkeypatch.setenv("ONTOLOGY_QWEN_BASE_URL", "https://provider.example/v1")

    response = client.post(
        "/model/v1/ontology-build", json=request.model_dump(mode="json")
    )

    assert response.status_code == 200
    formula = response.json()["output"]["proposals"][0]["operation"]["payload"][
        "formula"
    ]
    assert formula["op"] == "count_distinct"
    assert formula["args"] == [
        {"op": "field_ref", "ref": "property.request.id"}
    ]


def test_builder_formula_canonicalizer_does_not_repair_wrong_arity() -> None:
    raw = {
        "proposals": [
            {
                "operation": {
                    "collection": "metrics",
                    "payload": {
                        "formula": {
                            "op": "sum",
                            "args": [
                                {"op": "field_ref", "ref": "property.a"},
                                {"op": "field_ref", "ref": "property.b"},
                            ],
                        }
                    },
                }
            }
        ]
    }

    normalized = gateway_module._canonicalize_builder_formulae(raw)

    assert len(
        normalized["proposals"][0]["operation"]["payload"]["formula"]["args"]
    ) == 2


def test_builder_formula_canonicalizer_unwraps_empty_reference_envelope() -> None:
    normalized = gateway_module._canonicalize_formula_node(
        {
            "op": "field_ref",
            "args": [
                {
                    "op": "sum",
                    "ref": "property.trade.amount",
                }
            ],
        }
    )

    assert normalized == {
        "op": "sum",
        "args": [
            {"op": "field_ref", "ref": "property.trade.amount"}
        ],
    }


def test_builder_formula_canonicalizer_unwraps_one_operand_add_envelope() -> None:
    normalized = gateway_module._canonicalize_formula_node(
        {
            "op": "add",
            "args": [
                {
                    "op": "multiply",
                    "args": [
                        {"op": "field_ref", "ref": "property.trade.amount"},
                        {"op": "literal", "value": 100},
                    ],
                }
            ],
        }
    )

    assert normalized == {
        "op": "multiply",
        "args": [
            {"op": "field_ref", "ref": "property.trade.amount"},
            {"op": "literal", "value": 100},
        ],
    }


def test_builder_formula_canonicalizer_keeps_ambiguous_one_operand_subtract() -> None:
    normalized = gateway_module._canonicalize_formula_node(
        {
            "op": "subtract",
            "args": [{"op": "field_ref", "ref": "property.trade.amount"}],
        }
    )

    assert normalized == {
        "op": "subtract",
        "args": [{"op": "field_ref", "ref": "property.trade.amount"}],
    }


def test_builder_formula_canonicalizer_unwraps_valueless_literal_envelope() -> None:
    normalized = gateway_module._canonicalize_formula_node(
        {
            "op": "literal",
            "args": [
                {"op": "field_ref", "ref": "property.trade.latency_ms"}
            ],
        }
    )

    assert normalized == {
        "op": "field_ref",
        "ref": "property.trade.latency_ms",
    }


def test_ontology_reviewer_gateway_uses_a_fresh_findings_only_context(
    monkeypatch: pytest.MonkeyPatch,
    package: OntologyPackage,
) -> None:
    text = "A service request receives a unique identifier."
    intake = {
        "assets": [
            {
                "asset_id": "source.request",
                "kind": "requirement_transcription",
                "locator": "source-library:source-version.00000000000000000000000000000000",
                "source_version_id": "source-version.00000000000000000000000000000000",
                "checksum": hashlib.sha256(text.encode()).hexdigest(),
                "content_text": text,
            }
        ]
    }
    skill = load_skill_package("ontology-review", "1.0.0")
    bundle = normalize_evidence(intake, workspace_id="workspace.generic")
    candidate = ConstructionCandidateV1(
        candidate_id="candidate." + "8" * 32,
        occurrence_key="7" * 64,
        revision_digest="6" * 64,
        candidate_type="GAP",
        label="Missing contract",
        definition="A required contract is missing.",
        support_class="MISSING",
        risk_class="HIGH",
        compile_eligible=False,
        proposal={"rationale": "PRIVATE BUILDER RATIONALE"},
        draft_diff=CandidateDraftDiffV1(change_type="NON_COMPILABLE"),
    )
    request = reviewer_request(
        run_id="construction-run." + "9" * 32,
        workspace_id="workspace.generic",
        base_draft_checksum="5" * 64,
        skill=skill,
        package=package,
        candidates=(candidate,),
        evidence_bundle=bundle,
        deterministic_findings=(),
    )
    captured: dict[str, object] = {}

    def fake_transport(
        url: str, headers: dict[str, str], body: dict[str, object], timeout: float
    ) -> dict[str, object]:
        captured.update(url=url, headers=headers, body=body, timeout=timeout)
        return {
            "id": "provider-request.reviewer-1",
            "model": "qwen3.8-max",
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "contract": "reviewer-output/v1",
                                "request_digest": request.request_digest,
                                "findings": [],
                                "done": True,
                            }
                        )
                    }
                }
            ],
        }

    monkeypatch.setattr(gateway_module, "_provider_transport", fake_transport)
    monkeypatch.setenv("ONTOLOGY_REVIEWER_LLM_ENABLED", "true")
    monkeypatch.setenv("ONTOLOGY_QWEN_API_KEY", "test-only-reviewer-secret")
    monkeypatch.setenv("ONTOLOGY_QWEN_BASE_URL", "https://provider.example/v1")

    response = client.post(
        "/model/v1/ontology-review", json=request.model_dump(mode="json")
    )

    assert response.status_code == 200
    provider_body = captured["body"]
    serialized = json.dumps(provider_body)
    assert "Ontology Review Skill" in serialized
    assert "PRIVATE BUILDER RATIONALE" not in serialized
    assert "test-only-reviewer-secret" not in serialized
    assert provider_body["enable_thinking"] is False


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
                                "intent": case["expected_intent"],
                                "tool_ids": case["required_tools"],
                                "language": case["language"],
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
        "intent": case["expected_intent"],
        "tool_ids": case["required_tools"],
        "language": case["language"],
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
