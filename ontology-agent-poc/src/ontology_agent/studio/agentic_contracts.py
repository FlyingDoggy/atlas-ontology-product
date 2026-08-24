from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import Field, model_validator

from ..contracts import Sha256
from ..io import sha256_value
from ..models import AuthoringLanguage, StrictModel
from .package_authoring import PackageCollection, PackageDraftOperation


AgentRole = Literal["system", "user", "assistant", "tool"]


class AgentEngineContractV2(StrictModel):
    """The immutable execution envelope frozen when a v2 job is enqueued."""

    contract: Literal["studio-agent-engine/v2"] = "studio-agent-engine/v2"
    engine_id: str = Field(pattern=r"^[a-z][a-z0-9._-]*$")
    engine_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    runtime_digest: Sha256
    provider: str = Field(min_length=1, max_length=100)
    requested_model: str = Field(min_length=1, max_length=255)
    model_config_digest: Sha256
    skill_id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    skill_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    skill_checksum: Sha256
    tool_registry_digest: Sha256
    tool_policy_digest: Sha256
    parser_contract_digest: Sha256
    source_set_digest: Sha256
    max_model_calls: int = Field(ge=1, le=500)
    max_tool_calls: int = Field(ge=1, le=1000)
    max_input_tokens: int = Field(ge=1)
    max_output_tokens: int = Field(ge=1)
    output_language: AuthoringLanguage
    objective_checksum: Sha256
    engine_checksum: Sha256

    @model_validator(mode="after")
    def checksum_matches(self) -> AgentEngineContractV2:
        unsigned = self.model_dump(mode="json", exclude={"engine_checksum"})
        if sha256_value(unsigned) != self.engine_checksum:
            raise ValueError("Agent engine contract checksum mismatch")
        return self


ObligationKind = Literal[
    "REQUIREMENT",
    "METRIC",
    "SEMANTIC_MODEL",
    "DATA_MAPPING",
    "SQL_CONTRACT",
    "SOURCE_COVERAGE",
]
ObligationDisposition = Literal[
    "UNRESOLVED",
    "CANDIDATE",
    "GAP",
    "UNSUPPORTED",
    "NOOP",
]


class MetricSemanticObligationV1(StrictModel):
    """Frozen, source-derived semantic contract for one requested metric.

    The shell may normalize machine identity and mechanically explicit output
    conventions.  It does not author the metric formula: the Builder still owns
    modeling and must reconcile this exact source contract with the other evidence.
    """

    contract: Literal["studio-metric-semantic-obligation/v1"] = (
        "studio-metric-semantic-obligation/v1"
    )
    source_metric_key: str = Field(min_length=1, max_length=100)
    expected_metric_id: str = Field(
        pattern=r"^metric\.[A-Za-z0-9][A-Za-z0-9._-]*$"
    )
    name: str = Field(min_length=1, max_length=500)
    definition: str = Field(min_length=1, max_length=10000)
    calculation_logic: str = Field(min_length=1, max_length=20000)
    filters_and_scope: str = Field(min_length=1, max_length=10000)
    grain_and_dimensions: str = Field(min_length=1, max_length=10000)
    output_instruction: str = Field(min_length=1, max_length=10000)
    null_and_zero_policy: str = Field(min_length=1, max_length=10000)
    primary_sources: str = Field(min_length=1, max_length=10000)
    expected_metric_type: Literal["base", "derived"] | None = None
    expected_value_type: Literal["integer", "decimal", "percentage"] | None = None
    expected_unit: str | None = Field(default=None, min_length=1, max_length=100)
    required_formula_root: str | None = Field(default=None, min_length=1, max_length=50)
    required_formula_operations: tuple[str, ...] = Field(default=(), max_length=16)
    required_formula_literals: tuple[Decimal, ...] = Field(default=(), max_length=16)
    required_referenced_units: tuple[str, ...] = Field(default=(), max_length=16)
    semantic_contract_checksum: Sha256

    @model_validator(mode="after")
    def contract_is_exact(self) -> MetricSemanticObligationV1:
        if len(self.required_formula_operations) != len(
            set(self.required_formula_operations)
        ):
            raise ValueError("Required metric operations must be unique")
        if len(self.required_formula_literals) != len(
            set(self.required_formula_literals)
        ):
            raise ValueError("Required metric literals must be unique")
        if len(self.required_referenced_units) != len(
            set(self.required_referenced_units)
        ):
            raise ValueError("Required referenced units must be unique")
        unsigned = self.model_dump(
            mode="json", exclude={"semantic_contract_checksum"}
        )
        if sha256_value(unsigned) != self.semantic_contract_checksum:
            raise ValueError("Metric semantic obligation checksum mismatch")
        return self


class BuildObligationV1(StrictModel):
    obligation_id: str = Field(pattern=r"^obligation\.[A-Za-z0-9][A-Za-z0-9._-]*$")
    kind: ObligationKind
    title: str = Field(min_length=1, max_length=500)
    source_version_ids: tuple[str, ...] = Field(min_length=1, max_length=64)
    source_locator: str = Field(min_length=1, max_length=1000)
    required_candidate_collections: tuple[PackageCollection, ...] = Field(
        default=(), max_length=18
    )
    metric_semantic_contract: MetricSemanticObligationV1 | None = None
    required: bool = True

    @model_validator(mode="after")
    def required_collections_are_unique(self) -> BuildObligationV1:
        if len(self.required_candidate_collections) != len(
            set(self.required_candidate_collections)
        ):
            raise ValueError("Required Candidate collections must be unique")
        if (self.kind == "METRIC") != (self.metric_semantic_contract is not None):
            # Aggregate METRIC closure obligations intentionally have no one-metric
            # contract; only reject a contract attached to the wrong obligation kind.
            if self.metric_semantic_contract is not None:
                raise ValueError(
                    "Metric semantic contracts belong only to METRIC obligations"
                )
        return self


class BuildObjectiveV1(StrictModel):
    contract: Literal["studio-build-objective/v1"] = "studio-build-objective/v1"
    objective_id: str = Field(pattern=r"^build-objective\.[0-9a-f]{32}$")
    solution_id: str = Field(min_length=1, max_length=255)
    workspace_id: str = Field(min_length=1, max_length=255)
    selected_source_version_ids: tuple[str, ...] = Field(min_length=1, max_length=256)
    source_set_digest: Sha256
    capabilities: tuple[
        Literal["SEMANTIC", "ANALYTICS", "DATA_MAPPING"], ...
    ] = Field(min_length=1, max_length=3)
    output_language: AuthoringLanguage
    obligations: tuple[BuildObligationV1, ...] = Field(min_length=1, max_length=1000)
    required_validators: tuple[str, ...] = Field(min_length=1, max_length=64)
    objective_checksum: Sha256

    @model_validator(mode="after")
    def objective_is_closed(self) -> BuildObjectiveV1:
        if len(self.selected_source_version_ids) != len(
            set(self.selected_source_version_ids)
        ):
            raise ValueError("Build objective source versions must be unique")
        ids = [item.obligation_id for item in self.obligations]
        if len(ids) != len(set(ids)):
            raise ValueError("Build objective obligations must be unique")
        if len(self.capabilities) != len(set(self.capabilities)):
            raise ValueError("Build objective capabilities must be unique")
        unsigned = self.model_dump(mode="json", exclude={"objective_checksum"})
        if sha256_value(unsigned) != self.objective_checksum:
            # Persisted objectives are immutable, so schema evolution must
            # reproduce each historical JSON shape exactly.  There are two
            # legitimate predecessors: one already carried collection shape,
            # and the older one did not.  Never recompute or rewrite their
            # stored checksum.
            legacy_shapes: list[dict[str, Any]] = []
            without_metric_contract = dict(unsigned)
            without_metric_contract["obligations"] = [
                {
                    key: value
                    for key, value in obligation.items()
                    if key != "metric_semantic_contract"
                }
                for obligation in unsigned["obligations"]
            ]
            legacy_shapes.append(without_metric_contract)

            without_collection_shape = dict(without_metric_contract)
            without_collection_shape["obligations"] = [
                {
                    key: value
                    for key, value in obligation.items()
                    if not (
                        key == "required_candidate_collections" and not value
                    )
                }
                for obligation in without_metric_contract["obligations"]
            ]
            legacy_shapes.append(without_collection_shape)
            if not any(
                sha256_value(candidate) == self.objective_checksum
                for candidate in legacy_shapes
            ):
                raise ValueError("Build objective checksum mismatch")
        return self


class ObligationDispositionV1(StrictModel):
    obligation_id: str = Field(pattern=r"^obligation\.[A-Za-z0-9][A-Za-z0-9._-]*$")
    disposition: ObligationDisposition
    candidate_targets: tuple[str, ...] = ()
    gap_id: str | None = None
    explanation: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def disposition_has_support(self) -> ObligationDispositionV1:
        if self.disposition == "CANDIDATE" and not self.candidate_targets:
            raise ValueError("Candidate disposition requires at least one target")
        if self.disposition in {"GAP", "UNSUPPORTED"} and not self.gap_id:
            raise ValueError("Gap disposition requires a gap identity")
        if self.disposition == "UNRESOLVED" and (
            self.candidate_targets or self.gap_id
        ):
            raise ValueError("Unresolved obligation cannot claim a disposition")
        return self


class RunAuthorityContextV1(StrictModel):
    """Server-derived authority. It is never accepted from model tool arguments."""

    contract: Literal["studio-run-authority/v1"] = "studio-run-authority/v1"
    job_id: str = Field(pattern=r"^construction-job\.[0-9a-f]{32}$")
    run_id: str = Field(pattern=r"^construction-run\.[0-9a-f]{32}$")
    attempt_id: str = Field(pattern=r"^construction-attempt\.[0-9a-f]{32}$")
    lease_epoch: int = Field(ge=1)
    lease_owner: str = Field(min_length=1, max_length=255)
    workspace_id: str = Field(min_length=1, max_length=255)
    solution_id: str = Field(min_length=1, max_length=255)
    source_set_digest: Sha256
    selected_source_version_ids: tuple[str, ...] = Field(min_length=1, max_length=256)
    principal_id: str = Field(min_length=1, max_length=255)
    tool_registry_digest: Sha256
    tool_policy_digest: Sha256
    objective_checksum: Sha256
    candidate_revision: int = Field(ge=0)
    step_sequence: int = Field(ge=0)
    remaining_model_calls: int = Field(ge=0)
    remaining_tool_calls: int = Field(ge=0)


class AgentToolDefinitionV1(StrictModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    description: str = Field(min_length=1, max_length=2000)
    input_schema: dict[str, Any]
    mutating: bool

    @model_validator(mode="after")
    def schema_is_closed(self) -> AgentToolDefinitionV1:
        if self.input_schema.get("type") != "object":
            raise ValueError("Agent tool input must be an object schema")
        if self.input_schema.get("additionalProperties") is not False:
            raise ValueError("Agent tool input schema must be closed")
        return self


class AgentToolCallV1(StrictModel):
    tool_call_id: str = Field(min_length=1, max_length=500)
    name: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    arguments: dict[str, Any]


class AgentMessageV1(StrictModel):
    role: AgentRole
    content: str | None = None
    tool_calls: tuple[AgentToolCallV1, ...] = ()
    tool_call_id: str | None = Field(default=None, max_length=500)
    name: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def message_shape_matches_role(self) -> AgentMessageV1:
        if self.role == "assistant":
            if self.content is None and not self.tool_calls:
                raise ValueError("Assistant message requires content or tool calls")
        elif self.role == "tool":
            if self.content is None or not self.tool_call_id or not self.name:
                raise ValueError("Tool message requires result identity and content")
            if self.tool_calls:
                raise ValueError("Tool result cannot contain tool calls")
        elif self.content is None or self.tool_calls or self.tool_call_id:
            raise ValueError("System and user messages require plain content")
        return self


class AgentTurnRequestV1(StrictModel):
    contract: Literal["studio-agent-turn-request/v1"] = (
        "studio-agent-turn-request/v1"
    )
    engine_checksum: Sha256
    provider: str = Field(min_length=1, max_length=100)
    requested_model: str = Field(min_length=1, max_length=255)
    messages: tuple[AgentMessageV1, ...] = Field(min_length=2, max_length=1000)
    tools: tuple[AgentToolDefinitionV1, ...] = Field(min_length=1, max_length=64)
    remaining_output_tokens: int = Field(ge=1)
    request_digest: Sha256

    @model_validator(mode="after")
    def turn_request_is_exact(self) -> AgentTurnRequestV1:
        names = [item.name for item in self.tools]
        if len(names) != len(set(names)):
            raise ValueError("Agent tool definitions must be unique")
        unsigned = self.model_dump(mode="json", exclude={"request_digest"})
        if sha256_value(unsigned) != self.request_digest:
            raise ValueError("Agent turn request digest mismatch")
        return self


class AgentTokenUsageV1(StrictModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)

    @model_validator(mode="after")
    def total_matches(self) -> AgentTokenUsageV1:
        if self.total_tokens != self.input_tokens + self.output_tokens:
            raise ValueError("Agent token usage total mismatch")
        return self


class AgentTurnResultV1(StrictModel):
    contract: Literal["studio-agent-turn-result/v1"] = (
        "studio-agent-turn-result/v1"
    )
    requested_model: str = Field(min_length=1, max_length=255)
    response_model: str = Field(min_length=1, max_length=255)
    provider_request_id: str = Field(min_length=1, max_length=500)
    assistant_content: str | None = None
    tool_calls: tuple[AgentToolCallV1, ...] = Field(max_length=32)
    finish_reason: str = Field(min_length=1, max_length=100)
    usage: AgentTokenUsageV1
    request_digest: Sha256
    result_digest: Sha256

    @model_validator(mode="after")
    def result_is_exact(self) -> AgentTurnResultV1:
        if self.assistant_content is None and not self.tool_calls:
            raise ValueError("Agent result requires content or structured tool calls")
        ids = [item.tool_call_id for item in self.tool_calls]
        if len(ids) != len(set(ids)):
            raise ValueError("Agent result tool call IDs must be unique")
        unsigned = self.model_dump(mode="json", exclude={"result_digest"})
        if sha256_value(unsigned) != self.result_digest:
            raise ValueError("Agent turn result digest mismatch")
        return self


class AgentModelTurnReceiptV1(StrictModel):
    contract: Literal["studio-agent-model-turn/v1"] = (
        "studio-agent-model-turn/v1"
    )
    turn_id: str = Field(pattern=r"^agent-turn\.[0-9a-f]{32}$")
    job_id: str
    run_id: str
    attempt_id: str
    lease_epoch: int = Field(ge=1)
    step_sequence: int = Field(ge=1)
    request: AgentTurnRequestV1
    result: AgentTurnResultV1
    committed_at: datetime

    @model_validator(mode="after")
    def request_result_match(self) -> AgentModelTurnReceiptV1:
        if self.result.request_digest != self.request.request_digest:
            raise ValueError("Model turn result does not match its exact request")
        return self


class ToolInvocationV1(StrictModel):
    contract: Literal["studio-tool-invocation/v1"] = "studio-tool-invocation/v1"
    tool_call_id: str = Field(min_length=1, max_length=500)
    tool_name: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    arguments: dict[str, Any]
    arguments_digest: Sha256

    @model_validator(mode="after")
    def arguments_are_exact(self) -> ToolInvocationV1:
        if sha256_value(self.arguments) != self.arguments_digest:
            raise ValueError("Tool invocation arguments digest mismatch")
        return self


class EvidenceReceiptV2(StrictModel):
    contract: Literal["studio-evidence-receipt/v2"] = "studio-evidence-receipt/v2"
    receipt_id: str = Field(pattern=r"^evidence-receipt\.[0-9a-f]{32}$")
    run_id: str
    workspace_id: str
    solution_id: str
    source_set_digest: Sha256
    source_version_id: str
    source_bytes_checksum: Sha256
    parser_id: str
    parser_version: str
    parsed_artifact_checksum: Sha256
    canonical_locator: str = Field(min_length=1, max_length=2000)
    returned_content_checksum: Sha256
    logical_role_ids: tuple[str, ...] = Field(min_length=1, max_length=32)
    authority_context_digest: Sha256
    issued_at: datetime
    receipt_checksum: Sha256

    @model_validator(mode="after")
    def receipt_is_exact(self) -> EvidenceReceiptV2:
        unsigned = self.model_dump(mode="json", exclude={"receipt_checksum"})
        if sha256_value(unsigned) != self.receipt_checksum:
            raise ValueError("Evidence receipt checksum mismatch")
        return self


class EvidenceIndexReceiptV1(StrictModel):
    """Server-produced proof of what an exact source parser did and did not index."""

    contract: Literal["studio-evidence-index-receipt/v1"] = (
        "studio-evidence-index-receipt/v1"
    )
    source_version_id: str
    source_bytes_checksum: Sha256
    media_type: str = Field(min_length=1, max_length=255)
    parser_id: str
    parser_version: str
    parser_options_digest: Sha256
    parsed_artifact_checksum: Sha256
    completeness: Literal["COMPLETE", "PARTIAL", "UNSUPPORTED"]
    total_units: int = Field(ge=0)
    indexed_units: int = Field(ge=0)
    unit_kind: Literal["LINES", "CELLS", "STATEMENTS", "BYTES"]
    warnings: tuple[str, ...] = ()
    receipt_checksum: Sha256

    @model_validator(mode="after")
    def receipt_is_coherent(self) -> EvidenceIndexReceiptV1:
        if self.indexed_units > self.total_units:
            raise ValueError("Evidence index cannot index more units than exist")
        if self.completeness == "COMPLETE" and self.indexed_units != self.total_units:
            raise ValueError("Complete evidence index must cover every unit")
        if self.completeness == "UNSUPPORTED" and self.indexed_units != 0:
            raise ValueError("Unsupported evidence cannot claim indexed units")
        unsigned = self.model_dump(mode="json", exclude={"receipt_checksum"})
        if sha256_value(unsigned) != self.receipt_checksum:
            raise ValueError("Evidence index receipt checksum mismatch")
        return self


class CandidateClaimV1(StrictModel):
    path: str = Field(min_length=1, max_length=1000)
    support: Literal["EXACT", "DETERMINISTIC_DERIVED", "INFERRED", "ASSUMPTION"]
    evidence_receipt_ids: tuple[str, ...] = Field(max_length=32)

    @model_validator(mode="after")
    def exact_support_has_receipt(self) -> CandidateClaimV1:
        if self.support in {"EXACT", "DETERMINISTIC_DERIVED"} and not self.evidence_receipt_ids:
            raise ValueError("Exact or derived claim requires an evidence receipt")
        return self


class CandidateMutationV1(StrictModel):
    expected_candidate_revision: int = Field(ge=0)
    operation: PackageDraftOperation
    claims: tuple[CandidateClaimV1, ...] = Field(min_length=1, max_length=128)


class ToolInvocationReceiptV1(StrictModel):
    contract: Literal["studio-tool-receipt/v1"] = "studio-tool-receipt/v1"
    receipt_id: str = Field(pattern=r"^tool-receipt\.[0-9a-f]{32}$")
    job_id: str
    run_id: str
    attempt_id: str
    lease_epoch: int = Field(ge=1)
    step_sequence: int = Field(ge=1)
    tool_call_id: str
    tool_name: str
    arguments_digest: Sha256
    mutating: bool
    candidate_revision_before: int = Field(ge=0)
    candidate_revision_after: int = Field(ge=0)
    result: dict[str, Any]
    result_digest: Sha256
    committed_at: datetime

    @model_validator(mode="after")
    def revision_and_result_match(self) -> ToolInvocationReceiptV1:
        expected_after = self.candidate_revision_before + (1 if self.mutating else 0)
        if self.candidate_revision_after != expected_after:
            raise ValueError("Tool receipt candidate revision transition mismatch")
        if sha256_value(self.result) != self.result_digest:
            raise ValueError("Tool receipt result digest mismatch")
        return self


class CandidateBundleV2(StrictModel):
    contract: Literal["studio-candidate-bundle/v2"] = "studio-candidate-bundle/v2"
    bundle_id: str = Field(pattern=r"^candidate-bundle\.[0-9a-f]{32}$")
    run_id: str
    attempt_id: str
    objective_checksum: Sha256
    candidate_revision: int = Field(ge=0)
    operations: tuple[PackageDraftOperation, ...]
    claims_by_target: dict[str, tuple[CandidateClaimV1, ...]]
    obligation_dispositions: tuple[ObligationDispositionV1, ...]
    evidence_receipt_ids: tuple[str, ...]
    prospective_package_checksum: Sha256
    validator_report_digests: tuple[Sha256, ...]
    sealed_at: datetime
    bundle_checksum: Sha256

    @model_validator(mode="after")
    def bundle_is_exact(self) -> CandidateBundleV2:
        unsigned = self.model_dump(mode="json", exclude={"bundle_checksum"})
        if sha256_value(unsigned) != self.bundle_checksum:
            raise ValueError("Candidate bundle checksum mismatch")
        return self


class AgentRunCompletionV1(StrictModel):
    contract: Literal["studio-agent-completion/v1"] = "studio-agent-completion/v1"
    outcome: Literal["REVIEW_READY", "BLOCKED"]
    bundle: CandidateBundleV2
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
