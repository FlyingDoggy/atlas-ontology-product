from __future__ import annotations

from pathlib import Path

from ontology_agent.models import OntologyPackage, SqlContract, Status
from ontology_agent.governance import metric_dependencies_sparql
from ontology_agent.validation import validate_package, validate_semantic_package


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
