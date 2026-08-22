from __future__ import annotations

from pathlib import Path
from io import BytesIO
import hashlib
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from ontology_agent import api as api_module
from ontology_agent.api import control_app
from ontology_agent.io import DEFAULT_CASH_TRADING_SCENARIO_DIR, load_package, sha256_value
from ontology_agent.language_policy import (
    create_authoring_policy,
    operation_language_violations,
)
from ontology_agent.release import StudioReleases
from ontology_agent.studio.construction import (
    ConstructionDispositionV1,
    ConstructionReviewDecisionV1,
    ConstructionReviewRequestV1,
    FileConstructionRunStore,
    PostgresConstructionRunStore,
    StudioConstructionService,
)
from ontology_agent.studio.construction_jobs import InMemoryConstructionJobStore
from ontology_agent.studio.construction_worker import ConstructionWorker
from ontology_agent.studio.task_projection import project_build_task
from ontology_agent.studio.cash_workspace import CashTradingDraftWorkspaceService
from ontology_agent.studio.intake import ADTIntakeRegistry
from ontology_agent.studio.package_authoring import PackageDraftOperationsV1
from ontology_agent.studio.source_projection import build_authoring_projection
from ontology_agent.studio.source_library import (
    FileSourceLibraryStore,
    StudioSourceLibraryService,
)
from ontology_agent.studio.workspace import DraftWorkspaceService, WorkspaceConflictError
from ontology_agent.studio.builder import (
    BoundedBuilderOrchestrator,
    BuilderPhaseOutputV1,
    BuilderPhaseResponseV1,
    _source_operations,
)
from ontology_agent.studio.skill_packages import load_skill_package
from ontology_agent.studio.source_projection import StudioAuthoringProjectionV1
from ontology_agent.studio.reviewer import (
    BoundedReviewerOrchestrator,
    ReviewerFindingV1,
    ReviewerOutputV1,
    ReviewerResponseV1,
)


control_client = TestClient(control_app)


class _ConstructionBuilderModel:
    def generate(self, request):
        proposals = []
        if request.phase == "SEMANTIC":
            proposals = [
                {
                    "contract": "builder-proposal/v1",
                    "proposal_id": "proposal.service_request",
                    "operation": {
                        "action": "UPSERT",
                        "collection": "entities",
                        "object_id": "entity.service_request",
                        "payload": {
                            "id": "entity.service_request",
                            "version": "1.0.0",
                            "status": "proposed",
                            "name": {"en": "Service Request", "zh": "服务请求"},
                            "definition": "A request submitted for service.",
                            "owner": "Business Owner",
                            "sources": ["source.service_request"],
                            "decisions": [],
                            "tags": [],
                            "primary_key": "property.service_request.id",
                            "grain": "one service request",
                            "lifecycle": "submitted to closed",
                        },
                    },
                    "evidence_fragment_ids": [request.evidence_fragments[0].fragment_id],
                    "rationale": "The selected source explicitly describes the object.",
                    "assumptions": [],
                    "confidence": 0.9,
                }
            ]
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
            requested_model="qwen3.8-max",
            response_model="qwen3.8-max",
            provider_request_id=f"provider-{request.phase.lower()}",
            output=output,
            output_digest=sha256_value(output),
        )


class _PartiallyInvalidConstructionBuilderModel(_ConstructionBuilderModel):
    def generate(self, request):
        response = super().generate(request)
        if request.phase != "SEMANTIC":
            return response
        valid = response.output.proposals[0]
        invalid_payload = dict(valid.operation.payload or {})
        invalid_payload["id"] = "entity.untrusted_request"
        invalid_operation = valid.operation.model_copy(
            update={
                "object_id": "entity.untrusted_request",
                "payload": invalid_payload,
            }
        )
        invalid = valid.model_copy(
            update={
                "proposal_id": "proposal.untrusted_request",
                "operation": invalid_operation,
                "evidence_fragment_ids": ("evidence." + "0" * 64,),
            }
        )
        output = response.output.model_copy(
            update={"proposals": (valid, invalid)}
        )
        return response.model_copy(
            update={"output": output, "output_digest": sha256_value(output)}
        )


class _ConstructionReviewerModel:
    def review(self, request):
        target = next(
            item for item in request.candidates if item.candidate_type == "OBJECT"
        )
        finding = ReviewerFindingV1(
            finding_id="finding.model.confirm_owner",
            finding_type="MISSING_COVERAGE",
            severity="WARN",
            summary="对象负责人需要确认",
            detail="材料未明确说明该对象的最终业务负责人。",
            candidate_ids=(target.candidate_id,),
            evidence_fragment_ids=target.evidence_fragment_ids,
            blocks_release=False,
            recommendation="由业务负责人在人工复核时确认 owner。",
        )
        output = ReviewerOutputV1(
            request_digest=request.request_digest,
            findings=(finding,),
            done=True,
        )
        return ReviewerResponseV1(
            requested_model="qwen3.8-max",
            response_model="qwen3.8-max",
            provider_request_id="provider-review",
            output=output,
            output_digest=sha256_value(output),
        )


def _service(
    tmp_path: Path,
    scenario_dir: Path,
) -> tuple[StudioConstructionService, DraftWorkspaceService]:
    workspace = DraftWorkspaceService(
        tmp_path / "studio" / "workspaces",
        scenario_dir,
        StudioReleases(tmp_path / "registry" / "releases"),
    )
    package = workspace.candidate_package()
    intake = ADTIntakeRegistry(tmp_path / "intake", scenario_dir).register_reference()
    authoring = build_authoring_projection(
        package=package,
        intake=intake,
        scenario_dir=scenario_dir,
    )
    return (
        StudioConstructionService(
            store=FileConstructionRunStore(tmp_path / "studio" / "construction"),
            workspace=workspace,
            package=package,
            intake=intake,
            authoring=authoring,
            engine=None,
        ),
        workspace,
    )


def test_source_first_construction_closes_all_exact_inputs_without_claiming_semantica(
    tmp_path: Path,
    scenario_dir: Path,
) -> None:
    service, workspace = _service(tmp_path, scenario_dir)
    before = workspace.get()

    run = service.start(expected_revision=before.revision)

    assert run.status == "NEEDS_REVIEW"
    assert run.engine_status == "NOT_CONFIGURED"
    assert run.base_revision == before.revision
    assert len(run.selected_sources) == 5
    assert all(item.outcome == "SETTLED" for item in run.selected_sources)
    assert len(run.candidates) == 13
    assert sum(item.candidate_type == "REQUIREMENT" for item in run.candidates) == 5
    assert sum(item.candidate_type == "METRIC" for item in run.candidates) == 8
    assert sum(item.compile_eligible for item in run.candidates) == 3
    assert all(item.review_status == "UNREVIEWED" for item in run.candidates)
    assert all(item.support_class == "DIRECT_EXACT" for item in run.candidates)
    assert len({item.occurrence_key for item in run.candidates}) == 13
    assert service.get(run.run_id) == run
    assert service.start(expected_revision=before.revision).run_id == run.run_id


def test_legacy_v1_review_decision_keeps_its_original_exact_identity() -> None:
    provisional = ConstructionReviewDecisionV1(
        contract="construction-review-decision/v1",
        decision_id="construction-decision." + "1" * 32,
        run_id="construction-run." + "2" * 32,
        run_checksum="3" * 64,
        workspace_id="workspace.legacy",
        base_revision=1,
        base_draft_checksum="4" * 64,
        reviewer="domain-owner.demo",
        dispositions=(),
        request_digest="5" * 64,
        status="REVIEWED_NO_CHANGE",
        resulting_revision=1,
        resulting_draft_checksum="4" * 64,
        decided_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
        decision_checksum="0" * 64,
    )
    v2_only_fields = {
        "applied",
        "deferred_candidate_ids",
        "rejected_candidate_ids",
        "server_blockers",
    }
    unsigned = provisional.model_dump(
        mode="json",
        exclude={"decision_checksum", *v2_only_fields},
        exclude_none=True,
    )
    decision = provisional.model_copy(
        update={"decision_checksum": sha256_value(unsigned)}
    )
    legacy_subject = decision.model_dump(mode="json", exclude=v2_only_fields)
    row = SimpleNamespace(
        run_id=decision.run_id,
        decision_id=decision.decision_id,
        workspace_id=decision.workspace_id,
        decision_checksum=decision.decision_checksum,
        subject_checksum=sha256_value(
            decision.model_dump(
                mode="json",
                exclude=v2_only_fields,
                exclude_none=True,
            )
        ),
        request_digest=decision.request_digest,
        subject=legacy_subject,
    )

    restored = PostgresConstructionRunStore._decision_from_row(row)

    assert restored == decision


def test_product_task_projects_execution_success_as_review_ready_not_complete(
    tmp_path: Path,
    scenario_dir: Path,
) -> None:
    service, workspace = _service(tmp_path, scenario_dir)
    before = workspace.get()
    jobs = InMemoryConstructionJobStore()
    claimed = jobs.claim_next_after_enqueue(
        service.job_input(expected_revision=before.revision), "worker-a"
    )
    run = service.start(
        expected_revision=before.revision,
        planned_run_id=claimed.run_id,
        attempt_id=claimed.attempt_id,
        lease_epoch=claimed.lease_epoch,
    )
    jobs.begin_commit(claimed.job_id, "worker-a", claimed.lease_epoch)
    completed = jobs.complete_success(
        claimed.job_id,
        "worker-a",
        claimed.lease_epoch,
        run_id=run.run_id,
    )

    task = project_build_task(
        job=completed,
        solution_name="ADT 参考分析",
        run=run,
        decision=None,
    )

    assert task.execution_status == "SUCCEEDED"
    assert task.result_outcome in {"REVIEW_READY", "REVIEW_READY_WITH_WARNINGS"}
    assert task.review_status == "NEEDS_REVIEW"
    assert task.destination.type == "REVIEW"


def test_task_api_reads_durable_job_run_and_decision_without_building_workspace(
    tmp_path: Path,
    scenario_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, workspace = _service(tmp_path, scenario_dir)
    before = workspace.get()
    jobs = InMemoryConstructionJobStore()
    claimed = jobs.claim_next_after_enqueue(
        service.job_input(expected_revision=before.revision), "worker-a"
    )
    run = service.start(
        expected_revision=before.revision,
        planned_run_id=claimed.run_id,
        attempt_id=claimed.attempt_id,
        lease_epoch=claimed.lease_epoch,
    )
    jobs.begin_commit(claimed.job_id, "worker-a", claimed.lease_epoch)
    completed = jobs.complete_success(
        claimed.job_id,
        "worker-a",
        claimed.lease_epoch,
        run_id=run.run_id,
    )

    class _DurableRunStore:
        def __init__(self) -> None:
            self.run_reads = 0
            self.decision_reads = 0

        def get_run(self, run_id: str):
            self.run_reads += 1
            assert run_id == run.run_id
            return run

        def get_decision(self, run_id: str):
            self.decision_reads += 1
            assert run_id == run.run_id
            return None

    durable = _DurableRunStore()
    registration_reads = []

    monkeypatch.setattr(api_module, "_construction_job_store", lambda: jobs)
    monkeypatch.setattr(api_module, "_construction_run_store", lambda settings=None: durable)
    monkeypatch.setattr(
        api_module,
        "_solution_directory",
        lambda: SimpleNamespace(list=lambda: ()),
    )

    def registration(workspace_id: str):
        registration_reads.append(workspace_id)
        return SimpleNamespace(
            subject=SimpleNamespace(
                display_name=SimpleNamespace(zh="ADT 参考分析", en="ADT Reference")
            )
        )

    monkeypatch.setattr(api_module, "_registration_for_workspace", registration)

    def forbidden_workspace_build(*args, **kwargs):
        raise AssertionError("task projection must not initialize Studio construction")

    monkeypatch.setattr(api_module, "_studio_construction", forbidden_workspace_build)

    response = control_client.get("/control/construction-tasks")

    assert response.status_code == 200
    assert response.json()["tasks"][0]["task_id"] == completed.job_id
    assert response.json()["tasks"][0]["review_status"] == "NEEDS_REVIEW"
    assert durable.run_reads == 1
    assert durable.decision_reads == 1
    assert registration_reads == [completed.workspace_id]


def test_generic_builder_candidates_enter_review_without_writing_draft(
    tmp_path: Path,
    scenario_dir: Path,
) -> None:
    workspace = DraftWorkspaceService(
        tmp_path / "workspace",
        scenario_dir,
        StudioReleases(tmp_path / "releases"),
    )
    package = workspace.candidate_package()
    body = "A service request is submitted, assessed and closed."
    intake = {
        "assets": [
            {
                "asset_id": "source.service_request",
                "kind": "requirement_transcription",
                "locator": "source-library:source-version.00000000000000000000000000000000",
                "source_version_id": "source-version.00000000000000000000000000000000",
                "checksum": hashlib.sha256(body.encode()).hexdigest(),
                "registered_at": "2026-08-22T00:00:00Z",
                "content_text": body,
            }
        ]
    }
    before = workspace.get()
    service = StudioConstructionService(
        store=FileConstructionRunStore(tmp_path / "construction"),
        workspace=workspace,
        package=package,
        intake=intake,
        authoring=StudioAuthoringProjectionV1(
            requirements=(), metric_candidates=(), source_mode="CANONICAL_FALLBACK"
        ),
        builder=BoundedBuilderOrchestrator(
            model=_ConstructionBuilderModel(),
            skill=load_skill_package("ontology-build", "1.0.0"),
        ),
        reviewer=BoundedReviewerOrchestrator(
            model=_ConstructionReviewerModel(),
            skill=load_skill_package("ontology-review", "1.0.0"),
        ),
        engine=None,
    )

    run = service.start(expected_revision=before.revision)

    assert run.engine_status == "COMPLETED"
    assert workspace.get().revision == before.revision
    assert {item.candidate_type for item in run.candidates} == {"SOURCE", "OBJECT"}
    builder_stage = next(item for item in run.stage_receipts if item.stage == "BUILDER_AGENT")
    assert builder_stage.status == "PASS"
    reviewer_stage = next(item for item in run.stage_receipts if item.stage == "REVIEWER_AGENT")
    assert reviewer_stage.status == "PASS"
    assert run.machine_findings[0].finding_id == "finding.model.confirm_owner"
    assert all(item.review_status == "UNREVIEWED" for item in run.candidates)


def test_builder_quarantines_one_unknown_evidence_citation_without_losing_valid_work(
    tmp_path: Path,
    scenario_dir: Path,
) -> None:
    workspace = DraftWorkspaceService(
        tmp_path / "workspace",
        scenario_dir,
        StudioReleases(tmp_path / "releases"),
    )
    package = workspace.candidate_package()
    body = "A service request is submitted, assessed and closed."
    intake = {
        "assets": [
            {
                "asset_id": "source.service_request",
                "kind": "requirement_transcription",
                "locator": "source-library:source-version.00000000000000000000000000000000",
                "source_version_id": "source-version.00000000000000000000000000000000",
                "checksum": hashlib.sha256(body.encode()).hexdigest(),
                "registered_at": "2026-08-22T00:00:00Z",
                "content_text": body,
            }
        ]
    }
    service = StudioConstructionService(
        store=FileConstructionRunStore(tmp_path / "construction"),
        workspace=workspace,
        package=package,
        intake=intake,
        authoring=StudioAuthoringProjectionV1(
            requirements=(), metric_candidates=(), source_mode="CANONICAL_FALLBACK"
        ),
        builder=BoundedBuilderOrchestrator(
            model=_PartiallyInvalidConstructionBuilderModel(),
            skill=load_skill_package("ontology-build", "1.0.0"),
        ),
        engine=None,
    )

    run = service.start(expected_revision=workspace.get().revision)

    assert {item.candidate_type for item in run.candidates} == {
        "SOURCE",
        "OBJECT",
        "GAP",
    }
    assert not any(
        item.canonical_target == "entity.untrusted_request" for item in run.candidates
    )
    quarantined = next(
        item for item in run.candidates if item.candidate_type == "GAP"
    )
    assert (
        quarantined.proposal["gap_id"]
        == "gap.quarantined.proposal.untrusted_request"
    )
    assert quarantined.compile_eligible is False
    builder_stage = next(
        item for item in run.stage_receipts if item.stage == "BUILDER_AGENT"
    )
    assert builder_stage.status == "PASS"


def test_builder_registers_source_notes_in_the_selected_authoring_language(
    tmp_path: Path,
    scenario_dir: Path,
) -> None:
    workspace = DraftWorkspaceService(
        tmp_path / "workspace",
        scenario_dir,
        StudioReleases(tmp_path / "releases"),
    )
    package = workspace.candidate_package().model_copy(
        update={"authoring_policy": create_authoring_policy("zh")}
    )
    body = "证券交收失败监控业务需求。"
    intake = {
        "assets": [
            {
                "asset_id": "source.requirements",
                "kind": "requirement_transcription",
                "title": "业务需求",
                "locator": "source-library:source-version.00000000000000000000000000000000",
                "source_version_id": "source-version.00000000000000000000000000000000",
                "checksum": hashlib.sha256(body.encode()).hexdigest(),
                "registered_at": "2026-08-22T00:00:00Z",
                "content_text": body,
            }
        ]
    }

    operation = _source_operations(intake, package=package)[0]
    payload = operation.payload or {}

    assert str(payload["notes"]).startswith("已登记的精确来源版本。内容校验和：")
    assert operation_language_violations(payload, package.authoring_policy) == ()


def test_durable_worker_executes_planned_run_and_records_terminal_job(
    tmp_path: Path,
    scenario_dir: Path,
) -> None:
    service, workspace = _service(tmp_path, scenario_dir)
    jobs = InMemoryConstructionJobStore()
    queued = jobs.enqueue(service.job_input(expected_revision=workspace.get().revision))
    worker = ConstructionWorker(
        jobs=jobs,
        service_factory=lambda workspace_id, selected_source_version_ids: service,
        worker_id="worker.test",
    )

    completed = worker.process_one()

    assert completed is not None
    assert completed.job_id == queued.job_id
    assert completed.status == "SUCCEEDED"
    assert completed.result_run_id == queued.run_id
    assert service.get(queued.run_id).attempt_id == completed.attempt_id


def test_materially_different_cash_trading_case_uses_the_same_run_candidate_seam(
    tmp_path: Path,
) -> None:
    workspace = CashTradingDraftWorkspaceService(
        tmp_path / "cash-workspaces",
        DEFAULT_CASH_TRADING_SCENARIO_DIR,
        StudioReleases(tmp_path / "cash-releases"),
    )
    current = workspace.get()
    package = workspace.candidate_package()
    intake = workspace.get_intake()
    authoring = build_authoring_projection(
        package=package,
        intake=intake,
        scenario_dir=DEFAULT_CASH_TRADING_SCENARIO_DIR,
    )
    service = StudioConstructionService(
        store=FileConstructionRunStore(tmp_path / "cash-construction"),
        workspace=workspace,
        package=package,
        intake=intake,
        authoring=authoring,
        engine=None,
    )

    run = service.start(expected_revision=current.revision)

    assert run.status == "NEEDS_REVIEW"
    assert len(run.selected_sources) == 4
    assert {item.source_id for item in run.selected_sources} == {
        "SRC-EMAIL-001",
        "SRC-REQ-001",
        "SRC-DICT-001",
        "SRC-SAMPLE-001",
    }
    assert authoring.source_mode == "CANONICAL_FALLBACK"
    assert {item.candidate_type for item in run.candidates} == {"REQUIREMENT", "METRIC"}
    assert all(item.support_class == "SYNTHETIC" for item in run.candidates)


def test_exact_cash_reference_pack_compiles_a_complete_typed_case_candidate_set(
    tmp_path: Path,
) -> None:
    workspace = CashTradingDraftWorkspaceService(
        tmp_path / "cash-workspaces",
        DEFAULT_CASH_TRADING_SCENARIO_DIR,
        StudioReleases(tmp_path / "cash-releases"),
    )
    library = StudioSourceLibraryService(FileSourceLibraryStore(tmp_path / "sources"))
    receipt = library.install_reference_pack(
        workspace_id="workspace.cash_trading.reference",
        component_root=DEFAULT_CASH_TRADING_SCENARIO_DIR,
        manifest_path=(
            DEFAULT_CASH_TRADING_SCENARIO_DIR
            / "intake"
            / "reference-source-pack.json"
        ),
    )
    intake = workspace.get_intake().model_dump(mode="json")
    intake["assets"] = library.current_intake_assets(
        "workspace.cash_trading.reference",
        include_parsed_attachments=True,
    )
    package = workspace.candidate_package()
    authoring = build_authoring_projection(
        package=package,
        intake=intake,
        scenario_dir=DEFAULT_CASH_TRADING_SCENARIO_DIR,
    )
    service = StudioConstructionService(
        store=FileConstructionRunStore(tmp_path / "cash-construction"),
        workspace=workspace,
        package=package,
        intake=intake,
        authoring=authoring,
        engine=None,
    )

    run = service.start(expected_revision=workspace.get().revision)

    assert receipt.registered_source_count == 6
    assert authoring.source_mode == "EXACT_TRANSCRIPTION"
    assert len(run.selected_sources) == 6
    profile_stage = next(
        item
        for item in run.stage_receipts
        if item.stage == "PACKAGED_CASE_COMPILATION"
    )
    assert profile_stage.status == "PASS"
    assert profile_stage.item_count > 100
    typed_targets = {
        (item.proposed_operation.collection, item.proposed_operation.object_id)
        for item in run.candidates
        if item.proposed_operation is not None
    }
    expected_targets = {
        (collection, item.id)
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
        for item in getattr(package, collection)
    }
    assert typed_targets == expected_targets
    assert len(typed_targets) == sum(
        item.compile_eligible for item in run.candidates
    )
    assert {item.candidate_type for item in run.candidates}.issuperset(
        {
            "ACTOR",
            "PROCESS",
            "OBJECT",
            "PROPERTY",
            "LINK",
            "DIMENSION",
            "RULE",
            "METRIC",
            "DATA_SOURCE",
            "MAPPING",
            "JOIN",
            "ANALYSIS_PATTERN",
            "POLICY",
            "QUESTION",
        }
    )
    packaged = [
        item
        for item in run.candidates
        if item.proposal.get("contract") == "packaged-case-candidate/v1"
    ]
    assert packaged
    assert all(item.review_status == "UNREVIEWED" for item in packaged)
    assert all(item.support_class != "DIRECT_EXACT" for item in packaged)
    assert all(
        "reviewed baseline" in " ".join(item.limitations).lower()
        for item in packaged
    )

    reviewed = service.review(
        run.run_id,
        ConstructionReviewRequestV1(
            expected_revision=run.base_revision,
            reviewer="domain-owner.demo",
            dispositions=tuple(
                ConstructionDispositionV1(
                    candidate_id=item.candidate_id,
                    action="ACCEPT" if item.compile_eligible else "DEFER",
                    note=(
                        "Typed candidate reviewed against exact source and assumption boundary"
                        if item.compile_eligible
                        else "Source observation retained as non-authoritative evidence"
                    ),
                    blocks_release=False,
                )
                for item in run.candidates
            ),
        ),
    )
    assert reviewed.decision.status == "APPLIED_WITH_DEFERRED"
    assert len(reviewed.workspace["package_operations"]) == 2 * len(expected_targets)
    assert len(reviewed.decision.applied) == len(expected_targets)
    assert all(
        item.confirmation_status == "CONFIRMED"
        for item in reviewed.decision.applied
    )


def test_cash_attachments_become_exact_human_review_candidates_without_automatic_truth(
    tmp_path: Path,
) -> None:
    workspace = CashTradingDraftWorkspaceService(
        tmp_path / "cash-workspaces",
        DEFAULT_CASH_TRADING_SCENARIO_DIR,
        StudioReleases(tmp_path / "cash-releases"),
    )
    package = workspace.candidate_package()
    library = StudioSourceLibraryService(FileSourceLibraryStore(tmp_path / "sources"))

    dictionary_book = Workbook()
    overview = dictionary_book.active
    overview.title = "Data Model Overview"
    overview.append(["Table", "Category", "Primary Key", "Purpose", "Key Relationships", "Field Count"])
    overview.append(["trading_activity", "Activity", "trade_id", "Trade events", "instrument_id -> instrument_reference", 3])
    dictionary = dictionary_book.create_sheet("trading_activity")
    dictionary.append(["Table Name", "Field Name", "Field Description", "Nullable", "Allowable Value/Value List (if any)", "Data Type", "Source Database", "Source Table", "Source Field", "Transform Logic", "Remark"])
    dictionary.append(["trading_activity", "trade_id", "Trade identifier", "No", "Unique", "VARCHAR(64)", "ODS", "trade_event", "trade_id", "identity", "Primary key"])
    dictionary.append(["trading_activity", "instrument_id", "Instrument identifier", "No", "Instrument master", "VARCHAR(64)", "ODS", "trade_event", "instrument_id", "lookup", "Foreign key"])
    dictionary_payload = BytesIO()
    dictionary_book.save(dictionary_payload)
    library.register(
        workspace_id="workspace.cash_trading.reference",
        kind="data_dictionary",
        title="Cash data dictionary",
        original_name="dictionary.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        body=dictionary_payload.getvalue(),
    )

    sample_book = Workbook()
    sample = sample_book.active
    sample.title = "trading_activity"
    sample.append(["trade_id", "instrument_id"])
    sample.append(["T-1", "I-1"])
    sample_payload = BytesIO()
    sample_book.save(sample_payload)
    library.register(
        workspace_id="workspace.cash_trading.reference",
        kind="data_dictionary",
        title="Synthetic sample data",
        original_name="sample.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        body=sample_payload.getvalue(),
    )
    library.register(
        workspace_id="workspace.cash_trading.reference",
        kind="sql",
        title="Existing calculation SQL",
        original_name="controls.sql",
        media_type="text/sql",
        body=b"SELECT COUNT(*) FROM trading_activity;\n",
    )
    intake = {
        "contract": "cash-test-intake/v1",
        "assets": library.current_intake_assets(
            "workspace.cash_trading.reference", include_parsed_attachments=True
        ),
    }
    authoring = build_authoring_projection(
        package=package,
        intake=intake,
        scenario_dir=DEFAULT_CASH_TRADING_SCENARIO_DIR,
    )
    service = StudioConstructionService(
        store=FileConstructionRunStore(tmp_path / "cash-construction"),
        workspace=workspace,
        package=package,
        intake=intake,
        authoring=authoring,
        engine=None,
    )

    run = service.start(expected_revision=workspace.get().revision)
    contracts = {item.proposal.get("contract") for item in run.candidates}

    assert "source-table-observation/v1" in contracts
    assert "source-table-mapping-observation/v1" in contracts
    assert "source-sample-schema-observation/v1" in contracts
    assert "source-sql-observation/v1" in contracts
    assert "source-schema-consistency-observation/v1" in contracts
    attachment_candidates = [
        item for item in run.candidates if str(item.proposal.get("contract", "")).startswith("source-")
    ]
    assert attachment_candidates
    assert all(not item.compile_eligible for item in attachment_candidates)
    assert all(item.source_anchors for item in attachment_candidates)
    assert all(item.review_status == "UNREVIEWED" for item in attachment_candidates)
    mapping = next(
        item
        for item in attachment_candidates
        if item.proposal.get("contract")
        == "source-table-mapping-observation/v1"
    )
    assert mapping.proposal["count_matches_declared"] is False
    assert any("declares 3 fields" in item for item in mapping.limitations)
    consistency = next(
        item
        for item in attachment_candidates
        if item.proposal.get("contract")
        == "source-schema-consistency-observation/v1"
    )
    assert consistency.proposal["status"] == "MATCH"
    assert len(consistency.source_anchors) == 2


def test_review_requires_every_candidate_and_applies_only_typed_operations_once(
    tmp_path: Path,
    scenario_dir: Path,
) -> None:
    service, workspace = _service(tmp_path, scenario_dir)
    before = workspace.get()
    run = service.start(expected_revision=before.revision)
    dispositions = tuple(
        ConstructionDispositionV1(
            candidate_id=item.candidate_id,
            action="ACCEPT" if item.compile_eligible else "DEFER",
            note="直接证据支持" if item.compile_eligible else "待补编译能力",
            blocks_release=not item.compile_eligible,
        )
        for item in run.candidates
    )

    result = service.review(
        run.run_id,
        ConstructionReviewRequestV1(
            expected_revision=before.revision,
            reviewer="domain-owner.demo",
            dispositions=dispositions,
        ),
    )

    assert result.decision.status == "APPLIED_WITH_DEFERRED"
    assert result.workspace["revision"] == before.revision + 1
    assert len(result.workspace["package_operations"]) == 6
    assert len(result.decision.applied) == 3
    assert all(
        item.confirmation_status == "CONFIRMED"
        for item in result.decision.applied
    )
    assert service.review(
        run.run_id,
        ConstructionReviewRequestV1(
            expected_revision=before.revision,
            reviewer="domain-owner.demo",
            dispositions=dispositions,
        ),
    ).decision == result.decision


def test_stale_run_and_compile_ineligible_accept_fail_closed(
    tmp_path: Path,
    scenario_dir: Path,
) -> None:
    service, workspace = _service(tmp_path, scenario_dir)
    before = workspace.get()
    run = service.start(expected_revision=before.revision)
    unsupported = next(item for item in run.candidates if not item.compile_eligible)
    bad = tuple(
        ConstructionDispositionV1(
            candidate_id=item.candidate_id,
            action="ACCEPT" if item.candidate_id == unsupported.candidate_id else "REJECT",
            note="test",
            blocks_release=False,
        )
        for item in run.candidates
    )
    with pytest.raises(ValueError, match="not compile eligible"):
        service.review(
            run.run_id,
            ConstructionReviewRequestV1(
                expected_revision=before.revision,
                reviewer="domain-owner.demo",
                dispositions=bad,
            ),
        )

    workspace.apply_package_operations(
        PackageDraftOperationsV1.model_validate({
            "contract": "studio-package-operations/v1",
            "expected_revision": before.revision,
            "operations": [
                {
                    "action": "UPSERT",
                    "collection": "metrics",
                    "object_id": "metric.average_daily_turnover",
                    "payload": load_package(
                        scenario_dir / "ontology" / "package.yaml"
                    ).metrics[2].model_dump(mode="json"),
                }
            ],
        })
    )
    rejected = tuple(
        ConstructionDispositionV1(
            candidate_id=item.candidate_id,
            action="REJECT",
            note="stale",
            blocks_release=False,
        )
        for item in run.candidates
    )
    with pytest.raises(WorkspaceConflictError, match="stale"):
        service.review(
            run.run_id,
            ConstructionReviewRequestV1(
                expected_revision=before.revision,
                reviewer="domain-owner.demo",
                dispositions=rejected,
            ),
        )


def test_control_api_exposes_run_and_review_without_hidden_adt_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    scenario_dir: Path,
) -> None:
    monkeypatch.delenv("ONTOLOGY_PRODUCT_STATE_MODE", raising=False)
    monkeypatch.delenv("ONTOLOGY_SEMANTICA_WORKER_URL", raising=False)
    monkeypatch.setattr(api_module, "DEFAULT_SCENARIO_DIR", scenario_dir)
    monkeypatch.setattr(api_module, "DEFAULT_STUDIO_DIR", tmp_path / "studio-api")
    monkeypatch.setattr(api_module, "DEFAULT_PUBLISHED_DIR", tmp_path / "registry-api")
    opened = control_client.get(
        "/control/workspaces/workspace.adt.reference/workbench"
    ).json()

    generated = control_client.post(
        "/control/workspaces/workspace.adt.reference/construction-runs",
        json={"expected_revision": opened["workspace"]["revision"]},
    )

    assert generated.status_code == 200
    run = generated.json()
    assert run["engine_status"] == "NOT_CONFIGURED"
    assert len(run["candidates"]) == 13
    listed = control_client.get(
        "/control/workspaces/workspace.adt.reference/construction-runs"
    )
    assert listed.status_code == 200
    assert listed.json()["runs"][0]["run"]["run_id"] == run["run_id"]
    dispositions = [
        {
            "candidate_id": item["candidate_id"],
            "action": "ACCEPT" if item["compile_eligible"] else "DEFER",
            "note": "reviewed source" if item["compile_eligible"] else "compiler gap",
            "blocks_release": not item["compile_eligible"],
        }
        for item in run["candidates"]
    ]
    forbidden = control_client.post(
        "/control/workspaces/workspace.adt.reference/construction-runs/"
        + run["run_id"]
        + "/review",
        headers={"X-Atlas-Role": "viewer", "X-Atlas-User": "read-only.user"},
        json={
            "contract": "construction-review-request/v1",
            "expected_revision": run["base_revision"],
            "reviewer": "spoofed.user",
            "dispositions": dispositions,
        },
    )
    assert forbidden.status_code == 409
    reviewed = control_client.post(
        "/control/workspaces/workspace.adt.reference/construction-runs/"
        + run["run_id"]
        + "/review",
        headers={"X-Atlas-Role": "operator", "X-Atlas-User": "hkex.domain.owner"},
        json={
            "contract": "construction-review-request/v1",
            "expected_revision": run["base_revision"],
            "reviewer": "domain-owner.demo",
            "dispositions": dispositions,
        },
    )
    assert reviewed.status_code == 200
    decision = reviewed.json()["decision"]
    assert decision["contract"] == "construction-review-decision/v2"
    assert decision["status"] == "APPLIED_WITH_DEFERRED"
    assert decision["reviewer"] == "hkex.domain.owner"
    assert decision["applied"]
    assert all(item["confirmation_status"] == "CONFIRMED" for item in decision["applied"])
    assert reviewed.json()["workspace"]["revision"] == run["base_revision"] + 1

    fetched = control_client.get(
        "/control/workspaces/workspace.adt.reference/construction-runs/"
        + run["run_id"]
        + "/decisions/"
        + decision["decision_id"]
    )
    assert fetched.status_code == 200
    assert fetched.json() == decision

    retried = control_client.post(
        "/control/workspaces/workspace.adt.reference/construction-runs/"
        + run["run_id"]
        + "/review",
        headers={"X-Atlas-Role": "operator", "X-Atlas-User": "hkex.domain.owner"},
        json={
            "contract": "construction-review-request/v1",
            "expected_revision": run["base_revision"],
            "reviewer": "spoofed.user",
            "dispositions": dispositions,
        },
    )
    assert retried.status_code == 200
    assert retried.json()["decision"] == decision
