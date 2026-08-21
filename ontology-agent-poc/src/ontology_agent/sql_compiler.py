from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import duckdb

from .models import Condition, JoinContract, OntologyPackage, PhysicalBinding, QueryContract, Rule


IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class QueryCompilationError(ValueError):
    pass


@dataclass(frozen=True)
class CompiledQuery:
    operation: str
    sql: str
    params: tuple[Any, ...]
    metric_ids: tuple[str, ...]
    mapping_ids: tuple[str, ...]
    source_ids: tuple[str, ...]


def quote_identifier(value: str) -> str:
    if not IDENTIFIER.fullmatch(value):
        raise QueryCompilationError(f"Unsafe or unsupported SQL identifier: {value!r}")
    return f'"{value}"'


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _binding_map(package: OntologyPackage) -> dict[str, PhysicalBinding]:
    result: dict[str, PhysicalBinding] = {}
    for binding in package.bindings:
        if binding.logical_target in result:
            raise QueryCompilationError(
                f"Multiple physical bindings for {binding.logical_target}; an explicit environment selector is required"
            )
        result[binding.logical_target] = binding
    return result


def _join_map(package: OntologyPackage) -> dict[str, JoinContract]:
    return {join.id: join for join in package.joins}


def _condition_sql(
    condition: Condition,
    bindings: dict[str, PhysicalBinding],
    aliases: dict[str, str],
) -> tuple[str, list[Any], str]:
    binding = bindings.get(condition.property)
    if binding is None:
        raise QueryCompilationError(f"Missing physical binding for rule property {condition.property}")
    alias = aliases.get(binding.source)
    if alias is None:
        raise QueryCompilationError(
            f"Rule property {condition.property} belongs to source {binding.source}, which is not joined"
        )
    field = f"{alias}.{quote_identifier(binding.column)}"
    if condition.op == "is_true":
        return f"{field} = TRUE", [], binding.id
    if condition.op == "is_false":
        return f"{field} = FALSE", [], binding.id
    if condition.op in {"eq", "neq"}:
        operator = "=" if condition.op == "eq" else "<>"
        return f"{field} {operator} ?", [condition.value], binding.id
    values = condition.value
    if not isinstance(values, (list, tuple)) or not values:
        raise QueryCompilationError(f"{condition.op} requires a non-empty list value")
    operator = "IN" if condition.op == "in" else "NOT IN"
    return f"{field} {operator} ({', '.join('?' for _ in values)})", list(values), binding.id


def _join_sql(
    join: JoinContract,
    base_source: str,
    aliases: dict[str, str],
) -> str:
    if join.left_source != base_source:
        raise QueryCompilationError(
            f"Reference compiler supports governed one-hop joins from {base_source}; {join.id} starts at {join.left_source}"
        )
    left_alias = aliases[join.left_source]
    right_alias = aliases[join.right_source]
    predicates = [
        f"{left_alias}.{quote_identifier(key.left_column)} = "
        f"{right_alias}.{quote_identifier(key.right_column)}"
        for key in join.keys
    ]
    return (
        f"JOIN {quote_identifier(join.right_table)} AS {right_alias} ON "
        + " AND ".join(predicates)
    )


def _rules(package: OntologyPackage, rule_ids: Iterable[str]) -> list[Rule]:
    by_id = {rule.id: rule for rule in package.rules}
    missing = [rule_id for rule_id in rule_ids if rule_id not in by_id]
    if missing:
        raise QueryCompilationError(f"Unknown rules: {missing}")
    return [by_id[rule_id] for rule_id in rule_ids]


def _query_context(
    package: OntologyPackage,
    base_source: str,
    join_ids: list[str],
) -> tuple[dict[str, str], list[JoinContract], list[str]]:
    joins_by_id = _join_map(package)
    missing = [join_id for join_id in join_ids if join_id not in joins_by_id]
    if missing:
        raise QueryCompilationError(f"Unknown joins: {missing}")
    joins = [joins_by_id[join_id] for join_id in join_ids]
    aliases = {base_source: "b"}
    for index, join in enumerate(joins, start=1):
        if join.right_source in aliases:
            raise QueryCompilationError(f"Source {join.right_source} is joined more than once without a role name")
        aliases[join.right_source] = f"j{index}"
    return aliases, joins, [base_source, *(join.right_source for join in joins)]


def _period_and_population_scope(
    package: OntologyPackage,
    periods: tuple[str, ...],
    query: QueryContract,
    bindings: dict[str, PhysicalBinding],
    aliases: dict[str, str],
) -> tuple[str, list[Any], list[str]]:
    if not query.period_property or not query.date_property or not query.population_property:
        raise QueryCompilationError("Period, date and population properties are required")
    period_binding = bindings[query.period_property]
    date_binding = bindings[query.date_property]
    population_binding = bindings[query.population_property]
    for binding in (period_binding, date_binding, population_binding):
        if binding.source not in aliases:
            raise QueryCompilationError(
                f"Scope binding {binding.id} belongs to source {binding.source}, which is not joined"
            )
    definitions = {period.id: period for period in package.scenario.periods}
    missing = [period for period in periods if period not in definitions]
    if missing:
        raise QueryCompilationError(f"Unknown governed periods: {missing}")
    clauses: list[str] = []
    params: list[Any] = []
    for period_id in periods:
        definition = definitions[period_id]
        lower = ">=" if definition.inclusive else ">"
        upper = "<=" if definition.inclusive else "<"
        clauses.append(
            "(" 
            f"{aliases[period_binding.source]}.{quote_identifier(period_binding.column)} = ? AND "
            f"{aliases[date_binding.source]}.{quote_identifier(date_binding.column)} {lower} ? AND "
            f"{aliases[date_binding.source]}.{quote_identifier(date_binding.column)} {upper} ?"
            ")"
        )
        params.extend([period_id, definition.start, definition.end])
    population_sql = (
        f"{aliases[population_binding.source]}.{quote_identifier(population_binding.column)} = ?"
    )
    params.append(package.scenario.market_id)
    return (
        "(" + " OR ".join(clauses) + ") AND " + population_sql,
        params,
        [period_binding.id, date_binding.id, population_binding.id],
    )


def compile_turnover(
    package: OntologyPackage,
    periods: tuple[str, ...],
    *,
    by_segment: bool = False,
) -> CompiledQuery:
    if not periods:
        raise QueryCompilationError("At least one explicit period is required")
    metric = next(item for item in package.metrics if item.id == "metric.eligible_turnover")
    if not metric.query.base_source or not metric.query.measure_property or not metric.query.period_property:
        raise QueryCompilationError("Eligible turnover metric is missing its query contract")
    join_ids = list(metric.query.required_joins)
    if by_segment and "join.trade_instrument" not in join_ids:
        join_ids.append("join.trade_instrument")

    aliases, joins, source_ids = _query_context(package, metric.query.base_source, join_ids)
    bindings = _binding_map(package)
    measure = bindings[metric.query.measure_property]
    period = bindings[metric.query.period_property]
    if measure.source not in aliases or period.source not in aliases:
        raise QueryCompilationError("Measure or period binding is not reachable through the governed join graph")

    scope_sql, params, scope_mapping_ids = _period_and_population_scope(
        package, periods, metric.query, bindings, aliases
    )
    mapping_ids = [measure.id, period.id, *scope_mapping_ids]
    select = [
        f"{aliases[period.source]}.{quote_identifier(period.column)} AS period_id",
    ]
    group_by = ["period_id"]
    if by_segment:
        segment_id = bindings["property.segment.segment_id"]
        segment_name = bindings["property.segment.segment_name"]
        if segment_id.source not in aliases or segment_name.source not in aliases:
            raise QueryCompilationError("Segment bindings are not reachable through the governed join graph")
        select.extend(
            [
                f"{aliases[segment_id.source]}.{quote_identifier(segment_id.column)} AS segment_id",
                f"{aliases[segment_name.source]}.{quote_identifier(segment_name.column)} AS segment_name",
            ]
        )
        group_by.extend(["segment_id", "segment_name"])
        mapping_ids.extend([segment_id.id, segment_name.id])
    if metric.formula.op != "sum":
        raise QueryCompilationError(
            f"ADT turnover adapter requires sum(field_ref); got {metric.formula.op}"
        )
    select.append(
        f"SUM({aliases[measure.source]}.{quote_identifier(measure.column)}) AS turnover_hkd_mn"
    )
    entity = next(item for item in package.entities if item.id == metric.base_entity)
    primary_key = bindings[entity.primary_key]
    if primary_key.source not in aliases:
        raise QueryCompilationError("Base-entity primary key is not reachable for group-size enforcement")
    select.append(
        f"COUNT(DISTINCT {aliases[primary_key.source]}.{quote_identifier(primary_key.column)}) "
        "AS contributing_entity_count"
    )
    mapping_ids.append(primary_key.id)

    source = next(item for item in package.data_sources if item.id == metric.query.base_source)
    table = next(item for item in source.tables if item.name == measure.table)
    join_clauses = [_join_sql(join, metric.query.base_source, aliases) for join in joins]
    where = [scope_sql]
    for rule in _rules(package, metric.query.filters):
        for condition in rule.all:
            sql, condition_params, binding_id = _condition_sql(condition, bindings, aliases)
            where.append(sql)
            params.extend(condition_params)
            mapping_ids.append(binding_id)

    sql = "\n".join(
        [
            "SELECT",
            "  " + ",\n  ".join(select),
            f"FROM {quote_identifier(table.name)} AS b",
            *join_clauses,
            "WHERE " + "\n  AND ".join(where),
            "GROUP BY " + ", ".join(group_by),
            "ORDER BY " + ", ".join(group_by),
        ]
    )
    return CompiledQuery(
        operation="SegmentTurnover" if by_segment else "EligibleTurnover",
        sql=sql,
        params=tuple(params),
        metric_ids=(metric.id,),
        mapping_ids=tuple(dict.fromkeys(mapping_ids)),
        source_ids=tuple(dict.fromkeys(source_ids)),
    )


def compile_trading_days(package: OntologyPackage, periods: tuple[str, ...]) -> CompiledQuery:
    if not periods:
        raise QueryCompilationError("At least one explicit period is required")
    metric = next(item for item in package.metrics if item.id == "metric.trading_day_count")
    if not metric.query.base_source or not metric.query.measure_property or not metric.query.period_property:
        raise QueryCompilationError("Trading-day metric is missing its query contract")
    aliases, joins, source_ids = _query_context(
        package, metric.query.base_source, list(metric.query.required_joins)
    )
    if joins:
        raise QueryCompilationError("Reference trading-day metric must not depend on a fact-table join")
    bindings = _binding_map(package)
    measure = bindings[metric.query.measure_property]
    period = bindings[metric.query.period_property]
    source = next(item for item in package.data_sources if item.id == metric.query.base_source)
    table = next(item for item in source.tables if item.name == measure.table)

    scope_sql, params, scope_mapping_ids = _period_and_population_scope(
        package, periods, metric.query, bindings, aliases
    )
    where = [scope_sql]
    mapping_ids = [measure.id, period.id, *scope_mapping_ids]
    for rule in _rules(package, metric.query.filters):
        for condition in rule.all:
            sql, condition_params, binding_id = _condition_sql(condition, bindings, aliases)
            where.append(sql)
            params.extend(condition_params)
            mapping_ids.append(binding_id)

    if metric.formula.op != "count_distinct":
        raise QueryCompilationError(
            f"ADT calendar adapter requires count_distinct(field_ref); got {metric.formula.op}"
        )
    sql = "\n".join(
        [
            "SELECT",
            f"  b.{quote_identifier(period.column)} AS period_id,",
            f"  COUNT(DISTINCT b.{quote_identifier(measure.column)}) AS trading_day_count",
            f"FROM {quote_identifier(table.name)} AS b",
            "WHERE " + "\n  AND ".join(where),
            "GROUP BY period_id",
            "ORDER BY period_id",
        ]
    )
    return CompiledQuery(
        operation="TradingDayCount",
        sql=sql,
        params=tuple(params),
        metric_ids=(metric.id,),
        mapping_ids=tuple(dict.fromkeys(mapping_ids)),
        source_ids=tuple(source_ids),
    )


class DuckDBContext:
    def __init__(self, package: OntologyPackage, resource_paths: Mapping[str, Path]):
        self.package = package
        self.resource_paths = {
            source_id: path.resolve() for source_id, path in resource_paths.items()
        }
        self.connection = duckdb.connect(":memory:")
        self._register_sources()

    def _register_sources(self) -> None:
        duckdb_types = {
            "string": "VARCHAR",
            "integer": "BIGINT",
            "decimal": "DECIMAL(38, 6)",
            "boolean": "BOOLEAN",
            "date": "DATE",
            "datetime": "TIMESTAMP",
        }
        for source in self.package.data_sources:
            path = self.resource_paths.get(source.id)
            if path is None or not path.is_file():
                raise QueryCompilationError(
                    f"No resolved CSV resource is available for {source.id}"
                )
            if len(source.tables) != 1:
                raise QueryCompilationError(f"CSV source {source.id} must declare exactly one table")
            table = source.tables[0]
            table_name = quote_identifier(table.name)
            columns = "{" + ", ".join(
                f"{_sql_literal(field.name)}: {_sql_literal(duckdb_types[field.data_type])}"
                for field in table.fields
            ) + "}"
            self.connection.execute(
                f"CREATE VIEW {table_name} AS SELECT * FROM read_csv("
                f"{_sql_literal(str(path))}, header=true, columns={columns})"
            )

    def execute(self, query: CompiledQuery) -> list[dict[str, Any]]:
        cursor = self.connection.execute(query.sql, list(query.params))
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> DuckDBContext:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
