from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook

from ontology_agent.io import sha256_value
from ontology_agent.studio.agentic_contracts import RunAuthorityContextV1
from ontology_agent.studio.agentic_evidence import ExactEvidenceWorkspace
from ontology_agent.studio.source_library import FileSourceLibraryStore


def _context(version_ids: tuple[str, ...]) -> RunAuthorityContextV1:
    return RunAuthorityContextV1(
        job_id="construction-job." + "1" * 32,
        run_id="construction-run." + "2" * 32,
        attempt_id="construction-attempt." + "3" * 32,
        lease_epoch=1,
        lease_owner="worker-1",
        workspace_id="workspace.evidence",
        solution_id="ontology.evidence",
        source_set_digest=sha256_value(version_ids),
        selected_source_version_ids=version_ids,
        principal_id="service.builder",
        tool_registry_digest="4" * 64,
        tool_policy_digest="5" * 64,
        objective_checksum="6" * 64,
        candidate_revision=0,
        step_sequence=0,
        remaining_model_calls=20,
        remaining_tool_calls=100,
    )


def _xlsx_bytes() -> bytes:
    workbook = Workbook()
    requirements = workbook.active
    requirements.title = "01_Requirements_Process"
    requirements.append(["ID", "Question", "Output"])
    requirements.append(["R-01", "What is the order-to-trade ratio?", "Daily ratio"])
    metrics = workbook.create_sheet("02_Metric_Logic")
    metrics.append(["Metric", "Formula"])
    metrics.append(["Order-to-trade ratio", "orders / trades"])
    payload = BytesIO()
    workbook.save(payload)
    return payload.getvalue()


def _sparse_xlsx_bytes() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sparse"
    sheet["A1"] = "anchor"
    sheet["C3"] = "tail"
    payload = BytesIO()
    workbook.save(payload)
    return payload.getvalue()


def test_spreadsheet_sources_are_searchable_and_exact_ranges_are_citeable(
    tmp_path: Path,
) -> None:
    store = FileSourceLibraryStore(tmp_path / "sources")
    body = _xlsx_bytes()
    first = store.register(
        workspace_id="workspace.evidence",
        source_id="asset.requirements",
        kind="requirement_transcription",
        title="Requirements",
        original_name="input.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        body=body,
    )
    second = store.register(
        workspace_id="workspace.evidence",
        source_id="asset.metric_logic",
        kind="metric_transcription",
        title="Metric logic",
        original_name="input.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        body=body,
    )
    context = _context((first.source_version_id, second.source_version_id))
    evidence = ExactEvidenceWorkspace(
        context=context,
        versions=(first, second),
        store=store,
        logical_roles={
            first.source_version_id: ("asset.requirements",),
            second.source_version_id: ("asset.metric_logic",),
        },
    )

    sources = evidence.list_sources()
    assert {item.evidence_kind for item in sources} == {"SPREADSHEET"}
    assert sources[0].index_receipt.completeness == "COMPLETE"
    assert (
        sources[0].index_receipt.parsed_artifact_checksum
        == sources[1].index_receipt.parsed_artifact_checksum
    )
    hits = evidence.search("order-to-trade")
    assert {item.source_version_id for item in hits} == {
        first.source_version_id,
        second.source_version_id,
    }
    assert evidence.list_sheets(first.source_version_id)[1].name == "02_Metric_Logic"
    read = evidence.read_spreadsheet_range(
        first.source_version_id,
        sheet_name="01_Requirements_Process",
        cell_range="A1:C2",
    )
    assert "R-01" in read.content
    assert read.receipt.canonical_locator == "xlsx:01_Requirements_Process!A1:C2"
    assert read.receipt.logical_role_ids == ("asset.requirements",)


def test_sparse_spreadsheet_range_assigns_exact_coordinates_to_empty_cells(
    tmp_path: Path,
) -> None:
    store = FileSourceLibraryStore(tmp_path / "sources")
    version = store.register(
        workspace_id="workspace.evidence",
        source_id="asset.sparse",
        kind="data_dictionary",
        title="Sparse dictionary",
        original_name="sparse.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        body=_sparse_xlsx_bytes(),
    )
    evidence = ExactEvidenceWorkspace(
        context=_context((version.source_version_id,)),
        versions=(version,),
        store=store,
    )

    read = evidence.read_spreadsheet_range(
        version.source_version_id,
        sheet_name="Sparse",
        cell_range="A1:C3",
    )
    payload = json.loads(read.content)

    assert payload["rows"][0][0] == {
        "cell": "A1",
        "data_type": "s",
        "value": "anchor",
    }
    assert payload["rows"][0][1]["cell"] == "B1"
    assert payload["rows"][0][1]["value"] is None
    assert payload["rows"][2][2]["cell"] == "C3"
    assert payload["rows"][2][2]["value"] == "tail"


def test_sql_is_structurally_inspected_and_statement_read_is_citeable(
    tmp_path: Path,
) -> None:
    store = FileSourceLibraryStore(tmp_path / "sources")
    version = store.register(
        workspace_id="workspace.evidence",
        source_id="asset.sql.controls",
        kind="sql",
        title="Controls",
        original_name="controls.sql",
        media_type="text/sql",
        body=b"SELECT COUNT(*) FROM order_activity;\nSELECT COUNT(*) FROM trading_activity;\n",
    )
    context = _context((version.source_version_id,))
    evidence = ExactEvidenceWorkspace(context=context, versions=(version,), store=store)

    statements = evidence.inspect_sql(version.source_version_id)
    assert [item.statement_type for item in statements] == ["SELECT", "SELECT"]
    read = evidence.read_sql_statement(version.source_version_id, ordinal=2)
    assert "trading_activity" in read.content
    assert read.receipt.canonical_locator == "sql:statement:2"


def test_archived_only_source_is_explicit_not_a_workspace_failure(tmp_path: Path) -> None:
    store = FileSourceLibraryStore(tmp_path / "sources")
    version = store.register(
        workspace_id="workspace.evidence",
        source_id="asset.email",
        kind="other",
        title="Email screenshot",
        original_name="email.jpeg",
        media_type="image/jpeg",
        body=b"not-real-image-but-exact-archive-bytes",
    )
    evidence = ExactEvidenceWorkspace(
        context=_context((version.source_version_id,)),
        versions=(version,),
        store=store,
    )

    source = evidence.list_sources()[0]
    assert source.evidence_kind == "UNSUPPORTED"
    assert source.index_receipt.completeness == "UNSUPPORTED"
    assert source.index_receipt.indexed_units == 0
