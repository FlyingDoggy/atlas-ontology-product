from __future__ import annotations

from pathlib import Path

from ontology_agent.models import OntologyPackage, Status
from ontology_agent.governance import metric_dependencies_sparql
from ontology_agent.validation import validate_package


def test_reference_package_passes_all_gates(package: OntologyPackage, scenario_dir: Path) -> None:
    report = validate_package(package, scenario_dir, include_data=True)
    assert report.status == "PASS"
    assert len(report.checks) >= 33
    assert {check.category for check in report.checks} == {
        "structure",
        "source",
        "semantic",
        "binding",
        "data",
        "shacl",
    }
    assert all(check.status == "PASS" for check in report.checks)


def test_unconfirmed_object_blocks_publication(package: OntologyPackage, scenario_dir: Path) -> None:
    changed_metric = package.metrics[0].model_copy(update={"status": Status.PROPOSED})
    changed = package.model_copy(update={"metrics": (changed_metric, *package.metrics[1:])})
    report = validate_package(changed, scenario_dir, include_data=False)
    failed = {check.check_id for check in report.checks if check.status == "FAIL"}
    assert "CONFIRMED_ONLY" in failed
    assert "SHACL_GRAPH_CONFORMS" in failed


def test_decision_actor_and_affects_must_resolve(
    package: OntologyPackage, scenario_dir: Path
) -> None:
    changed_decision = package.decisions[0].model_copy(
        update={"decided_by": "actor.missing", "affects": ("metric.missing",)}
    )
    changed = package.model_copy(
        update={"decisions": (changed_decision, *package.decisions[1:])}
    )
    report = validate_package(changed, scenario_dir, include_data=False)
    failed = {check.check_id for check in report.checks if check.status == "FAIL"}
    assert "DECISION_REFERENCE_CLOSURE" in failed


def test_unexecuted_formula_unit_or_operator_is_rejected(
    package: OntologyPackage, scenario_dir: Path
) -> None:
    adt = next(metric for metric in package.metrics if metric.id == "metric.average_daily_turnover")
    changed_formula = adt.formula.model_copy(update={"op": "multiply"})
    changed_adt = adt.model_copy(
        update={"formula": changed_formula, "unit": "HKD_MN"}
    )
    metrics = tuple(changed_adt if metric.id == adt.id else metric for metric in package.metrics)
    pattern = package.analysis_patterns[0].model_copy(update={"operation": "UnknownOperator"})
    changed = package.model_copy(
        update={"metrics": metrics, "analysis_patterns": (pattern, *package.analysis_patterns[1:])}
    )
    report = validate_package(changed, scenario_dir, include_data=False)
    failed = {check.check_id for check in report.checks if check.status == "FAIL"}
    assert "ADT_CAPABILITY_CONTRACT" in failed


def test_sparql_governance_query_reads_rdf_metric_dependencies(
    package: OntologyPackage,
) -> None:
    assert metric_dependencies_sparql(
        package, "metric.average_daily_turnover"
    ) == ("metric.eligible_turnover", "metric.trading_day_count")
