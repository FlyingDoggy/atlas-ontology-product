from __future__ import annotations

from collections import defaultdict
from typing import Any, Literal, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import Field, model_validator

from ..contracts import Sha256
from ..io import sha256_value
from ..models import OntologyPackage, StrictModel
from .evidence import EvidenceBundleV1, EvidenceFragmentV1
from .package_authoring import PackageDraftOperation
from .skill_packages import LoadedSkillPackageV1


ReviewerFindingType = Literal[
    "UNSUPPORTED_CLAIM",
    "EVIDENCE_CONFLICT",
    "DUPLICATE_CANDIDATE",
    "BROKEN_REFERENCE",
    "INCONSISTENT_CONTRACT",
    "MISSING_COVERAGE",
    "MERGE_SUGGESTION",
    "DEPRECATION_SUGGESTION",
    "RELEASE_BLOCKER",
]


class ReviewerError(RuntimeError):
    """A Reviewer result cannot cross the machine-finding boundary."""


class ReviewerUnavailable(ReviewerError):
    """The configured Reviewer execution boundary is unavailable."""


class ReviewerCandidateProjectionV1(StrictModel):
    """Candidate facts visible to Reviewer; Builder rationale is intentionally absent."""

    contract: Literal["reviewer-candidate-projection/v1"] = (
        "reviewer-candidate-projection/v1"
    )
    candidate_id: str = Field(pattern=r"^candidate\.[0-9a-f]{32}$")
    candidate_type: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=500)
    definition: str = Field(min_length=1, max_length=4000)
    support_class: str = Field(min_length=1, max_length=100)
    risk_class: Literal["LOW", "MEDIUM", "HIGH"]
    compile_eligible: bool
    canonical_target: str | None = Field(default=None, max_length=500)
    proposed_operation: PackageDraftOperation | None = None
    evidence_fragment_ids: tuple[str, ...] = Field(max_length=32)
    change_type: Literal["CREATE", "UPDATE", "NO_CHANGE", "NON_COMPILABLE"]
    draft_before: dict[str, Any] | None = None
    changed_paths: tuple[str, ...] = Field(max_length=128)


class ReviewerFindingV1(StrictModel):
    contract: Literal["reviewer-finding/v1"] = "reviewer-finding/v1"
    finding_id: str = Field(pattern=r"^finding\.[A-Za-z0-9][A-Za-z0-9._-]*$")
    finding_type: ReviewerFindingType
    severity: Literal["INFO", "WARN", "ERROR"]
    summary: str = Field(min_length=1, max_length=500)
    detail: str = Field(min_length=1, max_length=3000)
    candidate_ids: tuple[str, ...] = Field(min_length=1, max_length=32)
    evidence_fragment_ids: tuple[str, ...] = Field(max_length=32)
    blocks_release: bool
    recommendation: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def blocking_findings_are_visible(self) -> ReviewerFindingV1:
        if self.blocks_release and self.severity == "INFO":
            raise ValueError("A release-blocking finding cannot be informational")
        if len(self.candidate_ids) != len(set(self.candidate_ids)):
            raise ValueError("Reviewer finding candidate IDs must be unique")
        if len(self.evidence_fragment_ids) != len(set(self.evidence_fragment_ids)):
            raise ValueError("Reviewer finding evidence IDs must be unique")
        return self


class ReviewerRequestV1(StrictModel):
    contract: Literal["reviewer-request/v1"] = "reviewer-request/v1"
    run_id: str = Field(pattern=r"^construction-run\.[0-9a-f]{32}$")
    workspace_id: str = Field(min_length=1, max_length=255)
    skill_id: str
    skill_version: str
    skill_checksum: Sha256
    source_set_digest: Sha256
    base_draft_checksum: Sha256
    evidence_fragments: tuple[EvidenceFragmentV1, ...] = Field(max_length=256)
    candidates: tuple[ReviewerCandidateProjectionV1, ...] = Field(
        min_length=1, max_length=512
    )
    deterministic_findings: tuple[ReviewerFindingV1, ...] = Field(max_length=512)
    draft_context: dict[str, Any]
    allowed_finding_types: tuple[ReviewerFindingType, ...]
    max_findings: int = Field(ge=1, le=256)
    request_digest: Sha256

    @model_validator(mode="after")
    def request_authority_is_closed(self) -> ReviewerRequestV1:
        if self.allowed_finding_types != tuple(ReviewerFindingType.__args__):
            raise ValueError("Reviewer finding scope mismatch")
        candidate_ids = {item.candidate_id for item in self.candidates}
        evidence_ids = {item.fragment_id for item in self.evidence_fragments}
        for finding in self.deterministic_findings:
            if not set(finding.candidate_ids).issubset(candidate_ids):
                raise ValueError("Deterministic finding cites an unknown candidate")
            if not set(finding.evidence_fragment_ids).issubset(evidence_ids):
                raise ValueError("Deterministic finding cites unknown evidence")
        unsigned = self.model_dump(
            mode="json", exclude={"request_digest"}, exclude_none=True
        )
        if sha256_value(unsigned) != self.request_digest:
            raise ValueError("Reviewer request digest mismatch")
        return self


class ReviewerOutputV1(StrictModel):
    contract: Literal["reviewer-output/v1"] = "reviewer-output/v1"
    request_digest: Sha256
    findings: tuple[ReviewerFindingV1, ...] = Field(max_length=256)
    done: bool

    @model_validator(mode="after")
    def unique_findings(self) -> ReviewerOutputV1:
        identities = [item.finding_id for item in self.findings]
        if len(identities) != len(set(identities)):
            raise ValueError("Reviewer finding IDs must be unique")
        return self


class ReviewerResponseV1(StrictModel):
    contract: Literal["reviewer-response/v1"] = "reviewer-response/v1"
    requested_model: str = Field(min_length=1, max_length=255)
    response_model: str = Field(min_length=1, max_length=255)
    provider_request_id: str = Field(min_length=1, max_length=500)
    output: ReviewerOutputV1
    output_digest: Sha256

    @model_validator(mode="after")
    def output_checksum_matches(self) -> ReviewerResponseV1:
        if sha256_value(self.output) != self.output_digest:
            raise ValueError("Reviewer response digest mismatch")
        return self


class ReviewerReceiptV1(StrictModel):
    contract: Literal["reviewer-receipt/v1"] = "reviewer-receipt/v1"
    request_digest: Sha256
    output_digest: Sha256
    finding_count: int = Field(ge=0)
    requested_model: str
    response_model: str
    provider_request_id: str


class ReviewerRunResultV1(StrictModel):
    contract: Literal["reviewer-run-result/v1"] = "reviewer-run-result/v1"
    skill_id: str
    skill_version: str
    skill_checksum: Sha256
    findings: tuple[ReviewerFindingV1, ...]
    receipt: ReviewerReceiptV1
    result_digest: Sha256

    @model_validator(mode="after")
    def result_checksum_matches(self) -> ReviewerRunResultV1:
        unsigned = self.model_dump(
            mode="json", exclude={"result_digest"}, exclude_none=True
        )
        if sha256_value(unsigned) != self.result_digest:
            raise ValueError("Reviewer result digest mismatch")
        return self


class ReviewerModel(Protocol):
    def review(self, request: ReviewerRequestV1) -> ReviewerResponseV1: ...


class HttpReviewerModel:
    """Internal model-gateway port; it has no Draft or publication capability."""

    def __init__(self, base_url: str, *, timeout_seconds: float = 60.0) -> None:
        normalized = base_url.strip().rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            raise ReviewerError("Model gateway URL must use HTTP or HTTPS")
        self.endpoint = normalized + "/model/v1/ontology-review"
        self.timeout_seconds = timeout_seconds

    def review(self, request: ReviewerRequestV1) -> ReviewerResponseV1:
        body = request.model_dump_json(exclude_none=True).encode("utf-8")
        if len(body) > 2_000_000:
            raise ReviewerError("Reviewer model request exceeds the product limit")
        message = Request(
            self.endpoint,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urlopen(message, timeout=self.timeout_seconds) as response:  # noqa: S310
                payload = response.read(5_000_001)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise ReviewerUnavailable("Reviewer model gateway is unavailable") from exc
        if len(payload) > 5_000_000:
            raise ReviewerError("Reviewer model response exceeds the product limit")
        try:
            return ReviewerResponseV1.model_validate_json(payload)
        except ValueError as exc:
            raise ReviewerError("Reviewer model violated the closed response") from exc


def _finding_id(kind: str, candidate_ids: tuple[str, ...], detail: str) -> str:
    digest = sha256_value(
        {"kind": kind, "candidate_ids": candidate_ids, "detail": detail}
    )
    return f"finding.deterministic.{digest[:24]}"


def deterministic_candidate_findings(
    candidates: tuple[Any, ...],
    *,
    package: OntologyPackage,
    evidence_bundle: EvidenceBundleV1 | None,
) -> tuple[ReviewerFindingV1, ...]:
    """Run bounded structural checks before asking a model for semantic critique."""

    known_sources = {item.id for item in package.sources}
    known_sources.update(
        item.proposed_operation.object_id
        for item in candidates
        if item.candidate_type == "SOURCE" and item.proposed_operation is not None
    )
    known_decisions = {item.id for item in package.decisions}
    findings: list[ReviewerFindingV1] = []
    by_target: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for candidate in candidates:
        operation = candidate.proposed_operation
        if operation is not None:
            by_target[(operation.collection, operation.object_id)].append(candidate)
        if candidate.support_class == "MODEL_INFERRED" and not candidate.source_anchors:
            detail = "Model-inferred candidate has no exact source anchor."
            findings.append(
                ReviewerFindingV1(
                    finding_id=_finding_id(
                        "UNSUPPORTED_CLAIM", (candidate.candidate_id,), detail
                    ),
                    finding_type="UNSUPPORTED_CLAIM",
                    severity="ERROR",
                    summary="模型推断缺少精确证据",
                    detail=detail,
                    candidate_ids=(candidate.candidate_id,),
                    evidence_fragment_ids=(),
                    blocks_release=True,
                    recommendation="补充可引用证据，或拒绝该候选。",
                )
            )
        if not candidate.compile_eligible:
            detail = "Candidate has no typed Draft operation and cannot be applied."
            findings.append(
                ReviewerFindingV1(
                    finding_id=_finding_id(
                        "MISSING_COVERAGE", (candidate.candidate_id,), detail
                    ),
                    finding_type="MISSING_COVERAGE",
                    severity="WARN",
                    summary="候选尚不可写入 Draft",
                    detail=detail,
                    candidate_ids=(candidate.candidate_id,),
                    evidence_fragment_ids=(),
                    blocks_release=candidate.risk_class == "HIGH",
                    recommendation="补齐类型化合同后重新构建，或暂缓该候选。",
                )
            )
        if candidate.draft_diff.change_type == "NO_CHANGE":
            detail = "The typed Candidate is identical to the current Draft object."
            findings.append(
                ReviewerFindingV1(
                    finding_id=_finding_id(
                        "DUPLICATE_CANDIDATE", (candidate.candidate_id,), detail
                    ),
                    finding_type="DUPLICATE_CANDIDATE",
                    severity="INFO",
                    summary="候选与当前 Draft 完全相同",
                    detail=detail,
                    candidate_ids=(candidate.candidate_id,),
                    evidence_fragment_ids=(),
                    blocks_release=False,
                    recommendation="无需重复应用；确认后可拒绝该候选。",
                )
            )
        if operation is None:
            continue
        payload = operation.payload or {}
        if candidate.canonical_target != operation.object_id:
            detail = "Candidate canonical target differs from its typed operation target."
            findings.append(
                ReviewerFindingV1(
                    finding_id=_finding_id(
                        "INCONSISTENT_CONTRACT", (candidate.candidate_id,), detail
                    ),
                    finding_type="INCONSISTENT_CONTRACT",
                    severity="ERROR",
                    summary="候选目标与变更合同不一致",
                    detail=detail,
                    candidate_ids=(candidate.candidate_id,),
                    evidence_fragment_ids=(),
                    blocks_release=True,
                    recommendation="拒绝候选并重新编译类型化变更。",
                )
            )
        source_refs = payload.get("sources", ())
        decision_refs = payload.get("decisions", ())
        missing_sources = sorted(set(source_refs) - known_sources) if isinstance(source_refs, (list, tuple)) else ["<invalid>"]
        missing_decisions = sorted(set(decision_refs) - known_decisions) if isinstance(decision_refs, (list, tuple)) else ["<invalid>"]
        if missing_sources or missing_decisions:
            detail = (
                f"Unknown source refs: {missing_sources or 'none'}; "
                f"unknown decision refs: {missing_decisions or 'none'}."
            )
            findings.append(
                ReviewerFindingV1(
                    finding_id=_finding_id(
                        "BROKEN_REFERENCE", (candidate.candidate_id,), detail
                    ),
                    finding_type="BROKEN_REFERENCE",
                    severity="ERROR",
                    summary="候选引用了不存在的权威对象",
                    detail=detail,
                    candidate_ids=(candidate.candidate_id,),
                    evidence_fragment_ids=(),
                    blocks_release=True,
                    recommendation="先登记缺失来源或决策，再重新生成候选。",
                )
            )

    for target, values in sorted(by_target.items()):
        if len(values) < 2:
            continue
        candidate_ids = tuple(item.candidate_id for item in values)
        detail = f"Multiple candidates write the same Draft target {target[0]}/{target[1]}."
        findings.append(
            ReviewerFindingV1(
                finding_id=_finding_id("DUPLICATE_CANDIDATE", candidate_ids, detail),
                finding_type="DUPLICATE_CANDIDATE",
                severity="ERROR",
                summary="多个候选写入同一 Draft 目标",
                detail=detail,
                candidate_ids=candidate_ids,
                evidence_fragment_ids=(),
                blocks_release=True,
                recommendation="合并为一个候选，或明确拒绝其余重复项。",
            )
        )
    return tuple(findings)


def reviewer_request(
    *,
    run_id: str,
    workspace_id: str,
    base_draft_checksum: str,
    skill: LoadedSkillPackageV1,
    package: OntologyPackage,
    candidates: tuple[Any, ...],
    evidence_bundle: EvidenceBundleV1,
    deterministic_findings: tuple[ReviewerFindingV1, ...],
) -> ReviewerRequestV1:
    fragment_by_anchor = {
        (item.anchor.source_id, item.anchor.snippet_checksum): item.fragment_id
        for item in evidence_bundle.fragments
    }
    projections = tuple(
        ReviewerCandidateProjectionV1(
            candidate_id=item.candidate_id,
            candidate_type=item.candidate_type,
            label=item.label,
            definition=item.definition,
            support_class=item.support_class,
            risk_class=item.risk_class,
            compile_eligible=item.compile_eligible,
            canonical_target=item.canonical_target,
            proposed_operation=item.proposed_operation,
            evidence_fragment_ids=tuple(
                dict.fromkeys(
                    fragment_by_anchor[(anchor.source_id, anchor.snippet_checksum)]
                    for anchor in item.source_anchors
                    if (anchor.source_id, anchor.snippet_checksum) in fragment_by_anchor
                )
            ),
            change_type=item.draft_diff.change_type,
            draft_before=item.draft_diff.before,
            changed_paths=item.draft_diff.changed_paths,
        )
        for item in candidates
    )
    unsigned = {
        "contract": "reviewer-request/v1",
        "run_id": run_id,
        "workspace_id": workspace_id,
        "skill_id": skill.manifest.skill_id,
        "skill_version": skill.manifest.version,
        "skill_checksum": skill.package_checksum,
        "source_set_digest": evidence_bundle.source_set_digest,
        "base_draft_checksum": base_draft_checksum,
        "evidence_fragments": evidence_bundle.fragments,
        "candidates": projections,
        "deterministic_findings": deterministic_findings,
        "draft_context": package.model_dump(mode="json"),
        "allowed_finding_types": tuple(ReviewerFindingType.__args__),
        "max_findings": 256,
    }
    return ReviewerRequestV1(**unsigned, request_digest=sha256_value(unsigned))


class BoundedReviewerOrchestrator:
    """Fresh-context machine review that emits findings and has no decision authority."""

    def __init__(self, *, model: ReviewerModel, skill: LoadedSkillPackageV1) -> None:
        if skill.manifest.role != "REVIEWER":
            raise ReviewerError("Reviewer requires a REVIEWER Skill Package")
        if skill.manifest.direct_draft_write or not skill.manifest.human_review_required:
            raise ReviewerError("Reviewer Skill authority is unsafe")
        self.model = model
        self.skill = skill

    def review(
        self,
        *,
        run_id: str,
        workspace_id: str,
        base_draft_checksum: str,
        package: OntologyPackage,
        candidates: tuple[Any, ...],
        evidence_bundle: EvidenceBundleV1,
    ) -> ReviewerRunResultV1:
        deterministic = deterministic_candidate_findings(
            candidates, package=package, evidence_bundle=evidence_bundle
        )
        request = reviewer_request(
            run_id=run_id,
            workspace_id=workspace_id,
            base_draft_checksum=base_draft_checksum,
            skill=self.skill,
            package=package,
            candidates=candidates,
            evidence_bundle=evidence_bundle,
            deterministic_findings=deterministic,
        )
        response = self.model.review(request)
        output = response.output
        if output.request_digest != request.request_digest or not output.done:
            raise ReviewerError("Reviewer did not close its exact request")
        candidate_ids = {item.candidate_id for item in request.candidates}
        evidence_ids = {item.fragment_id for item in request.evidence_fragments}
        for finding in output.findings:
            if finding.finding_type not in request.allowed_finding_types:
                raise ReviewerError("Reviewer finding escaped its type authority")
            if not set(finding.candidate_ids).issubset(candidate_ids):
                raise ReviewerError("Reviewer cited an unknown candidate")
            if not set(finding.evidence_fragment_ids).issubset(evidence_ids):
                raise ReviewerError("Reviewer cited unknown evidence")
        findings_by_id = {item.finding_id: item for item in deterministic}
        for finding in output.findings:
            if finding.finding_id in findings_by_id:
                raise ReviewerError("Reviewer collided with a deterministic finding")
            findings_by_id[finding.finding_id] = finding
        findings = tuple(findings_by_id.values())
        receipt = ReviewerReceiptV1(
            request_digest=request.request_digest,
            output_digest=response.output_digest,
            finding_count=len(findings),
            requested_model=response.requested_model,
            response_model=response.response_model,
            provider_request_id=response.provider_request_id,
        )
        unsigned = {
            "contract": "reviewer-run-result/v1",
            "skill_id": self.skill.manifest.skill_id,
            "skill_version": self.skill.manifest.version,
            "skill_checksum": self.skill.package_checksum,
            "findings": findings,
            "receipt": receipt,
        }
        return ReviewerRunResultV1(**unsigned, result_digest=sha256_value(unsigned))
