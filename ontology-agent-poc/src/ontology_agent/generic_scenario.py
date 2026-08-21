from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Literal, Mapping

from .contracts import PublicationError, RuntimeBindingSpec, VerifiedSnapshot
from .io import DEFAULT_PROJECT_ROOT, file_checksum, sha256_value, write_json
from .models import (
    AnalysisPlan,
    AnalysisResponse,
    EvidenceRecord,
    Metric,
    OntologyPackage,
    StepExecution,
    ValidationCheck,
)
from .scenario import (
    BoundAnalysisGoal,
    ScenarioAdapterDescriptor,
    ScenarioAdapterError,
    ScenarioEvaluation,
    ScenarioValidation,
)


GENERIC_ADAPTER_ID = "generic-ontology-analytics"
GENERIC_ADAPTER_VERSION = "1.0.0"
GENERIC_EVALUATION_SUITE = "generic.ontology.runtime.v1"
GENERIC_EVALUATION_CASE_IDS = ("semantic.definition.boundary",)

_IMPLEMENTATION_FILES = (
    "generic_scenario.py",
    "lifecycle.py",
    "models.py",
    "runtime.py",
    "runtime_snapshot.py",
    "scenario.py",
)


def generic_semantic_binding(
    *, environment_id: str, resource_root_id: str
) -> RuntimeBindingSpec:
    """Bind a release for ontology-backed answers without inventing a data engine."""

    return RuntimeBindingSpec(
        environment_id=environment_id,
        resource_root_id=resource_root_id,
        adapter_id=GENERIC_ADAPTER_ID,
        adapter_version=GENERIC_ADAPTER_VERSION,
        query_engine_id="ontology.catalog",
        query_engine_version="1",
        dataset_manifest_ref="agent/experience.json",
        data_resources=(),
    )


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9\u3400-\u9fff]+", " ", value.casefold()).strip()


def _is_chinese(value: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", value))


def _eligible_policies(package: OntologyPackage, role: str):
    return tuple(
        policy
        for policy in package.policies
        if role in policy.allowed_roles and role not in policy.denied_roles
    )


def _matching_question(package: OntologyPackage, question: str):
    normalized = _normalize(question)
    return next(
        (
            item
            for item in package.questions
            if any(_normalize(example) == normalized for example in item.examples)
        ),
        None,
    )


def _question_cases(package: OntologyPackage) -> tuple[dict[str, object], ...]:
    """Project governed package Questions into the common Agent UI contract."""

    patterns = {item.id: item for item in package.analysis_patterns}
    cases: list[dict[str, object]] = []
    for governed_question in package.questions:
        pattern = patterns.get(governed_question.analysis_pattern)
        if pattern is None:
            continue
        base_id = re.sub(
            r"[^a-z0-9._-]+", "-", governed_question.id.casefold()
        ).strip("-.")
        for index, question in enumerate(governed_question.examples, start=1):
            language = "zh" if _is_chinese(question) else "en"
            cases.append(
                {
                    "case_id": f"{base_id}.{language}.{index}",
                    "language": language,
                    "question": question,
                    "expected_intent": pattern.intent,
                    "required_tools": [pattern.operation],
                }
            )
            if len(cases) == 64:
                return tuple(cases)
    return tuple(cases)


def generic_question_family(package: OntologyPackage) -> dict[str, object]:
    """Return the same public question-family shape for every generic Solution."""

    cases = _question_cases(package)
    family_id = re.sub(
        r"[^a-z0-9._-]+", "-", f"{package.package_id}.questions".casefold()
    ).strip("-.")
    exact_family = {
        "contract": "registered-question-family/v1",
        "family_id": family_id,
        "version": package.version,
        "classification": "constructed_synthetic",
        "cases": cases,
    }
    return {
        "family_id": family_id,
        "family_checksum": sha256_value(exact_family),
        "classification": "constructed_synthetic",
        "cases": list(cases),
    }


def generic_bound_goal(
    package: OntologyPackage,
    *,
    case_id: str | None,
    question: str,
) -> BoundAnalysisGoal | None:
    """Resolve only an exact UI case; free-form text never gains extra authority."""

    if case_id is None:
        return None
    case = next(
        (
            item
            for item in _question_cases(package)
            if item["case_id"] == case_id and item["question"] == question
        ),
        None,
    )
    if case is None:
        return None
    return BoundAnalysisGoal(
        intent=str(case["expected_intent"]),
        tool_ids=tuple(str(item) for item in case["required_tools"]),
        language=str(case["language"]),
    )


def _matching_asset(package: OntologyPackage, question: str):
    normalized = _normalize(question)
    assets = (
        *package.entities,
        *package.metrics,
        *package.properties,
        *package.relationships,
        *package.dimensions,
        *package.rules,
        *package.processes,
        *package.actors,
    )
    matches = []
    for asset in assets:
        aliases = (asset.id, asset.name.en, asset.name.zh)
        score = max(
            (
                len(alias_normalized)
                for alias in aliases
                if (alias_normalized := _normalize(alias))
                and alias_normalized in normalized
            ),
            default=0,
        )
        if score:
            matches.append((score, asset))
    return max(matches, key=lambda item: item[0])[1] if matches else None


def _boundary(
    status: Literal["CLARIFY", "REFUSED"],
    answer: str,
    code: str,
    snapshot: VerifiedSnapshot,
) -> AnalysisResponse:
    return AnalysisResponse(
        status=status,
        answer=answer,
        snapshot_checksum=snapshot.snapshot_checksum,
        boundary_code=code,
    )


def _definition_answer(
    snapshot: VerifiedSnapshot,
    *,
    question: str,
    role: str,
    asset,
    policy,
    execution_dir: Path,
) -> AnalysisResponse:
    execution_id = "exec." + uuid.uuid4().hex
    plan_seed = {
        "plan_id": "plan." + uuid.uuid4().hex,
        "intent": "evidence_audit",
        "question": question,
        "snapshot_checksum": snapshot.snapshot_checksum,
        "steps": [],
    }
    plan = AnalysisPlan(**plan_seed, plan_hash=sha256_value(plan_seed))
    step = StepExecution(
        step_id="semantic_lookup",
        status="PASS",
        rows=({"asset_id": asset.id, "source_ids": list(asset.sources)},),
    )
    asset_digest = sha256_value(asset)
    evidence = EvidenceRecord(
        claim_id="claim." + uuid.uuid4().hex,
        claim_type="definition",
        claim=f"{asset.id} is defined by the active ontology release.",
        result_path="facts.asset.definition",
        value=asset.definition,
        display_value=asset.definition,
        execution_id=execution_id,
        snapshot_checksum=snapshot.snapshot_checksum,
        plan_hash=plan.plan_hash,
        dataset_checksum=snapshot.dataset_checksum,
        policy_id=policy.id,
        policy_decision_id=f"{policy.id}:{role}:ALLOW",
        query_or_operator_hashes=(asset_digest,),
        metric_ids=(asset.id,) if isinstance(asset, Metric) else (),
        metric_versions=(asset.version,) if isinstance(asset, Metric) else (),
        mapping_ids=(),
        source_ids=asset.sources,
        step_ids=(step.step_id,),
    )
    label = asset.name.zh if _is_chinese(question) else asset.name.en
    response = AnalysisResponse(
        status="ANSWERED",
        answer=f"{label}: {asset.definition}",
        execution_id=execution_id,
        snapshot_checksum=snapshot.snapshot_checksum,
        plan=plan,
        steps=(step,),
        facts={
            "asset": {
                "id": asset.id,
                "name": asset.name.model_dump(mode="json"),
                "definition": asset.definition,
                "source_ids": list(asset.sources),
            }
        },
        evidence=(evidence,),
    )
    write_json(execution_dir / f"{execution_id}.json", response.model_dump(mode="json"))
    return response


class GenericAnalyticScenarioAdapter:
    """One case-neutral adapter for capabilities declared by an active package.

    The first generic execution level intentionally supports ontology-definition
    lookup only. Numeric analysis remains closed until an approved data tool is
    bound; the adapter clarifies instead of manufacturing a result.
    """

    @property
    def descriptor(self) -> ScenarioAdapterDescriptor:
        return ScenarioAdapterDescriptor(
            adapter_id=GENERIC_ADAPTER_ID,
            adapter_version=GENERIC_ADAPTER_VERSION,
            query_engine_id="ontology.catalog",
            query_engine_version="1",
            certification_profiles={},
            evaluation_suite_id=GENERIC_EVALUATION_SUITE,
            evaluation_case_ids=GENERIC_EVALUATION_CASE_IDS,
            data_binding_policy="NONE",
        )

    def build_manifest(
        self, project_root: Path = DEFAULT_PROJECT_ROOT
    ) -> dict[str, object]:
        source_root = Path(__file__).resolve().parent
        files = {
            f"src/ontology_agent/{name}": file_checksum(source_root / name)
            for name in _IMPLEMENTATION_FILES
            if (source_root / name).is_file()
        }
        return {
            "contract": "scenario-adapter-build/v1",
            "adapter_id": GENERIC_ADAPTER_ID,
            "adapter_version": GENERIC_ADAPTER_VERSION,
            "query_engine": {"id": "ontology.catalog", "version": "1"},
            "capability": {
                "mode": "semantic-only",
                "operations": ["describe_governed_asset"],
            },
            "evaluation_suite": {
                "suite_id": GENERIC_EVALUATION_SUITE,
                "case_ids": list(GENERIC_EVALUATION_CASE_IDS),
            },
            "files": dict(sorted(files.items())),
        }

    def validate(
        self,
        package: OntologyPackage,
        *,
        binding: RuntimeBindingSpec | None = None,
        resource_paths: Mapping[str, Path] | None = None,
        dataset_manifest_path: Path | None = None,
    ) -> ScenarioValidation:
        checks: list[ValidationCheck] = []
        if binding is not None:
            descriptor = self.descriptor
            if (
                binding.query_engine_id != descriptor.query_engine_id
                or binding.query_engine_version != descriptor.query_engine_version
            ):
                raise ScenarioAdapterError(
                    "Generic semantic runtime requires ontology.catalog contract v1"
                )
            if resource_paths:
                raise ScenarioAdapterError(
                    "Semantic-only runtime cannot accept data resource bindings"
                )
            if dataset_manifest_path is None or not dataset_manifest_path.is_file():
                raise ScenarioAdapterError(
                    "Generic semantic runtime identity manifest is unavailable"
                )
        checks.append(
            ValidationCheck(
                check_id="GENERIC_SEMANTIC_RUNTIME_CONTRACT",
                category="semantic",
                status=(
                    "PASS"
                    if package.questions and package.policies
                    else "FAIL"
                ),
                message="The release declares at least one governed question and access policy",
                details={
                    "question_count": len(package.questions),
                    "policy_count": len(package.policies),
                },
            )
        )
        return ScenarioValidation(checks=tuple(checks))

    def evaluate(
        self,
        snapshot: VerifiedSnapshot,
        *,
        control_dir: Path | None,
        execution_dir: Path,
    ) -> ScenarioEvaluation:
        passed = bool(snapshot.package.questions and snapshot.package.policies)
        return ScenarioEvaluation(
            checks=(),
            suite={
                "suite_id": GENERIC_EVALUATION_SUITE,
                "status": "PASS" if passed else "FAIL",
                "case_count": 1,
                "cases": [
                    {
                        "id": GENERIC_EVALUATION_CASE_IDS[0],
                        "status": "PASS" if passed else "FAIL",
                        "defects": [] if passed else ["No governed question or policy"],
                    }
                ],
                "oracle": "active ontology release contract",
                "oracle_defects": {},
            },
        )

    def analyze(
        self,
        snapshot: VerifiedSnapshot,
        *,
        question: str,
        role: str,
        execution_dir: Path,
        bound_goal: BoundAnalysisGoal | None = None,
    ) -> AnalysisResponse:
        from .runtime_snapshot import verify_snapshot_handle

        try:
            verify_snapshot_handle(snapshot)
        except PublicationError:
            return AnalysisResponse(
                status="FAILED",
                answer="The active ontology snapshot failed integrity verification.",
                boundary_code="SNAPSHOT_VERIFICATION_FAILED",
            )
        policies = _eligible_policies(snapshot.package, role)
        if not policies:
            return _boundary(
                "REFUSED",
                "The active policy does not allow this role to use the requested capability.",
                "ROLE_NOT_ALLOWED",
                snapshot,
            )
        registered = _matching_question(snapshot.package, question)
        pattern = (
            next(
                (
                    item
                    for item in snapshot.package.analysis_patterns
                    if registered is not None
                    and item.id == registered.analysis_pattern
                ),
                None,
            )
            if registered is not None
            else None
        )
        if bound_goal is not None and (
            pattern is None
            or bound_goal.intent != pattern.intent
            or bound_goal.tool_ids != (pattern.operation,)
        ):
            return _boundary(
                "REFUSED",
                "The grounded request is outside the capability declared by the active release.",
                "BOUND_GOAL_CAPABILITY_MISMATCH",
                snapshot,
            )
        asset = _matching_asset(snapshot.package, question)
        asset_policy = next(
            (
                policy
                for policy in policies
                if asset is not None and asset.id not in policy.denied_fields
            ),
            None,
        )
        if (
            asset is not None
            and asset_policy is not None
            and (pattern is None or pattern.operation == "describe_governed_asset")
            and any(
                marker in _normalize(question)
                for marker in ("what is", "define", "explain", "什么是", "定义", "解释")
            )
        ):
            return _definition_answer(
                snapshot,
                question=question,
                role=role,
                asset=asset,
                policy=asset_policy,
                execution_dir=execution_dir,
            )
        if asset is not None and asset_policy is None:
            return _boundary(
                "REFUSED",
                "The active policy does not allow this role to inspect the requested ontology asset.",
                "FIELD_NOT_ALLOWED",
                snapshot,
            )
        if registered is not None:
            return _boundary(
                "CLARIFY",
                "This question is governed, but its approved runtime data tool is not bound. Specify the required inputs after the data contract is activated.",
                "RUNTIME_DATA_BINDING_REQUIRED",
                snapshot,
            )
        return _boundary(
            "REFUSED",
            "The active ontology does not declare a supported capability for this question.",
            "UNSUPPORTED_CAPABILITY",
            snapshot,
        )
