from __future__ import annotations

import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from .io import file_checksum
from .models import OntologyPackage, ValidationCheck
from .sql_compiler import (
    DuckDBContext,
    compile_trading_days,
    compile_turnover,
    quote_identifier,
)


def _check(check_id: str, passed: bool, message: str, **details: object) -> ValidationCheck:
    return ValidationCheck(
        check_id=check_id,
        category="data",
        status="PASS" if passed else "FAIL",
        message=message,
        details=details,
    )


def _close(actual: Any, expected: Any, tolerance: float) -> bool:
    try:
        return abs(float(actual) - float(expected)) <= tolerance
    except (TypeError, ValueError):
        return actual == expected


def _manifest_checks(
    package: OntologyPackage,
    resource_paths: Mapping[str, Path],
    manifest_path: Path,
    expected_dataset_id: str | None,
) -> list[ValidationCheck]:
    if not manifest_path.is_file():
        return [_check("DATA_MANIFEST", False, "Dataset manifest is missing", path=str(manifest_path))]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [_check("DATA_MANIFEST", False, "Dataset manifest cannot be read", error=str(exc))]

    mismatches: dict[str, object] = {}
    dataset_id = manifest.get("dataset_id")
    if expected_dataset_id is not None and dataset_id != expected_dataset_id:
        mismatches["dataset_id"] = {
            "actual": dataset_id,
            "expected": expected_dataset_id,
        }

    declared_files = manifest.get("files", {})
    for source in package.data_sources:
        path = resource_paths.get(source.id)
        if path is None:
            mismatches[source.id] = "resource binding missing"
            continue
        entry = declared_files.get(path.name)
        if not path.is_file():
            mismatches[source.id] = "file missing"
        elif not isinstance(entry, dict):
            mismatches[source.id] = "file absent from manifest"
        elif entry.get("sha256") != file_checksum(path):
            mismatches[source.id] = "sha256 mismatch"
    return [
        _check(
            "DATA_MANIFEST",
            not mismatches,
            "Dataset identity and file hashes match the ontology snapshot",
            dataset_id=dataset_id,
            mismatches=mismatches,
        )
    ]


def _schema_and_key_checks(
    package: OntologyPackage,
    context: DuckDBContext,
) -> list[ValidationCheck]:
    schema_mismatches: dict[str, object] = {}
    key_defects: dict[str, int] = {}
    null_defects: dict[str, dict[str, int]] = {}

    for source in package.data_sources:
        for table in source.tables:
            table_sql = quote_identifier(table.name)
            described = context.connection.execute(f"DESCRIBE SELECT * FROM {table_sql}").fetchall()
            actual_columns = {row[0] for row in described}
            expected_columns = {field.name for field in table.fields}
            if actual_columns != expected_columns:
                schema_mismatches[table.name] = {
                    "missing": sorted(expected_columns - actual_columns),
                    "unexpected": sorted(actual_columns - expected_columns),
                }

            required = [field.name for field in table.fields if not field.nullable]
            if required:
                expressions = ", ".join(
                    f"SUM(CASE WHEN {quote_identifier(column)} IS NULL THEN 1 ELSE 0 END) AS {quote_identifier(column)}"
                    for column in required
                )
                row = context.connection.execute(f"SELECT {expressions} FROM {table_sql}").fetchone()
                counts = {column: int(value or 0) for column, value in zip(required, row, strict=True)}
                defects = {column: count for column, count in counts.items() if count}
                if defects:
                    null_defects[table.name] = defects

            keys = [quote_identifier(column) for column in table.primary_key]
            if len(keys) == 1:
                expression = keys[0]
            else:
                expression = "(" + ", ".join(keys) + ")"
            duplicates = context.connection.execute(
                f"SELECT COUNT(*) - COUNT(DISTINCT {expression}) FROM {table_sql}"
            ).fetchone()[0]
            if duplicates:
                key_defects[table.name] = int(duplicates)

    return [
        _check(
            "PHYSICAL_SCHEMA",
            not schema_mismatches,
            "CSV columns match the declared physical schema",
            mismatches=schema_mismatches,
        ),
        _check(
            "REQUIRED_VALUES",
            not null_defects,
            "Non-nullable physical fields contain no nulls",
            defects=null_defects,
        ),
        _check(
            "PRIMARY_KEY_UNIQUENESS",
            not key_defects,
            "Declared table primary keys are unique",
            defects=key_defects,
        ),
    ]


def _join_checks(package: OntologyPackage, context: DuckDBContext) -> list[ValidationCheck]:
    defects: dict[str, object] = {}
    for join in package.joins:
        left = quote_identifier(join.left_table)
        right = quote_identifier(join.right_table)
        right_keys = [quote_identifier(key.right_column) for key in join.keys]
        group = ", ".join(right_keys)
        duplicate_groups = context.connection.execute(
            f"SELECT COUNT(*) FROM (SELECT {group} FROM {right} GROUP BY {group} HAVING COUNT(*) > 1)"
        ).fetchone()[0]

        predicate = " AND ".join(
            f"l.{quote_identifier(key.left_column)} = r.{quote_identifier(key.right_column)}"
            for key in join.keys
        )
        orphans = context.connection.execute(
            f"SELECT COUNT(*) FROM {left} AS l WHERE NOT EXISTS "
            f"(SELECT 1 FROM {right} AS r WHERE {predicate})"
        ).fetchone()[0]

        left_duplicates = 0
        if join.expected_cardinality == "1:1":
            left_keys = [quote_identifier(key.left_column) for key in join.keys]
            left_group = ", ".join(left_keys)
            left_duplicates = context.connection.execute(
                f"SELECT COUNT(*) FROM (SELECT {left_group} FROM {left} GROUP BY {left_group} HAVING COUNT(*) > 1)"
            ).fetchone()[0]
        if duplicate_groups or orphans or left_duplicates:
            defects[join.id] = {
                "right_duplicate_key_groups": int(duplicate_groups),
                "orphan_left_rows": int(orphans),
                "left_duplicate_key_groups": int(left_duplicates),
            }
    return [
        _check(
            "JOIN_CARDINALITY_AND_COVERAGE",
            not defects,
            "Join keys satisfy declared cardinality and every left row resolves",
            defects=defects,
        )
    ]


def _calendar_contract_checks(
    package: OntologyPackage, context: DuckDBContext
) -> list[ValidationCheck]:
    bindings = {binding.logical_target: binding for binding in package.bindings}
    market = bindings["property.calendar.market_id"]
    date = bindings["property.calendar.calendar_date"]
    period = bindings["property.calendar.period_id"]
    definitions = {item.id: item for item in package.scenario.periods}
    rows = context.connection.execute(
        f"SELECT {quote_identifier(date.column)}, {quote_identifier(period.column)} "
        f"FROM {quote_identifier(date.table)} WHERE {quote_identifier(market.column)} = ?",
        [package.scenario.market_id],
    ).fetchall()
    defects: list[dict[str, object]] = []
    for calendar_date, period_id in rows:
        definition = definitions.get(period_id)
        if definition is None:
            defects.append({"date": str(calendar_date), "period": period_id, "reason": "unknown period"})
            continue
        inside = (
            definition.start <= calendar_date <= definition.end
            if definition.inclusive
            else definition.start < calendar_date < definition.end
        )
        if not inside:
            defects.append(
                {"date": str(calendar_date), "period": period_id, "reason": "outside period bounds"}
            )
    return [
        _check(
            "CALENDAR_PERIOD_BOUNDS",
            not defects,
            "Scenario-market calendar rows agree with governed period bounds",
            defects=defects[:50],
            total_defects=len(defects),
        )
    ]


def _oracle_checks(
    package: OntologyPackage,
    control_dir: Path,
    context: DuckDBContext,
) -> list[ValidationCheck]:
    oracle_path = control_dir / "oracle.json"
    if not oracle_path.is_file():
        return [_check("GOLDEN_ORACLE", False, "Independent golden oracle is missing")]
    oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
    periods = tuple(oracle["periods"].keys())
    tolerance = float(oracle.get("tolerances", {}).get("absolute", 1e-6))

    turnover_rows = context.execute(compile_turnover(package, periods))
    day_rows = context.execute(compile_trading_days(package, periods))
    segment_rows = context.execute(compile_turnover(package, periods, by_segment=True))
    turnover = {row["period_id"]: row for row in turnover_rows}
    days = {row["period_id"]: row for row in day_rows}
    segments: dict[str, dict[str, Any]] = defaultdict(dict)
    group_sizes: dict[str, int] = {}
    for row in segment_rows:
        segments[row["period_id"]][row["segment_id"]] = row["turnover_hkd_mn"]
        group_sizes[f'{row["period_id"]}/{row["segment_id"]}'] = int(row["contributing_entity_count"])

    fact_defects: dict[str, object] = {}
    segment_defects: dict[str, object] = {}
    for period_id, expected in oracle["periods"].items():
        actual_turnover = turnover.get(period_id, {}).get("turnover_hkd_mn")
        actual_days = days.get(period_id, {}).get("trading_day_count")
        actual_adt = (
            float(actual_turnover) / int(actual_days)
            if actual_turnover is not None and actual_days
            else None
        )
        failures = {}
        if not _close(actual_turnover, expected["eligible_turnover_hkd_mn"], tolerance):
            failures["turnover"] = {"actual": actual_turnover, "expected": expected["eligible_turnover_hkd_mn"]}
        if actual_days != expected["trading_day_count"]:
            failures["trading_days"] = {"actual": actual_days, "expected": expected["trading_day_count"]}
        if not _close(actual_adt, expected["adt_hkd_mn_per_trading_day"], tolerance):
            failures["adt"] = {"actual": actual_adt, "expected": expected["adt_hkd_mn_per_trading_day"]}
        if failures:
            fact_defects[period_id] = failures

        expected_segments = expected["segments"]
        actual_segments = segments.get(period_id, {})
        failures = {
            segment: {"actual": actual_segments.get(segment), "expected": value}
            for segment, value in expected_segments.items()
            if not _close(actual_segments.get(segment), value, tolerance)
        }
        unexpected = sorted(set(actual_segments) - set(expected_segments))
        if failures or unexpected:
            segment_defects[period_id] = {"values": failures, "unexpected": unexpected}

    minimum_group_size = max((policy.minimum_group_size for policy in package.policies), default=1)
    undersized = {key: size for key, size in group_sizes.items() if size < minimum_group_size}
    comparison_defects: dict[str, object] = {}
    if len(periods) == 2 and "comparison" in oracle:
        previous_id, current_id = periods
        missing_inputs = sorted(
            period_id
            for period_id in periods
            if period_id not in turnover
            or period_id not in days
            or period_id not in segments
        )
        if missing_inputs:
            comparison_defects["missing_period_inputs"] = missing_inputs
        else:
            previous_turnover = Decimal(str(turnover[previous_id]["turnover_hkd_mn"]))
            current_turnover = Decimal(str(turnover[current_id]["turnover_hkd_mn"]))
            previous_days = Decimal(str(days[previous_id]["trading_day_count"]))
            current_days = Decimal(str(days[current_id]["trading_day_count"]))
            previous_adt = previous_turnover / previous_days
            current_adt = current_turnover / current_days
            turnover_delta = current_turnover - previous_turnover
            adt_delta = current_adt - previous_adt
            segment_deltas = {
                segment: Decimal(str(segments[current_id][segment]))
                - Decimal(str(segments[previous_id][segment]))
                for segment in segments[previous_id]
            }
            if not segment_deltas or previous_turnover == 0 or previous_adt == 0 or turnover_delta == 0:
                comparison_defects["undefined_control_comparison"] = True
            else:
                leading_segment = min(segment_deltas, key=segment_deltas.get)
                calendar_effect = (current_days - previous_days) * previous_adt
                activity_effect = (current_adt - previous_adt) * current_days
                residual = turnover_delta - calendar_effect - activity_effect
                actual_comparison = {
                    "turnover_delta_hkd_mn": turnover_delta,
                    "turnover_delta_pct": turnover_delta / previous_turnover * 100,
                    "adt_delta_hkd_mn_per_trading_day": adt_delta,
                    "adt_delta_pct": adt_delta / previous_adt * 100,
                    "largest_decline_segment": leading_segment,
                    "largest_decline_delta_hkd_mn": segment_deltas[leading_segment],
                    "largest_decline_contribution_pct": segment_deltas[leading_segment]
                    / turnover_delta
                    * 100,
                    "calendar_effect_hkd_mn": calendar_effect,
                    "activity_effect_hkd_mn": activity_effect,
                    "decomposition_residual_hkd_mn": residual,
                }
                for field, expected in oracle["comparison"].items():
                    actual = actual_comparison.get(field)
                    if not _close(actual, expected, tolerance):
                        comparison_defects[field] = {"actual": actual, "expected": expected}
    return [
        _check(
            "GOLDEN_PERIOD_FACTS",
            not fact_defects,
            "Compiled turnover, calendar and ADT results match the constructed synthetic control oracle",
            defects=fact_defects,
        ),
        _check(
            "GOLDEN_SEGMENT_RECONCILIATION",
            not segment_defects,
            "Compiled segment results match the constructed synthetic control oracle",
            defects=segment_defects,
        ),
        _check(
            "MINIMUM_GROUP_SIZE",
            not undersized,
            "Every exposed segment-period aggregate satisfies the policy group-size threshold",
            threshold=minimum_group_size,
            undersized=undersized,
        ),
        _check(
            "GOLDEN_COMPARISON_AND_DECOMPOSITION",
            not comparison_defects,
            "Comparison, leading segment and decomposition match the constructed control oracle",
            defects=comparison_defects,
        ),
    ]


def run_binding_checks(
    package: OntologyPackage,
    resource_paths: Mapping[str, Path],
    *,
    dataset_manifest_path: Path,
    expected_dataset_id: str | None = None,
) -> list[ValidationCheck]:
    checks = _manifest_checks(
        package,
        resource_paths,
        dataset_manifest_path,
        expected_dataset_id,
    )
    if any(check.status == "FAIL" for check in checks):
        return checks
    try:
        with DuckDBContext(package, resource_paths) as context:
            checks.extend(_schema_and_key_checks(package, context))
            checks.extend(_join_checks(package, context))
            checks.extend(_calendar_contract_checks(package, context))
    except Exception as exc:  # Validation must report a gate failure, not crash a review run.
        checks.append(
            _check(
                "DATA_VALIDATION_RUNTIME",
                False,
                "Data validation could not complete",
                error=f"{type(exc).__name__}: {exc}",
            )
        )
    return checks


def run_certification_checks(
    package: OntologyPackage,
    resource_paths: Mapping[str, Path],
    *,
    control_dir: Path,
) -> list[ValidationCheck]:
    try:
        with DuckDBContext(package, resource_paths) as context:
            return _oracle_checks(package, control_dir, context)
    except Exception as exc:
        return [
            _check(
                "CERTIFICATION_RUNTIME",
                False,
                "ADT certification could not complete",
                error=f"{type(exc).__name__}: {exc}",
            )
        ]


def scenario_resource_paths(
    package: OntologyPackage,
    scenario_dir: Path,
) -> dict[str, Path]:
    """Legacy ADT fixture convention; product code uses explicit RuntimeBindingSpec."""

    return {
        source.id: scenario_dir / "data" / f"{source.tables[0].name}.csv"
        for source in package.data_sources
        if len(source.tables) == 1
    }


def run_data_checks(package: OntologyPackage, scenario_dir: Path) -> list[ValidationCheck]:
    resources = scenario_resource_paths(package, scenario_dir)
    manifest_path = scenario_dir / "data" / "manifest.json"
    expected_dataset_id: str | None = None
    if manifest_path.is_file():
        try:
            expected_dataset_id = json.loads(
                manifest_path.read_text(encoding="utf-8")
            ).get("dataset_id")
        except (OSError, json.JSONDecodeError):
            pass
    checks = run_binding_checks(
        package,
        resources,
        dataset_manifest_path=manifest_path,
        expected_dataset_id=expected_dataset_id,
    )
    if any(check.status == "FAIL" for check in checks):
        return checks
    checks.extend(
        run_certification_checks(
            package,
            resources,
            control_dir=scenario_dir / "golden",
        )
    )
    return checks
