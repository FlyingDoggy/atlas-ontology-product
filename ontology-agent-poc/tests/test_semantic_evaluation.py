from __future__ import annotations

from pathlib import Path

from ontology_agent.io import load_package
from ontology_agent.semantic_evaluation import (
    evaluate_semantic_acceptance,
    load_semantic_acceptance_profile,
)


PROJECT_ROOT = Path(__file__).parents[1]
PACKAGE_PATH = PROJECT_ROOT / "scenarios" / "cash_trading" / "ontology" / "package.yaml"
PROFILE_PATH = (
    PROJECT_ROOT
    / "tests"
    / "fixtures"
    / "evals"
    / "cash_trading"
    / "metric-signatures.json"
)


def test_cash_reference_package_satisfies_external_metric_signature_profile() -> None:
    report = evaluate_semantic_acceptance(
        load_package(PACKAGE_PATH),
        load_semantic_acceptance_profile(PROFILE_PATH),
    )

    assert report.passed, report.model_dump(mode="json")
    assert len(report.results) == 8


def test_external_profile_rejects_currency_relabelling_and_raw_ratio_output() -> None:
    package = load_package(PACKAGE_PATH)
    metrics = []
    for metric in package.metrics:
        if metric.id == "metric.active_client_trading_volume":
            metric = metric.model_copy(update={"unit": "USD"})
        elif metric.id == "metric.order_to_trade_ratio":
            metric = metric.model_copy(update={"unit": "ratio", "value_type": "decimal"})
        metrics.append(metric)

    report = evaluate_semantic_acceptance(
        package.model_copy(update={"metrics": tuple(metrics)}),
        load_semantic_acceptance_profile(PROFILE_PATH),
    )

    assert not report.passed
    failed = {item.resolved_metric_id: item.defects for item in report.results if not item.passed}
    assert "metric.active_client_trading_volume" in failed
    assert "metric.order_to_trade_ratio" in failed
