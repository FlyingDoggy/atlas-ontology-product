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
        primary_key = property_map.get(entity.primary_key)
        if primary_key is None:
            invalid_entity_keys[entity.id] = f"unknown primary key: {entity.primary_key}"
        elif primary_key.entity != entity.id:
            invalid_entity_keys[entity.id] = (
                f"primary key {entity.primary_key} belongs to {primary_key.entity}"
            )
    checks.append(
        _check(
            "ENTITY_KEY_CLOSURE",
            "semantic",
            not invalid_entity_keys,
            "Every entity primary key resolves to one of its own properties",
            invalid=invalid_entity_keys,
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
            and measure.unit != metric.unit
        ):
            defects.append(
                f"measure unit {measure.unit} does not match metric unit {metric.unit}"
            )

        def check_formula(node: FormulaNode) -> None:
            if node.op in {"add", "subtract"}:
                operand_units = {
                    metric_map[child.ref].unit
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
