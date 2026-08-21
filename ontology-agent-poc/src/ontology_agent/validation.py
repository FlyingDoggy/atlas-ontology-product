from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

from .io import package_checksum
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

    ordered_periods = sorted(package.scenario.periods, key=lambda period: period.start)
    period_defects: list[str] = []
    if len({period.id for period in ordered_periods}) != len(ordered_periods):
        period_defects.append("duplicate period IDs")
    for index, period in enumerate(ordered_periods):
        if period.start > period.end:
            period_defects.append(f"{period.id}: start is after end")
        if (
            period.start < package.scenario.data_window_start
            or period.end > package.scenario.data_window_end
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

    missing_sources = sorted(
        {source for item in objects for source in item.sources if source not in source_ids}
    )
    checks.append(_check("SOURCE_REFERENCES", "source", not missing_sources, "Every governed object points to a registered source", missing=missing_sources))

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

    invalid_owners = sorted({item.owner for item in objects if item.owner not in actor_ids})
    checks.append(_check("OWNER_REFERENCES", "source", not invalid_owners, "Every governed object has a registered accountable actor", missing=invalid_owners))

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
    invalid_dimensions = sorted(
        dim.id
        for dim in package.dimensions
        if dim.entity not in entity_ids
        or dim.key_property not in property_ids
        or dim.label_property not in property_ids
    )
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

    invalid_rule_conditions = sorted(
        rule.id
        for rule in package.rules
        if any(condition.property not in property_ids for condition in rule.all)
    )
    checks.append(_check("RULE_REFERENCE_CLOSURE", "semantic", not invalid_rule_conditions, "Rule conditions reference known properties", invalid=invalid_rule_conditions))

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
    for metric in package.metrics:
        missing: list[str] = []
        if metric.base_entity not in entity_ids:
            missing.append(metric.base_entity)
        missing.extend(ref for ref in metric.result_grain if ref not in dimension_ids)
        missing.extend(ref for ref in metric.allowed_dimensions if ref not in dimension_ids)
        missing.extend(ref for ref in metric.query.filters if ref not in rule_ids)
        missing.extend(ref for ref in metric.query.required_joins if ref not in join_ids)
        missing.extend(ref for ref in _formula_refs(metric.formula, "metric_ref") if ref not in metric_ids)
        missing.extend(ref for ref in _formula_refs(metric.formula, "field_ref") if ref not in property_ids)
        if metric.metric_type == "base" and metric.query.measure_property not in property_ids:
            missing.append(str(metric.query.measure_property))
        if metric.metric_type == "base" and metric.query.period_property not in property_ids:
            missing.append(str(metric.query.period_property))
        if metric.metric_type == "base" and metric.query.date_property not in property_ids:
            missing.append(str(metric.query.date_property))
        if metric.metric_type == "base" and metric.query.population_property not in property_ids:
            missing.append(str(metric.query.population_property))
        if metric.metric_type == "base" and metric.query.base_source not in data_source_ids:
            missing.append(str(metric.query.base_source))
        if missing:
            invalid_metrics[metric.id] = sorted(set(missing))
    checks.append(_check("METRIC_REFERENCE_CLOSURE", "semantic", not invalid_metrics, "Metric formulas, grains, dimensions, rules and sources resolve", invalid=invalid_metrics))

    inconsistent_queries: dict[str, list[str]] = {}
    for metric in package.metrics:
        issues: list[str] = []
        field_refs = _formula_refs(metric.formula, "field_ref")
        if metric.metric_type == "base":
            if metric.query.measure_property not in field_refs:
                issues.append("query measure is not referenced by formula")
            if not metric.query.period_property:
                issues.append("period property is missing")
        elif any(
            value
            for value in (
                metric.query.base_source,
                metric.query.measure_property,
                metric.query.period_property,
                metric.query.date_property,
                metric.query.population_property,
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
    invalid_bindings: dict[str, str] = {}
    for binding in package.bindings:
        source = source_map.get(binding.source)
        if source is None:
            invalid_bindings[binding.id] = "unknown source"
            continue
        table = next((table for table in source.tables if table.name == binding.table), None)
        field = next((field for field in table.fields if field.name == binding.column), None) if table else None
        if table is None:
            invalid_bindings[binding.id] = "unknown table"
        elif field is None:
            invalid_bindings[binding.id] = "unknown column"
        elif field.data_type != binding.data_type:
            invalid_bindings[binding.id] = f"type mismatch: {field.data_type} != {binding.data_type}"
        elif binding.unit and field.unit and binding.unit != field.unit:
            invalid_bindings[binding.id] = f"unit mismatch: {field.unit} != {binding.unit}"
    checks.append(_check("PHYSICAL_BINDINGS", "binding", not invalid_bindings, "Bindings resolve to schema-compatible fields", invalid=invalid_bindings))

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
