from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

from .io import package_checksum
from .language_policy import package_language_violations
from .metric_semantics import canonical_unit, infer_formula_unit, units_compatible
from .models import (
    FormulaNode,
    OntologyPackage,
    Status,
    ValidationCheck,
    ValidationReport,
)
from .rdf_projection import validate_graph
from .scenario import default_scenario_adapters


def _check(check_id: str, category: str, passed: bool, message: str, **details: object) -> ValidationCheck:
    return ValidationCheck(
        check_id=check_id,
        category=category,
        status="PASS" if passed else "FAIL",
        message=message,
        details=details,
    )


def _formula_refs(node: FormulaNode, operation: str) -> set[str]:
    refs = {node.ref} if node.op == operation and node.ref else set()
    for child in node.args:
        refs.update(_formula_refs(child, operation))
    return refs


def _formula_operations(node: FormulaNode) -> set[str]:
    operations = {node.op}
    for child in node.args:
        operations.update(_formula_operations(child))
    return operations


def _formula_tautologies(node: FormulaNode, path: str = "formula") -> list[str]:
    defects: list[str] = []
    if (
        node.op == "divide"
        and len(node.args) == 2
        and node.args[0].model_dump(mode="json")
        == node.args[1].model_dump(mode="json")
    ):
        defects.append(
            f"{path}: numerator and denominator are the same expression"
        )
    for index, child in enumerate(node.args):
        defects.extend(_formula_tautologies(child, f"{path}.args[{index}]"))
    return defects


def _metric_cycles(package: OntologyPackage) -> list[list[str]]:
    dependencies = {
        metric.id: _formula_refs(metric.formula, "metric_ref") for metric in package.metrics
    }
    cycles: list[list[str]] = []
    visiting: list[str] = []
    visited: set[str] = set()

    def visit(metric_id: str) -> None:
        if metric_id in visiting:
            start = visiting.index(metric_id)
            cycles.append([*visiting[start:], metric_id])
            return
        if metric_id in visited:
            return
        visiting.append(metric_id)
        for dependency in dependencies.get(metric_id, set()):
            visit(dependency)
        visiting.pop()
        visited.add(metric_id)

    for metric_id in dependencies:
        visit(metric_id)
    return cycles


def _formula_type_defects(package: OntologyPackage) -> dict[str, list[str]]:
    """Return deterministic formula defects without trying to infer business truth.

    The validator owns the mechanical boundary: arithmetic operators require numeric
    operands.  It deliberately does not decide whether a business formula is the
    *right* formula; that remains an evidence and human-review concern.
    """

    property_types = {item.id: item.data_type for item in package.properties}
    metric_types = {item.id: item.value_type for item in package.metrics}
    numeric = {"integer", "decimal", "percentage"}
    defects: dict[str, list[str]] = {}

    def infer(metric_id: str, node: FormulaNode, path: str) -> str | None:
        if node.op == "field_ref":
            return property_types.get(node.ref or "")
        if node.op == "metric_ref":
            return metric_types.get(node.ref or "")
        if node.op == "literal":
            return "decimal"

        child_types = [
            infer(metric_id, child, f"{path}.args[{index}]")
            for index, child in enumerate(node.args)
        ]
        if node.op == "count_distinct":
            return "integer"
        if node.op == "duration_ms":
            invalid = sorted(
                {item for item in child_types if item is not None and item != "datetime"}
            )
            if invalid:
                defects.setdefault(metric_id, []).append(
                    f"{path}: duration_ms requires datetime operands, got "
                    + ", ".join(invalid)
                )
            return "integer"
        if node.op == "sum":
            child_type = child_types[0] if child_types else None
            if child_type is not None and child_type not in numeric:
                defects.setdefault(metric_id, []).append(
                    f"{path}: sum requires a numeric operand, got {child_type}"
                )
            return child_type
        if node.op in {"add", "subtract", "multiply", "divide"}:
            invalid = sorted(
                {item for item in child_types if item is not None and item not in numeric}
            )
            if invalid:
                defects.setdefault(metric_id, []).append(
                    f"{path}: {node.op} requires numeric operands, got "
                    + ", ".join(invalid)
                )
            if node.op == "divide" or any(
                item in {"decimal", "percentage"} for item in child_types
            ):
                return "decimal"
            return "integer" if child_types else None
        return None

    for metric in package.metrics:
        infer(metric.id, metric.formula, "formula")
    return defects


def _static_checks(package: OntologyPackage) -> list[ValidationCheck]:
    checks: list[ValidationCheck] = []
    objects = package.governed_objects()
    object_ids = [item.id for item in objects]
    source_ids = {item.id for item in package.sources}
    decision_ids = {item.id for item in package.decisions}
    actor_ids = {item.id for item in package.actors}
    entity_ids = {item.id for item in package.entities}
    property_ids = {item.id for item in package.properties}
    dimension_ids = {item.id for item in package.dimensions}
    rule_ids = {item.id for item in package.rules}
    metric_ids = {item.id for item in package.metrics}
    data_source_ids = {item.id for item in package.data_sources}
    analysis_ids = {item.id for item in package.analysis_patterns}
    binding_targets = {item.logical_target for item in package.bindings}
    join_ids = {item.id for item in package.joins}
    role_ids = {role for actor in package.actors for role in actor.roles}

    checks.append(
        _check(
            "PACKAGE_STATUS",
            "source",
            package.status is Status.CONFIRMED,
            "Draft package is confirmed before publication",
            status=package.status.value,
        )
    )

    language_violations = package_language_violations(package)
    checks.append(
        _check(
            "AUTHORING_LANGUAGE_POLICY",
            "semantic",
            not language_violations,
            "Human-readable ontology content follows the Solution authoring language",
            authoring_language=(
                package.authoring_policy.authoring_language
                if package.authoring_policy is not None
                else None
            ),
            violations=language_violations,
        )
    )

    ordered_periods = sorted(package.scenario.periods, key=lambda period: period.start)
    period_defects: list[str] = []
    window_start = package.scenario.data_window_start
    window_end = package.scenario.data_window_end
    if (window_start is None) != (window_end is None):
        period_defects.append("data window must provide both start and end")
    if window_start is not None and window_end is not None and window_start > window_end:
        period_defects.append("data window start is after end")
    if ordered_periods and (window_start is None or window_end is None):
        period_defects.append("periods require a scenario data window")
    if len({period.id for period in ordered_periods}) != len(ordered_periods):
        period_defects.append("duplicate period IDs")
    for index, period in enumerate(ordered_periods):
        if period.start > period.end:
            period_defects.append(f"{period.id}: start is after end")
        if (
            window_start is not None
            and window_end is not None
            and (period.start < window_start or period.end > window_end)
        ):
            period_defects.append(f"{period.id}: outside scenario data window")
        if index and period.start <= ordered_periods[index - 1].end:
            period_defects.append(
                f"{ordered_periods[index - 1].id}/{period.id}: periods overlap"
            )
    checks.append(
        _check(
            "SCENARIO_PERIODS",
            "semantic",
            not period_defects,
            "Scenario periods are unique, valid, non-overlapping and inside the data window",
            defects=period_defects,
        )
    )

    duplicates = sorted(identifier for identifier, count in Counter(object_ids).items() if count > 1)
    checks.append(_check("UNIQUE_IDS", "structure", not duplicates, "All governed object IDs are unique", duplicates=duplicates))

    source_reference_defects = {
        item.id: sorted(source for source in item.sources if source not in source_ids)
        for item in objects
        if any(source not in source_ids for source in item.sources)
    }
    missing_sources = sorted(
        {
            source
            for invalid in source_reference_defects.values()
            for source in invalid
        }
    )
    checks.append(
        _check(
            "SOURCE_REFERENCES",
            "source",
            not missing_sources,
            "Every governed object points to a registered ontology source ID",
            missing=missing_sources,
            by_object=source_reference_defects,
            expected_reference_type="sources[].id (ontology package source ID, not source-version ID)",
            registered_source_ids=sorted(source_ids),
        )
    )

    missing_decisions = sorted(
        {decision for item in objects for decision in item.decisions if decision not in decision_ids}
    )
    checks.append(_check("DECISION_REFERENCES", "source", not missing_decisions, "Every decision reference resolves", missing=missing_decisions))

    invalid_decisions: dict[str, list[str]] = {}
    governed_ids = set(object_ids)
    for decision in package.decisions:
        missing: list[str] = []
        if decision.decided_by not in actor_ids:
            missing.append(decision.decided_by)
        missing.extend(reference for reference in decision.affects if reference not in governed_ids)
        if missing:
            invalid_decisions[decision.id] = sorted(set(missing))
    checks.append(
        _check(
            "DECISION_REFERENCE_CLOSURE",
            "source",
            not invalid_decisions,
            "Decision actors and affected governed objects resolve",
            invalid=invalid_decisions,
        )
    )

    governed_assets = tuple(item for item in objects if item is not package.scenario)
    invalid_owners = sorted(
        {item.owner for item in governed_assets if item.owner not in actor_ids}
    )
    checks.append(
        _check(
            "OWNER_REFERENCES",
            "source",
            not invalid_owners,
            "Every governed asset has a registered accountable actor",
            missing=invalid_owners,
        )
    )

    invalid_processes: dict[str, list[str]] = {}
    for process in package.processes:
        missing = [step.actor for step in process.steps if step.actor not in actor_ids]
        missing.extend(
            reference
            for step in process.steps
            for reference in step.governed_refs
            if reference not in governed_ids
        )
        if missing:
            invalid_processes[process.id] = sorted(set(missing))
    checks.append(
        _check(
            "PROCESS_REFERENCE_CLOSURE",
            "semantic",
            not invalid_processes,
            "Process actors and governed references resolve",
            invalid=invalid_processes,
        )
    )

    invalid_process_steps: dict[str, list[str]] = {}
    for process in package.processes:
        duplicates = sorted(
            step_id
            for step_id, count in Counter(step.id for step in process.steps).items()
            if count > 1
        )
        if duplicates:
            invalid_process_steps[process.id] = duplicates
    checks.append(
        _check(
            "PROCESS_STEP_INTEGRITY",
            "semantic",
            not invalid_process_steps,
            "Process step identities are unique within each process",
            duplicates=invalid_process_steps,
        )
    )

    unpublished_status = sorted(
        item.id for item in objects if item.status is not Status.CONFIRMED
    )
    checks.append(_check("CONFIRMED_ONLY", "source", not unpublished_status, "Every publishable object is confirmed", invalid=unpublished_status))

    invalid_properties = sorted(prop.id for prop in package.properties if prop.entity not in entity_ids)
    invalid_relationships = sorted(
        rel.id
        for rel in package.relationships
        if rel.from_entity not in entity_ids or rel.to_entity not in entity_ids
    )
    property_map = {item.id: item for item in package.properties}
    invalid_dimensions: dict[str, list[str]] = {}
    for dimension in package.dimensions:
        defects: list[str] = []
        if dimension.entity not in entity_ids:
            defects.append(f"unknown entity: {dimension.entity}")
        for role, property_id in (
            ("key", dimension.key_property),
            ("label", dimension.label_property),
        ):
            prop = property_map.get(property_id)
            if prop is None:
                defects.append(f"unknown {role} property: {property_id}")
            elif prop.entity != dimension.entity:
                defects.append(
                    f"{role} property {property_id} belongs to {prop.entity}"
                )
        if defects:
            invalid_dimensions[dimension.id] = defects
    checks.append(
        _check(
            "BUSINESS_REFERENCE_CLOSURE",
            "semantic",
            not (invalid_properties or invalid_relationships or invalid_dimensions),
            "Entity, property, relationship and dimension references close",
            properties=invalid_properties,
            relationships=invalid_relationships,
            dimensions=invalid_dimensions,
        )
    )

    invalid_entity_keys: dict[str, str] = {}
    for entity in package.entities:
        defects: list[str] = []
        for key_id in entity.primary_key_properties():
            primary_key = property_map.get(key_id)
            if primary_key is None:
                defects.append(f"unknown primary key property: {key_id}")
            elif primary_key.entity != entity.id:
                defects.append(
                    f"primary key property {key_id} belongs to {primary_key.entity}"
                )
        if defects:
            invalid_entity_keys[entity.id] = "; ".join(defects)
    checks.append(
        _check(
            "ENTITY_KEY_CLOSURE",
            "semantic",
            not invalid_entity_keys,
            "Every entity primary-key component resolves to one of its own properties",
            invalid=invalid_entity_keys,
        )
    )

    invalid_rule_conditions: dict[str, list[str]] = {}
    invalid_rule_semantics: dict[str, list[str]] = {}
    for rule in package.rules:
        missing: list[str] = []
        defects: list[str] = []
        for condition in rule.all:
            if condition.property not in property_ids:
                missing.append(condition.property)
            if condition.op in {"eq_property", "neq_property"}:
                target = str(condition.value)
                if target not in property_ids:
                    missing.append(target)
                left = property_map.get(condition.property)
                right = property_map.get(target)
                if left is not None and right is not None and not (
                    left.data_type == right.data_type
                    or {left.data_type, right.data_type} == {"string", "enum"}
                ):
                    defects.append(
                        f"{condition.property} cannot be compared with {target}: "
                        f"{left.data_type} != {right.data_type}"
                    )
            elif (
                condition.op in {"eq", "neq"}
                and isinstance(condition.value, str)
                and condition.value in property_ids
            ):
                defects.append(
                    f"{condition.property} compares a property id as a literal; "
                    "use eq_property or neq_property"
                )
        if missing:
            invalid_rule_conditions[rule.id] = sorted(set(missing))
        if defects:
            invalid_rule_semantics[rule.id] = defects
    checks.append(_check("RULE_REFERENCE_CLOSURE", "semantic", not invalid_rule_conditions, "Rule conditions reference known properties", invalid=invalid_rule_conditions))
    checks.append(
        _check(
            "RULE_CONDITION_SEMANTICS",
            "semantic",
            not invalid_rule_semantics,
            "Rule conditions distinguish governed property comparisons from literal comparisons",
            invalid=invalid_rule_semantics,
        )
    )

    cycles = _metric_cycles(package)
    checks.append(
        _check(
            "METRIC_DEPENDENCY_DAG",
            "semantic",
            not cycles,
            "Metric dependencies form an acyclic graph",
            cycles=cycles,
        )
    )

    invalid_metrics: dict[str, list[str]] = {}
    metric_reference_defects: dict[str, dict[str, list[str]]] = {}
    for metric in package.metrics:
        defects: dict[str, list[str]] = {}
        if metric.base_entity not in entity_ids:
            defects["unknown_base_entity"] = [metric.base_entity]
        result_grain = sorted(
            ref for ref in metric.result_grain if ref not in dimension_ids
        )
        if result_grain:
            defects["unknown_result_grain_dimensions"] = result_grain
        allowed_dimensions = sorted(
            ref for ref in metric.allowed_dimensions if ref not in dimension_ids
        )
        if allowed_dimensions:
            defects["unknown_allowed_dimensions"] = allowed_dimensions
        filters = sorted(ref for ref in metric.query.filters if ref not in rule_ids)
        if filters:
            defects["unknown_filter_rules"] = filters
        required_joins = sorted(
            ref for ref in metric.query.required_joins if ref not in join_ids
        )
        if required_joins:
            defects["unknown_required_joins"] = required_joins
        metric_refs = sorted(
            ref
            for ref in _formula_refs(metric.formula, "metric_ref")
            if ref not in metric_ids
        )
        if metric_refs:
            defects["unknown_formula_metric_refs"] = metric_refs
        field_refs = sorted(
            ref
            for ref in _formula_refs(metric.formula, "field_ref")
            if ref not in property_ids
        )
        if field_refs:
            defects["unknown_formula_field_refs"] = field_refs
        if metric.metric_type == "base" and metric.query.measure_property not in property_ids:
            defects["unknown_query_measure_property"] = [
                str(metric.query.measure_property)
            ]
        if (
            metric.metric_type == "base"
            and metric.query.period_property
            and metric.query.period_property not in property_ids
        ):
            defects["unknown_query_period_property"] = [
                str(metric.query.period_property)
            ]
        if metric.metric_type == "base" and metric.query.date_property not in property_ids:
            defects["unknown_query_date_property"] = [
                str(metric.query.date_property)
            ]
        if (
            metric.metric_type == "base"
            and metric.query.population_property
            and metric.query.population_property not in property_ids
        ):
            defects["unknown_query_population_property"] = [
                str(metric.query.population_property)
            ]
        if (
            metric.metric_type == "base"
            and metric.query.population_rule
            and metric.query.population_rule not in rule_ids
        ):
            defects["unknown_query_population_rule"] = [
                str(metric.query.population_rule)
            ]
        if metric.metric_type == "base" and metric.query.base_source not in data_source_ids:
            defects["unknown_query_base_source"] = [str(metric.query.base_source)]
        if defects:
            metric_reference_defects[metric.id] = defects
            invalid_metrics[metric.id] = sorted(
                {
                    reference
                    for references in defects.values()
                    for reference in references
                }
            )
    checks.append(
        _check(
            "METRIC_REFERENCE_CLOSURE",
            "semantic",
            not invalid_metrics,
            "Metric references resolve against the collection required by each field",
            invalid=invalid_metrics,
            by_metric=metric_reference_defects,
            expected_reference_types={
                "base_entity": "entities[].id",
                "result_grain": "dimensions[].id",
                "allowed_dimensions": "dimensions[].id",
                "query.filters": "rules[].id",
                "query.required_joins": "joins[].id",
                "formula.metric_ref": "metrics[].id",
                "formula.field_ref": "properties[].id",
                "query.*_property": "properties[].id",
                "query.population_rule": "rules[].id",
                "query.base_source": "data_sources[].id",
            },
            registered_ids={
                "entities": sorted(entity_ids),
                "dimensions": sorted(dimension_ids),
                "properties": sorted(property_ids),
                "rules": sorted(rule_ids),
                "metrics": sorted(metric_ids),
                "data_sources": sorted(data_source_ids),
                "joins": sorted(join_ids),
            },
        )
    )

    inconsistent_queries: dict[str, list[str]] = {}
    for metric in package.metrics:
        issues: list[str] = []
        field_refs = _formula_refs(metric.formula, "field_ref")
        if metric.metric_type == "base":
            if metric.query.measure_property not in field_refs:
                issues.append("query measure is not referenced by formula")
            if not metric.query.date_property:
                issues.append("date property is missing")
        elif any(
            value
            for value in (
                metric.query.base_source,
                metric.query.measure_property,
                metric.query.period_property,
                metric.query.date_property,
                metric.query.population_property,
                metric.query.population_rule,
                metric.query.required_joins,
                metric.query.filters,
            )
        ):
            issues.append("derived metric unexpectedly contains a physical query contract")
        if issues:
            inconsistent_queries[metric.id] = issues
    checks.append(
        _check(
            "METRIC_QUERY_CONSISTENCY",
            "semantic",
            not inconsistent_queries,
            "Metric formula and physical query responsibilities are consistent",
            invalid=inconsistent_queries,
        )
    )

    invalid_metric_time: dict[str, list[str]] = {}
    for metric in package.metrics:
        if metric.metric_type != "base":
            continue
        defects: list[str] = []
        date_property = property_map.get(metric.query.date_property or "")
        period_property = property_map.get(metric.query.period_property or "")
        if date_property and date_property.data_type not in {"date", "datetime"}:
            defects.append(
                f"date property {date_property.id} has type {date_property.data_type}"
            )
        if period_property and period_property.data_type not in {
            "string",
            "enum",
            "date",
            "datetime",
        }:
            defects.append(
                f"period property {period_property.id} has type {period_property.data_type}"
            )
        if defects:
            invalid_metric_time[metric.id] = defects
    checks.append(
        _check(
            "METRIC_TIME_SEMANTICS",
            "semantic",
            not invalid_metric_time,
            "Metric date and period properties use compatible semantic types",
            invalid=invalid_metric_time,
        )
    )

    invalid_metric_population: dict[str, list[str]] = {}
    for metric in package.metrics:
        if metric.metric_type != "base":
            continue
        if metric.status != Status.PROPOSED:
            continue
        population_property_id = metric.query.population_property
        population_rule_id = metric.query.population_rule
        defects: list[str] = []
        if bool(population_property_id) == bool(population_rule_id):
            defects.append(
                "exactly one of population_property or population_rule is required"
            )
        population_property = property_map.get(population_property_id or "")
        if population_property is not None and population_property.data_type != "boolean":
            defects.append(
                f"population property {population_property.id} has type "
                f"{population_property.data_type}; a newly authored physical "
                "population property must be boolean"
            )
        if defects:
            invalid_metric_population[metric.id] = defects
    checks.append(
        _check(
            "METRIC_POPULATION_SEMANTICS",
            "semantic",
            not invalid_metric_population,
            "New base metrics use one executable population property or rule",
            invalid=invalid_metric_population,
            compatibility=(
                "Confirmed legacy metrics may retain a non-boolean market-scope "
                "property. A new Candidate uses either an evidenced boolean property "
                "or a governed Rule; it must not invent a physical eligibility column."
            ),
        )
    )

    metric_map = {item.id: item for item in package.metrics}
    invalid_metric_units: dict[str, list[str]] = {}
    for metric in package.metrics:
        defects: list[str] = []
        measure = property_map.get(metric.query.measure_property or "")
        if (
            metric.metric_type == "base"
            and metric.formula.op != "count_distinct"
            and measure is not None
            and measure.unit
            and metric.unit
            and not units_compatible(measure.unit, metric.unit)
        ):
            defects.append(
                f"measure unit {measure.unit} does not match metric unit {metric.unit}"
            )

        def check_formula(node: FormulaNode) -> None:
            if node.op in {"add", "subtract"}:
                operand_units = {
                    canonical_unit(metric_map[child.ref].unit)
                    for child in node.args
                    if child.op == "metric_ref" and child.ref in metric_map
                }
                if len(operand_units) > 1:
                    defects.append(
                        f"{node.op} operands have incompatible units: "
                        + ", ".join(sorted(operand_units))
                    )
            for child in node.args:
                check_formula(child)

        check_formula(metric.formula)
        inferred_unit = infer_formula_unit(
            metric.formula,
            metrics=metric_map,
            properties=property_map,
        )
        if (
            metric.status == Status.PROPOSED
            and metric.metric_type == "derived"
            and inferred_unit is not None
            and not units_compatible(inferred_unit, metric.unit)
        ):
            defects.append(
                f"formula unit {inferred_unit} does not match declared unit "
                f"{canonical_unit(metric.unit) or metric.unit}"
            )
        if defects:
            invalid_metric_units[metric.id] = defects
    checks.append(
        _check(
            "METRIC_UNIT_COMPATIBILITY",
            "semantic",
            not invalid_metric_units,
            "Metric formulas preserve explicit unit compatibility",
            invalid=invalid_metric_units,
        )
    )

    formula_type_defects = _formula_type_defects(package)
    checks.append(
        _check(
            "METRIC_FORMULA_TYPE_COMPATIBILITY",
            "semantic",
            not formula_type_defects,
            "Metric arithmetic operators receive mechanically compatible value types",
            invalid=formula_type_defects,
        )
    )

    formula_layering_defects: dict[str, list[str]] = {}
    for metric in package.metrics:
        operations = _formula_operations(metric.formula)
        defects: list[str] = []
        if metric.metric_type == "derived":
            hidden_physical = sorted(
                operations.intersection(
                    {"field_ref", "sum", "count_distinct", "duration_ms"}
                )
            )
            if hidden_physical:
                defects.append(
                    "derived metric embeds physical aggregation instead of "
                    "composing governed base metrics: " + ", ".join(hidden_physical)
                )
        elif "metric_ref" in operations:
            defects.append("base metric depends on another metric")
        if defects:
            formula_layering_defects[metric.id] = defects
    checks.append(
        _check(
            "METRIC_FORMULA_LAYERING",
            "semantic",
            not formula_layering_defects,
            "Base metrics own physical aggregation and derived metrics compose governed metric references",
            invalid=formula_layering_defects,
        )
    )

    formula_tautology_defects = {
        metric.id: defects
        for metric in package.metrics
        if (defects := _formula_tautologies(metric.formula))
    }
    checks.append(
        _check(
            "METRIC_FORMULA_TAUTOLOGY",
            "semantic",
            not formula_tautology_defects,
            "Metric division does not use an identical numerator and denominator",
            invalid=formula_tautology_defects,
        )
    )

    required_binding_targets = {
        reference
        for metric in package.metrics
        if metric.metric_type == "base"
        for reference in (
            metric.query.measure_property,
            metric.query.period_property,
            metric.query.date_property,
            metric.query.population_property,
        )
        if reference
    }
    required_binding_targets.update(
        condition.property for rule in package.rules for condition in rule.all
    )
    missing_bindings = sorted(required_binding_targets - binding_targets)
    checks.append(_check("METRIC_BINDING_CLOSURE", "binding", not missing_bindings, "Every executable measure, period and rule property has a physical binding", missing=missing_bindings))

    duplicate_binding_targets = sorted(
        target for target, count in Counter(item.logical_target for item in package.bindings).items() if count > 1
    )
    checks.append(
        _check(
            "UNIQUE_LOGICAL_BINDINGS",
            "binding",
            not duplicate_binding_targets,
            "Each logical target has one active physical binding in this environment",
            duplicates=duplicate_binding_targets,
        )
    )

    source_map = {source.id: source for source in package.data_sources}
    invalid_source_schemas: dict[str, list[str]] = {}
    for source in package.data_sources:
        defects: list[str] = []
        duplicate_tables = sorted(
            table_name
            for table_name, count in Counter(
                table.name for table in source.tables
            ).items()
            if count > 1
        )
        defects.extend(f"duplicate table: {name}" for name in duplicate_tables)
        for table in source.tables:
            field_map = {field.name: field for field in table.fields}
            duplicate_fields = sorted(
                field_name
                for field_name, count in Counter(
                    field.name for field in table.fields
                ).items()
                if count > 1
            )
            defects.extend(
                f"{table.name}: duplicate field {name}" for name in duplicate_fields
            )
            for key in table.primary_key:
                field = field_map.get(key)
                if field is None:
                    defects.append(f"{table.name}: unknown primary-key field {key}")
                elif field.nullable:
                    defects.append(f"{table.name}: primary-key field {key} is nullable")
        if defects:
            invalid_source_schemas[source.id] = defects
    checks.append(
        _check(
            "DATA_SOURCE_SCHEMA_INTEGRITY",
            "data",
            not invalid_source_schemas,
            "Physical schemas have unique tables and fields with valid primary keys",
            invalid=invalid_source_schemas,
        )
    )

    invalid_bindings: dict[str, str] = {}
    incompatible_logical_bindings: dict[str, str] = {}
    allowed_generic_transformations = {
        "identity",
        "yn_to_boolean",
        "yn_to_boolean_not",
    }
    for binding in package.bindings:
        source = source_map.get(binding.source)
        if source is None:
            invalid_bindings[binding.id] = "unknown source"
            continue
        if (
            binding.status == Status.PROPOSED
            and binding.transformation not in allowed_generic_transformations
        ):
            invalid_bindings[binding.id] = (
                "new Candidate binding uses an unregistered transformation: "
                + binding.transformation
            )
            continue
        table = next((table for table in source.tables if table.name == binding.table), None)
        field = next((field for field in table.fields if field.name == binding.column), None) if table else None
        if table is None:
            invalid_bindings[binding.id] = "unknown table"
        elif field is None:
            invalid_bindings[binding.id] = "unknown column"
        elif binding.transformation == "identity" and field.data_type != binding.data_type:
            invalid_bindings[binding.id] = f"type mismatch: {field.data_type} != {binding.data_type}"
        elif binding.transformation in {"yn_to_boolean", "yn_to_boolean_not"} and not (
            field.data_type == "string" and binding.data_type == "boolean"
        ):
            invalid_bindings[binding.id] = (
                f"{binding.transformation} requires string physical input and "
                f"boolean logical output, got {field.data_type} -> {binding.data_type}"
            )
        elif (
            binding.transformation not in {"identity", "yn_to_boolean", "yn_to_boolean_not"}
            and field.data_type != binding.data_type
        ):
            invalid_bindings[binding.id] = (
                f"certified transformation output type mismatch: "
                f"{field.data_type} != {binding.data_type}"
            )
        elif binding.unit and field.unit and binding.unit != field.unit:
            invalid_bindings[binding.id] = f"unit mismatch: {field.unit} != {binding.unit}"
        logical = property_map.get(binding.logical_target)
        if logical is None:
            incompatible_logical_bindings[binding.id] = "unknown logical property"
        elif logical.data_type != binding.data_type and not (
            logical.data_type == "enum" and binding.data_type == "string"
        ):
            incompatible_logical_bindings[binding.id] = (
                f"logical type mismatch: {logical.data_type} != {binding.data_type}"
            )
        elif logical.unit and binding.unit and logical.unit != binding.unit:
            incompatible_logical_bindings[binding.id] = (
                f"logical unit mismatch: {logical.unit} != {binding.unit}"
            )
    checks.append(_check("PHYSICAL_BINDINGS", "binding", not invalid_bindings, "Bindings resolve to schema-compatible fields", invalid=invalid_bindings))
    checks.append(
        _check(
            "LOGICAL_BINDING_COMPATIBILITY",
            "binding",
            not incompatible_logical_bindings,
            "Bindings preserve logical property types and units",
            invalid=incompatible_logical_bindings,
        )
    )

    invalid_joins: dict[str, list[str]] = {}
    join_type_mismatches: dict[str, list[str]] = {}
    for join in package.joins:
        missing: list[str] = []
        mismatches: list[str] = []
        for key in join.keys:
            resolved_fields = []
            for source_id, table_name, column_name in [
                (join.left_source, join.left_table, key.left_column),
                (join.right_source, join.right_table, key.right_column),
            ]:
                source = source_map.get(source_id)
                table = next((item for item in source.tables if item.name == table_name), None) if source else None
                field = next((item for item in table.fields if item.name == column_name), None) if table else None
                if not field:
                    missing.append(f"{source_id}.{table_name}.{column_name}")
                else:
                    resolved_fields.append(field)
            if len(resolved_fields) == 2 and resolved_fields[0].data_type != resolved_fields[1].data_type:
                mismatches.append(
                    f"{key.left_column}:{resolved_fields[0].data_type} != "
                    f"{key.right_column}:{resolved_fields[1].data_type}"
                )
        if missing:
            invalid_joins[join.id] = missing
        if mismatches:
            join_type_mismatches[join.id] = mismatches
    checks.append(_check("JOIN_SCHEMA_CLOSURE", "binding", not invalid_joins, "Join contracts reference known fields", invalid=invalid_joins))
    checks.append(
        _check(
            "JOIN_TYPE_COMPATIBILITY",
            "binding",
            not join_type_mismatches,
            "Join-key physical types are compatible",
            invalid=join_type_mismatches,
        )
    )

    implementable_ids = metric_ids | rule_ids | analysis_ids
    invalid_sql_contracts: dict[str, list[str]] = {}
    for contract in package.sql_contracts:
        defects: list[str] = []
        if contract.statement_source not in source_ids:
            defects.append(f"unknown statement source: {contract.statement_source}")
        input_identities: list[str] = []
        for relation in contract.inputs:
            source = source_map.get(relation.source)
            table = (
                next(
                    (item for item in source.tables if item.name == relation.table),
                    None,
                )
                if source
                else None
            )
            if source is None:
                defects.append(f"unknown input source: {relation.source}")
            elif table is None:
                defects.append(
                    f"unknown input table: {relation.source}.{relation.table}"
                )
            input_identities.append(
                relation.alias or f"{relation.source}.{relation.table}"
            )
        duplicate_inputs = sorted(
            identity
            for identity, count in Counter(input_identities).items()
            if count > 1
        )
        if duplicate_inputs:
            defects.append("duplicate input aliases: " + ", ".join(duplicate_inputs))
        duplicate_outputs = sorted(
            field
            for field, count in Counter(contract.output_fields).items()
            if count > 1
        )
        if duplicate_outputs:
            defects.append("duplicate output fields: " + ", ".join(duplicate_outputs))
        duplicate_parameters = sorted(
            name
            for name, count in Counter(
                parameter.name for parameter in contract.parameters
            ).items()
            if count > 1
        )
        if duplicate_parameters:
            defects.append(
                "duplicate parameters: " + ", ".join(duplicate_parameters)
            )
        missing_implements = sorted(set(contract.implements) - implementable_ids)
        if missing_implements:
            defects.append("unknown implemented assets: " + ", ".join(missing_implements))
        if contract.execution_mode != "reference_only":
            if not contract.inputs:
                defects.append("executable SQL contract has no declared input")
            if not contract.output_fields:
                defects.append("executable SQL contract has no declared output")
            if not contract.implements:
                defects.append("executable SQL contract implements no governed asset")
        if defects:
            invalid_sql_contracts[contract.id] = defects
    checks.append(
        _check(
            "SQL_CONTRACT_CLOSURE",
            "binding",
            not invalid_sql_contracts,
            "SQL contracts resolve exact statements, physical inputs and governed outputs",
            invalid=invalid_sql_contracts,
        )
    )

    invalid_analyses: dict[str, list[str]] = {}
    for pattern in package.analysis_patterns:
        missing = [ref for ref in pattern.required_metrics if ref not in metric_ids]
        missing.extend(ref for ref in pattern.required_dimensions if ref not in dimension_ids)
        if missing:
            invalid_analyses[pattern.id] = sorted(set(missing))
    checks.append(_check("ANALYSIS_CAPABILITY_CLOSURE", "semantic", not invalid_analyses, "Analysis patterns reference available metrics and dimensions", invalid=invalid_analyses))

    invalid_questions = sorted(
        question.id for question in package.questions if question.analysis_pattern not in analysis_ids
    )
    checks.append(_check("QUESTION_CAPABILITY_CLOSURE", "semantic", not invalid_questions, "Competency questions bind to registered analysis patterns", invalid=invalid_questions))

    invalid_policies: dict[str, list[str]] = {}
    for policy in package.policies:
        defects: list[str] = []
        overlap = sorted(set(policy.allowed_roles) & set(policy.denied_roles))
        if overlap:
            defects.append(f"roles are both allowed and denied: {', '.join(overlap)}")
        unknown_roles = sorted(
            (set(policy.allowed_roles) | set(policy.denied_roles)) - role_ids
        )
        if unknown_roles:
            defects.append(f"unknown roles: {', '.join(unknown_roles)}")
        if not policy.allowed_roles:
            defects.append("no role is explicitly allowed")
        if not policy.allowed_grains:
            defects.append("no disclosure grain is explicitly allowed")
        if defects:
            invalid_policies[policy.id] = defects
    checks.append(
        _check(
            "POLICY_SEMANTICS",
            "semantic",
            not invalid_policies,
            "Access and disclosure policies are non-contradictory and reference known roles",
            invalid=invalid_policies,
        )
    )

    return checks


def _adt_capability_check(package: OntologyPackage) -> ValidationCheck:
    adapter = default_scenario_adapters().resolve("adt-reference", "1.0.0")
    return adapter.validate(package).checks[0]


def _report(package: OntologyPackage, checks: list[ValidationCheck]) -> ValidationReport:
    status = "PASS" if all(check.status != "FAIL" for check in checks) else "FAIL"
    return ValidationReport(
        package_id=package.package_id,
        package_version=package.version,
        package_checksum=package_checksum(package),
        validated_at=datetime.now(UTC),
        status=status,
        checks=tuple(checks),
    )


def validate_semantic_package(package: OntologyPackage) -> ValidationReport:
    """Validate a portable ontology release without an Agent implementation or data."""

    checks = _static_checks(package)
    shacl_check, _, _, _ = validate_graph(package)
    checks.append(shacl_check)
    return _report(package, checks)


_CANDIDATE_EXCLUDED_CHECKS = frozenset({"PACKAGE_STATUS", "CONFIRMED_ONLY"})


def validate_candidate_package(package: OntologyPackage) -> ValidationReport:
    """Validate a prospective Draft without pretending it already has authority.

    Candidate objects are expected to remain ``proposed`` until human review, so
    publication-status checks are intentionally excluded.  Every structural,
    reference, language, binding, SQL, capability and SHACL check still runs.
    """

    checks = [
        check
        for check in _static_checks(package)
        if check.check_id not in _CANDIDATE_EXCLUDED_CHECKS
    ]
    shacl_check, _, _, _ = validate_graph(package, require_confirmed=False)
    checks.append(shacl_check)
    return _report(package, checks)


def validate_package(
    package: OntologyPackage,
    scenario_dir: Path,
    *,
    include_data: bool = True,
) -> ValidationReport:
    checks = _static_checks(package)
    checks.append(_adt_capability_check(package))
    if include_data:
        from .data_validation import run_data_checks

        checks.extend(run_data_checks(package, scenario_dir))
    shacl_check, _, _, _ = validate_graph(package)
    checks.append(shacl_check)
    return _report(package, checks)


def failed_checks(report: ValidationReport) -> Iterable[ValidationCheck]:
    return (check for check in report.checks if check.status == "FAIL")
