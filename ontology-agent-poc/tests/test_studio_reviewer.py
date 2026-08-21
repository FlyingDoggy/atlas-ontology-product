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
)
from ontology_agent.studio.skill_packages import load_skill_package


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
