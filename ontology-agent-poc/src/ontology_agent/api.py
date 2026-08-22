from __future__ import annotations

import json
import os
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .adt_scenario import (
    ADT_CERTIFICATION_PROFILE,
    adt_golden_certification,
    adt_synthetic_binding,
)
from .cash_trading_scenario import (
    CASH_CERTIFICATION_PROFILE,
    CASH_PACKAGE_ID,
    cash_trading_golden_certification,
    cash_trading_synthetic_binding,
)
from .contracts import ReleaseRef, RuntimeSnapshotRef
from .generic_scenario import (
    generic_bound_goal,
    generic_question_family,
    generic_semantic_binding,
)
from .durable_lifecycle import DurableLifecycleSettings
from .io import (
    DEFAULT_CASH_TRADING_SCENARIO_DIR,
    DEFAULT_PACKAGE_PATH,
    DEFAULT_PUBLISHED_DIR,
    DEFAULT_SCENARIO_DIR,
    DEFAULT_STUDIO_DIR,
    file_checksum,
    load_package,
    sha256_value,
)
from .lifecycle import (
    AgentRuntime,
    FileResourceResolver,
)
from .llm_agent import _gateway_transport, run_engineering_demo_grounding
from .llm_contracts import (
    engineering_demo_status,
    load_egress_decision,
    load_evaluation_manifest,
    load_question_family,
    load_rollout_record,
    load_run_profile,
    public_question_family,
)
from .llm_contracts import EngineeringDemoResponse
from .publisher import (
    PublicationError,
    list_published_snapshots,
    load_verified_snapshot,
)
from .product_context import (
    ProductContextService,
    ProductContextV1,
    ProductInfrastructureError,
    ProductInfrastructureSettings,
    legacy_product_context,
)
from .release import StudioReleases
from .runtime import (
    DEFAULT_EXECUTION_DIR,
    analyze_latest,
    analyze_snapshot,
    load_execution,
)
from .semantic_change import (
    CreateSemanticChangeRequestV1,
    FileSemanticChangeRequestStore,
    SemanticChangeError,
    build_semantic_change_request,
)
from .solution_adapters import (
    ADT_STUDIO_ADAPTER_ID,
    CASH_TRADING_STUDIO_ADAPTER_ID,
    GENERIC_STUDIO_ADAPTER_ID,
    ADTStudioAdapter,
    CashTradingStudioAdapter,
    GenericStudioAdapter,
)
from .solution_llm import attempt_solution_grounding, deterministic_only
from .studio.cash_workspace import CashTradingDraftWorkspaceService
from .studio.generic_workspace import GenericDraftWorkspaceService
from .studio.construction import (
    ConstructionConflict,
    ConstructionError,
    ConstructionReviewRequestV1,
    FileConstructionRunStore,
    HttpSemanticaConstructionEngine,
    PostgresConstructionRunStore,
    StudioConstructionService,
)
from .studio.builder import BoundedBuilderOrchestrator, BuilderError, HttpBuilderModel
from .studio.reviewer import (
    BoundedReviewerOrchestrator,
    HttpReviewerModel,
    ReviewerError,
)
from .studio.skill_packages import SkillPackageError, load_skill_package
from .studio.construction_jobs import (
    ConstructionJobConflict,
    ConstructionJobError,
    InMemoryConstructionJobStore,
    PostgresConstructionJobStore,
)
from .studio.task_projection import StudioBuildTaskSummaryV1, project_build_task
from .studio.editor import DraftOperationsV1, EditorDescriptorError
from .studio.intake import IntakeError
from .studio.llm import (
    StudioLLMError,
    StudioObservationConflict,
    StudioObservationDisposition,
    StudioObservationService,
    load_semantic_slot_manifest,
    load_studio_egress_decision,
    load_studio_evaluation_manifest,
    load_studio_rollout_record,
    load_studio_run_profile,
)
from .studio.package_authoring import PackageDraftOperationsV1
from .studio.review_drafts import (
    InMemoryReviewDraftStore,
    PostgresReviewDraftStore,
    ReviewDraftConflict,
    ReviewDraftError,
    ReviewDraftSaveV1,
)
from .studio.solutions import (
    CompositeLocalSolutionCatalog,
    SolutionCatalogError,
    SolutionCatalogService,
    SolutionDisplayName,
    SolutionRegistrationRecordV1,
)
from .studio.solution_management import (
    SolutionDirectoryEntryV1,
    SolutionDirectoryPatchV1,
    SolutionDirectoryService,
    SolutionManagementError,
)
from .studio.workspace import (
    DraftUpdate,
    DraftWorkspaceService,
    WorkspaceConflictError,
    WorkspaceError,
    WorkspaceStateError,
    WorkspaceUnavailableError,
)
from .studio.workspace_store import (
    PostgresS3WorkspaceStateStore,
    WorkspaceIdentity,
    WorkspaceStoreError,
)
from .studio.workbench import build_studio_workbench
from .studio.source_projection import (
    SourceProjectionError,
    build_authoring_projection,
)
from .studio.source_library import (
    MAX_SOURCE_BATCH_BYTES,
    MAX_SOURCE_BATCH_FILES,
    SourceKind,
    SourceIntakeBatchManifestV1,
    SourceLibraryError,
    StudioSourceLibraryService,
)
from .validation import validate_semantic_package


PACKAGE_ID = "ontology.exchange_analytics.adt"
DEMO_PRINCIPAL_ROLE = "MarketAnalyst"
DEMO_VERSION = os.environ.get("ONTOLOGY_DEMO_VERSION", "0.1.0-demo.2")


app = FastAPI(
    title="Ontology-based Analytic Agent ADT Adapter",
    version=DEMO_VERSION,
    description=(
        "Synthetic ADT vertical slice. The fixed demo role is a policy simulation, "
        "not production authentication or authorization."
    ),
)

_console_origins = tuple(
    origin.strip()
    for origin in os.environ.get(
        "ONTOLOGY_CONSOLE_ORIGINS",
        "http://127.0.0.1:8780,http://localhost:8780",
    ).split(",")
    if origin.strip()
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(_console_origins),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

control_app = FastAPI(
    title="Ontology Package Control Plane",
    version=DEMO_VERSION,
    description="Separate build, validation and publication surface; do not expose on the runtime route.",
)
control_app.add_middleware(
    CORSMiddleware,
    allow_origins=list(_console_origins),
    allow_methods=["DELETE", "GET", "PATCH", "POST"],
    allow_headers=["Content-Type"],
)

agent_control_app = FastAPI(
    title="Ontology Analytic Agent Runtime Control",
    version=DEMO_VERSION,
    description="Separate prepare and activation surface; do not expose on ordinary runtime routes.",
)
agent_control_app.add_middleware(
    CORSMiddleware,
    allow_origins=list(_console_origins),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1)


class SolutionAnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_case_id: str | None = Field(default=None, min_length=1, max_length=200)
    question: str = Field(min_length=1, max_length=1000)
    role: str | None = Field(default=None, min_length=1, max_length=100)


class SolutionQuestionCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]+$")
    language: str = Field(pattern=r"^(en|zh)$")
    question: str = Field(min_length=1, max_length=2000)
    expected_intent: str = Field(pattern=r"^[a-z][a-z0-9_]+$")
    required_tools: tuple[str, ...] = Field(min_length=1, max_length=12)


class SolutionQuestionFamily(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    contract: str = Field(pattern=r"^registered-question-family/v1$")
    family_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]+$")
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    classification: str = Field(pattern=r"^constructed_synthetic$")
    cases: tuple[SolutionQuestionCase, ...] = Field(min_length=1, max_length=64)


class CreateStudioSolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract: Literal["studio-solution-create/v1"] = "studio-solution-create/v1"
    creation_mode: Literal["TEMPLATE", "BLANK"]
    template_solution_id: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    )
    display_name: SolutionDisplayName
    description: str = Field(min_length=1, max_length=1000)
    owner: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_creation_source(self) -> CreateStudioSolutionRequest:
        if self.creation_mode == "TEMPLATE" and self.template_solution_id is None:
            raise ValueError("Template creation requires a template solution")
        if self.creation_mode == "BLANK" and self.template_solution_id is not None:
            raise ValueError("Blank creation cannot reference a template solution")
        return self


def _public_solution_question_family(path: Path) -> dict[str, Any]:
    family = SolutionQuestionFamily.model_validate(
        json.loads(path.read_text(encoding="utf-8"))
    )
    if len({case.case_id for case in family.cases}) != len(family.cases):
        raise ValueError("Solution question case IDs must be unique")
    return {
        "family_id": family.family_id,
        "family_checksum": sha256_value(family),
        "classification": family.classification,
        "cases": [
            {
                "case_id": case.case_id,
                "language": case.language,
                "question": case.question,
                "expected_intent": case.expected_intent,
                "required_tools": list(case.required_tools),
            }
            for case in family.cases
        ],
    }


class LlmAnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_case_id: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=1, max_length=500)


class PrepareRuntimeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    release: ReleaseRef
    certify_adt: bool = True
    certify_reference: bool | None = None


class ActivateRuntimeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    snapshot: RuntimeSnapshotRef
    expected_current: RuntimeSnapshotRef | None = None
    require_adt_certification: bool = True


class RollbackRuntimeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_snapshot: RuntimeSnapshotRef
    expected_current: RuntimeSnapshotRef
    require_adt_certification: bool = True


class PatchDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    update: DraftUpdate


class ExpectedRevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)


class ConstructionStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    source_version_ids: tuple[str, ...] = Field(default=(), max_length=100)
    authoring_language: Literal["en", "zh"] | None = None


class StudioObservationReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    dispositions: tuple[StudioObservationDisposition, ...] = Field(
        min_length=5, max_length=5
    )


class VerifyActiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_snapshot: RuntimeSnapshotRef


def _studio_releases() -> StudioReleases:
    return StudioReleases(DEFAULT_PUBLISHED_DIR / "releases")


def _agent_runtime(config: dict[str, Any] | None = None) -> AgentRuntime:
    resource_roots = {
        "adt-scenario": DEFAULT_SCENARIO_DIR,
        "cash-trading-scenario": DEFAULT_CASH_TRADING_SCENARIO_DIR,
    }
    if config is not None:
        resource_roots[str(config["resource_root_id"])] = Path(
            config["scenario_dir"]
        )
    return AgentRuntime(
        release_root=DEFAULT_PUBLISHED_DIR / "releases",
        runtime_root=DEFAULT_PUBLISHED_DIR / "runtime",
        resources=FileResourceResolver(resource_roots),
    )


def _semantic_change_requests() -> FileSemanticChangeRequestStore:
    return FileSemanticChangeRequestStore(
        DEFAULT_STUDIO_DIR / "semantic-change-requests"
    )


def _solution_catalog() -> SolutionCatalogService | CompositeLocalSolutionCatalog:
    try:
        settings = ProductInfrastructureSettings.from_env()
        primary = SolutionCatalogService.from_settings(
            settings,
            manifest_path=DEFAULT_SCENARIO_DIR / "solution-registration.json",
            component_root=DEFAULT_SCENARIO_DIR,
        )
        if settings.mode != "legacy-compatibility":
            return primary
        cash = SolutionCatalogService.from_settings(
            settings,
            manifest_path=(
                DEFAULT_CASH_TRADING_SCENARIO_DIR / "solution-registration.json"
            ),
            component_root=DEFAULT_CASH_TRADING_SCENARIO_DIR,
        )
        return CompositeLocalSolutionCatalog((primary, cash))
    except ProductInfrastructureError as exc:
        raise SolutionCatalogError("Solution catalog settings are unavailable") from exc


def _solution_directory() -> SolutionDirectoryService:
    try:
        settings = ProductInfrastructureSettings.from_env()
        return SolutionDirectoryService.from_settings(
            settings,
            local_path=DEFAULT_STUDIO_DIR / "solution-directory.json",
        )
    except ProductInfrastructureError as exc:
        raise SolutionManagementError(
            "Solution directory settings are unavailable"
        ) from exc


def _directory_entry(
    record: SolutionRegistrationRecordV1,
) -> SolutionDirectoryEntryV1:
    return _solution_directory().resolve(
        solution_id=record.subject.solution_id,
        fallback_name=record.subject.display_name,
        fallback_description=(
            f"{record.subject.display_name.zh}的本体建模、验证与发布工作区。"
        ),
    )


def _latest_solution_registration(solution_id: str) -> SolutionRegistrationRecordV1:
    candidates = tuple(
        record
        for record in _solution_catalog().list()
        if record.subject.solution_id == solution_id
    )
    if not candidates:
        raise SolutionCatalogError("Solution registration is not installed")
    return max(
        candidates,
        key=lambda record: tuple(
            int(part) for part in record.subject.solution_version.split(".")
        ),
    )


def _ensure_solution_active(solution_id: str) -> None:
    record = _latest_solution_registration(solution_id)
    if _directory_entry(record).status != "ACTIVE":
        raise SolutionCatalogError("Solution is not active in the Studio directory")


def _registration_for_workspace(workspace_id: str) -> SolutionRegistrationRecordV1:
    candidates = tuple(
        record
        for record in _solution_catalog().list()
        if record.subject.workspace_id == workspace_id
    )
    if not candidates:
        raise WorkspaceError("Draft workspace is not registered")
    return max(
        candidates,
        key=lambda record: tuple(
            int(part) for part in record.subject.solution_version.split(".")
        ),
    )


def _installed_solution_root(
    registration: SolutionRegistrationRecordV1,
) -> Path:
    return _solution_catalog().materialize(
        registration,
        DEFAULT_STUDIO_DIR / "installed-solutions",
    )


def _draft_workspaces(
    workspace_id: str = "workspace.adt.reference",
) -> Any:
    registration = _registration_for_workspace(workspace_id)
    adapter_id = registration.subject.studio_adapter_id
    if adapter_id not in {
        ADT_STUDIO_ADAPTER_ID,
        CASH_TRADING_STUDIO_ADAPTER_ID,
        GENERIC_STUDIO_ADAPTER_ID,
    }:
        raise WorkspaceError("The registered Studio adapter is not installed")
    try:
        settings = ProductInfrastructureSettings.from_env()
        state_store = (
            PostgresS3WorkspaceStateStore.from_settings(settings)
            if settings.mode == "postgresql-s3"
            else None
        )
    except (ProductInfrastructureError, WorkspaceStoreError) as exc:
        raise WorkspaceUnavailableError(
            "Workspace durable settings are unavailable"
        ) from exc
    solution_root = _installed_solution_root(registration)
    identity = (
        WorkspaceIdentity(
            solution_id=registration.subject.solution_id,
            solution_version=(
                registration.subject.semantic_source_version
                or registration.subject.solution_version
            ),
            workspace_id=registration.subject.workspace_id,
            studio_adapter_id=registration.subject.studio_adapter_id,
        )
        if state_store is not None
        else None
    )
    service_type = {
        ADT_STUDIO_ADAPTER_ID: DraftWorkspaceService,
        CASH_TRADING_STUDIO_ADAPTER_ID: CashTradingDraftWorkspaceService,
        GENERIC_STUDIO_ADAPTER_ID: GenericDraftWorkspaceService,
    }[adapter_id]
    return service_type(
        DEFAULT_STUDIO_DIR / "workspaces",
        solution_root,
        _studio_releases(),
        state_store=state_store,
        identity=identity,
    )


def _studio_adapter(
    workspace_id: str,
) -> ADTStudioAdapter | CashTradingStudioAdapter | GenericStudioAdapter:
    registration = _registration_for_workspace(workspace_id)
    adapter_id = registration.subject.studio_adapter_id
    if adapter_id not in {
        ADT_STUDIO_ADAPTER_ID,
        CASH_TRADING_STUDIO_ADAPTER_ID,
        GENERIC_STUDIO_ADAPTER_ID,
    }:
        raise WorkspaceError("The registered Studio adapter is not installed")
    component = next(
        (
            item
            for item in registration.subject.components
            if item.kind == "authoring_profile"
        ),
        None,
    )
    if component is None:
        raise WorkspaceError("The registered authoring profile is unavailable")
    candidate = PurePosixPath(component.locator)
    root = _installed_solution_root(registration)
    descriptor_path = root.joinpath(*candidate.parts).resolve()
    if not descriptor_path.is_relative_to(root) or not descriptor_path.is_file():
        raise WorkspaceError("The registered authoring profile is unavailable")
    try:
        adapter_type = {
            ADT_STUDIO_ADAPTER_ID: ADTStudioAdapter,
            CASH_TRADING_STUDIO_ADAPTER_ID: CashTradingStudioAdapter,
            GENERIC_STUDIO_ADAPTER_ID: GenericStudioAdapter,
        }[adapter_id]
        return adapter_type(
            workspace=_draft_workspaces(workspace_id),
            descriptor_path=descriptor_path,
            component_root=root,
        )
    except EditorDescriptorError as exc:
        raise WorkspaceStateError("The registered editor descriptor is invalid") from exc


def _runtime_configuration(package_id: str) -> dict[str, Any]:
    try:
        _ensure_solution_active(package_id)
    except (SolutionCatalogError, SolutionManagementError) as exc:
        raise PublicationError("The solution is archived or unavailable") from exc
    if package_id == PACKAGE_ID:
        return {
            "environment_id": "adt-poc",
            "resource_root_id": "adt-scenario",
            "scenario_dir": DEFAULT_SCENARIO_DIR,
            "binding": adt_synthetic_binding(resource_root_id="adt-scenario"),
            "certification": adt_golden_certification(
                resource_root_id="adt-scenario"
            ),
            "certification_profile": ADT_CERTIFICATION_PROFILE,
        }
    if package_id == CASH_PACKAGE_ID:
        return {
            "environment_id": "cash-trading-poc",
            "resource_root_id": "cash-trading-scenario",
            "scenario_dir": DEFAULT_CASH_TRADING_SCENARIO_DIR,
            "binding": cash_trading_synthetic_binding(
                resource_root_id="cash-trading-scenario"
            ),
            "certification": cash_trading_golden_certification(
                resource_root_id="cash-trading-scenario"
            ),
            "certification_profile": CASH_CERTIFICATION_PROFILE,
        }
    try:
        registration = _latest_solution_registration(package_id)
        entry = _directory_entry(registration)
        if entry.status != "ACTIVE":
            raise PublicationError("The solution is archived or deleted")
        scenario_dir = _installed_solution_root(registration)
    except (SolutionCatalogError, SolutionManagementError) as exc:
        raise PublicationError(
            "No installed runtime configuration matches the package"
        ) from exc
    resource_root_id = registration.subject.authoring_root_id
    if registration.subject.studio_adapter_id == ADT_STUDIO_ADAPTER_ID:
        return {
            "environment_id": "adt-poc",
            "resource_root_id": resource_root_id,
            "scenario_dir": scenario_dir,
            "binding": adt_synthetic_binding(resource_root_id=resource_root_id),
            "certification": adt_golden_certification(
                resource_root_id=resource_root_id
            ),
            "certification_profile": ADT_CERTIFICATION_PROFILE,
        }
    if registration.subject.studio_adapter_id == CASH_TRADING_STUDIO_ADAPTER_ID:
        return {
            "environment_id": "cash-trading-poc",
            "resource_root_id": resource_root_id,
            "scenario_dir": scenario_dir,
            "binding": cash_trading_synthetic_binding(
                resource_root_id=resource_root_id
            ),
            "certification": cash_trading_golden_certification(
                resource_root_id=resource_root_id
            ),
            "certification_profile": CASH_CERTIFICATION_PROFILE,
        }
    if registration.subject.studio_adapter_id == GENERIC_STUDIO_ADAPTER_ID:
        environment_id = "solution-" + sha256_value(package_id)[:16]
        return {
            "generic": True,
            "environment_id": environment_id,
            "resource_root_id": resource_root_id,
            "scenario_dir": scenario_dir,
            "binding": generic_semantic_binding(
                environment_id=environment_id,
                resource_root_id=resource_root_id,
            ),
            "certification": None,
            "certification_profile": None,
        }
    raise PublicationError("No installed runtime adapter matches the package")


def _runtime_role_catalog(package: Any) -> list[dict[str, Any]]:
    allowed = {
        role
        for policy in package.policies
        for role in policy.allowed_roles
    }
    denied = {
        role
        for policy in package.policies
        for role in policy.denied_roles
    }
    relevant = allowed | denied
    catalog: list[dict[str, Any]] = []
    seen: set[str] = set()
    for actor in package.actors:
        for role in actor.roles:
            if role not in relevant or role in seen:
                continue
            catalog.append(
                {
                    "role_id": role,
                    "name": actor.name.model_dump(mode="json"),
                    "access": "ALLOWED" if role in allowed else "DENIED",
                }
            )
            seen.add(role)
    return catalog


def _default_runtime_role(package: Any) -> str | None:
    if package.scenario.default_role:
        return package.scenario.default_role
    return next(
        (
            role
            for policy in package.policies
            for role in policy.allowed_roles
            if role not in policy.denied_roles
        ),
        None,
    )


def _studio_observations() -> StudioObservationService:
    registration = _registration_for_workspace("workspace.adt.reference")
    solution_root = _installed_solution_root(registration)
    profile_path = Path(
        os.environ.get(
            "ONTOLOGY_STUDIO_LLM_PROFILE_PATH",
            str(
                solution_root
                / "llm"
                / "studio"
                / "engineering-profile.json"
            ),
        )
    )
    manifest_path = Path(
        os.environ.get(
            "ONTOLOGY_STUDIO_LLM_SLOT_MANIFEST_PATH",
            str(
                solution_root
                / "llm"
                / "studio"
                / "semantic-slot-manifest.json"
            ),
        )
    )
    egress_path = os.environ.get("ONTOLOGY_STUDIO_LLM_EGRESS_DECISION_PATH")
    rollout_path = os.environ.get("ONTOLOGY_STUDIO_LLM_ROLLOUT_PATH")
    evaluation_path = os.environ.get(
        "ONTOLOGY_STUDIO_LLM_EVALUATION_MANIFEST_PATH"
    )
    gateway_url = os.environ.get("ONTOLOGY_MODEL_GATEWAY_URL")
    if not egress_path or not rollout_path or not evaluation_path or not gateway_url:
        raise StudioLLMError("Studio LLM authority or gateway is unavailable")

    profile = load_studio_run_profile(profile_path)
    slot_manifest = load_semantic_slot_manifest(manifest_path)
    egress = load_studio_egress_decision(Path(egress_path))
    rollout = load_studio_rollout_record(Path(rollout_path))
    evaluation = load_studio_evaluation_manifest(Path(evaluation_path))
    def boundary(body: dict[str, object], timeout: float) -> dict[str, object]:
        return _gateway_transport(
            gateway_url.rstrip("/") + "/model/v1/studio-observe",
            body,
            timeout,
        )

    return StudioObservationService(
        root=DEFAULT_STUDIO_DIR / "llm",
        workspace=_draft_workspaces(),
        profile=profile,
        slot_manifest=slot_manifest,
        egress=egress,
        rollout=rollout,
        evaluation=evaluation,
        model_boundary=boundary,
    )


def _studio_intake_payload(
    workspace_id: str,
    workspace: Any,
    *,
    include_parsed_attachments: bool = False,
) -> dict[str, Any]:
    base_intake = workspace.get_intake(workspace_id)
    intake_payload = (
        base_intake.model_dump(mode="json")
        if hasattr(base_intake, "model_dump")
        else dict(base_intake)
    )
    uploaded_assets = _studio_source_library().current_intake_assets(
        workspace_id,
        include_parsed_attachments=include_parsed_attachments,
    )
    if uploaded_assets:
        base_assets = tuple(
            dict(item)
            for item in intake_payload.get("assets", ())
            if isinstance(item, dict)
        )
        uploaded_ids = {str(item["asset_id"]) for item in uploaded_assets}
        singleton_overrides = {
            str(item["kind"])
            for item in uploaded_assets
            if item["kind"] in {
                "requirement_transcription",
                "metric_transcription",
            }
        }
        retained = tuple(
            item
            for item in base_assets
            if str(item.get("asset_id") or item.get("file_id")) not in uploaded_ids
            and str(item.get("kind")) not in singleton_overrides
        )
        intake_payload["assets"] = tuple(
            sorted(
                (*retained, *uploaded_assets),
                key=lambda item: (
                    str(item.get("kind")),
                    str(item.get("asset_id") or item.get("file_id")),
                ),
            )
        )
    return intake_payload


def _studio_construction(
    workspace_id: str,
    selected_source_version_ids: tuple[str, ...] = (),
) -> StudioConstructionService:
    adapter = _studio_adapter(workspace_id)
    workspace = adapter.workspace
    package = workspace.candidate_package(workspace_id)
    intake = _studio_intake_payload(
        workspace_id,
        workspace,
        include_parsed_attachments=True,
    )
    selection = tuple(sorted(selected_source_version_ids))
    if len(selection) != len(set(selection)):
        raise ConstructionError("Selected source versions must be unique")
    if selection:
        assets = tuple(
            item
            for item in intake.get("assets", ())
            if isinstance(item, dict)
            and str(item.get("source_version_id")) in set(selection)
        )
        found = {
            str(item.get("source_version_id"))
            for item in assets
            if item.get("source_version_id")
        }
        missing = sorted(set(selection) - found)
        if missing:
            raise ConstructionError(
                "Selected source version is not a current exact workspace source: "
                + ", ".join(missing)
            )
        intake["assets"] = assets
    worker_url = os.environ.get("ONTOLOGY_SEMANTICA_WORKER_URL", "").strip()
    engine = (
        HttpSemanticaConstructionEngine(
            worker_url,
            timeout_seconds=float(
                os.environ.get("ONTOLOGY_SEMANTICA_TIMEOUT_SECONDS", "20")
            ),
        )
        if worker_url
        else None
    )
    model_gateway_url = os.environ.get("ONTOLOGY_MODEL_GATEWAY_URL", "").strip()
    builder_enabled = os.environ.get("ONTOLOGY_BUILDER_ENABLED", "true").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    try:
        builder = (
            BoundedBuilderOrchestrator(
                model=HttpBuilderModel(
                    model_gateway_url,
                    timeout_seconds=float(
                        os.environ.get("ONTOLOGY_BUILDER_TIMEOUT_SECONDS", "75")
                    ),
                ),
                skill=load_skill_package(
                    "ontology-build",
                    os.environ.get("ONTOLOGY_BUILD_SKILL_VERSION", "1.2.0"),
                    root=(
                        Path(os.environ["ONTOLOGY_SKILL_ROOT"])
                        if os.environ.get("ONTOLOGY_SKILL_ROOT")
                        else None
                    ),
                ),
            )
            if builder_enabled and model_gateway_url
            else None
        )
    except (BuilderError, SkillPackageError, ValueError) as exc:
        raise ConstructionError("Ontology Build Skill is unavailable") from exc
    reviewer_enabled = os.environ.get(
        "ONTOLOGY_REVIEWER_ENABLED", "true"
    ).strip().lower() in {"1", "true", "yes"}
    try:
        reviewer = (
            BoundedReviewerOrchestrator(
                model=HttpReviewerModel(
                    model_gateway_url,
                    timeout_seconds=float(
                        os.environ.get("ONTOLOGY_REVIEWER_TIMEOUT_SECONDS", "75")
                    ),
                ),
                skill=load_skill_package(
                    "ontology-review",
                    os.environ.get("ONTOLOGY_REVIEW_SKILL_VERSION", "1.0.0"),
                    root=(
                        Path(os.environ["ONTOLOGY_SKILL_ROOT"])
                        if os.environ.get("ONTOLOGY_SKILL_ROOT")
                        else None
                    ),
                ),
            )
            if reviewer_enabled and model_gateway_url
            else None
        )
    except (ReviewerError, SkillPackageError, ValueError) as exc:
        raise ConstructionError("Ontology Review Skill is unavailable") from exc
    try:
        settings = ProductInfrastructureSettings.from_env()
        run_store = _construction_run_store(settings)
    except (ProductInfrastructureError, ConstructionError) as exc:
        raise ConstructionError(
            "Construction durable settings are unavailable"
        ) from exc
    return StudioConstructionService(
        store=run_store,
        workspace=workspace,
        package=package,
        intake=intake,
        authoring=build_authoring_projection(
            package=package,
            intake=intake,
            scenario_dir=workspace.scenario_dir,
        ),
        builder=builder,
        reviewer=reviewer,
        engine=engine,
        review_drafts=(
            _review_draft_store() if settings.mode == "postgresql-s3" else None
        ),
        selected_source_version_ids=selection,
        workspace_id=workspace_id,
    )


def _studio_source_library() -> StudioSourceLibraryService:
    try:
        settings = ProductInfrastructureSettings.from_env()
        return StudioSourceLibraryService.from_settings(
            settings,
            local_root=DEFAULT_STUDIO_DIR / "sources",
        )
    except (ProductInfrastructureError, SourceLibraryError) as exc:
        raise SourceLibraryError("Source library settings are unavailable") from exc


_LOCAL_CONSTRUCTION_JOBS = InMemoryConstructionJobStore()
_LOCAL_REVIEW_DRAFTS = InMemoryReviewDraftStore()


def _construction_run_store(
    settings: ProductInfrastructureSettings | None = None,
) -> Any:
    """Return the durable Run/Decision authority without building a workspace.

    Task projections are read models. They must not initialize the authoring,
    source-intake, Builder, or Reviewer graph merely to display durable state.
    """

    try:
        resolved = settings or ProductInfrastructureSettings.from_env()
        if resolved.mode == "postgresql-s3":
            return PostgresConstructionRunStore.from_settings(resolved)
        return FileConstructionRunStore(DEFAULT_STUDIO_DIR / "construction")
    except (ProductInfrastructureError, ConstructionError) as exc:
        raise ConstructionError(
            "Construction durable settings are unavailable"
        ) from exc


def _construction_job_store() -> Any:
    try:
        settings = ProductInfrastructureSettings.from_env()
        if settings.mode == "postgresql-s3":
            return PostgresConstructionJobStore.from_settings(settings)
        return _LOCAL_CONSTRUCTION_JOBS
    except (ProductInfrastructureError, ConstructionJobError) as exc:
        raise ConstructionJobError(
            "Construction job authority is unavailable"
        ) from exc


def _construction_revision_with_language(
    workspace_id: str,
    request: ConstructionStartRequest,
) -> int:
    """Freeze a blank Solution's authoring language before the first Build."""

    adapter = _studio_adapter(workspace_id)
    workspace_service = adapter.workspace
    current = workspace_service.get(workspace_id)
    existing = getattr(current, "authoring_language", None)
    requested = request.authoring_language
    if existing is not None:
        if requested is not None and requested != existing:
            raise WorkspaceConflictError(
                "Ontology authoring language is locked for this Solution"
            )
        return current.revision
    configure = getattr(workspace_service, "configure_authoring_language", None)
    if configure is None:
        return current.revision
    language = requested or "en"
    configured = configure(
        language,
        expected_revision=request.expected_revision,
        workspace_id=workspace_id,
    )
    return configured.revision


def _review_draft_store() -> Any:
    try:
        settings = ProductInfrastructureSettings.from_env()
        if settings.mode == "postgresql-s3":
            return PostgresReviewDraftStore.from_settings(settings)
        return _LOCAL_REVIEW_DRAFTS
    except (ProductInfrastructureError, ReviewDraftError) as exc:
        raise ReviewDraftError("Review draft authority is unavailable") from exc


def _workspace_error(exc: Exception) -> HTTPException:
    if isinstance(exc, SolutionCatalogError):
        return HTTPException(status_code=503, detail="Solution catalog is unavailable")
    if isinstance(exc, WorkspaceUnavailableError):
        return HTTPException(status_code=503, detail="Studio workspace is unavailable")
    if isinstance(exc, WorkspaceConflictError):
        return HTTPException(status_code=409, detail="Draft revision conflict")
    if isinstance(
        exc,
        (
            WorkspaceStateError,
            PublicationError,
            IntakeError,
            ConstructionError,
            ConstructionJobError,
            ReviewDraftError,
            SourceLibraryError,
            SourceProjectionError,
        ),
    ):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail="Draft update is invalid")
    return HTTPException(status_code=404, detail="Draft workspace not found")


def _solution_payload(
    record: SolutionRegistrationRecordV1,
    directory: SolutionDirectoryEntryV1 | None = None,
) -> dict[str, Any]:
    subject = record.subject
    entry = directory or _directory_entry(record)
    return {
        "solution_id": subject.solution_id,
        "solution_version": subject.solution_version,
        "semantic_source_version": (
            subject.semantic_source_version or subject.solution_version
        ),
        "scenario_id": subject.scenario_id,
        "workspace_id": subject.workspace_id,
        "studio_adapter_id": subject.studio_adapter_id,
        "classification": subject.classification,
        "display_name": entry.display_name.model_dump(mode="json"),
        "directory": entry.model_dump(mode="json"),
        "components": [
            {
                "component_id": component.component_id,
                "kind": component.kind,
                "sha256": component.sha256,
                "media_type": component.media_type,
            }
            for component in subject.components
        ],
        "limitations": list(subject.limitations),
        "persistence": record.persistence,
        "subject_checksum": record.subject_checksum,
        "artifact": (
            record.artifact.model_dump(mode="json")
            if record.artifact is not None
            else None
        ),
        "installable": record.bundle is not None,
        "resource_count": len(subject.resources),
        "bundle_checksum": (
            record.bundle.subject_checksum if record.bundle is not None else None
        ),
    }


def _runtime_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove SQL, parameters, rows, errors and filesystem details from ordinary API responses."""
    sanitized = dict(payload)
    sanitized["steps"] = [
        {
            "step_id": step.get("step_id"),
            "status": step.get("status"),
            "sql_hash": step.get("sql_hash"),
        }
        for step in payload.get("steps", [])
    ]
    return sanitized


@app.get("/api/healthz")
@app.get("/api/health", include_in_schema=False)
def health() -> dict[str, str]:
    return {"status": "alive", "version": DEMO_VERSION}


@app.get("/api/readyz")
def readiness() -> dict[str, str]:
    try:
        snapshot = load_verified_snapshot(
            PACKAGE_ID,
            scenario_dir=DEFAULT_SCENARIO_DIR,
            published_root=DEFAULT_PUBLISHED_DIR,
        )
        output_parent = DEFAULT_EXECUTION_DIR.parent
        if not output_parent.exists() or not os.access(output_parent, os.W_OK):
            raise PublicationError("Execution output is not writable")
        settings = ProductInfrastructureSettings.from_env()
        if settings.mode == "postgresql-s3":
            ProductContextService.from_settings(settings).get_active(
                snapshot.manifest["environment_id"]
            )
    except (PublicationError, ProductInfrastructureError) as exc:
        raise HTTPException(
            status_code=503,
            detail="No compatible active runtime and verified product context are ready",
        ) from exc
    return {
        "status": "ready",
        "version": DEMO_VERSION,
        "release_checksum": snapshot.release_checksum,
        "snapshot_checksum": snapshot.snapshot_checksum,
    }


@app.get("/api/llm/status")
def llm_status() -> dict[str, Any]:
    return engineering_demo_status().model_dump(mode="json")


@app.get("/api/llm/questions")
def llm_questions() -> dict[str, Any]:
    return public_question_family(
        DEFAULT_SCENARIO_DIR / "llm" / "question-family.json"
    ).model_dump(mode="json")


@app.get("/api/solutions")
def list_agent_solutions() -> dict[str, Any]:
    try:
        records = _solution_catalog().list()
        visible: list[tuple[SolutionRegistrationRecordV1, SolutionDirectoryEntryV1]] = []
        for record in records:
            directory = _directory_entry(record)
            if directory.status == "ACTIVE":
                visible.append((record, directory))
    except (SolutionCatalogError, SolutionManagementError) as exc:
        raise HTTPException(status_code=503, detail="Solution catalog is unavailable") from exc
    solutions: list[dict[str, Any]] = []
    for record, directory in visible:
        subject = record.subject
        try:
            config = _runtime_configuration(subject.solution_id)
            active = _agent_runtime(config).active_ref(
                config["environment_id"], subject.solution_id
            )
        except PublicationError:
            active = None
        solutions.append(
            {
                **_solution_payload(record, directory),
                "runtime": {
                    "state": "ACTIVE" if active is not None else "NOT_ACTIVE",
                    "environment_id": (
                        config["environment_id"] if active is not None else None
                    ),
                    "snapshot_checksum": active.checksum if active is not None else None,
                },
            }
        )
    return {"contract": "agent-solution-catalog/v1", "solutions": solutions}


@app.get("/api/solutions/{solution_id}/questions")
def solution_questions(solution_id: str) -> dict[str, Any]:
    try:
        config = _runtime_configuration(solution_id)
        if config.get("generic") is True:
            snapshot = _agent_runtime(config).open_active(
                config["environment_id"], solution_id
            ).snapshot
            return generic_question_family(snapshot.package)
        return _public_solution_question_family(
            config["scenario_dir"] / "llm" / "question-family.json"
        )
    except (PublicationError, OSError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Solution question family not found") from exc


@app.post("/api/solutions/{solution_id}/analyze")
def analyze_solution(
    solution_id: str, request: SolutionAnalyzeRequest
) -> dict[str, Any]:
    try:
        config = _runtime_configuration(solution_id)
        snapshot = _agent_runtime(config).open_active(
            config["environment_id"], solution_id
        ).snapshot
    except PublicationError as exc:
        raise HTTPException(
            status_code=503, detail="No compatible active solution runtime is ready"
        ) from exc
    role = request.role or _default_runtime_role(snapshot.package)
    if role is None:
        raise HTTPException(
            status_code=409,
            detail="The active solution has no allowed runtime role",
        )
    role_allowed = any(
        role in policy.allowed_roles and role not in policy.denied_roles
        for policy in snapshot.package.policies
    )
    if config.get("generic") is True:
        bound_goal = generic_bound_goal(
            snapshot.package,
            case_id=request.question_case_id,
            question=request.question,
        )
        grounding_execution = deterministic_only(
            "GENERIC_ACTIVE_ONTOLOGY_BOUNDARY"
            if role_allowed
            else "ROLE_NOT_ELIGIBLE_FOR_MODEL"
        )
    else:
        grounding = attempt_solution_grounding(
            solution_id=solution_id,
            scenario_dir=config["scenario_dir"],
            snapshot_checksum=snapshot.snapshot_checksum,
            question_case_id=request.question_case_id,
            question=request.question,
            role_allowed=role_allowed,
        )
        bound_goal = grounding.bound_goal
        grounding_execution = grounding.execution
    response = analyze_snapshot(
        snapshot,
        question=request.question,
        role=role,
        execution_dir=DEFAULT_EXECUTION_DIR,
        bound_goal=bound_goal,
    )
    payload = _runtime_payload(response.model_dump(mode="json"))
    payload["llm"] = grounding_execution.model_dump(mode="json")
    return payload


@app.post("/api/solutions/{solution_id}/semantic-change-requests")
def create_solution_semantic_change_request(
    solution_id: str,
    request: CreateSemanticChangeRequestV1,
) -> dict[str, Any]:
    try:
        config = _runtime_configuration(solution_id)
        snapshot = _agent_runtime(config).open_active(
            config["environment_id"], solution_id
        ).snapshot
        execution = load_execution(request.execution_id, DEFAULT_EXECUTION_DIR)
        semantic_request = build_semantic_change_request(
            solution_id=solution_id,
            environment_id=config["environment_id"],
            active_snapshot_checksum=snapshot.snapshot_checksum,
            request=request,
            execution=execution,
        )
        stored = _semantic_change_requests().append(semantic_request)
    except PublicationError as exc:
        raise HTTPException(
            status_code=503,
            detail="No compatible active solution runtime is ready",
        ) from exc
    except (SemanticChangeError, FileNotFoundError, ValueError) as exc:
        raise HTTPException(
            status_code=409,
            detail="Semantic change request was not accepted",
        ) from exc
    return stored.model_dump(mode="json")


@app.get("/api/solutions/{solution_id}/ontology")
def solution_ontology(solution_id: str) -> dict[str, Any]:
    try:
        config = _runtime_configuration(solution_id)
        snapshot = _agent_runtime(config).open_active(
            config["environment_id"], solution_id
        ).snapshot
    except PublicationError as exc:
        raise HTTPException(status_code=404, detail="No active solution ontology") from exc
    package = snapshot.package
    return {
        "package_id": package.package_id,
        "version": package.version,
        "snapshot_checksum": snapshot.snapshot_checksum,
        "scenario": package.scenario.model_dump(mode="json"),
        "metrics": [
            {
                "id": metric.id,
                "version": metric.version,
                "name": metric.name.model_dump(mode="json"),
                "definition": metric.definition,
                "unit": metric.unit,
                "formula": metric.formula.model_dump(mode="json"),
            }
            for metric in package.metrics
        ],
        "analysis_patterns": [
            {
                "id": pattern.id,
                "intent": pattern.intent,
                "operation": pattern.operation,
                "output_fields": pattern.output_fields,
            }
            for pattern in package.analysis_patterns
        ],
    }


@app.get("/api/solutions/{solution_id}/runtime/active")
def solution_active_runtime(solution_id: str) -> dict[str, Any]:
    try:
        config = _runtime_configuration(solution_id)
        snapshot = _agent_runtime(config).open_active(
            config["environment_id"], solution_id
        ).snapshot
    except PublicationError as exc:
        raise HTTPException(status_code=404, detail="No active solution runtime") from exc
    return {
        "package_id": snapshot.package.package_id,
        "version": snapshot.package.version,
        "release_checksum": snapshot.release_checksum,
        "snapshot_checksum": snapshot.snapshot_checksum,
        "environment_id": snapshot.manifest["environment_id"],
        "certification_profile": (
            snapshot.manifest.get("certification") or {}
        ).get("profile_id"),
        "default_role": _default_runtime_role(snapshot.package),
        "roles": _runtime_role_catalog(snapshot.package),
    }


@app.post("/api/llm/analyze")
def llm_analyze(request: LlmAnalyzeRequest) -> dict[str, Any]:
    status = engineering_demo_status()
    if status.mode == "off":
        return EngineeringDemoResponse(
            outcome="FAILED_PRECONDITION",
            answer="",
            model_called=False,
            provider_call_count=0,
            tool_call_count=0,
            fallback_used=False,
            committed=False,
            reason_code="LLM_MODE_OFF",
        ).model_dump(mode="json")
    family = load_question_family(
        DEFAULT_SCENARIO_DIR / "llm" / "question-family.json"
    )
    if family.resolve(request.question_case_id, request.question) is None:
        return EngineeringDemoResponse(
            outcome="REFUSED",
            answer="",
            model_called=False,
            provider_call_count=0,
            tool_call_count=0,
            fallback_used=False,
            committed=False,
            reason_code="QUESTION_NOT_REGISTERED",
        ).model_dump(mode="json")
    decision_path = os.environ.get("ONTOLOGY_LLM_EGRESS_DECISION_PATH")
    if not decision_path:
        return EngineeringDemoResponse(
            outcome="FAILED_PRECONDITION",
            answer="",
            model_called=False,
            provider_call_count=0,
            tool_call_count=0,
            fallback_used=False,
            committed=False,
            reason_code="EGRESS_DECISION_NOT_AVAILABLE",
        ).model_dump(mode="json")
    try:
        egress = load_egress_decision(Path(decision_path))
    except (OSError, ValueError):
        return EngineeringDemoResponse(
            outcome="FAILED_PRECONDITION",
            answer="",
            model_called=False,
            provider_call_count=0,
            tool_call_count=0,
            fallback_used=False,
            committed=False,
            reason_code="EGRESS_DECISION_INVALID",
        ).model_dump(mode="json")
    if egress.decision == "DENY":
        return EngineeringDemoResponse(
            outcome="REFUSED",
            answer="",
            model_called=False,
            provider_call_count=0,
            tool_call_count=0,
            fallback_used=False,
            committed=False,
            reason_code="EGRESS_DECISION_DENIED",
        ).model_dump(mode="json")
    if not egress.permits(family):
        return EngineeringDemoResponse(
            outcome="FAILED_PRECONDITION",
            answer="",
            model_called=False,
            provider_call_count=0,
            tool_call_count=0,
            fallback_used=False,
            committed=False,
            reason_code="EGRESS_DECISION_INVALID",
        ).model_dump(mode="json")
    profile_path = os.environ.get("ONTOLOGY_LLM_PROFILE_PATH")
    if not profile_path:
        return EngineeringDemoResponse(
            outcome="FAILED_PRECONDITION",
            answer="",
            model_called=False,
            provider_call_count=0,
            tool_call_count=0,
            fallback_used=False,
            committed=False,
            reason_code="RUN_PROFILE_NOT_AVAILABLE",
        ).model_dump(mode="json")
    try:
        profile = load_run_profile(Path(profile_path))
    except (OSError, ValueError):
        return EngineeringDemoResponse(
            outcome="FAILED_PRECONDITION",
            answer="",
            model_called=False,
            provider_call_count=0,
            tool_call_count=0,
            fallback_used=False,
            committed=False,
            reason_code="RUN_PROFILE_INVALID",
        ).model_dump(mode="json")
    profile_digest = sha256_value(profile)
    if not profile.matches(egress):
        return EngineeringDemoResponse(
            outcome="FAILED_PRECONDITION",
            answer="",
            model_called=False,
            provider_call_count=0,
            tool_call_count=0,
            fallback_used=False,
            committed=False,
            reason_code="RUN_PROFILE_INVALID",
            profile_digest=profile_digest,
        ).model_dump(mode="json")
    rollout_path = os.environ.get("ONTOLOGY_LLM_ROLLOUT_PATH")
    if not rollout_path:
        return EngineeringDemoResponse(
            outcome="FAILED_PRECONDITION",
            answer="",
            model_called=False,
            provider_call_count=0,
            tool_call_count=0,
            fallback_used=False,
            committed=False,
            reason_code="ROLLOUT_NOT_AVAILABLE",
            profile_digest=profile_digest,
        ).model_dump(mode="json")
    try:
        rollout = load_rollout_record(Path(rollout_path))
    except (OSError, ValueError):
        return EngineeringDemoResponse(
            outcome="FAILED_PRECONDITION",
            answer="",
            model_called=False,
            provider_call_count=0,
            tool_call_count=0,
            fallback_used=False,
            committed=False,
            reason_code="ROLLOUT_INVALID",
            profile_digest=profile_digest,
        ).model_dump(mode="json")
    if not rollout.permits(
        mode=status.mode,
        profile=profile,
        family=family,
        egress=egress,
    ):
        return EngineeringDemoResponse(
            outcome="FAILED_PRECONDITION",
            answer="",
            model_called=False,
            provider_call_count=0,
            tool_call_count=0,
            fallback_used=False,
            committed=False,
            reason_code="ROLLOUT_INVALID",
            profile_digest=profile_digest,
        ).model_dump(mode="json")
    if status.mode == "active-question-family-canary":
        evaluation_path = os.environ.get("ONTOLOGY_LLM_EVALUATION_MANIFEST_PATH")
        if not evaluation_path:
            return EngineeringDemoResponse(
                outcome="FAILED_PRECONDITION",
                answer="",
                model_called=False,
                provider_call_count=0,
                tool_call_count=0,
                fallback_used=False,
                committed=False,
                reason_code="EVALUATION_MANIFEST_NOT_AVAILABLE",
                profile_digest=profile_digest,
            ).model_dump(mode="json")
        try:
            evaluation = load_evaluation_manifest(Path(evaluation_path))
            evaluation_checksum = file_checksum(Path(evaluation_path))
        except (OSError, ValueError):
            evaluation = None
            evaluation_checksum = None
        if (
            evaluation is None
            or evaluation.manifest_id != rollout.evaluation_manifest_ref
            or evaluation_checksum != rollout.evaluation_manifest_checksum
            or not evaluation.permits(
                family=family,
                profile=profile,
                egress=egress,
                rollout_approved_by=rollout.approved_by,
                rollout_issued_at=rollout.issued_at,
            )
        ):
            return EngineeringDemoResponse(
                outcome="FAILED_PRECONDITION",
                answer="",
                model_called=False,
                provider_call_count=0,
                tool_call_count=0,
                fallback_used=False,
                committed=False,
                reason_code="EVALUATION_MANIFEST_INVALID",
                profile_digest=profile_digest,
            ).model_dump(mode="json")
    gateway_url = os.environ.get("ONTOLOGY_MODEL_GATEWAY_URL")
    if not gateway_url:
        return EngineeringDemoResponse(
            outcome="FAILED_PRECONDITION",
            answer="",
            model_called=False,
            provider_call_count=0,
            tool_call_count=0,
            fallback_used=False,
            committed=False,
            reason_code="MODEL_GATEWAY_NOT_AVAILABLE",
            profile_digest=profile_digest,
        ).model_dump(mode="json")
    try:
        snapshot = _agent_runtime().open_active("adt-poc", PACKAGE_ID).snapshot
    except PublicationError:
        return EngineeringDemoResponse(
            outcome="FAILED_PRECONDITION",
            answer="",
            model_called=False,
            provider_call_count=0,
            tool_call_count=0,
            fallback_used=False,
            committed=False,
            reason_code="NO_ACTIVE_SNAPSHOT",
            profile_digest=profile_digest,
        ).model_dump(mode="json")
    case = family.resolve(request.question_case_id, request.question)
    assert case is not None
    response = run_engineering_demo_grounding(
        status=status,
        family=family,
        case=case,
        egress=egress,
        profile=profile,
        rollout=rollout,
        snapshot=snapshot,
        state_path=Path(
            os.environ.get(
                "ONTOLOGY_LLM_STATE_PATH",
                str(DEFAULT_EXECUTION_DIR.parent / "llm-engineering.sqlite3"),
            )
        ),
        gateway_url=gateway_url,
    )
    return response.model_dump(mode="json")


@app.post("/api/analyze")
def analyze(request: AnalyzeRequest) -> dict[str, Any]:
    response = analyze_latest(
        question=request.question,
        role=DEMO_PRINCIPAL_ROLE,
        package_id=PACKAGE_ID,
        scenario_dir=DEFAULT_SCENARIO_DIR,
        published_root=DEFAULT_PUBLISHED_DIR,
        execution_dir=DEFAULT_EXECUTION_DIR,
    )
    return _runtime_payload(response.model_dump(mode="json"))


@app.get("/api/executions/{execution_id}")
def execution(execution_id: str) -> dict[str, Any]:
    try:
        return _runtime_payload(load_execution(execution_id))
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Execution record not found") from exc


@app.get("/api/ontology")
def ontology() -> dict[str, Any]:
    try:
        snapshot = load_verified_snapshot(
            PACKAGE_ID,
            scenario_dir=DEFAULT_SCENARIO_DIR,
            published_root=DEFAULT_PUBLISHED_DIR,
        )
    except PublicationError as exc:
        raise HTTPException(status_code=404, detail="No compatible ontology snapshot") from exc
    package = snapshot.package
    return {
        "package_id": package.package_id,
        "version": package.version,
        "snapshot_checksum": snapshot.snapshot_checksum,
        "scenario": {
            "id": package.scenario.id,
            "market_id": package.scenario.market_id,
            "periods": [period.model_dump(mode="json") for period in package.scenario.periods],
        },
        "metrics": [
            {
                "id": metric.id,
                "version": metric.version,
                "name": metric.name.model_dump(mode="json"),
                "definition": metric.definition,
                "unit": metric.unit,
                "formula": metric.formula.model_dump(mode="json"),
            }
            for metric in package.metrics
        ],
        "analysis_patterns": [
            {
                "id": pattern.id,
                "intent": pattern.intent,
                "operation": pattern.operation,
                "output_fields": pattern.output_fields,
            }
            for pattern in package.analysis_patterns
        ],
    }


@app.get("/api/snapshots")
def snapshots() -> dict[str, Any]:
    return {
        "package_id": PACKAGE_ID,
        "releases": list_published_snapshots(PACKAGE_ID, published_root=DEFAULT_PUBLISHED_DIR),
    }


@app.get("/api/runtime/active")
def active_runtime() -> dict[str, Any]:
    try:
        snapshot = _agent_runtime().open_active("adt-poc", PACKAGE_ID).snapshot
    except PublicationError as exc:
        raise HTTPException(status_code=404, detail="No active runtime snapshot") from exc
    return {
        "package_id": snapshot.package.package_id,
        "version": snapshot.package.version,
        "release_checksum": snapshot.release_checksum,
        "snapshot_checksum": snapshot.snapshot_checksum,
        "environment_id": snapshot.manifest["environment_id"],
        "certification_profile": (
            snapshot.manifest.get("certification") or {}
        ).get("profile_id"),
    }


@app.get("/api/product/context", response_model=ProductContextV1)
def product_context() -> ProductContextV1:
    try:
        snapshot = _agent_runtime().open_active("adt-poc", PACKAGE_ID).snapshot
        settings = ProductInfrastructureSettings.from_env()
        if settings.mode == "legacy-compatibility":
            return legacy_product_context(snapshot)
        return ProductContextService.from_settings(settings).get_active(
            snapshot.manifest["environment_id"]
        )
    except (PublicationError, ProductInfrastructureError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Product context is unavailable or failed identity verification",
        ) from exc


@control_app.post("/control/validate")
def validate_control() -> dict[str, Any]:
    package = load_package(DEFAULT_PACKAGE_PATH)
    report = validate_semantic_package(package)
    return report.model_dump(mode="json")


@control_app.get("/control/healthz")
def control_health() -> dict[str, str]:
    return {"status": "alive", "version": DEMO_VERSION}


@control_app.get("/control/readyz")
def control_readiness() -> dict[str, str]:
    try:
        registration = _registration_for_workspace("workspace.adt.reference")
        workspace = _draft_workspaces(registration.subject.workspace_id).get(
            registration.subject.workspace_id
        )
    except (WorkspaceError, IntakeError, SolutionCatalogError) as exc:
        raise HTTPException(status_code=503, detail="Studio workspace is not ready") from exc
    return {
        "status": "ready",
        "version": DEMO_VERSION,
        "solution_id": registration.subject.solution_id,
        "solution_registration_checksum": registration.subject_checksum,
        "workspace_id": workspace.workspace_id,
        "draft_checksum": workspace.draft_checksum,
    }


@control_app.get("/control/solutions")
def list_control_solutions() -> dict[str, Any]:
    try:
        records = _solution_catalog().list()
        visible: list[dict[str, Any]] = []
        for record in records:
            directory = _directory_entry(record)
            if directory.status != "DELETED":
                visible.append(_solution_payload(record, directory))
    except (SolutionCatalogError, SolutionManagementError) as exc:
        raise HTTPException(status_code=503, detail="Solution catalog is unavailable") from exc
    return {
        "contract": "studio-solution-catalog/v1",
        "solutions": visible,
    }


@control_app.post("/control/solutions", status_code=201)
def create_control_solution(request: CreateStudioSolutionRequest) -> dict[str, Any]:
    catalog = _solution_catalog()
    if not isinstance(catalog, SolutionCatalogService) or catalog.artifacts is None:
        raise HTTPException(
            status_code=409,
            detail="Creating solutions requires the durable PostgreSQL/S3 catalog",
        )
    suffix = uuid.uuid4().hex[:12]
    solution_id = f"ontology.custom.{suffix}"
    scenario_id = f"scenario.custom.{suffix}"
    workspace_id = f"workspace.custom.{suffix}"
    try:
        if request.creation_mode == "TEMPLATE":
            assert request.template_solution_id is not None
            template = _latest_solution_registration(request.template_solution_id)
            if _directory_entry(template).status != "ACTIVE":
                raise SolutionManagementError("Archived solutions cannot be templates")
            record = catalog.clone_template(
                template,
                solution_id=solution_id,
                scenario_id=scenario_id,
                workspace_id=workspace_id,
                display_name=request.display_name,
                description=request.description,
            )
        else:
            record = catalog.create_blank(
                solution_id=solution_id,
                scenario_id=scenario_id,
                workspace_id=workspace_id,
                display_name=request.display_name,
                description=request.description,
                owner=request.owner,
            )
        directory = _solution_directory().create(
            solution_id=solution_id,
            display_name=request.display_name,
            description=request.description,
            owner=request.owner,
            creation_mode=request.creation_mode,
            template_solution_id=request.template_solution_id,
        )
    except (SolutionCatalogError, SolutionManagementError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "contract": "studio-solution-create-result/v1",
        "solution": _solution_payload(record, directory),
    }


@control_app.patch("/control/solutions/{solution_id}/metadata")
def update_control_solution(
    solution_id: str, request: SolutionDirectoryPatchV1
) -> dict[str, Any]:
    try:
        record = _latest_solution_registration(solution_id)
        current = _directory_entry(record)
        if current.status == "DELETED":
            raise SolutionManagementError("Deleted solutions cannot be changed")
        directory = _solution_directory().patch(current, request)
    except (SolutionCatalogError, SolutionManagementError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _solution_payload(record, directory)


def _solution_has_active_runtime(solution_id: str) -> bool:
    try:
        config = _runtime_configuration(solution_id)
        return (
            _agent_runtime(config).active_ref(config["environment_id"], solution_id)
            is not None
        )
    except PublicationError:
        return False


@control_app.post("/control/solutions/{solution_id}/archive")
def archive_control_solution(solution_id: str) -> dict[str, Any]:
    try:
        record = _latest_solution_registration(solution_id)
        current = _directory_entry(record)
        if _solution_has_active_runtime(solution_id):
            raise SolutionManagementError(
                "Deactivate the Agent runtime before archiving this solution"
            )
        directory = _solution_directory().transition(current, "ARCHIVED")
    except (SolutionCatalogError, SolutionManagementError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _solution_payload(record, directory)


@control_app.post("/control/solutions/{solution_id}/restore")
def restore_control_solution(solution_id: str) -> dict[str, Any]:
    try:
        record = _latest_solution_registration(solution_id)
        current = _directory_entry(record)
        directory = _solution_directory().transition(current, "ACTIVE")
    except (SolutionCatalogError, SolutionManagementError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _solution_payload(record, directory)


@control_app.delete("/control/solutions/{solution_id}")
def delete_control_solution(solution_id: str) -> dict[str, Any]:
    try:
        record = _latest_solution_registration(solution_id)
        current = _directory_entry(record)
        if current.status != "ARCHIVED":
            raise SolutionManagementError(
                "Archive the solution before permanently removing it"
            )
        if _solution_has_active_runtime(solution_id):
            raise SolutionManagementError(
                "Deactivate the Agent runtime before removing this solution"
            )
        if _studio_releases().list(solution_id):
            raise SolutionManagementError(
                "Published releases must be retained; this solution cannot be removed"
            )
        directory = _solution_directory().transition(current, "DELETED")
    except (SolutionCatalogError, SolutionManagementError, PublicationError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "contract": "studio-solution-delete-result/v1",
        "solution_id": solution_id,
        "status": directory.status,
        "audit_artifacts_retained": True,
    }


@control_app.get("/control/solutions/{solution_id}/{solution_version}")
def get_control_solution(solution_id: str, solution_version: str) -> dict[str, Any]:
    try:
        record = _solution_catalog().get(solution_id, solution_version)
        directory = _directory_entry(record)
        if directory.status == "DELETED":
            raise SolutionCatalogError("Solution registration was removed")
    except (SolutionCatalogError, SolutionManagementError) as exc:
        raise HTTPException(status_code=404, detail="Solution registration not found") from exc
    return _solution_payload(record, directory)


@control_app.post("/control/publish")
def publish_control() -> dict[str, Any]:
    package = load_package(DEFAULT_PACKAGE_PATH)
    try:
        publication = _studio_releases().publish(
            package,
            limitations=("constructed synthetic; not HKEX validated",),
        )
    except PublicationError as exc:
        raise HTTPException(status_code=409, detail="Publication blocked") from exc
    return {
        "package_id": publication.ref.package_id,
        "version": publication.ref.version,
        "release_checksum": publication.ref.checksum,
        "idempotent": publication.idempotent,
        "validation_status": publication.validation_status,
    }


@control_app.get("/control/workspaces/{workspace_id}")
def get_workspace(workspace_id: str) -> dict[str, Any]:
    try:
        workspace = _draft_workspaces(workspace_id).get(workspace_id)
    except (WorkspaceError, IntakeError, SolutionCatalogError) as exc:
        raise _workspace_error(exc) from exc
    return workspace.model_dump(mode="json")


@control_app.get("/control/workspaces/{workspace_id}/editor")
def get_workspace_editor(workspace_id: str) -> dict[str, Any]:
    try:
        adapter = _studio_adapter(workspace_id)
        workspace = adapter.workspace.get(workspace_id)
    except (
        WorkspaceError,
        IntakeError,
        SolutionCatalogError,
        EditorDescriptorError,
    ) as exc:
        raise _workspace_error(exc) from exc
    return {
        "contract": "studio-workspace-editor/v1",
        "persistence": (
            "postgresql-s3"
            if adapter.workspace.state_store is not None
            else "legacy-compatibility"
        ),
        "descriptor": adapter.descriptor.model_dump(mode="json"),
        "workspace": workspace.model_dump(mode="json"),
    }


@control_app.get("/control/workspaces/{workspace_id}/editor-descriptor")
def get_workspace_editor_descriptor(workspace_id: str) -> dict[str, Any]:
    try:
        descriptor = _studio_adapter(workspace_id).descriptor
    except (
        WorkspaceError,
        SolutionCatalogError,
        EditorDescriptorError,
    ) as exc:
        raise _workspace_error(exc) from exc
    return descriptor.model_dump(mode="json")


@control_app.get("/control/workspaces/{workspace_id}/workbench")
def get_workspace_workbench(workspace_id: str) -> dict[str, Any]:
    try:
        adapter = _studio_adapter(workspace_id)
        workspace = adapter.workspace.get(workspace_id)
        package = adapter.workspace.candidate_package(workspace_id)
        intake = _studio_intake_payload(workspace_id, adapter.workspace)
        workbench = build_studio_workbench(
            persistence=(
                "postgresql-s3"
                if adapter.workspace.state_store is not None
                else "legacy-compatibility"
            ),
            package=package,
            workspace=workspace,
            intake=intake,
            authoring=build_authoring_projection(
                package=package,
                intake=intake,
                scenario_dir=adapter.workspace.scenario_dir,
            ),
            revisions=adapter.workspace.list_revisions(workspace_id),
            semantic_change_requests=_semantic_change_requests().list(
                package.package_id
            ),
        )
    except (
        WorkspaceError,
        IntakeError,
        SolutionCatalogError,
        EditorDescriptorError,
        SemanticChangeError,
        SourceProjectionError,
    ) as exc:
        raise _workspace_error(exc) from exc
    return workbench.model_dump(mode="json")


@control_app.post("/control/workspaces/{workspace_id}/draft-operations")
def apply_workspace_draft_operations(
    workspace_id: str,
    request: DraftOperationsV1,
) -> dict[str, Any]:
    try:
        workspace = _studio_adapter(workspace_id).apply_operations(
            request, workspace_id=workspace_id
        )
    except (
        WorkspaceError,
        IntakeError,
        SolutionCatalogError,
        EditorDescriptorError,
        ValueError,
    ) as exc:
        raise _workspace_error(exc) from exc
    return workspace.model_dump(mode="json")


@control_app.post("/control/workspaces/{workspace_id}/package-operations")
def apply_workspace_package_operations(
    workspace_id: str,
    request: PackageDraftOperationsV1,
) -> dict[str, Any]:
    try:
        workspace = _studio_adapter(workspace_id).workspace.apply_package_operations(
            request,
            workspace_id=workspace_id,
        )
    except (
        WorkspaceError,
        IntakeError,
        SolutionCatalogError,
        EditorDescriptorError,
        ValueError,
    ) as exc:
        raise _workspace_error(exc) from exc
    return workspace.model_dump(mode="json")


def _source_library_payload(
    workspace_id: str, service: StudioSourceLibraryService
) -> dict[str, Any]:
    current = service.list_current(workspace_id)
    versions = service.list_versions(workspace_id)
    current_ids = {item.source_version_id for item in current}
    return {
        "contract": "studio-source-library/v1",
        "workspace_id": workspace_id,
        "current": [item.model_dump(mode="json") for item in current],
        "versions": [
            {
                **item.model_dump(mode="json"),
                "is_current": item.source_version_id in current_ids,
            }
            for item in versions
        ],
    }


@control_app.get("/control/workspaces/{workspace_id}/sources")
def list_workspace_sources(workspace_id: str) -> dict[str, Any]:
    try:
        _registration_for_workspace(workspace_id)
        service = _studio_source_library()
        return _source_library_payload(workspace_id, service)
    except (SolutionCatalogError, SourceLibraryError) as exc:
        raise _workspace_error(exc) from exc


@control_app.post("/control/workspaces/{workspace_id}/sources")
async def register_workspace_source(
    workspace_id: str,
    request: Request,
    kind: SourceKind,
    title: str,
    original_name: str,
) -> dict[str, Any]:
    try:
        _registration_for_workspace(workspace_id)
        body = await request.body()
        version = _studio_source_library().register(
            workspace_id=workspace_id,
            kind=kind,
            title=title,
            original_name=original_name,
            media_type=request.headers.get("content-type", "application/octet-stream"),
            body=body,
        )
    except (SolutionCatalogError, SourceLibraryError) as exc:
        raise _workspace_error(exc) from exc
    return version.model_dump(mode="json")


@control_app.post("/control/workspaces/{workspace_id}/source-intake/batches")
async def register_workspace_source_batch(
    workspace_id: str,
    manifest_json: str = Form(...),
    files: list[UploadFile] = File(...),
) -> dict[str, Any]:
    """Register one user-selected physical batch and return its exact receipt."""

    try:
        _registration_for_workspace(workspace_id)
        manifest = SourceIntakeBatchManifestV1.model_validate_json(manifest_json)
        if len(files) != len(manifest.items):
            raise SourceLibraryError(
                "Batch manifest and binary part count disagree"
            )
        if len(files) > MAX_SOURCE_BATCH_FILES:
            raise SourceLibraryError("Source intake batch has too many files")
        bodies: list[bytes] = []
        total = 0
        for upload, item in zip(files, manifest.items, strict=True):
            if upload.filename != item.original_name:
                raise SourceLibraryError(
                    "Batch binary order or file identity does not match manifest"
                )
            body = await upload.read()
            total += len(body)
            if total > MAX_SOURCE_BATCH_BYTES:
                raise SourceLibraryError(
                    "Source intake batch exceeds the 100 MiB limit"
                )
            bodies.append(body)
        receipt = _studio_source_library().register_batch(
            workspace_id=workspace_id,
            manifest=manifest,
            bodies=tuple(bodies),
        )
        return receipt.model_dump(mode="json")
    except (SolutionCatalogError, SourceLibraryError, ValueError) as exc:
        raise _workspace_error(exc) from exc


@control_app.post(
    "/control/workspaces/{workspace_id}/sources/install-reference-pack"
)
def install_workspace_reference_source_pack(workspace_id: str) -> dict[str, Any]:
    try:
        registration = _registration_for_workspace(workspace_id)
        root = _installed_solution_root(registration)
        receipt = _studio_source_library().install_reference_pack(
            workspace_id=workspace_id,
            component_root=root,
            manifest_path=root / "intake" / "reference-source-pack.json",
        )
    except (SolutionCatalogError, SourceLibraryError) as exc:
        raise _workspace_error(exc) from exc
    return receipt.model_dump(mode="json")


@control_app.post(
    "/control/workspaces/{workspace_id}/sources/import-installed"
)
def import_workspace_installed_sources(workspace_id: str) -> dict[str, Any]:
    """Promote exact package intake assets into previewable Source Library versions."""

    try:
        registration = _registration_for_workspace(workspace_id)
        root = _installed_solution_root(registration)
        base_intake = _draft_workspaces(workspace_id).get_intake(workspace_id)
        intake_payload = (
            base_intake.model_dump(mode="json")
            if hasattr(base_intake, "model_dump")
            else dict(base_intake)
        )
        asset_values = (
            *(intake_payload.get("assets") or ()),
            *(intake_payload.get("source_files") or ()),
        )
        assets = tuple(
            dict(item) for item in asset_values if isinstance(item, dict)
        )
        resources = tuple(
            item.model_dump(mode="json")
            for item in registration.subject.resources
        )
        service = _studio_source_library()
        service.import_installed_assets(
            workspace_id=workspace_id,
            component_root=root,
            assets=assets,
            resources=resources,
        )
        return _source_library_payload(workspace_id, service)
    except (
        IntakeError,
        SolutionCatalogError,
        SourceLibraryError,
        WorkspaceError,
    ) as exc:
        raise _workspace_error(exc) from exc


@control_app.get(
    "/control/workspaces/{workspace_id}/sources/{source_version_id}/preview"
)
def preview_workspace_source(
    workspace_id: str, source_version_id: str
) -> dict[str, Any]:
    try:
        _registration_for_workspace(workspace_id)
        preview = _studio_source_library().preview(source_version_id, workspace_id)
    except (SolutionCatalogError, SourceLibraryError) as exc:
        raise _workspace_error(exc) from exc
    return preview.model_dump(mode="json")


@control_app.get("/control/workspaces/{workspace_id}/construction-runs")
def list_workspace_construction_runs(workspace_id: str) -> dict[str, Any]:
    try:
        service = _studio_construction(workspace_id)
        records = service.list()
    except (
        ConstructionError,
        WorkspaceError,
        IntakeError,
        SourceProjectionError,
        SolutionCatalogError,
        EditorDescriptorError,
    ) as exc:
        raise _workspace_error(exc) from exc
    return {
        "contract": "construction-run-list/v1",
        "workspace_id": workspace_id,
        "engine_configured": bool(
            os.environ.get("ONTOLOGY_MODEL_GATEWAY_URL", "").strip()
            or os.environ.get("ONTOLOGY_SEMANTICA_WORKER_URL", "").strip()
        ),
        "runs": [
            {
                "run": run.model_dump(mode="json"),
                "decision": (
                    decision.model_dump(mode="json") if decision is not None else None
                ),
            }
            for run, decision in records
        ],
    }


@control_app.get("/control/workspaces/{workspace_id}/construction-jobs")
def list_workspace_construction_jobs(workspace_id: str) -> dict[str, Any]:
    try:
        _registration_for_workspace(workspace_id)
        jobs = _construction_job_store().list(workspace_id)
    except (SolutionCatalogError, ConstructionJobError) as exc:
        raise _workspace_error(exc) from exc
    return {
        "contract": "construction-job-list/v1",
        "workspace_id": workspace_id,
        "jobs": [job.model_dump(mode="json") for job in jobs],
    }


def _build_task_summary(
    job: Any,
    *,
    run_store: Any | None = None,
    solution_name: str | None = None,
) -> StudioBuildTaskSummaryV1:
    """Project durable execution state into one truthful product-level task."""

    if solution_name is None:
        registration = _registration_for_workspace(job.workspace_id)
        display_name = registration.subject.display_name
        solution_name = display_name.zh or display_name.en
    durable_runs = run_store or _construction_run_store()
    run = None
    decision = None
    try:
        run = durable_runs.get_run(job.run_id)
    except ConstructionError:
        # A queued/running job has no immutable run yet. A terminal job without
        # one is deliberately projected as a technical failure by the policy.
        pass
    if run is not None:
        decision = durable_runs.get_decision(run.run_id)
    return project_build_task(
        job=job,
        solution_name=solution_name,
        run=run,
        decision=decision,
    )


@control_app.get("/control/construction-tasks")
def list_construction_tasks(
    status: str | None = None,
    solution_id: str | None = None,
) -> dict[str, Any]:
    try:
        jobs = _construction_job_store().list_all()
        if solution_id:
            jobs = tuple(job for job in jobs if job.solution_id == solution_id)
        run_store = _construction_run_store()
        directory_names = {
            entry.solution_id: entry.display_name.zh or entry.display_name.en
            for entry in _solution_directory().list()
        }
        solution_names: dict[str, str] = {}
        projected: list[StudioBuildTaskSummaryV1] = []
        for job in jobs:
            if job.workspace_id not in solution_names:
                solution_name = directory_names.get(job.solution_id)
                if solution_name is None:
                    registration = _registration_for_workspace(job.workspace_id)
                    display_name = registration.subject.display_name
                    solution_name = display_name.zh or display_name.en
                solution_names[job.workspace_id] = solution_name
            projected.append(
                _build_task_summary(
                    job,
                    run_store=run_store,
                    solution_name=solution_names[job.workspace_id],
                )
            )
        tasks = tuple(projected)
    except (
        ConstructionJobError,
        ConstructionError,
        WorkspaceError,
        IntakeError,
        SourceProjectionError,
        SolutionCatalogError,
        EditorDescriptorError,
    ) as exc:
        raise _workspace_error(exc) from exc
    if status:
        requested = status.strip().upper()
        tasks = tuple(
            task
            for task in tasks
            if task.execution_status == requested or task.result_outcome == requested
        )
    return {
        "contract": "studio-build-task-list/v1",
        "tasks": [task.model_dump(mode="json") for task in tasks],
    }


@control_app.get("/control/construction-tasks/{task_id}")
def get_construction_task(task_id: str) -> dict[str, Any]:
    try:
        task = _build_task_summary(_construction_job_store().get(task_id))
    except (
        ConstructionJobError,
        ConstructionError,
        WorkspaceError,
        IntakeError,
        SourceProjectionError,
        SolutionCatalogError,
        EditorDescriptorError,
    ) as exc:
        raise _workspace_error(exc) from exc
    return task.model_dump(mode="json")


@control_app.post("/control/workspaces/{workspace_id}/construction-jobs")
def enqueue_workspace_construction_job(
    workspace_id: str,
    request: ConstructionStartRequest,
) -> dict[str, Any]:
    try:
        revision = _construction_revision_with_language(workspace_id, request)
        service = _studio_construction(workspace_id, request.source_version_ids)
        job = _construction_job_store().enqueue(
            service.job_input(expected_revision=revision)
        )
    except (
        ConstructionJobConflict,
        ConstructionJobError,
        ConstructionError,
        WorkspaceError,
        IntakeError,
        SourceProjectionError,
        SolutionCatalogError,
        EditorDescriptorError,
    ) as exc:
        raise _workspace_error(exc) from exc
    return job.model_dump(mode="json")


@control_app.post(
    "/control/workspaces/{workspace_id}/construction-jobs/{job_id}/cancel"
)
def cancel_workspace_construction_job(
    workspace_id: str, job_id: str
) -> dict[str, Any]:
    try:
        job = _construction_job_store().cancel(job_id)
        if job.workspace_id != workspace_id:
            raise ConstructionJobError("Construction job workspace mismatch")
    except (ConstructionJobError, ConstructionJobConflict) as exc:
        raise _workspace_error(exc) from exc
    return job.model_dump(mode="json")


@control_app.post(
    "/control/workspaces/{workspace_id}/construction-jobs/{job_id}/retry"
)
def retry_workspace_construction_job(
    workspace_id: str, job_id: str
) -> dict[str, Any]:
    try:
        previous = _construction_job_store().get(job_id)
        if previous.workspace_id != workspace_id:
            raise ConstructionJobError("Construction job workspace mismatch")
        current = _studio_construction(
            workspace_id, previous.selected_source_version_ids
        ).job_input(
            expected_revision=previous.base_revision
        )
        if (
            current.base_draft_checksum != previous.base_draft_checksum
            or current.source_set_digest != previous.source_set_digest
        ):
            raise ConstructionJobConflict(
                "Retry input is stale; enqueue a new run from the current Draft"
            )
        job = _construction_job_store().retry(job_id)
    except (
        ConstructionJobError,
        ConstructionJobConflict,
        ConstructionError,
        WorkspaceError,
        IntakeError,
        SourceProjectionError,
        SolutionCatalogError,
        EditorDescriptorError,
    ) as exc:
        raise _workspace_error(exc) from exc
    return job.model_dump(mode="json")


@control_app.post("/control/workspaces/{workspace_id}/construction-runs")
def start_workspace_construction_run(
    workspace_id: str,
    request: ConstructionStartRequest,
) -> dict[str, Any]:
    try:
        revision = _construction_revision_with_language(workspace_id, request)
        run = _studio_construction(workspace_id, request.source_version_ids).start(
            expected_revision=revision
        )
    except (
        ConstructionError,
        WorkspaceError,
        IntakeError,
        SourceProjectionError,
        SolutionCatalogError,
        EditorDescriptorError,
    ) as exc:
        raise _workspace_error(exc) from exc
    return run.model_dump(mode="json")


@control_app.post(
    "/control/workspaces/{workspace_id}/construction-runs/{run_id}/review"
)
def review_workspace_construction_run(
    workspace_id: str,
    run_id: str,
    request: ConstructionReviewRequestV1,
    http_request: Request,
) -> dict[str, Any]:
    try:
        role = http_request.headers.get("x-atlas-role", "").strip().lower()
        if role and role != "operator":
            raise ConstructionConflict("Operator authority is required for final review")
        principal = http_request.headers.get("x-atlas-user", "").strip()
        authoritative_request = request.model_copy(
            update={"reviewer": principal or request.reviewer}
        )
        service = _studio_construction(workspace_id)
        result = service.review(run_id, authoritative_request)
        if result.decision.workspace_id != workspace_id:
            raise ConstructionConflict("Construction decision workspace mismatch")
    except (
        ConstructionConflict,
        ConstructionError,
        WorkspaceError,
        IntakeError,
        SourceProjectionError,
        SolutionCatalogError,
        EditorDescriptorError,
        ValueError,
    ) as exc:
        raise _workspace_error(exc) from exc
    return result.model_dump(mode="json")


@control_app.get(
    "/control/workspaces/{workspace_id}/construction-runs/{run_id}/decisions/{decision_id}"
)
def get_workspace_construction_decision(
    workspace_id: str,
    run_id: str,
    decision_id: str,
) -> dict[str, Any]:
    try:
        records = _studio_construction(workspace_id).list()
        decision = next(
            (
                current_decision
                for current_run, current_decision in records
                if current_run.run_id == run_id
                and current_decision is not None
                and current_decision.decision_id == decision_id
            ),
            None,
        )
        if decision is None:
            raise ConstructionError("Construction decision is not available")
    except (
        ConstructionError,
        WorkspaceError,
        IntakeError,
        SourceProjectionError,
        SolutionCatalogError,
        EditorDescriptorError,
    ) as exc:
        raise _workspace_error(exc) from exc
    return decision.model_dump(mode="json")


@control_app.get(
    "/control/workspaces/{workspace_id}/construction-runs/{run_id}/review-draft"
)
def get_workspace_construction_review_draft(
    workspace_id: str, run_id: str
) -> dict[str, Any]:
    try:
        run = _studio_construction(workspace_id).get(run_id)
        if run.workspace_id != workspace_id:
            raise ReviewDraftError("Review draft workspace mismatch")
        draft = _review_draft_store().get(run_id)
    except (
        ConstructionError,
        ReviewDraftError,
        WorkspaceError,
        SolutionCatalogError,
    ) as exc:
        raise _workspace_error(exc) from exc
    return {
        "contract": "construction-review-draft-response/v1",
        "workspace_id": workspace_id,
        "run_id": run_id,
        "review_draft": draft.model_dump(mode="json") if draft else None,
    }


@control_app.put(
    "/control/workspaces/{workspace_id}/construction-runs/{run_id}/review-draft"
)
def save_workspace_construction_review_draft(
    workspace_id: str,
    run_id: str,
    request: ReviewDraftSaveV1,
) -> dict[str, Any]:
    try:
        run = _studio_construction(workspace_id).get(run_id)
        if run.workspace_id != workspace_id:
            raise ReviewDraftError("Review draft workspace mismatch")
        draft = _review_draft_store().save(run, request)
    except (
        ConstructionError,
        ReviewDraftError,
        ReviewDraftConflict,
        WorkspaceError,
        SolutionCatalogError,
        ValueError,
    ) as exc:
        raise _workspace_error(exc) from exc
    return draft.model_dump(mode="json")


@control_app.get("/control/workspaces/{workspace_id}/llm/status")
def studio_llm_status(workspace_id: str) -> dict[str, Any]:
    def unavailable() -> dict[str, Any]:
        return {
            "installed": False,
            "demo_class": "STUDIO_LLM_ENGINEERING_DEMO",
            "mode": "off",
            "provider": None,
            "requested_model": None,
            "workflow": "NOT_INSTALLED",
            "slot_count": 0,
            "label": "当前 solution 未安装可用的 Studio LLM profile",
            "can_publish": False,
        }

    try:
        registration = _registration_for_workspace(workspace_id)
        solution_root = _installed_solution_root(registration)
    except (WorkspaceError, SolutionCatalogError) as exc:
        raise _workspace_error(exc) from exc
    manifest_path = (
        solution_root / "llm" / "studio" / "semantic-slot-manifest.json"
    )
    if not manifest_path.is_file():
        return unavailable()
    try:
        manifest = load_semantic_slot_manifest(manifest_path)
        profile = load_studio_run_profile(
            solution_root / "llm" / "studio" / "engineering-profile.json"
        )
    except (OSError, ValueError, StudioLLMError) as exc:
        if workspace_id != "workspace.adt.reference":
            return unavailable()
        raise HTTPException(
            status_code=503, detail="Studio LLM profile is unavailable"
        ) from exc
    mode = os.environ.get("ONTOLOGY_STUDIO_LLM_MODE", "off")
    if mode not in {"off", "active-observation-canary"}:
        mode = "off"
    if workspace_id != "workspace.adt.reference":
        # A package profile is a capability description, not rollout authority.
        # The current canary authority is exact to the ADT observation task.
        mode = "off"
    if mode == "active-observation-canary":
        try:
            service = _studio_observations()
            if (
                service.rollout.mode != mode
                or not service.rollout.permits(
                    profile=service.profile,
                    slot_manifest=service.slot_manifest,
                    egress=service.egress,
                    evaluation=service.evaluation,
                )
            ):
                mode = "off"
        except (OSError, ValueError, StudioLLMError):
            mode = "off"
    return {
        "installed": True,
        "demo_class": "STUDIO_LLM_ENGINEERING_DEMO",
        "mode": mode,
        "provider": profile.provider,
        "requested_model": profile.requested_model,
        "workflow": "CLEARED_INPUT_TO_HUMAN_REVIEWED_DRAFT",
        "slot_count": len(manifest.slots),
        "label": "PROPOSED observations · not published ontology",
        "can_publish": False,
    }


@control_app.get("/control/workspaces/{workspace_id}/llm/observations")
def list_studio_observations(workspace_id: str) -> dict[str, Any]:
    if workspace_id != "workspace.adt.reference":
        raise HTTPException(status_code=404, detail="Draft workspace not found")
    try:
        service = _studio_observations()
        items = service.list_for_workspace(workspace_id)
    except StudioLLMError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "workspace_id": workspace_id,
        "observation_sets": [
            {
                "observation_set": item.model_dump(mode="json"),
                "decision": (
                    decision.model_dump(mode="json")
                    if (decision := service.decision_for(item.observation_set_id))
                    else None
                ),
            }
            for item in items
        ],
    }


@control_app.post("/control/workspaces/{workspace_id}/llm/observations")
def generate_studio_observations(
    workspace_id: str,
    request: ExpectedRevisionRequest,
) -> dict[str, Any]:
    if workspace_id != "workspace.adt.reference":
        raise HTTPException(status_code=404, detail="Draft workspace not found")
    if os.environ.get("ONTOLOGY_STUDIO_LLM_MODE", "off") != "active-observation-canary":
        raise HTTPException(status_code=409, detail="Studio LLM mode is off")
    try:
        observation_set = _studio_observations().generate(
            expected_revision=request.expected_revision
        )
    except (StudioLLMError, WorkspaceError, IntakeError, OSError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return observation_set.model_dump(mode="json")


@control_app.post(
    "/control/workspaces/{workspace_id}/llm/observations/{observation_set_id}/review"
)
def review_studio_observations(
    workspace_id: str,
    observation_set_id: str,
    request: StudioObservationReviewRequest,
) -> dict[str, Any]:
    if workspace_id != "workspace.adt.reference":
        raise HTTPException(status_code=404, detail="Draft workspace not found")
    try:
        result = _studio_observations().review(
            observation_set_id,
            expected_revision=request.expected_revision,
            reviewer="market-data-steward.demo",
            dispositions=request.dispositions,
        )
    except (StudioLLMError, StudioObservationConflict, WorkspaceError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return result.model_dump(mode="json")


@control_app.get("/control/workspaces/{workspace_id}/intake")
def get_workspace_intake(workspace_id: str) -> dict[str, Any]:
    try:
        submission = _draft_workspaces(workspace_id).get_intake(workspace_id)
    except (WorkspaceError, IntakeError, SolutionCatalogError) as exc:
        raise _workspace_error(exc) from exc
    return submission.model_dump(mode="json")


@control_app.get("/control/workspaces/{workspace_id}/revisions")
def get_workspace_revisions(workspace_id: str) -> dict[str, Any]:
    try:
        records = _draft_workspaces(workspace_id).list_revisions(workspace_id)
    except (WorkspaceError, IntakeError, SolutionCatalogError) as exc:
        raise _workspace_error(exc) from exc
    return {
        "workspace_id": workspace_id,
        "revisions": [record.model_dump(mode="json") for record in records],
    }


@control_app.patch("/control/workspaces/{workspace_id}/draft")
def patch_workspace_draft(
    workspace_id: str, request: PatchDraftRequest
) -> dict[str, Any]:
    if workspace_id != "workspace.adt.reference":
        raise HTTPException(
            status_code=422,
            detail="This workspace uses descriptor-driven draft operations",
        )
    try:
        workspace = _draft_workspaces(workspace_id).patch(
            request.update,
            expected_revision=request.expected_revision,
            workspace_id=workspace_id,
        )
    except (WorkspaceError, IntakeError, SolutionCatalogError, ValueError) as exc:
        raise _workspace_error(exc) from exc
    return workspace.model_dump(mode="json")


@control_app.post("/control/workspaces/{workspace_id}/validate")
def validate_workspace_draft(
    workspace_id: str, request: ExpectedRevisionRequest
) -> dict[str, Any]:
    try:
        workspace = _draft_workspaces(workspace_id).validate(
            expected_revision=request.expected_revision,
            workspace_id=workspace_id,
        )
    except (WorkspaceError, IntakeError, SolutionCatalogError) as exc:
        raise _workspace_error(exc) from exc
    return workspace.model_dump(mode="json")


@control_app.post("/control/workspaces/{workspace_id}/publish")
def publish_workspace_draft(
    workspace_id: str, request: ExpectedRevisionRequest
) -> dict[str, Any]:
    try:
        workspace, publication = _draft_workspaces(workspace_id).publish(
            expected_revision=request.expected_revision,
            workspace_id=workspace_id,
        )
    except (WorkspaceError, PublicationError, IntakeError, SolutionCatalogError) as exc:
        raise _workspace_error(exc) from exc
    return {
        "workspace": workspace.model_dump(mode="json"),
        "release": {
            "package_id": publication.ref.package_id,
            "version": publication.ref.version,
            "release_checksum": publication.ref.checksum,
            "idempotent": publication.idempotent,
            "validation_status": publication.validation_status,
        },
    }


@agent_control_app.post("/agent-control/runtime/prepare")
def prepare_runtime(request: PrepareRuntimeRequest) -> dict[str, Any]:
    try:
        config = _runtime_configuration(request.release.package_id)
        certify = (
            request.certify_reference
            if request.certify_reference is not None
            else request.certify_adt
        )
        prepared = _agent_runtime(config).prepare(
            request.release,
            binding=config["binding"],
            certification=config["certification"] if certify else None,
        )
    except PublicationError as exc:
        raise HTTPException(status_code=409, detail="Runtime preparation blocked") from exc
    return {
        "snapshot": prepared.ref.model_dump(mode="json"),
        "readiness": prepared.readiness.model_dump(mode="json"),
        "idempotent": prepared.idempotent,
    }


@agent_control_app.get("/agent-control/healthz")
def agent_control_health() -> dict[str, str]:
    return {"status": "alive", "version": DEMO_VERSION}


@agent_control_app.get("/agent-control/readyz")
def agent_control_readiness() -> dict[str, str]:
    try:
        snapshot = _agent_runtime().open_active("adt-poc", PACKAGE_ID).snapshot
    except PublicationError as exc:
        raise HTTPException(status_code=503, detail="Agent runtime is not ready") from exc
    return {
        "status": "ready",
        "version": DEMO_VERSION,
        "release_checksum": snapshot.release_checksum,
        "snapshot_checksum": snapshot.snapshot_checksum,
    }


@agent_control_app.get("/agent-control/runtime/status/{package_id}")
def agent_runtime_status(package_id: str) -> dict[str, Any]:
    try:
        config = _runtime_configuration(package_id)
        runtime = _agent_runtime(config)
        active = runtime.active_ref(config["environment_id"], package_id)
        rollback_target = runtime.rollback_target(
            config["environment_id"], package_id
        )
    except PublicationError as exc:
        raise HTTPException(status_code=404, detail="Runtime package not found") from exc
    return {
        "environment_id": config["environment_id"],
        "package_id": package_id,
        "state_authority": DurableLifecycleSettings.from_env().mode,
        "active": active.model_dump(mode="json") if active is not None else None,
        "rollback_target": (
            rollback_target.model_dump(mode="json")
            if rollback_target is not None
            else None
        ),
    }


@agent_control_app.post("/agent-control/runtime/activate")
def activate_runtime(request: ActivateRuntimeRequest) -> dict[str, Any]:
    try:
        config = _runtime_configuration(request.snapshot.release.package_id)
        receipt = _agent_runtime(config).activate(
            request.snapshot,
            expected_current=request.expected_current,
            require_certification=(
                config["certification_profile"]
                if request.require_adt_certification
                else None
            ),
        )
    except PublicationError as exc:
        raise HTTPException(status_code=409, detail="Runtime activation blocked") from exc
    return receipt.model_dump(mode="json")


@agent_control_app.post("/agent-control/runtime/rollback")
def rollback_runtime(request: RollbackRuntimeRequest) -> dict[str, Any]:
    try:
        config = _runtime_configuration(request.target_snapshot.release.package_id)
        receipt = _agent_runtime(config).activate(
            request.target_snapshot,
            expected_current=request.expected_current,
            require_certification=(
                config["certification_profile"]
                if request.require_adt_certification
                else None
            ),
        )
    except PublicationError as exc:
        raise HTTPException(status_code=409, detail="Runtime rollback blocked") from exc
    return receipt.model_dump(mode="json")


@agent_control_app.post("/agent-control/runtime/verify-active")
def verify_active_runtime(request: VerifyActiveRequest) -> dict[str, Any]:
    try:
        config = _runtime_configuration(request.expected_snapshot.release.package_id)
        verification = _agent_runtime(config).verify_active(
            config["environment_id"],
            request.expected_snapshot.release.package_id,
            expected_snapshot=request.expected_snapshot,
            execution_dir=DEFAULT_EXECUTION_DIR,
        )
    except PublicationError as exc:
        raise HTTPException(
            status_code=409,
            detail="Active runtime verification blocked",
        ) from exc
    return verification.model_dump(mode="json")
