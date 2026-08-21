from __future__ import annotations

from pathlib import Path
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from ontology_agent import api as api_module
from ontology_agent.api import control_app
from ontology_agent.io import DEFAULT_CASH_TRADING_SCENARIO_DIR, load_package
from ontology_agent.release import StudioReleases
from ontology_agent.studio.construction import (
    ConstructionDispositionV1,
    ConstructionReviewRequestV1,
    FileConstructionRunStore,
    StudioConstructionService,
)
from ontology_agent.studio.construction_jobs import InMemoryConstructionJobStore
from ontology_agent.studio.construction_worker import ConstructionWorker
from ontology_agent.studio.cash_workspace import CashTradingDraftWorkspaceService
from ontology_agent.studio.intake import ADTIntakeRegistry
from ontology_agent.studio.package_authoring import PackageDraftOperationsV1
from ontology_agent.studio.source_projection import build_authoring_projection
from ontology_agent.studio.source_library import (
    FileSourceLibraryStore,
    StudioSourceLibraryService,
)
from ontology_agent.studio.workspace import DraftWorkspaceService, WorkspaceConflictError


control_client = TestClient(control_app)


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
    assert len(reviewed.workspace["package_operations"]) == len(expected_targets)


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
    assert len(result.workspace["package_operations"]) == 3
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
    reviewed = control_client.post(
        "/control/workspaces/workspace.adt.reference/construction-runs/"
        + run["run_id"]
        + "/review",
        json={
            "contract": "construction-review-request/v1",
            "expected_revision": run["base_revision"],
            "reviewer": "domain-owner.demo",
            "dispositions": dispositions,
        },
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["decision"]["status"] == "APPLIED_WITH_DEFERRED"
