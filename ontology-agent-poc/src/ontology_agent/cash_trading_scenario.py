from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

import pyarrow.parquet as pq
import yaml

from .cash_trading_runtime import (
    CASH_OPERATOR_VERSION,
    CashTradingDuckDB,
    _latency_query,
    _summary_query,
    _trend_query,
    analyze_cash_snapshot,
)
from .contracts import (
    CertificationSpec,
    DataResourceBinding,
    RuntimeBindingSpec,
    VerifiedSnapshot,
)
from .io import DEFAULT_PROJECT_ROOT, file_checksum, sha256_value
from .models import AnalysisResponse, OntologyPackage, ValidationCheck
from .scenario import (
    BoundAnalysisGoal,
    ScenarioAdapterDescriptor,
    ScenarioAdapterError,
    ScenarioEvaluation,
    ScenarioValidation,
)


CASH_PACKAGE_ID = "ontology.exchange_analytics.cash_trading"
CASH_ADAPTER_ID = "cash-trading-reference"
CASH_ADAPTER_VERSION = CASH_OPERATOR_VERSION
CASH_CERTIFICATION_PROFILE = "cash-trading-golden-v1"
CASH_EVALUATION_SUITE = "cash-trading.tracer.v1.suite"
CASH_EVALUATION_CASE_IDS = (
    "golden.self_trade.summary.en",
    "golden.self_trade.trend.zh",
    "golden.self_trade.timeline.en",
    "golden.latency.en",
    "golden.evidence.en",
    "boundary.missing_time",
    "boundary.misconduct",
    "boundary.role",
)

_RAW_SOURCES = {
    "source.order_activity": "order_activity",
    "source.trading_activity": "trading_activity",
    "source.instrument_reference": "instrument_reference",
    "source.account_reference": "account_reference",
    "source.trading_calendar": "trading_calendar",
    "source.order_type_reference": "order_type_reference",
    "source.exchange_rate": "exchange_rate",
}
_EXPECTED_SOURCES = (
    *_RAW_SOURCES,
    "source.cash_trade_analytics",
    "source.cash_order_lifecycle_analytics",
)
_EXPECTED_RULES = {
    "rule.active_client_trade",
    "rule.submitted_order",
    "rule.rejected_order",
    "rule.eligible_client_order",
    "rule.fully_filled_client_order",
    "rule.canceled_order",
    "rule.eligible_trade",
    "rule.self_trade_eligible",
    "rule.potential_self_trade",
    "rule.nonnegative_latency",
}
_EXPECTED_METRICS = {
    "metric.submitted_order_count",
    "metric.rejected_order_count",
    "metric.order_rejection_rate",
    "metric.submitted_order_quantity",
    "metric.executed_order_quantity",
    "metric.order_fill_rate",
    "metric.eligible_trade_count",
    "metric.active_client_trade_quantity",
    "metric.active_client_trade_notional_hkd",
    "metric.active_client_trade_notional_usd_pre_haircut",
    "metric.active_client_trading_volume",
    "metric.eligible_client_order_count",
    "metric.fully_filled_client_order_count",
    "metric.client_order_completion_rate",
    "metric.canceled_order_count",
    "metric.cancel_to_trade_ratio",
    "metric.order_to_trade_denominator",
    "metric.order_to_trade_ratio",
    "metric.self_trade_eligible_trade_count",
    "metric.potential_self_trade_count",
    "metric.potential_self_trade_rate",
    "metric.trade_capture_latency_ms",
}
_EXPECTED_OPERATIONS = {
    "cash.query_metric",
    "cash.self_trade_summary",
    "cash.self_trade_daily_trend",
    "cash.self_trade_timeline",
    "cash.trade_latency_profile",
    "cash.evidence_audit",
}
_IMPLEMENTATION_FILES = (
    "cash_trading_deepagent.py",
    "cash_trading_runtime.py",
    "cash_trading_scenario.py",
    "contracts.py",
    "io.py",
    "lifecycle.py",
    "models.py",
    "release.py",
    "runtime_snapshot.py",
    "scenario.py",
)


def cash_trading_synthetic_binding(*, resource_root_id: str) -> RuntimeBindingSpec:
    resources = tuple(
        DataResourceBinding(
            source_id=source_id,
            resource_ref=(
                "sql/reference_controls.sql"
                if source_id
                in {
                    "source.cash_trade_analytics",
                    "source.cash_order_lifecycle_analytics",
                }
                else f"data/{table}.parquet"
            ),
        )
        for source_id, table in [
            *list(_RAW_SOURCES.items()),
            ("source.cash_trade_analytics", "cash_trade_analytics"),
            (
                "source.cash_order_lifecycle_analytics",
                "cash_order_lifecycle_analytics",
            ),
        ]
    )
    return RuntimeBindingSpec(
        environment_id="cash-trading-poc",
        resource_root_id=resource_root_id,
        adapter_id=CASH_ADAPTER_ID,
        adapter_version=CASH_ADAPTER_VERSION,
        query_engine_id="duckdb.local",
        query_engine_version="1",
        dataset_manifest_ref="data/manifest.json",
        expected_dataset_id="cash-trading-synthetic-v1",
        data_resources=resources,
    )


def cash_trading_golden_certification(*, resource_root_id: str) -> CertificationSpec:
    return CertificationSpec(
        profile_id=CASH_CERTIFICATION_PROFILE,
        profile_version="1.0.0",
        resource_root_id=resource_root_id,
        controls_ref="golden",
    )


def _check(
    check_id: str,
    category: str,
    passed: bool,
    message: str,
    **details: object,
) -> ValidationCheck:
    return ValidationCheck(
        check_id=check_id,
        category=category,
        status="PASS" if passed else "FAIL",
        message=message,
        details=details,
    )


def _read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ScenarioAdapterError(f"Cash Trading {label} is missing")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScenarioAdapterError(f"Cash Trading {label} is unreadable") from exc
    if not isinstance(value, dict):
        raise ScenarioAdapterError(f"Cash Trading {label} is malformed")
    return value


def _capability_check(package: OntologyPackage) -> ValidationCheck:
    defects: list[str] = []
    if package.package_id != CASH_PACKAGE_ID:
        defects.append(f"package_id={package.package_id}")
    actual_sources = tuple(source.id for source in package.data_sources)
    if set(actual_sources) != set(_EXPECTED_SOURCES):
        defects.append("source set differs from the fixed adapter contract")
    actual_rules = {rule.id for rule in package.rules}
    if actual_rules != _EXPECTED_RULES:
        defects.append("rule set differs from the fixed adapter contract")
    actual_metrics = {metric.id for metric in package.metrics}
    if actual_metrics != _EXPECTED_METRICS:
        defects.append("metric set differs from the fixed adapter contract")
    actual_operations = {item.operation for item in package.analysis_patterns}
    if actual_operations != _EXPECTED_OPERATIONS:
        defects.append("analysis operation set differs from the fixed adapter contract")
    rate = next(
        (item for item in package.metrics if item.id == "metric.potential_self_trade_rate"),
        None,
    )
    rate_division = (
        rate.formula.args[0]
        if rate is not None
        and rate.formula.op == "multiply"
        and len(rate.formula.args) == 2
        else None
    )
    rate_scale = (
        rate.formula.args[1]
        if rate is not None
        and rate.formula.op == "multiply"
        and len(rate.formula.args) == 2
        else None
    )
    if (
        rate is None
        or rate_division is None
        or rate_division.op != "divide"
        or tuple(child.ref for child in rate_division.args)
        != (
            "metric.potential_self_trade_count",
            "metric.self_trade_eligible_trade_count",
        )
        or rate_scale is None
        or rate_scale.op != "literal"
        or rate_scale.value != Decimal("100")
    ):
        defects.append(
            "self-trade percentage numerator/denominator/scale contract differs"
        )
    return _check(
        "CASH_CAPABILITY_CONTRACT",
        "semantic",
        not defects,
        "Package matches the closed Cash Trading adapter capability set",
        defects=defects,
    )


def _binding_checks(
    package: OntologyPackage,
    binding: RuntimeBindingSpec,
    resource_paths: Mapping[str, Path],
    dataset_manifest_path: Path,
) -> tuple[ValidationCheck, ...]:
    checks: list[ValidationCheck] = []
    manifest = _read_json(dataset_manifest_path, "dataset manifest")
    checks.append(
        _check(
            "CASH_DATASET_CONTRACT",
            "data",
            manifest.get("contract") == "typed-tabular-dataset-manifest/v1"
            and manifest.get("classification") == "constructed_synthetic"
            and manifest.get("dataset_id") == binding.expected_dataset_id,
            "Dataset contract, classification and identity match the binding",
            contract=manifest.get("contract"),
            classification=manifest.get("classification"),
            dataset_id=manifest.get("dataset_id"),
        )
    )
    declared_tables = {
        item.get("table"): item
        for item in manifest.get("tables", [])
        if isinstance(item, dict)
    }
    table_defects: list[str] = []
    package_sources = {source.id: source for source in package.data_sources}
    for source_id, table_name in _RAW_SOURCES.items():
        path = resource_paths.get(source_id)
        declared = declared_tables.get(table_name)
        package_source = package_sources.get(source_id)
        if path is None or not path.is_file() or path.suffix.lower() != ".parquet":
            table_defects.append(f"{source_id}: missing Parquet")
            continue
        if declared is None:
            table_defects.append(f"{table_name}: missing manifest entry")
            continue
        if (
            file_checksum(path) != declared.get("sha256")
            or path.stat().st_size != declared.get("size_bytes")
        ):
            table_defects.append(f"{table_name}: byte identity mismatch")
            continue
        metadata = pq.ParquetFile(path).metadata
        expected_columns = (
            len(package_source.tables[0].fields)
            if package_source is not None and len(package_source.tables) == 1
            else -1
        )
        if (
            metadata.num_rows != declared.get("row_count")
            or metadata.num_columns != declared.get("column_count")
            or metadata.num_columns != expected_columns
        ):
            table_defects.append(f"{table_name}: row/column shape mismatch")
    checks.append(
        _check(
            "CASH_PARQUET_IDENTITY",
            "data",
            not table_defects and set(declared_tables) == set(_RAW_SOURCES.values()),
            "Every raw Parquet source matches the typed manifest and package schema",
            defects=table_defects,
            declared_tables=sorted(declared_tables),
        )
    )

    scenario_root = dataset_manifest_path.parent.parent
    quality_path = scenario_root / "data" / str(
        manifest.get("quality_report", {}).get("path", "")
    )
    schema_path = scenario_root / "data" / str(manifest.get("schema", {}).get("path", ""))
    quality = _read_json(quality_path, "quality report")
    known_warnings = {
        "schema.overview_count.order_activity",
        "schema.overview_count.trading_activity",
    }
    actual_warnings = {
        item.get("check_id")
        for item in quality.get("checks", [])
        if isinstance(item, dict) and item.get("status") == "WARN"
    }
    quality_ok = (
        file_checksum(quality_path) == manifest.get("quality_report", {}).get("sha256")
        and quality_path.stat().st_size == manifest.get("quality_report", {}).get("size_bytes")
        and quality.get("summary", {}).get("fail") == 0
        and actual_warnings == known_warnings
    )
    schema_ok = (
        schema_path.is_file()
        and file_checksum(schema_path) == manifest.get("schema", {}).get("sha256")
        and schema_path.stat().st_size == manifest.get("schema", {}).get("size_bytes")
    )
    checks.append(
        _check(
            "CASH_TYPED_SCHEMA_AND_QUALITY",
            "data",
            quality_ok and schema_ok,
            "Typed schema and quality report are exact; only the two documented overview-count warnings remain",
            warning_ids=sorted(actual_warnings),
            quality_status=quality.get("status"),
        )
    )

    assumption_path = scenario_root / "governance" / "assumption-register.json"
    assumption_payload = (
        _read_json(assumption_path, "assumption register")
        if assumption_path.is_file()
        else None
    )
    assumption_checksum = (
        sha256_value(assumption_payload) if assumption_payload is not None else None
    )
    assumption_ok = (
        assumption_checksum == manifest.get("assumption_register_checksum")
    )
    checks.append(
        _check(
            "CASH_ASSUMPTION_REGISTER_IDENTITY",
            "source",
            assumption_ok,
            "The dataset is bound to the exact correction/assumption/synthetic-content register",
            expected=manifest.get("assumption_register_checksum"),
            actual=assumption_checksum,
        )
    )

    analytic_paths = {
        source_id: resource_paths.get(source_id)
        for source_id in (
            "source.cash_trade_analytics",
            "source.cash_order_lifecycle_analytics",
        )
    }
    exact_paths = {
        path.resolve()
        for path in analytic_paths.values()
        if path is not None and path.is_file()
    }
    analytic_ok = (
        len(analytic_paths) == 2
        and all(path is not None and path.is_file() for path in analytic_paths.values())
        and len(exact_paths) == 1
        and next(iter(exact_paths)).name == "reference_controls.sql"
        and "not Deloitte/HKEX-provided SQL"
        in next(iter(exact_paths)).read_text(encoding="utf-8")[:500]
    )
    checks.append(
        _check(
            "CASH_ADAPTER_VIEW_RESOURCE",
            "binding",
            analytic_ok,
            "Both logical analytic sources are represented by the same compiler-generated reference SQL and executed only by fixed adapter code",
            source_ids=sorted(analytic_paths),
        )
    )
    return tuple(checks)


def _control_checks(
    snapshot: VerifiedSnapshot,
    control_root: Path,
) -> tuple[tuple[ValidationCheck, ...], dict[str, Any], dict[str, Any]]:
    oracle_path = control_root / "oracle.json"
    questions_path = control_root / "questions.yaml"
    oracle = _read_json(oracle_path, "independent oracle")
    if not questions_path.is_file():
        raise ScenarioAdapterError("Cash Trading golden question manifest is missing")
    questions = yaml.safe_load(questions_path.read_text(encoding="utf-8"))
    if not isinstance(questions, dict):
        raise ScenarioAdapterError("Cash Trading golden question manifest is malformed")
    defects: list[str] = []
    expected_manifest_checksum = oracle.get("dataset_manifest", {}).get("sha256")
    if file_checksum(snapshot.dataset_manifest_path) != expected_manifest_checksum:
        defects.append("oracle dataset manifest checksum differs")
    data_manifest = _read_json(snapshot.dataset_manifest_path, "dataset manifest")
    if oracle.get("assumption_register_checksum") != data_manifest.get(
        "assumption_register_checksum"
    ):
        defects.append("oracle assumption register checksum differs")
    if oracle.get("classification") != "constructed_synthetic":
        defects.append("oracle classification is not constructed_synthetic")
    identity_check = _check(
        "CASH_ORACLE_IDENTITY",
        "data",
        not defects,
        "Independent controls bind to the exact dataset and assumption register",
        defects=defects,
    )

    start, end = date(2026, 8, 3), date(2026, 8, 7)
    with CashTradingDuckDB(snapshot.resource_paths) as context:
        summary = context.execute(_summary_query(start, end))[0]
        latency = context.execute(_latency_query(start, end))[0]
        daily = context.execute(_trend_query(start, end))
    expected_self = oracle.get("controls", {}).get("potential_self_trade", {})
    expected_latency = oracle.get("controls", {}).get("trade_capture_latency", {})
    value_defects: list[str] = []
    comparisons = {
        "eligible_trade_count": (summary.get("eligible_trade_count"), expected_self.get("eligible_trade_count")),
        "candidate_trade_count": (summary.get("candidate_trade_count"), expected_self.get("candidate_trade_count")),
        "candidate_rate_percent": (
            Decimal(str(summary.get("candidate_rate_percent"))),
            Decimal(str(expected_self.get("candidate_rate_percent"))),
        ),
        "eligible_latency_count": (latency.get("eligible_latency_count"), expected_latency.get("eligible_latency_count")),
        "negative_latency_count": (latency.get("negative_latency_count"), expected_latency.get("negative_latency_count")),
        "minimum_ms": (latency.get("minimum_ms"), expected_latency.get("minimum_ms")),
        "p50_ms": (latency.get("p50_ms"), expected_latency.get("p50_ms")),
        "p95_ms": (latency.get("p95_ms"), expected_latency.get("p95_ms")),
        "p99_ms": (latency.get("p99_ms"), expected_latency.get("p99_ms")),
        "maximum_ms": (latency.get("maximum_ms"), expected_latency.get("maximum_ms")),
    }
    for name, (actual, expected) in comparisons.items():
        if actual != expected:
            value_defects.append(f"{name}: {actual!r} != {expected!r}")
    actual_daily = [
        {
            "business_date": row["business_date"].isoformat(),
            "eligible_trade_count": row["eligible_trade_count"],
            "candidate_trade_count": row["candidate_trade_count"],
            "candidate_rate_percent": format(
                Decimal(str(row["candidate_rate_percent"])).normalize(), "f"
            ),
        }
        for row in daily
    ]
    if actual_daily != expected_self.get("daily"):
        value_defects.append("daily self-trade controls differ")
    value_check = _check(
        "CASH_INDEPENDENT_CONTROL_MATCH",
        "data",
        not value_defects,
        "DuckDB runtime results match the independently generated PyArrow controls",
        defects=value_defects,
    )
    return (identity_check, value_check), oracle, questions


def _run_suite(
    snapshot: VerifiedSnapshot,
    oracle: dict[str, Any],
    questions: dict[str, Any],
    execution_dir: Path,
) -> dict[str, Any]:
    raw_cases = questions.get("questions")
    if not isinstance(raw_cases, list):
        raise ScenarioAdapterError("Cash Trading golden question cases are malformed")
    cases: list[dict[str, Any]] = []
    for raw in raw_cases:
        if not isinstance(raw, dict):
            raise ScenarioAdapterError("Cash Trading golden case is malformed")
        response = analyze_cash_snapshot(
            snapshot,
            question=str(raw.get("question", "")),
            role=str(raw.get("role", "")),
            execution_dir=execution_dir,
        )
        defects: list[str] = []
        if response.status != raw.get("expected_status"):
            defects.append(
                f"status {response.status} != {raw.get('expected_status')}"
            )
        expected_intent = raw.get("expected_intent")
        if expected_intent is not None and (
            response.plan is None or response.plan.intent != expected_intent
        ):
            defects.append("resolved intent differs")
        expected_boundary = raw.get("expected_boundary_code")
        if expected_boundary is not None and response.boundary_code != expected_boundary:
            defects.append("boundary code differs")
        if response.status == "ANSWERED" and not response.evidence:
            defects.append("answered response has no evidence")

        case_id = str(raw.get("id"))
        if case_id == "golden.self_trade.summary.en" and response.status == "ANSWERED":
            expected = oracle["controls"]["potential_self_trade"]
            actual = response.facts.get("summary", {})
            if actual.get("eligible_trade_count") != expected["eligible_trade_count"]:
                defects.append("summary denominator differs from oracle")
            if actual.get("candidate_trade_count") != expected["candidate_trade_count"]:
                defects.append("summary numerator differs from oracle")
        elif case_id == "golden.latency.en" and response.status == "ANSWERED":
            expected = oracle["controls"]["trade_capture_latency"]
            actual = response.facts.get("latency", {})
            for name in ("eligible_latency_count", "p50_ms", "p95_ms", "p99_ms"):
                if actual.get(name) != expected[name]:
                    defects.append(f"latency {name} differs from oracle")
        elif case_id == "golden.self_trade.timeline.en" and response.status == "ANSWERED":
            quality = response.facts.get("timeline_quality", {})
            if quality.get("candidate_trade_count") != 1:
                defects.append("timeline candidate count differs")
            if not quality.get("events_are_observed_only"):
                defects.append("timeline completeness limitation is missing")
        cases.append(
            {
                "id": case_id,
                "status": "PASS" if not defects else "FAIL",
                "defects": defects,
                "execution_id": response.execution_id,
            }
        )
    case_ids = tuple(case["id"] for case in cases)
    if case_ids != CASH_EVALUATION_CASE_IDS:
        raise ScenarioAdapterError("Cash Trading golden cases changed or reordered")
    return {
        "suite_id": CASH_EVALUATION_SUITE,
        "status": "PASS" if all(case["status"] == "PASS" for case in cases) else "FAIL",
        "case_count": len(cases),
        "cases": cases,
        "oracle": str(oracle.get("oracle_id")),
        "oracle_defects": {},
    }


class CashTradingScenarioAdapter:
    """Fixed constructed-synthetic Cash Trading implementation behind the common seam."""

    @property
    def descriptor(self) -> ScenarioAdapterDescriptor:
        return ScenarioAdapterDescriptor(
            adapter_id=CASH_ADAPTER_ID,
            adapter_version=CASH_ADAPTER_VERSION,
            query_engine_id="duckdb.local",
            query_engine_version="1",
            certification_profiles={CASH_CERTIFICATION_PROFILE: "1.0.0"},
            evaluation_suite_id=CASH_EVALUATION_SUITE,
            evaluation_case_ids=CASH_EVALUATION_CASE_IDS,
        )

    def build_manifest(self, project_root: Path = DEFAULT_PROJECT_ROOT) -> dict[str, object]:
        source_root = Path(__file__).resolve().parent
        files = {
            f"src/ontology_agent/{name}": file_checksum(source_root / name)
            for name in _IMPLEMENTATION_FILES
            if (source_root / name).is_file()
        }
        for relative in ("pyproject.toml", "uv.lock"):
            path = project_root / relative
            if path.is_file():
                files[relative] = file_checksum(path)
        return {
            "contract": "scenario-adapter-build/v1",
            "adapter_id": CASH_ADAPTER_ID,
            "adapter_version": CASH_ADAPTER_VERSION,
            "query_engine": {"id": "duckdb.local", "version": "1"},
            "evaluation_suite": {
                "suite_id": CASH_EVALUATION_SUITE,
                "case_ids": list(CASH_EVALUATION_CASE_IDS),
            },
            "capability": {
                "package_id": CASH_PACKAGE_ID,
                "operations": sorted(_EXPECTED_OPERATIONS),
                "source_ids": list(_EXPECTED_SOURCES),
                "execution_boundary": "fixed adapter SQL over verified Parquet",
            },
            "files": dict(sorted(files.items())),
        }

    def validate(
        self,
        package: OntologyPackage,
        *,
        binding: RuntimeBindingSpec | None = None,
        resource_paths: Mapping[str, Path] | None = None,
        dataset_manifest_path: Path | None = None,
    ) -> ScenarioValidation:
        checks: list[ValidationCheck] = [_capability_check(package)]
        if binding is None:
            return ScenarioValidation(checks=tuple(checks))
        if (
            binding.query_engine_id != "duckdb.local"
            or binding.query_engine_version != "1"
        ):
            raise ScenarioAdapterError(
                "The Cash Trading reference adapter requires DuckDB contract v1"
            )
        if resource_paths is None or dataset_manifest_path is None:
            raise ScenarioAdapterError(
                "Cash Trading runtime resources and dataset manifest are required"
            )
        checks.extend(
            _binding_checks(package, binding, resource_paths, dataset_manifest_path)
        )
        return ScenarioValidation(checks=tuple(checks))

    def evaluate(
        self,
        snapshot: VerifiedSnapshot,
        *,
        control_dir: Path | None,
        execution_dir: Path,
    ) -> ScenarioEvaluation:
        control_root = control_dir or snapshot.control_dir
        if control_root is None:
            raise ScenarioAdapterError(
                "Cash Trading verification requires the bound golden control directory"
            )
        checks, oracle, questions = _control_checks(snapshot, control_root)
        suite = _run_suite(snapshot, oracle, questions, execution_dir)
        return ScenarioEvaluation(checks=checks, suite=suite)

    def analyze(
        self,
        snapshot: VerifiedSnapshot,
        *,
        question: str,
        role: str,
        execution_dir: Path,
        bound_goal: BoundAnalysisGoal | None = None,
    ) -> AnalysisResponse:
        expected_tools = {
            "anomaly_triage": ("self_trade_summary",),
            "time_series": ("self_trade_trend",),
            "timeline_evidence": ("self_trade_timeline",),
            "latency_profile": ("trade_latency_profile",),
        }
        if bound_goal is not None and expected_tools.get(bound_goal.intent) != bound_goal.tool_ids:
            return AnalysisResponse(
                status="REFUSED",
                answer="The grounded goal does not match the installed Cash Trading capability set.",
                snapshot_checksum=snapshot.snapshot_checksum,
                boundary_code="BOUND_GOAL_CAPABILITY_MISMATCH",
            )
        return analyze_cash_snapshot(
            snapshot,
            question=question,
            role=role,
            execution_dir=execution_dir,
            bound_goal=bound_goal,
        )
