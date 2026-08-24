from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from ontology_agent.io import sha256_value
from ontology_agent.models import OntologyPackage
from ontology_agent.studio.agentic_contracts import (
    BuildObjectiveV1,
    CandidateClaimV1,
    CandidateMutationV1,
    EvidenceReceiptV2,
    ObligationDispositionV1,
    RunAuthorityContextV1,
    ToolInvocationV1,
)
from ontology_agent.studio.agentic_store import (
    AgenticAuthorityError,
    AgenticStoreConflict,
    CandidateSealedError,
    InMemoryAgentCheckpointStore,
)
from ontology_agent.studio.package_authoring import PackageDraftOperation


NOW = datetime(2026, 8, 23, tzinfo=timezone.utc)


def _objective() -> BuildObjectiveV1:
    raw = {
        "contract": "studio-build-objective/v1",
        "objective_id": "build-objective." + "1" * 32,
        "solution_id": "ontology.example",
        "workspace_id": "workspace.example",
        "selected_source_version_ids": ["source-version." + "2" * 32],
        "source_set_digest": "3" * 64,
        "capabilities": ["SEMANTIC"],
        "output_language": "en",
        "obligations": [
            {
                "obligation_id": "obligation.request",
                "kind": "REQUIREMENT",
                "title": "Represent the service request",
                "source_version_ids": ["source-version." + "2" * 32],
                "source_locator": "lines:1-2",
                "required": True,
            }
        ],
        "required_validators": ["candidate.materialize"],
    }
    raw["objective_checksum"] = sha256_value(raw)
    return BuildObjectiveV1.model_validate(raw)


def _context(objective: BuildObjectiveV1, *, lease_epoch: int = 1) -> RunAuthorityContextV1:
    return RunAuthorityContextV1(
        job_id="construction-job." + "4" * 32,
        run_id="construction-run." + "5" * 32,
        attempt_id="construction-attempt." + "6" * 32,
        lease_epoch=lease_epoch,
        lease_owner="worker-1",
        workspace_id=objective.workspace_id,
        solution_id=objective.solution_id,
        source_set_digest=objective.source_set_digest,
        selected_source_version_ids=objective.selected_source_version_ids,
        principal_id="service.builder",
        tool_registry_digest="7" * 64,
        tool_policy_digest="8" * 64,
        objective_checksum=objective.objective_checksum,
        candidate_revision=0,
        step_sequence=0,
        remaining_model_calls=20,
        remaining_tool_calls=100,
    )


def _invocation(call_id: str, name: str, arguments: dict[str, object]) -> ToolInvocationV1:
    return ToolInvocationV1(
        tool_call_id=call_id,
        tool_name=name,
        arguments=arguments,
        arguments_digest=sha256_value(arguments),
    )


def _evidence(context: RunAuthorityContextV1) -> EvidenceReceiptV2:
    unsigned: dict[str, object] = {
        "contract": "studio-evidence-receipt/v2",
        "receipt_id": "evidence-receipt." + "9" * 32,
        "run_id": context.run_id,
        "workspace_id": context.workspace_id,
        "solution_id": context.solution_id,
        "source_set_digest": context.source_set_digest,
        "source_version_id": context.selected_source_version_ids[0],
        "source_bytes_checksum": "a" * 64,
        "parser_id": "plain-text",
        "parser_version": "1.0.0",
        "parsed_artifact_checksum": "b" * 64,
        "canonical_locator": "lines:1-2",
        "returned_content_checksum": "c" * 64,
        "logical_role_ids": ["asset.requirements"],
        "authority_context_digest": sha256_value(context),
        "issued_at": "2026-08-23T00:00:00Z",
    }
    unsigned["receipt_checksum"] = sha256_value(unsigned)
    return EvidenceReceiptV2.model_validate(unsigned)


def _entity_operation() -> PackageDraftOperation:
    return PackageDraftOperation(
        action="UPSERT",
        collection="entities",
        object_id="entity.service_request",
        payload={
            "id": "entity.service_request",
            "version": "1.0.0",
            "status": "proposed",
            "name": {"en": "Service Request"},
            "definition": "A request submitted for service.",
            "owner": "Service Owner",
            "sources": ["source.solution_brief"],
            "primary_key": "property.service_request.id",
            "grain": "one service request",
            "lifecycle": "submitted to closed",
        },
    )


def test_atomic_candidate_write_is_idempotent_and_revision_fenced(
    package: OntologyPackage,
) -> None:
    objective = _objective()
    context = _context(objective)
    store = InMemoryAgentCheckpointStore(clock=lambda: NOW)
    store.start_attempt(context, objective, package)

    evidence_invocation = _invocation("call-read", "evidence.read", {"line": 1})
    store.commit_tool_execution(
        context,
        evidence_invocation,
        result={"content": "A service request is submitted."},
        evidence_receipt=_evidence(context),
    )
    mutation = CandidateMutationV1(
        expected_candidate_revision=0,
        operation=_entity_operation(),
        claims=(
            CandidateClaimV1(
                path="definition",
                support="EXACT",
                evidence_receipt_ids=("evidence-receipt." + "9" * 32,),
            ),
        ),
    )
    invocation = _invocation(
        "call-upsert", "candidate.upsert", {"target": "entity.service_request"}
    )
    disposition = ObligationDispositionV1(
        obligation_id="obligation.request",
        disposition="CANDIDATE",
        candidate_targets=("entities:entity.service_request",),
    )
    first = store.commit_tool_execution(
        context,
        invocation,
        result={"candidate_revision": 1},
        mutation=mutation,
        obligation_dispositions=(disposition,),
    )
    replay = store.commit_tool_execution(
        context,
        invocation,
        result={"this": "must not replace the committed result"},
        mutation=mutation,
        obligation_dispositions=(disposition,),
    )
    assert replay == first
    assert store.view(context).candidate_revision == 1
    assert len(store.view(context).operations) == 1
    activity = store.activity(context.attempt_id)
    assert activity.candidate_count == 1
    assert activity.candidate_collection_counts == {"entities": 1}
    assert activity.tool_call_count == 2
    assert activity.activity_stage == "MODELING"

    changed = _invocation(
        "call-upsert", "candidate.upsert", {"target": "entity.other"}
    )
    with pytest.raises(AgenticStoreConflict, match="different arguments"):
        store.get_tool_receipt(context, changed)


def test_failed_attempt_continues_candidates_with_fresh_evidence_authority(
    package: OntologyPackage,
) -> None:
    objective = _objective()
    first_context = _context(objective)
    store = InMemoryAgentCheckpointStore(clock=lambda: NOW)
    store.start_attempt(first_context, objective, package)
    store.commit_tool_execution(
        first_context,
        _invocation("call-read", "evidence.read", {"line": 1}),
        result={"content": "A service request is submitted."},
        evidence_receipt=_evidence(first_context),
    )
    store.commit_tool_execution(
        first_context,
        _invocation("call-upsert", "candidate.upsert", {"target": "entity.service_request"}),
        result={"candidate_revision": 1},
        mutation=CandidateMutationV1(
            expected_candidate_revision=0,
            operation=_entity_operation(),
            claims=(
                CandidateClaimV1(
                    path="definition",
                    support="EXACT",
                    evidence_receipt_ids=("evidence-receipt." + "9" * 32,),
                ),
            ),
        ),
        obligation_dispositions=(
            ObligationDispositionV1(
                obligation_id="obligation.request",
                disposition="CANDIDATE",
                candidate_targets=("entities:entity.service_request",),
            ),
        ),
    )

    resumed_context = first_context.model_copy(
        update={
            "job_id": "construction-job." + "a" * 32,
            "run_id": "construction-run." + "b" * 32,
            "attempt_id": "construction-attempt." + "c" * 32,
        }
    )
    resumed = store.start_attempt(
        resumed_context,
        objective,
        package,
        resume_from_attempt_id=first_context.attempt_id,
    )

    assert resumed.resume_from_attempt_id == first_context.attempt_id
    assert resumed.initial_candidate_revision == 1
    assert resumed.initial_candidate_count == 1
    assert resumed.candidate_revision == 1
    assert resumed.step_sequence == 0
    assert resumed.operations == (_entity_operation(),)
    assert resumed.model_turns == ()
    assert store.activity(resumed_context.attempt_id).tool_call_count == 0
    assert len(resumed.evidence_receipts) == 1
    rebound = resumed.evidence_receipts[0]
    assert rebound.receipt_id != "evidence-receipt." + "9" * 32
    assert rebound.run_id == resumed_context.run_id
    assert rebound.authority_context_digest == sha256_value(resumed_context)
    claim = resumed.claims_by_target["entities:entity.service_request"][0]
    assert claim.evidence_receipt_ids == (rebound.receipt_id,)


def test_continuation_index_reuses_reissued_receipts_and_exact_candidate_ids(
    package: OntologyPackage,
) -> None:
    objective = _objective()
    first_context = _context(objective)
    store = InMemoryAgentCheckpointStore(clock=lambda: NOW)
    store.start_attempt(first_context, objective, package)
    store.commit_tool_execution(
        first_context,
        _invocation("call-read", "evidence.read", {"line": 1}),
        result={"content": "A service request is submitted."},
        evidence_receipt=_evidence(first_context),
    )
    operation = _entity_operation().model_copy(
        update={
            "payload": {
                **_entity_operation().payload,
                "sources": ["asset.requirements"],
            }
        }
    )
    store.commit_tool_execution(
        first_context,
        _invocation("call-upsert", "candidate.upsert", {"target": "entity.service_request"}),
        result={"candidate_revision": 1},
        mutation=CandidateMutationV1(
            expected_candidate_revision=0,
            operation=operation,
            claims=(
                CandidateClaimV1(
                    path="definition",
                    support="EXACT",
                    evidence_receipt_ids=("evidence-receipt." + "9" * 32,),
                ),
            ),
        ),
    )
    resumed_context = first_context.model_copy(
        update={
            "job_id": "construction-job." + "a" * 32,
            "run_id": "construction-run." + "b" * 32,
            "attempt_id": "construction-attempt." + "c" * 32,
        }
    )

    resumed = store.start_attempt(
        resumed_context,
        objective,
        package,
        resume_from_attempt_id=first_context.attempt_id,
    )

    notes = resumed.continuation_handoff_notes or ""
    _, marker, raw_index = notes.partition(
        "CURRENT SERVER CONTINUATION INDEX (EXACT EXECUTION STATE):\n"
    )
    assert marker
    index = json.loads(raw_index)
    assert index["candidate_revision"] == 1
    assert index["candidate_index"] == {
        "entities": ["entity.service_request"]
    }
    readiness = index["unresolved_obligation_readiness"][0]
    assert readiness["mechanically_eligible_targets_by_collection"] == {
        "entities": ["entities:entity.service_request"]
    }
    assert readiness["reusable_exact_receipts"][0]["receipt_id"] == (
        resumed.evidence_receipts[0].receipt_id
    )


def test_candidate_continuation_rejects_changed_tool_authority(
    package: OntologyPackage,
) -> None:
    objective = _objective()
    first_context = _context(objective)
    store = InMemoryAgentCheckpointStore(clock=lambda: NOW)
    store.start_attempt(first_context, objective, package)
    changed_context = first_context.model_copy(
        update={
            "job_id": "construction-job." + "a" * 32,
            "run_id": "construction-run." + "b" * 32,
            "attempt_id": "construction-attempt." + "c" * 32,
            "tool_registry_digest": "d" * 64,
        }
    )

    with pytest.raises(AgenticAuthorityError, match="authority boundary"):
        store.start_attempt(
            changed_context,
            objective,
            package,
            resume_from_attempt_id=first_context.attempt_id,
        )


def test_stale_lease_and_post_seal_mutation_are_rejected(
    package: OntologyPackage,
) -> None:
    objective = _objective()
    context = _context(objective)
    store = InMemoryAgentCheckpointStore(clock=lambda: NOW)
    store.start_attempt(context, objective, package)
    with pytest.raises(AgenticAuthorityError, match="stale"):
        store.view(_context(objective, lease_epoch=2))

    # A blocked outcome may legitimately seal a partial bundle after an explicit gap.
    disposition = ObligationDispositionV1(
        obligation_id="obligation.request",
        disposition="GAP",
        gap_id="gap.missing-business-owner",
        explanation="The source does not identify an accountable owner.",
    )
    store.commit_tool_execution(
        context,
        _invocation("call-gap", "gap.record", {"id": disposition.gap_id}),
        result={"candidate_revision": 1},
        expected_candidate_revision=0,
        obligation_dispositions=(disposition,),
    )
    bundle = store.seal(
        context,
        prospective_package_checksum=sha256_value(package),
        validator_report_digests=("d" * 64,),
    )
    assert bundle.candidate_revision == 1

    with pytest.raises(CandidateSealedError, match="sealed"):
        store.commit_tool_execution(
            context,
            _invocation("call-gap-2", "gap.record", {"id": "gap.other"}),
            result={"candidate_revision": 2},
            expected_candidate_revision=1,
            obligation_dispositions=(disposition,),
        )
