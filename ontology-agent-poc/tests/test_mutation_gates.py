from __future__ import annotations

import csv
import json
from datetime import timedelta
from pathlib import Path

from ontology_agent.io import file_checksum
from ontology_agent.models import OntologyPackage
from ontology_agent.validation import validate_package


def _failed(package: OntologyPackage, scenario_dir: Path) -> set[str]:
    report = validate_package(package, scenario_dir, include_data=True)
    assert report.status == "FAIL"
    return {check.check_id for check in report.checks if check.status == "FAIL"}


def _refresh_manifest(scenario_dir: Path, filename: str, row_count: int | None = None) -> None:
    path = scenario_dir / "data" / filename
    manifest_path = scenario_dir / "data" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][filename]["sha256"] = file_checksum(path)
    if row_count is not None:
        manifest["files"][filename]["rows"] = row_count
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_wrong_measure_mapping_is_caught_by_oracle(
    package: OntologyPackage, scenario_dir: Path
) -> None:
    bindings = tuple(
        binding.model_copy(update={"column": "order_value_hkd_mn"})
        if binding.id == "binding.trade.executed_value"
        else binding
        for binding in package.bindings
    )
    changed = package.model_copy(update={"bindings": bindings})
    failed = _failed(changed, scenario_dir)
    assert "GOLDEN_PERIOD_FACTS" in failed
    assert "GOLDEN_SEGMENT_RECONCILIATION" in failed


def test_missing_eligibility_filter_is_caught_by_sentinels(
    package: OntologyPackage, scenario_dir: Path
) -> None:
    metric = package.metrics[0]
    changed_metric = metric.model_copy(
        update={"query": metric.query.model_copy(update={"filters": ()})}
    )
    changed = package.model_copy(update={"metrics": (changed_metric, *package.metrics[1:])})
    failed = _failed(changed, scenario_dir)
    assert "GOLDEN_PERIOD_FACTS" in failed


def test_calendar_change_is_caught_even_with_refreshed_file_hash(
    package: OntologyPackage, scenario_dir: Path
) -> None:
    path = scenario_dir / "data" / "trading_calendar.csv"
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])
    changed = False
    for row in rows:
        if row["period_id"] == "2025-Q3" and row["is_trading_day"] == "false":
            row["is_trading_day"] = "true"
            changed = True
            break
    assert changed
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    _refresh_manifest(scenario_dir, path.name, len(rows))
    failed = _failed(package, scenario_dir)
    assert "GOLDEN_PERIOD_FACTS" in failed


def test_duplicate_dimension_key_blocks_fanout(
    package: OntologyPackage, scenario_dir: Path
) -> None:
    path = scenario_dir / "data" / "instrument_dim.csv"
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])
    rows.append(dict(rows[0], segment_id="OTHER", segment_name="Other Securities"))
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    _refresh_manifest(scenario_dir, path.name, len(rows))
    failed = _failed(package, scenario_dir)
    assert "PRIMARY_KEY_UNIQUENESS" in failed
    assert "JOIN_CARDINALITY_AND_COVERAGE" in failed


def test_market_scope_mutation_changes_execution_and_is_blocked(
    package: OntologyPackage, scenario_dir: Path
) -> None:
    scenario = package.scenario.model_copy(update={"market_id": "UNBOUND-MARKET"})
    changed = package.model_copy(update={"scenario": scenario})
    failed = _failed(changed, scenario_dir)
    assert {"GOLDEN_PERIOD_FACTS", "DATA_VALIDATION_RUNTIME"} & failed


def test_period_bound_mutation_is_not_ignored(
    package: OntologyPackage, scenario_dir: Path
) -> None:
    period = package.scenario.periods[0]
    changed_period = period.model_copy(update={"start": period.start + timedelta(days=1)})
    scenario = package.scenario.model_copy(
        update={"periods": (changed_period, *package.scenario.periods[1:])}
    )
    changed = package.model_copy(update={"scenario": scenario})
    failed = _failed(changed, scenario_dir)
    assert "CALENDAR_PERIOD_BOUNDS" in failed
    # Runtime binding fails closed before the optional certification stage.
    assert "GOLDEN_PERIOD_FACTS" not in failed


def test_unsupported_binding_transformation_fails_capability_gate(
    package: OntologyPackage, scenario_dir: Path
) -> None:
    binding = package.bindings[0].model_copy(update={"transformation": "multiply_by_1000"})
    changed = package.model_copy(update={"bindings": (binding, *package.bindings[1:])})
    failed = _failed(changed, scenario_dir)
    assert "ADT_CAPABILITY_CONTRACT" in failed
