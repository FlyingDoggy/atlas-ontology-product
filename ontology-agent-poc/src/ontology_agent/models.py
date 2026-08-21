from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Status(StrEnum):
    PROPOSED = "proposed"
    NEEDS_CLARIFICATION = "needs_clarification"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"


class LocalizedName(StrictModel):
    en: str = Field(min_length=1)
    zh: str = Field(min_length=1)


class SourceReference(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    source_type: Literal[
        "requirement_transcription",
        "metric_transcription",
        "data_model",
        "data_dictionary",
        "sample_data",
        "assumption_register",
        "derived_control",
        "sql",
        "human_confirmation",
        "public_reference",
    ]
    title: str
    locator: str
    owner: str
    captured_on: date
    trust: Literal["primary", "secondary", "assumption"]
    notes: str = ""


class GovernedObject(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    version: str = Field(default="1.0.0", pattern=r"^\d+\.\d+\.\d+$")
    status: Status
    name: LocalizedName
    definition: str = Field(min_length=1)
    owner: str
    sources: tuple[str, ...] = Field(min_length=1)
    decisions: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()


class Actor(GovernedObject):
    roles: tuple[str, ...]


class ProcessStep(StrictModel):
    id: str
    name: str
    actor: str
    operation: str
    governed_refs: tuple[str, ...] = ()
    output_artifacts: tuple[str, ...] = ()
    on_failure: Literal["stop", "clarify", "review", "refuse"]


class Process(GovernedObject):
    process_type: Literal["business", "analysis", "governance"]
    trigger: str
    steps: tuple[ProcessStep, ...] = Field(min_length=1)
    exception_paths: tuple[str, ...] = ()


class PeriodDefinition(StrictModel):
    id: str
    start: date
    end: date
    inclusive: bool = True


class Scenario(GovernedObject):
    """Optional execution context for one solution.

    Exchange-specific context is deliberately optional.  A blank or non-trading
    solution must not manufacture a market, date window or role merely to satisfy
    the package envelope.
    """

    timezone: str | None = None
    market_id: str | None = None
    data_window_start: date | None = None
    data_window_end: date | None = None
    periods: tuple[PeriodDefinition, ...] = ()
    default_role: str | None = None


class Entity(GovernedObject):
    primary_key: str
    grain: str
    lifecycle: str


class Property(GovernedObject):
    entity: str
    data_type: Literal["string", "integer", "decimal", "boolean", "date", "datetime", "enum"]
    required: bool
    unit: str | None = None
    enum_values: tuple[str, ...] = ()
    null_meaning: str = "not_allowed"


class Relationship(GovernedObject):
    from_entity: str
    to_entity: str
    predicate: str
    cardinality: Literal["1:1", "1:N", "N:1", "N:N"]


class Dimension(GovernedObject):
    entity: str
    key_property: str
    label_property: str
    hierarchy: tuple[str, ...] = ()
    member_resolution: Literal["exact", "controlled_alias", "none"] = "exact"


class Condition(StrictModel):
    property: str
    op: Literal["eq", "neq", "in", "not_in", "is_true", "is_false"]
    value: Any | None = None


class Rule(GovernedObject):
    rule_type: Literal["eligibility", "quality", "calendar", "policy", "alert"]
    all: tuple[Condition, ...]
    failure_behavior: Literal["exclude", "block", "warn"]


class FormulaNode(StrictModel):
    op: Literal[
        "field_ref",
        "metric_ref",
        "literal",
        "sum",
        "count_distinct",
        "add",
        "subtract",
        "multiply",
        "divide",
    ]
    ref: str | None = None
    value: Decimal | None = None
    args: tuple[FormulaNode, ...] = ()

    @model_validator(mode="after")
    def validate_shape(self) -> FormulaNode:
        if self.op in {"field_ref", "metric_ref"} and not self.ref:
            raise ValueError(f"{self.op} requires ref")
        if self.op == "literal" and self.value is None:
            raise ValueError("literal requires value")
        unary = {"sum", "count_distinct"}
        binary = {"add", "subtract", "multiply", "divide"}
        if self.op in unary and len(self.args) != 1:
            raise ValueError(f"{self.op} requires one argument")
        if self.op in binary and len(self.args) != 2:
            raise ValueError(f"{self.op} requires two arguments")
        return self


class QueryContract(StrictModel):
    base_source: str | None = None
    measure_property: str | None = None
    period_property: str | None = None
    date_property: str | None = None
    population_property: str | None = None
    required_joins: tuple[str, ...] = ()
    filters: tuple[str, ...] = ()


class Metric(GovernedObject):
    metric_type: Literal["base", "derived"]
    base_entity: str
    result_grain: tuple[str, ...]
    value_type: Literal["integer", "decimal", "percentage"]
    unit: str
    aggregation_semantics: Literal[
        "additive", "semi_additive", "non_additive", "derived_non_additive"
    ]
    formula: FormulaNode
    query: QueryContract = QueryContract()
    allowed_dimensions: tuple[str, ...] = ()
    null_policy: Literal["exclude", "zero", "fail_validation"] = "fail_validation"
    zero_denominator_policy: Literal["zero", "null", "refuse"] = "refuse"


class FieldDefinition(StrictModel):
    name: str
    data_type: Literal["string", "integer", "decimal", "boolean", "date", "datetime"]
    nullable: bool
    description: str
    unit: str | None = None


class TableDefinition(StrictModel):
    name: str
    grain: str
    primary_key: tuple[str, ...]
    fields: tuple[FieldDefinition, ...]


class DataSource(GovernedObject):
    protocol: Literal["tabular/v1"] = "tabular/v1"
    tables: tuple[TableDefinition, ...]


class PhysicalBinding(GovernedObject):
    logical_target: str
    source: str
    table: str
    column: str
    data_type: Literal["string", "integer", "decimal", "boolean", "date", "datetime"]
    unit: str | None = None
    transformation: str = "identity"


class JoinKeyPair(StrictModel):
    left_column: str
    right_column: str


class JoinContract(GovernedObject):
    left_source: str
    left_table: str
    right_source: str
    right_table: str
    keys: tuple[JoinKeyPair, ...] = Field(min_length=1)
    expected_cardinality: Literal["1:1", "N:1"]
    fanout_policy: Literal["block", "deduplicate_reviewed"] = "block"


class SqlInputRelation(StrictModel):
    source: str
    table: str
    alias: str | None = None


class SqlParameter(StrictModel):
    name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    data_type: Literal["string", "integer", "decimal", "boolean", "date", "datetime"]
    required: bool = True
    description: str = ""


class SqlContract(GovernedObject):
    """Governed reference to exact SQL evidence, not a mutable SQL text copy."""

    dialect: Literal[
        "ansi",
        "postgresql",
        "duckdb",
        "bigquery",
        "snowflake",
        "spark",
        "other",
    ] = "ansi"
    statement_source: str
    statement_locator: str = Field(min_length=1)
    inputs: tuple[SqlInputRelation, ...] = ()
    output_fields: tuple[str, ...] = ()
    implements: tuple[str, ...] = ()
    parameters: tuple[SqlParameter, ...] = ()
    execution_mode: Literal[
        "reference_only", "validated_query", "runtime_tool"
    ] = "reference_only"
    read_only: Literal[True] = True


class AnalysisPattern(GovernedObject):
    intent: Literal[
        "metric_fact",
        "period_compare",
        "segment_contribution",
        "sequential_decomposition",
        "evidence_audit",
        "turnover_driver",
        "anomaly_triage",
        "time_series",
        "latency_profile",
        "timeline_evidence",
    ]
    operation: str
    required_metrics: tuple[str, ...]
    required_dimensions: tuple[str, ...] = ()
    exactly_two_periods: bool = False
    output_fields: tuple[str, ...]
    failure_conditions: tuple[str, ...] = ()


class Policy(GovernedObject):
    allowed_roles: tuple[str, ...]
    denied_roles: tuple[str, ...]
    allowed_grains: tuple[str, ...]
    denied_fields: tuple[str, ...]
    minimum_group_size: int = Field(ge=1)


class BusinessQuestion(GovernedObject):
    examples: tuple[str, ...]
    analysis_pattern: str
    required_inputs: tuple[str, ...]
    expected_answer: str


class Decision(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    question: str
    options: tuple[str, ...]
    decision: str
    decided_by: str
    decided_on: date
    affects: tuple[str, ...]
    residual_assumption: str = ""


class OntologyPackage(StrictModel):
    package_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    status: Status
    created_at: datetime
    scenario: Scenario
    actors: tuple[Actor, ...]
    processes: tuple[Process, ...]
    sources: tuple[SourceReference, ...]
    decisions: tuple[Decision, ...]
    entities: tuple[Entity, ...]
    properties: tuple[Property, ...]
    relationships: tuple[Relationship, ...]
    dimensions: tuple[Dimension, ...]
    rules: tuple[Rule, ...]
    metrics: tuple[Metric, ...]
    data_sources: tuple[DataSource, ...]
    bindings: tuple[PhysicalBinding, ...]
    joins: tuple[JoinContract, ...]
    sql_contracts: tuple[SqlContract, ...] = ()
    analysis_patterns: tuple[AnalysisPattern, ...]
    policies: tuple[Policy, ...]
    questions: tuple[BusinessQuestion, ...]

    def governed_objects(self) -> tuple[GovernedObject, ...]:
        return (
            self.scenario,
            *self.actors,
            *self.processes,
            *self.entities,
            *self.properties,
            *self.relationships,
            *self.dimensions,
            *self.rules,
            *self.metrics,
            *self.data_sources,
            *self.bindings,
            *self.joins,
            *self.sql_contracts,
            *self.analysis_patterns,
            *self.policies,
            *self.questions,
        )


class ValidationCheck(StrictModel):
    check_id: str
    category: Literal["structure", "source", "semantic", "binding", "data", "shacl"]
    status: Literal["PASS", "FAIL", "WARN"]
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ValidationReport(StrictModel):
    package_id: str
    package_version: str
    package_checksum: str
    validated_at: datetime
    status: Literal["PASS", "FAIL"]
    checks: tuple[ValidationCheck, ...]


class AtomicQueryContract(StrictModel):
    contract_id: str
    operation: str
    operator_version: str
    analysis_pattern: str
    scenario_id: str
    metric: str
    periods: tuple[str, ...]
    period_bounds: tuple[PeriodDefinition, ...]
    dimensions: tuple[str, ...]
    result_grain: tuple[str, ...]
    filters: tuple[str, ...]
    source_ids: tuple[str, ...]
    population_id: str
    market_id: str
    timezone: str
    policy_id: str
    policy_decision_id: str
    role: str
    snapshot_checksum: str


class PlanStep(StrictModel):
    step_id: str
    operation: str
    contract: AtomicQueryContract
    depends_on: tuple[str, ...] = ()
    required: bool = True


class AnalysisPlan(StrictModel):
    plan_id: str
    intent: str
    question: str
    snapshot_checksum: str
    steps: tuple[PlanStep, ...]
    plan_hash: str


class StepExecution(StrictModel):
    step_id: str
    status: Literal["PASS", "FAIL", "SKIPPED"]
    sql: str | None = None
    params: tuple[Any, ...] = ()
    sql_hash: str | None = None
    rows: tuple[dict[str, Any], ...] = ()
    error: str | None = None


class EvidenceRecord(StrictModel):
    claim_id: str
    claim_type: Literal["numeric", "direction", "ranking", "limitation", "definition"]
    claim: str
    result_path: str
    value: str
    display_value: str
    unit: str | None = None
    execution_id: str
    snapshot_checksum: str
    plan_hash: str
    dataset_checksum: str
    policy_id: str
    policy_decision_id: str
    query_or_operator_hashes: tuple[str, ...]
    metric_ids: tuple[str, ...]
    metric_versions: tuple[str, ...]
    mapping_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    step_ids: tuple[str, ...]


class AnalysisResponse(StrictModel):
    status: Literal["ANSWERED", "CLARIFY", "REFUSED", "FAILED"]
    answer: str
    execution_id: str | None = None
    snapshot_checksum: str | None = None
    plan: AnalysisPlan | None = None
    steps: tuple[StepExecution, ...] = ()
    facts: dict[str, Any] = Field(default_factory=dict)
    evidence: tuple[EvidenceRecord, ...] = ()
    boundary_code: str | None = None
