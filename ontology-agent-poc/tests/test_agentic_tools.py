from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ontology_agent.io import sha256_value
from ontology_agent.models import OntologyPackage
from ontology_agent.studio.agentic_contracts import (
    AgentToolCallV1,
    BuildObjectiveV1,
    RunAuthorityContextV1,
)
from ontology_agent.studio.agentic_evidence import ExactEvidenceWorkspace
from ontology_agent.studio.agentic_store import InMemoryAgentCheckpointStore
from ontology_agent.studio.agentic_tools import (
    StudioToolHarness,
    tool_definitions,
    tool_registry_digest,
)
from ontology_agent.studio.source_library import FileSourceLibraryStore


def _setup(
    tmp_path: Path,
    package: OntologyPackage,
    *,
    include_secondary_source: bool = False,
    required_candidate_collections: tuple[str, ...] = (),
    metric_semantic_contract: dict[str, object] | None = None,
) -> tuple[StudioToolHarness, RunAuthorityContextV1]:
    source_store = FileSourceLibraryStore(tmp_path / "sources")
    body = (
        b"A service request is submitted by a customer.\n"
        b"Each service request has a unique request identifier.\n"
    )
    version = source_store.register(
        workspace_id="workspace.example",
        source_id="source.requirements",
        kind="requirement_transcription",
        title="Service request requirement",
        original_name="requirements.md",
        media_type="text/markdown",
        body=body,
    )
    versions = [version]
    if include_secondary_source:
        versions.append(
            source_store.register(
                workspace_id="workspace.example",
                source_id="source.metric_logic",
                kind="metric_transcription",
                title="Service request metric logic",
                original_name="metrics.md",
                media_type="text/markdown",
                body=b"Open request count is the number of submitted requests.\n",
            )
        )
    objective_raw = {
        "contract": "studio-build-objective/v1",
        "objective_id": "build-objective." + "1" * 32,
        "solution_id": "ontology.example",
        "workspace_id": "workspace.example",
        "selected_source_version_ids": [item.source_version_id for item in versions],
        "source_set_digest": sha256_value(
            [item.subject_checksum for item in versions]
        ),
        "capabilities": ["SEMANTIC"],
        "output_language": "en",
        "obligations": [
            {
                "obligation_id": "obligation.service-request",
                "kind": "METRIC" if metric_semantic_contract else "REQUIREMENT",
                "title": "Represent the service request and its identifier",
                "source_version_ids": [version.source_version_id],
                "source_locator": "lines:1-2",
                "required_candidate_collections": list(
                    required_candidate_collections
                ),
                "metric_semantic_contract": metric_semantic_contract,
                "required": True,
            }
        ],
        "required_validators": ["candidate.materialize", "reference.closure"],
    }
    objective_raw["objective_checksum"] = sha256_value(objective_raw)
    objective = BuildObjectiveV1.model_validate(objective_raw)
    context = RunAuthorityContextV1(
        job_id="construction-job." + "2" * 32,
        run_id="construction-run." + "3" * 32,
        attempt_id="construction-attempt." + "4" * 32,
        lease_epoch=1,
        lease_owner="worker-1",
        workspace_id=objective.workspace_id,
        solution_id=objective.solution_id,
        source_set_digest=objective.source_set_digest,
        selected_source_version_ids=objective.selected_source_version_ids,
        principal_id="service.builder",
        tool_registry_digest=tool_registry_digest(),
        tool_policy_digest="5" * 64,
        objective_checksum=objective.objective_checksum,
        candidate_revision=0,
        step_sequence=0,
        remaining_model_calls=20,
        remaining_tool_calls=100,
    )
    checkpoint = InMemoryAgentCheckpointStore(
        clock=lambda: datetime(2026, 8, 23, tzinfo=timezone.utc)
    )
    checkpoint.start_attempt(context, objective, package)
    evidence = ExactEvidenceWorkspace(
        context=context,
        versions=tuple(versions),
        store=source_store,
        clock=lambda: datetime(2026, 8, 23, tzinfo=timezone.utc),
    )
    return StudioToolHarness(store=checkpoint, evidence=evidence, context=context), context


def _call(call_id: str, name: str, **arguments: object) -> AgentToolCallV1:
    return AgentToolCallV1(
        tool_call_id=call_id,
        name=name,
        arguments=arguments,
    )


def test_candidate_write_tool_advertises_flat_server_managed_contract() -> None:
    definition = next(
        item for item in tool_definitions() if item.name == "candidate.upsert"
    )
    properties = definition.input_schema["properties"]

    assert "operation" not in properties
    assert {"collection", "object_id", "payload", "claims", "obligation_ids"} <= set(
        properties
    )
    assert "obligation_ids" not in definition.input_schema["required"]
    assert "server derives" in definition.description

    patch_definition = next(
        item for item in tool_definitions() if item.name == "candidate.apply_patch"
    )
    assert patch_definition.input_schema["properties"]["items"]["maxItems"] == 32


def test_scenario_is_exposed_as_a_typed_candidate_collection(
    tmp_path: Path, package: OntologyPackage
) -> None:
    harness, _ = _setup(tmp_path, package)
    schema = harness.execute(
        _call("schema-scenario", "schema.get_collection", collection="scenario")
    )

    assert schema["collection"] == "scenario"
    assert {"id", "status", "sources"}.isdisjoint(
        schema["candidate_payload_schema"]["properties"]
    )

    source = harness.execute(_call("source-list", "evidence.list_sources"))
    source_version_id = source["sources"][0]["source_version_id"]
    read = harness.execute(
        _call(
            "scenario-evidence",
            "evidence.read",
            source_version_id=source_version_id,
            start_line=1,
            end_line=2,
        )
    )
    payload = package.scenario.model_dump(
        mode="json", exclude={"id", "status", "sources"}
    )
    payload["definition"] = "The governed scenario described by the exact input."
    result = harness.execute(
        _call(
            "scenario-upsert",
            "candidate.upsert",
            expected_candidate_revision=0,
            collection="scenario",
            # The model may propose a descriptive identity, but Scenario is a
            # package singleton whose real identity belongs to the shell.
            object_id="scenario.model_guess",
            payload=payload,
            claims=[
                {
                    "path": "definition",
                    "support": "EXACT",
                    "evidence_receipt_ids": [
                        read["evidence_receipt"]["receipt_id"]
                    ],
                }
            ],
        )
    )

    assert result["candidate_revision"] == 1
    assert result["target"] == f"scenario:{package.scenario.id}"


def test_search_is_not_citeable_and_completion_forces_repair(
    tmp_path: Path, package: OntologyPackage
) -> None:
    harness, _ = _setup(tmp_path, package)
    search = harness.execute(_call("search-1", "evidence.search", query="request"))
    assert search["hits"][0]["citeable"] is False

    read = harness.execute(
        _call(
            "read-1",
            "evidence.read",
            source_version_id=search["hits"][0]["source_version_id"],
            start_line=1,
            end_line=2,
        )
    )
    receipt_id = read["evidence_receipt"]["receipt_id"]
    entity_payload = {
        "id": "entity.service_request",
        "version": "1.0.0",
        "status": "proposed",
        "name": {"en": "Service Request"},
        "definition": "A request submitted by a customer.",
        "owner": "actor.domain_owner",
        "sources": ["source.requirements"],
        "primary_key": "property.service_request.id",
        "grain": "one service request",
        "lifecycle": "submitted to closed",
    }
    upsert = harness.execute(
        _call(
            "upsert-entity",
            "candidate.upsert",
            expected_candidate_revision=0,
            operation={
                "action": "UPSERT",
                "collection": "entities",
                "object_id": "entity.service_request",
                "payload": entity_payload,
            },
            claims=[
                {
                    "path": "definition",
                    "support": "EXACT",
                    "evidence_receipt_ids": [receipt_id],
                }
            ],
            obligation_ids=["obligation.service-request"],
        )
    )
    assert upsert["candidate_revision"] == 1

    first_completion = harness.execute(
        _call("complete-1", "run.request_completion", reason="Model believes it is done")
    )
    assert first_completion["completed"] is False
    assert "property.service_request.id" in first_completion["blockers"][0]

    harness.execute(
        _call(
            "upsert-property",
            "candidate.upsert",
            expected_candidate_revision=1,
            operation={
                "action": "UPSERT",
                "collection": "properties",
                "object_id": "property.service_request.id",
                "payload": {
                    "id": "property.service_request.id",
                    "version": "1.0.0",
                    "status": "proposed",
                    "name": {"en": "Service Request ID"},
                    "definition": "Unique identifier of the service request.",
                    "owner": "actor.domain_owner",
                    "sources": ["source.requirements"],
                    "entity": "entity.service_request",
                    "data_type": "string",
                    "required": True,
                },
            },
            claims=[
                {
                    "path": "definition",
                    "support": "EXACT",
                    "evidence_receipt_ids": [receipt_id],
                }
            ],
            obligation_ids=["obligation.service-request"],
        )
    )
    completed = harness.execute(
        _call("complete-2", "run.request_completion", reason="Repaired missing key")
    )
    assert completed["completed"] is True
    assert completed["outcome"] == "REVIEW_READY"
    assert harness.completion is not None
    assert harness.completion.bundle.candidate_revision == 2


def test_completion_rejects_requirement_covered_only_by_wrong_artifact_types(
    tmp_path: Path, package: OntologyPackage
) -> None:
    harness, _ = _setup(
        tmp_path,
        package,
        required_candidate_collections=("analysis_patterns", "questions"),
    )
    source = harness.execute(_call("list", "evidence.list_sources"))["sources"][0]
    read = harness.execute(
        _call(
            "read",
            "evidence.read",
            source_version_id=source["source_version_id"],
            start_line=1,
            end_line=2,
        )
    )
    receipt_id = read["evidence_receipt"]["receipt_id"]
    harness.execute(
        _call(
            "upsert-entity",
            "candidate.upsert",
            expected_candidate_revision=0,
            operation={
                "action": "UPSERT",
                "collection": "entities",
                "object_id": "entity.service_request",
                "payload": {
                    "id": "entity.service_request",
                    "status": "proposed",
                    "name": {"en": "Service Request"},
                    "definition": "A request submitted by a customer.",
                    "owner": "actor.domain_owner",
                    "sources": [source["source_id"]],
                    "primary_key": "property.service_request.id",
                    "grain": "one service request",
                    "lifecycle": "submitted to closed",
                },
            },
            claims=[
                {
                    "path": "definition",
                    "support": "EXACT",
                    "evidence_receipt_ids": [receipt_id],
                }
            ],
            obligation_ids=["obligation.service-request"],
        )
    )
    harness.execute(
        _call(
            "upsert-property",
            "candidate.upsert",
            expected_candidate_revision=1,
            operation={
                "action": "UPSERT",
                "collection": "properties",
                "object_id": "property.service_request.id",
                "payload": {
                    "id": "property.service_request.id",
                    "status": "proposed",
                    "name": {"en": "Service Request ID"},
                    "definition": "Unique request identifier.",
                    "owner": "actor.domain_owner",
                    "sources": [source["source_id"]],
                    "entity": "entity.service_request",
                    "data_type": "string",
                    "required": True,
                },
            },
            claims=[
                {
                    "path": "definition",
                    "support": "EXACT",
                    "evidence_receipt_ids": [receipt_id],
                }
            ],
            obligation_ids=["obligation.service-request"],
        )
    )

    validation = harness.execute(
        _call("validate-shape", "candidate.validate")
    )
    assert validation["valid"] is False
    assert any(
        "analysis_patterns, questions" in blocker
        for blocker in validation["errors"]
    )
    completion = harness.execute(
        _call("complete-shape", "run.request_completion", reason="done")
    )
    assert completion["completed"] is False
    assert any(
        "OBLIGATION_SHAPE" in blocker for blocker in completion["blockers"]
    )


def test_model_can_inspect_collection_schema_and_repair_bad_tool_input(
    tmp_path: Path, package: OntologyPackage
) -> None:
    harness, _ = _setup(tmp_path, package)

    schema = harness.execute(
        _call("schema-entity", "schema.get_collection", collection="entities")
    )
    assert schema["collection"] == "entities"
    serialized = str(schema["candidate_payload_schema"])
    assert "primary_key" in serialized
    assert "lifecycle" in serialized


def test_candidate_validation_rejects_metric_relabelling_and_accepts_formula_repair(
    tmp_path: Path, package: OntologyPackage
) -> None:
    metric_contract: dict[str, object] = {
        "contract": "studio-metric-semantic-obligation/v1",
        "source_metric_key": "M-01",
        "expected_metric_id": "metric.service_request_ratio",
        "name": "Service request ratio",
        "definition": "Percentage of one request population over another.",
        "calculation_logic": "numerator / denominator x 100",
        "filters_and_scope": "same reporting population",
        "grain_and_dimensions": "reporting period",
        "output_instruction": "Output a percentage",
        "null_and_zero_policy": "Refuse when denominator is zero",
        "primary_sources": "registered requirements",
        "expected_metric_type": "derived",
        "expected_value_type": "percentage",
        "expected_unit": "PERCENT",
        "required_formula_root": "multiply",
        "required_formula_operations": ["divide", "multiply"],
        "required_formula_literals": ["100"],
        "required_referenced_units": [],
    }
    metric_contract["semantic_contract_checksum"] = sha256_value(metric_contract)
    harness, _ = _setup(
        tmp_path,
        package,
        required_candidate_collections=("metrics",),
        metric_semantic_contract=metric_contract,
    )
    source = harness.execute(_call("list-metric", "evidence.list_sources"))[
        "sources"
    ][0]
    read = harness.execute(
        _call(
            "read-metric",
            "evidence.read",
            source_version_id=source["source_version_id"],
            start_line=1,
            end_line=2,
        )
    )
    receipt_id = read["evidence_receipt"]["receipt_id"]

    def payload(formula: dict[str, object]) -> dict[str, object]:
        return {
            "name": {"en": "Service Request Ratio"},
            "definition": "Percentage of one request population over another.",
            "owner": "actor.domain_owner",
            "metric_type": "derived",
            "base_entity": "entity.trade",
            "result_grain": ["dimension.period"],
            "value_type": "percentage",
            "unit": "PERCENT",
            "aggregation_semantics": "derived_non_additive",
            "formula": formula,
            "null_policy": "exclude",
            "zero_denominator_policy": "refuse",
        }

    raw_ratio = {
        "op": "divide",
        "args": [
            {"op": "metric_ref", "ref": "metric.trading_day_count"},
            {"op": "metric_ref", "ref": "metric.eligible_turnover"},
        ],
    }
    harness.execute(
        _call(
            "upsert-raw-ratio",
            "candidate.upsert",
            expected_candidate_revision=0,
            collection="metrics",
            object_id="metric.service_request_ratio",
            payload=payload(raw_ratio),
            claims=[
                {
                    "path": "formula",
                    "support": "EXACT",
                    "evidence_receipt_ids": [receipt_id],
                }
            ],
            obligation_ids=["obligation.service-request"],
        )
    )
    invalid = harness.execute(_call("validate-raw-ratio", "candidate.validate"))
    assert invalid["valid"] is False
    assert any(
        "METRIC_OBLIGATION_SEMANTICS" in error
        and "formula root divide != multiply" in error
        and "missing formula literals: 100" in error
        for error in invalid["errors"]
    )

    harness.execute(
        _call(
            "repair-ratio",
            "candidate.upsert",
            expected_candidate_revision=1,
            collection="metrics",
            object_id="metric.service_request_ratio",
            payload=payload(
                {
                    "op": "multiply",
                    "args": [raw_ratio, {"op": "literal", "value": 100}],
                }
            ),
            claims=[
                {
                    "path": "formula",
                    "support": "EXACT",
                    "evidence_receipt_ids": [receipt_id],
                }
            ],
            obligation_ids=["obligation.service-request"],
        )
    )
    repaired = harness.execute(_call("validate-repaired", "candidate.validate"))
    assert repaired["valid"] is True, repaired["errors"]


def test_flat_candidate_write_injects_identity_status_and_provenance(
    tmp_path: Path, package: OntologyPackage
) -> None:
    harness, context = _setup(tmp_path, package)
    source = harness.execute(_call("list-flat", "evidence.list_sources"))["sources"][0]
    read = harness.execute(
        _call(
            "read-flat",
            "evidence.read",
            source_version_id=source["source_version_id"],
            start_line=1,
            end_line=2,
        )
    )
    receipt_id = read["candidate_citation"]["evidence_receipt_id"]

    result = harness.execute(
        _call(
            "upsert-flat",
            "candidate.upsert",
            expected_candidate_revision=0,
            collection="entities",
            object_id="entity.service_request",
            payload={
                "name": {"en": "Service Request"},
                "definition": "A request submitted by a customer.",
                "owner": "actor.domain_owner",
                "primary_key": "property.service_request.id",
                "grain": "one service request",
                "lifecycle": "submitted to closed",
            },
            claims=[
                {
                    "path": "definition",
                    "support": "EXACT",
                    "evidence_receipt_ids": [receipt_id],
                }
            ],
            obligation_ids=["obligation.service-request"],
        )
    )

    assert result["candidate_revision"] == 1
    payload = harness.store.view(context).operations[0].payload
    assert payload is not None
    assert payload["id"] == "entity.service_request"
    assert payload["status"] == "proposed"
    assert payload["sources"] == [source["source_id"]]

    error = harness.execute_for_runtime(
        _call(
            "bad-range",
            "evidence.read",
            source_version_id="source-version.missing",
            start_line=1,
            end_line=2,
        )
    )
    assert error["ok"] is False
    assert error["repairable"] is True
    assert "EVIDENCEWORKSPACEERROR" == error["error_code"]

    invalid_patch = harness.execute_for_runtime(
        _call(
            "bad-patch-shape",
            "candidate.apply_patch",
            expected_candidate_revision=-1,
            items=[],
        )
    )
    assert invalid_patch["ok"] is False
    assert invalid_patch["repairable"] is True
    assert "expected_candidate_revision" in invalid_patch["message"]
    assert "items" in invalid_patch["message"]
    assert "greater than or equal to 0" in invalid_patch["message"]
    assert "at least 1 item" in invalid_patch["message"]


def test_missing_deprecate_target_is_a_repairable_tool_error(
    tmp_path: Path, package: OntologyPackage
) -> None:
    harness, _ = _setup(tmp_path, package)
    source = harness.execute(_call("source-list", "evidence.list_sources"))["sources"][0]
    read = harness.execute(
        _call(
            "source-read",
            "evidence.read",
            source_version_id=source["source_version_id"],
            start_line=1,
            end_line=1,
        )
    )

    error = harness.execute_for_runtime(
        _call(
            "bad-deprecate",
            "candidate.upsert",
            expected_candidate_revision=0,
            operation={
                "action": "DEPRECATE",
                "collection": "bindings",
                "object_id": "binding.missing",
            },
            claims=[
                {
                    "path": "status",
                    "support": "INFERRED",
                    "evidence_receipt_ids": [
                        read["evidence_receipt"]["receipt_id"]
                    ],
                }
            ],
            obligation_ids=["obligation.service-request"],
        )
    )

    assert error["ok"] is False
    assert error["repairable"] is True
    assert "operation: Extra inputs are not permitted" in error["message"]


def test_candidate_sources_are_derived_only_from_current_run_receipts(
    tmp_path: Path, package: OntologyPackage
) -> None:
    harness, context = _setup(
        tmp_path,
        package,
        include_secondary_source=True,
    )
    sources = {
        item["source_id"]: item
        for item in harness.execute(
            _call("source-list", "evidence.list_sources")
        )["sources"]
    }
    requirement_read = harness.execute(
        _call(
            "read-requirement",
            "evidence.read",
            source_version_id=sources["source.requirements"]["source_version_id"],
            start_line=1,
            end_line=2,
        )
    )
    metric_read = harness.execute(
        _call(
            "read-metric",
            "evidence.read",
            source_version_id=sources["source.metric_logic"]["source_version_id"],
            start_line=1,
            end_line=1,
        )
    )
    operation = {
        "action": "UPSERT",
        "collection": "entities",
        "object_id": "entity.service_request",
        "payload": {
            "id": "entity.service_request",
            "version": "1.0.0",
            "status": "proposed",
            "name": {"en": "Service Request"},
            "definition": "A request submitted by a customer.",
            "owner": "actor.domain_owner",
            "sources": ["source.requirements", "source.metric_logic"],
            "primary_key": "property.service_request.id",
            "grain": "one service request",
            "lifecycle": "submitted to closed",
        },
    }

    accepted = harness.execute(
        _call(
            "patch-with-server-managed-provenance",
            "candidate.apply_patch",
            expected_candidate_revision=0,
            items=[
                {
                    "operation": operation,
                    "claims": [
                        {
                            "path": "definition",
                            "support": "EXACT",
                            "evidence_receipt_ids": [
                                requirement_read["evidence_receipt"]["receipt_id"]
                            ],
                        }
                    ],
                    "obligation_ids": ["obligation.service-request"],
                }
            ],
        )
    )

    assert accepted["accepted"] is True
    assert accepted["candidate_revision"] == 1
    stored = harness.store.view(context).operations[0]
    assert stored.payload is not None
    assert stored.payload["sources"] == ["source.requirements"]
    assert "source.metric_logic" not in stored.payload["sources"]
    assert metric_read["evidence_receipt"]["receipt_id"] not in {
        receipt_id
        for claims in harness.store.view(context).claims_by_target.values()
        for claim in claims
        for receipt_id in claim.evidence_receipt_ids
    }


def test_existing_draft_source_identity_can_be_preserved_without_new_receipt(
    tmp_path: Path, package: OntologyPackage
) -> None:
    harness, _ = _setup(tmp_path, package)
    existing = next(item for item in package.actors if item.id == "actor.data_steward")
    payload = existing.model_dump(mode="json")
    payload["status"] = "proposed"
    payload["definition"] = "Candidate clarification of the existing steward role."

    result = harness.execute(
        _call(
            "preserve-existing-source",
            "candidate.upsert",
            expected_candidate_revision=0,
            operation={
                "action": "UPSERT",
                "collection": "actors",
                "object_id": existing.id,
                "payload": payload,
            },
            claims=[
                {
                    "path": "definition",
                    "support": "ASSUMPTION",
                    "evidence_receipt_ids": [],
                }
            ],
            obligation_ids=["obligation.service-request"],
        )
    )

    assert result["accepted"] is True
    assert result["candidate_revision"] == 1


def test_candidate_patch_atomically_adds_a_reference_closed_group(
    tmp_path: Path, package: OntologyPackage
) -> None:
    harness, context = _setup(tmp_path, package)
    sources = harness.execute(_call("list", "evidence.list_sources"))
    read = harness.execute(
        _call(
            "read",
            "evidence.read",
            source_version_id=sources["sources"][0]["source_version_id"],
            start_line=1,
            end_line=2,
        )
    )
    receipt_id = read["evidence_receipt"]["receipt_id"]
    result = harness.execute(
        _call(
            "patch",
            "candidate.apply_patch",
            expected_candidate_revision=0,
            items=[
                {
                    "operation": {
                        "action": "UPSERT",
                        "collection": "entities",
                        "object_id": "entity.service_request",
                        "payload": {
                            "id": "entity.service_request",
                            "version": "1.0.0",
                            "status": "proposed",
                            "name": {"en": "Service Request"},
                            "definition": "A request submitted by a customer.",
                            "owner": "actor.domain_owner",
                            "sources": ["source.requirements"],
                            "primary_key": "property.service_request.id",
                            "grain": "one service request",
                            "lifecycle": "submitted to closed",
                        },
                    },
                    "claims": [
                        {
                            "path": "definition",
                            "support": "EXACT",
                            "evidence_receipt_ids": [receipt_id],
                        }
                    ],
                    "obligation_ids": ["obligation.service-request"],
                },
                {
                    "operation": {
                        "action": "UPSERT",
                        "collection": "properties",
                        "object_id": "property.service_request.id",
                        "payload": {
                            "id": "property.service_request.id",
                            "version": "1.0.0",
                            "status": "proposed",
                            "name": {"en": "Service Request ID"},
                            "definition": "Unique identifier of the service request.",
                            "owner": "actor.domain_owner",
                            "sources": ["source.requirements"],
                            "entity": "entity.service_request",
                            "data_type": "string",
                            "required": True,
                        },
                    },
                    "claims": [
                        {
                            "path": "definition",
                            "support": "EXACT",
                            "evidence_receipt_ids": [receipt_id],
                        }
                    ],
                    "obligation_ids": ["obligation.service-request"],
                },
            ],
        )
    )
    view = harness.store.view(context)
    assert result["candidate_revision"] == 1
    assert set(result["targets"]) == {
        "entities:entity.service_request",
        "properties:property.service_request.id",
    }
    assert len(view.operations) == 2
    assert view.obligation_dispositions[0].candidate_targets == (
        "entities:entity.service_request",
        "properties:property.service_request.id",
    )


def test_existing_evidenced_candidates_can_close_source_coverage_obligation(
    tmp_path: Path, package: OntologyPackage
) -> None:
    harness, context = _setup(tmp_path, package)
    source = harness.execute(_call("list", "evidence.list_sources"))["sources"][0]
    read = harness.execute(
        _call(
            "read",
            "evidence.read",
            source_version_id=source["source_version_id"],
            start_line=1,
            end_line=2,
        )
    )
    receipt_id = read["evidence_receipt"]["receipt_id"]
    harness.execute(
        _call(
            "upsert-entity",
            "candidate.upsert",
            expected_candidate_revision=0,
            operation={
                "action": "UPSERT",
                "collection": "entities",
                "object_id": "entity.service_request",
                "payload": {
                    "id": "entity.service_request",
                    "version": "1.0.0",
                    "status": "proposed",
                    "name": {"en": "Service Request"},
                    "definition": "A request submitted by a customer.",
                    "owner": "actor.domain_owner",
                    "sources": [source["source_id"]],
                    "primary_key": "property.service_request.id",
                    "grain": "one service request",
                    "lifecycle": "submitted to closed",
                },
            },
            claims=[
                {
                    "path": "definition",
                    "support": "EXACT",
                    "evidence_receipt_ids": [receipt_id],
                }
            ],
            obligation_ids=["obligation.service-request"],
        )
    )

    result = harness.execute(
        _call(
            "cover-source",
            "obligation.cover",
            expected_candidate_revision=1,
            items=[
                {
                    "obligation_id": "obligation.service-request",
                    "candidate_targets": ["entities:entity.service_request"],
                    "explanation": "The candidate cites and evidences the frozen source.",
                }
            ],
        )
    )

    assert result["candidate_revision"] == 2
    disposition = harness.store.view(context).obligation_dispositions[0]
    assert disposition.disposition == "CANDIDATE"
    assert disposition.candidate_targets == ("entities:entity.service_request",)


def test_candidate_write_overrides_model_supplied_source_identity(
    tmp_path: Path, package: OntologyPackage
) -> None:
    harness, context = _setup(tmp_path, package)
    source = harness.execute(_call("list", "evidence.list_sources"))["sources"][0]
    read = harness.execute(
        _call(
            "read",
            "evidence.read",
            source_version_id=source["source_version_id"],
            start_line=1,
            end_line=2,
        )
    )
    result = harness.execute(
        _call(
            "upsert-entity",
            "candidate.upsert",
            expected_candidate_revision=0,
            operation={
                "action": "UPSERT",
                "collection": "entities",
                "object_id": "entity.service_request",
                "payload": {
                    "id": "entity.service_request",
                    "version": "1.0.0",
                    "status": "proposed",
                    "name": {"en": "Service Request"},
                    "definition": "A request submitted by a customer.",
                    "owner": "actor.domain_owner",
                    "sources": ["source.unrelated"],
                    "primary_key": "property.service_request.id",
                    "grain": "one service request",
                    "lifecycle": "submitted to closed",
                },
            },
            claims=[
                {
                    "path": "definition",
                    "support": "EXACT",
                    "evidence_receipt_ids": [
                        read["evidence_receipt"]["receipt_id"]
                    ],
                }
            ],
            obligation_ids=["obligation.service-request"],
        )
    )

    assert result["accepted"] is True
    view = harness.store.view(context)
    assert view.candidate_revision == 1
    assert view.operations[0].payload is not None
    assert view.operations[0].payload["sources"] == [source["source_id"]]
