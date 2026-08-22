from __future__ import annotations

import hashlib
from io import BytesIO

import pytest
from openpyxl import Workbook

from ontology_agent.studio.evidence import (
    EvidenceNormalizationError,
    normalize_evidence,
)
from ontology_agent.studio.source_library import (
    FileSourceLibraryStore,
    StudioSourceLibraryService,
)


def test_exact_text_and_xlsx_become_bounded_traceable_fragments(tmp_path) -> None:
    service = StudioSourceLibraryService(FileSourceLibraryStore(tmp_path / "sources"))
    service.register(
        workspace_id="workspace.generic",
        kind="requirement_transcription",
        title="Business requirements",
        original_name="requirements.md",
        media_type="text/markdown",
        body=b"Process: receive request\nObject: customer request\nOutput: daily summary\n",
    )
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Fields"
    sheet.append(["field", "type", "description"])
    sheet.append(["request_id", "string", "request identifier"])
    payload = BytesIO()
    workbook.save(payload)
    service.register(
        workspace_id="workspace.generic",
        kind="data_dictionary",
        title="Data dictionary",
        original_name="dictionary.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        body=payload.getvalue(),
    )
    intake = {
        "assets": service.current_intake_assets(
            "workspace.generic", include_parsed_attachments=True
        )
    }

    bundle = normalize_evidence(intake, workspace_id="workspace.generic")

    assert {item.content_kind for item in bundle.fragments} == {
        "TEXT_RANGE",
        "XLSX_ROW",
    }
    assert all(item.source_checksum == item.anchor.source_checksum for item in bundle.fragments)
    assert all(item.fragment_id.startswith("evidence.") for item in bundle.fragments)
    assert bundle.unsupported_sources == ()
    assert normalize_evidence(intake, workspace_id="workspace.generic") == bundle


def test_tampered_exact_text_is_rejected() -> None:
    intake = {
        "assets": (
            {
                "asset_id": "source.requirements",
                "kind": "requirement_transcription",
                "locator": "source-library:source-version.invalid",
                "checksum": "0" * 64,
                "content_text": "This text does not match the registered checksum.",
            },
        )
    }

    with pytest.raises(EvidenceNormalizationError, match="checksum mismatch"):
        normalize_evidence(intake, workspace_id="workspace.generic")


def test_registered_but_unparsed_media_stays_explicitly_unsupported() -> None:
    intake = {
        "assets": (
            {
                "asset_id": "source.image",
                "kind": "other",
                "locator": "source-library:source-version.image",
                "checksum": "a" * 64,
                "processing_mode": "REGISTERED_NOT_PARSED",
            },
        )
    }

    bundle = normalize_evidence(intake, workspace_id="workspace.generic")

    assert bundle.fragments == ()
    assert bundle.unsupported_sources[0].source_id == "source.image"


def _text_asset(*, source_id: str, kind: str, content: str) -> dict[str, str]:
    return {
        "asset_id": source_id,
        "kind": kind,
        "checksum": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "content_text": content,
    }


def test_global_fragment_limit_samples_across_all_selected_sources() -> None:
    intake = {
        "assets": (
            _text_asset(
                source_id="source.dictionary",
                kind="data_dictionary",
                content="\n".join(f"field_{index}" for index in range(20)),
            ),
            _text_asset(
                source_id="source.requirements",
                kind="requirement_transcription",
                content="Question: calculate daily order-to-trade ratio",
            ),
            _text_asset(
                source_id="source.sql",
                kind="sql",
                content="SELECT COUNT(*) FROM order_activity;",
            ),
        )
    }

    bundle = normalize_evidence(
        intake,
        workspace_id="workspace.generic",
        max_fragments=3,
        lines_per_fragment=1,
    )

    assert {fragment.source_id for fragment in bundle.fragments} == {
        "source.dictionary",
        "source.requirements",
        "source.sql",
    }


def test_source_set_digest_includes_sources_after_fragment_budget_is_exhausted() -> None:
    first = _text_asset(
        source_id="source.dictionary",
        kind="data_dictionary",
        content="field_name",
    )
    late_v1 = _text_asset(
        source_id="source.sql",
        kind="sql",
        content="SELECT 1;",
    )
    late_v2 = _text_asset(
        source_id="source.sql",
        kind="sql",
        content="SELECT 2;",
    )

    v1 = normalize_evidence(
        {"assets": (first, late_v1)},
        workspace_id="workspace.generic",
        max_fragments=1,
    )
    v2 = normalize_evidence(
        {"assets": (first, late_v2)},
        workspace_id="workspace.generic",
        max_fragments=1,
    )

    assert v1.source_set_digest != v2.source_set_digest


def test_xlsx_projection_prioritizes_sheet_matching_logical_role(tmp_path) -> None:
    service = StudioSourceLibraryService(FileSourceLibraryStore(tmp_path / "sources"))
    workbook = Workbook()
    guidance = workbook.active
    guidance.title = "Guidance"
    for index in range(20):
        guidance.append([f"instruction {index}"])
    metric = workbook.create_sheet("02_Metric_Logic")
    metric.append(["metric", "formula"])
    metric.append(["Order-to-trade ratio", "orders / trades"])
    payload = BytesIO()
    workbook.save(payload)
    service.register(
        workspace_id="workspace.generic",
        kind="metric_transcription",
        title="Metric logic",
        original_name="input.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        body=payload.getvalue(),
    )
    intake = {
        "assets": service.current_intake_assets(
            "workspace.generic", include_parsed_attachments=True
        )
    }

    bundle = normalize_evidence(
        intake,
        workspace_id="workspace.generic",
        max_fragments=1,
    )

    assert bundle.fragments[0].anchor.sheet_name == "02_Metric_Logic"


def test_xlsx_dictionary_samples_across_physical_table_sheets(tmp_path) -> None:
    service = StudioSourceLibraryService(FileSourceLibraryStore(tmp_path / "sources"))
    workbook = Workbook()
    first = workbook.active
    first.title = "order_activity"
    first.append(["field", "type"])
    first.append(["activity_id", "string"])
    first.append(["trading_date", "date"])
    second = workbook.create_sheet("trading_activity")
    second.append(["field", "type"])
    second.append(["trade_id", "string"])
    second.append(["transaction_timestamp", "datetime"])
    payload = BytesIO()
    workbook.save(payload)
    service.register(
        workspace_id="workspace.generic",
        kind="data_dictionary",
        title="Data dictionary",
        original_name="dictionary.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        body=payload.getvalue(),
    )
    intake = {
        "assets": service.current_intake_assets(
            "workspace.generic", include_parsed_attachments=True
        )
    }

    bundle = normalize_evidence(
        intake,
        workspace_id="workspace.generic",
        max_fragments=2,
    )

    assert [item.anchor.sheet_name for item in bundle.fragments] == [
        "order_activity",
        "trading_activity",
    ]
