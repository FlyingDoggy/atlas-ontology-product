from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from ..io import sha256_value
from ..models import AuthoringLanguage
from .agentic_contracts import (
    AgentEngineContractV2,
    BuildObjectiveV1,
    BuildObligationV1,
    MetricSemanticObligationV1,
)
from .agentic_runtime import AGENT_CONTEXT_POLICY, ModelToolGateway
from .agentic_store import AgentCheckpointStore
from .agentic_tools import tool_definitions, tool_registry_digest
from .package_authoring import PackageDraftOperation
from .skill_packages import LoadedSkillPackageV2
from .source_library import SourceLibraryStore, StudioSourceVersionV1
from .source_projection import StudioAuthoringProjectionV1


class AgenticConstructionPlanError(RuntimeError):
    """Frozen Agentic Builder inputs could not be formed without ambiguity."""


@dataclass(frozen=True)
class FrozenAgenticBuildPlan:
    versions: tuple[StudioSourceVersionV1, ...]
    objective: BuildObjectiveV1
    engine: AgentEngineContractV2
    skill_instructions: str


@dataclass(frozen=True)
class AgenticConstructionRuntime:
    plan: FrozenAgenticBuildPlan
    checkpoint_store: AgentCheckpointStore
    source_store: SourceLibraryStore
    gateway: ModelToolGateway
    reviewer_skill: LoadedSkillPackageV2 | None = None
    principal_id: str = "service.ontology-builder"


_SOURCE_TYPE_BY_KIND = {
    "requirement_transcription": "requirement_transcription",
    "metric_transcription": "metric_transcription",
    "data_model": "data_model",
    "data_dictionary": "data_dictionary",
    "sql": "sql",
    "other": "public_reference",
}


def normalized_source_operations(
    versions: Iterable[StudioSourceVersionV1],
    *,
    owner: str,
    output_language: AuthoringLanguage = "en",
) -> tuple[PackageDraftOperation, ...]:
    """Project frozen Source Library identities into the Candidate Workspace.

    This is input normalization, not ontology reasoning.  The model may cite these
    exact logical IDs, but it neither invents nor authorizes them.
    """

    ordered = tuple(sorted(versions, key=lambda item: item.source_version_id))
    source_ids = [item.source_id for item in ordered]
    if len(source_ids) != len(set(source_ids)):
        raise AgenticConstructionPlanError(
            "An Agentic build cannot select two versions of one logical source"
        )
    return tuple(
        PackageDraftOperation(
            action="UPSERT",
            collection="sources",
            object_id=item.source_id,
            payload={
                "id": item.source_id,
                "source_type": _SOURCE_TYPE_BY_KIND[item.kind],
                "title": item.title,
                "locator": f"source-library:{item.source_version_id}",
                "owner": owner,
                "captured_on": item.registered_at.date().isoformat(),
                "trust": (
                    "primary"
                    if item.kind
                    in {
                        "requirement_transcription",
                        "metric_transcription",
                        "data_model",
                        "data_dictionary",
                    }
                    else "secondary"
                ),
                "notes": (
                    (
                        "Ontology Studio 已冻结并标准化该输入；"
                        f"内容校验和 {item.content_checksum}；"
                        f"处理模式 {item.processing_mode}。"
                    )
                    if output_language == "zh"
                    else (
                        "Frozen input normalized by Ontology Studio; "
                        f"content checksum {item.content_checksum}; "
                        f"processing mode {item.processing_mode}."
                    )
                ),
            },
        )
        for item in ordered
    )


def exact_source_set_digest(versions: Iterable[StudioSourceVersionV1]) -> str:
    ordered = tuple(sorted(versions, key=lambda item: item.source_version_id))
    if not ordered:
        raise AgenticConstructionPlanError("Agentic construction requires exact sources")
    identities = [
        {
            "source_version_id": item.source_version_id,
            "source_id": item.source_id,
            "kind": item.kind,
            "content_checksum": item.content_checksum,
            "subject_checksum": item.subject_checksum,
        }
        for item in ordered
    ]
    return sha256_value(identities)


def _safe_obligation_id(prefix: str, value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    normalized = normalized[:96] or sha256_value(value)[:24]
    return f"obligation.{prefix}.{normalized}"


def _source_scope(
    versions: tuple[StudioSourceVersionV1, ...], source_id: str | None
) -> tuple[str, ...]:
    scoped = tuple(
        item.source_version_id for item in versions if source_id and item.source_id == source_id
    )
    return scoped or tuple(item.source_version_id for item in versions)


def _anchor_locator(anchor: object | None, fallback: str) -> str:
    locator = getattr(anchor, "locator", None)
    return str(locator) if locator else fallback


_EXPLICIT_MULTIPLIER = re.compile(
    r"(?:\*|×|\bx\b)\s*([0-9][0-9,_]*(?:\.[0-9]+)?)",
    re.IGNORECASE,
)
_RATIO_LANGUAGE = re.compile(
    r"(?:/|÷|\bdivid(?:e|ed)\b|\bratio\b|\brate\b|百分比|比例)",
    re.IGNORECASE,
)
_PERCENT_LANGUAGE = re.compile(r"(?:%|\bpercent(?:age)?\b|百分比)", re.IGNORECASE)
_MILLISECOND_LANGUAGE = re.compile(
    r"(?:\bmilliseconds?\b|(?<![A-Za-z])ms(?![A-Za-z])|毫秒)", re.IGNORECASE
)
_DURATION_LANGUAGE = re.compile(
    r"(?:timestamp|time\s*stamp|时间戳).*(?:difference|minus|elapsed|latency|延迟|差|-)"
    r"|(?:difference|minus|elapsed|latency|延迟|差).*(?:timestamp|time\s*stamp|时间戳)",
    re.IGNORECASE | re.DOTALL,
)
_CURRENCY_MILLION_LANGUAGE = re.compile(
    r"\b([A-Z]{3})\s*(?:million|mn)\b", re.IGNORECASE
)


def _stable_metric_id(metric_key: str, name: str, canonical_id: str | None) -> str:
    if canonical_id and canonical_id.startswith("metric."):
        return canonical_id
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_name.casefold()).strip("_")
    if not slug:
        slug = re.sub(r"[^a-z0-9]+", "_", metric_key.casefold()).strip("_")
    return f"metric.{slug or sha256_value(name)[:16]}"


def _metric_semantic_contract(
    metric: object,
) -> MetricSemanticObligationV1:
    """Freeze exact source semantics plus only mechanically explicit conventions."""

    metric_key = str(getattr(metric, "metric_key"))
    name = str(getattr(metric, "name"))
    calculation_logic = str(getattr(metric, "calculation_logic"))
    output_instruction = str(getattr(metric, "unit"))
    combined = f"{calculation_logic}\n{output_instruction}"

    expected_metric_type: str | None = None
    expected_value_type: str | None = None
    expected_unit: str | None = None
    required_root: str | None = None
    required_operations: list[str] = []
    required_literals: list[Decimal] = []
    required_referenced_units: list[str] = []

    ratio_output = bool(_PERCENT_LANGUAGE.search(output_instruction)) and bool(
        _RATIO_LANGUAGE.search(calculation_logic)
    )
    currency_million = _CURRENCY_MILLION_LANGUAGE.search(output_instruction)
    if ratio_output:
        expected_metric_type = "derived"
        expected_value_type = "percentage"
        expected_unit = "PERCENT"
        required_root = "multiply"
        required_operations.extend(("divide", "multiply"))
        required_literals.append(Decimal("100"))
    elif _MILLISECOND_LANGUAGE.search(output_instruction):
        expected_value_type = "integer"
        expected_unit = "MILLISECOND"
        if _DURATION_LANGUAGE.search(calculation_logic):
            required_root = "duration_ms"
            required_operations.append("duration_ms")
    elif currency_million:
        currency = currency_million.group(1).upper()
        expected_metric_type = "derived"
        expected_value_type = "decimal"
        expected_unit = f"{currency}_MN"
        required_root = "divide"
        required_operations.extend(("sum", "divide"))
        required_literals.append(Decimal("1000000"))
        required_referenced_units.append(currency)

    for match in _EXPLICIT_MULTIPLIER.finditer(combined):
        value = Decimal(match.group(1).replace(",", "").replace("_", ""))
        if value not in required_literals:
            required_literals.append(value)
        if "multiply" not in required_operations:
            required_operations.append("multiply")

    raw: dict[str, object] = {
        "contract": "studio-metric-semantic-obligation/v1",
        "source_metric_key": metric_key,
        "expected_metric_id": _stable_metric_id(
            metric_key, name, getattr(metric, "canonical_metric_id", None)
        ),
        "name": name,
        "definition": str(getattr(metric, "definition")),
        "calculation_logic": calculation_logic,
        "filters_and_scope": str(getattr(metric, "filters_and_scope")),
        "grain_and_dimensions": str(getattr(metric, "grain_and_dimensions")),
        "output_instruction": output_instruction,
        "null_and_zero_policy": str(getattr(metric, "null_and_zero_policy")),
        "primary_sources": str(getattr(metric, "primary_sources")),
        "expected_metric_type": expected_metric_type,
        "expected_value_type": expected_value_type,
        "expected_unit": expected_unit,
        "required_formula_root": required_root,
        "required_formula_operations": required_operations,
        "required_formula_literals": required_literals,
        "required_referenced_units": required_referenced_units,
    }
    raw["semantic_contract_checksum"] = sha256_value(raw)
    return MetricSemanticObligationV1.model_validate(raw)


def compile_build_objective(
    *,
    solution_id: str,
    workspace_id: str,
    versions: Iterable[StudioSourceVersionV1],
    authoring: StudioAuthoringProjectionV1,
    output_language: AuthoringLanguage,
    enforce_typed_candidate_shape: bool = False,
    enforce_metric_semantic_contract: bool = False,
) -> BuildObjectiveV1:
    ordered = tuple(sorted(versions, key=lambda item: item.source_version_id))
    source_set_digest = exact_source_set_digest(ordered)
    obligations: list[BuildObligationV1] = []

    for requirement in authoring.requirements:
        anchor = requirement.source_anchor
        obligations.append(
            BuildObligationV1(
                obligation_id=_safe_obligation_id(
                    "requirement", requirement.requirement_key
                ),
                kind="REQUIREMENT",
                title=requirement.question[:500],
                source_version_ids=_source_scope(
                    ordered, getattr(anchor, "source_id", None)
                ),
                source_locator=_anchor_locator(
                    anchor, f"requirement:{requirement.requirement_key}"
                ),
                required_candidate_collections=(
                    ("analysis_patterns", "questions")
                    if enforce_typed_candidate_shape
                    else ()
                ),
            )
        )

    for metric in authoring.metric_candidates:
        anchor = metric.source_anchor
        obligations.append(
            BuildObligationV1(
                obligation_id=_safe_obligation_id("metric", metric.metric_key),
                kind="METRIC",
                title=f"{metric.name}: {metric.definition}"[:500],
                source_version_ids=_source_scope(
                    ordered, getattr(anchor, "source_id", None)
                ),
                source_locator=_anchor_locator(anchor, f"metric:{metric.metric_key}"),
                required_candidate_collections=(
                    ("metrics",) if enforce_typed_candidate_shape else ()
                ),
                metric_semantic_contract=(
                    _metric_semantic_contract(metric)
                    if enforce_metric_semantic_contract
                    else None
                ),
            )
        )

    for version in ordered:
        obligations.append(
            BuildObligationV1(
                obligation_id=_safe_obligation_id(
                    "source-coverage", version.source_version_id
                ),
                kind="SOURCE_COVERAGE",
                title=f"Inspect and disposition source: {version.title}",
                source_version_ids=(version.source_version_id,),
                source_locator="exact-source:complete-inventory",
            )
        )

    all_version_ids = tuple(item.source_version_id for item in ordered)
    obligations.append(
        BuildObligationV1(
            obligation_id="obligation.semantic-model.closure",
            kind="SEMANTIC_MODEL",
            title="Produce the coherent business objects, properties, relationships, rules and processes required by the evidence",
            source_version_ids=all_version_ids,
            source_locator="source-set:semantic-closure",
            required_candidate_collections=(
                ("entities", "properties") if enforce_typed_candidate_shape else ()
            ),
        )
    )
    if enforce_typed_candidate_shape:
        obligations.extend(
            (
            BuildObligationV1(
                obligation_id="obligation.semantic-relationships.closure",
                kind="SEMANTIC_MODEL",
                title="Represent evidenced links between governed business objects",
                source_version_ids=all_version_ids,
                source_locator="source-set:relationship-closure",
                required_candidate_collections=("relationships",),
            ),
            BuildObligationV1(
                obligation_id="obligation.semantic-rules.closure",
                kind="SEMANTIC_MODEL",
                title="Represent evidenced eligibility, quality, calendar or policy rules",
                source_version_ids=all_version_ids,
                source_locator="source-set:rule-closure",
                required_candidate_collections=("rules",),
            ),
            BuildObligationV1(
                obligation_id="obligation.business-process.closure",
                kind="SEMANTIC_MODEL",
                title="Represent the evidenced business or analytical process and its accountable steps",
                source_version_ids=all_version_ids,
                source_locator="source-set:process-closure",
                required_candidate_collections=("processes",),
            ),
            )
        )

    capabilities: list[str] = ["SEMANTIC"]
    if authoring.requirements or authoring.metric_candidates:
        capabilities.append("ANALYTICS")
        obligations.append(
            BuildObligationV1(
                obligation_id="obligation.analytics.closure",
                kind="METRIC",
                title="Close analytical questions through governed metrics, dimensions, policies and answer patterns",
                source_version_ids=all_version_ids,
                source_locator="source-set:analytics-closure",
                required_candidate_collections=(
                    ("metrics", "dimensions")
                    if enforce_typed_candidate_shape
                    else ()
                ),
            )
        )
        if enforce_typed_candidate_shape:
            obligations.append(
                BuildObligationV1(
                    obligation_id="obligation.analytics-interface.closure",
                    kind="REQUIREMENT",
                    title="Expose evidenced analytical requirements as governed question families and executable analysis patterns",
                    source_version_ids=all_version_ids,
                    source_locator="source-set:analytics-interface-closure",
                    required_candidate_collections=("analysis_patterns", "questions"),
                )
            )
    mapping_versions = tuple(
        item.source_version_id
        for item in ordered
        if item.kind in {"data_model", "data_dictionary", "sql"}
    )
    if mapping_versions:
        capabilities.append("DATA_MAPPING")
        obligations.append(
            BuildObligationV1(
                obligation_id="obligation.data-mapping.closure",
                kind="DATA_MAPPING",
                title="Map governed concepts to physical data, fields, joins and executable SQL lineage where supported",
                source_version_ids=mapping_versions,
                source_locator="source-set:data-mapping-closure",
                required_candidate_collections=(
                    ("data_sources", "bindings")
                    if enforce_typed_candidate_shape
                    else ()
                ),
            )
        )
        if enforce_typed_candidate_shape:
            obligations.append(
                BuildObligationV1(
                    obligation_id="obligation.data-joins.closure",
                    kind="DATA_MAPPING",
                    title="Represent the evidenced physical joins required to traverse mapped data sources",
                    source_version_ids=mapping_versions,
                    source_locator="source-set:data-join-closure",
                    required_candidate_collections=("joins",),
                )
            )
    for version in ordered:
        if version.kind != "sql":
            continue
        obligations.append(
            BuildObligationV1(
                obligation_id=_safe_obligation_id("sql-contract", version.source_version_id),
                kind="SQL_CONTRACT",
                title=f"Inspect and preserve executable logic from {version.title}",
                source_version_ids=(version.source_version_id,),
                source_locator="sql:all-statements",
                required_candidate_collections=(
                    ("sql_contracts",) if enforce_typed_candidate_shape else ()
                ),
            )
        )

    objective_seed = {
        "solution_id": solution_id,
        "workspace_id": workspace_id,
        "selected_source_version_ids": all_version_ids,
        "source_set_digest": source_set_digest,
        "capabilities": capabilities,
        "output_language": output_language,
        "obligations": [item.model_dump(mode="json") for item in obligations],
        "required_validators": [
            "candidate.materialize",
            "candidate.semantic",
            "binding.closure",
            "sql.contract.closure",
            "language.policy",
            "obligation.denominator",
        ],
    }
    raw: dict[str, object] = {
        "contract": "studio-build-objective/v1",
        "objective_id": "build-objective." + sha256_value(objective_seed)[:32],
        **objective_seed,
    }
    raw["objective_checksum"] = sha256_value(raw)
    return BuildObjectiveV1.model_validate(raw)


def render_skill_instructions(skill: LoadedSkillPackageV2) -> str:
    sections = [skill.instructions.strip()]
    for path, content in sorted(skill.reference_texts.items()):
        sections.append(f"## Governed reference: {path}\n\n{content.strip()}")
    return "\n\n".join(sections)


def compile_engine_contract(
    *,
    objective: BuildObjectiveV1,
    skill: LoadedSkillPackageV2,
    provider: str,
    requested_model: str,
) -> AgentEngineContractV2:
    definitions = tool_definitions()
    registry_names = tuple(item.name for item in definitions)
    if tuple(skill.manifest.tool_ids) != registry_names:
        raise AgenticConstructionPlanError(
            "Build Skill tool set does not match the server-owned registry"
        )
    if skill.manifest.role != "BUILDER":
        raise AgenticConstructionPlanError("Agentic construction requires a Build Skill")
    tool_policy_digest = sha256_value(
        {
            "tool_ids": registry_names,
            "mutating_tools": [item.name for item in definitions if item.mutating],
            "serial_tool_calls": True,
            "candidate_only_writes": True,
            "human_review_required": True,
            "direct_draft_write": False,
        }
    )
    raw: dict[str, object] = {
        "contract": "studio-agent-engine/v2",
        "engine_id": "studio.agentic-builder",
        "engine_version": "2.0.0",
        "runtime_digest": sha256_value(
            {
                "runtime": "ontology-studio/serial-agent-runtime@2",
                "replay": "durable-model-and-tool-journal",
                "completion": "server-owned-tool-only",
                "context_policy": AGENT_CONTEXT_POLICY,
            }
        ),
        "provider": provider,
        "requested_model": requested_model,
        "model_config_digest": sha256_value(
            {
                "temperature": 0,
                "parallel_tool_calls": False,
                "enable_thinking": False,
                "tool_choice": "auto",
            }
        ),
        "skill_id": skill.manifest.skill_id,
        "skill_version": skill.manifest.version,
        "skill_checksum": skill.package_checksum,
        "tool_registry_digest": tool_registry_digest(),
        "tool_policy_digest": tool_policy_digest,
        "parser_contract_digest": sha256_value(
            {
                "text": "utf8-lines@2.0.0",
                "xlsx": "openpyxl-cell-index@2.0.0",
                "sql": "duckdb-sql-statements@2.0.0",
                "unsupported": "archive-only@1.0.0",
                "xlsx_index_cell_limit": 500_000,
                "xlsx_exact_read_cell_limit": 5_000,
            }
        ),
        "source_set_digest": objective.source_set_digest,
        "max_model_calls": skill.manifest.max_model_calls,
        "max_tool_calls": skill.manifest.max_tool_calls,
        "max_input_tokens": int(
            os.environ.get("ONTOLOGY_BUILDER_MAX_INPUT_TOKENS", "3000000")
        ),
        "max_output_tokens": int(
            os.environ.get("ONTOLOGY_BUILDER_TOTAL_OUTPUT_TOKENS", "400000")
        ),
        "output_language": objective.output_language,
        "objective_checksum": objective.objective_checksum,
    }
    raw["engine_checksum"] = sha256_value(raw)
    return AgentEngineContractV2.model_validate(raw)


def continuation_engine_contract(
    engine: AgentEngineContractV2,
) -> AgentEngineContractV2:
    """Freeze a smaller, fresh budget for one Candidate repair round."""

    raw = engine.model_dump(mode="json", exclude={"engine_checksum"})
    raw.update(
        {
            "max_model_calls": min(
                engine.max_model_calls,
                int(
                    os.environ.get(
                        "ONTOLOGY_BUILDER_CONTINUATION_MAX_MODEL_CALLS", "24"
                    )
                ),
            ),
            "max_tool_calls": min(
                engine.max_tool_calls,
                int(
                    os.environ.get(
                        "ONTOLOGY_BUILDER_CONTINUATION_MAX_TOOL_CALLS", "48"
                    )
                ),
            ),
            "max_input_tokens": min(
                engine.max_input_tokens,
                int(
                    os.environ.get(
                        "ONTOLOGY_BUILDER_CONTINUATION_MAX_INPUT_TOKENS", "650000"
                    )
                ),
            ),
            "max_output_tokens": min(
                engine.max_output_tokens,
                int(
                    os.environ.get(
                        "ONTOLOGY_BUILDER_CONTINUATION_MAX_OUTPUT_TOKENS", "100000"
                    )
                ),
            ),
        }
    )
    if min(
        int(raw["max_model_calls"]),
        int(raw["max_tool_calls"]),
        int(raw["max_input_tokens"]),
        int(raw["max_output_tokens"]),
    ) < 1:
        raise AgenticConstructionPlanError(
            "Candidate continuation budget must remain positive"
        )
    raw["engine_checksum"] = sha256_value(raw)
    return AgentEngineContractV2.model_validate(raw)


def freeze_agentic_build_plan(
    *,
    solution_id: str,
    workspace_id: str,
    versions: Iterable[StudioSourceVersionV1],
    authoring: StudioAuthoringProjectionV1,
    output_language: AuthoringLanguage,
    skill: LoadedSkillPackageV2,
    provider: str,
    requested_model: str,
) -> FrozenAgenticBuildPlan:
    ordered = tuple(sorted(versions, key=lambda item: item.source_version_id))
    objective = compile_build_objective(
        solution_id=solution_id,
        workspace_id=workspace_id,
        versions=ordered,
        authoring=authoring,
        output_language=output_language,
        enforce_typed_candidate_shape=(
            tuple(int(part) for part in skill.manifest.version.split("."))
            >= (2, 0, 2)
        ),
        enforce_metric_semantic_contract=(
            tuple(int(part) for part in skill.manifest.version.split("."))
            >= (2, 0, 5)
        ),
    )
    engine = compile_engine_contract(
        objective=objective,
        skill=skill,
        provider=provider,
        requested_model=requested_model,
    )
    return FrozenAgenticBuildPlan(
        versions=ordered,
        objective=objective,
        engine=engine,
        skill_instructions=render_skill_instructions(skill),
    )


def plan_checksum(plan: FrozenAgenticBuildPlan) -> str:
    """A compact test/audit identity; runtime authority uses the contracts above."""

    return sha256_value(
        {
            "source_versions": [item.subject_checksum for item in plan.versions],
            "objective": plan.objective.objective_checksum,
            "engine": plan.engine.engine_checksum,
            "instructions": sha256_value(plan.skill_instructions),
        }
    )
