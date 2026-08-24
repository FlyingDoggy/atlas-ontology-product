from __future__ import annotations

import json
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ontology_agent.io import sha256_value
from ontology_agent.models import OntologyPackage
from ontology_agent.studio.agentic_contracts import (
    AgentEngineContractV2,
    AgentMessageV1,
    AgentTokenUsageV1,
    AgentToolCallV1,
    AgentTurnRequestV1,
    AgentTurnResultV1,
    BuildObjectiveV1,
    RunAuthorityContextV1,
)
from ontology_agent.studio.agentic_evidence import ExactEvidenceWorkspace
from ontology_agent.studio.agentic_runtime import (
    AgentRuntimeError,
    HttpModelToolGateway,
    StudioAgentRuntime,
)
from ontology_agent.studio.agentic_store import InMemoryAgentCheckpointStore
from ontology_agent.studio.agentic_tools import StudioToolHarness, tool_registry_digest
from ontology_agent.studio.source_library import FileSourceLibraryStore


NOW = datetime(2026, 8, 23, tzinfo=timezone.utc)


def _turn_request() -> AgentTurnRequestV1:
    raw: dict[str, object] = {
        "contract": "studio-agent-turn-request/v1",
        "engine_checksum": "a" * 64,
        "provider": "test-provider",
        "requested_model": "test-model",
        "messages": [
            {
                "role": "system",
                "content": "Build a governed candidate.",
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
                "name": "candidate.validate",
                "description": "Validate the candidate.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                "mutating": False,
            }
        ],
        "remaining_output_tokens": 1000,
    }
    raw["request_digest"] = sha256_value(raw)
    return AgentTurnRequestV1.model_validate(raw)


class _FakeHttpResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> _FakeHttpResponse:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def test_http_gateway_retries_the_exact_request_after_transient_502(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payloads: list[bytes | None] = []

    def urlopen(request: object, *, timeout: float) -> _FakeHttpResponse:
        del timeout
        payload = getattr(request, "data", None)
        payloads.append(payload)
        if len(payloads) == 1:
            raise urllib.error.HTTPError(
                "http://model-gateway/model/v1/agent-turn",
                502,
                "Bad Gateway",
                hdrs=None,
                fp=None,
            )
        parsed = AgentTurnRequestV1.model_validate_json(payload)
        result = _result(
            parsed,
            call_id="call-after-retry",
            name="candidate.validate",
            arguments={},
        )
        return _FakeHttpResponse(result.model_dump_json().encode("utf-8"))

    monkeypatch.setattr(
        "ontology_agent.studio.agentic_runtime.urllib.request.urlopen", urlopen
    )
    request = _turn_request()
    result = HttpModelToolGateway(
        "http://model-gateway",
        max_attempts=2,
        retry_backoff_seconds=0,
    ).next(request)

    assert result.request_digest == request.request_digest
    assert len(payloads) == 2
    assert payloads[0] == payloads[1]


def test_http_gateway_does_not_retry_non_transient_http_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def urlopen(request: object, *, timeout: float) -> _FakeHttpResponse:
        del request, timeout
        nonlocal calls
        calls += 1
        raise urllib.error.HTTPError(
            "http://model-gateway/model/v1/agent-turn",
            400,
            "Bad Request",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(
        "ontology_agent.studio.agentic_runtime.urllib.request.urlopen", urlopen
    )

    with pytest.raises(AgentRuntimeError, match="unavailable"):
        HttpModelToolGateway(
            "http://model-gateway",
            max_attempts=3,
            retry_backoff_seconds=0,
        ).next(_turn_request())

    assert calls == 1


def _result(
    request: AgentTurnRequestV1,
    *,
    call_id: str,
    name: str,
    arguments: dict[str, object],
) -> AgentTurnResultV1:
    raw: dict[str, object] = {
        "contract": "studio-agent-turn-result/v1",
        "requested_model": request.requested_model,
        "response_model": request.requested_model,
        "provider_request_id": "provider." + call_id,
        "assistant_content": None,
        "tool_calls": [
            {
                "tool_call_id": call_id,
                "name": name,
                "arguments": arguments,
            }
        ],
        "finish_reason": "tool_calls",
        "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        "request_digest": request.request_digest,
    }
    raw["result_digest"] = sha256_value(raw)
    return AgentTurnResultV1.model_validate(raw)


class ScriptedGateway:
    def __init__(self) -> None:
        self.calls = 0

    @staticmethod
    def _last_tool(request: AgentTurnRequestV1) -> dict[str, object]:
        return json.loads(request.messages[-1].content or "{}")

    def next(self, request: AgentTurnRequestV1) -> AgentTurnResultV1:
        self.calls += 1
        if self.calls == 1:
            return _result(
                request,
                call_id="call-search",
                name="evidence.search",
                arguments={"query": "request identifier"},
            )
        if self.calls == 2:
            tool_result = self._last_tool(request)
            assert tool_result["_runtime_budget"] == {
                "authority": "NON_AUTHORITATIVE_EXECUTION_SIGNAL",
                "model_calls_remaining": 9,
                "tool_calls_remaining": 19,
                "state": "LOW",
                "guidance": (
                    "Prioritize closing frozen obligations, deterministic "
                    "validation, and run.request_completion."
                ),
            }
            hit = tool_result["hits"][0]
            return _result(
                request,
                call_id="call-read",
                name="evidence.read",
                arguments={
                    "source_version_id": hit["source_version_id"],
                    "start_line": 1,
                    "end_line": 2,
                },
            )
        if self.calls == 3:
            tool_result = self._last_tool(request)
            assert tool_result["_runtime_budget"]["state"] == "CRITICAL"
            assert tool_result["_runtime_budget"]["model_calls_remaining"] == 8
            receipt_id = tool_result["evidence_receipt"]["receipt_id"]
            return _result(
                request,
                call_id="call-entity",
                name="candidate.upsert",
                arguments={
                    "expected_candidate_revision": 0,
                    "operation": {
                        "action": "UPSERT",
                        "collection": "entities",
                        "object_id": "entity.service_request",
                        "payload": {
                            "id": "entity.service_request",
                            "version": "1.0.0",
                            "status": "proposed",
                            "name": {"en": "Service Request"},
                            "definition": "A request submitted for service.",
                            "owner": "actor.domain_owner",
                            "sources": ["source.requirements"],
                            "primary_key": "property.service_request.id",
                            "grain": "one service request",
                            "lifecycle": "submitted to closed",
                        },
                    },
                    "claims": [
                        {
                            "path": "definition",
                            "support": "EXACT",
                            "evidence_receipt_ids": [receipt_id],
                        }
                    ],
                    "obligation_ids": ["obligation.service-request"],
                },
            )
        if self.calls == 4:
            return _result(
                request,
                call_id="call-complete-too-soon",
                name="run.request_completion",
                arguments={"reason": "The requirement is modeled."},
            )
        if self.calls == 5:
            # Recover the exact evidence receipt from the earlier durable tool result.
            receipt_id = None
            for message in request.messages:
                if message.role != "tool" or message.name != "evidence.read":
                    continue
                receipt_id = json.loads(message.content or "{}")["evidence_receipt"][
                    "receipt_id"
                ]
            assert receipt_id is not None
            return _result(
                request,
                call_id="call-property",
                name="candidate.upsert",
                arguments={
                    "expected_candidate_revision": 1,
                    "operation": {
                        "action": "UPSERT",
                        "collection": "properties",
                        "object_id": "property.service_request.id",
                        "payload": {
                            "id": "property.service_request.id",
                            "version": "1.0.0",
                            "status": "proposed",
                            "name": {"en": "Service Request ID"},
                            "definition": "Unique identifier for the service request.",
                            "owner": "actor.domain_owner",
                            "sources": ["source.requirements"],
                            "entity": "entity.service_request",
                            "data_type": "string",
                            "required": True,
                        },
                    },
                    "claims": [
                        {
                            "path": "definition",
                            "support": "EXACT",
                            "evidence_receipt_ids": [receipt_id],
                        }
                    ],
                    "obligation_ids": ["obligation.service-request"],
                },
            )
        return _result(
            request,
            call_id="call-complete",
            name="run.request_completion",
            arguments={"reason": "The closure failure was repaired."},
        )


class FaultOnceHarness(StudioToolHarness):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.failed = False

    def execute(self, call: AgentToolCallV1) -> dict[str, object]:
        if not self.failed:
            self.failed = True
            raise RuntimeError("simulated worker crash")
        return super().execute(call)


class CompactingGateway:
    def __init__(self) -> None:
        self.calls = 0
        self.requests: list[AgentTurnRequestV1] = []

    def next(self, request: AgentTurnRequestV1) -> AgentTurnResultV1:
        self.calls += 1
        self.requests.append(request)
        if self.calls == 1:
            return _result(
                request,
                call_id="call-context-schema",
                name="schema.get_collection",
                arguments={"collection": "entities"},
            )
        if self.calls == 2:
            return _result(
                request,
                call_id="call-context-memory",
                name="run.update_working_memory",
                arguments={
                    "notes": (
                        "I inventoried the frozen source set. The fixture requirement "
                        "cannot be modeled from supported evidence; next record a "
                        "governed unsupported disposition."
                    )
                },
            )
        if self.calls == 3:
            return _result(
                request,
                call_id="call-context-gap",
                name="gap.record",
                arguments={
                    "expected_candidate_revision": 0,
                    "gap_id": "gap.service-request.unsupported",
                    "obligation_ids": ["obligation.service-request"],
                    "description": "The fixture deliberately exercises a governed gap.",
                    "unsupported": True,
                },
            )
        if self.calls == 4:
            return _result(
                request,
                call_id="call-context-memory-after-gap",
                name="run.update_working_memory",
                arguments={
                    "notes": (
                        "The frozen obligation now has a governed unsupported "
                        "disposition at Candidate revision 1. Next request "
                        "deterministic completion."
                    )
                },
            )
        return _result(
            request,
            call_id="call-context-complete",
            name="run.request_completion",
            arguments={"reason": "The frozen obligation has a governed disposition."},
        )


class FailOnThirdToolHarness(StudioToolHarness):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.executions = 0
        self.failed = False

    def execute(self, call: AgentToolCallV1) -> dict[str, object]:
        self.executions += 1
        if self.executions == 3 and not self.failed:
            self.failed = True
            raise RuntimeError("simulated crash after compacted model turn")
        return super().execute(call)


def _fixture(
    tmp_path: Path, package: OntologyPackage
) -> tuple[
    AgentEngineContractV2,
    BuildObjectiveV1,
    RunAuthorityContextV1,
    InMemoryAgentCheckpointStore,
    ExactEvidenceWorkspace,
]:
    sources = FileSourceLibraryStore(tmp_path / "sources")
    version = sources.register(
        workspace_id="workspace.example",
        source_id="source.requirements",
        kind="requirement_transcription",
        title="Service request requirement",
        original_name="requirements.md",
        media_type="text/markdown",
        body=(
            b"A service request is submitted by a customer.\n"
            b"Each service request has a unique request identifier.\n"
        ),
    )
    objective_raw: dict[str, object] = {
        "contract": "studio-build-objective/v1",
        "objective_id": "build-objective." + "1" * 32,
        "solution_id": "ontology.example",
        "workspace_id": "workspace.example",
        "selected_source_version_ids": [version.source_version_id],
        "source_set_digest": sha256_value([version.subject_checksum]),
        "capabilities": ["SEMANTIC"],
        "output_language": "en",
        "obligations": [
            {
                "obligation_id": "obligation.service-request",
                "kind": "REQUIREMENT",
                "title": "Represent the service request and identifier",
                "source_version_ids": [version.source_version_id],
                "source_locator": "lines:1-2",
                "required": True,
            }
        ],
        "required_validators": ["candidate.materialize", "reference.closure"],
    }
    objective_raw["objective_checksum"] = sha256_value(objective_raw)
    objective = BuildObjectiveV1.model_validate(objective_raw)
    context = RunAuthorityContextV1(
        job_id="construction-job." + "2" * 32,
        run_id="construction-run." + "3" * 32,
        attempt_id="construction-attempt." + "4" * 32,
        lease_epoch=1,
        lease_owner="worker-1",
        workspace_id=objective.workspace_id,
        solution_id=objective.solution_id,
        source_set_digest=objective.source_set_digest,
        selected_source_version_ids=objective.selected_source_version_ids,
        principal_id="service.builder",
        tool_registry_digest=tool_registry_digest(),
        tool_policy_digest="5" * 64,
        objective_checksum=objective.objective_checksum,
        candidate_revision=0,
        step_sequence=0,
        remaining_model_calls=20,
        remaining_tool_calls=100,
    )
    engine_raw: dict[str, object] = {
        "contract": "studio-agent-engine/v2",
        "engine_id": "studio.agentic-builder",
        "engine_version": "2.0.0",
        "runtime_digest": "6" * 64,
        "provider": "qwen",
        "requested_model": "qwen3.8-max",
        "model_config_digest": "7" * 64,
        "skill_id": "ontology-build",
        "skill_version": "2.0.0",
        "skill_checksum": "8" * 64,
        "tool_registry_digest": context.tool_registry_digest,
        "tool_policy_digest": context.tool_policy_digest,
        "parser_contract_digest": "9" * 64,
        "source_set_digest": context.source_set_digest,
        "max_model_calls": 10,
        "max_tool_calls": 20,
        "max_input_tokens": 10000,
        "max_output_tokens": 10000,
        "output_language": "en",
        "objective_checksum": objective.objective_checksum,
    }
    engine_raw["engine_checksum"] = sha256_value(engine_raw)
    engine = AgentEngineContractV2.model_validate(engine_raw)
    checkpoints = InMemoryAgentCheckpointStore(clock=lambda: NOW)
    checkpoints.start_attempt(context, objective, package)
    evidence = ExactEvidenceWorkspace(
        context=context,
        versions=(version,),
        store=sources,
        clock=lambda: NOW,
    )
    return engine, objective, context, checkpoints, evidence


def test_production_tracer_recovers_then_searches_reads_repairs_and_seals(
    tmp_path: Path, package: OntologyPackage
) -> None:
    engine, objective, context, checkpoints, evidence = _fixture(tmp_path, package)
    gateway = ScriptedGateway()
    harness = FaultOnceHarness(
        store=checkpoints, evidence=evidence, context=context
    )
    runtime = StudioAgentRuntime(gateway=gateway, checkpoint_store=checkpoints)
    with pytest.raises(RuntimeError, match="simulated worker crash"):
        runtime.run(
            engine=engine,
            objective=objective,
            context=context,
            skill_instructions="Build an evidence-grounded ontology candidate.",
            harness=harness,
        )
    assert len(checkpoints.view(context).model_turns) == 1
    assert gateway.calls == 1

    trace = runtime.run(
        engine=engine,
        objective=objective,
        context=context,
        skill_instructions="Build an evidence-grounded ontology candidate.",
        harness=harness,
    )
    assert trace.completion.outcome == "REVIEW_READY"
    assert trace.completion.bundle.candidate_revision == 2
    assert trace.model_calls == 6
    assert trace.tool_calls == 6
    assert gateway.calls == 6  # the journaled first decision was not called again
    assert len(checkpoints.view(context).evidence_receipts) == 1


def test_execution_fence_stops_before_any_provider_call(
    tmp_path: Path, package: OntologyPackage
) -> None:
    engine, objective, context, checkpoints, evidence = _fixture(tmp_path, package)
    gateway = ScriptedGateway()
    harness = StudioToolHarness(
        store=checkpoints, evidence=evidence, context=context
    )

    with pytest.raises(RuntimeError, match="cancelled"):
        StudioAgentRuntime(gateway=gateway, checkpoint_store=checkpoints).run(
            engine=engine,
            objective=objective,
            context=context,
            skill_instructions="Build an evidence-grounded ontology candidate.",
            harness=harness,
            execution_fence=lambda: (_ for _ in ()).throw(
                RuntimeError("cancelled")
            ),
        )

    assert gateway.calls == 0
    assert checkpoints.view(context).model_turns == ()


def test_execution_fence_discards_inflight_provider_result_after_cancel(
    tmp_path: Path, package: OntologyPackage
) -> None:
    engine, objective, context, checkpoints, evidence = _fixture(tmp_path, package)
    gateway = ScriptedGateway()
    harness = StudioToolHarness(
        store=checkpoints, evidence=evidence, context=context
    )
    fence_calls = 0

    def fence() -> None:
        nonlocal fence_calls
        fence_calls += 1
        if fence_calls == 2:
            raise RuntimeError("cancelled after provider return")

    with pytest.raises(RuntimeError, match="cancelled after provider return"):
        StudioAgentRuntime(gateway=gateway, checkpoint_store=checkpoints).run(
            engine=engine,
            objective=objective,
            context=context,
            skill_instructions="Build an evidence-grounded ontology candidate.",
            harness=harness,
            execution_fence=fence,
        )

    assert gateway.calls == 1
    assert checkpoints.view(context).model_turns == ()
    assert checkpoints.view(context).evidence_receipts == ()


def test_context_checkpoint_compacts_provider_history_and_recovers_exactly(
    tmp_path: Path, package: OntologyPackage
) -> None:
    engine, objective, context, checkpoints, evidence = _fixture(tmp_path, package)
    gateway = CompactingGateway()
    harness = FailOnThirdToolHarness(
        store=checkpoints, evidence=evidence, context=context
    )
    runtime = StudioAgentRuntime(
        gateway=gateway,
        checkpoint_store=checkpoints,
        context_max_uncheckpointed_model_turns=1,
    )

    with pytest.raises(
        RuntimeError, match="simulated crash after compacted model turn"
    ):
        runtime.run(
            engine=engine,
            objective=objective,
            context=context,
            skill_instructions="Build an evidence-grounded ontology candidate.",
            harness=harness,
        )

    journal = checkpoints.view(context).model_turns
    assert len(journal) == 3
    assert len(journal[1].request.tools) == 1
    assert journal[1].request.tools[0].name == "run.update_working_memory"
    assert "context checkpoint is now required" in (
        journal[1].request.messages[-1].content or ""
    )
    memory_checkpoint = journal[2].request.messages[-1].content or ""
    assert memory_checkpoint.startswith("STUDIO_CONTEXT_CHECKPOINT\n")
    assert '"revision":0' in memory_checkpoint
    assert "A service request is submitted by a customer" not in memory_checkpoint
    assert "NON_AUTHORITATIVE_AGENT_MEMORY" in memory_checkpoint
    assert "next record a governed unsupported disposition" in memory_checkpoint
    assert '"schema_collections":["entities"]' in memory_checkpoint
    assert '"schema_contracts"' not in memory_checkpoint
    assert '"candidate_payload_schema"' not in memory_checkpoint
    assert len(memory_checkpoint.encode("utf-8")) < 32_000

    trace = runtime.run(
        engine=engine,
        objective=objective,
        context=context,
        skill_instructions="Build an evidence-grounded ontology candidate.",
        harness=harness,
    )

    assert trace.completion.outcome == "BLOCKED"
    assert trace.completion.bundle.candidate_revision == 1
    assert gateway.calls == 5
    final_journal = checkpoints.view(context).model_turns
    assert len(final_journal) == 5
    final_checkpoint = final_journal[-1].request.messages[-1].content or ""
    assert final_checkpoint.startswith("STUDIO_CONTEXT_CHECKPOINT\n")
    assert '"revision":1' in final_checkpoint


def test_default_context_window_allows_a_complete_multi_object_repair_batch(
    tmp_path: Path, package: OntologyPackage
) -> None:
    engine, objective, context, checkpoints, _ = _fixture(tmp_path, package)
    runtime = StudioAgentRuntime(
        gateway=CompactingGateway(), checkpoint_store=checkpoints
    )
    messages = runtime._initial_messages(
        skill_instructions="Build an evidence-grounded ontology candidate.",
        objective=objective,
    )
    for index in range(8):
        messages.extend(
                (
                    AgentMessageV1(role="assistant", content=f"inspect-{index}"),
                    AgentMessageV1(
                        role="tool",
                        content=f"result-{index}",
                        name="candidate.get",
                        tool_call_id=f"call-{index}",
                    ),
                )
        )

    assert runtime.context_max_uncheckpointed_model_turns == 24
    assert runtime._should_compact(messages) is False


def test_large_engine_budget_reserves_proportional_closeout_window(
    tmp_path: Path, package: OntologyPackage
) -> None:
    engine, _, _, checkpoints, _ = _fixture(tmp_path, package)
    large_engine = engine.model_copy(
        update={"max_model_calls": 480, "max_tool_calls": 960}
    )

    low = StudioAgentRuntime._with_runtime_budget(
        {}, engine=large_engine, model_calls=360, tool_calls=360
    )
    critical = StudioAgentRuntime._with_runtime_budget(
        {}, engine=large_engine, model_calls=432, tool_calls=432
    )

    assert low["_runtime_budget"]["state"] == "LOW"
    assert low["_runtime_budget"]["model_calls_remaining"] == 120
    assert critical["_runtime_budget"]["state"] == "CRITICAL"
    assert critical["_runtime_budget"]["model_calls_remaining"] == 48


def test_continuation_bootstrap_tells_model_to_validate_and_repair(
    tmp_path: Path, package: OntologyPackage
) -> None:
    _, objective, _, checkpoints, _ = _fixture(tmp_path, package)
    messages = StudioAgentRuntime(
        gateway=CompactingGateway(), checkpoint_store=checkpoints
    )._initial_messages(
        skill_instructions="Build an evidence-grounded ontology candidate.",
        objective=objective,
        resume_from_attempt_id="construction-attempt." + "a" * 32,
        initial_candidate_revision=25,
        initial_candidate_count=155,
        continuation_handoff_notes=(
            "ENTITY_KEY_CLOSURE was repaired; continue with SQL and metric references."
        ),
    )

    instruction = messages[-1].content or ""
    assert "repair continuation, not a new build" in instruction
    assert "seeded 155 durable Candidates at revision 25" in instruction
    assert "First call candidate.validate" in instruction
    assert "Do not rebuild the ontology from zero" in instruction
    assert "NON-AUTHORITATIVE working memory" in instruction
    assert "ENTITY_KEY_CLOSURE was repaired" in instruction
    assert "Re-run candidate.validate" in instruction
