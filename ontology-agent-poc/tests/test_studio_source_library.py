from __future__ import annotations

import hashlib
import json
from pathlib import Path
from io import BytesIO

import pytest
from openpyxl import Workbook

from ontology_agent.studio.source_library import (
    FileSourceLibraryStore,
    SourceIntakeBatchManifestV1,
    SourceLibraryConflict,
    SourceLibraryError,
    StudioSourceLibraryService,
)
from ontology_agent.studio.intake import ADTIntakeRegistry


PROJECT_ROOT = Path(__file__).parents[1]
CASH_SCENARIO = PROJECT_ROOT / "scenarios" / "cash_trading"
ADT_SCENARIO = PROJECT_ROOT / "scenarios" / "adt"


def _service(tmp_path: Path) -> StudioSourceLibraryService:
    return StudioSourceLibraryService(FileSourceLibraryStore(tmp_path / "sources"))


def test_source_versions_are_immutable_and_one_current_version_exists_per_logical_source(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)

    first = service.register(
        workspace_id="workspace.adt.reference",
        kind="requirement_transcription",
        title="需求说明",
        original_name="requirements.md",
        media_type="text/markdown",
        body=b"| O-01 | What is ADT? | period and value | table |\n",
    )
    second = service.register(
        workspace_id="workspace.adt.reference",
        kind="requirement_transcription",
        title="需求说明（修订）",
        original_name="requirements.md",
        media_type="text/markdown",
        body=b"| O-01 | What is ADT? | period, value and evidence | table |\n",
    )

    assert first.source_version_id != second.source_version_id
    assert service.list_current("workspace.adt.reference") == (second,)
    assert service.list_versions("workspace.adt.reference") == (second, first)
    assert service.read_exact(first) != service.read_exact(second)


def test_batch_intake_registers_multiple_files_and_multiple_roles_with_one_receipt(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    requirements = "O-01,分析每日成交活动\n".encode()
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Data Dictionary"
    sheet.append(["field", "type"])
    sheet.append(["trade_id", "string"])
    workbook_body = BytesIO()
    workbook.save(workbook_body)
    manifest = SourceIntakeBatchManifestV1.model_validate(
        {
            "idempotency_key": "batch-browser-0001",
            "items": [
                {
                    "client_file_id": "requirements",
                    "original_name": "requirements.csv",
                    "declared_media_type": "text/csv",
                    "registrations": [
                        {"kind": "requirement_transcription", "title": "业务需求"},
                    ],
                },
                {
                    "client_file_id": "dictionary",
                    "original_name": "cash_dictionary.xlsx",
                    "declared_media_type": "application/octet-stream",
                    "registrations": [
                        {"kind": "data_dictionary", "title": "字段字典"},
                        {"kind": "data_model", "title": "逻辑数据模型"},
                    ],
                },
            ],
        }
    )

    receipt = service.register_batch(
        workspace_id="workspace.cash.batch",
        manifest=manifest,
        bodies=(requirements, workbook_body.getvalue()),
    )
    repeated = service.register_batch(
        workspace_id="workspace.cash.batch",
        manifest=manifest,
        bodies=(requirements, workbook_body.getvalue()),
    )

    assert receipt == repeated
    assert [item.capability for item in receipt.physical_files] == [
        "TEXT_EXTRACTED",
        "XLSX_TABULAR_EXTRACTED",
    ]
    assert len(receipt.registrations) == 3
    assert receipt.failures == ()
    assert len(service.list_current("workspace.cash.batch")) == 3


def test_batch_intake_reports_archived_only_and_rejects_it_for_transcription(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    manifest = SourceIntakeBatchManifestV1.model_validate(
        {
            "idempotency_key": "batch-browser-0002",
            "items": [
                {
                    "client_file_id": "supporting-pdf",
                    "original_name": "supporting.pdf",
                    "declared_media_type": "application/pdf",
                    "registrations": [{"kind": "other", "title": "补充材料"}],
                },
                {
                    "client_file_id": "requirements-pdf",
                    "original_name": "requirements.pdf",
                    "declared_media_type": "application/pdf",
                    "registrations": [
                        {"kind": "requirement_transcription", "title": "业务需求"}
                    ],
                },
            ],
        }
    )

    receipt = service.register_batch(
        workspace_id="workspace.cash.batch",
        manifest=manifest,
        bodies=(b"%PDF synthetic", b"%PDF synthetic requirements"),
    )

    assert receipt.physical_files[0].capability == "ARCHIVED_ONLY"
    assert receipt.registrations[0].capability == "ARCHIVED_ONLY"
    assert receipt.failures[0].client_file_id == "requirements-pdf"
    assert receipt.failures[0].reason_code == "TRANSCRIPTION_REQUIRES_TEXT_OR_XLSX"


def test_batch_idempotency_key_cannot_name_different_bytes(tmp_path: Path) -> None:
    service = _service(tmp_path)
    manifest = SourceIntakeBatchManifestV1.model_validate(
        {
            "idempotency_key": "batch-browser-0003",
            "items": [
                {
                    "client_file_id": "requirements",
                    "original_name": "requirements.md",
                    "declared_media_type": "text/markdown",
                    "registrations": [
                        {"kind": "requirement_transcription", "title": "业务需求"}
                    ],
                }
            ],
        }
    )
    service.register_batch(
        workspace_id="workspace.cash.batch",
        manifest=manifest,
        bodies=(b"first",),
    )

    with pytest.raises(SourceLibraryConflict, match="Idempotency"):
        service.register_batch(
            workspace_id="workspace.cash.batch",
            manifest=manifest,
            bodies=(b"second",),
        )


def test_multiple_attachments_of_the_same_kind_coexist_and_reupload_versions_one_document(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)

    dictionary = service.register(
        workspace_id="workspace.cash.reference",
        kind="data_dictionary",
        title="字段字典",
        original_name="order_trade_dictionary.xlsx",
        media_type="application/octet-stream",
        body=b"dictionary-v1",
    )
    sample = service.register(
        workspace_id="workspace.cash.reference",
        kind="data_dictionary",
        title="样例数据",
        original_name="cash_sample.xlsx",
        media_type="application/octet-stream",
        body=b"sample-v1",
    )
    dictionary_v2 = service.register(
        workspace_id="workspace.cash.reference",
        kind="data_dictionary",
        title="字段字典（修订）",
        original_name="ORDER_TRADE_DICTIONARY.xlsx",
        media_type="application/octet-stream",
        body=b"dictionary-v2",
    )

    current = service.list_current("workspace.cash.reference")
    assert {item.source_id for item in current} == {
        dictionary.source_id,
        sample.source_id,
    }
    assert dictionary.source_id == dictionary_v2.source_id
    assert sample.source_id != dictionary.source_id
    assert dictionary_v2 in current
    assert dictionary not in current
    assert service.list_versions("workspace.cash.reference") == (
        dictionary_v2,
        sample,
        dictionary,
    )


def test_transcribed_text_projects_exact_bytes_but_attachments_remain_register_only(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    requirements = service.register(
        workspace_id="workspace.adt.reference",
        kind="requirement_transcription",
        title="需求说明",
        original_name="requirements.md",
        media_type="text/markdown",
        body="| O-01 | 各季度 ADT？ | 期间、ADT | 表格 |\n".encode(),
    )
    model = service.register(
        workspace_id="workspace.adt.reference",
        kind="data_model",
        title="数据模型",
        original_name="model.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        body=b"PK\x03\x04synthetic-xlsx",
    )

    assets = {
        item["asset_id"]: item
        for item in service.current_intake_assets("workspace.adt.reference")
    }

    assert assets[requirements.source_id]["processing_mode"] == "TRANSCRIBED"
    assert assets[requirements.source_id]["content_text"].startswith("| O-01")
    assert assets[model.source_id]["processing_mode"] == "REGISTERED_NOT_PARSED"
    assert "content_text" not in assets[model.source_id]


def test_source_registration_fails_closed_on_unsafe_or_empty_input(tmp_path: Path) -> None:
    service = _service(tmp_path)

    with pytest.raises(SourceLibraryError, match="empty"):
        service.register(
            workspace_id="workspace.adt.reference",
            kind="sql",
            title="SQL",
            original_name="adt.sql",
            media_type="text/sql",
            body=b"",
        )
    with pytest.raises(SourceLibraryError, match="UTF-8"):
        service.register(
            workspace_id="workspace.adt.reference",
            kind="metric_transcription",
            title="指标逻辑",
            original_name="metrics.md",
            media_type="text/markdown",
            body=b"\xff\xfe",
        )


def test_xlsx_preview_has_exact_sheet_cell_formula_and_value_anchors(tmp_path: Path) -> None:
    service = _service(tmp_path)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Metric Logic"
    sheet["A1"] = "Metric"
    sheet["B1"] = "Value"
    sheet["A2"] = "ADT"
    sheet["B2"] = "=100/5"
    payload = BytesIO()
    workbook.save(payload)
    version = service.register(
        workspace_id="workspace.adt.reference",
        kind="data_dictionary",
        title="指标与数据字典",
        original_name="dictionary.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        body=payload.getvalue(),
    )

    preview = service.preview(version.source_version_id, "workspace.adt.reference")

    assert preview.status == "PARSED"
    assert preview.sheets[0].sheet_name == "Metric Logic"
    assert preview.sheets[0].used_range == "A1:B2"
    formula = next(item for item in preview.sheets[0].cells if item.cell == "B2")
    assert formula.raw_formula == "=100/5"
    assert formula.display_value is None
    assert len(formula.snippet_checksum) == 64


def test_construction_intake_can_request_parsed_attachment_previews_without_bloating_default_workbench(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Data Model Overview"
    sheet.append(["Table", "Category", "Primary Key", "Purpose"])
    sheet.append(["trading_activity", "Activity", "trade_id", "Trade events"])
    payload = BytesIO()
    workbook.save(payload)
    dictionary = service.register(
        workspace_id="workspace.cash.reference",
        kind="data_dictionary",
        title="Data dictionary",
        original_name="dictionary.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        body=payload.getvalue(),
    )
    sql = service.register(
        workspace_id="workspace.cash.reference",
        kind="sql",
        title="Existing calculations",
        original_name="controls.sql",
        media_type="text/sql",
        body=b"SELECT COUNT(*) FROM trading_activity;\n",
    )

    default_assets = {
        item["asset_id"]: item
        for item in service.current_intake_assets("workspace.cash.reference")
    }
    construction_assets = {
        item["asset_id"]: item
        for item in service.current_intake_assets(
            "workspace.cash.reference", include_parsed_attachments=True
        )
    }

    assert "source_preview" not in default_assets[dictionary.source_id]
    assert "source_preview" not in default_assets[sql.source_id]
    assert construction_assets[dictionary.source_id]["source_preview"]["status"] == "PARSED"
    assert construction_assets[dictionary.source_id]["source_preview"]["sheets"][0]["sheet_name"] == "Data Model Overview"
    assert construction_assets[sql.source_id]["source_preview"]["status"] == "PARSED"
    assert construction_assets[sql.source_id]["source_preview"]["text_lines"][0]["text"].startswith("SELECT")


def test_packaged_reference_sources_install_idempotently_with_exact_physical_identity(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    manifest_path = CASH_SCENARIO / "intake" / "reference-source-pack.json"

    first = service.install_reference_pack(
        workspace_id="workspace.cash.reference",
        component_root=CASH_SCENARIO,
        manifest_path=manifest_path,
    )
    second = service.install_reference_pack(
        workspace_id="workspace.cash.reference",
        component_root=CASH_SCENARIO,
        manifest_path=manifest_path,
    )

    current = service.list_current("workspace.cash.reference")
    by_id = {item.source_id: item for item in current}
    assert first.pack_id == "cash-trading.deloitte-hk.reference.20260820"
    assert first.physical_file_count == 4
    assert first.registered_source_count == 6
    assert second.subject_checksum == first.subject_checksum
    assert len(current) == 6
    assert (
        by_id["asset.requirements"].content_checksum
        == by_id["asset.metric_logic"].content_checksum
    )
    assert len(service.list_versions("workspace.cash.reference")) == 6


def test_installed_adt_assets_are_versioned_idempotently_and_all_can_be_previewed(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    intake = ADTIntakeRegistry(
        tmp_path / "submissions", ADT_SCENARIO
    ).register_reference()
    registration = json.loads(
        (ADT_SCENARIO / "solution-registration.json").read_text(encoding="utf-8")
    )
    assets = tuple(item.model_dump(mode="json") for item in intake.assets)
    resources = tuple(registration["resources"])

    first = service.import_installed_assets(
        workspace_id="workspace.adt.reference",
        component_root=ADT_SCENARIO,
        assets=assets,
        resources=resources,
    )
    second = service.import_installed_assets(
        workspace_id="workspace.adt.reference",
        component_root=ADT_SCENARIO,
        assets=assets,
        resources=resources,
    )

    assert len(first) == 5
    assert [item.source_version_id for item in second] == [
        item.source_version_id for item in first
    ]
    assert len(service.list_current("workspace.adt.reference")) == 5
    assert len(service.list_versions("workspace.adt.reference")) == 5
    previews = [
        service.preview(item.source_version_id, "workspace.adt.reference")
        for item in first
    ]
    assert all(item.status == "PARSED" for item in previews)
    dictionary = next(
        item for item, version in zip(previews, first, strict=True)
        if version.kind == "data_dictionary"
    )
    assert dictionary.text_lines[0].text.startswith("table_name")


def test_installed_asset_import_fails_closed_when_package_inventory_disagrees(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    package = tmp_path / "package"
    package.mkdir()
    body = b"field_name,data_type\ntrade_id,string\n"
    (package / "dictionary.csv").write_bytes(body)
    checksum = hashlib.sha256(body).hexdigest()
    asset = {
        "asset_id": "asset.dictionary",
        "kind": "data_dictionary",
        "locator": "dictionary.csv",
        "media_type": "text/csv",
        "checksum": checksum,
    }
    resource = {
        "locator": "dictionary.csv",
        "media_type": "text/csv",
        "sha256": "0" * 64,
        "size_bytes": len(body),
    }

    with pytest.raises(SourceLibraryError, match="identity mismatch"):
        service.import_installed_assets(
            workspace_id="workspace.test",
            component_root=package,
            assets=(asset,),
            resources=(resource,),
        )
