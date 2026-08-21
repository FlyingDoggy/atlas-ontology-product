from __future__ import annotations

import os
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .io import file_checksum, sha256_value
from .models import StrictModel


DemoMode = Literal["off", "shadow", "active-question-family-canary"]
DemoOutcome = Literal[
    "ANSWERED",
    "CLARIFY",
    "REFUSED",
    "FAILED_PRECONDITION",
    "FAILED_EXECUTION",
]

DEMO_CLASS = "LLM_ENGINEERING_DEMO"
DEMO_PROVIDER = "qwen"
DEMO_REQUESTED_MODEL = "qwen3.8-max"
DEMO_INPUT_POLICY = "REGISTERED_SYNTHETIC_QUESTION_FAMILY_ONLY"
DEMO_LABEL = (
    "LLM Engineering Demo — constructed-synthetic ADT; bounded engineering controls; "
    "not Stage 1 governed-evidence conformant; not HKEX validated; not production-ready."
)
DEMO_OUTCOMES: tuple[DemoOutcome, ...] = (
    "ANSWERED",
    "CLARIFY",
    "REFUSED",
    "FAILED_PRECONDITION",
    "FAILED_EXECUTION",
)


class EngineeringDemoStatus(StrictModel):
    demo_class: Literal["LLM_ENGINEERING_DEMO"] = DEMO_CLASS
    mode: DemoMode
    provider: Literal["qwen"] = DEMO_PROVIDER
    requested_model: Literal["qwen3.8-max"] = DEMO_REQUESTED_MODEL
    input_policy: Literal[
        "REGISTERED_SYNTHETIC_QUESTION_FAMILY_ONLY"
    ] = DEMO_INPUT_POLICY
    outcomes: tuple[DemoOutcome, ...] = DEMO_OUTCOMES
    label: str = DEMO_LABEL


class RegisteredQuestionCase(StrictModel):
    case_id: str = Field(pattern=r"^adt\.[a-z]+\.(?:en|zh)\.v\d+$")
    language: Literal["en", "zh"]
    question: str = Field(min_length=1, max_length=500)
    expected_intent: Literal[
        "period_compare", "turnover_driver", "sequential_decomposition"
    ]
    required_tools: tuple[
        Literal["compare_periods", "rank_contributors", "decompose_change"], ...
    ] = Field(min_length=1, max_length=3)


class RegisteredQuestionFamily(StrictModel):
    contract: Literal["registered-question-family/v1"]
    family_id: Literal["adt.synthetic.analysis.v1"]
    version: Literal["1.0.0"]
    classification: Literal["constructed_synthetic"]
    cases: tuple[RegisteredQuestionCase, ...] = Field(min_length=1)

    def resolve(self, case_id: str, question: str) -> RegisteredQuestionCase | None:
        matches = [
            case
            for case in self.cases
            if case.case_id == case_id and case.question == question
        ]
        return matches[0] if len(matches) == 1 else None


class PublicQuestionCase(StrictModel):
    case_id: str
    language: Literal["en", "zh"]
    question: str


class PublicQuestionFamily(StrictModel):
    family_id: str
    family_checksum: str
    classification: Literal["constructed_synthetic"]
    cases: tuple[PublicQuestionCase, ...]


class SafePeriodResult(StrictModel):
    period_id: str
    adt_hkd_mn_per_trading_day: Decimal
    eligible_turnover_hkd_mn: Decimal
    trading_day_count: int


class SafeComparisonResult(StrictModel):
    previous: SafePeriodResult
    current: SafePeriodResult
    adt_direction: Literal["increase", "decrease", "no_change"]
    adt_delta_hkd_mn_per_trading_day: Decimal
    adt_delta_pct: Decimal


class SafeContributorResult(StrictModel):
    segment_id: str
    segment_name: str
    rank: int
    delta_hkd_mn: Decimal
    net_change_contribution_pct: Decimal


class SafeDecompositionResult(StrictModel):
    method: Literal["sequential_calendar_first"]
    calendar_effect_hkd_mn: Decimal
    activity_effect_hkd_mn: Decimal
    residual_hkd_mn: Decimal
    causal_claim: Literal[False]
    order_dependent: Literal[True]


class EngineeringDemoResult(StrictModel):
    comparison: SafeComparisonResult
    leading_contributor: SafeContributorResult | None = None
    decomposition: SafeDecompositionResult | None = None
    clause_ids: tuple[str, ...] = Field(min_length=1)


class EngineeringDemoResponse(StrictModel):
    demo_class: Literal["LLM_ENGINEERING_DEMO"] = DEMO_CLASS
    outcome: DemoOutcome
    answer: str
    run_id: str | None = None
    snapshot_checksum: str | None = None
    model_called: bool
    provider_call_count: int = Field(ge=0)
    tool_call_count: int = Field(ge=0)
    fallback_used: bool
    committed: bool
    reason_code: str | None = None
    profile_digest: str | None = None
    obligation_digest: str | None = None
    commit_digest: str | None = None
    result: EngineeringDemoResult | None = None
    label: str = DEMO_LABEL


class ModelEgressDecision(StrictModel):
    contract: Literal["model-egress-decision/v1"]
    decision_id: str = Field(pattern=r"^egress\.[A-Za-z0-9._-]+$")
    decision: Literal["ALLOW", "DENY"]
    product: Literal["ontology-analytic-agent"]
    task: Literal["adt-engineering-demo"]
    provider: Literal["qwen"]
    provider_account_ref: str = Field(min_length=1)
    endpoint_ref: str = Field(min_length=1)
    region: str = Field(min_length=1)
    classification: Literal["constructed_synthetic"]
    question_family_id: Literal["adt.synthetic.analysis.v1"]
    question_family_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    allowed_projection_contracts: tuple[
        Literal["model-question-projection/v1", "model-evidence-projection/v1"], ...
    ] = Field(min_length=1)
    retention_profile: str = Field(min_length=1)
    approved_by: str = Field(min_length=1)
    issued_at: datetime
    expires_at: datetime

    def permits(
        self,
        family: RegisteredQuestionFamily,
        *,
        now: datetime | None = None,
    ) -> bool:
        instant = now or datetime.now(timezone.utc)
        return (
            self.decision == "ALLOW"
            and self.question_family_id == family.family_id
            and self.question_family_checksum == sha256_value(family)
            and "model-question-projection/v1" in self.allowed_projection_contracts
            and self.issued_at <= instant < self.expires_at
        )


class ProfileArtifactPin(StrictModel):
    artifact_id: Literal[
        "prompt-manifest", "tool-registry", "projection-policy", "question-family"
    ]
    relative_path: str = Field(min_length=1)
    checksum: str = Field(pattern=r"^[0-9a-f]{64}$")


class EngineeringBudgets(StrictModel):
    absolute_timeout_ms: int = Field(ge=1000, le=15000)
    provider_timeout_ms: int = Field(ge=500, le=10000)
    max_provider_calls: int = Field(ge=1, le=3)
    max_tool_calls: int = Field(ge=1, le=3)
    max_iterations: int = Field(ge=1, le=3)
    max_input_tokens: int = Field(ge=1, le=10000)
    max_output_tokens: int = Field(ge=1, le=2000)


class EngineeringRunProfile(StrictModel):
    contract: Literal["engineering-run-profile/v1"]
    profile_id: Literal["adt.agent.qwen3.8max.v1"]
    version: Literal["1.0.0"]
    provider: Literal["qwen"]
    requested_model: Literal["qwen3.8-max"]
    accepted_response_models: tuple[Literal["qwen3.8-max"], ...] = Field(
        min_length=1
    )
    provider_account_ref: str = Field(min_length=1)
    endpoint_ref: str = Field(min_length=1)
    region: str = Field(min_length=1)
    artifact_pins: tuple[ProfileArtifactPin, ...] = Field(min_length=4, max_length=4)
    input_contracts: tuple[
        Literal["model-question-projection/v1", "model-evidence-projection/v1"], ...
    ]
    output_contracts: tuple[
        Literal[
            "bound-goal-candidate/v1",
            "next-tool-selection/v1",
            "presentation-selection/v1",
        ],
        ...,
    ]
    tool_ids: tuple[
        Literal["compare_periods", "rank_contributors", "decompose_change"], ...
    ]
    budgets: EngineeringBudgets
    temperature: Literal[0]
    thinking: Literal[False]
    fallback_policy: Literal["restart-original-trusted-request/v1"]
    outcome_contract: Literal["engineering-demo-five-outcome/v1"]
    renderer_policy: Literal["closed-answer-clause-deterministic-renderer/v1"]
    trace_policy: Literal["safe-metadata-no-raw-content/v1"]

    def matches(self, egress: ModelEgressDecision) -> bool:
        return (
            self.provider == egress.provider
            and self.provider_account_ref == egress.provider_account_ref
            and self.endpoint_ref == egress.endpoint_ref
            and self.region == egress.region
            and self.requested_model in self.accepted_response_models
            and self.tool_ids
            == ("compare_periods", "rank_contributors", "decompose_change")
        )


class TaskRolloutRecord(StrictModel):
    contract: Literal["task-rollout-record/v1"]
    rollout_id: str = Field(pattern=r"^rollout\.[A-Za-z0-9._-]+$")
    task: Literal["adt-engineering-demo"]
    mode: Literal["shadow", "active-question-family-canary"]
    epoch: int = Field(ge=1)
    status: Literal["ACTIVE", "OFF"]
    profile_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    question_family_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    egress_decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluation_manifest_ref: str | None = None
    evaluation_manifest_checksum: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    label_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    auto_off_triggers: tuple[
        Literal[
            "PROFILE_MISMATCH",
            "MODEL_IDENTITY_MISMATCH",
            "SCHEMA_FAILURE",
            "LEAK_DETECTED",
            "DEADLINE_EXCEEDED",
        ],
        ...,
    ] = Field(min_length=5, max_length=5)
    approved_by: str = Field(min_length=1)
    issued_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def active_canary_requires_evaluation(self) -> TaskRolloutRecord:
        if self.mode == "active-question-family-canary" and (
            not self.evaluation_manifest_ref or not self.evaluation_manifest_checksum
        ):
            raise ValueError("Active canary requires a frozen evaluation manifest")
        if (self.evaluation_manifest_ref is None) != (
            self.evaluation_manifest_checksum is None
        ):
            raise ValueError("Evaluation manifest ref and checksum must be paired")
        return self

    def permits(
        self,
        *,
        mode: DemoMode,
        profile: EngineeringRunProfile,
        family: RegisteredQuestionFamily,
        egress: ModelEgressDecision,
        now: datetime | None = None,
    ) -> bool:
        instant = now or datetime.now(timezone.utc)
        return (
            self.status == "ACTIVE"
            and self.mode == mode
            and self.profile_digest == sha256_value(profile)
            and self.question_family_checksum == sha256_value(family)
            and self.egress_decision_digest == sha256_value(egress)
            and self.label_digest == sha256_value(DEMO_LABEL)
            and self.issued_at <= instant < self.expires_at
            and set(self.auto_off_triggers)
            == {
                "PROFILE_MISMATCH",
                "MODEL_IDENTITY_MISMATCH",
                "SCHEMA_FAILURE",
                "LEAK_DETECTED",
                "DEADLINE_EXCEEDED",
            }
        )


class AutomaticOffLatch(StrictModel):
    contract: Literal["engineering-automatic-off-latch/v1"]
    task: Literal["adt-engineering-demo"]
    rollout_id: str
    rollout_epoch: int = Field(ge=1)
    rollout_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    trigger: Literal[
        "PROFILE_MISMATCH",
        "MODEL_IDENTITY_MISMATCH",
        "SCHEMA_FAILURE",
        "LEAK_DETECTED",
        "DEADLINE_EXCEEDED",
    ]
    tripped_at: datetime
    latch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class EvaluationCaseResult(StrictModel):
    case_id: str = Field(min_length=1)
    outcome: Literal["ANSWERED"]
    committed: Literal[True]
    response_model: Literal["qwen3.8-max"]
    provider_call_count: Literal[2]
    tool_sequence: tuple[
        Literal["compare_periods", "rank_contributors", "decompose_change"], ...
    ] = Field(min_length=1, max_length=2)
    commit_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    latency_ms: int = Field(ge=0, le=15000)


class EvaluationSecurityGates(StrictModel):
    unregistered_input_zero_call_blocked: Literal[True] = True
    projection_leak_blocked: Literal[True] = True
    early_finish_partial_release_blocked: Literal[True] = True
    rollout_race_blocked: Literal[True] = True
    model_identity_mismatch_blocked: Literal[True] = True
    exact_model_output_schema_passed: Literal[True] = True


class EngineeringEvaluationManifest(StrictModel):
    contract: Literal["engineering-evaluation-manifest/v1"]
    manifest_id: Literal["eval-manifest.adt.llm.v1"]
    demo_class: Literal["LLM_ENGINEERING_DEMO"]
    profile_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    question_family_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    egress_decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider: Literal["qwen"]
    requested_model: Literal["qwen3.8-max"]
    response_model: Literal["qwen3.8-max"]
    case_results: tuple[EvaluationCaseResult, ...] = Field(min_length=1)
    security_gates: EvaluationSecurityGates
    raw_content_retained: Literal[False]
    evaluated_at: datetime
    approved_by: str = Field(min_length=1)

    def permits(
        self,
        *,
        family: RegisteredQuestionFamily,
        profile: EngineeringRunProfile,
        egress: ModelEgressDecision,
        rollout_approved_by: str,
        rollout_issued_at: datetime,
    ) -> bool:
        expected = {case.case_id: case.required_tools for case in family.cases}
        observed = {case.case_id: case.tool_sequence for case in self.case_results}
        return (
            len(observed) == len(self.case_results)
            and observed == expected
            and self.profile_digest == sha256_value(profile)
            and self.question_family_checksum == sha256_value(family)
            and self.egress_decision_digest == sha256_value(egress)
            and self.provider == profile.provider == egress.provider
            and self.requested_model == profile.requested_model
            and self.response_model in profile.accepted_response_models
            and self.approved_by == rollout_approved_by
            and self.evaluated_at <= rollout_issued_at
        )


class RunCapability(StrictModel):
    contract: Literal["engineering-run-capability/v1"]
    run_id: str = Field(pattern=r"^run\.[0-9a-f]{32}$")
    rollout_id: str
    rollout_epoch: int = Field(ge=1)
    snapshot_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    question_family_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    egress_decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    question_case_id: str
    principal: str
    purpose: Literal["constructed-synthetic-adt-analysis"]
    tool_ids: tuple[
        Literal["compare_periods", "rank_contributors", "decompose_change"], ...
    ]
    issued_at: datetime
    expires_at: datetime


class ModelQuestionProjection(StrictModel):
    contract: Literal["model-question-projection/v1"]
    family_id: Literal["adt.synthetic.analysis.v1"]
    family_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    case_id: str
    language: Literal["en", "zh"]
    question: str = Field(min_length=1, max_length=500)
    metric_aliases: tuple[str, ...] = Field(min_length=1)
    period_ids: tuple[Literal["2025-Q3", "2025-Q4"], Literal["2025-Q3", "2025-Q4"]]
    dimension_aliases: tuple[str, ...] = Field(min_length=1)
    allowed_intents: tuple[
        Literal["period_compare", "turnover_driver", "sequential_decomposition"], ...
    ] = Field(min_length=1)


class ModelGroundingRequest(StrictModel):
    contract: Literal["model-grounding-request/v1"]
    capability: RunCapability
    profile_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    egress_decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    projection_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    deadline_at: datetime
    projection: ModelQuestionProjection


class BoundGoalCandidate(StrictModel):
    contract: Literal["bound-goal-candidate/v1"]
    intent: Literal["period_compare", "turnover_driver", "sequential_decomposition"]
    metric_id: Literal["metric.average_daily_turnover"]
    previous_period_id: Literal["2025-Q3"]
    current_period_id: Literal["2025-Q4"]
    population_id: Literal["scenario.adt_reference:SYNTH-CASH"]
    requested_analyses: tuple[
        Literal["compare_periods", "rank_contributors", "decompose_change"], ...
    ] = Field(min_length=1, max_length=3)
    first_tool: Literal["compare_periods"]
    language: Literal["en", "zh"]


class ModelGroundingResponse(StrictModel):
    contract: Literal["model-grounding-response/v1"]
    run_id: str = Field(pattern=r"^run\.[0-9a-f]{32}$")
    requested_model: Literal["qwen3.8-max"]
    response_model: Literal["qwen3.8-max"]
    provider_request_id: str = Field(min_length=1)
    goal: BoundGoalCandidate
    output_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class ModelEvidenceProjection(StrictModel):
    contract: Literal["model-evidence-projection/v1"]
    run_id: str = Field(pattern=r"^run\.[0-9a-f]{32}$")
    step_id: Literal["step.compare-periods"]
    tool_id: Literal["compare_periods"]
    result_contract: Literal["safe-period-comparison/v1"]
    aggregate_values: SafeComparisonResult
    claim_handles: tuple[str, ...] = Field(min_length=1)
    mandatory_limitations: tuple[
        Literal["constructed-synthetic", "descriptive-non-causal"], ...
    ] = Field(min_length=2, max_length=2)


class ModelNextToolRequest(StrictModel):
    contract: Literal["model-next-tool-request/v1"]
    capability: RunCapability
    profile_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    egress_decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    projection_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    deadline_at: datetime
    goal: BoundGoalCandidate
    projection: ModelEvidenceProjection
    allowed_next_actions: tuple[
        Literal["rank_contributors", "decompose_change", "finish"], ...
    ] = Field(min_length=1, max_length=3)


class NextToolSelection(StrictModel):
    contract: Literal["next-tool-selection/v1"]
    action: Literal["CALL_TOOL", "FINISH"]
    next_tool: Literal["rank_contributors", "decompose_change"] | None = None
    reason_code: Literal[
        "DRIVER_DETAIL_REQUIRED",
        "DECOMPOSITION_REQUIRED",
        "COMPARISON_COMPLETE",
        "NO_MATERIAL_CHANGE",
    ]

    @model_validator(mode="after")
    def action_matches_tool(self) -> NextToolSelection:
        if (self.action == "CALL_TOOL") != (self.next_tool is not None):
            raise ValueError("CALL_TOOL requires exactly one next tool; FINISH requires none")
        return self


class ModelNextToolResponse(StrictModel):
    contract: Literal["model-next-tool-response/v1"]
    run_id: str = Field(pattern=r"^run\.[0-9a-f]{32}$")
    requested_model: Literal["qwen3.8-max"]
    response_model: Literal["qwen3.8-max"]
    provider_request_id: str = Field(min_length=1)
    selection: NextToolSelection
    output_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class EngineeringDemoCommitSubject(StrictModel):
    contract: Literal["engineering-demo-response-commit/v1"]
    commit_id: str = Field(pattern=r"^commit\.[0-9a-f]{32}$")
    run_id: str = Field(pattern=r"^run\.[0-9a-f]{32}$")
    outcome: Literal["ANSWERED"]
    snapshot_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    rollout_id: str
    rollout_epoch: int = Field(ge=1)
    egress_decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    response_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    committed_at: datetime


class EngineeringDemoCommitReceipt(EngineeringDemoCommitSubject):
    commit_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class AnswerObligationManifest(StrictModel):
    contract: Literal["answer-obligation-manifest/v1"]
    intent: Literal["period_compare", "turnover_driver", "sequential_decomposition"]
    language: Literal["en", "zh"]
    metric_id: Literal["metric.average_daily_turnover"]
    previous_period_id: Literal["2025-Q3"]
    current_period_id: Literal["2025-Q4"]
    population_id: Literal["scenario.adt_reference:SYNTH-CASH"]
    required_tool_ids: tuple[
        Literal["compare_periods", "rank_contributors", "decompose_change"], ...
    ] = Field(min_length=1, max_length=2)
    required_clause_ids: tuple[
        Literal[
            "clause.adt.period-comparison",
            "clause.adt.leading-contributor",
            "clause.adt.calendar-first-decomposition",
            "clause.adt.synthetic-limitation",
            "clause.adt.non-causal-limitation",
        ],
        ...,
    ] = Field(min_length=3, max_length=4)


class RenderedClosedAnswer(StrictModel):
    answer: str
    result: EngineeringDemoResult
    obligation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


def engineering_demo_status() -> EngineeringDemoStatus:
    return EngineeringDemoStatus(mode=os.environ.get("ONTOLOGY_LLM_MODE", "off"))


def load_question_family(path: Path) -> RegisteredQuestionFamily:
    return RegisteredQuestionFamily.model_validate(json.loads(path.read_text(encoding="utf-8")))


def public_question_family(path: Path) -> PublicQuestionFamily:
    family = load_question_family(path)
    return PublicQuestionFamily(
        family_id=family.family_id,
        family_checksum=sha256_value(family),
        classification=family.classification,
        cases=tuple(
            PublicQuestionCase(
                case_id=case.case_id,
                language=case.language,
                question=case.question,
            )
            for case in family.cases
        ),
    )


def load_egress_decision(path: Path) -> ModelEgressDecision:
    return ModelEgressDecision.model_validate(json.loads(path.read_text(encoding="utf-8")))


def load_run_profile(path: Path) -> EngineeringRunProfile:
    profile = EngineeringRunProfile.model_validate(
        json.loads(path.read_text(encoding="utf-8"))
    )
    base = path.parent.resolve()
    pins = {pin.artifact_id: pin for pin in profile.artifact_pins}
    if set(pins) != {
        "prompt-manifest",
        "tool-registry",
        "projection-policy",
        "question-family",
    }:
        raise ValueError("Run profile artifact pin set is incomplete")
    for pin in profile.artifact_pins:
        relative = Path(pin.relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Run profile artifact path is unsafe")
        artifact = (base / relative).resolve()
        if not artifact.is_relative_to(base) or file_checksum(artifact) != pin.checksum:
            raise ValueError(f"Run profile artifact pin failed: {pin.artifact_id}")
    return profile


def load_rollout_record(path: Path) -> TaskRolloutRecord:
    return TaskRolloutRecord.model_validate(json.loads(path.read_text(encoding="utf-8")))


def load_evaluation_manifest(path: Path) -> EngineeringEvaluationManifest:
    return EngineeringEvaluationManifest.model_validate(
        json.loads(path.read_text(encoding="utf-8"))
    )


def build_question_projection(
    family: RegisteredQuestionFamily,
    case: RegisteredQuestionCase,
) -> ModelQuestionProjection:
    return ModelQuestionProjection(
        contract="model-question-projection/v1",
        family_id=family.family_id,
        family_checksum=sha256_value(family),
        case_id=case.case_id,
        language=case.language,
        question=case.question,
        metric_aliases=("Average Daily Turnover", "ADT", "日均成交额"),
        period_ids=("2025-Q3", "2025-Q4"),
        dimension_aliases=("Market segment", "market board", "板块"),
        allowed_intents=(case.expected_intent,),
    )
