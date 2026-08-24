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


def test_composite_entity_key_compiles_as_one_distinct_row_value(
    package: OntologyPackage,
) -> None:
    trade = next(item for item in package.entities if item.id == "entity.trade")
    changed_trade = trade.model_copy(
        update={
            "primary_key": (
                "property.trade.trade_id",
                "property.trade.market_id",
            )
        }
    )
    entities = tuple(
        changed_trade if item.id == changed_trade.id else item
        for item in package.entities
    )

    query = compile_turnover(
        package.model_copy(update={"entities": entities}),
        ("2025-Q3",),
    )

    assert (
        'COUNT(DISTINCT (b."trade_id", b."market_id")) '
        "AS contributing_entity_count"
    ) in query.sql
    assert "binding.trade.trade_id" in query.mapping_ids
    assert "binding.trade.market_id" in query.mapping_ids


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


def test_governed_yn_boolean_transformation_compiles_to_sql(
    package: OntologyPackage,
) -> None:
    binding = next(
        item
        for item in package.bindings
        if item.logical_target == "property.trade.cancellation_flag"
    )
    source = next(item for item in package.data_sources if item.id == binding.source)
    table = next(item for item in source.tables if item.name == binding.table)
    changed_fields = tuple(
        field.model_copy(update={"data_type": "string"})
        if field.name == binding.column
        else field
        for field in table.fields
    )
    changed_table = table.model_copy(update={"fields": changed_fields})
    changed_source = source.model_copy(update={"tables": (changed_table,)})
    changed_sources = tuple(
        changed_source if item.id == source.id else item
        for item in package.data_sources
    )
    changed_binding = binding.model_copy(update={"transformation": "yn_to_boolean"})
    changed_bindings = tuple(
        changed_binding if item.id == binding.id else item
        for item in package.bindings
    )
    changed = package.model_copy(
        update={"data_sources": changed_sources, "bindings": changed_bindings}
    )

    query = compile_turnover(changed, ("2025-Q3",))

    assert "CASE WHEN UPPER(TRIM(b.\"cancellation_flag\")) = 'Y' THEN TRUE" in query.sql


def test_governed_population_rule_compiles_without_invented_boolean_column(
    package: OntologyPackage,
) -> None:
    metric = next(
        item for item in package.metrics if item.id == "metric.eligible_turnover"
    )
    changed_metric = metric.model_copy(
        update={
            "query": metric.query.model_copy(
                update={
                    "population_property": None,
                    "population_rule": "rule.eligible_trade",
                    "filters": (),
                }
            )
        }
    )
    changed = package.model_copy(
        update={
            "metrics": tuple(
                changed_metric if item.id == metric.id else item
                for item in package.metrics
            )
        }
    )

    query = compile_turnover(changed, ("2025-Q3",))

    assert 'b."status" = ?' in query.sql
    assert 'b."cancellation_flag" = FALSE' in query.sql
    assert "EXECUTED" in query.params
    assert "SYNTH-CASH" not in query.params
