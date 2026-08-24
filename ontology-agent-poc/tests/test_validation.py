from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from ontology_agent.models import Condition, FormulaNode, OntologyPackage, SqlContract, Status
from ontology_agent.governance import metric_dependencies_sparql
from ontology_agent.validation import (
    validate_candidate_package,
    validate_package,
    validate_semantic_package,
)


def test_legacy_null_comparison_is_read_compatible_but_not_authorable() -> None:
    with pytest.raises(ValidationError):
        Condition.model_validate(
            {"property": "property.x", "op": "eq", "value": None}
        )

    restored = Condition.model_validate(
        {"property": "property.x", "op": "eq", "value": None},
        context={"allow_legacy_null_condition_comparison": True},
    )

    assert restored.op == "eq"
    assert restored.value is None


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


def test_candidate_validation_keeps_semantic_gates_without_publish_authority(
    package: OntologyPackage,
) -> None:
    target = next(item for item in package.metrics if item.metric_type == "derived")
    proposed = target.model_copy(update={"status": Status.PROPOSED})
    candidate = package.model_copy(
        update={
            "metrics": tuple(
                proposed if item.id == target.id else item for item in package.metrics
            )
        }
    )

    report = validate_candidate_package(candidate)
    failed = {check.check_id for check in report.checks if check.status == "FAIL"}

    assert "PACKAGE_STATUS" not in {check.check_id for check in report.checks}
    assert "CONFIRMED_ONLY" not in {check.check_id for check in report.checks}
    assert "METRIC_REFERENCE_CLOSURE" not in failed
    assert report.status == "PASS"


def test_source_reference_failure_identifies_objects_and_expected_id_namespace(
    package: OntologyPackage,
) -> None:
    invalid_source_version = "source-version." + "a" * 32
    metric = package.metrics[0].model_copy(
        update={"sources": (invalid_source_version,)}
    )
    metrics = tuple(
        metric if item.id == metric.id else item for item in package.metrics
    )

    report = validate_semantic_package(package.model_copy(update={"metrics": metrics}))
    check = next(
        item for item in report.checks if item.check_id == "SOURCE_REFERENCES"
    )

    assert check.status == "FAIL"
    assert check.details["missing"] == [invalid_source_version]
    assert check.details["by_object"] == {metric.id: [invalid_source_version]}
    assert "not source-version ID" in check.details["expected_reference_type"]
    assert check.details["registered_source_ids"] == sorted(
        item.id for item in package.sources
    )


def test_metric_reference_failure_explains_dimension_and_property_namespaces(
    package: OntologyPackage,
) -> None:
    metric = next(item for item in package.metrics if item.metric_type == "base")
    property_id = next(
        item.id for item in package.properties if item.entity == metric.base_entity
    )
    changed = metric.model_copy(
        update={"result_grain": (property_id,), "allowed_dimensions": (property_id,)}
    )
    metrics = tuple(
        changed if item.id == metric.id else item for item in package.metrics
    )

    report = validate_semantic_package(package.model_copy(update={"metrics": metrics}))
    check = next(
        item
        for item in report.checks
        if item.check_id == "METRIC_REFERENCE_CLOSURE"
    )

    assert check.status == "FAIL"
    assert check.details["by_metric"][metric.id] == {
        "unknown_result_grain_dimensions": [property_id],
        "unknown_allowed_dimensions": [property_id],
    }
    assert check.details["expected_reference_types"]["result_grain"] == (
        "dimensions[].id"
    )
    assert check.details["registered_ids"]["dimensions"] == sorted(
        item.id for item in package.dimensions
    )


def test_proposed_base_metric_requires_boolean_population_property(
    package: OntologyPackage,
) -> None:
    metric = next(item for item in package.metrics if item.metric_type == "base")
    non_boolean_population = next(
        item.id
        for item in package.properties
        if item.data_type == "string" and item.id != metric.query.population_property
    )
    changed = metric.model_copy(
        update={
            "status": Status.PROPOSED,
            "query": metric.query.model_copy(
                update={
                    "population_property": non_boolean_population,
                    "filters": (),
                }
            ),
        }
    )
    metrics = tuple(
        changed if item.id == metric.id else item for item in package.metrics
    )

    report = validate_semantic_package(package.model_copy(update={"metrics": metrics}))
    check = next(
        item
        for item in report.checks
        if item.check_id == "METRIC_POPULATION_SEMANTICS"
    )

    assert check.status == "FAIL"
    assert non_boolean_population in check.details["invalid"][metric.id][0]


def test_proposed_base_metric_filters_do_not_replace_boolean_population(
    package: OntologyPackage,
) -> None:
    metric = next(item for item in package.metrics if item.metric_type == "base")
    non_boolean_population = next(
        item.id for item in package.properties if item.data_type == "string"
    )
    changed = metric.model_copy(
        update={
            "status": Status.PROPOSED,
            "query": metric.query.model_copy(
                update={
                    "population_property": non_boolean_population,
                    "filters": (package.rules[0].id,),
                }
            ),
        }
    )
    metrics = tuple(
        changed if item.id == metric.id else item for item in package.metrics
    )

    assert "METRIC_POPULATION_SEMANTICS" in _failed_ids(
        package.model_copy(update={"metrics": metrics})
    )


def test_confirmed_legacy_metric_keeps_non_boolean_market_scope_compatibility(
    package: OntologyPackage,
) -> None:
    check = next(
        item
        for item in validate_semantic_package(package).checks
        if item.check_id == "METRIC_POPULATION_SEMANTICS"
    )

    assert check.status == "PASS"


def test_proposed_base_metric_accepts_governed_population_rule(
    package: OntologyPackage,
) -> None:
    metric = next(item for item in package.metrics if item.metric_type == "base")
    changed = metric.model_copy(
        update={
            "status": Status.PROPOSED,
            "query": metric.query.model_copy(
                update={
                    "period_property": None,
                    "population_property": None,
                    "population_rule": package.rules[0].id,
                    "filters": (),
                }
            ),
        }
    )
    metrics = tuple(
        changed if item.id == metric.id else item for item in package.metrics
    )
    report = validate_semantic_package(
        package.model_copy(update={"metrics": metrics})
    )
    checks = {item.check_id: item for item in report.checks}

    assert checks["METRIC_REFERENCE_CLOSURE"].status == "PASS"
    assert checks["METRIC_QUERY_CONSISTENCY"].status == "PASS"
    assert checks["METRIC_POPULATION_SEMANTICS"].status == "PASS"


def test_proposed_base_metric_rejects_two_population_scopes(
    package: OntologyPackage,
) -> None:
    metric = next(item for item in package.metrics if item.metric_type == "base")
    changed = metric.model_copy(
        update={
            "status": Status.PROPOSED,
            "query": metric.query.model_copy(
                update={"population_rule": package.rules[0].id}
            ),
        }
    )
    metrics = tuple(
        changed if item.id == metric.id else item for item in package.metrics
    )
    report = validate_semantic_package(
        package.model_copy(update={"metrics": metrics})
    )
    check = next(
        item
        for item in report.checks
        if item.check_id == "METRIC_POPULATION_SEMANTICS"
    )

    assert check.status == "FAIL"
    assert "exactly one" in check.details["invalid"][metric.id][0]


def test_base_metric_population_rule_must_resolve(
    package: OntologyPackage,
) -> None:
    metric = next(item for item in package.metrics if item.metric_type == "base")
    changed = metric.model_copy(
        update={
            "query": metric.query.model_copy(
                update={
                    "population_property": None,
                    "population_rule": "rule.missing_population",
                }
            ),
        }
    )
    metrics = tuple(
        changed if item.id == metric.id else item for item in package.metrics
    )
    report = validate_semantic_package(
        package.model_copy(update={"metrics": metrics})
    )
    check = next(
        item
        for item in report.checks
        if item.check_id == "METRIC_REFERENCE_CLOSURE"
    )

    assert check.status == "FAIL"
    assert check.details["by_metric"][metric.id][
        "unknown_query_population_rule"
    ] == ["rule.missing_population"]


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


def _failed_ids(package: OntologyPackage) -> set[str]:
    return {
        check.check_id
        for check in validate_semantic_package(package).checks
        if check.status == "FAIL"
    }


def test_generic_scenario_does_not_require_exchange_placeholders(
    package: OntologyPackage,
) -> None:
    scenario = package.scenario.model_copy(
        update={
            "timezone": None,
            "market_id": None,
            "data_window_start": None,
            "data_window_end": None,
            "periods": (),
            "default_role": None,
        }
    )

    report = validate_semantic_package(package.model_copy(update={"scenario": scenario}))

    assert next(
        check for check in report.checks if check.check_id == "SCENARIO_PERIODS"
    ).status == "PASS"


def test_entity_primary_key_must_belong_to_the_entity(
    package: OntologyPackage,
) -> None:
    entity = package.entities[0]
    foreign_property = next(
        item for item in package.properties if item.entity != entity.id
    )
    changed = entity.model_copy(update={"primary_key": foreign_property.id})
    entities = tuple(changed if item.id == entity.id else item for item in package.entities)

    assert "ENTITY_KEY_CLOSURE" in _failed_ids(
        package.model_copy(update={"entities": entities})
    )


def test_entity_composite_primary_key_closes_over_all_components(
    package: OntologyPackage,
) -> None:
    entity = package.entities[0]
    own_properties = [
        item.id for item in package.properties if item.entity == entity.id
    ][:2]
    changed = entity.model_copy(update={"primary_key": tuple(own_properties)})
    entities = tuple(changed if item.id == entity.id else item for item in package.entities)

    assert "ENTITY_KEY_CLOSURE" not in _failed_ids(
        package.model_copy(update={"entities": entities})
    )

    foreign_property = next(
        item for item in package.properties if item.entity != entity.id
    )
    invalid = changed.model_copy(
        update={"primary_key": (*own_properties, foreign_property.id)}
    )
    invalid_entities = tuple(
        invalid if item.id == entity.id else item for item in package.entities
    )
    assert "ENTITY_KEY_CLOSURE" in _failed_ids(
        package.model_copy(update={"entities": invalid_entities})
    )


def test_binding_must_preserve_the_logical_property_type(
    package: OntologyPackage,
) -> None:
    binding = next(
        item
        for item in package.bindings
        if next(
            prop for prop in package.properties if prop.id == item.logical_target
        ).data_type
        != "string"
    )
    changed = binding.model_copy(update={"data_type": "string"})
    bindings = tuple(
        changed if item.id == binding.id else item for item in package.bindings
    )

    assert "LOGICAL_BINDING_COMPATIBILITY" in _failed_ids(
        package.model_copy(update={"bindings": bindings})
    )


def test_metric_arithmetic_rejects_non_numeric_operands(
    package: OntologyPackage,
) -> None:
    metric = next(item for item in package.metrics if item.metric_type == "base")
    string_property = next(
        item for item in package.properties if item.data_type == "string"
    )
    formula = FormulaNode(
        op="sum",
        args=(FormulaNode(op="field_ref", ref=string_property.id),),
    )
    changed = metric.model_copy(
        update={
            "formula": formula,
            "query": metric.query.model_copy(
                update={"measure_property": string_property.id}
            ),
        }
    )
    metrics = tuple(changed if item.id == metric.id else item for item in package.metrics)

    assert "METRIC_FORMULA_TYPE_COMPATIBILITY" in _failed_ids(
        package.model_copy(update={"metrics": metrics})
    )


def test_duration_ms_requires_two_datetime_properties(
    package: OntologyPackage,
) -> None:
    metric = next(item for item in package.metrics if item.metric_type == "base")
    string_property = next(
        item for item in package.properties if item.data_type == "string"
    )
    ref = FormulaNode(op="field_ref", ref=string_property.id)
    changed = metric.model_copy(
        update={
            "formula": FormulaNode(op="duration_ms", args=(ref, ref)),
            "query": metric.query.model_copy(
                update={"measure_property": string_property.id}
            ),
        }
    )
    metrics = tuple(
        changed if item.id == metric.id else item for item in package.metrics
    )

    assert "METRIC_FORMULA_TYPE_COMPATIBILITY" in _failed_ids(
        package.model_copy(update={"metrics": metrics})
    )


def test_null_comparison_requires_explicit_null_operator() -> None:
    with pytest.raises(ValueError, match="use is_null"):
        Condition(property="property.example", op="eq", value=None)


def test_property_id_literal_is_rejected_as_rule_semantics(
    package: OntologyPackage,
) -> None:
    rule = package.rules[0]
    left = rule.all[0].property
    right = next(item.id for item in package.properties if item.id != left)
    changed_rule = rule.model_copy(
        update={"all": (Condition(property=left, op="eq", value=right),)}
    )
    rules = tuple(
        changed_rule if item.id == rule.id else item for item in package.rules
    )

    assert "RULE_CONDITION_SEMANTICS" in _failed_ids(
        package.model_copy(update={"rules": rules})
    )


def test_derived_metric_cannot_hide_physical_aggregation_without_base_metrics(
    package: OntologyPackage,
) -> None:
    derived = next(item for item in package.metrics if item.metric_type == "derived")
    base = next(item for item in package.metrics if item.metric_type == "base")
    changed = derived.model_copy(update={"formula": base.formula})
    metrics = tuple(
        changed if item.id == derived.id else item for item in package.metrics
    )

    assert "METRIC_FORMULA_LAYERING" in _failed_ids(
        package.model_copy(update={"metrics": metrics})
    )


def test_dividing_an_expression_by_itself_is_rejected_as_tautological(
    package: OntologyPackage,
) -> None:
    derived = next(item for item in package.metrics if item.metric_type == "derived")
    base = next(item for item in package.metrics if item.metric_type == "base")
    repeated = FormulaNode(op="metric_ref", ref=base.id)
    changed = derived.model_copy(
        update={"formula": FormulaNode(op="divide", args=(repeated, repeated))}
    )
    metrics = tuple(
        changed if item.id == derived.id else item for item in package.metrics
    )

    assert "METRIC_FORMULA_TAUTOLOGY" in _failed_ids(
        package.model_copy(update={"metrics": metrics})
    )


def test_new_derived_metric_cannot_relabel_a_referenced_currency(
    package: OntologyPackage,
) -> None:
    derived = next(item for item in package.metrics if item.metric_type == "derived")
    base = next(item for item in package.metrics if item.metric_type == "base")
    changed = derived.model_copy(
        update={
            "status": Status.PROPOSED,
            "unit": "USD",
            "formula": FormulaNode(op="metric_ref", ref=base.id),
        }
    )
    metrics = tuple(
        changed if item.id == derived.id else item for item in package.metrics
    )
    report = validate_semantic_package(package.model_copy(update={"metrics": metrics}))
    check = next(
        item for item in report.checks if item.check_id == "METRIC_UNIT_COMPATIBILITY"
    )

    assert check.status == "FAIL"
    assert derived.id in check.details["invalid"]


def test_physical_schema_rejects_duplicate_and_nullable_primary_key_fields(
    package: OntologyPackage,
) -> None:
    source = package.data_sources[0]
    table = source.tables[0]
    key_name = table.primary_key[0]
    key = next(item for item in table.fields if item.name == key_name)
    changed_key = key.model_copy(update={"nullable": True})
    fields = tuple(
        changed_key if item.name == key_name else item for item in table.fields
    ) + (changed_key,)
    changed_table = table.model_copy(update={"fields": fields})
    changed_source = source.model_copy(update={"tables": (changed_table, *source.tables[1:])})
    sources = tuple(
        changed_source if item.id == source.id else item for item in package.data_sources
    )

    assert "DATA_SOURCE_SCHEMA_INTEGRITY" in _failed_ids(
        package.model_copy(update={"data_sources": sources})
    )


def test_sql_contract_resolves_exact_statement_inputs_and_governed_output(
    package: OntologyPackage,
) -> None:
    source = package.data_sources[0]
    table = source.tables[0]
    statement_source = next(
        item.id for item in package.sources if item.source_type == "sql"
    )
    contract = SqlContract.model_validate(
        {
            "id": "sql.adt.reference",
            "status": "confirmed",
            "name": {"en": "ADT SQL", "zh": "ADT SQL"},
            "definition": "Governed reference to the exact ADT calculation SQL.",
            "owner": package.actors[0].id,
            "sources": [statement_source],
            "dialect": "duckdb",
            "statement_source": statement_source,
            "statement_locator": "statement:adt",
            "inputs": [{"source": source.id, "table": table.name}],
            "output_fields": ["adt"],
            "implements": [package.metrics[0].id],
            "execution_mode": "validated_query",
        }
    )
    valid = package.model_copy(update={"sql_contracts": (contract,)})
    invalid = valid.model_copy(
        update={
            "sql_contracts": (
                contract.model_copy(
                    update={
                        "inputs": (
                            contract.inputs[0].model_copy(update={"table": "missing"}),
                        )
                    }
                ),
            )
        }
    )

    assert "SQL_CONTRACT_CLOSURE" not in _failed_ids(valid)
    assert "SQL_CONTRACT_CLOSURE" in _failed_ids(invalid)
