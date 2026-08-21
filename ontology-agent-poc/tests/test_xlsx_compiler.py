from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from openpyxl import Workbook

from ontology_agent.intake import CompilationError, compile_tabular_xlsx
from ontology_agent.io import canonical_bytes, file_checksum


DICTIONARY_HEADERS = [
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
]


def _save_packet(root: Path) -> tuple[Path, Path]:
    dictionary_path = root / "dictionary.xlsx"
    dictionary = Workbook()
    overview = dictionary.active
    overview.title = "Overview"
    overview.append(["Table", "Field Count"])
    overview.append(["event", 5])
    sheet = dictionary.create_sheet("event_dictionary")
    sheet.append(DICTIONARY_HEADERS)
    for name, nullable, sql_type in [
        ("event_id", "No", "VARCHAR(64)"),
        ("event_date", "No", "DATE"),
        ("event_timestamp", "No", "TIMESTAMP(6)"),
        ("amount", "No", "DECIMAL(20,8)"),
        ("status", "No", "VARCHAR(16)"),
    ]:
        sheet.append(
            [
                "event",
                name,
                f"Description for {name}",
                nullable,
                "OPEN; CLOSED" if name == "status" else "",
                sql_type,
                "SYNTHETIC",
                "event",
                name,
                "identity",
                "",
            ]
        )
    dictionary.save(dictionary_path)

    sample_path = root / "sample.xlsx"
    sample = Workbook()
    data = sample.active
    data.title = "event_data"
    data.append(["event_id", "event_date", "event_timestamp", "amount", "status"])
    data.append(["E1", date(2026, 8, 20), datetime(2026, 8, 20, 9, 30), 12.5, "OPEN"])
    data.append(["E2", date(2026, 8, 20), datetime(2026, 8, 20, 9, 31), 7.25, "CLOSED"])
    sample.save(sample_path)
    return dictionary_path, sample_path


def _write_contracts(root: Path, dictionary_path: Path, sample_path: Path) -> tuple[Path, Path, Path]:
    source_manifest = {
        "files": [
            {
                "source_id": "DICT",
                "file_name": dictionary_path.name,
                "size_bytes": dictionary_path.stat().st_size,
                "sha256": file_checksum(dictionary_path),
            },
            {
                "source_id": "SAMPLE",
                "file_name": sample_path.name,
                "size_bytes": sample_path.stat().st_size,
                "sha256": file_checksum(sample_path),
            },
        ]
    }
    spec = {
        "contract": "tabular-xlsx-compilation/v1",
        "build_id": "test.build.v1",
        "dataset_id": "test-dataset-v1",
        "dictionary_source_id": "DICT",
        "sample_source_id": "SAMPLE",
        "source_timezone": "Asia/Hong_Kong",
        "storage_timezone": "UTC",
        "dictionary_overview_sheet": "Overview",
        "tables": [
            {
                "table": "event",
                "dictionary_sheet": "event_dictionary",
                "data_sheet": "event_data",
                "primary_key": ["event_id"],
                "declared_overview_field_count": 5,
            }
        ],
        "value_aliases": [
            {
                "table": "event",
                "column": "status",
                "aliases": {"CANCELLED": "CANCELED"},
                "decision_id": "TEST-001",
            }
        ],
        "enum_checks": [
            {
                "table": "event",
                "column": "status",
                "allowed_values": ["OPEN", "CLOSED"],
                "allow_null": False,
            }
        ],
        "reference_checks": [],
    }
    assumptions = {"contract": "test-assumptions/v1", "decisions": [{"id": "TEST-001"}]}
    paths = (root / "sources.json", root / "spec.json", root / "assumptions.json")
    for path, payload in zip(paths, (source_manifest, spec, assumptions), strict=True):
        path.write_bytes(canonical_bytes(payload) + b"\n")
    return paths


def test_xlsx_compiler_is_typed_reproducible_and_source_preserving(tmp_path: Path) -> None:
    dictionary_path, sample_path = _save_packet(tmp_path)
    source_path, spec_path, assumptions_path = _write_contracts(
        tmp_path, dictionary_path, sample_path
    )
    source_hashes = (file_checksum(dictionary_path), file_checksum(sample_path))

    first = compile_tabular_xlsx(
        spec_path=spec_path,
        source_manifest_path=source_path,
        assumption_register_path=assumptions_path,
        input_root=tmp_path,
        output_dir=tmp_path / "out",
    )
    first_hashes = {
        path.name: file_checksum(path)
        for path in (
            *first.table_paths,
            first.schema_path,
            first.quality_report_path,
            first.manifest_path,
        )
    }
    second = compile_tabular_xlsx(
        spec_path=spec_path,
        source_manifest_path=source_path,
        assumption_register_path=assumptions_path,
        input_root=tmp_path,
        output_dir=tmp_path / "out",
    )
    second_hashes = {
        path.name: file_checksum(path)
        for path in (
            *second.table_paths,
            second.schema_path,
            second.quality_report_path,
            second.manifest_path,
        )
    }

    assert first_hashes == second_hashes
    assert source_hashes == (file_checksum(dictionary_path), file_checksum(sample_path))
    table = pq.read_table(second.table_paths[0])
    assert table.num_rows == 2
    assert table.schema.field("event_date").type == pa.date32()
    assert table.schema.field("event_timestamp").type == pa.timestamp("us", tz="UTC")
    assert table.schema.field("amount").type == pa.decimal128(20, 8)
    assert table.column("event_timestamp")[0].as_py().hour == 1
    assert second.quality_status == "PASS"


def test_xlsx_compiler_fails_closed_on_source_identity_change(tmp_path: Path) -> None:
    dictionary_path, sample_path = _save_packet(tmp_path)
    source_path, spec_path, assumptions_path = _write_contracts(
        tmp_path, dictionary_path, sample_path
    )
    with sample_path.open("ab") as stream:
        stream.write(b"tamper")

    with pytest.raises(CompilationError, match="Source size mismatch"):
        compile_tabular_xlsx(
            spec_path=spec_path,
            source_manifest_path=source_path,
            assumption_register_path=assumptions_path,
            input_root=tmp_path,
            output_dir=tmp_path / "out",
        )


def test_xlsx_compiler_fails_before_output_on_invalid_enum(tmp_path: Path) -> None:
    dictionary_path, sample_path = _save_packet(tmp_path)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "event_data"
    sheet.append(["event_id", "event_date", "event_timestamp", "amount", "status"])
    sheet.append(["E1", date(2026, 8, 20), datetime(2026, 8, 20, 9, 30), 12.5, "BROKEN"])
    workbook.save(sample_path)
    source_path, spec_path, assumptions_path = _write_contracts(
        tmp_path, dictionary_path, sample_path
    )

    with pytest.raises(CompilationError, match="pre-output checks failed"):
        compile_tabular_xlsx(
            spec_path=spec_path,
            source_manifest_path=source_path,
            assumption_register_path=assumptions_path,
            input_root=tmp_path,
            output_dir=tmp_path / "out",
        )
    assert not (tmp_path / "out" / "event.parquet").exists()
