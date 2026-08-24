from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from io import BytesIO
from typing import Any, Callable, Iterable, Literal

import duckdb
from openpyxl import load_workbook
from openpyxl.utils.cell import get_column_letter, range_boundaries

from ..io import sha256_value
from .agentic_contracts import (
    EvidenceIndexReceiptV1,
    EvidenceReceiptV2,
    RunAuthorityContextV1,
)
from .source_library import SourceLibraryStore, StudioSourceVersionV1


class EvidenceWorkspaceError(RuntimeError):
    """Exact evidence could not be read inside the frozen run scope."""


EvidenceKind = Literal["TEXT", "SPREADSHEET", "SQL", "UNSUPPORTED"]
_MAX_XLSX_INDEX_CELLS = 500_000
_MAX_XLSX_READ_CELLS = 5_000


@dataclass(frozen=True)
class EvidenceSearchHit:
    source_version_id: str
    logical_role_ids: tuple[str, ...]
    canonical_locator: str
    snippet: str
    snippet_checksum: str


@dataclass(frozen=True)
class EvidenceReadResult:
    content: str
    receipt: EvidenceReceiptV2


@dataclass(frozen=True)
class SpreadsheetSheet:
    name: str
    used_range: str
    indexed_cells: int
    total_cells: int


@dataclass(frozen=True)
class SqlStatement:
    ordinal: int
    statement_type: str
    query: str
    query_checksum: str


@dataclass(frozen=True)
class EvidenceSource:
    source_version_id: str
    source_id: str
    title: str
    original_name: str
    media_type: str
    kind: str
    evidence_kind: EvidenceKind
    logical_role_ids: tuple[str, ...]
    index_receipt: EvidenceIndexReceiptV1


@dataclass(frozen=True)
class _SearchUnit:
    canonical_locator: str
    text: str


@dataclass(frozen=True)
class _ParsedProjection:
    body: bytes
    evidence_kind: EvidenceKind
    parser_id: str
    parser_version: str
    parsed_artifact_checksum: str
    completeness: Literal["COMPLETE", "PARTIAL", "UNSUPPORTED"]
    total_units: int
    indexed_units: int
    unit_kind: Literal["LINES", "CELLS", "STATEMENTS", "BYTES"]
    warnings: tuple[str, ...]
    lines: tuple[str, ...] = ()
    search_units: tuple[_SearchUnit, ...] = ()
    sheets: tuple[SpreadsheetSheet, ...] = ()
    sql_statements: tuple[SqlStatement, ...] = ()


@dataclass(frozen=True)
class _SourceIndex:
    version: StudioSourceVersionV1
    projection: _ParsedProjection
    logical_role_ids: tuple[str, ...]
    index_receipt: EvidenceIndexReceiptV1


def _json_value(value: object) -> object:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    return value


def _xlsx_used_range(max_row: int, max_column: int) -> str:
    return f"A1:{get_column_letter(max(1, max_column))}{max(1, max_row)}"


def _parse_text(body: bytes) -> _ParsedProjection:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EvidenceWorkspaceError("Text evidence must be valid UTF-8") from exc
    lines = tuple(text.splitlines())
    units = tuple(
        _SearchUnit(canonical_locator=f"lines:{number}-{number}", text=line)
        for number, line in enumerate(lines, start=1)
    )
    artifact = {
        "parser_id": "utf8-lines",
        "parser_version": "2.0.0",
        "source_bytes_checksum": hashlib.sha256(body).hexdigest(),
        "line_count": len(lines),
        "line_checksums": [hashlib.sha256(line.encode("utf-8")).hexdigest() for line in lines],
        "completeness": "COMPLETE",
    }
    return _ParsedProjection(
        body=body,
        evidence_kind="TEXT",
        parser_id="utf8-lines",
        parser_version="2.0.0",
        parsed_artifact_checksum=sha256_value(artifact),
        completeness="COMPLETE",
        total_units=len(lines),
        indexed_units=len(lines),
        unit_kind="LINES",
        warnings=(),
        lines=lines,
        search_units=units,
    )


def _parse_xlsx(body: bytes) -> _ParsedProjection:
    try:
        workbook = load_workbook(BytesIO(body), read_only=True, data_only=False)
    except Exception as exc:
        raise EvidenceWorkspaceError("XLSX evidence could not be parsed") from exc
    try:
        total_cells = sum(
            max(1, sheet.max_row) * max(1, sheet.max_column)
            for sheet in workbook.worksheets
        )
        remaining = _MAX_XLSX_INDEX_CELLS
        units: list[_SearchUnit] = []
        sheets: list[SpreadsheetSheet] = []
        indexed_cells = 0
        for sheet in workbook.worksheets:
            sheet_total = max(1, sheet.max_row) * max(1, sheet.max_column)
            sheet_budget = min(remaining, sheet_total)
            inspected = 0
            if sheet_budget:
                for row in sheet.iter_rows(
                    min_row=1,
                    max_row=max(1, sheet.max_row),
                    min_col=1,
                    max_col=max(1, sheet.max_column),
                ):
                    for cell in row:
                        if inspected >= sheet_budget:
                            break
                        inspected += 1
                        if cell.value is None:
                            continue
                        display = json.dumps(
                            _json_value(cell.value),
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                        units.append(
                            _SearchUnit(
                                canonical_locator=f"xlsx:{sheet.title}!{cell.coordinate}",
                                text=display,
                            )
                        )
                    if inspected >= sheet_budget:
                        break
            indexed_cells += inspected
            remaining -= inspected
            sheets.append(
                SpreadsheetSheet(
                    name=sheet.title,
                    used_range=_xlsx_used_range(sheet.max_row, sheet.max_column),
                    indexed_cells=inspected,
                    total_cells=sheet_total,
                )
            )
        completeness: Literal["COMPLETE", "PARTIAL"] = (
            "COMPLETE" if indexed_cells == total_cells else "PARTIAL"
        )
        warnings = (
            ()
            if completeness == "COMPLETE"
            else (
                f"Search index is bounded to {_MAX_XLSX_INDEX_CELLS} cells; use spreadsheet.read_range for exact ranges.",
            )
        )
        artifact = {
            "parser_id": "openpyxl-cell-index",
            "parser_version": "2.0.0",
            "source_bytes_checksum": hashlib.sha256(body).hexdigest(),
            "sheets": [
                {
                    "name": item.name,
                    "used_range": item.used_range,
                    "indexed_cells": item.indexed_cells,
                    "total_cells": item.total_cells,
                }
                for item in sheets
            ],
            "search_units": [
                {
                    "locator": item.canonical_locator,
                    "checksum": hashlib.sha256(item.text.encode("utf-8")).hexdigest(),
                }
                for item in units
            ],
            "completeness": completeness,
        }
        return _ParsedProjection(
            body=body,
            evidence_kind="SPREADSHEET",
            parser_id="openpyxl-cell-index",
            parser_version="2.0.0",
            parsed_artifact_checksum=sha256_value(artifact),
            completeness=completeness,
            total_units=total_cells,
            indexed_units=indexed_cells,
            unit_kind="CELLS",
            warnings=warnings,
            search_units=tuple(units),
            sheets=tuple(sheets),
        )
    finally:
        workbook.close()


def _parse_sql(body: bytes) -> _ParsedProjection:
    text_projection = _parse_text(body)
    sql = "\n".join(text_projection.lines)
    try:
        connection = duckdb.connect(":memory:")
        try:
            extracted = connection.extract_statements(sql)
        finally:
            connection.close()
    except Exception as exc:
        raise EvidenceWorkspaceError("SQL evidence is not parseable by the enabled SQL parser") from exc
    statements = tuple(
        SqlStatement(
            ordinal=ordinal,
            statement_type=str(statement.type).removeprefix("StatementType."),
            query=statement.query.strip(),
            query_checksum=hashlib.sha256(statement.query.strip().encode("utf-8")).hexdigest(),
        )
        for ordinal, statement in enumerate(extracted, start=1)
    )
    artifact = {
        "parser_id": "duckdb-sql-statements",
        "parser_version": "2.0.0",
        "source_bytes_checksum": hashlib.sha256(body).hexdigest(),
        "line_count": len(text_projection.lines),
        "statements": [
            {
                "ordinal": item.ordinal,
                "statement_type": item.statement_type,
                "query_checksum": item.query_checksum,
            }
            for item in statements
        ],
        "completeness": "COMPLETE",
    }
    return _ParsedProjection(
        body=body,
        evidence_kind="SQL",
        parser_id="duckdb-sql-statements",
        parser_version="2.0.0",
        parsed_artifact_checksum=sha256_value(artifact),
        completeness="COMPLETE",
        total_units=len(statements),
        indexed_units=len(statements),
        unit_kind="STATEMENTS",
        warnings=(),
        lines=text_projection.lines,
        search_units=text_projection.search_units,
        sql_statements=statements,
    )


def _unsupported(body: bytes, media_type: str) -> _ParsedProjection:
    artifact = {
        "parser_id": "archive-only",
        "parser_version": "1.0.0",
        "source_bytes_checksum": hashlib.sha256(body).hexdigest(),
        "media_type": media_type,
        "completeness": "UNSUPPORTED",
    }
    return _ParsedProjection(
        body=body,
        evidence_kind="UNSUPPORTED",
        parser_id="archive-only",
        parser_version="1.0.0",
        parsed_artifact_checksum=sha256_value(artifact),
        completeness="UNSUPPORTED",
        total_units=len(body),
        indexed_units=0,
        unit_kind="BYTES",
        warnings=("No enabled content parser; bytes remain registered as exact archive evidence.",),
    )


def _select_parser(version: StudioSourceVersionV1, body: bytes) -> _ParsedProjection:
    name = version.original_name.casefold()
    media = version.media_type.casefold()
    if name.endswith(".xlsx") or "spreadsheetml" in media:
        return _parse_xlsx(body)
    if version.kind == "sql" or name.endswith(".sql") or media in {"text/sql", "application/sql"}:
        return _parse_sql(body)
    if version.processing_mode in {"TRANSCRIBED", "STRUCTURED_TRANSCRIPTION"} or media.startswith("text/") or name.endswith((".md", ".txt", ".csv", ".json", ".yaml", ".yml")):
        return _parse_text(body)
    return _unsupported(body, version.media_type)


class ExactEvidenceWorkspace:
    """Run-scoped exact evidence. Search discovers; typed reads mint authority."""

    def __init__(
        self,
        *,
        context: RunAuthorityContextV1,
        versions: Iterable[StudioSourceVersionV1],
        store: SourceLibraryStore,
        logical_roles: dict[str, tuple[str, ...]] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.context = context
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._indices: dict[str, _SourceIndex] = {}
        roles = logical_roles or {}
        parsed_by_checksum: dict[str, _ParsedProjection] = {}
        for version in versions:
            if version.workspace_id != context.workspace_id:
                raise EvidenceWorkspaceError("Evidence version crossed workspace scope")
            if version.source_version_id not in context.selected_source_version_ids:
                raise EvidenceWorkspaceError("Evidence version is outside the source set")
            body = store.read_exact(version)
            actual_checksum = hashlib.sha256(body).hexdigest()
            if actual_checksum != version.content_checksum:
                raise EvidenceWorkspaceError("Exact source bytes do not match their registered checksum")
            projection = parsed_by_checksum.get(actual_checksum)
            if projection is None:
                projection = _select_parser(version, body)
                parsed_by_checksum[actual_checksum] = projection
            parser_options = {
                "max_xlsx_index_cells": _MAX_XLSX_INDEX_CELLS,
                "max_xlsx_read_cells": _MAX_XLSX_READ_CELLS,
            }
            receipt_raw: dict[str, object] = {
                "contract": "studio-evidence-index-receipt/v1",
                "source_version_id": version.source_version_id,
                "source_bytes_checksum": version.content_checksum,
                "media_type": version.media_type,
                "parser_id": projection.parser_id,
                "parser_version": projection.parser_version,
                "parser_options_digest": sha256_value(parser_options),
                "parsed_artifact_checksum": projection.parsed_artifact_checksum,
                "completeness": projection.completeness,
                "total_units": projection.total_units,
                "indexed_units": projection.indexed_units,
                "unit_kind": projection.unit_kind,
                "warnings": list(projection.warnings),
            }
            receipt_raw["receipt_checksum"] = sha256_value(receipt_raw)
            self._indices[version.source_version_id] = _SourceIndex(
                version=version,
                projection=projection,
                logical_role_ids=roles.get(version.source_version_id, (version.source_id,)),
                index_receipt=EvidenceIndexReceiptV1.model_validate(receipt_raw),
            )
        if set(self._indices) != set(context.selected_source_version_ids):
            missing = sorted(set(context.selected_source_version_ids) - set(self._indices))
            raise EvidenceWorkspaceError("Frozen source set is incomplete: " + ", ".join(missing))

    def list_sources(self) -> tuple[EvidenceSource, ...]:
        return tuple(
            EvidenceSource(
                source_version_id=index.version.source_version_id,
                source_id=index.version.source_id,
                title=index.version.title,
                original_name=index.version.original_name,
                media_type=index.version.media_type,
                kind=index.version.kind,
                evidence_kind=index.projection.evidence_kind,
                logical_role_ids=index.logical_role_ids,
                index_receipt=index.index_receipt,
            )
            for index in (self._indices[key] for key in sorted(self._indices))
        )

    def search(
        self,
        query: str,
        *,
        source_version_ids: tuple[str, ...] = (),
        max_hits: int = 20,
    ) -> tuple[EvidenceSearchHit, ...]:
        needle = query.casefold().strip()
        if not needle:
            raise EvidenceWorkspaceError("Evidence search query is empty")
        selected = source_version_ids or tuple(sorted(self._indices))
        hits: list[EvidenceSearchHit] = []
        for source_version_id in selected:
            index = self._index(source_version_id)
            for unit in index.projection.search_units:
                if needle not in unit.text.casefold():
                    continue
                snippet = unit.text[:1000]
                hits.append(
                    EvidenceSearchHit(
                        source_version_id=source_version_id,
                        logical_role_ids=index.logical_role_ids,
                        canonical_locator=unit.canonical_locator,
                        snippet=snippet,
                        snippet_checksum=hashlib.sha256(snippet.encode("utf-8")).hexdigest(),
                    )
                )
                if len(hits) >= max_hits:
                    return tuple(hits)
        return tuple(hits)

    def read_lines(self, source_version_id: str, *, start_line: int, end_line: int) -> EvidenceReadResult:
        index = self._index(source_version_id)
        if index.projection.evidence_kind not in {"TEXT", "SQL"}:
            raise EvidenceWorkspaceError("This source does not support line reads")
        if start_line < 1 or end_line < start_line or end_line > len(index.projection.lines):
            raise EvidenceWorkspaceError("Evidence line range is outside the exact source")
        content = "\n".join(index.projection.lines[start_line - 1 : end_line])
        return self._read_result(index, f"lines:{start_line}-{end_line}", content)

    def list_sheets(self, source_version_id: str) -> tuple[SpreadsheetSheet, ...]:
        index = self._index(source_version_id)
        if index.projection.evidence_kind != "SPREADSHEET":
            raise EvidenceWorkspaceError("This source is not a spreadsheet")
        return index.projection.sheets

    def read_spreadsheet_range(
        self,
        source_version_id: str,
        *,
        sheet_name: str,
        cell_range: str,
    ) -> EvidenceReadResult:
        index = self._index(source_version_id)
        if index.projection.evidence_kind != "SPREADSHEET":
            raise EvidenceWorkspaceError("This source is not a spreadsheet")
        try:
            min_col, min_row, max_col, max_row = range_boundaries(cell_range.upper())
        except (TypeError, ValueError) as exc:
            raise EvidenceWorkspaceError("Spreadsheet range must be an A1 range") from exc
        cell_count = (max_col - min_col + 1) * (max_row - min_row + 1)
        if cell_count > _MAX_XLSX_READ_CELLS:
            raise EvidenceWorkspaceError(
                f"Spreadsheet read exceeds the {_MAX_XLSX_READ_CELLS}-cell exact-read limit"
            )
        workbook = load_workbook(BytesIO(index.projection.body), read_only=True, data_only=False)
        try:
            if sheet_name not in workbook.sheetnames:
                raise EvidenceWorkspaceError("Spreadsheet sheet does not exist")
            sheet = workbook[sheet_name]
            rows: list[list[dict[str, object]]] = []
            for row_number, row in enumerate(
                sheet.iter_rows(
                min_row=min_row,
                max_row=max_row,
                min_col=min_col,
                max_col=max_col,
                ),
                start=min_row,
            ):
                rows.append(
                    [
                        {
                            # Read-only worksheets represent sparse cells as
                            # EmptyCell, which deliberately has no coordinate.
                            # The requested A1 range already gives us the exact
                            # deterministic coordinate without inspecting value.
                            "cell": f"{get_column_letter(column_number)}{row_number}",
                            "value": _json_value(cell.value),
                            "data_type": cell.data_type,
                        }
                        for column_number, cell in enumerate(row, start=min_col)
                    ]
                )
        finally:
            workbook.close()
        content = json.dumps(
            {"sheet": sheet_name, "range": cell_range.upper(), "rows": rows},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return self._read_result(index, f"xlsx:{sheet_name}!{cell_range.upper()}", content)

    def inspect_sql(self, source_version_id: str) -> tuple[SqlStatement, ...]:
        index = self._index(source_version_id)
        if index.projection.evidence_kind != "SQL":
            raise EvidenceWorkspaceError("This source is not SQL")
        return index.projection.sql_statements

    def read_sql_statement(self, source_version_id: str, *, ordinal: int) -> EvidenceReadResult:
        index = self._index(source_version_id)
        if index.projection.evidence_kind != "SQL":
            raise EvidenceWorkspaceError("This source is not SQL")
        statement = next(
            (item for item in index.projection.sql_statements if item.ordinal == ordinal),
            None,
        )
        if statement is None:
            raise EvidenceWorkspaceError("SQL statement ordinal does not exist")
        return self._read_result(index, f"sql:statement:{ordinal}", statement.query)

    def _read_result(self, index: _SourceIndex, locator: str, content: str) -> EvidenceReadResult:
        unsigned: dict[str, object] = {
            "contract": "studio-evidence-receipt/v2",
            "receipt_id": "evidence-receipt." + uuid.uuid4().hex,
            "run_id": self.context.run_id,
            "workspace_id": self.context.workspace_id,
            "solution_id": self.context.solution_id,
            "source_set_digest": self.context.source_set_digest,
            "source_version_id": index.version.source_version_id,
            "source_bytes_checksum": index.version.content_checksum,
            "parser_id": index.projection.parser_id,
            "parser_version": index.projection.parser_version,
            "parsed_artifact_checksum": index.projection.parsed_artifact_checksum,
            "canonical_locator": locator,
            "returned_content_checksum": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "logical_role_ids": list(index.logical_role_ids),
            "authority_context_digest": sha256_value(self.context),
            "issued_at": self.clock().isoformat().replace("+00:00", "Z"),
        }
        unsigned["receipt_checksum"] = sha256_value(unsigned)
        return EvidenceReadResult(
            content=content,
            receipt=EvidenceReceiptV2.model_validate(unsigned),
        )

    def _index(self, source_version_id: str) -> _SourceIndex:
        if source_version_id not in self.context.selected_source_version_ids:
            raise EvidenceWorkspaceError("Evidence source is outside run authority")
        try:
            return self._indices[source_version_id]
        except KeyError as exc:
            raise EvidenceWorkspaceError("Evidence source is unavailable") from exc
