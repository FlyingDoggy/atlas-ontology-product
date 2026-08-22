from __future__ import annotations

import hashlib
import json

import pytest

from ontology_agent.io import sha256_value
from ontology_agent.models import OntologyPackage
from ontology_agent.studio.construction import (
    CandidateDraftDiffV1,
    ConstructionCandidateV1,
)
from ontology_agent.studio.evidence import normalize_evidence
from ontology_agent.studio.reviewer import (
    BoundedReviewerOrchestrator,
    ReviewerError,
    ReviewerFindingV1,
    ReviewerOutputV1,
    ReviewerRequestV1,
    ReviewerResponseV1,
    deterministic_candidate_findings,
)
from ontology_agent.studio.package_authoring import PackageDraftOperation
from ontology_agent.studio.skill_packages import load_skill_package


def _typed_candidate(
    suffix: str, candidate_type: str, operation: PackageDraftOperation
) -> ConstructionCandidateV1:
    return ConstructionCandidateV1(
        candidate_id="candidate." + suffix * 32,
        occurrence_key=suffix * 64,
        revision_digest=("f" if suffix != "f" else "e") * 64,
        candidate_type=candidate_type,
        label=operation.object_id,
        definition="Typed review candidate.",
        support_class="DIRECT_EXACT",
        risk_class="HIGH",
        compile_eligible=True,
        canonical_target=operation.object_id,
        proposal={},
        proposed_operation=operation,
        draft_diff=CandidateDraftDiffV1(
            change_type="CREATE", after=operation.payload
        ),
    )


def _intake() -> dict[str, object]:
    body = "A customer request is received and assigned a unique request identifier."
    return {
        "assets": (
            {
                "asset_id": "source.input",
                "kind": "requirement_transcription",
                "locator": "source-library:source-version.00000000000000000000000000000000",
                "source_version_id": "source-version.00000000000000000000000000000000",
                "checksum": hashlib.sha256(body.encode()).hexdigest(),
                "content_text": body,
            },
        )
    }


def _candidate() -> ConstructionCandidateV1:
    return ConstructionCandidateV1(
        candidate_id="candidate." + "1" * 32,
        occurrence_key="2" * 64,
        revision_digest="3" * 64,
        candidate_type="OBJECT",
        label="Customer Request",
        definition="A request received from a customer.",
        support_class="MODEL_INFERRED",
        risk_class="MEDIUM",
        compile_eligible=False,
        canonical_target=None,
        proposal={"rationale": "PRIVATE BUILDER RATIONALE MUST NOT CROSS"},
        proposed_operation=None,
        source_anchors=(),
        impact_refs=(),
        limitations=("Builder-only explanation",),
        draft_diff=CandidateDraftDiffV1(change_type="NON_COMPILABLE"),
    )


class FakeReviewerModel:
    def __init__(self, *, escape: bool = False) -> None:
        self.escape = escape
        self.requests: list[ReviewerRequestV1] = []

    def review(self, request: ReviewerRequestV1) -> ReviewerResponseV1:
        self.requests.append(request)
        findings: tuple[ReviewerFindingV1, ...] = ()
        if self.escape:
            findings = (
                ReviewerFindingV1(
                    finding_id="finding.model.unknown",
                    finding_type="UNSUPPORTED_CLAIM",
                    severity="ERROR",
                    summary="Unknown candidate",
                    detail="The finding attempts to escape the closed candidate set.",
                    candidate_ids=("candidate." + "9" * 32,),
                    evidence_fragment_ids=(),
                    blocks_release=True,
                    recommendation="Reject.",
                ),
            )
        output = ReviewerOutputV1(
            request_digest=request.request_digest,
            findings=findings,
            done=True,
        )
        return ReviewerResponseV1(
            requested_model="qwen3.8-max",
            response_model="qwen3.8-max",
            provider_request_id="provider-review-1",
            output=output,
            output_digest=sha256_value(output),
        )


def _reviewer(model: FakeReviewerModel) -> BoundedReviewerOrchestrator:
    return BoundedReviewerOrchestrator(
        model=model,
        skill=load_skill_package("ontology-review", "1.0.0"),
    )


def test_reviewer_gets_a_fresh_projection_and_only_returns_findings(
    package: OntologyPackage,
) -> None:
    model = FakeReviewerModel()
    bundle = normalize_evidence(_intake(), workspace_id="workspace.generic")

    result = _reviewer(model).review(
        run_id="construction-run." + "4" * 32,
        workspace_id="workspace.generic",
        base_draft_checksum="5" * 64,
        package=package,
        candidates=(_candidate(),),
        evidence_bundle=bundle,
    )

    request_json = json.dumps(model.requests[0].model_dump(mode="json"))
    assert "PRIVATE BUILDER RATIONALE" not in request_json
    assert "Builder-only explanation" not in request_json
    assert {item.finding_type for item in result.findings} == {
        "UNSUPPORTED_CLAIM",
        "MISSING_COVERAGE",
    }
    assert any(item.blocks_release for item in result.findings)


def test_reviewer_rejects_a_finding_for_an_unknown_candidate(
    package: OntologyPackage,
) -> None:
    bundle = normalize_evidence(_intake(), workspace_id="workspace.generic")

    with pytest.raises(ReviewerError, match="unknown candidate"):
        _reviewer(FakeReviewerModel(escape=True)).review(
            run_id="construction-run." + "6" * 32,
            workspace_id="workspace.generic",
            base_draft_checksum="7" * 64,
            package=package,
            candidates=(_candidate(),),
            evidence_bundle=bundle,
        )


def test_deterministic_review_blocks_binding_outside_candidate_schema(
    package: OntologyPackage,
) -> None:
    source_id = package.sources[0].id
    owner_id = package.actors[0].id
    logical_target = package.properties[0].id
    data_source_operation = PackageDraftOperation.model_validate(
        {
            "action": "UPSERT",
            "collection": "data_sources",
            "object_id": "ds.review_test",
            "payload": {
                "id": "ds.review_test",
                "status": "proposed",
                "name": {"en": "Review test source"},
                "definition": "A source used to test binding closure.",
                "owner": owner_id,
                "sources": [source_id],
                "tables": [
                    {
                        "name": "events",
                        "grain": "one event",
                        "primary_key": ["event_id"],
                        "fields": [
                            {
                                "name": "event_id",
                                "data_type": "string",
                                "nullable": False,
                                "description": "Event identifier.",
                            }
                        ],
                    }
                ],
            },
        }
    )
    binding_operation = PackageDraftOperation.model_validate(
        {
            "action": "UPSERT",
            "collection": "bindings",
            "object_id": "bind.review_test.missing_column",
            "payload": {
                "id": "bind.review_test.missing_column",
                "status": "proposed",
                "name": {"en": "Missing column binding"},
                "definition": "A binding to a column absent from the schema.",
                "owner": owner_id,
                "sources": [source_id],
                "logical_target": logical_target,
                "source": "ds.review_test",
                "table": "events",
                "column": "missing_column",
                "data_type": "string",
            },
        }
    )

    binding_candidate = _typed_candidate("b", "MAPPING", binding_operation)
    findings = deterministic_candidate_findings(
        (
            _typed_candidate("a", "DATA_SOURCE", data_source_operation),
            binding_candidate,
        ),
        package=package,
        evidence_bundle=None,
    )

    binding_findings = [
        item
        for item in findings
        if binding_candidate.candidate_id in item.candidate_ids
    ]
    assert any(
        item.finding_type == "BROKEN_REFERENCE"
        and item.blocks_release
        and "unknown physical column" in item.detail
        for item in binding_findings
    )


def test_deterministic_review_blocks_invalid_metric_references_and_query_contract(
    package: OntologyPackage,
) -> None:
    source_id = package.sources[0].id
    owner_id = package.actors[0].id
    metric_operation = PackageDraftOperation.model_validate(
        {
            "action": "UPSERT",
            "collection": "metrics",
            "object_id": "metric.review_test",
            "payload": {
                "id": "metric.review_test",
                "status": "proposed",
                "name": {"en": "Invalid review metric"},
                "definition": "A derived metric with unresolved references.",
                "owner": owner_id,
                "sources": [source_id],
                "metric_type": "derived",
                "base_entity": "entity.missing",
                "result_grain": ["dimension.missing"],
                "value_type": "decimal",
                "unit": "ratio",
                "aggregation_semantics": "derived_non_additive",
                "formula": {"op": "field_ref", "ref": "property.missing"},
                "query": {"base_source": "ds.unexpected"},
            },
        }
    )
    candidate = _typed_candidate("c", "METRIC", metric_operation)

    findings = deterministic_candidate_findings(
        (candidate,), package=package, evidence_bundle=None
    )

    candidate_findings = [
        item for item in findings if candidate.candidate_id in item.candidate_ids
    ]
    assert any(
        item.finding_type == "BROKEN_REFERENCE"
        and item.blocks_release
        and "property.missing" in item.detail
        for item in candidate_findings
    )
    assert any(
        item.finding_type == "INCONSISTENT_CONTRACT"
        and item.blocks_release
        and "derived metric" in item.detail
        for item in candidate_findings
    )


def test_deterministic_review_blocks_join_outside_candidate_schemas(
    package: OntologyPackage,
) -> None:
    source_id = package.sources[0].id
    owner_id = package.actors[0].id
    data_source_operation = PackageDraftOperation.model_validate(
        {
            "action": "UPSERT",
            "collection": "data_sources",
            "object_id": "ds.join_review",
            "payload": {
                "id": "ds.join_review",
                "status": "proposed",
                "name": {"en": "Join review source"},
                "definition": "A source used to test join closure.",
                "owner": owner_id,
                "sources": [source_id],
                "tables": [
                    {
                        "name": "left_events",
                        "grain": "one left event",
                        "primary_key": ["event_id"],
                        "fields": [
                            {
                                "name": "event_id",
                                "data_type": "string",
                                "nullable": False,
                                "description": "Event identifier.",
                            }
                        ],
                    }
                ],
            },
        }
    )
    join_operation = PackageDraftOperation.model_validate(
        {
            "action": "UPSERT",
            "collection": "joins",
            "object_id": "join.review_test",
            "payload": {
                "id": "join.review_test",
                "status": "proposed",
                "name": {"en": "Invalid review join"},
                "definition": "A join whose right relation is absent.",
                "owner": owner_id,
                "sources": [source_id],
                "left_source": "ds.join_review",
                "left_table": "left_events",
                "right_source": "ds.join_review",
                "right_table": "missing_table",
                "keys": [
                    {"left_column": "event_id", "right_column": "event_id"}
                ],
                "expected_cardinality": "N:1",
            },
        }
    )
    join_candidate = _typed_candidate("d", "LINK", join_operation)

    findings = deterministic_candidate_findings(
        (
            _typed_candidate("e", "DATA_SOURCE", data_source_operation),
            join_candidate,
        ),
        package=package,
        evidence_bundle=None,
    )

    assert any(
        item.finding_type == "BROKEN_REFERENCE"
        and item.blocks_release
        and "missing_table" in item.detail
        for item in findings
        if join_candidate.candidate_id in item.candidate_ids
    )


def test_deterministic_review_blocks_relationship_with_missing_endpoint(
    package: OntologyPackage,
) -> None:
    source_id = package.sources[0].id
    owner_id = package.actors[0].id
    relationship_operation = PackageDraftOperation.model_validate(
        {
            "action": "UPSERT",
            "collection": "relationships",
            "object_id": "relationship.review_test.missing_endpoint",
            "payload": {
                "id": "relationship.review_test.missing_endpoint",
                "status": "proposed",
                "name": {"en": "Missing endpoint relationship"},
                "definition": "A relationship whose target entity is absent.",
                "owner": owner_id,
                "sources": [source_id],
                "from_entity": package.entities[0].id,
                "to_entity": "entity.missing",
                "predicate": "references",
                "cardinality": "N:1",
            },
        }
    )
    candidate = _typed_candidate("9", "LINK", relationship_operation)

    findings = deterministic_candidate_findings(
        (candidate,), package=package, evidence_bundle=None
    )

    assert any(
        item.finding_type == "BROKEN_REFERENCE"
        and item.blocks_release
        and "entity.missing" in item.detail
        for item in findings
        if candidate.candidate_id in item.candidate_ids
    )
