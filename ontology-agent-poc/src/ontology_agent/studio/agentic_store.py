from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Literal, Protocol

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..io import canonical_bytes, sha256_value
from ..models import OntologyPackage, StrictModel
from ..product_context import Base, ProductInfrastructureSettings
from .agentic_contracts import (
    AgentModelTurnReceiptV1,
    AgentTurnRequestV1,
    AgentTurnResultV1,
    BuildObjectiveV1,
    CandidateBundleV2,
    CandidateClaimV1,
    CandidateMutationV1,
    EvidenceReceiptV2,
    ObligationDispositionV1,
    RunAuthorityContextV1,
    ToolInvocationReceiptV1,
    ToolInvocationV1,
)
from .package_authoring import PackageDraftOperation, apply_package_operations


class AgenticStoreError(RuntimeError):
    """The Agent attempt journal or Candidate Workspace cannot be trusted."""


class AgenticStoreConflict(AgenticStoreError):
    """A CAS, tool-call identity, or immutable artifact conflict occurred."""


class AgenticAuthorityError(AgenticStoreError):
    """The caller no longer owns the active attempt lease."""


class CandidateSealedError(AgenticStoreConflict):
    """A sealed Candidate Bundle cannot be mutated."""


AgentAttemptActivityStage = Literal[
    "PREPARING",
    "READING_SOURCES",
    "MODELING",
    "VALIDATING",
    "FINALIZING",
]


class AgentAttemptActivityV1(StrictModel):
    """Safe progress projection: counts and stages, never prompts or reasoning."""

    contract: Literal["studio-agent-attempt-activity/v1"] = (
        "studio-agent-attempt-activity/v1"
    )
    attempt_id: str
    candidate_revision: int
    candidate_count: int
    candidate_collection_counts: dict[str, int]
    model_turn_count: int
    tool_call_count: int
    activity_stage: AgentAttemptActivityStage
    updated_at: datetime


def _activity_stage(tool_name: str | None, candidate_count: int) -> AgentAttemptActivityStage:
    if tool_name in {"candidate.materialize", "candidate.validate"}:
        return "VALIDATING"
    if tool_name in {"run.complete", "run.finish"}:
        return "FINALIZING"
    if tool_name and tool_name.startswith("candidate."):
        return "MODELING"
    if tool_name and tool_name.startswith(
        ("evidence.", "spreadsheet.", "sql.", "source.", "schema.")
    ):
        return "READING_SOURCES"
    return "MODELING" if candidate_count else "PREPARING"


@dataclass(frozen=True)
class CandidateWorkspaceView:
    objective: BuildObjectiveV1
    base_package: OntologyPackage
    candidate_revision: int
    step_sequence: int
    operations: tuple[PackageDraftOperation, ...]
    claims_by_target: dict[str, tuple[CandidateClaimV1, ...]]
    obligation_dispositions: tuple[ObligationDispositionV1, ...]
    evidence_receipts: tuple[EvidenceReceiptV2, ...]
    model_turns: tuple[AgentModelTurnReceiptV1, ...]
    sealed_bundle: CandidateBundleV2 | None
    cancelled: bool
    resume_from_attempt_id: str | None
    initial_candidate_revision: int
    initial_candidate_count: int
    continuation_handoff_notes: str | None


class AgentCheckpointStore(Protocol):
    def start_attempt(
        self,
        context: RunAuthorityContextV1,
        objective: BuildObjectiveV1,
        base_package: OntologyPackage,
        *,
        resume_from_attempt_id: str | None = None,
    ) -> CandidateWorkspaceView: ...

    def view(self, context: RunAuthorityContextV1) -> CandidateWorkspaceView: ...

    def activity(self, attempt_id: str) -> AgentAttemptActivityV1: ...

    def get_tool_receipt(
        self, context: RunAuthorityContextV1, invocation: ToolInvocationV1
    ) -> ToolInvocationReceiptV1 | None: ...

    def commit_model_turn(
        self,
        context: RunAuthorityContextV1,
        request: AgentTurnRequestV1,
        result: AgentTurnResultV1,
    ) -> AgentModelTurnReceiptV1: ...

    def commit_tool_execution(
        self,
        context: RunAuthorityContextV1,
        invocation: ToolInvocationV1,
        *,
        result: dict[str, object],
        expected_candidate_revision: int | None = None,
        mutation: CandidateMutationV1 | None = None,
        mutations: tuple[CandidateMutationV1, ...] = (),
        obligation_dispositions: tuple[ObligationDispositionV1, ...] = (),
        evidence_receipt: EvidenceReceiptV2 | None = None,
    ) -> ToolInvocationReceiptV1: ...

    def seal(
        self,
        context: RunAuthorityContextV1,
        *,
        prospective_package_checksum: str,
        validator_report_digests: tuple[str, ...],
    ) -> CandidateBundleV2: ...


@dataclass
class _AttemptState:
    authority: RunAuthorityContextV1
    objective: BuildObjectiveV1
    base_package: OntologyPackage
    candidate_revision: int = 0
    step_sequence: int = 0
    operations: dict[str, PackageDraftOperation] = field(default_factory=dict)
    claims_by_target: dict[str, tuple[CandidateClaimV1, ...]] = field(
        default_factory=dict
    )
    dispositions: dict[str, ObligationDispositionV1] = field(default_factory=dict)
    evidence_receipts: dict[str, EvidenceReceiptV2] = field(default_factory=dict)
    tool_receipts: dict[str, ToolInvocationReceiptV1] = field(default_factory=dict)
    model_turns: list[AgentModelTurnReceiptV1] = field(default_factory=list)
    sealed_bundle: CandidateBundleV2 | None = None
    cancelled: bool = False
    resume_from_attempt_id: str | None = None
    initial_candidate_revision: int = 0
    initial_candidate_count: int = 0
    continuation_handoff_notes: str | None = None


def _target(operation: PackageDraftOperation) -> str:
    return f"{operation.collection}:{operation.object_id}"


def _view(state: _AttemptState) -> CandidateWorkspaceView:
    return CandidateWorkspaceView(
        objective=state.objective,
        base_package=state.base_package,
        candidate_revision=state.candidate_revision,
        step_sequence=state.step_sequence,
        operations=tuple(state.operations[key] for key in sorted(state.operations)),
        claims_by_target=dict(state.claims_by_target),
        obligation_dispositions=tuple(
            state.dispositions[item.obligation_id]
            for item in state.objective.obligations
        ),
        evidence_receipts=tuple(
            state.evidence_receipts[key] for key in sorted(state.evidence_receipts)
        ),
        model_turns=tuple(state.model_turns),
        sealed_bundle=state.sealed_bundle,
        cancelled=state.cancelled,
        resume_from_attempt_id=state.resume_from_attempt_id,
        initial_candidate_revision=state.initial_candidate_revision,
        initial_candidate_count=state.initial_candidate_count,
        continuation_handoff_notes=state.continuation_handoff_notes,
    )


def _assert_resume_scope(
    seed: _AttemptState,
    context: RunAuthorityContextV1,
    objective: BuildObjectiveV1,
    base_package: OntologyPackage,
) -> None:
    if seed.objective != objective or seed.base_package != base_package:
        raise AgenticStoreConflict(
            "Candidate continuation does not match the frozen objective or Draft"
        )
    frozen = seed.authority
    if (
        frozen.attempt_id == context.attempt_id
        or frozen.workspace_id != context.workspace_id
        or frozen.solution_id != context.solution_id
        or frozen.source_set_digest != context.source_set_digest
        or frozen.selected_source_version_ids != context.selected_source_version_ids
        or frozen.principal_id != context.principal_id
        or frozen.tool_registry_digest != context.tool_registry_digest
        or frozen.tool_policy_digest != context.tool_policy_digest
        or frozen.objective_checksum != context.objective_checksum
    ):
        raise AgenticAuthorityError(
            "Candidate continuation changed the frozen authority boundary"
        )


def _reissue_evidence_receipt(
    receipt: EvidenceReceiptV2,
    context: RunAuthorityContextV1,
    *,
    issued_at: datetime,
) -> EvidenceReceiptV2:
    raw = receipt.model_dump(mode="json", exclude={"receipt_checksum"})
    raw.update(
        {
            "receipt_id": "evidence-receipt." + uuid.uuid4().hex,
            "run_id": context.run_id,
            "workspace_id": context.workspace_id,
            "solution_id": context.solution_id,
            "source_set_digest": context.source_set_digest,
            "authority_context_digest": sha256_value(context),
            "issued_at": issued_at.isoformat().replace("+00:00", "Z"),
        }
    )
    raw["receipt_checksum"] = sha256_value(raw)
    return EvidenceReceiptV2.model_validate(raw)


_LEGACY_CANDIDATE_SNAPSHOT_MARKER = (
    "\n\nCURRENT SERVER CANDIDATE SNAPSHOT (NON-AUTHORITATIVE):\n"
)
_CONTINUATION_INDEX_MARKER = (
    "\n\nCURRENT SERVER CONTINUATION INDEX (EXACT EXECUTION STATE):\n"
)


def _working_memory_only(notes: str | None) -> str | None:
    value = (notes or "").strip()
    for marker in (
        _LEGACY_CANDIDATE_SNAPSHOT_MARKER.strip(),
        _CONTINUATION_INDEX_MARKER.strip(),
    ):
        value = value.partition(marker)[0].strip()
    return value or None


def _receipt_matches_source_locator(
    source_locator: str, receipt: EvidenceReceiptV2
) -> bool:
    """Match a frozen worksheet obligation to an already-minted exact receipt."""

    parts = {}
    for item in source_locator.split(";"):
        key, separator, value = item.partition("=")
        if separator:
            parts[key.strip()] = value.strip()
    sheet = parts.get("sheet")
    cell_range = parts.get("range")
    if sheet and cell_range:
        return receipt.canonical_locator == f"xlsx:{sheet}!{cell_range}"
    return receipt.canonical_locator == source_locator


def _continuation_server_index(
    *,
    seed: _AttemptState,
    claims_by_target: dict[str, tuple[CandidateClaimV1, ...]],
    receipts: dict[str, EvidenceReceiptV2],
    inspected_targets: set[str],
) -> dict[str, object]:
    """Project exact continuation state without making semantic decisions.

    The index exposes mechanically eligible options and reusable receipt identities.
    The model still chooses semantic mappings; the shell merely prevents it from
    spending turns rediscovering durable server state.
    """

    candidate_index: dict[str, list[str]] = {}
    for operation in seed.operations.values():
        candidate_index.setdefault(operation.collection, []).append(
            operation.object_id
        )

    receipt_versions = {
        receipt_id: receipt.source_version_id
        for receipt_id, receipt in receipts.items()
    }
    roles_by_version: dict[str, set[str]] = {}
    for receipt in receipts.values():
        roles_by_version.setdefault(receipt.source_version_id, set()).update(
            receipt.logical_role_ids
        )

    def readiness(
        target: str, *, expected_versions: set[str], expected_roles: set[str]
    ) -> dict[str, object]:
        operation = seed.operations.get(target)
        if operation is None:
            return {
                "exists": False,
                "logical_source_ready": False,
                "exact_evidence_ready": False,
            }
        payload_sources = {
            str(value) for value in (operation.payload or {}).get("sources", [])
        }
        cited_versions = {
            receipt_versions[receipt_id]
            for claim in claims_by_target.get(target, ())
            for receipt_id in claim.evidence_receipt_ids
            if receipt_id in receipt_versions
        }
        return {
            "exists": True,
            "logical_source_ready": bool(payload_sources & expected_roles),
            "exact_evidence_ready": bool(cited_versions & expected_versions),
        }

    unresolved = []
    snapshot_targets = set(inspected_targets)
    for obligation in seed.objective.obligations:
        disposition = seed.dispositions.get(obligation.obligation_id)
        if disposition is not None and disposition.disposition != "UNRESOLVED":
            continue
        expected_versions = set(obligation.source_version_ids)
        expected_roles = set().union(
            *(roles_by_version.get(version_id, set()) for version_id in expected_versions)
        )
        item: dict[str, object] = {
            "obligation_id": obligation.obligation_id,
            "kind": obligation.kind,
            "required_candidate_collections": list(
                obligation.required_candidate_collections
            ),
        }
        contract = obligation.metric_semantic_contract
        if contract is not None:
            required_target = f"metrics:{contract.expected_metric_id}"
            target_readiness = readiness(
                required_target,
                expected_versions=expected_versions,
                expected_roles=expected_roles,
            )
            item["required_target"] = required_target
            item["required_target_readiness"] = target_readiness
            if not all(target_readiness.values()):
                snapshot_targets.add(required_target)
        else:
            eligible_by_collection: dict[str, list[str]] = {}
            allowed_collections = set(obligation.required_candidate_collections)
            for target, operation in sorted(seed.operations.items()):
                if allowed_collections and operation.collection not in allowed_collections:
                    continue
                target_readiness = readiness(
                    target,
                    expected_versions=expected_versions,
                    expected_roles=expected_roles,
                )
                if not (
                    target_readiness["logical_source_ready"]
                    and target_readiness["exact_evidence_ready"]
                ):
                    continue
                values = eligible_by_collection.setdefault(operation.collection, [])
                if len(values) < 8:
                    values.append(target)
            item["mechanically_eligible_targets_by_collection"] = (
                eligible_by_collection
            )

        exact_receipts = [
            {
                "receipt_id": receipt.receipt_id,
                "source_version_id": receipt.source_version_id,
                "canonical_locator": receipt.canonical_locator,
                "logical_role_ids": list(receipt.logical_role_ids),
            }
            for receipt in receipts.values()
            if receipt.source_version_id in expected_versions
            and _receipt_matches_source_locator(obligation.source_locator, receipt)
        ]
        if exact_receipts:
            item["reusable_exact_receipts"] = sorted(
                exact_receipts, key=lambda value: str(value["receipt_id"])
            )[:8]
        unresolved.append(item)

    candidate_snapshots: list[dict[str, object]] = []
    snapshot_bytes = 0
    for target in sorted(snapshot_targets):
        operation = seed.operations.get(target)
        if operation is None:
            continue
        editable_payload = dict(operation.payload or {})
        for server_owned in ("id", "status", "sources"):
            editable_payload.pop(server_owned, None)
        item = {
            "target": target,
            "collection": operation.collection,
            "object_id": operation.object_id,
            "editable_payload": editable_payload,
        }
        item_size = len(canonical_bytes(item))
        if snapshot_bytes + item_size > 32_000:
            break
        candidate_snapshots.append(item)
        snapshot_bytes += item_size

    return {
        "candidate_revision": seed.candidate_revision,
        "candidate_index": {
            collection: sorted(object_ids)
            for collection, object_ids in sorted(candidate_index.items())
        },
        "unresolved_obligation_readiness": unresolved,
        "editable_candidate_snapshots": candidate_snapshots,
    }


def _resume_state(
    seed: _AttemptState,
    context: RunAuthorityContextV1,
    objective: BuildObjectiveV1,
    base_package: OntologyPackage,
    *,
    issued_at: datetime,
) -> _AttemptState:
    """Fork durable Candidate state, never the prior model conversation or budget."""

    _assert_resume_scope(seed, context, objective, base_package)
    receipt_id_map: dict[str, str] = {}
    receipts: dict[str, EvidenceReceiptV2] = {}
    for old_id, receipt in sorted(seed.evidence_receipts.items()):
        rebound = _reissue_evidence_receipt(receipt, context, issued_at=issued_at)
        receipt_id_map[old_id] = rebound.receipt_id
        receipts[rebound.receipt_id] = rebound

    claims_by_target: dict[str, tuple[CandidateClaimV1, ...]] = {}
    for target, claims in seed.claims_by_target.items():
        claims_by_target[target] = tuple(
            CandidateClaimV1(
                path=claim.path,
                support=claim.support,
                evidence_receipt_ids=tuple(
                    receipt_id_map[receipt_id]
                    for receipt_id in claim.evidence_receipt_ids
                ),
            )
            for claim in claims
        )

    handoff_notes = _working_memory_only(seed.continuation_handoff_notes)
    for turn in reversed(seed.model_turns):
        if not turn.result.tool_calls:
            continue
        call = turn.result.tool_calls[0]
        if call.name != "run.update_working_memory":
            continue
        notes = call.arguments.get("notes")
        if isinstance(notes, str) and notes.strip():
            handoff_notes = notes.strip()[:6_000]
            break

    inspected_targets: set[str] = set()
    for turn in seed.model_turns:
        if not turn.result.tool_calls:
            continue
        call = turn.result.tool_calls[0]
        if call.name != "candidate.get":
            continue
        collection = call.arguments.get("collection")
        object_id = call.arguments.get("object_id")
        if isinstance(collection, str) and isinstance(object_id, str):
            inspected_targets.add(f"{collection}:{object_id}")
    if seed.operations:
        server_index = canonical_bytes(
            _continuation_server_index(
                seed=seed,
                claims_by_target=claims_by_target,
                receipts=receipts,
                inspected_targets=inspected_targets,
            )
        ).decode("utf-8")
        handoff_notes = (
            (
                handoff_notes + _CONTINUATION_INDEX_MARKER
                if handoff_notes
                else _CONTINUATION_INDEX_MARKER.lstrip()
            )
            + server_index
        )

    return _AttemptState(
        authority=context,
        objective=objective,
        base_package=base_package,
        candidate_revision=seed.candidate_revision,
        step_sequence=0,
        operations=dict(seed.operations),
        claims_by_target=claims_by_target,
        dispositions=dict(seed.dispositions),
        evidence_receipts=receipts,
        tool_receipts={},
        model_turns=[],
        sealed_bundle=None,
        cancelled=False,
        resume_from_attempt_id=seed.authority.attempt_id,
        initial_candidate_revision=seed.candidate_revision,
        initial_candidate_count=len(seed.operations),
        continuation_handoff_notes=handoff_notes,
    )


class InMemoryAgentCheckpointStore:
    """Reference implementation of the production journal transaction semantics."""

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._attempts: dict[str, _AttemptState] = {}
        self._lock = threading.RLock()

    def start_attempt(
        self,
        context: RunAuthorityContextV1,
        objective: BuildObjectiveV1,
        base_package: OntologyPackage,
        *,
        resume_from_attempt_id: str | None = None,
    ) -> CandidateWorkspaceView:
        with self._lock:
            if objective.objective_checksum != context.objective_checksum:
                raise AgenticAuthorityError("Build objective is outside run authority")
            if (
                objective.workspace_id != context.workspace_id
                or objective.solution_id != context.solution_id
                or objective.source_set_digest != context.source_set_digest
                or objective.selected_source_version_ids
                != context.selected_source_version_ids
            ):
                raise AgenticAuthorityError("Build objective scope mismatch")
            existing = self._attempts.get(context.attempt_id)
            if existing is not None:
                if existing.resume_from_attempt_id != resume_from_attempt_id:
                    raise AgenticStoreConflict(
                        "Attempt identity already names another continuation lineage"
                    )
                if (
                    existing.objective != objective
                    or existing.base_package != base_package
                ):
                    raise AgenticStoreConflict(
                        "Attempt identity already names another frozen input"
                    )
                if context.lease_epoch < existing.authority.lease_epoch:
                    raise AgenticAuthorityError("Agent attempt lease is stale")
                if context.lease_epoch > existing.authority.lease_epoch:
                    frozen = existing.authority
                    if (
                        frozen.job_id != context.job_id
                        or frozen.run_id != context.run_id
                        or frozen.attempt_id != context.attempt_id
                        or frozen.workspace_id != context.workspace_id
                        or frozen.solution_id != context.solution_id
                        or frozen.source_set_digest != context.source_set_digest
                        or frozen.selected_source_version_ids
                        != context.selected_source_version_ids
                        or frozen.principal_id != context.principal_id
                        or frozen.tool_registry_digest != context.tool_registry_digest
                        or frozen.tool_policy_digest != context.tool_policy_digest
                        or frozen.objective_checksum != context.objective_checksum
                    ):
                        raise AgenticAuthorityError("Agent attempt rebind changed frozen scope")
                    existing.authority = context
                self._assert_authority(existing, context)
                return _view(existing)
            if resume_from_attempt_id is not None:
                try:
                    seed = self._attempts[resume_from_attempt_id]
                except KeyError as exc:
                    raise AgenticStoreError(
                        "Candidate continuation source is unavailable"
                    ) from exc
                state = _resume_state(
                    seed,
                    context,
                    objective,
                    base_package,
                    issued_at=self.clock(),
                )
            else:
                dispositions = {
                    item.obligation_id: ObligationDispositionV1(
                        obligation_id=item.obligation_id,
                        disposition="UNRESOLVED",
                    )
                    for item in objective.obligations
                }
                state = _AttemptState(
                    authority=context,
                    objective=objective,
                    base_package=base_package,
                    dispositions=dispositions,
                )
            self._attempts[context.attempt_id] = state
            return _view(state)

    def _state(self, attempt_id: str) -> _AttemptState:
        try:
            return self._attempts[attempt_id]
        except KeyError as exc:
            raise AgenticStoreError("Agent attempt is unavailable") from exc

    @staticmethod
    def _assert_authority(
        state: _AttemptState, context: RunAuthorityContextV1
    ) -> None:
        frozen = state.authority
        if state.cancelled:
            raise AgenticAuthorityError("Agent attempt is cancelled")
        if (
            frozen.job_id != context.job_id
            or frozen.run_id != context.run_id
            or frozen.attempt_id != context.attempt_id
            or frozen.lease_epoch != context.lease_epoch
            or frozen.lease_owner != context.lease_owner
            or frozen.workspace_id != context.workspace_id
            or frozen.solution_id != context.solution_id
            or frozen.source_set_digest != context.source_set_digest
            or frozen.selected_source_version_ids
            != context.selected_source_version_ids
            or frozen.principal_id != context.principal_id
            or frozen.tool_registry_digest != context.tool_registry_digest
            or frozen.tool_policy_digest != context.tool_policy_digest
            or frozen.objective_checksum != context.objective_checksum
        ):
            raise AgenticAuthorityError("Agent attempt lease or scope is stale")

    def view(self, context: RunAuthorityContextV1) -> CandidateWorkspaceView:
        with self._lock:
            state = self._state(context.attempt_id)
            self._assert_authority(state, context)
            return _view(state)

    def activity(self, attempt_id: str) -> AgentAttemptActivityV1:
        with self._lock:
            try:
                state = self._attempts[attempt_id]
            except KeyError as exc:
                raise AgenticStoreError("Agent attempt is unavailable") from exc
            receipts = sorted(
                state.tool_receipts.values(), key=lambda item: item.step_sequence
            )
            counts: dict[str, int] = {}
            for operation in state.operations.values():
                counts[operation.collection] = counts.get(operation.collection, 0) + 1
            last_tool = receipts[-1].tool_name if receipts else None
            return AgentAttemptActivityV1(
                attempt_id=attempt_id,
                candidate_revision=state.candidate_revision,
                candidate_count=len(state.operations),
                candidate_collection_counts=counts,
                model_turn_count=len(state.model_turns),
                tool_call_count=len(receipts),
                activity_stage=_activity_stage(last_tool, len(state.operations)),
                updated_at=self.clock(),
            )

    def get_tool_receipt(
        self, context: RunAuthorityContextV1, invocation: ToolInvocationV1
    ) -> ToolInvocationReceiptV1 | None:
        with self._lock:
            state = self._state(context.attempt_id)
            self._assert_authority(state, context)
            existing = state.tool_receipts.get(invocation.tool_call_id)
            if existing is None:
                return None
            if (
                existing.tool_name != invocation.tool_name
                or existing.arguments_digest != invocation.arguments_digest
            ):
                raise AgenticStoreConflict(
                    "Tool call ID was replayed with different arguments"
                )
            return existing

    def commit_tool_execution(
        self,
        context: RunAuthorityContextV1,
        invocation: ToolInvocationV1,
        *,
        result: dict[str, object],
        expected_candidate_revision: int | None = None,
        mutation: CandidateMutationV1 | None = None,
        mutations: tuple[CandidateMutationV1, ...] = (),
        obligation_dispositions: tuple[ObligationDispositionV1, ...] = (),
        evidence_receipt: EvidenceReceiptV2 | None = None,
    ) -> ToolInvocationReceiptV1:
        with self._lock:
            state = self._state(context.attempt_id)
            self._assert_authority(state, context)
            existing = self.get_tool_receipt(context, invocation)
            if existing is not None:
                return existing
            if mutation is not None and mutations:
                raise AgenticStoreConflict(
                    "A tool execution cannot mix one mutation with a mutation patch"
                )
            all_mutations = (mutation,) if mutation is not None else mutations
            changes_candidate = bool(all_mutations) or bool(obligation_dispositions)
            if state.sealed_bundle is not None and changes_candidate:
                raise CandidateSealedError("Candidate Bundle is already sealed")
            if changes_candidate:
                mutation_revisions = {
                    item.expected_candidate_revision for item in all_mutations
                }
                if len(mutation_revisions) > 1:
                    raise AgenticStoreConflict(
                        "Candidate patch mutations must share one CAS revision"
                    )
                expected = (
                    next(iter(mutation_revisions))
                    if mutation_revisions
                    else expected_candidate_revision
                )
                if expected is None or expected != state.candidate_revision:
                    raise AgenticStoreConflict("Candidate revision CAS failed")
            if evidence_receipt is not None:
                if (
                    evidence_receipt.run_id != context.run_id
                    or evidence_receipt.workspace_id != context.workspace_id
                    or evidence_receipt.solution_id != context.solution_id
                    or evidence_receipt.source_set_digest != context.source_set_digest
                    or evidence_receipt.source_version_id
                    not in context.selected_source_version_ids
                ):
                    raise AgenticAuthorityError(
                        "Evidence receipt is outside the exact run source set"
                    )
                state.evidence_receipts[evidence_receipt.receipt_id] = evidence_receipt
            if all_mutations:
                receipt_ids = {
                    receipt_id
                    for item in all_mutations
                    for claim in item.claims
                    for receipt_id in claim.evidence_receipt_ids
                }
                if not receipt_ids.issubset(state.evidence_receipts):
                    raise AgenticStoreConflict(
                        "Candidate claim references an unavailable evidence receipt"
                    )
                # Validate the operation against the exact prospective package before
                # it becomes the new candidate head. Cross-reference closure is a
                # completion concern; closed payload typing is immediate.
                prospective = dict(state.operations)
                mutation_targets = [_target(item.operation) for item in all_mutations]
                if len(mutation_targets) != len(set(mutation_targets)):
                    raise AgenticStoreConflict(
                        "Candidate patch contains duplicate targets"
                    )
                for item in all_mutations:
                    prospective[_target(item.operation)] = item.operation
                apply_package_operations(
                    state.base_package,
                    tuple(prospective[key] for key in sorted(prospective)),
                )
                state.operations = prospective
                for item in all_mutations:
                    state.claims_by_target[_target(item.operation)] = item.claims
            obligation_ids = {item.obligation_id for item in state.objective.obligations}
            for disposition in obligation_dispositions:
                if disposition.obligation_id not in obligation_ids:
                    raise AgenticStoreConflict(
                        "Model cannot introduce or replace frozen obligations"
                    )
                for target in disposition.candidate_targets:
                    if target not in state.operations:
                        raise AgenticStoreConflict(
                            "Obligation disposition references a missing candidate"
                        )
                state.dispositions[disposition.obligation_id] = disposition
            before = state.candidate_revision
            if changes_candidate:
                state.candidate_revision += 1
            state.step_sequence += 1
            committed_at = self.clock()
            receipt = ToolInvocationReceiptV1(
                receipt_id="tool-receipt." + uuid.uuid4().hex,
                job_id=context.job_id,
                run_id=context.run_id,
                attempt_id=context.attempt_id,
                lease_epoch=context.lease_epoch,
                step_sequence=state.step_sequence,
                tool_call_id=invocation.tool_call_id,
                tool_name=invocation.tool_name,
                arguments_digest=invocation.arguments_digest,
                mutating=changes_candidate,
                candidate_revision_before=before,
                candidate_revision_after=state.candidate_revision,
                result=result,
                result_digest=sha256_value(result),
                committed_at=committed_at,
            )
            state.tool_receipts[invocation.tool_call_id] = receipt
            return receipt

    def commit_model_turn(
        self,
        context: RunAuthorityContextV1,
        request: AgentTurnRequestV1,
        result: AgentTurnResultV1,
    ) -> AgentModelTurnReceiptV1:
        with self._lock:
            state = self._state(context.attempt_id)
            self._assert_authority(state, context)
            if result.request_digest != request.request_digest:
                raise AgenticStoreConflict("Model result does not match its request")
            existing = next(
                (
                    item
                    for item in state.model_turns
                    if item.request.request_digest == request.request_digest
                ),
                None,
            )
            if existing is not None:
                if existing.result != result:
                    raise AgenticStoreConflict(
                        "Model request digest already names another result"
                    )
                return existing
            state.step_sequence += 1
            receipt = AgentModelTurnReceiptV1(
                turn_id="agent-turn." + uuid.uuid4().hex,
                job_id=context.job_id,
                run_id=context.run_id,
                attempt_id=context.attempt_id,
                lease_epoch=context.lease_epoch,
                step_sequence=state.step_sequence,
                request=request,
                result=result,
                committed_at=self.clock(),
            )
            state.model_turns.append(receipt)
            return receipt

    def seal(
        self,
        context: RunAuthorityContextV1,
        *,
        prospective_package_checksum: str,
        validator_report_digests: tuple[str, ...],
    ) -> CandidateBundleV2:
        with self._lock:
            state = self._state(context.attempt_id)
            self._assert_authority(state, context)
            if state.sealed_bundle is not None:
                if (
                    state.sealed_bundle.prospective_package_checksum
                    != prospective_package_checksum
                    or state.sealed_bundle.validator_report_digests
                    != validator_report_digests
                ):
                    raise CandidateSealedError(
                        "Attempt is already sealed with another exact result"
                    )
                return state.sealed_bundle
            unresolved = [
                item.obligation_id
                for item in state.dispositions.values()
                if item.disposition == "UNRESOLVED"
            ]
            if unresolved:
                raise AgenticStoreConflict(
                    "Cannot seal while frozen obligations are unresolved"
                )
            unsigned: dict[str, object] = {
                "contract": "studio-candidate-bundle/v2",
                "bundle_id": "candidate-bundle." + uuid.uuid4().hex,
                "run_id": context.run_id,
                "attempt_id": context.attempt_id,
                "objective_checksum": state.objective.objective_checksum,
                "candidate_revision": state.candidate_revision,
                "operations": [
                    state.operations[key].model_dump(mode="json")
                    for key in sorted(state.operations)
                ],
                "claims_by_target": {
                    key: [item.model_dump(mode="json") for item in value]
                    for key, value in sorted(state.claims_by_target.items())
                },
                "obligation_dispositions": [
                    state.dispositions[item.obligation_id].model_dump(mode="json")
                    for item in state.objective.obligations
                ],
                "evidence_receipt_ids": sorted(state.evidence_receipts),
                "prospective_package_checksum": prospective_package_checksum,
                "validator_report_digests": list(validator_report_digests),
                "sealed_at": self.clock().isoformat().replace("+00:00", "Z"),
            }
            unsigned["bundle_checksum"] = sha256_value(unsigned)
            state.sealed_bundle = CandidateBundleV2.model_validate(unsigned)
            return state.sealed_bundle

    def cancel(self, attempt_id: str) -> None:
        with self._lock:
            self._state(attempt_id).cancelled = True


def _state_payload(state: _AttemptState) -> dict[str, object]:
    return {
        "contract": "studio-agent-attempt-state/v1",
        "authority": state.authority.model_dump(mode="json"),
        "objective": state.objective.model_dump(mode="json"),
        "base_package": state.base_package.model_dump(mode="json"),
        "candidate_revision": state.candidate_revision,
        "step_sequence": state.step_sequence,
        "operations": [
            state.operations[key].model_dump(mode="json")
            for key in sorted(state.operations)
        ],
        "claims_by_target": {
            key: [item.model_dump(mode="json") for item in values]
            for key, values in sorted(state.claims_by_target.items())
        },
        "dispositions": {
            key: item.model_dump(mode="json")
            for key, item in sorted(state.dispositions.items())
        },
        "evidence_receipts": {
            key: item.model_dump(mode="json")
            for key, item in sorted(state.evidence_receipts.items())
        },
        "sealed_bundle": (
            state.sealed_bundle.model_dump(mode="json")
            if state.sealed_bundle is not None
            else None
        ),
        "cancelled": state.cancelled,
        "resume_from_attempt_id": state.resume_from_attempt_id,
        "initial_candidate_revision": state.initial_candidate_revision,
        "initial_candidate_count": state.initial_candidate_count,
        "continuation_handoff_notes": state.continuation_handoff_notes,
    }


def _state_from_payload(
    payload: dict[str, object],
    *,
    model_turns: tuple[AgentModelTurnReceiptV1, ...] = (),
) -> _AttemptState:
    operations = tuple(
        PackageDraftOperation.model_validate(item)
        for item in payload.get("operations", [])  # type: ignore[arg-type]
    )
    raw_claims = payload.get("claims_by_target", {})
    raw_dispositions = payload.get("dispositions", {})
    raw_receipts = payload.get("evidence_receipts", {})
    sealed = payload.get("sealed_bundle")
    return _AttemptState(
        authority=RunAuthorityContextV1.model_validate(payload["authority"]),
        objective=BuildObjectiveV1.model_validate(payload["objective"]),
        base_package=OntologyPackage.model_validate(payload["base_package"]),
        candidate_revision=int(payload.get("candidate_revision", 0)),
        step_sequence=int(payload.get("step_sequence", 0)),
        operations={_target(item): item for item in operations},
        claims_by_target={
            str(key): tuple(CandidateClaimV1.model_validate(item) for item in values)
            for key, values in dict(raw_claims).items()  # type: ignore[arg-type]
        },
        dispositions={
            str(key): ObligationDispositionV1.model_validate(value)
            for key, value in dict(raw_dispositions).items()  # type: ignore[arg-type]
        },
        evidence_receipts={
            str(key): EvidenceReceiptV2.model_validate(value)
            for key, value in dict(raw_receipts).items()  # type: ignore[arg-type]
        },
        model_turns=list(model_turns),
        sealed_bundle=(CandidateBundleV2.model_validate(sealed) if sealed else None),
        cancelled=bool(payload.get("cancelled", False)),
        resume_from_attempt_id=(
            str(payload["resume_from_attempt_id"])
            if payload.get("resume_from_attempt_id")
            else None
        ),
        initial_candidate_revision=int(payload.get("initial_candidate_revision", 0)),
        initial_candidate_count=int(payload.get("initial_candidate_count", 0)),
        continuation_handoff_notes=(
            str(payload["continuation_handoff_notes"])
            if payload.get("continuation_handoff_notes")
            else None
        ),
    )


class StudioAgentAttemptRow(Base):
    __tablename__ = "studio_agent_attempt"

    attempt_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    workspace_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    solution_id: Mapped[str] = mapped_column(String(255), nullable=False)
    lease_epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    lease_owner: Mapped[str] = mapped_column(String(255), nullable=False)
    candidate_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    step_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    state_payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StudioAgentModelTurnRow(Base):
    __tablename__ = "studio_agent_model_turn"
    __table_args__ = (
        UniqueConstraint(
            "attempt_id",
            "request_digest",
            name="uq_studio_agent_model_turn_request",
        ),
    )

    turn_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    attempt_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    lease_epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    step_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    committed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StudioAgentToolReceiptRow(Base):
    __tablename__ = "studio_agent_tool_receipt"
    __table_args__ = (
        UniqueConstraint(
            "attempt_id",
            "tool_call_id",
            name="uq_studio_agent_tool_receipt_call",
        ),
    )

    receipt_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    attempt_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    lease_epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    step_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    tool_call_id: Mapped[str] = mapped_column(String(500), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(255), nullable=False)
    arguments_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    committed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PostgresAgentCheckpointStore:
    """Canonical durable Candidate Workspace and append-only execution journal."""

    def __init__(
        self,
        database_url: str,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @classmethod
    def from_settings(
        cls, settings: ProductInfrastructureSettings
    ) -> PostgresAgentCheckpointStore:
        if settings.mode != "postgresql-s3" or not settings.database_url:
            raise AgenticStoreError("Agent checkpoint storage requires PostgreSQL")
        return cls(settings.database_url)

    @staticmethod
    def _assert_frozen_input(
        state: _AttemptState,
        context: RunAuthorityContextV1,
        objective: BuildObjectiveV1,
        base_package: OntologyPackage,
    ) -> None:
        if state.objective != objective or state.base_package != base_package:
            raise AgenticStoreConflict("Attempt identity already names another frozen input")
        frozen = state.authority
        if (
            frozen.job_id != context.job_id
            or frozen.run_id != context.run_id
            or frozen.attempt_id != context.attempt_id
            or frozen.workspace_id != context.workspace_id
            or frozen.solution_id != context.solution_id
            or frozen.source_set_digest != context.source_set_digest
            or frozen.selected_source_version_ids != context.selected_source_version_ids
            or frozen.principal_id != context.principal_id
            or frozen.tool_registry_digest != context.tool_registry_digest
            or frozen.tool_policy_digest != context.tool_policy_digest
            or frozen.objective_checksum != context.objective_checksum
        ):
            raise AgenticAuthorityError("Agent attempt rebind changed frozen scope")

    @staticmethod
    def _turns(session: Session, attempt_id: str) -> tuple[AgentModelTurnReceiptV1, ...]:
        rows = session.scalars(
            select(StudioAgentModelTurnRow)
            .where(StudioAgentModelTurnRow.attempt_id == attempt_id)
            .order_by(StudioAgentModelTurnRow.step_sequence)
        ).all()
        return tuple(AgentModelTurnReceiptV1.model_validate(row.payload) for row in rows)

    def _locked_state(
        self, session: Session, context: RunAuthorityContextV1
    ) -> tuple[StudioAgentAttemptRow, _AttemptState]:
        row = session.scalar(
            select(StudioAgentAttemptRow)
            .where(StudioAgentAttemptRow.attempt_id == context.attempt_id)
            .with_for_update()
        )
        if row is None:
            raise AgenticStoreError("Agent attempt is unavailable")
        state = _state_from_payload(
            row.state_payload,
            model_turns=self._turns(session, context.attempt_id),
        )
        InMemoryAgentCheckpointStore._assert_authority(state, context)
        return row, state

    @staticmethod
    def _persist(row: StudioAgentAttemptRow, state: _AttemptState, now: datetime) -> None:
        row.lease_epoch = state.authority.lease_epoch
        row.lease_owner = state.authority.lease_owner
        row.candidate_revision = state.candidate_revision
        row.step_sequence = state.step_sequence
        row.state_payload = _state_payload(state)
        row.updated_at = now

    def start_attempt(
        self,
        context: RunAuthorityContextV1,
        objective: BuildObjectiveV1,
        base_package: OntologyPackage,
        *,
        resume_from_attempt_id: str | None = None,
    ) -> CandidateWorkspaceView:
        if objective.objective_checksum != context.objective_checksum:
            raise AgenticAuthorityError("Build objective is outside run authority")
        if (
            objective.workspace_id != context.workspace_id
            or objective.solution_id != context.solution_id
            or objective.source_set_digest != context.source_set_digest
            or objective.selected_source_version_ids
            != context.selected_source_version_ids
        ):
            raise AgenticAuthorityError("Build objective scope mismatch")
        try:
            with Session(self.engine) as session, session.begin():
                row = session.scalar(
                    select(StudioAgentAttemptRow)
                    .where(StudioAgentAttemptRow.attempt_id == context.attempt_id)
                    .with_for_update()
                )
                now = self.clock()
                if row is None:
                    if resume_from_attempt_id is not None:
                        seed_row = session.scalar(
                            select(StudioAgentAttemptRow)
                            .where(
                                StudioAgentAttemptRow.attempt_id
                                == resume_from_attempt_id
                            )
                            .with_for_update()
                        )
                        if seed_row is None:
                            raise AgenticStoreError(
                                "Candidate continuation source is unavailable"
                            )
                        seed = _state_from_payload(
                            seed_row.state_payload,
                            model_turns=self._turns(session, resume_from_attempt_id),
                        )
                        state = _resume_state(
                            seed,
                            context,
                            objective,
                            base_package,
                            issued_at=now,
                        )
                    else:
                        state = _AttemptState(
                            authority=context,
                            objective=objective,
                            base_package=base_package,
                            dispositions={
                                item.obligation_id: ObligationDispositionV1(
                                    obligation_id=item.obligation_id,
                                    disposition="UNRESOLVED",
                                )
                                for item in objective.obligations
                            },
                        )
                    row = StudioAgentAttemptRow(
                        attempt_id=context.attempt_id,
                        job_id=context.job_id,
                        run_id=context.run_id,
                        workspace_id=context.workspace_id,
                        solution_id=context.solution_id,
                        lease_epoch=context.lease_epoch,
                        lease_owner=context.lease_owner,
                        candidate_revision=state.candidate_revision,
                        step_sequence=0,
                        state_payload=_state_payload(state),
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(row)
                    session.flush()
                    return _view(state)
                state = _state_from_payload(
                    row.state_payload,
                    model_turns=self._turns(session, context.attempt_id),
                )
                if state.resume_from_attempt_id != resume_from_attempt_id:
                    raise AgenticStoreConflict(
                        "Attempt identity already names another continuation lineage"
                    )
                self._assert_frozen_input(state, context, objective, base_package)
                if context.lease_epoch < state.authority.lease_epoch:
                    raise AgenticAuthorityError("Agent attempt lease is stale")
                if context.lease_epoch > state.authority.lease_epoch:
                    state.authority = context
                    self._persist(row, state, now)
                InMemoryAgentCheckpointStore._assert_authority(state, context)
                return _view(state)
        except AgenticStoreError:
            raise
        except (IntegrityError, SQLAlchemyError) as exc:
            raise AgenticStoreError("Agent attempt start failed") from exc

    def view(self, context: RunAuthorityContextV1) -> CandidateWorkspaceView:
        try:
            with Session(self.engine) as session:
                row = session.get(StudioAgentAttemptRow, context.attempt_id)
                if row is None:
                    raise AgenticStoreError("Agent attempt is unavailable")
                state = _state_from_payload(
                    row.state_payload,
                    model_turns=self._turns(session, context.attempt_id),
                )
                InMemoryAgentCheckpointStore._assert_authority(state, context)
                return _view(state)
        except AgenticStoreError:
            raise
        except SQLAlchemyError as exc:
            raise AgenticStoreError("Agent attempt read failed") from exc

    def activity(self, attempt_id: str) -> AgentAttemptActivityV1:
        try:
            with Session(self.engine) as session:
                row = session.get(StudioAgentAttemptRow, attempt_id)
                if row is None:
                    raise AgenticStoreError("Agent attempt is unavailable")
                state = _state_from_payload(row.state_payload)
                counts: dict[str, int] = {}
                for operation in state.operations.values():
                    counts[operation.collection] = counts.get(operation.collection, 0) + 1
                last_tool = session.scalar(
                    select(StudioAgentToolReceiptRow.tool_name)
                    .where(StudioAgentToolReceiptRow.attempt_id == attempt_id)
                    .order_by(StudioAgentToolReceiptRow.step_sequence.desc())
                    .limit(1)
                )
                model_turn_count = len(self._turns(session, attempt_id))
                tool_call_count = len(
                    session.scalars(
                        select(StudioAgentToolReceiptRow.receipt_id).where(
                            StudioAgentToolReceiptRow.attempt_id == attempt_id
                        )
                    ).all()
                )
                return AgentAttemptActivityV1(
                    attempt_id=attempt_id,
                    candidate_revision=state.candidate_revision,
                    candidate_count=len(state.operations),
                    candidate_collection_counts=counts,
                    model_turn_count=model_turn_count,
                    tool_call_count=tool_call_count,
                    activity_stage=_activity_stage(last_tool, len(state.operations)),
                    updated_at=row.updated_at,
                )
        except AgenticStoreError:
            raise
        except SQLAlchemyError as exc:
            raise AgenticStoreError("Agent attempt activity read failed") from exc

    def get_tool_receipt(
        self, context: RunAuthorityContextV1, invocation: ToolInvocationV1
    ) -> ToolInvocationReceiptV1 | None:
        try:
            with Session(self.engine) as session:
                attempt = session.get(StudioAgentAttemptRow, context.attempt_id)
                if attempt is None:
                    raise AgenticStoreError("Agent attempt is unavailable")
                state = _state_from_payload(attempt.state_payload)
                InMemoryAgentCheckpointStore._assert_authority(state, context)
                row = session.scalar(
                    select(StudioAgentToolReceiptRow).where(
                        StudioAgentToolReceiptRow.attempt_id == context.attempt_id,
                        StudioAgentToolReceiptRow.tool_call_id == invocation.tool_call_id,
                    )
                )
                if row is None:
                    return None
                receipt = ToolInvocationReceiptV1.model_validate(row.payload)
                if (
                    receipt.tool_name != invocation.tool_name
                    or receipt.arguments_digest != invocation.arguments_digest
                ):
                    raise AgenticStoreConflict(
                        "Tool call ID was replayed with different arguments"
                    )
                return receipt
        except AgenticStoreError:
            raise
        except SQLAlchemyError as exc:
            raise AgenticStoreError("Agent tool receipt read failed") from exc

    @staticmethod
    def _apply_tool(
        state: _AttemptState,
        context: RunAuthorityContextV1,
        invocation: ToolInvocationV1,
        *,
        result: dict[str, object],
        expected_candidate_revision: int | None,
        mutation: CandidateMutationV1 | None,
        mutations: tuple[CandidateMutationV1, ...],
        obligation_dispositions: tuple[ObligationDispositionV1, ...],
        evidence_receipt: EvidenceReceiptV2 | None,
        clock: Callable[[], datetime],
    ) -> ToolInvocationReceiptV1:
        if mutation is not None and mutations:
            raise AgenticStoreConflict(
                "A tool execution cannot mix one mutation with a mutation patch"
            )
        all_mutations = (mutation,) if mutation is not None else mutations
        changes_candidate = bool(all_mutations) or bool(obligation_dispositions)
        if state.sealed_bundle is not None and changes_candidate:
            raise CandidateSealedError("Candidate Bundle is already sealed")
        if changes_candidate:
            mutation_revisions = {
                item.expected_candidate_revision for item in all_mutations
            }
            if len(mutation_revisions) > 1:
                raise AgenticStoreConflict(
                    "Candidate patch mutations must share one CAS revision"
                )
            expected = (
                next(iter(mutation_revisions))
                if mutation_revisions
                else expected_candidate_revision
            )
            if expected is None or expected != state.candidate_revision:
                raise AgenticStoreConflict("Candidate revision CAS failed")
        if evidence_receipt is not None:
            if (
                evidence_receipt.run_id != context.run_id
                or evidence_receipt.workspace_id != context.workspace_id
                or evidence_receipt.solution_id != context.solution_id
                or evidence_receipt.source_set_digest != context.source_set_digest
                or evidence_receipt.source_version_id
                not in context.selected_source_version_ids
            ):
                raise AgenticAuthorityError(
                    "Evidence receipt is outside the exact run source set"
                )
            state.evidence_receipts[evidence_receipt.receipt_id] = evidence_receipt
        if all_mutations:
            receipt_ids = {
                receipt_id
                for item in all_mutations
                for claim in item.claims
                for receipt_id in claim.evidence_receipt_ids
            }
            if not receipt_ids.issubset(state.evidence_receipts):
                raise AgenticStoreConflict(
                    "Candidate claim references an unavailable evidence receipt"
                )
            prospective = dict(state.operations)
            mutation_targets = [_target(item.operation) for item in all_mutations]
            if len(mutation_targets) != len(set(mutation_targets)):
                raise AgenticStoreConflict("Candidate patch contains duplicate targets")
            for item in all_mutations:
                prospective[_target(item.operation)] = item.operation
            apply_package_operations(
                state.base_package,
                tuple(prospective[key] for key in sorted(prospective)),
            )
            state.operations = prospective
            for item in all_mutations:
                state.claims_by_target[_target(item.operation)] = item.claims
        obligation_ids = {item.obligation_id for item in state.objective.obligations}
        for disposition in obligation_dispositions:
            if disposition.obligation_id not in obligation_ids:
                raise AgenticStoreConflict(
                    "Model cannot introduce or replace frozen obligations"
                )
            for target in disposition.candidate_targets:
                if target not in state.operations:
                    raise AgenticStoreConflict(
                        "Obligation disposition references a missing candidate"
                    )
            state.dispositions[disposition.obligation_id] = disposition
        before = state.candidate_revision
        if changes_candidate:
            state.candidate_revision += 1
        state.step_sequence += 1
        return ToolInvocationReceiptV1(
            receipt_id="tool-receipt." + uuid.uuid4().hex,
            job_id=context.job_id,
            run_id=context.run_id,
            attempt_id=context.attempt_id,
            lease_epoch=context.lease_epoch,
            step_sequence=state.step_sequence,
            tool_call_id=invocation.tool_call_id,
            tool_name=invocation.tool_name,
            arguments_digest=invocation.arguments_digest,
            mutating=changes_candidate,
            candidate_revision_before=before,
            candidate_revision_after=state.candidate_revision,
            result=result,
            result_digest=sha256_value(result),
            committed_at=clock(),
        )

    def commit_tool_execution(
        self,
        context: RunAuthorityContextV1,
        invocation: ToolInvocationV1,
        *,
        result: dict[str, object],
        expected_candidate_revision: int | None = None,
        mutation: CandidateMutationV1 | None = None,
        mutations: tuple[CandidateMutationV1, ...] = (),
        obligation_dispositions: tuple[ObligationDispositionV1, ...] = (),
        evidence_receipt: EvidenceReceiptV2 | None = None,
    ) -> ToolInvocationReceiptV1:
        try:
            with Session(self.engine) as session, session.begin():
                row, state = self._locked_state(session, context)
                existing_row = session.scalar(
                    select(StudioAgentToolReceiptRow).where(
                        StudioAgentToolReceiptRow.attempt_id == context.attempt_id,
                        StudioAgentToolReceiptRow.tool_call_id == invocation.tool_call_id,
                    )
                )
                if existing_row is not None:
                    existing = ToolInvocationReceiptV1.model_validate(existing_row.payload)
                    if (
                        existing.tool_name != invocation.tool_name
                        or existing.arguments_digest != invocation.arguments_digest
                    ):
                        raise AgenticStoreConflict(
                            "Tool call ID was replayed with different arguments"
                        )
                    return existing
                receipt = self._apply_tool(
                    state,
                    context,
                    invocation,
                    result=result,
                    expected_candidate_revision=expected_candidate_revision,
                    mutation=mutation,
                    mutations=mutations,
                    obligation_dispositions=obligation_dispositions,
                    evidence_receipt=evidence_receipt,
                    clock=self.clock,
                )
                now = receipt.committed_at
                self._persist(row, state, now)
                session.add(
                    StudioAgentToolReceiptRow(
                        receipt_id=receipt.receipt_id,
                        attempt_id=context.attempt_id,
                        lease_epoch=context.lease_epoch,
                        step_sequence=receipt.step_sequence,
                        tool_call_id=invocation.tool_call_id,
                        tool_name=invocation.tool_name,
                        arguments_digest=invocation.arguments_digest,
                        payload=receipt.model_dump(mode="json"),
                        committed_at=now,
                    )
                )
                session.flush()
                return receipt
        except AgenticStoreError:
            raise
        except (IntegrityError, SQLAlchemyError) as exc:
            raise AgenticStoreError("Agent tool execution commit failed") from exc

    def commit_model_turn(
        self,
        context: RunAuthorityContextV1,
        request: AgentTurnRequestV1,
        result: AgentTurnResultV1,
    ) -> AgentModelTurnReceiptV1:
        if result.request_digest != request.request_digest:
            raise AgenticStoreConflict("Model result does not match its request")
        try:
            with Session(self.engine) as session, session.begin():
                row, state = self._locked_state(session, context)
                existing_row = session.scalar(
                    select(StudioAgentModelTurnRow).where(
                        StudioAgentModelTurnRow.attempt_id == context.attempt_id,
                        StudioAgentModelTurnRow.request_digest == request.request_digest,
                    )
                )
                if existing_row is not None:
                    existing = AgentModelTurnReceiptV1.model_validate(existing_row.payload)
                    if existing.result != result:
                        raise AgenticStoreConflict(
                            "Model request digest already names another result"
                        )
                    return existing
                state.step_sequence += 1
                receipt = AgentModelTurnReceiptV1(
                    turn_id="agent-turn." + uuid.uuid4().hex,
                    job_id=context.job_id,
                    run_id=context.run_id,
                    attempt_id=context.attempt_id,
                    lease_epoch=context.lease_epoch,
                    step_sequence=state.step_sequence,
                    request=request,
                    result=result,
                    committed_at=self.clock(),
                )
                state.model_turns.append(receipt)
                self._persist(row, state, receipt.committed_at)
                session.add(
                    StudioAgentModelTurnRow(
                        turn_id=receipt.turn_id,
                        attempt_id=context.attempt_id,
                        lease_epoch=context.lease_epoch,
                        step_sequence=receipt.step_sequence,
                        request_digest=request.request_digest,
                        payload=receipt.model_dump(mode="json"),
                        committed_at=receipt.committed_at,
                    )
                )
                session.flush()
                return receipt
        except AgenticStoreError:
            raise
        except (IntegrityError, SQLAlchemyError) as exc:
            raise AgenticStoreError("Agent model turn commit failed") from exc

    def seal(
        self,
        context: RunAuthorityContextV1,
        *,
        prospective_package_checksum: str,
        validator_report_digests: tuple[str, ...],
    ) -> CandidateBundleV2:
        try:
            with Session(self.engine) as session, session.begin():
                row, state = self._locked_state(session, context)
                if state.sealed_bundle is not None:
                    if (
                        state.sealed_bundle.prospective_package_checksum
                        != prospective_package_checksum
                        or state.sealed_bundle.validator_report_digests
                        != validator_report_digests
                    ):
                        raise CandidateSealedError(
                            "Attempt is already sealed with another exact result"
                        )
                    return state.sealed_bundle
                unresolved = [
                    item.obligation_id
                    for item in state.dispositions.values()
                    if item.disposition == "UNRESOLVED"
                ]
                if unresolved:
                    raise AgenticStoreConflict(
                        "Cannot seal while frozen obligations are unresolved"
                    )
                unsigned: dict[str, object] = {
                    "contract": "studio-candidate-bundle/v2",
                    "bundle_id": "candidate-bundle." + uuid.uuid4().hex,
                    "run_id": context.run_id,
                    "attempt_id": context.attempt_id,
                    "objective_checksum": state.objective.objective_checksum,
                    "candidate_revision": state.candidate_revision,
                    "operations": [
                        state.operations[key].model_dump(mode="json")
                        for key in sorted(state.operations)
                    ],
                    "claims_by_target": {
                        key: [item.model_dump(mode="json") for item in value]
                        for key, value in sorted(state.claims_by_target.items())
                    },
                    "obligation_dispositions": [
                        state.dispositions[item.obligation_id].model_dump(mode="json")
                        for item in state.objective.obligations
                    ],
                    "evidence_receipt_ids": sorted(state.evidence_receipts),
                    "prospective_package_checksum": prospective_package_checksum,
                    "validator_report_digests": list(validator_report_digests),
                    "sealed_at": self.clock().isoformat().replace("+00:00", "Z"),
                }
                unsigned["bundle_checksum"] = sha256_value(unsigned)
                state.sealed_bundle = CandidateBundleV2.model_validate(unsigned)
                self._persist(row, state, self.clock())
                session.flush()
                return state.sealed_bundle
        except AgenticStoreError:
            raise
        except SQLAlchemyError as exc:
            raise AgenticStoreError("Candidate Bundle seal failed") from exc
