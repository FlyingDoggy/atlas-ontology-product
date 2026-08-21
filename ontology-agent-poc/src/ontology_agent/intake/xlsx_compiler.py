from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

import pyarrow as pa
import pyarrow.parquet as pq
from openpyxl import load_workbook
from pydantic import Field, model_validator

from ..io import canonical_bytes, file_checksum, sha256_value
from ..models import StrictModel


COMPILER_ID = "ontology-agent.tabular-xlsx-compiler"
COMPILER_VERSION = "1.0.0"
_SQL_TYPE = re.compile(r"^(?P<base>[A-Z]+)(?:\((?P<args>[0-9, ]+)\))?$")


class CompilationError(RuntimeError):
    """The input packet cannot be compiled without violating its contract."""


class TableSpec(StrictModel):
    table: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    dictionary_sheet: str = Field(min_length=1)
    data_sheet: str = Field(min_length=1)
    primary_key: tuple[str, ...] = Field(min_length=1)
    declared_overview_field_count: int | None = Field(default=None, ge=1)


class ValueAliasSpec(StrictModel):
    table: str
    column: str
    aliases: dict[str, str] = Field(min_length=1)
    decision_id: str


class EnumCheckSpec(StrictModel):
    table: str
    column: str
    allowed_values: tuple[str, ...] = Field(min_length=1)
    allow_null: bool = True


class ReferenceCheckSpec(StrictModel):
    check_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    from_table: str
    from_columns: tuple[str, ...] = Field(min_length=1)
    to_table: str
    to_columns: tuple[str, ...] = Field(min_length=1)
    allow_null: bool = True

    @model_validator(mode="after")
    def validate_arity(self) -> ReferenceCheckSpec:
        if len(self.from_columns) != len(self.to_columns):
            raise ValueError("Reference check column arity must match")
        return self


class XlsxCompilationSpec(StrictModel):
    contract: Literal["tabular-xlsx-compilation/v1"]
    build_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    dataset_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    dictionary_source_id: str
    sample_source_id: str
    source_timezone: str
    storage_timezone: Literal["UTC"] = "UTC"
    dictionary_overview_sheet: str
    tables: tuple[TableSpec, ...] = Field(min_length=1)
    value_aliases: tuple[ValueAliasSpec, ...] = ()
    enum_checks: tuple[EnumCheckSpec, ...] = ()
    reference_checks: tuple[ReferenceCheckSpec, ...] = ()

    @model_validator(mode="after")
    def validate_unique_objects(self) -> XlsxCompilationSpec:
        table_names = [item.table for item in self.tables]
        if len(table_names) != len(set(table_names)):
            raise ValueError("Compilation tables must be unique")
        aliases = [(item.table, item.column) for item in self.value_aliases]
        if len(aliases) != len(set(aliases)):
            raise ValueError("A table column may have only one alias map")
        checks = [item.check_id for item in self.reference_checks]
        if len(checks) != len(set(checks)):
            raise ValueError("Reference check IDs must be unique")
        return self


@dataclass(frozen=True, slots=True)
class CompilationResult:
    manifest_path: Path
    schema_path: Path
    quality_report_path: Path
    table_paths: tuple[Path, ...]
    manifest_checksum: str
    quality_status: Literal["PASS", "WARN"]


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CompilationError(f"Cannot read JSON contract {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CompilationError(f"JSON contract {path} must be an object")
    return payload


def _write_canonical_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_bytes(canonical_bytes(payload) + b"\n")


def _source_by_id(source_manifest: dict[str, Any], source_id: str) -> dict[str, Any]:
    matches = [item for item in source_manifest.get("files", []) if item.get("source_id") == source_id]
    if len(matches) != 1:
        raise CompilationError(f"Source manifest must contain exactly one {source_id}")
    return matches[0]


def _verified_source(input_root: Path, source: dict[str, Any]) -> Path:
    path = input_root / str(source["file_name"])
    if not path.is_file():
        raise CompilationError(f"Source file is missing: {path}")
    observed_size = path.stat().st_size
    if observed_size != source["size_bytes"]:
        raise CompilationError(f"Source size mismatch for {path.name}")
    observed_checksum = file_checksum(path)
    if observed_checksum != source["sha256"]:
        raise CompilationError(f"Source checksum mismatch for {path.name}")
    return path


def _arrow_type(sql_type: str) -> tuple[pa.DataType, dict[str, int] | None]:
    match = _SQL_TYPE.fullmatch(sql_type.strip().upper())
    if match is None:
        raise CompilationError(f"Unsupported dictionary SQL type: {sql_type}")
    base = match.group("base")
    raw_args = match.group("args")
    args = tuple(int(value.strip()) for value in raw_args.split(",")) if raw_args else ()
    if base in {"VARCHAR", "CHAR"}:
        return pa.string(), None
    if base == "BIGINT":
        return pa.int64(), None
    if base == "INTEGER":
        return pa.int32(), None
    if base == "SMALLINT":
        return pa.int16(), None
    if base == "DATE":
        return pa.date32(), None
    if base == "TIMESTAMP":
        return pa.timestamp("us", tz="UTC"), None
    if base == "DECIMAL" and len(args) == 2:
        precision, scale = args
        return pa.decimal128(precision, scale), {"precision": precision, "scale": scale}
    raise CompilationError(f"Unsupported dictionary SQL type: {sql_type}")


def _normalize_value(
    value: Any,
    *,
    arrow_type: pa.DataType,
    decimal_meta: dict[str, int] | None,
    source_timezone: ZoneInfo,
    aliases: dict[str, str],
) -> tuple[Any, bool]:
    if value is None:
        return None, False
    changed = False
    if isinstance(value, str):
        stripped = value.strip()
        changed = stripped != value
        value = aliases.get(stripped, stripped)
        changed = changed or value != stripped
    if pa.types.is_string(arrow_type):
        return str(value), changed
    if pa.types.is_integer(arrow_type):
        if isinstance(value, bool):
            raise ValueError("boolean is not an integer value")
        return int(value), changed
    if pa.types.is_date32(arrow_type):
        if isinstance(value, datetime):
            return value.date(), changed
        if isinstance(value, date):
            return value, changed
        return date.fromisoformat(str(value)), changed
    if pa.types.is_timestamp(arrow_type):
        if not isinstance(value, datetime):
            value = datetime.fromisoformat(str(value))
        if value.tzinfo is None:
            value = value.replace(tzinfo=source_timezone)
        return value.astimezone(timezone.utc), changed
    if pa.types.is_decimal(arrow_type):
        if decimal_meta is None:
            raise ValueError("decimal metadata missing")
        try:
            decimal_value = Decimal(str(value))
        except InvalidOperation as exc:
            raise ValueError(f"invalid decimal value {value!r}") from exc
        quantum = Decimal(1).scaleb(-decimal_meta["scale"])
        return decimal_value.quantize(quantum, rounding=ROUND_HALF_EVEN), changed
    raise ValueError(f"unsupported Arrow type {arrow_type}")


def _read_dictionary_sheet(workbook: Any, sheet_name: str) -> list[dict[str, Any]]:
    if sheet_name not in workbook.sheetnames:
        raise CompilationError(f"Dictionary sheet is missing: {sheet_name}")
    worksheet = workbook[sheet_name]
    rows = worksheet.iter_rows(values_only=True)
    headers = next(rows, None)
    if headers is None:
        raise CompilationError(f"Dictionary sheet is empty: {sheet_name}")
    header_names = [str(value).strip() if value is not None else "" for value in headers]
    required = {
        "Table Name",
        "Field Name",
        "Field Description",
        "Nullable",
        "Allowable Value/Value List (if any)",
        "Data Type",
        "Source Database",
        "Source Table",
        "Source Field",
        "Transform Logic",
        "Remark",
    }
    if not required.issubset(set(header_names)):
        missing = sorted(required - set(header_names))
        raise CompilationError(f"Dictionary sheet {sheet_name} is missing columns: {missing}")
    result: list[dict[str, Any]] = []
    for row in rows:
        record = dict(zip(header_names, row, strict=False))
        if record.get("Field Name") is None:
            continue
        result.append(record)
    if not result:
        raise CompilationError(f"Dictionary sheet has no fields: {sheet_name}")
    return result


def _read_sample_sheet(workbook: Any, sheet_name: str) -> tuple[list[str], list[tuple[Any, ...]]]:
    if sheet_name not in workbook.sheetnames:
        raise CompilationError(f"Sample sheet is missing: {sheet_name}")
    worksheet = workbook[sheet_name]
    rows = worksheet.iter_rows(values_only=True)
    raw_headers = next(rows, None)
    if raw_headers is None:
        raise CompilationError(f"Sample sheet is empty: {sheet_name}")
    headers = [str(value).strip() if value is not None else "" for value in raw_headers]
    if any(not item for item in headers) or len(headers) != len(set(headers)):
        raise CompilationError(f"Sample sheet has empty or duplicate headers: {sheet_name}")
    return headers, [tuple(row) for row in rows if any(value is not None for value in row)]


def _check(
    checks: list[dict[str, Any]],
    *,
    check_id: str,
    status: Literal["PASS", "WARN", "FAIL"],
    message: str,
    evidence: dict[str, Any] | None = None,
    decision_ids: tuple[str, ...] = (),
) -> None:
    checks.append(
        {
            "check_id": check_id,
            "status": status,
            "message": message,
            "evidence": evidence or {},
            "decision_ids": list(decision_ids),
        }
    )


def compile_tabular_xlsx(
    *,
    spec_path: Path,
    source_manifest_path: Path,
    assumption_register_path: Path,
    input_root: Path,
    output_dir: Path,
) -> CompilationResult:
    """Compile exact XLSX evidence into typed Parquet and deterministic manifests.

    The compiler is deliberately scenario-neutral. Scenario semantics enter through
    an exact compilation spec and a versioned assumption register. It never edits
    source workbooks and fails closed on checksum, schema, primary-key, enum or
    reference-integrity errors.
    """

    spec_payload = _load_json(spec_path)
    spec = XlsxCompilationSpec.model_validate(spec_payload)
    source_manifest = _load_json(source_manifest_path)
    assumptions = _load_json(assumption_register_path)
    source_manifest_checksum = sha256_value(source_manifest)
    assumption_register_checksum = sha256_value(assumptions)
    spec_checksum = sha256_value(spec_payload)

    dictionary_source = _source_by_id(source_manifest, spec.dictionary_source_id)
    sample_source = _source_by_id(source_manifest, spec.sample_source_id)
    dictionary_path = _verified_source(input_root, dictionary_source)
    sample_path = _verified_source(input_root, sample_source)
    source_checksums_before = {
        dictionary_path: file_checksum(dictionary_path),
        sample_path: file_checksum(sample_path),
    }

    try:
        dictionary_workbook = load_workbook(dictionary_path, read_only=True, data_only=True)
        sample_workbook = load_workbook(sample_path, read_only=True, data_only=True)
    except Exception as exc:  # openpyxl has multiple format-specific exceptions
        raise CompilationError(f"Cannot open XLSX evidence: {exc}") from exc

    alias_index = {(item.table, item.column): item for item in spec.value_aliases}
    enum_index = {(item.table, item.column): item for item in spec.enum_checks}
    source_timezone = ZoneInfo(spec.source_timezone)
    checks: list[dict[str, Any]] = []
    table_rows: dict[str, list[dict[str, Any]]] = {}
    table_schemas: dict[str, pa.Schema] = {}
    table_metadata: dict[str, list[dict[str, Any]]] = {}
    alias_counts: dict[str, int] = {}

    for table_spec in spec.tables:
        dictionary_fields = _read_dictionary_sheet(
            dictionary_workbook, table_spec.dictionary_sheet
        )
        headers, sample_rows = _read_sample_sheet(sample_workbook, table_spec.data_sheet)
        field_names = [str(item["Field Name"]).strip() for item in dictionary_fields]
        if headers != field_names:
            _check(
                checks,
                check_id=f"schema.headers.{table_spec.table}",
                status="FAIL",
                message="Sample headers do not exactly match the ordered dictionary fields",
                evidence={"dictionary": field_names, "sample": headers},
            )
            continue
        _check(
            checks,
            check_id=f"schema.headers.{table_spec.table}",
            status="PASS",
            message="Sample headers exactly match the ordered dictionary fields",
            evidence={"field_count": len(headers)},
        )

        declared_count = table_spec.declared_overview_field_count
        if declared_count is not None and declared_count != len(headers):
            _check(
                checks,
                check_id=f"schema.overview_count.{table_spec.table}",
                status="WARN",
                message="Overview field count differs from the exact detailed dictionary and sample headers",
                evidence={"overview": declared_count, "actual": len(headers)},
                decision_ids=("CT-ASM-019",),
            )
        else:
            _check(
                checks,
                check_id=f"schema.overview_count.{table_spec.table}",
                status="PASS",
                message="Overview field count matches the detailed dictionary",
                evidence={"field_count": len(headers)},
            )

        fields: list[pa.Field] = []
        decimal_meta_by_column: dict[str, dict[str, int] | None] = {}
        metadata_rows: list[dict[str, Any]] = []
        for definition in dictionary_fields:
            name = str(definition["Field Name"]).strip()
            sql_type = str(definition["Data Type"]).strip().upper()
            arrow_type, decimal_meta = _arrow_type(sql_type)
            nullable_text = str(definition["Nullable"]).strip().upper()
            if nullable_text not in {"YES", "NO"}:
                raise CompilationError(
                    f"Invalid Nullable value for {table_spec.table}.{name}: {nullable_text}"
                )
            nullable = nullable_text == "YES"
            fields.append(pa.field(name, arrow_type, nullable=nullable))
            decimal_meta_by_column[name] = decimal_meta
            metadata_rows.append(
                {
                    "name": name,
                    "description": str(definition["Field Description"] or "").strip(),
                    "nullable": nullable,
                    "allowable_values": str(
                        definition["Allowable Value/Value List (if any)"] or ""
                    ).strip(),
                    "sql_type": sql_type,
                    "arrow_type": str(arrow_type),
                    "source_database": str(definition["Source Database"] or "").strip(),
                    "source_table": str(definition["Source Table"] or "").strip(),
                    "source_field": str(definition["Source Field"] or "").strip(),
                    "transform_logic": str(definition["Transform Logic"] or "").strip(),
                    "remark": str(definition["Remark"] or "").strip(),
                }
            )
        schema = pa.schema(fields)
        normalized_rows: list[dict[str, Any]] = []
        conversion_errors: list[dict[str, Any]] = []
        alias_count_by_column: dict[str, int] = {}
        for row_number, raw_row in enumerate(sample_rows, start=2):
            record: dict[str, Any] = {}
            for column_index, field in enumerate(schema):
                raw_value = raw_row[column_index] if column_index < len(raw_row) else None
                alias_spec = alias_index.get((table_spec.table, field.name))
                aliases = alias_spec.aliases if alias_spec is not None else {}
                try:
                    value, changed = _normalize_value(
                        raw_value,
                        arrow_type=field.type,
                        decimal_meta=decimal_meta_by_column[field.name],
                        source_timezone=source_timezone,
                        aliases=aliases,
                    )
                except (TypeError, ValueError, InvalidOperation) as exc:
                    conversion_errors.append(
                        {
                            "row": row_number,
                            "column": field.name,
                            "value": repr(raw_value),
                            "error": str(exc),
                        }
                    )
                    value = None
                if changed:
                    alias_count_by_column[field.name] = (
                        alias_count_by_column.get(field.name, 0) + 1
                    )
                record[field.name] = value
            normalized_rows.append(record)
        if conversion_errors:
            _check(
                checks,
                check_id=f"types.convert.{table_spec.table}",
                status="FAIL",
                message="One or more values could not be converted to the dictionary type",
                evidence={"errors": conversion_errors[:25], "error_count": len(conversion_errors)},
            )
        else:
            _check(
                checks,
                check_id=f"types.convert.{table_spec.table}",
                status="PASS",
                message="All values converted to the dictionary types",
                evidence={"row_count": len(normalized_rows)},
            )
        for column, count in alias_count_by_column.items():
            alias_counts[f"{table_spec.table}.{column}"] = count

        required_columns = [field.name for field in schema if not field.nullable]
        null_failures = {
            column: sum(1 for row in normalized_rows if row[column] is None)
            for column in required_columns
        }
        null_failures = {key: value for key, value in null_failures.items() if value}
        _check(
            checks,
            check_id=f"required.not_null.{table_spec.table}",
            status="FAIL" if null_failures else "PASS",
            message=(
                "Required columns contain nulls"
                if null_failures
                else "All required columns are populated"
            ),
            evidence={"null_counts": null_failures},
        )

        missing_pk = [column for column in table_spec.primary_key if column not in headers]
        if missing_pk:
            _check(
                checks,
                check_id=f"primary_key.{table_spec.table}",
                status="FAIL",
                message="Primary-key columns are absent",
                evidence={"missing_columns": missing_pk},
            )
        else:
            keys = [tuple(row[column] for column in table_spec.primary_key) for row in normalized_rows]
            null_key_count = sum(any(value is None for value in key) for key in keys)
            duplicate_count = len(keys) - len(set(keys))
            _check(
                checks,
                check_id=f"primary_key.{table_spec.table}",
                status="FAIL" if null_key_count or duplicate_count else "PASS",
                message=(
                    "Primary key contains null or duplicate values"
                    if null_key_count or duplicate_count
                    else "Primary key is complete and unique"
                ),
                evidence={
                    "columns": list(table_spec.primary_key),
                    "null_key_count": null_key_count,
                    "duplicate_count": duplicate_count,
                },
            )

        for (enum_table, column), enum_spec in enum_index.items():
            if enum_table != table_spec.table:
                continue
            if column not in headers:
                _check(
                    checks,
                    check_id=f"enum.{table_spec.table}.{column}",
                    status="FAIL",
                    message="Configured enum column is absent",
                )
                continue
            invalid = sorted(
                {
                    str(row[column])
                    for row in normalized_rows
                    if row[column] is not None
                    and str(row[column]) not in enum_spec.allowed_values
                }
            )
            null_count = sum(row[column] is None for row in normalized_rows)
            status: Literal["PASS", "FAIL"] = (
                "FAIL" if invalid or (null_count and not enum_spec.allow_null) else "PASS"
            )
            _check(
                checks,
                check_id=f"enum.{table_spec.table}.{column}",
                status=status,
                message="Enum values are valid" if status == "PASS" else "Enum values are invalid",
                evidence={"invalid_values": invalid, "null_count": null_count},
            )

        table_rows[table_spec.table] = normalized_rows
        table_schemas[table_spec.table] = schema
        table_metadata[table_spec.table] = metadata_rows

    if any(check["status"] == "FAIL" for check in checks):
        raise CompilationError(
            "Compilation stopped before output because pre-output checks failed: "
            + ", ".join(check["check_id"] for check in checks if check["status"] == "FAIL")
        )

    for reference in spec.reference_checks:
        if reference.from_table not in table_rows or reference.to_table not in table_rows:
            _check(
                checks,
                check_id=reference.check_id,
                status="FAIL",
                message="Reference check names an unknown table",
            )
            continue
        from_headers = set(table_rows[reference.from_table][0]) if table_rows[reference.from_table] else set()
        to_headers = set(table_rows[reference.to_table][0]) if table_rows[reference.to_table] else set()
        missing_columns = [
            f"{reference.from_table}.{column}"
            for column in reference.from_columns
            if column not in from_headers
        ] + [
            f"{reference.to_table}.{column}"
            for column in reference.to_columns
            if column not in to_headers
        ]
        if missing_columns:
            _check(
                checks,
                check_id=reference.check_id,
                status="FAIL",
                message="Reference check column is absent",
                evidence={"missing_columns": missing_columns},
            )
            continue
        target = {
            tuple(row[column] for column in reference.to_columns)
            for row in table_rows[reference.to_table]
        }
        failures: list[dict[str, Any]] = []
        for row_number, row in enumerate(table_rows[reference.from_table], start=2):
            key = tuple(row[column] for column in reference.from_columns)
            if any(value is None for value in key):
                if reference.allow_null:
                    continue
                failures.append({"row": row_number, "key": [str(value) for value in key]})
            elif key not in target:
                failures.append({"row": row_number, "key": [str(value) for value in key]})
        _check(
            checks,
            check_id=reference.check_id,
            status="FAIL" if failures else "PASS",
            message=(
                "Reference integrity failures found"
                if failures
                else "Reference integrity is valid"
            ),
            evidence={"failure_count": len(failures), "examples": failures[:20]},
        )

    if any(check["status"] == "FAIL" for check in checks):
        raise CompilationError(
            "Compilation stopped before output because pre-output checks failed: "
            + ", ".join(check["check_id"] for check in checks if check["status"] == "FAIL")
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    table_outputs: list[dict[str, Any]] = []
    final_table_paths: list[Path] = []
    with tempfile.TemporaryDirectory(prefix="xlsx-compile-", dir=output_dir.parent) as temp_name:
        temp_dir = Path(temp_name)
        for table_spec in spec.tables:
            table = pa.Table.from_pylist(
                table_rows[table_spec.table], schema=table_schemas[table_spec.table]
            )
            temp_path = temp_dir / f"{table_spec.table}.parquet"
            pq.write_table(
                table,
                temp_path,
                compression="zstd",
                use_dictionary=True,
                write_statistics=True,
                version="2.6",
            )
            final_path = output_dir / temp_path.name
            os.replace(temp_path, final_path)
            final_table_paths.append(final_path)
            table_outputs.append(
                {
                    "table": table_spec.table,
                    "path": final_path.name,
                    "row_count": table.num_rows,
                    "column_count": table.num_columns,
                    "primary_key": list(table_spec.primary_key),
                    "sha256": file_checksum(final_path),
                    "size_bytes": final_path.stat().st_size,
                }
            )

    source_checksums_after = {
        path: file_checksum(path) for path in source_checksums_before
    }
    if source_checksums_after != source_checksums_before:
        raise CompilationError("A source workbook changed during compilation")

    quality_status: Literal["PASS", "WARN"] = (
        "WARN" if any(check["status"] == "WARN" for check in checks) else "PASS"
    )
    schema_payload = {
        "contract": "typed-tabular-schema/v1",
        "build_id": spec.build_id,
        "compiler": {"id": COMPILER_ID, "version": COMPILER_VERSION},
        "source_manifest_checksum": source_manifest_checksum,
        "compilation_spec_checksum": spec_checksum,
        "assumption_register_checksum": assumption_register_checksum,
        "tables": [
            {
                "table": table_spec.table,
                "primary_key": list(table_spec.primary_key),
                "fields": table_metadata[table_spec.table],
            }
            for table_spec in spec.tables
        ],
    }
    quality_payload = {
        "contract": "tabular-data-quality-report/v1",
        "build_id": spec.build_id,
        "status": quality_status,
        "compiler": {"id": COMPILER_ID, "version": COMPILER_VERSION},
        "source_manifest_checksum": source_manifest_checksum,
        "compilation_spec_checksum": spec_checksum,
        "assumption_register_checksum": assumption_register_checksum,
        "checks": checks,
        "summary": {
            "pass": sum(check["status"] == "PASS" for check in checks),
            "warn": sum(check["status"] == "WARN" for check in checks),
            "fail": sum(check["status"] == "FAIL" for check in checks),
            "value_normalizations": alias_counts,
        },
    }
    schema_path = output_dir / "schema.json"
    quality_report_path = output_dir / "quality-report.json"
    _write_canonical_json(schema_path, schema_payload)
    _write_canonical_json(quality_report_path, quality_payload)
    manifest_payload = {
        "contract": "typed-tabular-dataset-manifest/v1",
        "build_id": spec.build_id,
        "dataset_id": spec.dataset_id,
        "classification": "constructed_synthetic",
        "compiler": {"id": COMPILER_ID, "version": COMPILER_VERSION},
        "source_manifest_checksum": source_manifest_checksum,
        "compilation_spec_checksum": spec_checksum,
        "assumption_register_checksum": assumption_register_checksum,
        "source_files": [
            {
                "source_id": dictionary_source["source_id"],
                "sha256": dictionary_source["sha256"],
                "size_bytes": dictionary_source["size_bytes"],
            },
            {
                "source_id": sample_source["source_id"],
                "sha256": sample_source["sha256"],
                "size_bytes": sample_source["size_bytes"],
            },
        ],
        "time_convention": {
            "source_timezone": spec.source_timezone,
            "storage_timezone": spec.storage_timezone,
            "decision_id": "CT-ASM-020",
        },
        "schema": {
            "path": schema_path.name,
            "sha256": file_checksum(schema_path),
            "size_bytes": schema_path.stat().st_size,
        },
        "quality_report": {
            "path": quality_report_path.name,
            "sha256": file_checksum(quality_report_path),
            "size_bytes": quality_report_path.stat().st_size,
            "status": quality_status,
        },
        "tables": table_outputs,
        "limitations": [
            "Constructed-synthetic sample; not HKEX validated",
            "Physical production schemas and business controls remain unconfirmed",
            "All provisional transformations are identified by the assumption register checksum",
        ],
    }
    manifest_path = output_dir / "manifest.json"
    _write_canonical_json(manifest_path, manifest_payload)
    return CompilationResult(
        manifest_path=manifest_path,
        schema_path=schema_path,
        quality_report_path=quality_report_path,
        table_paths=tuple(final_table_paths),
        manifest_checksum=file_checksum(manifest_path),
        quality_status=quality_status,
    )
