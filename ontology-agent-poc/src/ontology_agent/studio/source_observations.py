from __future__ import annotations

import re
from typing import Any, Literal

from openpyxl.utils import column_index_from_string, get_column_letter
from pydantic import Field

from ..io import sha256_value
from ..models import StrictModel
from .source_projection import SourceProjectionAnchorV1


class SourceObservationError(RuntimeError):
    """An attachment preview could not be converted without losing identity."""


class SourceObservationV1(StrictModel):
    contract: Literal["source-observation/v1"] = "source-observation/v1"
    candidate_type: Literal["OBJECT", "PROPERTY", "RULE", "MAPPING"]
    source_key: str = Field(min_length=1, max_length=500)
    label: str = Field(min_length=1, max_length=500)
    definition: str = Field(min_length=1, max_length=4000)
    support_class: Literal["DIRECT_EXACT", "DERIVED_DETERMINISTIC"]
    proposal: dict[str, Any]
    source_anchors: tuple[SourceProjectionAnchorV1, ...] = Field(
        min_length=1, max_length=20
    )
    limitations: tuple[str, ...] = ()


def _record(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return dict(value)
    return {}


def _assets(intake: Any) -> tuple[dict[str, Any], ...]:
    payload = _record(intake)
    values = payload.get("assets") or payload.get("source_files") or ()
    return tuple(_record(item) for item in values)


def _preview_identity(asset: dict[str, Any]) -> tuple[str, str, str, dict[str, Any]]:
    source_id = str(asset.get("asset_id") or asset.get("file_id") or "")
    source_checksum = str(asset.get("checksum") or asset.get("sha256") or "")
    source_version_id = str(asset.get("source_version_id") or "")
    preview = _record(asset.get("source_preview"))
    if (
        not source_id
        or not re.fullmatch(r"[0-9a-f]{64}", source_checksum)
        or not source_version_id
        or preview.get("contract") != "studio-source-preview/v1"
        or preview.get("status") != "PARSED"
        or preview.get("source_version_id") != source_version_id
        or preview.get("content_checksum") != source_checksum
    ):
        raise SourceObservationError("Attachment preview identity is invalid")
    return source_id, source_checksum, source_version_id, preview


def _sheet_rows(
    *,
    source_version_id: str,
    source_checksum: str,
    sheet: dict[str, Any],
) -> dict[int, dict[str, tuple[Any, str]]]:
    sheet_name = str(sheet.get("sheet_name") or "")
    if not sheet_name:
        raise SourceObservationError("Attachment preview sheet identity is invalid")
    rows: dict[int, dict[str, tuple[Any, str]]] = {}
    for raw_cell in sheet.get("cells", ()):
        cell = _record(raw_cell)
        coordinate = str(cell.get("cell") or "")
        match = re.fullmatch(r"([A-Z]+)([1-9][0-9]*)", coordinate)
        if match is None:
            raise SourceObservationError("Attachment preview cell identity is invalid")
        expected = sha256_value(
            {
                "source_version_id": source_version_id,
                "content_checksum": source_checksum,
                "sheet": sheet_name,
                "cell": coordinate,
                "raw_formula": cell.get("raw_formula"),
                "display_value": cell.get("display_value"),
            }
        )
        if cell.get("snippet_checksum") != expected:
            raise SourceObservationError("Attachment preview cell checksum mismatch")
        column, row_number = match.groups()
        rows.setdefault(int(row_number), {})[column] = (
            cell.get("display_value"),
            expected,
        )
    return rows


def _cell_text(row: dict[str, tuple[Any, str]], column: str) -> str:
    value = row.get(column, (None, ""))[0]
    return "" if value is None else str(value).strip()


def _normalized(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _xlsx_anchor(
    *,
    source_id: str,
    source_checksum: str,
    sheet_name: str,
    rows: dict[int, dict[str, tuple[Any, str]]],
    start_row: int,
    end_row: int,
    start_column: str,
    end_column: str,
) -> SourceProjectionAnchorV1:
    start_index = column_index_from_string(start_column)
    end_index = column_index_from_string(end_column)
    snippets: list[str] = []
    for row_number in range(start_row, end_row + 1):
        for column, (_, checksum) in sorted(
            rows.get(row_number, {}).items(),
            key=lambda item: column_index_from_string(item[0]),
        ):
            column_index = column_index_from_string(column)
            if start_index <= column_index <= end_index:
                snippets.append(checksum)
    if not snippets:
        raise SourceObservationError("Attachment evidence range is empty")
    cell_range = f"{start_column}{start_row}:{end_column}{end_row}"
    return SourceProjectionAnchorV1(
        source_id=source_id,
        source_checksum=source_checksum,
        locator_kind="XLSX_ROW" if start_row == end_row else "XLSX_RANGE",
        locator=f"sheet={sheet_name};range={cell_range}",
        line_number=start_row,
        sheet_name=sheet_name,
        cell_range=cell_range,
        snippet_checksum=sha256_value(
            {
                "source_id": source_id,
                "source_checksum": source_checksum,
                "sheet_name": sheet_name,
                "cell_range": cell_range,
                "cell_snippet_checksums": snippets,
            }
        ),
    )


def _text_anchor(
    *,
    source_id: str,
    source_checksum: str,
    source_version_id: str,
    lines: tuple[dict[str, Any], ...],
) -> SourceProjectionAnchorV1:
    if not lines:
        raise SourceObservationError("Text attachment preview is empty")
    snippets: list[str] = []
    for line in lines:
        line_number = int(line.get("line_number") or 0)
        text = str(line.get("text") or "")
        expected = sha256_value(
            {
                "source_version_id": source_version_id,
                "content_checksum": source_checksum,
                "line_number": line_number,
                "text": text,
            }
        )
        if line.get("snippet_checksum") != expected:
            raise SourceObservationError("Text attachment line checksum mismatch")
        snippets.append(expected)
    start = int(lines[0]["line_number"])
    end = int(lines[-1]["line_number"])
    return SourceProjectionAnchorV1(
        source_id=source_id,
        source_checksum=source_checksum,
        locator_kind="TEXT_RANGE",
        locator=f"lines={start}-{end}",
        line_number=start,
        snippet_checksum=sha256_value(
            {
                "source_id": source_id,
                "source_checksum": source_checksum,
                "line_range": [start, end],
                "line_snippet_checksums": snippets,
            }
        ),
    )


def _used_range_end_row(value: str) -> int:
    match = re.search(r":?[A-Z]+([1-9][0-9]*)$", value)
    return int(match.group(1)) if match else 1


def _workbook_observations(asset: dict[str, Any]) -> tuple[SourceObservationV1, ...]:
    source_id, source_checksum, source_version_id, preview = _preview_identity(asset)
    sheets = tuple(_record(item) for item in preview.get("sheets", ()))
    sheet_rows = {
        str(sheet.get("sheet_name")): _sheet_rows(
            source_version_id=source_version_id,
            source_checksum=source_checksum,
            sheet=sheet,
        )
        for sheet in sheets
    }
    observations: list[SourceObservationV1] = []
    dictionary_sheets: set[str] = set()
    declared_field_counts: dict[str, int] = {}
    overview = next(
        (
            sheet
            for sheet in sheets
            if _normalized(sheet.get("sheet_name")) == "data model overview"
        ),
        None,
    )
    if overview is not None:
        name = str(overview["sheet_name"])
        rows = sheet_rows[name]
        header_number = next(
            (
                row_number
                for row_number, row in sorted(rows.items())
                if _normalized(_cell_text(row, "A")) == "table"
                and _normalized(_cell_text(row, "B")) == "category"
            ),
            None,
        )
        if header_number is None:
            raise SourceObservationError("Data model overview header is missing")
        for row_number, row in sorted(rows.items()):
            if row_number <= header_number:
                continue
            table_name = _cell_text(row, "A")
            category = _cell_text(row, "B")
            if not table_name or not category:
                continue
            declared_count_text = _cell_text(row, "F")
            declared_count_match = re.search(r"[0-9]+", declared_count_text)
            if declared_count_match is not None:
                declared_field_counts[table_name] = int(declared_count_match.group())
            observations.append(
                SourceObservationV1(
                    candidate_type="OBJECT",
                    source_key=f"{source_id}:table:{table_name}",
                    label=table_name,
                    definition=_cell_text(row, "D") or f"Source table {table_name}",
                    support_class="DIRECT_EXACT",
                    proposal={
                        "contract": "source-table-observation/v1",
                        "source_version_id": source_version_id,
                        "table_name": table_name,
                        "category": category,
                        "primary_key": _cell_text(row, "C"),
                        "purpose": _cell_text(row, "D"),
                        "key_relationships": _cell_text(row, "E"),
                        "declared_field_count": declared_count_text,
                    },
                    source_anchors=(
                        _xlsx_anchor(
                            source_id=source_id,
                            source_checksum=source_checksum,
                            sheet_name=name,
                            rows=rows,
                            start_row=row_number,
                            end_row=row_number,
                            start_column="A",
                            end_column="F",
                        ),
                    ),
                    limitations=(
                        "Source table is an ontology candidate; a reviewer must decide its canonical object mapping.",
                    ),
                )
            )

    required_headers = {
        "table name",
        "field name",
        "field description",
        "nullable",
        "data type",
    }
    for sheet in sheets:
        sheet_name = str(sheet.get("sheet_name") or "")
        if not sheet_name or sheet is overview:
            continue
        rows = sheet_rows[sheet_name]
        header_number: int | None = None
        header_by_name: dict[str, str] = {}
        for row_number, row in sorted(rows.items()):
            candidate = {
                _normalized(value): column
                for column, (value, _) in row.items()
                if _normalized(value)
            }
            if required_headers.issubset(candidate):
                header_number = row_number
                header_by_name = candidate
                break
        if header_number is None:
            continue
        dictionary_sheets.add(sheet_name)
        fields: list[dict[str, Any]] = []
        last_row = header_number
        for row_number, row in sorted(rows.items()):
            if row_number <= header_number:
                continue
            field_name = _cell_text(row, header_by_name["field name"])
            if not field_name:
                continue
            last_row = row_number
            fields.append(
                {
                    "field_name": field_name,
                    "description": _cell_text(
                        row, header_by_name["field description"]
                    ),
                    "nullable": _cell_text(row, header_by_name["nullable"]),
                    "allowable_values": _cell_text(
                        row,
                        header_by_name.get(
                            "allowable value value list if any", "ZZZ"
                        ),
                    ),
                    "data_type": _cell_text(row, header_by_name["data type"]),
                    "source_database": _cell_text(
                        row, header_by_name.get("source database", "ZZZ")
                    ),
                    "source_table": _cell_text(
                        row, header_by_name.get("source table", "ZZZ")
                    ),
                    "source_field": _cell_text(
                        row, header_by_name.get("source field", "ZZZ")
                    ),
                    "transform_logic": _cell_text(
                        row, header_by_name.get("transform logic", "ZZZ")
                    ),
                    "remark": _cell_text(
                        row, header_by_name.get("remark", "ZZZ")
                    ),
                }
            )
        if not fields:
            continue
        declared_table = _cell_text(
            rows[last_row], header_by_name["table name"]
        )
        table_name = declared_table or sheet_name
        end_column = get_column_letter(
            max(
                column_index_from_string(column)
                for column in header_by_name.values()
            )
        )
        limitations = [
            "Field and transform rows are observations; canonical properties, bindings and joins require human review."
        ]
        declared_count = declared_field_counts.get(table_name)
        count_matches_declared = (
            declared_count is None or declared_count == len(fields)
        )
        if not count_matches_declared:
            limitations.append(
                f"Overview declares {declared_count} fields but the detailed sheet contains {len(fields)} field rows."
            )
        if bool(sheet.get("truncated")):
            limitations.append(
                "The parsed attachment exceeded the extraction bound; rerun with a dedicated adapter before acceptance."
            )
        observations.append(
            SourceObservationV1(
                candidate_type="MAPPING",
                source_key=f"{source_id}:mapping:{table_name}",
                label=f"{table_name} 字段与来源映射",
                definition=f"{len(fields)} 个字段及其来源、类型、枚举和转换逻辑。",
                support_class="DIRECT_EXACT",
                proposal={
                    "contract": "source-table-mapping-observation/v1",
                    "source_version_id": source_version_id,
                    "table_name": table_name,
                    "field_count": len(fields),
                    "declared_field_count": declared_count,
                    "count_matches_declared": count_matches_declared,
                    "complete": not bool(sheet.get("truncated")),
                    "fields": fields,
                },
                source_anchors=(
                    _xlsx_anchor(
                        source_id=source_id,
                        source_checksum=source_checksum,
                        sheet_name=sheet_name,
                        rows=rows,
                        start_row=header_number,
                        end_row=last_row,
                        start_column="A",
                        end_column=end_column,
                    ),
                ),
                limitations=tuple(limitations),
            )
        )

    for sheet in sheets:
        sheet_name = str(sheet.get("sheet_name") or "")
        if (
            not sheet_name
            or sheet is overview
            or sheet_name in dictionary_sheets
        ):
            continue
        rows = sheet_rows[sheet_name]
        header_number = next(
            (number for number, row in sorted(rows.items()) if row), None
        )
        if header_number is None:
            continue
        header = rows[header_number]
        columns = [
            _cell_text(header, column)
            for column in sorted(header, key=column_index_from_string)
            if _cell_text(header, column)
        ]
        if not columns:
            continue
        end_column = max(header, key=column_index_from_string)
        used_end = _used_range_end_row(str(sheet.get("used_range") or "A1"))
        observations.append(
            SourceObservationV1(
                candidate_type="PROPERTY",
                source_key=f"{source_id}:sample-schema:{sheet_name}",
                label=f"{sheet_name} 样例 Schema",
                definition=(
                    f"样例材料声明 {len(columns)} 个字段、约 "
                    f"{max(0, used_end - header_number)} 条数据记录。"
                ),
                support_class="DERIVED_DETERMINISTIC",
                proposal={
                    "contract": "source-sample-schema-observation/v1",
                    "source_version_id": source_version_id,
                    "sheet_name": sheet_name,
                    "columns": columns,
                    "observed_row_count": max(0, used_end - header_number),
                    "sample_values_promoted_to_truth": False,
                },
                source_anchors=(
                    _xlsx_anchor(
                        source_id=source_id,
                        source_checksum=source_checksum,
                        sheet_name=sheet_name,
                        rows=rows,
                        start_row=header_number,
                        end_row=header_number,
                        start_column="A",
                        end_column=end_column,
                    ),
                ),
                limitations=(
                    "Sample values are synthetic observations and are not promoted to business facts or enum truth.",
                ),
            )
        )
    return tuple(observations)


def _sql_observation(asset: dict[str, Any]) -> SourceObservationV1:
    source_id, source_checksum, source_version_id, preview = _preview_identity(asset)
    lines = tuple(_record(item) for item in preview.get("text_lines", ()))
    anchor = _text_anchor(
        source_id=source_id,
        source_checksum=source_checksum,
        source_version_id=source_version_id,
        lines=lines,
    )
    text = "\n".join(str(item.get("text") or "") for item in lines)
    statement_count = len([item for item in text.split(";") if item.strip()])
    limitations = [
        "SQL is retained as a calculation observation; it is not executed or promoted to a canonical Formula/Query contract automatically."
    ]
    if preview.get("limitation"):
        limitations.append(str(preview["limitation"]))
    return SourceObservationV1(
        candidate_type="RULE",
        source_key=f"{source_id}:sql",
        label=str(
            asset.get("title")
            or asset.get("original_name")
            or "SQL logic"
        ),
        definition=(
            f"登记了 {statement_count} 个 SQL statement，"
            "等待与指标、规则和映射逐项核对。"
        ),
        support_class="DIRECT_EXACT",
        proposal={
            "contract": "source-sql-observation/v1",
            "source_version_id": source_version_id,
            "source_checksum": source_checksum,
            "statement_count": statement_count,
            "executable_as_canonical_query": False,
        },
        source_anchors=(anchor,),
        limitations=tuple(limitations),
    )


def build_source_observations(intake: Any) -> tuple[SourceObservationV1, ...]:
    observations: list[SourceObservationV1] = []
    for asset in _assets(intake):
        if not asset.get("source_preview"):
            continue
        kind = str(asset.get("kind") or "")
        preview = _record(asset.get("source_preview"))
        if (
            kind in {"data_model", "data_dictionary"}
            and preview.get("sheets")
        ):
            observations.extend(_workbook_observations(asset))
        elif kind == "sql" and preview.get("text_lines"):
            observations.append(_sql_observation(asset))
    mappings = {
        str(item.proposal.get("table_name")): item
        for item in observations
        if item.proposal.get("contract")
        == "source-table-mapping-observation/v1"
    }
    samples = {
        str(item.proposal.get("sheet_name")): item
        for item in observations
        if item.proposal.get("contract")
        == "source-sample-schema-observation/v1"
    }
    for table_name in sorted(mappings.keys() & samples.keys()):
        mapping = mappings[table_name]
        sample = samples[table_name]
        dictionary_fields = {
            str(item.get("field_name"))
            for item in mapping.proposal.get("fields", ())
            if item.get("field_name")
        }
        sample_fields = {
            str(item)
            for item in sample.proposal.get("columns", ())
            if str(item)
        }
        missing_in_sample = tuple(sorted(dictionary_fields - sample_fields))
        extra_in_sample = tuple(sorted(sample_fields - dictionary_fields))
        matches = not missing_in_sample and not extra_in_sample
        observations.append(
            SourceObservationV1(
                candidate_type="RULE",
                source_key=(
                    f"{mapping.source_key}:versus:{sample.source_key}:schema"
                ),
                label=f"{table_name} 字典与样例一致性",
                definition=(
                    "字段字典与样例表头一致。"
                    if matches
                    else (
                        f"字段字典与样例表头不一致：样例缺少 {len(missing_in_sample)} "
                        f"个字段，额外包含 {len(extra_in_sample)} 个字段。"
                    )
                ),
                support_class="DERIVED_DETERMINISTIC",
                proposal={
                    "contract": "source-schema-consistency-observation/v1",
                    "table_name": table_name,
                    "status": "MATCH" if matches else "MISMATCH",
                    "dictionary_field_count": len(dictionary_fields),
                    "sample_field_count": len(sample_fields),
                    "missing_in_sample": missing_in_sample,
                    "extra_in_sample": extra_in_sample,
                },
                source_anchors=(
                    mapping.source_anchors[0],
                    sample.source_anchors[0],
                ),
                limitations=(
                    "This proves header consistency only; it does not prove data completeness, key integrity or business correctness.",
                ),
            )
        )
    return tuple(observations)
