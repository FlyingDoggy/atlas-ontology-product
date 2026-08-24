from __future__ import annotations

import json
from pathlib import Path

from ontology_agent.io import sha256_value
from ontology_agent.models import OntologyPackage
from ontology_agent.release import StudioReleases
from ontology_agent.studio.agentic_construction import (
    AgenticConstructionRuntime,
    freeze_agentic_build_plan,
)
from ontology_agent.studio.agentic_contracts import (
    AgentTurnRequestV1,
    AgentTurnResultV1,
)
from ontology_agent.studio.agentic_store import InMemoryAgentCheckpointStore
from ontology_agent.studio.construction import (
    FileConstructionRunStore,
    StudioConstructionService,
)
from ontology_agent.studio.construction_jobs import InMemoryConstructionJobStore
from ontology_agent.studio.construction_worker import ConstructionWorker
from ontology_agent.studio.skill_packages import LoadedSkillPackageV2, load_skill_package
from ontology_agent.studio.source_library import FileSourceLibraryStore
from ontology_agent.studio.source_projection import (
    RequirementProjectionV1,
    StudioAuthoringProjectionV1,
)
from ontology_agent.studio.workspace import DraftWorkspaceService


def _tool_result(
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
        "usage": {"input_tokens": 100, "output_tokens": 30, "total_tokens": 130},
        "request_digest": request.request_digest,
    }
    raw["result_digest"] = sha256_value(raw)
    return AgentTurnResultV1.model_validate(raw)


class EndToEndBuilderGateway:
    """A deterministic provider double; the production runtime remains fully agentic."""

    def __init__(
        self,
        *,
        source_version_id: str,
        source_reference_id: str,
        obligation_ids: tuple[str, ...],
    ) -> None:
        self.source_version_id = source_version_id
        self.source_reference_id = source_reference_id
        self.obligation_ids = obligation_ids
        self.calls = 0
        self.steps = 0

    @staticmethod
    def _receipt_id(request: AgentTurnRequestV1) -> str:
        for message in reversed(request.messages):
            if message.role != "tool" or not message.content:
                continue
            payload = json.loads(message.content)
            receipt = payload.get("evidence_receipt")
            if isinstance(receipt, dict) and receipt.get("receipt_id"):
                return str(receipt["receipt_id"])
        raise AssertionError("exact evidence receipt is unavailable")

    def next(self, request: AgentTurnRequestV1) -> AgentTurnResultV1:
        self.calls += 1
        if len(request.tools) == 1 and request.tools[0].name == "run.update_working_memory":
            return _tool_result(
                request,
                call_id="call-context-memory",
                name="run.update_working_memory",
                arguments={
                    "notes": (
                        "The frozen evidence was read and the entity/property candidate "
                        "pair has been authored. Next validate and request completion."
                    )
                },
            )
        self.steps += 1
        if self.steps == 1:
            return _tool_result(
                request,
                call_id="call-list-sources",
                name="evidence.list_sources",
                arguments={},
            )
        if self.steps == 2:
            return _tool_result(
                request,
                call_id="call-search",
                name="evidence.search",
                arguments={"query": "service request identifier"},
            )
        if self.steps == 3:
            return _tool_result(
                request,
                call_id="call-read",
                name="evidence.read",
                arguments={
                    "source_version_id": self.source_version_id,
                    "start_line": 1,
                    "end_line": 2,
                },
            )
        if self.steps == 4:
            return _tool_result(
                request,
                call_id="call-schema-entity",
                name="schema.get_collection",
                arguments={"collection": "entities"},
            )
        if self.steps == 5:
            receipt_id = self._receipt_id(request)
            return _tool_result(
                request,
                call_id="call-upsert-entity",
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
                            "sources": [self.source_reference_id],
                            "decisions": [],
                            "tags": [],
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
                    "obligation_ids": list(self.obligation_ids),
                },
            )
        if self.steps == 6:
            return _tool_result(
                request,
                call_id="call-schema-property",
                name="schema.get_collection",
                arguments={"collection": "properties"},
            )
        if self.steps == 7:
            receipt_id = self._receipt_id(request)
            return _tool_result(
                request,
                call_id="call-upsert-property",
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
                            "sources": [self.source_reference_id],
                            "decisions": [],
                            "tags": [],
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
                    "obligation_ids": list(self.obligation_ids),
                },
            )
        if self.steps == 8:
            return _tool_result(
                request,
                call_id="call-validate",
                name="candidate.validate",
                arguments={},
            )
        return _tool_result(
            request,
            call_id="call-complete",
            name="run.request_completion",
            arguments={"reason": "All frozen obligations have typed candidates."},
        )


def test_worker_runs_frozen_agentic_build_to_review_ready_run(
    tmp_path: Path,
    scenario_dir: Path,
    package: OntologyPackage,
) -> None:
    workspace = DraftWorkspaceService(
        tmp_path / "workspace",
        scenario_dir,
        StudioReleases(tmp_path / "releases"),
    )
    source_store = FileSourceLibraryStore(tmp_path / "sources")
    source = source_store.register(
        workspace_id=workspace.get().workspace_id,
        source_id="asset.service-requirements",
        kind="requirement_transcription",
        title="Service request requirements",
        original_name="requirements.md",
        media_type="text/markdown",
        body=(
            b"A service request is submitted for service.\n"
            b"Each service request has a unique service request identifier.\n"
        ),
    )
    authoring = StudioAuthoringProjectionV1(
        requirements=(
            RequirementProjectionV1(
                requirement_key="O-01",
                question="Represent the service request and its identifier",
                minimum_output="A governed object and identifier",
                presentation="ontology",
                status="SOURCE_SUPPORTED",
                support_class="DIRECT_EXACT",
                source_anchor=None,
            ),
        ),
        metric_candidates=(),
        source_mode="EXACT_TRANSCRIPTION",
    )
    skill = load_skill_package("ontology-build", "2.0.0")
    assert isinstance(skill, LoadedSkillPackageV2)
    plan = freeze_agentic_build_plan(
        solution_id=workspace.get().package_id,
        workspace_id=workspace.get().workspace_id,
        versions=(source,),
        authoring=authoring,
        output_language="en",
        skill=skill,
        provider="qwen",
        requested_model="qwen3.8-max",
    )
    gateway = EndToEndBuilderGateway(
        source_version_id=source.source_version_id,
        source_reference_id=source.source_id,
        obligation_ids=tuple(item.obligation_id for item in plan.objective.obligations),
    )
    checkpoints = InMemoryAgentCheckpointStore()
    service = StudioConstructionService(
        store=FileConstructionRunStore(tmp_path / "construction"),
        workspace=workspace,
        package=package,
        intake={"assets": ()},
        authoring=authoring,
        engine=None,
        selected_source_version_ids=(source.source_version_id,),
        workspace_id=workspace.get().workspace_id,
        agentic=AgenticConstructionRuntime(
            plan=plan,
            checkpoint_store=checkpoints,
            source_store=source_store,
            gateway=gateway,
        ),
    )
    jobs = InMemoryConstructionJobStore()
    queued = jobs.enqueue(service.job_input(expected_revision=workspace.get().revision))
    worker = ConstructionWorker(
        jobs=jobs,
        service_factory=lambda workspace_id, selected_source_version_ids: service,
        worker_id="worker.agentic-test",
    )

    completed = worker.process_one()

    assert completed is not None
    assert completed.status == "SUCCEEDED"
    assert completed.result_run_id == queued.run_id
    # A complete small build fits within the default 24-turn window and must
    # not spend an extra model turn checkpointing before its governed write.
    assert gateway.calls == 9
    run = service.get(queued.run_id)
    assert run.status == "NEEDS_REVIEW"
    assert run.engine_status == "COMPLETED"
    assert {item.candidate_type for item in run.candidates} == {
        "SOURCE",
        "OBJECT",
        "PROPERTY",
    }
    normalized_source = next(
        item for item in run.candidates if item.candidate_type == "SOURCE"
    )
    assert normalized_source.proposal["contract"] == "agentic-source-normalization/v1"
    assert normalized_source.proposed_operation is not None
    assert normalized_source.proposed_operation.object_id == source.source_id
    assert all(item.review_status == "UNREVIEWED" for item in run.candidates)
    assert {
        item.candidate_type: item.support_class for item in run.candidates
    } == {
        "SOURCE": "DERIVED_DETERMINISTIC",
        "OBJECT": "DIRECT_EXACT",
        "PROPERTY": "DIRECT_EXACT",
    }
    assert all(
        item.proposal.get("contract") == "agentic-candidate-projection/v1"
        for item in run.candidates
        if item.candidate_type != "SOURCE"
    )
    attempt = checkpoints.view(
        checkpoints._attempts[completed.attempt_id].authority  # type: ignore[attr-defined]
    )
    assert attempt.sealed_bundle is not None
    assert len(attempt.model_turns) == 9
