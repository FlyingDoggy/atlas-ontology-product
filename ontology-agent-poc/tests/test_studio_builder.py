from __future__ import annotations

import hashlib

import pytest

from ontology_agent.io import sha256_value
from ontology_agent.models import OntologyPackage
from ontology_agent.studio.builder import (
    BoundedBuilderOrchestrator,
    BuilderError,
    BuilderPhaseOutputV1,
    BuilderPhaseRequestV1,
    BuilderPhaseResponseV1,
    _phase_evidence_fragments,
)
from ontology_agent.studio.evidence import normalize_evidence
from ontology_agent.studio.skill_packages import load_skill_package


def _intake() -> dict[str, object]:
    body = "A customer request is received, assessed and closed.\nEach request has a request ID."
    return {
        "assets": (
            {
                "asset_id": "source.input",
                "kind": "requirement_transcription",
                "locator": "source-library:source-version.00000000000000000000000000000000",
                "source_version_id": "source-version.00000000000000000000000000000000",
                "title": "Customer request process",
                "checksum": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                "registered_at": "2026-08-22T00:00:00Z",
                "content_text": body,
                "processing_mode": "TRANSCRIBED",
            },
        )
    }


class FakeBuilderModel:
    def __init__(self, *, source_id: str = "source.input", escape: bool = False) -> None:
        self.source_id = source_id
        self.escape = escape
        self.requests: list[BuilderPhaseRequestV1] = []

    def generate(self, request: BuilderPhaseRequestV1) -> BuilderPhaseResponseV1:
        self.requests.append(request)
        proposals: tuple[dict[str, object], ...] = ()
        if request.phase == "SEMANTIC":
            fragment_id = request.evidence_fragments[0].fragment_id
            collection = "metrics" if self.escape else "entities"
            payload: dict[str, object]
            if collection == "entities":
                payload = {
                    "id": "entity.customer_request",
                    "version": "1.0.0",
                    "status": "proposed",
                    "name": {"en": "Customer Request", "zh": "客户请求"},
                    "definition": "A request received from a customer for assessment.",
                    "owner": "Business Owner",
                    "sources": [self.source_id],
                    "decisions": [],
                    "tags": [],
                    "primary_key": "property.customer_request.id",
                    "grain": "one customer request",
                    "lifecycle": "received to closed",
                }
            else:
                payload = {
                    "id": "metric.request_count",
                    "version": "1.0.0",
                    "status": "proposed",
                    "name": {"en": "Request Count", "zh": "请求数"},
                    "definition": "Count of customer requests.",
                    "owner": "Business Owner",
                    "sources": [self.source_id],
                    "decisions": [],
                    "tags": [],
                    "metric_type": "base",
                    "base_entity": "entity.customer_request",
                    "result_grain": [],
                    "value_type": "integer",
                    "unit": "request",
                    "aggregation_semantics": "additive",
                    "formula": {
                        "op": "count_distinct",
                        "args": [{"op": "field_ref", "ref": "property.customer_request.id"}],
                    },
                    "allowed_dimensions": [],
                    "null_policy": "fail_validation",
                    "zero_denominator_policy": "refuse",
                }
            proposals = (
                {
                    "contract": "builder-proposal/v1",
                    "proposal_id": "proposal.customer_request",
                    "operation": {
                        "action": "UPSERT",
                        "collection": collection,
                        "object_id": payload["id"],
                        "payload": payload,
                    },
                    "evidence_fragment_ids": [fragment_id],
                    "rationale": "The exact requirement describes the object.",
                    "assumptions": [],
                    "confidence": 0.85,
                },
            )
        output = BuilderPhaseOutputV1.model_validate(
            {
                "contract": "builder-phase-output/v1",
                "phase": request.phase,
                "request_digest": request.request_digest,
                "proposals": proposals,
                "gaps": [],
                "done": True,
            }
        )
        return BuilderPhaseResponseV1(
            requested_model="qwen3.8-max",
            response_model="qwen3.8-max",
            provider_request_id=f"request-{request.phase.lower()}",
            output=output,
            output_digest=sha256_value(output),
        )


def _builder(model: FakeBuilderModel) -> BoundedBuilderOrchestrator:
    return BoundedBuilderOrchestrator(
        model=model,
        skill=load_skill_package("ontology-build", "1.0.0"),
    )


def test_builder_creates_typed_review_candidates_without_mutating_draft(
    package: OntologyPackage,
) -> None:
    model = FakeBuilderModel()
    original = package.model_dump(mode="json")

    result = _builder(model).build(
        run_id="construction-run." + "1" * 32,
        workspace_id="workspace.generic",
        intake=_intake(),
        package=package,
    )

    assert len(model.requests) == 3
    assert result.skill_id == "ontology-build"
    assert result.source_operations[0].collection == "sources"
    assert result.proposals[0].operation.collection == "entities"
    assert result.proposals[0].evidence_fragment_ids[0].startswith("evidence.")
    assert len(result.phase_receipts) == 3
    assert package.model_dump(mode="json") == original


def test_builder_1_2_runs_one_bounded_semantic_dependency_audit(
    package: OntologyPackage,
) -> None:
    model = FakeBuilderModel()
    builder = BoundedBuilderOrchestrator(
        model=model,
        skill=load_skill_package("ontology-build", "1.2.0"),
    )

    result = builder.build(
        run_id="construction-run." + "9" * 32,
        workspace_id="workspace.generic",
        intake=_intake(),
        package=package,
    )

    assert [request.phase for request in model.requests] == [
        "SEMANTIC",
        "SEMANTIC",
        "DATA",
        "ANALYTICS",
    ]
    assert len(result.phase_receipts) == 4
    assert len(result.proposals) == 1


def test_builder_derives_source_authority_from_exact_evidence_not_the_model(
    package: OntologyPackage,
) -> None:
    result = _builder(FakeBuilderModel(source_id="source.invented")).build(
        run_id="construction-run." + "2" * 32,
        workspace_id="workspace.generic",
        intake=_intake(),
        package=package,
    )

    assert result.proposals[0].operation.payload["sources"] == ["source.input"]


def test_builder_rejects_collection_escape_between_phases(
    package: OntologyPackage,
) -> None:
    with pytest.raises(BuilderError, match="phase authority"):
        _builder(FakeBuilderModel(escape=True)).build(
            run_id="construction-run." + "3" * 32,
            workspace_id="workspace.generic",
            intake=_intake(),
            package=package,
        )


def test_phase_evidence_routing_prioritizes_the_phase_source_role() -> None:
    assets = []
    for source_id, kind, body in (
        ("source.model", "data_model", "entity and table definitions"),
        ("source.metric", "metric_transcription", "metric formula and grain"),
        ("source.sql", "sql", "SELECT 1"),
    ):
        assets.append(
            {
                "asset_id": source_id,
                "kind": kind,
                "checksum": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                "content_text": body,
            }
        )
    bundle = normalize_evidence(
        {"assets": assets}, workspace_id="workspace.generic"
    )

    semantic = _phase_evidence_fragments(bundle, "SEMANTIC")
    analytics = _phase_evidence_fragments(bundle, "ANALYTICS")
    data = _phase_evidence_fragments(bundle, "DATA")

    assert semantic[0].source_kind == "data_model"
    assert analytics[0].source_kind == "metric_transcription"
    assert data[0].source_kind == "data_model"
