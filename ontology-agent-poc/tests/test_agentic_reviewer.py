from __future__ import annotations

import pytest

from ontology_agent.io import sha256_value
from ontology_agent.studio.agentic_contracts import (
    AgentToolCallV1,
    AgentTurnRequestV1,
    AgentTurnResultV1,
)
from ontology_agent.studio.agentic_reviewer import (
    ReviewerToolConflict,
    ReviewerToolHarness,
    compile_review_engine,
    compile_review_objective,
    reviewer_tool_definitions,
    render_review_skill_instructions,
    run_agentic_review,
)
from ontology_agent.studio.agentic_runtime import StudioAgentRuntime
from ontology_agent.studio.agentic_store import InMemoryAgentCheckpointStore
from ontology_agent.studio.construction import (
    CandidateDraftDiffV1,
    ConstructionCandidateV1,
)
from ontology_agent.studio.package_authoring import PackageDraftOperation
from ontology_agent.studio.reviewer import ReviewerFindingV1
from ontology_agent.studio.skill_packages import LoadedSkillPackageV2, load_skill_package


class _Evidence:
    def list_sources(self):
        return ()


def _candidate(suffix: str, *, risk: str = "LOW") -> ConstructionCandidateV1:
    operation = PackageDraftOperation(
        action="UPSERT",
        collection="entities",
        object_id=f"entity.review_{suffix}",
        payload={
            "id": f"entity.review_{suffix}",
            "status": "proposed",
            "name": {"en": f"Review {suffix}"},
            "definition": "A typed review test object.",
            "primary_key": f"property.review_{suffix}_id",
            "grain": "one review test object",
            "lifecycle": "test",
            "owner": "actor.test",
            "sources": ["source.test"],
        },
    )
    return ConstructionCandidateV1(
        candidate_id="candidate." + suffix * 32,
        occurrence_key=("a" if suffix != "a" else "b") * 64,
        revision_digest=("c" if suffix != "c" else "d") * 64,
        candidate_type="OBJECT",
        label=f"Review {suffix}",
        definition="A typed review test object.",
        support_class="MODEL_INFERRED",
        risk_class=risk,
        compile_eligible=True,
        canonical_target=operation.object_id,
        proposal={"contract": "agentic-candidate-projection/v1"},
        proposed_operation=operation,
        draft_diff=CandidateDraftDiffV1(
            change_type="CREATE", after=operation.payload
        ),
    )


def _finding(candidate_id: str) -> ReviewerFindingV1:
    return ReviewerFindingV1(
        finding_id="finding.deterministic.test",
        finding_type="BROKEN_REFERENCE",
        severity="ERROR",
        summary="Broken deterministic reference",
        detail="The typed object references a missing property.",
        candidate_ids=(candidate_id,),
        evidence_fragment_ids=(),
        finding_authority="DETERMINISTIC",
        blocks_release=True,
        recommendation="Repair the reference before acceptance.",
    )


def _call(name: str, arguments: dict, suffix: str) -> AgentToolCallV1:
    return AgentToolCallV1(
        tool_call_id=f"tool-{suffix}", name=name, arguments=arguments
    )


def _harness() -> tuple[ReviewerToolHarness, tuple[ConstructionCandidateV1, ...]]:
    candidates = (_candidate("1", risk="HIGH"), _candidate("2"))
    deterministic = (_finding(candidates[0].candidate_id),)
    objective = compile_review_objective(
        run_id="construction-run." + "3" * 32,
        workspace_id="workspace.review",
        solution_id="ontology.review",
        source_set_digest="4" * 64,
        base_draft_checksum="5" * 64,
        candidate_bundle_checksum="6" * 64,
        candidates=candidates,
        deterministic_findings=deterministic,
        output_language="en",
    )
    return (
        ReviewerToolHarness(
            objective=objective,
            candidates=candidates,
            deterministic_findings=deterministic,
            evidence=_Evidence(),  # type: ignore[arg-type]
        ),
        candidates,
    )


def test_reviewer_registry_has_one_product_write_and_no_candidate_mutation() -> None:
    definitions = reviewer_tool_definitions()
    assert [item.name for item in definitions if item.mutating] == ["finding.upsert"]
    assert "candidate.upsert" not in {item.name for item in definitions}
    assert "candidate.apply_patch" not in {item.name for item in definitions}


def test_reviewer_completion_enforces_denominator_and_advisory_authority() -> None:
    harness, candidates = _harness()
    early = harness.execute_for_runtime(
        _call("run.request_completion", {"reason": "done"}, "early")
    )
    assert early["ok"] is False

    page = harness.execute_for_runtime(
        _call("candidate.list", {"offset": 0, "limit": 25}, "list")
    )
    assert page["complete_denominator_disclosed"] is True
    harness.execute_for_runtime(
        _call(
            "candidate.get",
            {"candidate_id": candidates[0].candidate_id},
            "get-high",
        )
    )
    harness.execute_for_runtime(
        _call("validator.list_findings", {}, "validators")
    )
    result = harness.execute_for_runtime(
        _call(
            "finding.upsert",
            {
                "expected_finding_revision": 0,
                "finding_key": "semantic-owner-check",
                "finding_type": "RELEASE_BLOCKER",
                "severity": "ERROR",
                "summary": "Owner requires confirmation",
                "detail": "The evidence does not identify the final business owner.",
                "candidate_ids": [candidates[0].candidate_id],
                "evidence_receipt_ids": [],
                "recommendation": "Ask the domain owner to confirm during HITL.",
            },
            "finding",
        )
    )
    assert result["finding"]["finding_authority"] == "ADVISORY"
    assert result["finding"]["blocks_release"] is False

    completed = harness.execute_for_runtime(
        _call("run.request_completion", {"reason": "review complete"}, "complete")
    )
    assert completed["ok"] is True
    assert harness.completion is not None
    assert harness.completion.findings[0].finding_authority == "ADVISORY"
    assert harness.completion.findings[0].blocks_release is False


def test_reviewer_can_inspect_a_bounded_candidate_batch() -> None:
    harness, candidates = _harness()

    result = harness.execute_for_runtime(
        _call(
            "candidate.get",
            {"candidate_ids": [item.candidate_id for item in candidates]},
            "get-batch",
        )
    )

    assert [item["candidate_id"] for item in result["candidates"]] == [
        item.candidate_id for item in candidates
    ]
    assert harness.inspected_candidate_ids == {
        item.candidate_id for item in candidates
    }


def test_reviewer_projects_and_enforces_mechanical_batch_plan() -> None:
    harness, candidates = _harness()

    plan = harness.review_plan()

    assert plan["contract"] == "studio-review-execution-plan/v1"
    assert plan["candidate_list_pages"] == [{"offset": 0, "limit": 100}]
    assert plan["required_high_risk_inspection_batches"] == [
        [candidates[0].candidate_id]
    ]
    assert plan["authority"] == "MECHANICAL_NAVIGATION_ONLY"


def test_reviewer_rejects_singleton_loop_when_high_risk_batch_remains() -> None:
    candidates = tuple(_candidate(str(index), risk="HIGH") for index in range(3, 6))
    objective = compile_review_objective(
        run_id="construction-run." + "7" * 32,
        workspace_id="workspace.review.batch",
        solution_id="ontology.review.batch",
        source_set_digest="8" * 64,
        base_draft_checksum="9" * 64,
        candidate_bundle_checksum="a" * 64,
        candidates=candidates,
        deterministic_findings=(),
        output_language="en",
    )
    harness = ReviewerToolHarness(
        objective=objective,
        candidates=candidates,
        deterministic_findings=(),
        evidence=_Evidence(),  # type: ignore[arg-type]
    )

    singleton = harness.execute_for_runtime(
        _call(
            "candidate.get",
            {"candidate_ids": [candidates[0].candidate_id]},
            "singleton-high-risk",
        )
    )
    assert singleton["ok"] is False
    assert "exact next batch" in singleton["message"]

    complete_batch = harness.execute_for_runtime(
        _call(
            "candidate.get",
            {"candidate_ids": [item.candidate_id for item in candidates]},
            "complete-high-risk-batch",
        )
    )
    assert len(complete_batch["candidates"]) == 3


def test_reviewer_invalid_arguments_explain_repair_fields() -> None:
    harness, _ = _harness()

    result = harness.execute_for_runtime(
        _call(
            "candidate.get",
            {"candidate_id": "not-a-candidate", "candidate_ids": []},
            "invalid-get",
        )
    )

    assert result["ok"] is False
    assert "candidate_id" in result["message"]


def test_reviewer_rejects_unread_evidence_and_unauthorized_candidate_write() -> None:
    harness, candidates = _harness()
    unread = harness.execute_for_runtime(
        _call(
            "finding.upsert",
            {
                "expected_finding_revision": 0,
                "finding_key": "invented-receipt",
                "finding_type": "UNSUPPORTED_CLAIM",
                "severity": "WARN",
                "summary": "Unsupported",
                "detail": "This cites evidence the Reviewer never read.",
                "candidate_ids": [candidates[0].candidate_id],
                "evidence_receipt_ids": ["evidence-receipt." + "9" * 32],
                "recommendation": "Read exact evidence first.",
            },
            "unread",
        )
    )
    assert unread["ok"] is False
    unauthorized = harness.execute_for_runtime(
        _call("candidate.upsert", {}, "unauthorized")
    )
    assert unauthorized["ok"] is False


def test_review_skill_v2_and_engine_freeze_exact_tool_authority() -> None:
    harness, _candidates = _harness()
    skill = load_skill_package("ontology-review", "2.0.0")
    assert isinstance(skill, LoadedSkillPackageV2)
    engine = compile_review_engine(
        objective=harness.objective,
        skill=skill,
        provider="qwen",
        requested_model="qwen3.8-max",
        parser_contract_digest="7" * 64,
    )
    assert engine.tool_registry_digest
    assert engine.objective_checksum == harness.objective.objective_checksum
    assert engine.skill_version == "2.0.0"


class _ReviewGateway:
    def __init__(self, high_risk_id: str) -> None:
        self.high_risk_id = high_risk_id
        self.requests: list[AgentTurnRequestV1] = []

    @staticmethod
    def _result(
        request: AgentTurnRequestV1,
        *,
        ordinal: int,
        name: str,
        arguments: dict[str, object],
    ) -> AgentTurnResultV1:
        raw: dict[str, object] = {
            "contract": "studio-agent-turn-result/v1",
            "requested_model": request.requested_model,
            "response_model": request.requested_model,
            "provider_request_id": f"review-provider-{ordinal}",
            "assistant_content": None,
            "tool_calls": [
                {
                    "tool_call_id": f"review-call-{ordinal}",
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

    def next(self, request: AgentTurnRequestV1) -> AgentTurnResultV1:
        self.requests.append(request)
        ordinal = len(self.requests)
        script = (
            ("candidate.list", {"offset": 0, "limit": 25}),
            ("candidate.get", {"candidate_id": self.high_risk_id}),
            ("validator.list_findings", {}),
            ("run.request_completion", {"reason": "reviewed exact denominator"}),
        )
        name, arguments = script[ordinal - 1]
        return self._result(
            request,
            ordinal=ordinal,
            name=name,
            arguments=arguments,
        )


def test_reviewer_uses_common_serial_runtime_with_fresh_context() -> None:
    harness, candidates = _harness()
    skill = load_skill_package("ontology-review", "2.0.0")
    assert isinstance(skill, LoadedSkillPackageV2)
    engine = compile_review_engine(
        objective=harness.objective,
        skill=skill,
        provider="qwen",
        requested_model="qwen3.8-max",
        parser_contract_digest="8" * 64,
    )
    gateway = _ReviewGateway(candidates[0].candidate_id)
    completion, usage = run_agentic_review(
        runtime=StudioAgentRuntime(
            gateway=gateway,
            checkpoint_store=InMemoryAgentCheckpointStore(),
        ),
        engine=engine,
        objective=harness.objective,
        skill_instructions=render_review_skill_instructions(skill),
        harness=harness,
    )

    assert completion.reviewed_candidate_ids == harness.objective.candidate_ids
    assert usage == {
        "model_calls": 4,
        "tool_calls": 4,
        "input_tokens": 40,
        "output_tokens": 20,
        "candidate_list_calls": 1,
        "candidate_get_calls": 1,
        "exact_evidence_read_calls": 0,
        "finding_write_calls": 0,
    }
    first_context = "\n".join(
        item.content or "" for item in gateway.requests[0].messages
    )
    assert "PRIVATE BUILDER RATIONALE" not in first_context
    assert "fresh Reviewer context" in first_context
    assert "studio-review-execution-plan/v1" in first_context
    assert candidates[0].candidate_id in first_context


def test_reviewer_tool_call_replay_mismatch_is_not_repairable() -> None:
    harness, _ = _harness()
    first = _call("candidate.list", {"offset": 0, "limit": 25}, "replay")
    harness.execute_for_runtime(first)

    conflicting = _call("candidate.list", {"offset": 25, "limit": 25}, "replay")
    with pytest.raises(ReviewerToolConflict):
        harness.execute_for_runtime(conflicting)
