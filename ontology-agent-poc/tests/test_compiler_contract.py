from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from ontology_agent.formula import evaluate_scalar_formula
from ontology_agent.models import OntologyPackage
from ontology_agent.sql_compiler import compile_trading_days, compile_turnover
from ontology_agent.validation import validate_package


def test_sql_is_scoped_by_governed_period_bounds_market_and_entity_count(
    package: OntologyPackage,
) -> None:
    periods = ("2025-Q3", "2025-Q4")
    turnover = compile_turnover(package, periods, by_segment=True)
    days = compile_trading_days(package, periods)
    for query in (turnover, days):
        assert '"calendar_date" >= ?' in query.sql
        assert '"calendar_date" <= ?' in query.sql
        assert '"market_id" = ?' in query.sql
        assert "SYNTH-CASH" in query.params
    assert 'COUNT(DISTINCT b."trade_id") AS contributing_entity_count' in turnover.sql

    changed_market = package.model_copy(
        update={"scenario": package.scenario.model_copy(update={"market_id": "ANOTHER"})}
    )
    assert "ANOTHER" in compile_turnover(changed_market, periods).params

    period = package.scenario.periods[0]
    changed_period = period.model_copy(update={"start": period.start + timedelta(days=1)})
    changed_bounds = package.model_copy(
        update={
            "scenario": package.scenario.model_copy(
                update={"periods": (changed_period, *package.scenario.periods[1:])}
            )
        }
    )
    assert changed_period.start in compile_turnover(changed_bounds, periods).params


def test_published_formula_ast_drives_decimal_derivation(package: OntologyPackage) -> None:
    adt = next(metric for metric in package.metrics if metric.id == "metric.average_daily_turnover")
    value = evaluate_scalar_formula(
        adt.formula,
        {
            "metric.eligible_turnover": Decimal("8210000"),
            "metric.trading_day_count": Decimal("63"),
        },
        zero_denominator_policy=adt.zero_denominator_policy,
    )
    assert value == Decimal("8210000") / Decimal("63")


def test_datetime_time_semantics_fail_closed(
    package: OntologyPackage, scenario_dir: Path
) -> None:
    properties = tuple(
        prop.model_copy(update={"data_type": "datetime"})
        if prop.id == "property.calendar.calendar_date"
        else prop
        for prop in package.properties
    )
    changed = package.model_copy(update={"properties": properties})
    report = validate_package(changed, scenario_dir, include_data=False)
    failed = {check.check_id for check in report.checks if check.status == "FAIL"}
    assert "ADT_CAPABILITY_CONTRACT" in failed
