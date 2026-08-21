from __future__ import annotations

import fcntl
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..io import sha256_value, write_json
from .intake import IntakeError, SourceAnchor
from .workspace import (
    DraftUpdate,
    DraftWorkspace,
    DraftWorkspaceService,
    EligibilityUpdate,
    REFERENCE_WORKSPACE_ID,
    WorkspaceConflictError,
)


class StudioLLMError(RuntimeError):
    pass


class StudioObservationConflict(StudioLLMError):
    pass


class StudioLLMModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SemanticSlotDefinition(StudioLLMModel):
    slot_id: str = Field(min_length=1)
    draft_path: str = Field(min_length=1)
    source_field: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_.-]*$")
    value_kind: Literal["STRING", "BOOLEAN", "STRING_LIST"]
    required: bool
    allowed_values: tuple[str, ...] = ()


class SemanticSlotManifest(StudioLLMModel):
    contract: Literal["semantic-slot-manifest/v1"]
    manifest_id: str = Field(pattern=r"^slots\.studio\.[A-Za-z0-9._-]+$")
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    slots: tuple[SemanticSlotDefinition, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def closed_package_denominator(self) -> SemanticSlotManifest:
        if len({item.slot_id for item in self.slots}) != len(self.slots):
            raise ValueError("Semantic slot ids must be unique")
        if len({item.draft_path for item in self.slots}) != len(self.slots):
            raise ValueError("Semantic slot draft paths must be unique")
        return self


class StudioRunProfile(StudioLLMModel):
    contract: Literal["studio-engineering-run-profile/v1"]
    profile_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    provider: Literal["qwen"]
    requested_model: Literal["qwen3.8-max"]
    accepted_response_models: tuple[Literal["qwen3.8-max"], ...] = Field(
        min_length=1, max_length=1
    )
    provider_account_ref: str = Field(min_length=1)
    endpoint_ref: str = Field(min_length=1)
    region: Literal["cn-beijing"]
    slot_manifest_path: Literal["semantic-slot-manifest.json"]
    prompt_manifest_path: Literal["prompts.json"]
    prompt_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    projection_policy_path: Literal["projection-policy.json"]
    projection_policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    absolute_timeout_ms: int = Field(ge=1000, le=30000)
    provider_timeout_ms: int = Field(ge=500, le=25000)
    max_input_tokens: int = Field(ge=1, le=5000)
    max_output_tokens: int = Field(ge=1, le=2000)
    temperature: Literal[0]
    thinking: Literal[False]
    trace_policy: Literal["safe-metadata-no-raw-response/v1"]


class StudioEgressDecision(StudioLLMModel):
    contract: Literal["studio-model-egress-decision/v1"]
    decision_id: str = Field(pattern=r"^egress\.studio\.[A-Za-z0-9._-]+$")
    decision: Literal["ALLOW", "DENY"]
    product: Literal["ontology-studio"]
    task: Literal["adt-observation-tracer"]
    provider: Literal["qwen"]
    provider_account_ref: str = Field(min_length=1)
    endpoint_ref: str = Field(min_length=1)
    region: Literal["cn-beijing"]
    classification: Literal["constructed_synthetic"]
    intake_submission_id: Literal["submission.reference.adt.v1"]
    profile_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    slot_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    allowed_projection_contract: Literal["studio-cleared-input-projection/v1"]
    approved_by: str = Field(min_length=1)
    issued_at: datetime
    expires_at: datetime

    def permits(
        self,
        *,
        profile: StudioRunProfile,
        slot_manifest: SemanticSlotManifest,
        intake_submission_id: str,
        now: datetime | None = None,
    ) -> bool:
        instant = now or datetime.now(timezone.utc)
        return (
            self.decision == "ALLOW"
            and self.provider == profile.provider
            and self.provider_account_ref == profile.provider_account_ref
            and self.endpoint_ref == profile.endpoint_ref
            and self.region == profile.region
            and self.profile_digest == sha256_value(profile)
            and self.slot_manifest_digest == sha256_value(slot_manifest)
            and self.intake_submission_id == intake_submission_id
            and self.issued_at <= instant < self.expires_at
        )


class StudioEvaluationSecurityGates(StudioLLMModel):
    closed_projection_only: Literal[True] = True
    wrong_source_anchor_blocked: Literal[True] = True
    incomplete_slot_denominator_blocked: Literal[True] = True
    stale_draft_write_blocked: Literal[True] = True
    human_only_draft_mutation: Literal[True] = True
    model_publish_route_absent: Literal[True] = True


class StudioEvaluationManifest(StudioLLMModel):
    contract: Literal["studio-evaluation-manifest/v1"]
    manifest_id: Literal["eval-manifest.studio.adt.v1"]
    demo_class: Literal["STUDIO_LLM_ENGINEERING_DEMO"]
    profile_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    slot_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    egress_decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider: Literal["qwen"]
    requested_model: Literal["qwen3.8-max"]
    response_model: Literal["qwen3.8-max"]
    observed_slot_ids: tuple[str, ...] = Field(min_length=5, max_length=5)
    observation_count: Literal[5]
    security_gates: StudioEvaluationSecurityGates
    raw_content_retained: Literal[False]
    evaluated_at: datetime
    approved_by: str = Field(min_length=1)

    def permits(
        self,
        *,
        profile: StudioRunProfile,
        slot_manifest: SemanticSlotManifest,
        egress: StudioEgressDecision,
        rollout_approved_by: str,
        rollout_issued_at: datetime,
    ) -> bool:
        expected_slots = tuple(item.slot_id for item in slot_manifest.slots)
        return (
            self.profile_digest == sha256_value(profile)
            and self.slot_manifest_digest == sha256_value(slot_manifest)
            and self.egress_decision_digest == sha256_value(egress)
            and self.provider == profile.provider == egress.provider
            and self.requested_model == profile.requested_model
            and self.response_model in profile.accepted_response_models
            and self.observed_slot_ids == expected_slots
            and self.observation_count == len(expected_slots)
            and self.approved_by == rollout_approved_by
            and self.evaluated_at <= rollout_issued_at
        )


class StudioRolloutRecord(StudioLLMModel):
    contract: Literal["studio-task-rollout-record/v1"]
    rollout_id: Literal["rollout.studio.adt.qwen.demo.v1"]
    task: Literal["adt-observation-tracer"]
    mode: Literal["shadow", "active-observation-canary"]
    epoch: int = Field(ge=1)
    status: Literal["ACTIVE", "OFF"]
    profile_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    slot_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    egress_decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluation_manifest_ref: Literal["eval-manifest.studio.adt.v1"] | None = None
    evaluation_manifest_digest: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    approved_by: str = Field(min_length=1)
    issued_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def active_canary_requires_evaluation(self) -> StudioRolloutRecord:
        if self.mode == "active-observation-canary" and (
            self.evaluation_manifest_ref is None
            or self.evaluation_manifest_digest is None
        ):
            raise ValueError("Active Studio rollout requires an evaluation manifest")
        if (self.evaluation_manifest_ref is None) != (
            self.evaluation_manifest_digest is None
        ):
            raise ValueError("Studio evaluation manifest ref and digest must be paired")
        return self

    def permits(
        self,
        *,
        profile: StudioRunProfile,
        slot_manifest: SemanticSlotManifest,
        egress: StudioEgressDecision,
        evaluation: StudioEvaluationManifest | None,
        now: datetime | None = None,
    ) -> bool:
        instant = now or datetime.now(timezone.utc)
        exact_base = (
            self.status == "ACTIVE"
            and self.profile_digest == sha256_value(profile)
            and self.slot_manifest_digest == sha256_value(slot_manifest)
            and self.egress_decision_digest == sha256_value(egress)
            and self.issued_at <= instant < self.expires_at
        )
        if not exact_base:
            return False
        if self.mode == "shadow":
            return evaluation is None
        return (
            evaluation is not None
            and self.evaluation_manifest_ref == evaluation.manifest_id
            and self.evaluation_manifest_digest == sha256_value(evaluation)
            and evaluation.permits(
                profile=profile,
                slot_manifest=slot_manifest,
                egress=egress,
                rollout_approved_by=self.approved_by,
                rollout_issued_at=self.issued_at,
            )
        )


class StudioSlotValue(StudioLLMModel):
    kind: Literal["STRING", "BOOLEAN", "STRING_LIST"]
    string_value: str | None = None
    boolean_value: bool | None = None
    string_list_value: tuple[str, ...] | None = None

    @model_validator(mode="after")
    def one_typed_value(self) -> StudioSlotValue:
        populated = sum(
            item is not None
            for item in (
                self.string_value,
                self.boolean_value,
                self.string_list_value,
            )
        )
        if populated != 1:
            raise ValueError("A Studio slot value must contain exactly one typed value")
        if self.kind == "STRING" and (
            self.string_value is None or not self.string_value.strip()
        ):
            raise ValueError("STRING requires a non-empty string_value")
        if self.kind == "BOOLEAN" and self.boolean_value is None:
            raise ValueError("BOOLEAN requires boolean_value")
        if self.kind == "STRING_LIST" and (
            not self.string_list_value
            or len(set(self.string_list_value)) != len(self.string_list_value)
        ):
            raise ValueError("STRING_LIST requires a non-empty unique list")
        if self.kind != "STRING" and self.string_value is not None:
            raise ValueError("string_value is not allowed for this kind")
        if self.kind != "BOOLEAN" and self.boolean_value is not None:
            raise ValueError("boolean_value is not allowed for this kind")
        if self.kind != "STRING_LIST" and self.string_list_value is not None:
            raise ValueError("string_list_value is not allowed for this kind")
        return self

    def python_value(self) -> str | bool | tuple[str, ...]:
        if self.kind == "STRING":
            assert self.string_value is not None
            return self.string_value
        if self.kind == "BOOLEAN":
            assert self.boolean_value is not None
            return self.boolean_value
        assert self.string_list_value is not None
        return self.string_list_value


class StudioSourceFragment(StudioLLMModel):
    asset_id: str = Field(min_length=1)
    locator: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=2000)
    checksum: str = Field(pattern=r"^[0-9a-f]{64}$")


class StudioProjectionSlot(StudioLLMModel):
    slot_id: str
    draft_path: str
    value_kind: Literal["STRING", "BOOLEAN", "STRING_LIST"]
    required: bool
    allowed_values: tuple[str, ...]
    current_value: StudioSlotValue
    source_fragment: StudioSourceFragment | None


class StudioClearedInputProjection(StudioLLMModel):
    contract: Literal["studio-cleared-input-projection/v1"]
    workspace_id: Literal["workspace.adt.reference"]
    base_revision: int = Field(ge=1)
    base_draft_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    intake_submission_id: Literal["submission.reference.adt.v1"]
    intake_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    claim_ceiling: Literal["CONSTRUCTED_SYNTHETIC_NOT_HKEX_VALIDATED"]
    slots: tuple[StudioProjectionSlot, ...] = Field(min_length=5, max_length=5)
    declared_gap_ids: tuple[str, ...]


class StudioObservationRequest(StudioLLMModel):
    contract: Literal["studio-observation-request/v1"]
    run_id: str = Field(pattern=r"^studio-run\.[0-9a-f]{32}$")
    profile_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    slot_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    egress_decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    projection_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    deadline_at: datetime
    projection: StudioClearedInputProjection


class StudioObservationCandidate(StudioLLMModel):
    slot_id: str
    status: Literal["PROPOSED", "MISSING"]
    support_code: Literal["DIRECT_SOURCE", "MISSING_SOURCE"]
    source_fragment_checksum: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    value: StudioSlotValue | None = None

    @model_validator(mode="after")
    def status_matches_support(self) -> StudioObservationCandidate:
        if self.status == "PROPOSED" and (
            self.support_code != "DIRECT_SOURCE"
            or self.source_fragment_checksum is None
            or self.value is None
        ):
            raise ValueError("PROPOSED requires direct source support and a value")
        if self.status == "MISSING" and (
            self.support_code != "MISSING_SOURCE"
            or self.source_fragment_checksum is not None
            or self.value is not None
        ):
            raise ValueError("MISSING cannot carry a source claim or value")
        return self


class StudioObservationCandidateSet(StudioLLMModel):
    contract: Literal["studio-observation-candidate-set/v1"]
    run_id: str = Field(pattern=r"^studio-run\.[0-9a-f]{32}$")
    requested_model: Literal["qwen3.8-max"]
    response_model: Literal["qwen3.8-max"]
    provider_request_id: str = Field(min_length=1)
    observations: tuple[StudioObservationCandidate, ...] = Field(
        min_length=5, max_length=5
    )


class StudioObservationPayload(StudioLLMModel):
    contract: Literal["studio-observation-payload/v1"]
    observations: tuple[StudioObservationCandidate, ...] = Field(
        min_length=5, max_length=5
    )


class StudioObservation(StudioLLMModel):
    observation_id: str = Field(pattern=r"^observation\.[0-9a-f]{32}\.[0-9]{2}$")
    slot_id: str
    status: Literal["PROPOSED", "MISSING"]
    support_code: Literal["DIRECT_SOURCE", "MISSING_SOURCE"]
    value: StudioSlotValue | None
    source_anchor: SourceAnchor | None
    source_fragment_checksum: str | None


class StudioObservationSet(StudioLLMModel):
    contract: Literal["studio-observation-set/v1"]
    observation_set_id: str = Field(pattern=r"^observation-set\.[0-9a-f]{32}$")
    run_id: str = Field(pattern=r"^studio-run\.[0-9a-f]{32}$")
    workspace_id: Literal["workspace.adt.reference"]
    base_revision: int = Field(ge=1)
    base_draft_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    intake_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    slot_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    egress_decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    projection_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    requested_model: Literal["qwen3.8-max"]
    response_model: Literal["qwen3.8-max"]
    provider_request_id: str
    created_at: datetime
    projection: StudioClearedInputProjection
    observations: tuple[StudioObservation, ...] = Field(min_length=5, max_length=5)
    observation_set_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")


class StudioObservationDisposition(StudioLLMModel):
    observation_id: str = Field(pattern=r"^observation\.[0-9a-f]{32}\.[0-9]{2}$")
    action: Literal["ACCEPT", "EDIT", "REJECT"]
    reason_code: Literal[
        "SOURCE_SUPPORTED",
        "REVIEWER_CORRECTION",
        "NOT_SUPPORTED",
        "KEEP_MISSING",
    ]
    edited_value: StudioSlotValue | None = None

    @model_validator(mode="after")
    def action_matches_value_and_reason(self) -> StudioObservationDisposition:
        if self.action == "ACCEPT" and (
            self.edited_value is not None or self.reason_code != "SOURCE_SUPPORTED"
        ):
            raise ValueError("ACCEPT uses the proposed value and SOURCE_SUPPORTED")
        if self.action == "EDIT" and (
            self.edited_value is None or self.reason_code != "REVIEWER_CORRECTION"
        ):
            raise ValueError("EDIT requires a reviewer correction")
        if self.action == "REJECT" and (
            self.edited_value is not None
            or self.reason_code not in {"NOT_SUPPORTED", "KEEP_MISSING"}
        ):
            raise ValueError("REJECT cannot carry a replacement value")
        return self


class StudioReviewDecision(StudioLLMModel):
    contract: Literal["studio-observation-review-decision/v1"]
    decision_id: str = Field(pattern=r"^studio-decision\.[0-9a-f]{32}$")
    observation_set_id: str = Field(pattern=r"^observation-set\.[0-9a-f]{32}$")
    observation_set_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    workspace_id: Literal["workspace.adt.reference"]
    base_revision: int = Field(ge=1)
    base_draft_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewer: str = Field(min_length=1)
    dispositions: tuple[StudioObservationDisposition, ...] = Field(
        min_length=5, max_length=5
    )
    review_request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["APPLIED", "REVIEWED_NO_CHANGE"]
    resulting_revision: int = Field(ge=1)
    resulting_draft_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    decided_at: datetime
    decision_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")


class StudioReviewResult(StudioLLMModel):
    decision: StudioReviewDecision
    workspace: DraftWorkspace


StudioModelBoundary = Callable[[dict[str, object], float], dict[str, object]]


def _load_model(path: Path, model: type[StudioLLMModel]) -> Any:
    try:
        return model.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise StudioLLMError(f"Invalid Studio LLM artifact: {path.name}") from exc


def load_studio_run_profile(path: Path) -> StudioRunProfile:
    profile = _load_model(path, StudioRunProfile)
    try:
        prompt = json.loads(
            (path.parent / profile.prompt_manifest_path).read_text(encoding="utf-8")
        )
        policy = json.loads(
            (path.parent / profile.projection_policy_path).read_text(encoding="utf-8")
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise StudioLLMError("Invalid Studio LLM profile dependency") from exc
    if (
        sha256_value(prompt) != profile.prompt_manifest_digest
        or sha256_value(policy) != profile.projection_policy_digest
    ):
        raise StudioLLMError("Studio LLM profile dependency digest mismatch")
    return profile


def load_semantic_slot_manifest(path: Path) -> SemanticSlotManifest:
    return _load_model(path, SemanticSlotManifest)


def load_studio_egress_decision(path: Path) -> StudioEgressDecision:
    return _load_model(path, StudioEgressDecision)


def load_studio_evaluation_manifest(path: Path) -> StudioEvaluationManifest:
    return _load_model(path, StudioEvaluationManifest)


def load_studio_rollout_record(path: Path) -> StudioRolloutRecord:
    return _load_model(path, StudioRolloutRecord)


class StudioObservationService:
    """Deep boundary for safe projection, immutable observations and later review."""

    def __init__(
        self,
        *,
        root: Path,
        workspace: DraftWorkspaceService,
        profile: StudioRunProfile,
        slot_manifest: SemanticSlotManifest,
        egress: StudioEgressDecision,
        rollout: StudioRolloutRecord,
        evaluation: StudioEvaluationManifest | None,
        model_boundary: StudioModelBoundary,
    ):
        self.root = root.resolve()
        self.workspace = workspace
        self.profile = profile
        self.slot_manifest = slot_manifest
        self.egress = egress
        self.rollout = rollout
        self.evaluation = evaluation
        self.model_boundary = model_boundary

    def _path(self, observation_set_id: str) -> Path:
        if not observation_set_id.startswith("observation-set."):
            raise StudioLLMError("Invalid observation set id")
        return self.root / "observation-sets" / f"{observation_set_id}.json"

    def _decision_path(self, observation_set_id: str) -> Path:
        if not observation_set_id.startswith("observation-set."):
            raise StudioLLMError("Invalid observation set id")
        return self.root / "decisions" / f"{observation_set_id}.json"

    @staticmethod
    def _slot_value(workspace: DraftWorkspace, slot_id: str) -> StudioSlotValue:
        if slot_id == "metric.definition":
            return StudioSlotValue(
                kind="STRING", string_value=workspace.draft.metric_definition
            )
        if slot_id == "eligibility.include_status":
            return StudioSlotValue(
                kind="STRING",
                string_value=workspace.draft.eligibility_rule.include_status,
            )
        if slot_id == "eligibility.exclude_cancelled":
            return StudioSlotValue(
                kind="BOOLEAN",
                boolean_value=workspace.draft.eligibility_rule.exclude_cancelled,
            )
        if slot_id == "metric.allowed_dimensions":
            return StudioSlotValue(
                kind="STRING_LIST",
                string_list_value=workspace.draft.allowed_dimensions,
            )
        if slot_id == "mapping.amount":
            return StudioSlotValue(
                kind="STRING", string_value=workspace.draft.amount_mapping
            )
        raise StudioLLMError("Unknown semantic slot")

    def _projection(self, workspace: DraftWorkspace) -> StudioClearedInputProjection:
        intake = self.workspace.get_intake(workspace.workspace_id)
        anchors = {item.field: item for item in intake.anchors}
        slots: list[StudioProjectionSlot] = []
        for definition in self.slot_manifest.slots:
            anchor = anchors.get(definition.source_field)
            fragment = None
            if anchor is not None:
                try:
                    text = self.workspace.intake.project_anchor_text(intake, anchor)
                except IntakeError as exc:
                    raise StudioLLMError("Cleared input projection failed") from exc
                if text:
                    unsigned = {
                        "asset_id": anchor.asset_id,
                        "locator": anchor.locator,
                        "text": text,
                    }
                    fragment = StudioSourceFragment(
                        **unsigned,
                        checksum=sha256_value(unsigned),
                    )
            slots.append(
                StudioProjectionSlot(
                    slot_id=definition.slot_id,
                    draft_path=definition.draft_path,
                    value_kind=definition.value_kind,
                    required=definition.required,
                    allowed_values=definition.allowed_values,
                    current_value=self._slot_value(workspace, definition.slot_id),
                    source_fragment=fragment,
                )
            )
        return StudioClearedInputProjection(
            contract="studio-cleared-input-projection/v1",
            workspace_id=workspace.workspace_id,
            base_revision=workspace.revision,
            base_draft_checksum=workspace.draft_checksum,
            intake_submission_id=intake.submission_id,
            intake_checksum=intake.content_checksum,
            claim_ceiling=intake.claim_ceiling,
            slots=tuple(slots),
            declared_gap_ids=tuple(item.gap_id for item in intake.gaps),
        )

    @staticmethod
    def _validate_value(
        definition: SemanticSlotDefinition,
        value: StudioSlotValue,
    ) -> None:
        if value.kind != definition.value_kind:
            raise StudioLLMError("Observation value kind does not match its slot")
        python_value = value.python_value()
        if definition.allowed_values:
            values = (
                python_value
                if isinstance(python_value, tuple)
                else (python_value,)
            )
            if any(item not in definition.allowed_values for item in values):
                raise StudioLLMError("Observation value is outside the slot allowlist")

    def generate(self, *, expected_revision: int) -> StudioObservationSet:
        self.root.mkdir(parents=True, exist_ok=True)
        lock_path = self.root / "observation-generation.lock"
        with lock_path.open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                return self._generate_locked(expected_revision=expected_revision)
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _generate_locked(self, *, expected_revision: int) -> StudioObservationSet:
        base = self.workspace.get(REFERENCE_WORKSPACE_ID)
        if base.revision != expected_revision:
            raise WorkspaceConflictError("Draft revision conflict")
        if not self.rollout.permits(
            profile=self.profile,
            slot_manifest=self.slot_manifest,
            egress=self.egress,
            evaluation=self.evaluation,
        ):
            raise StudioLLMError("Studio model rollout is not allowed")
        if not self.egress.permits(
            profile=self.profile,
            slot_manifest=self.slot_manifest,
            intake_submission_id=base.intake_submission_id,
        ):
            raise StudioLLMError("Studio model egress is not allowed")
        pending = tuple(
            item
            for item in self.list_for_workspace(base.workspace_id)
            if item.base_revision == base.revision
            and item.base_draft_checksum == base.draft_checksum
            and self.decision_for(item.observation_set_id) is None
        )
        if len(pending) > 1:
            raise StudioObservationConflict(
                "The exact draft has multiple pending observation sets"
            )
        if pending:
            return pending[0]
        projection = self._projection(base)
        run_id = "studio-run." + uuid.uuid4().hex
        request = StudioObservationRequest(
            contract="studio-observation-request/v1",
            run_id=run_id,
            profile_digest=sha256_value(self.profile),
            slot_manifest_digest=sha256_value(self.slot_manifest),
            egress_decision_digest=sha256_value(self.egress),
            projection_digest=sha256_value(projection),
            deadline_at=datetime.now(timezone.utc)
            + timedelta(milliseconds=self.profile.absolute_timeout_ms),
            projection=projection,
        )
        raw = self.model_boundary(
            request.model_dump(mode="json"),
            self.profile.provider_timeout_ms / 1000,
        )
        try:
            candidate_set = StudioObservationCandidateSet.model_validate(raw)
        except ValueError as exc:
            raise StudioLLMError("Studio model response violates the closed schema") from exc
        if candidate_set.run_id != run_id:
            raise StudioLLMError("Studio model response run identity mismatch")
        expected_ids = tuple(item.slot_id for item in self.slot_manifest.slots)
        if tuple(item.slot_id for item in candidate_set.observations) != expected_ids:
            raise StudioLLMError("Studio model response does not close the slot denominator")

        projection_slots = {item.slot_id: item for item in projection.slots}
        definitions = {item.slot_id: item for item in self.slot_manifest.slots}
        observation_nonce = uuid.uuid4().hex
        observations: list[StudioObservation] = []
        for index, candidate in enumerate(candidate_set.observations, start=1):
            projected = projection_slots[candidate.slot_id]
            definition = definitions[candidate.slot_id]
            fragment = projected.source_fragment
            if fragment is None:
                if candidate.status != "MISSING":
                    raise StudioLLMError("A missing source cannot support a proposal")
                anchor = None
            else:
                if (
                    candidate.status == "PROPOSED"
                    and candidate.source_fragment_checksum != fragment.checksum
                ):
                    raise StudioLLMError("Observation source fragment checksum mismatch")
                anchor = SourceAnchor(
                    field=definition.source_field,
                    asset_id=fragment.asset_id,
                    locator=fragment.locator,
                )
            if candidate.value is not None:
                self._validate_value(definition, candidate.value)
            observations.append(
                StudioObservation(
                    observation_id=f"observation.{observation_nonce}.{index:02d}",
                    slot_id=candidate.slot_id,
                    status=candidate.status,
                    support_code=candidate.support_code,
                    value=candidate.value,
                    source_anchor=anchor,
                    source_fragment_checksum=candidate.source_fragment_checksum,
                )
            )

        current = self.workspace.get(REFERENCE_WORKSPACE_ID)
        if (
            current.revision != base.revision
            or current.draft_checksum != base.draft_checksum
        ):
            raise StudioObservationConflict(
                "The draft changed while observations were being generated"
            )
        set_id = "observation-set." + uuid.uuid4().hex
        unsigned = {
            "contract": "studio-observation-set/v1",
            "observation_set_id": set_id,
            "run_id": run_id,
            "workspace_id": base.workspace_id,
            "base_revision": base.revision,
            "base_draft_checksum": base.draft_checksum,
            "intake_checksum": base.intake_checksum,
            "profile_digest": sha256_value(self.profile),
            "slot_manifest_digest": sha256_value(self.slot_manifest),
            "egress_decision_digest": sha256_value(self.egress),
            "projection_digest": sha256_value(projection),
            "requested_model": candidate_set.requested_model,
            "response_model": candidate_set.response_model,
            "provider_request_id": candidate_set.provider_request_id,
            "created_at": datetime.now(timezone.utc),
            "projection": projection,
            "observations": tuple(observations),
        }
        provisional = StudioObservationSet(
            **unsigned,
            observation_set_checksum="0" * 64,
        )
        checksum_payload = provisional.model_dump(
            mode="json",
            exclude={"observation_set_checksum"},
            exclude_none=True,
        )
        observation_set = provisional.model_copy(
            update={"observation_set_checksum": sha256_value(checksum_payload)}
        )
        path = self._path(set_id)
        if path.exists():
            raise StudioObservationConflict("Observation set id collision")
        write_json(path, observation_set.model_dump(mode="json"))
        return observation_set

    def get(self, observation_set_id: str) -> StudioObservationSet:
        path = self._path(observation_set_id)
        try:
            observation_set = StudioObservationSet.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            raise StudioLLMError("Observation set is unavailable") from exc
        unsigned = observation_set.model_dump(
            mode="json",
            exclude={"observation_set_checksum"},
            exclude_none=True,
        )
        if sha256_value(unsigned) != observation_set.observation_set_checksum:
            raise StudioLLMError("Observation set checksum mismatch")
        return observation_set

    def list_for_workspace(
        self, workspace_id: str = REFERENCE_WORKSPACE_ID
    ) -> tuple[StudioObservationSet, ...]:
        if workspace_id != REFERENCE_WORKSPACE_ID:
            raise StudioLLMError("Only the fixed ADT workspace is supported")
        root = self.root / "observation-sets"
        if not root.exists():
            return ()
        return tuple(
            sorted(
                (self.get(path.stem) for path in root.glob("*.json")),
                key=lambda item: item.created_at,
                reverse=True,
            )
        )

    def decision_for(
        self, observation_set_id: str
    ) -> StudioReviewDecision | None:
        if not self._decision_path(observation_set_id).is_file():
            return None
        return self.get_decision(observation_set_id)

    def get_decision(self, observation_set_id: str) -> StudioReviewDecision:
        path = self._decision_path(observation_set_id)
        try:
            decision = StudioReviewDecision.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            raise StudioLLMError("Review decision is unavailable") from exc
        unsigned = decision.model_dump(
            mode="json", exclude={"decision_checksum"}, exclude_none=True
        )
        if sha256_value(unsigned) != decision.decision_checksum:
            raise StudioLLMError("Review decision checksum mismatch")
        return decision

    def review(
        self,
        observation_set_id: str,
        *,
        expected_revision: int,
        reviewer: str,
        dispositions: tuple[StudioObservationDisposition, ...],
    ) -> StudioReviewResult:
        observation_set = self.get(observation_set_id)
        current = self.workspace.get(observation_set.workspace_id)
        if (
            expected_revision != observation_set.base_revision
            or current.revision != expected_revision
            or current.draft_checksum != observation_set.base_draft_checksum
        ):
            raise WorkspaceConflictError(
                "The observation set is stale for the current draft"
            )
        observation_ids = tuple(item.observation_id for item in observation_set.observations)
        if tuple(item.observation_id for item in dispositions) != observation_ids:
            raise StudioLLMError("Every observation requires one ordered disposition")

        request_payload = {
            "observation_set_id": observation_set_id,
            "observation_set_checksum": observation_set.observation_set_checksum,
            "expected_revision": expected_revision,
            "reviewer": reviewer,
            "dispositions": dispositions,
        }
        request_digest = sha256_value(request_payload)
        decision_path = self._decision_path(observation_set_id)
        if decision_path.exists():
            existing = self.get_decision(observation_set_id)
            if existing.review_request_digest != request_digest:
                raise StudioObservationConflict(
                    "The observation set already has a different final decision"
                )
            return StudioReviewResult(decision=existing, workspace=current)

        definitions = {item.slot_id: item for item in self.slot_manifest.slots}
        metric_definition: str | None = None
        include_status: str | None = None
        exclude_cancelled: bool | None = None
        allowed_dimensions: tuple[str, ...] | None = None
        amount_mapping: str | None = None
        for observation, disposition in zip(
            observation_set.observations, dispositions, strict=True
        ):
            if observation.status == "MISSING" and disposition.action != "REJECT":
                raise StudioLLMError("A missing observation cannot be accepted or edited")
            if disposition.action == "REJECT":
                continue
            chosen = (
                disposition.edited_value
                if disposition.action == "EDIT"
                else observation.value
            )
            if chosen is None:
                raise StudioLLMError("The reviewed observation has no value")
            definition = definitions[observation.slot_id]
            self._validate_value(definition, chosen)
            value = chosen.python_value()
            if observation.slot_id == "metric.definition":
                assert isinstance(value, str)
                metric_definition = value
            elif observation.slot_id == "eligibility.include_status":
                assert isinstance(value, str)
                include_status = value
            elif observation.slot_id == "eligibility.exclude_cancelled":
                assert isinstance(value, bool)
                exclude_cancelled = value
            elif observation.slot_id == "metric.allowed_dimensions":
                assert isinstance(value, tuple)
                allowed_dimensions = value
            elif observation.slot_id == "mapping.amount":
                assert isinstance(value, str)
                amount_mapping = value

        eligibility_update = (
            EligibilityUpdate(
                include_status=include_status,
                exclude_cancelled=exclude_cancelled,
            )
            if include_status is not None or exclude_cancelled is not None
            else None
        )
        updated = self.workspace.patch(
            DraftUpdate(
                metric_definition=metric_definition,
                eligibility_rule=eligibility_update,
                allowed_dimensions=allowed_dimensions,
                amount_mapping=amount_mapping,
            ),
            expected_revision=expected_revision,
            workspace_id=observation_set.workspace_id,
        )
        unsigned = {
            "contract": "studio-observation-review-decision/v1",
            "decision_id": "studio-decision." + uuid.uuid4().hex,
            "observation_set_id": observation_set.observation_set_id,
            "observation_set_checksum": observation_set.observation_set_checksum,
            "workspace_id": observation_set.workspace_id,
            "base_revision": observation_set.base_revision,
            "base_draft_checksum": observation_set.base_draft_checksum,
            "reviewer": reviewer,
            "dispositions": dispositions,
            "review_request_digest": request_digest,
            "status": (
                "APPLIED" if updated.revision > current.revision else "REVIEWED_NO_CHANGE"
            ),
            "resulting_revision": updated.revision,
            "resulting_draft_checksum": updated.draft_checksum,
            "decided_at": datetime.now(timezone.utc),
        }
        provisional = StudioReviewDecision(
            **unsigned,
            decision_checksum="0" * 64,
        )
        checksum_payload = provisional.model_dump(
            mode="json", exclude={"decision_checksum"}, exclude_none=True
        )
        decision = provisional.model_copy(
            update={"decision_checksum": sha256_value(checksum_payload)}
        )
        if decision_path.exists():
            raise StudioObservationConflict(
                "The observation set already has a final decision"
            )
        write_json(decision_path, decision.model_dump(mode="json"))
        return StudioReviewResult(decision=decision, workspace=updated)
