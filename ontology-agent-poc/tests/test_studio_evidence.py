from __future__ import annotations

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
