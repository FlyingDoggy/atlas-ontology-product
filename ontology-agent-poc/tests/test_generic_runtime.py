from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ontology_agent import api as api_module
from ontology_agent.api import app
from ontology_agent.contracts import DataResourceBinding, RuntimePreparationError
from ontology_agent.generic_scenario import generic_semantic_binding
from ontology_agent.io import (
    DEFAULT_CASH_TRADING_SCENARIO_DIR,
    load_package,
    sha256_value,
)
from ontology_agent.lifecycle import AgentRuntime, FileResourceResolver
from ontology_agent.models import OntologyPackage
from ontology_agent.release import StudioReleases
from ontology_agent.runtime import analyze_snapshot
from ontology_agent.studio.builder import (
    BoundedBuilderOrchestrator,
    BuilderPhaseOutputV1,
    BuilderPhaseResponseV1,
)
from ontology_agent.studio.construction import (
    ConstructionDispositionV1,
    ConstructionReviewRequestV1,
    FileConstructionRunStore,
    StudioConstructionService,
)
from ontology_agent.studio.generic_workspace import GenericDraftWorkspaceService
from ontology_agent.studio.package_authoring import PackageDraftOperationsV1
from ontology_agent.studio.reviewer import (
    BoundedReviewerOrchestrator,
    ReviewerOutputV1,
    ReviewerResponseV1,
)
from ontology_agent.studio.skill_packages import load_skill_package
from ontology_agent.studio.source_library import (
    FileSourceLibraryStore,
    SourceIntakeBatchManifestV1,
    StudioSourceLibraryService,
)
from ontology_agent.studio.source_projection import (
    StudioAuthoringProjectionV1,
    build_authoring_projection,
)
from ontology_agent.studio.solutions import SolutionDisplayName, _write_blank_solution_files


PROJECT_ROOT = Path(__file__).parents[1]
HKEX_ROOT = PROJECT_ROOT.parent


def _service_request_package(root: Path) -> OntologyPackage:
    _write_blank_solution_files(
        root,
        solution_id="ontology.operations.service_request",
        scenario_id="scenario.operations.service_request",
        workspace_id="workspace.operations.service_request",
        display_name=SolutionDisplayName(
            en="Service Request Operations",
            zh="服务请求运营分析",
        ),
        description="Govern service-request definitions and analytics.",
        owner="actor.service_owner",
    )
    package = load_package(root / "ontology" / "package.yaml")
    source_id = "source.service_requirements"
    common = {
        "version": "1.0.0",
        "status": "confirmed",
        "owner": "actor.service_owner",
        "sources": [source_id],
        "decisions": [],
        "tags": [],
    }
    return OntologyPackage.model_validate(
        {
            **package.model_dump(mode="json"),
            "status": "confirmed",
            "scenario": {
                **package.scenario.model_dump(mode="json"),
                "status": "confirmed",
                "default_role": "ServiceAnalyst",
            },
            "sources": [
                *[item.model_dump(mode="json") for item in package.sources],
                {
                    "id": source_id,
                    "source_type": "requirement_transcription",
                    "title": "Service request requirements",
                    "locator": "source-library:service-request-requirements-v1",
                    "owner": "actor.service_owner",
                    "captured_on": date(2026, 8, 22),
                    "trust": "primary",
                    "notes": "Exact transcribed source used by the reviewed Draft.",
                },
            ],
            "actors": [
                {
                    **common,
                    "id": "actor.service_owner",
                    "name": {"en": "Service owner", "zh": "服务负责人"},
                    "definition": "Accountable owner of the service-request process.",
                    "roles": ["ServiceAnalyst", "RestrictedUser"],
                }
            ],
            "entities": [
                {
                    **common,
                    "id": "entity.service_request",
                    "name": {"en": "Service Request", "zh": "服务请求"},
                    "definition": "A request submitted by a customer and handled through closure.",
                    "primary_key": "property.service_request.id",
                    "grain": "one service request",
                    "lifecycle": "submitted to closed",
                }
            ],
            "properties": [
                {
                    **common,
                    "id": "property.service_request.id",
                    "name": {"en": "Service Request ID", "zh": "服务请求编号"},
                    "definition": "Unique identifier of one service request.",
                    "entity": "entity.service_request",
                    "data_type": "string",
                    "required": True,
                    "null_meaning": "not_allowed",
                },
                {
                    **common,
                    "id": "property.service_request.submitted_date",
                    "name": {"en": "Submitted Date", "zh": "提交日期"},
                    "definition": "Business date on which the request was submitted.",
                    "entity": "entity.service_request",
                    "data_type": "date",
                    "required": True,
                    "null_meaning": "not_allowed",
                },
            ],
            "metrics": [
                {
                    **common,
                    "id": "metric.service_request_count",
                    "name": {"en": "Service Request Count", "zh": "服务请求数量"},
                    "definition": "Distinct count of service requests in a governed period.",
                    "metric_type": "base",
                    "base_entity": "entity.service_request",
                    "result_grain": [],
                    "value_type": "integer",
                    "unit": "request",
                    "aggregation_semantics": "additive",
                    "formula": {
                        "op": "count_distinct",
                        "args": [
                            {"op": "field_ref", "ref": "property.service_request.id"}
                        ],
                    },
                    "query": {
                        "base_source": "data_source.service_requests",
                        "measure_property": "property.service_request.id",
                        "period_property": "property.service_request.submitted_date",
                        "date_property": "property.service_request.submitted_date",
                        "population_property": "property.service_request.id",
                        "required_joins": [],
                        "filters": [],
                    },
                    "allowed_dimensions": [],
                    "null_policy": "fail_validation",
                    "zero_denominator_policy": "refuse",
                }
            ],
            "data_sources": [
                {
                    **common,
                    "id": "data_source.service_requests",
                    "name": {"en": "Service Requests", "zh": "服务请求数据"},
                    "definition": "Approved logical schema for service-request analytics.",
                    "protocol": "tabular/v1",
                    "tables": [
                        {
                            "name": "service_requests",
                            "grain": "one service request",
                            "primary_key": ["request_id"],
                            "fields": [
                                {
                                    "name": "request_id",
                                    "data_type": "string",
                                    "nullable": False,
                                    "description": "Unique service-request identifier.",
                                },
                                {
                                    "name": "submitted_date",
                                    "data_type": "date",
                                    "nullable": False,
                                    "description": "Request submission date.",
                                },
                            ],
                        }
                    ],
                }
            ],
            "bindings": [
                {
                    **common,
                    "id": "binding.service_request.id",
                    "name": {"en": "Request ID mapping", "zh": "请求编号映射"},
                    "definition": "Map the logical request identifier to its physical field.",
                    "logical_target": "property.service_request.id",
                    "source": "data_source.service_requests",
                    "table": "service_requests",
                    "column": "request_id",
                    "data_type": "string",
                    "transformation": "identity",
                },
                {
                    **common,
                    "id": "binding.service_request.submitted_date",
                    "name": {"en": "Submitted date mapping", "zh": "提交日期映射"},
                    "definition": "Map the logical submission date to its physical field.",
                    "logical_target": "property.service_request.submitted_date",
                    "source": "data_source.service_requests",
                    "table": "service_requests",
                    "column": "submitted_date",
                    "data_type": "date",
                    "transformation": "identity",
                },
            ],
            "analysis_patterns": [
                {
                    **common,
                    "id": "analysis.service_request_definition",
                    "name": {"en": "Service request definition", "zh": "服务请求定义"},
                    "definition": "Return an approved ontology definition with its source identity.",
                    "intent": "evidence_audit",
                    "operation": "describe_governed_asset",
                    "required_metrics": ["metric.service_request_count"],
                    "required_dimensions": [],
                    "output_fields": ["asset_id", "definition", "source_ids"],
                    "failure_conditions": ["asset is not present in the active ontology"],
                },
                {
                    **common,
                    "id": "analysis.service_request_count",
                    "name": {"en": "Service request count", "zh": "服务请求数量"},
                    "definition": "Count service requests for a governed period.",
                    "intent": "metric_fact",
                    "operation": "count_service_requests",
                    "required_metrics": ["metric.service_request_count"],
                    "required_dimensions": [],
                    "output_fields": ["period", "request_count"],
                    "failure_conditions": ["period is missing", "runtime data tool is unavailable"],
                },
            ],
            "policies": [
                {
                    **common,
                    "id": "policy.service_request_access",
                    "name": {"en": "Service request access", "zh": "服务请求访问策略"},
                    "definition": "Allow governed service analysis only to service analysts.",
                    "allowed_roles": ["ServiceAnalyst"],
                    "denied_roles": ["RestrictedUser"],
                    "allowed_grains": ["ontology_definition"],
                    "denied_fields": ["property.service_request.submitted_date"],
                    "minimum_group_size": 1,
                }
            ],
            "questions": [
                {
                    **common,
                    "id": "question.service_request_definition",
                    "name": {"en": "Define service request", "zh": "定义服务请求"},
                    "definition": "Explain the approved meaning of a service request.",
                    "examples": ["What is a service request?", "什么是服务请求？"],
                    "analysis_pattern": "analysis.service_request_definition",
                    "required_inputs": [],
                    "expected_answer": "Approved definition and exact source identity.",
                },
                {
                    **common,
                    "id": "question.service_request_count",
                    "name": {"en": "Count service requests", "zh": "统计服务请求"},
                    "definition": "Count service requests in a specified period.",
                    "examples": ["How many service requests were closed?"],
                    "analysis_pattern": "analysis.service_request_count",
                    "required_inputs": ["period"],
                    "expected_answer": "A period-scoped request count.",
                },
            ],
        }
    )


def test_generic_runtime_answers_clarifies_and_refuses_from_one_active_release(
    tmp_path: Path,
) -> None:
    scenario_root = tmp_path / "service-request"
    package = _service_request_package(scenario_root)
    releases = StudioReleases(tmp_path / "published" / "releases")
    published = releases.publish(package)
    runtime = AgentRuntime(
        release_root=tmp_path / "published" / "releases",
        runtime_root=tmp_path / "published" / "runtime",
        resources=FileResourceResolver({"generic-service": scenario_root}),
    )
    binding = generic_semantic_binding(
        environment_id="service-request-demo",
        resource_root_id="generic-service",
    )

    assert binding.data_resources == ()
    prepared = runtime.prepare(published.ref, binding=binding)
    runtime.activate(prepared.ref)
    snapshot = runtime.open_active(
        "service-request-demo", package.package_id
    ).snapshot

    answered = analyze_snapshot(
        snapshot,
        question="What is a service request?",
        role="ServiceAnalyst",
        execution_dir=tmp_path / "executions",
    )
    clarify = analyze_snapshot(
        snapshot,
        question="How many service requests were closed?",
        role="ServiceAnalyst",
        execution_dir=tmp_path / "executions",
    )
    refused = analyze_snapshot(
        snapshot,
        question="Predict which customer will complain next month.",
        role="ServiceAnalyst",
        execution_dir=tmp_path / "executions",
    )
    denied_asset = analyze_snapshot(
        snapshot,
        question="Define Submitted Date.",
        role="ServiceAnalyst",
        execution_dir=tmp_path / "executions",
    )

    assert answered.status == "ANSWERED"
    assert answered.facts["asset"]["id"] == "entity.service_request"
    assert answered.evidence[0].source_ids == ("source.service_requirements",)
    assert clarify.status == "CLARIFY"
    assert clarify.boundary_code == "RUNTIME_DATA_BINDING_REQUIRED"
    assert refused.status == "REFUSED"
    assert refused.boundary_code == "UNSUPPORTED_CAPABILITY"
    assert denied_asset.status == "REFUSED"
    assert denied_asset.boundary_code == "FIELD_NOT_ALLOWED"
    assert tuple((tmp_path / "executions").glob("exec.*.json"))


def test_generic_semantic_runtime_rejects_data_resources(tmp_path: Path) -> None:
    scenario_root = tmp_path / "service-request"
    package = _service_request_package(scenario_root)
    releases = StudioReleases(tmp_path / "published" / "releases")
    published = releases.publish(package)
    runtime = AgentRuntime(
        release_root=tmp_path / "published" / "releases",
        runtime_root=tmp_path / "published" / "runtime",
        resources=FileResourceResolver({"generic-service": scenario_root}),
    )
    binding = generic_semantic_binding(
        environment_id="service-request-demo",
        resource_root_id="generic-service",
    ).model_copy(
        update={
            "data_resources": (
                DataResourceBinding(
                    source_id="source.unreviewed",
                    resource_ref="input/solution-brief.md",
                ),
            )
        }
    )

    with pytest.raises(RuntimePreparationError, match="Semantic-only"):
        runtime.prepare(published.ref, binding=binding)


class _ServiceRequestBuilderModel:
    """Deterministic model double for the public Builder contract.

    The fixture is a third business case, while the production orchestrator, Skill
    package and typed operation boundary remain exactly the same as every Solution.
    """

    def __init__(self, target: OntologyPackage) -> None:
        self.target = target

    def generate(self, request):
        fragment_id = request.evidence_fragments[0].fragment_id
        proposals = []
        for collection in request.allowed_collections:
            for item in getattr(self.target, collection):
                payload = item.model_dump(mode="json")
                payload["status"] = "proposed"
                proposals.append(
                    {
                        "contract": "builder-proposal/v1",
                        "proposal_id": f"proposal.{collection}.{item.id}",
                        "operation": {
                            "action": "UPSERT",
                            "collection": collection,
                            "object_id": item.id,
                            "payload": payload,
                        },
                        "evidence_fragment_ids": [fragment_id],
                        "rationale": (
                            "The exact service-request transcription supports this "
                            "candidate; a human must still review it."
                        ),
                        "assumptions": [],
                        "confidence": 0.9,
                    }
                )
        output = BuilderPhaseOutputV1.model_validate(
            {
                "contract": "builder-phase-output/v1",
                "phase": request.phase,
                "request_digest": request.request_digest,
                "proposals": proposals,
                "gaps": [],
                "done": True,
            }
        )
        return BuilderPhaseResponseV1(
            requested_model="contract-test-model",
            response_model="contract-test-model",
            provider_request_id=f"service-request-{request.phase.lower()}",
            output=output,
            output_digest=sha256_value(output),
        )


class _ServiceRequestReviewerModel:
    def review(self, request):
        output = ReviewerOutputV1(
            request_digest=request.request_digest,
            findings=(),
            done=True,
        )
        return ReviewerResponseV1(
            requested_model="contract-test-model",
            response_model="contract-test-model",
            provider_request_id="service-request-review",
            output=output,
            output_digest=sha256_value(output),
        )


class _CashPackageBuilderModel:
    """Deterministic Cash fixture behind the same bounded Builder port as Qwen."""

    def __init__(self, target: OntologyPackage) -> None:
        self.target = target

    def generate(self, request):
        fragment_id = request.evidence_fragments[0].fragment_id
        proposals = []
        for collection in request.allowed_collections:
            for item in getattr(self.target, collection):
                payload = item.model_dump(mode="json")
                payload["status"] = "proposed"
                # Source authority is replaced by the orchestrator from the cited
                # exact fragment. A model cannot import decisions from a reference
                # package into a new Solution.
                payload["decisions"] = []
                proposals.append(
                    {
                        "contract": "builder-proposal/v1",
                        "proposal_id": f"proposal.cash.{collection}.{item.id}",
                        "operation": {
                            "action": "UPSERT",
                            "collection": collection,
                            "object_id": item.id,
                            "payload": payload,
                        },
                        "evidence_fragment_ids": [fragment_id],
                        "rationale": (
                            "The selected Cash Trading source versions support this "
                            "review candidate; a human remains the publication authority."
                        ),
                        "assumptions": [],
                        "confidence": 0.9,
                    }
                )
        output = BuilderPhaseOutputV1.model_validate(
            {
                "contract": "builder-phase-output/v1",
                "phase": request.phase,
                "request_digest": request.request_digest,
                "proposals": proposals,
                "gaps": [],
                "done": True,
            }
        )
        return BuilderPhaseResponseV1(
            requested_model="contract-test-model",
            response_model="contract-test-model",
            provider_request_id=f"cash-e2e-{request.phase.lower()}",
            output=output,
            output_digest=sha256_value(output),
        )


def _cash_build_target() -> OntologyPackage:
    """Keep the reviewed Cash semantics while respecting one bounded phase call."""

    target = load_package(
        DEFAULT_CASH_TRADING_SCENARIO_DIR / "ontology" / "package.yaml"
    )
    omitted_relationship_ids = {
        "relationship.trade_participant",
        "relationship.order_participant",
    }
    omitted_property_ids = {
        "property.order.order_id",
        "property.order.trading_date",
        "property.order.order_status",
        "property.order.transaction_timestamp",
        "property.instrument.primary_symbol",
        "property.calendar.is_trading_day",
    }
    return target.model_copy(
        update={
            "properties": tuple(
                item
                for item in target.properties
                if item.id not in omitted_property_ids
            ),
            "relationships": tuple(
                item
                for item in target.relationships
                if item.id not in omitted_relationship_ids
            ),
        }
    )


def test_third_case_runs_from_blank_solution_through_build_review_release_and_ask(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario_root = tmp_path / "service-request"
    target = _service_request_package(scenario_root)
    workspace_id = "workspace.operations.service_request"
    releases = StudioReleases(tmp_path / "published" / "releases")
    workspace = GenericDraftWorkspaceService(
        tmp_path / "studio" / "workspaces",
        scenario_root,
        releases,
    )
    source_body = (
        "A service request has one request identifier and submission date. "
        "Service analysts may inspect its approved definition and count requests "
        "for a stated period."
    )
    intake = {
        "assets": [
            {
                "asset_id": "source.service_requirements",
                "kind": "requirement_transcription",
                "title": "Service request requirements",
                "locator": "source-library:service-request-requirements-v1",
                "source_version_id": "source-version.service-request-requirements-v1",
                "checksum": hashlib.sha256(source_body.encode()).hexdigest(),
                "registered_at": "2026-08-22T00:00:00Z",
                "content_text": source_body,
            }
        ]
    }
    construction = StudioConstructionService(
        store=FileConstructionRunStore(tmp_path / "studio" / "construction"),
        workspace=workspace,
        workspace_id=workspace_id,
        package=workspace.candidate_package(workspace_id),
        intake=intake,
        authoring=StudioAuthoringProjectionV1(
            requirements=(),
            metric_candidates=(),
            source_mode="CANONICAL_FALLBACK",
        ),
        builder=BoundedBuilderOrchestrator(
            model=_ServiceRequestBuilderModel(target),
            skill=load_skill_package("ontology-build", "1.1.0"),
        ),
        reviewer=BoundedReviewerOrchestrator(
            model=_ServiceRequestReviewerModel(),
            skill=load_skill_package("ontology-review", "1.0.0"),
        ),
        engine=None,
    )

    initial = workspace.get(workspace_id)
    run = construction.start(expected_revision=initial.revision)
    assert run.engine_status == "COMPLETED"
    assert workspace.get(workspace_id).revision == initial.revision
    assert {item.stage for item in run.stage_receipts} >= {
        "BUILDER_AGENT",
        "REVIEWER_AGENT",
    }
    assert all(item.compile_eligible for item in run.candidates)

    reviewed = construction.review(
        run.run_id,
        ConstructionReviewRequestV1(
            expected_revision=run.base_revision,
            reviewer="service-owner.demo",
            dispositions=tuple(
                ConstructionDispositionV1(
                    candidate_id=item.candidate_id,
                    action="ACCEPT",
                    note="Accepted against the exact source and review findings.",
                    blocks_release=False,
                )
                for item in run.candidates
            ),
        ),
    )
    assert reviewed.decision.status == "APPLIED"

    confirmed_package = workspace.candidate_package(workspace_id)
    confirmed_assets = []
    for collection in (
        "actors",
        "processes",
        "entities",
        "properties",
        "relationships",
        "dimensions",
        "rules",
        "metrics",
        "data_sources",
        "bindings",
        "joins",
        "sql_contracts",
        "analysis_patterns",
        "policies",
        "questions",
    ):
        confirmed_assets.extend(getattr(confirmed_package, collection))
    assert confirmed_assets
    assert all(item.status.value == "confirmed" for item in confirmed_assets)
    assert len(reviewed.decision.applied) == len(confirmed_assets) + 1
    confirmed = workspace.get(workspace_id)
    validated = workspace.validate(
        expected_revision=confirmed.revision,
        workspace_id=workspace_id,
    )
    assert validated.validation.status == "PASS"
    published_workspace, publication = workspace.publish(
        expected_revision=validated.revision,
        workspace_id=workspace_id,
    )
    assert published_workspace.last_published == publication.ref

    runtime = AgentRuntime(
        release_root=tmp_path / "published" / "releases",
        runtime_root=tmp_path / "published" / "runtime",
        resources=FileResourceResolver({"generic-service": scenario_root}),
    )
    prepared = runtime.prepare(
        publication.ref,
        binding=generic_semantic_binding(
            environment_id="service-request-demo",
            resource_root_id="generic-service",
        ),
    )
    runtime.activate(prepared.ref)
    snapshot = runtime.open_active(
        "service-request-demo", target.package_id
    ).snapshot

    answered = analyze_snapshot(
        snapshot,
        question="What is a service request?",
        role="ServiceAnalyst",
        execution_dir=tmp_path / "executions",
    )
    clarify = analyze_snapshot(
        snapshot,
        question="How many service requests were closed?",
        role="ServiceAnalyst",
        execution_dir=tmp_path / "executions",
    )
    refused = analyze_snapshot(
        snapshot,
        question="Predict next month's customer complaints.",
        role="ServiceAnalyst",
        execution_dir=tmp_path / "executions",
    )
    assert answered.status == "ANSWERED"
    assert clarify.status == "CLARIFY"
    assert refused.status == "REFUSED"

    config = {
        "generic": True,
        "environment_id": "service-request-demo",
        "resource_root_id": "generic-service",
        "scenario_dir": scenario_root,
        "binding": generic_semantic_binding(
            environment_id="service-request-demo",
            resource_root_id="generic-service",
        ),
        "certification": None,
        "certification_profile": None,
    }
    monkeypatch.setattr(api_module, "DEFAULT_PUBLISHED_DIR", tmp_path / "published")
    monkeypatch.setattr(api_module, "DEFAULT_EXECUTION_DIR", tmp_path / "api-executions")
    monkeypatch.setattr(api_module, "_runtime_configuration", lambda _solution_id: config)
    client = TestClient(app)
    questions = client.get(f"/api/solutions/{target.package_id}/questions")
    assert questions.status_code == 200
    public_case = next(
        item
        for item in questions.json()["cases"]
        if item["question"] == "What is a service request?"
    )
    api_answer = client.post(
        f"/api/solutions/{target.package_id}/analyze",
        json={
            "question_case_id": public_case["case_id"],
            "question": public_case["question"],
        },
    )
    api_runtime = client.get(
        f"/api/solutions/{target.package_id}/runtime/active"
    )
    assert api_answer.status_code == 200
    assert api_answer.json()["status"] == "ANSWERED"
    assert api_answer.json()["llm"]["status"] == "DETERMINISTIC_ONLY"
    assert api_runtime.status_code == 200
    assert api_runtime.json()["default_role"] == "ServiceAnalyst"


def test_cash_materials_build_a_blank_solution_through_human_review_and_release(
    tmp_path: Path,
) -> None:
    """Cash acceptance: five physical files become one reviewed immutable release."""

    scenario_root = tmp_path / "cash-build"
    workspace_id = "workspace.cash_trading.e2e"
    _write_blank_solution_files(
        scenario_root,
        solution_id="ontology.exchange_analytics.cash_trading.e2e",
        scenario_id="scenario.exchange_analytics.cash_trading.e2e",
        workspace_id=workspace_id,
        display_name=SolutionDisplayName(
            en="Cash Market Order and Trading Activity Monitoring",
            zh="现金市场订单与成交活动监控",
        ),
        description=(
            "Build a governed Cash Trading ontology from registered business material."
        ),
        owner="actor.cash_trading_solution_owner",
    )
    releases = StudioReleases(tmp_path / "published" / "releases")
    workspace = GenericDraftWorkspaceService(
        tmp_path / "studio" / "workspaces",
        scenario_root,
        releases,
    )
    initial = workspace.get(workspace_id)
    configured = workspace.configure_authoring_language(
        "en",
        expected_revision=initial.revision,
        workspace_id=workspace_id,
    )

    material_root = HKEX_ROOT / "HKEX DTT Input"
    physical_files = (
        material_root
        / "HKEX_Analytics_Scenario_Input_Template_with_ADT_Reference_v20260819.xlsx",
        material_root / "order_trade_activities_data_dictionary.xlsx",
        material_root / "cash_trading_sample_data.xlsx",
        material_root / "email screenshot.jpeg",
        DEFAULT_CASH_TRADING_SCENARIO_DIR / "sql" / "reference_controls.sql",
    )
    library = StudioSourceLibraryService(
        FileSourceLibraryStore(tmp_path / "studio" / "sources")
    )
    manifest = SourceIntakeBatchManifestV1.model_validate(
        {
            "idempotency_key": "cash-trading-e2e-materials-v1",
            "items": [
                {
                    "client_file_id": "requirements-and-metrics",
                    "original_name": physical_files[0].name,
                    "declared_media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "registrations": [
                        {
                            "kind": "requirement_transcription",
                            "title": "Cash Trading requirements and analytical workflow",
                        },
                        {
                            "kind": "metric_transcription",
                            "title": "Eight Cash Trading metric definitions",
                        },
                    ],
                },
                {
                    "client_file_id": "data-model-and-dictionary",
                    "original_name": physical_files[1].name,
                    "declared_media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "registrations": [
                        {
                            "kind": "data_model",
                            "title": "Order and trading logical data model",
                        },
                        {
                            "kind": "data_dictionary",
                            "title": "Order and trading field dictionary",
                        },
                    ],
                },
                {
                    "client_file_id": "sample-data",
                    "original_name": physical_files[2].name,
                    "declared_media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "registrations": [
                        {
                            "kind": "data_dictionary",
                            "title": "Cash Trading data dictionary and sample data",
                        }
                    ],
                },
                {
                    "client_file_id": "source-boundary-email",
                    "original_name": physical_files[3].name,
                    "declared_media_type": "image/jpeg",
                    "registrations": [
                        {
                            "kind": "other",
                            "title": "Material source and limitation record",
                        }
                    ],
                },
                {
                    "client_file_id": "reference-sql",
                    "original_name": physical_files[4].name,
                    "declared_media_type": "text/sql",
                    "registrations": [
                        {
                            "kind": "sql",
                            "title": "Internally synthesized reference control SQL",
                        }
                    ],
                },
            ],
        }
    )
    bodies = tuple(path.read_bytes() for path in physical_files)
    receipt = library.register_batch(
        workspace_id=workspace_id,
        manifest=manifest,
        bodies=bodies,
    )
    current_sources = library.list_current(workspace_id)

    assert receipt.failures == ()
    assert len(receipt.physical_files) == 5
    assert len(receipt.registrations) == 7
    assert len(current_sources) == 7
    assert sum(item.capability == "ARCHIVED_ONLY" for item in receipt.physical_files) == 1
    physical_checksums = {item.content_checksum for item in receipt.physical_files}
    assert {
        hashlib.sha256(library.read_exact(item)).hexdigest()
        for item in current_sources
    } == physical_checksums

    package = workspace.candidate_package(workspace_id)
    intake = {
        "contract": "cash-trading-e2e-intake/v1",
        "assets": library.current_intake_assets(
            workspace_id,
            include_parsed_attachments=True,
        ),
    }
    authoring = build_authoring_projection(
        package=package,
        intake=intake,
        scenario_dir=DEFAULT_CASH_TRADING_SCENARIO_DIR,
    )
    construction = StudioConstructionService(
        store=FileConstructionRunStore(tmp_path / "studio" / "construction"),
        workspace=workspace,
        workspace_id=workspace_id,
        package=package,
        intake=intake,
        authoring=authoring,
        builder=BoundedBuilderOrchestrator(
            model=_CashPackageBuilderModel(_cash_build_target()),
            skill=load_skill_package("ontology-build", "1.1.0"),
        ),
        reviewer=BoundedReviewerOrchestrator(
            model=_ServiceRequestReviewerModel(),
            skill=load_skill_package("ontology-review", "1.0.0"),
        ),
        engine=None,
    )

    run = construction.start(expected_revision=configured.revision)

    assert authoring.source_mode == "EXACT_TRANSCRIPTION"
    assert run.status == "NEEDS_REVIEW"
    assert run.engine_status == "COMPLETED"
    assert run.authoring_language == "en"
    assert len(run.selected_sources) == 7
    assert workspace.get(workspace_id).revision == configured.revision
    required_metric_ids = {
        "metric.order_rejection_rate",
        "metric.order_fill_rate",
        "metric.trade_capture_latency_ms",
        "metric.active_client_trading_volume",
        "metric.client_order_completion_rate",
        "metric.cancel_to_trade_ratio",
        "metric.order_to_trade_ratio",
        "metric.potential_self_trade_rate",
    }
    metric_targets = {
        item.proposed_operation.object_id
        for item in run.candidates
        if item.candidate_type == "METRIC" and item.proposed_operation is not None
    }
    assert required_metric_ids <= metric_targets
    assert {
        "OBJECT",
        "PROPERTY",
        "LINK",
        "METRIC",
        "DATA_SOURCE",
        "MAPPING",
    } <= {item.candidate_type for item in run.candidates}

    reviewed = construction.review(
        run.run_id,
        ConstructionReviewRequestV1(
            expected_revision=run.base_revision,
            reviewer="cash-domain-owner.demo",
            dispositions=tuple(
                ConstructionDispositionV1(
                    candidate_id=item.candidate_id,
                    action="ACCEPT" if item.compile_eligible else "REJECT",
                    note=(
                        "Accepted against the exact registered Cash Trading evidence."
                        if item.compile_eligible
                        else "Retained as evidence only; it is not an ontology mutation."
                    ),
                    blocks_release=False,
                )
                for item in run.candidates
            ),
        ),
    )

    assert reviewed.decision.status == "APPLIED"
    assert reviewed.decision.server_blockers == ()
    assert reviewed.decision.resulting_revision > run.base_revision
    confirmed_package = workspace.candidate_package(workspace_id)
    assert required_metric_ids <= {item.id for item in confirmed_package.metrics}
    assert {item.id for item in confirmed_package.data_sources}
    assert {item.id for item in confirmed_package.bindings}
    assert {
        item.status.value
        for collection in (
            "actors",
            "processes",
            "entities",
            "properties",
            "relationships",
            "dimensions",
            "rules",
            "metrics",
            "data_sources",
            "bindings",
            "joins",
            "analysis_patterns",
            "policies",
            "questions",
        )
        for item in getattr(confirmed_package, collection)
    } == {"confirmed"}

    confirmed = workspace.get(workspace_id)
    validated = workspace.validate(
        expected_revision=confirmed.revision,
        workspace_id=workspace_id,
    )
    assert validated.validation.status == "PASS", validated.validation.report
    published_workspace, publication = workspace.publish(
        expected_revision=validated.revision,
        workspace_id=workspace_id,
    )
    assert published_workspace.last_published == publication.ref
    assert publication.ref.package_id == "ontology.exchange_analytics.cash_trading.e2e"
