from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Literal, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import Field, model_validator

from ..contracts import Sha256
from ..io import canonical_bytes, sha256_value
from ..models import AuthoringLanguage, GovernedObject, OntologyPackage, StrictModel
from .evidence import (
    EvidenceBundleV1,
    EvidenceFragmentV1,
    UnsupportedEvidenceSourceV1,
    normalize_evidence,
)
from .package_authoring import (
    PackageDraftOperation,
    apply_package_operations,
    package_collection_schemas,
)
from .skill_packages import LoadedSkillPackageV1


BuilderPhase = Literal["SEMANTIC", "ANALYTICS", "DATA"]

PHASE_COLLECTIONS: dict[BuilderPhase, tuple[str, ...]] = {
    "SEMANTIC": ("actors", "processes", "entities", "properties", "relationships"),
    "ANALYTICS": (
        "dimensions",
        "rules",
        "metrics",
        "analysis_patterns",
        "policies",
        "questions",
    ),
    "DATA": ("data_sources", "bindings", "joins", "sql_contracts"),
}

PHASE_PROPOSAL_LIMITS: dict[BuilderPhase, int] = {
    "SEMANTIC": 24,
    "ANALYTICS": 24,
    "DATA": 24,
}

PHASE_EVIDENCE_KIND_PRIORITY: dict[BuilderPhase, tuple[str, ...]] = {
    "SEMANTIC": (
        "data_model",
        "data_dictionary",
        "requirement_transcription",
        "metric_transcription",
        "sql",
    ),
    "ANALYTICS": (
        "metric_transcription",
        "requirement_transcription",
        "sql",
        "data_model",
        "data_dictionary",
    ),
    "DATA": (
        "data_model",
        "data_dictionary",
        "sql",
        "metric_transcription",
        "requirement_transcription",
    ),
}


def _phase_evidence_fragments(
    bundle: EvidenceBundleV1,
    phase: BuilderPhase,
    *,
    limit: int = 160,
) -> tuple[EvidenceFragmentV1, ...]:
    priorities = {
        kind: rank for rank, kind in enumerate(PHASE_EVIDENCE_KIND_PRIORITY[phase])
    }
    ordered = sorted(
        enumerate(bundle.fragments),
        key=lambda indexed: (
            priorities.get(indexed[1].source_kind, len(priorities)),
            indexed[0],
        ),
    )
    return tuple(fragment for _, fragment in ordered[:limit])

_SOURCE_TYPE_BY_KIND: dict[str, str] = {
    "requirement_transcription": "requirement_transcription",
    "metric_transcription": "metric_transcription",
    "data_model": "data_model",
    "data_dictionary": "data_dictionary",
    "sql": "sql",
    "sample_data": "sample_data",
    "other": "public_reference",
}


class BuilderError(RuntimeError):
    """A Builder result cannot cross the typed candidate boundary."""


class BuilderUnavailable(BuilderError):
    """The configured model execution boundary is unavailable."""


class BuildGapV1(StrictModel):
    contract: Literal["builder-gap/v1"] = "builder-gap/v1"
    gap_id: str = Field(pattern=r"^gap\.[A-Za-z0-9][A-Za-z0-9._-]*$")
    category: Literal[
        "MISSING_EVIDENCE",
        "CONFLICT",
        "UNSUPPORTED_FORMAT",
        "INCOMPLETE_CONTRACT",
        "AMBIGUITY",
    ]
    description: str = Field(min_length=1, max_length=2000)
    evidence_fragment_ids: tuple[str, ...] = Field(max_length=32)
    blocking: bool
    clarification_question: str | None = Field(default=None, max_length=1000)


class BuilderProposalV1(StrictModel):
    contract: Literal["builder-proposal/v1"] = "builder-proposal/v1"
    proposal_id: str = Field(pattern=r"^proposal\.[A-Za-z0-9][A-Za-z0-9._-]*$")
    operation: PackageDraftOperation
    evidence_fragment_ids: tuple[str, ...] = Field(min_length=1, max_length=32)
    rationale: str = Field(min_length=1, max_length=2000)
    assumptions: tuple[str, ...] = Field(max_length=16)
    confidence: float = Field(ge=0, le=1)


class BuilderPhaseOutputV1(StrictModel):
    contract: Literal["builder-phase-output/v1"] = "builder-phase-output/v1"
    phase: BuilderPhase
    request_digest: Sha256
    proposals: tuple[BuilderProposalV1, ...] = Field(max_length=64)
    gaps: tuple[BuildGapV1, ...] = Field(max_length=64)
    done: bool

    @model_validator(mode="after")
    def unique_result_identities(self) -> BuilderPhaseOutputV1:
        proposal_ids = [item.proposal_id for item in self.proposals]
        gap_ids = [item.gap_id for item in self.gaps]
        targets = [
            (item.operation.collection, item.operation.object_id)
            for item in self.proposals
        ]
        if len(proposal_ids) != len(set(proposal_ids)):
            raise ValueError("Builder proposal IDs must be unique")
        if len(gap_ids) != len(set(gap_ids)):
            raise ValueError("Builder gap IDs must be unique")
        if len(targets) != len(set(targets)):
            raise ValueError("Builder phase cannot propose one target twice")
        return self


class BuilderPhaseRequestV1(StrictModel):
    contract: Literal["builder-phase-request/v1"] = "builder-phase-request/v1"
    run_id: str = Field(pattern=r"^construction-run\.[0-9a-f]{32}$")
    workspace_id: str = Field(min_length=1, max_length=255)
    phase: BuilderPhase
    skill_id: str
    skill_version: str
    skill_checksum: Sha256
    source_set_digest: Sha256
    authoring_language: AuthoringLanguage | None = None
    language_policy_digest: Sha256 | None = None
    evidence_fragments: tuple[EvidenceFragmentV1, ...] = Field(max_length=256)
    unsupported_sources: tuple[UnsupportedEvidenceSourceV1, ...] = Field(max_length=256)
    draft_context: dict[str, Any]
    prior_operations: tuple[PackageDraftOperation, ...] = Field(max_length=256)
    allowed_collections: tuple[str, ...]
    asset_contract_schemas: dict[str, dict[str, Any]]
    max_proposals: int = Field(ge=1, le=64)
    request_digest: Sha256

    @model_validator(mode="after")
    def digest_and_scope_are_exact(self) -> BuilderPhaseRequestV1:
        expected = PHASE_COLLECTIONS[self.phase]
        if self.allowed_collections != expected:
            raise ValueError("Builder phase collection scope mismatch")
        if set(self.asset_contract_schemas) != set(expected):
            raise ValueError("Builder phase schemas do not match its scope")
        unsigned = self.model_dump(
            mode="json", exclude={"request_digest"}, exclude_none=True
        )
        if sha256_value(unsigned) != self.request_digest:
            raise ValueError("Builder request digest mismatch")
        return self


class BuilderPhaseResponseV1(StrictModel):
    contract: Literal["builder-phase-response/v1"] = "builder-phase-response/v1"
    requested_model: str = Field(min_length=1, max_length=255)
    response_model: str = Field(min_length=1, max_length=255)
    provider_request_id: str = Field(min_length=1, max_length=500)
    output: BuilderPhaseOutputV1
    output_digest: Sha256

    @model_validator(mode="after")
    def output_checksum_matches(self) -> BuilderPhaseResponseV1:
        if sha256_value(self.output) != self.output_digest:
            raise ValueError("Builder response digest mismatch")
        return self


class BuilderPhaseReceiptV1(StrictModel):
    contract: Literal["builder-phase-receipt/v1"] = "builder-phase-receipt/v1"
    phase: BuilderPhase
    request_digest: Sha256
    output_digest: Sha256
    proposal_count: int = Field(ge=0)
    gap_count: int = Field(ge=0)
    requested_model: str
    response_model: str
    provider_request_id: str


class BuilderRunResultV1(StrictModel):
    contract: Literal["builder-run-result/v1"] = "builder-run-result/v1"
    skill_id: str
    skill_version: str
    skill_checksum: Sha256
    evidence_bundle: EvidenceBundleV1
    source_operations: tuple[PackageDraftOperation, ...]
    proposals: tuple[BuilderProposalV1, ...]
    gaps: tuple[BuildGapV1, ...]
    phase_receipts: tuple[BuilderPhaseReceiptV1, ...]
    result_digest: Sha256

    @model_validator(mode="after")
    def result_checksum_matches(self) -> BuilderRunResultV1:
        unsigned = self.model_dump(
            mode="json", exclude={"result_digest"}, exclude_none=True
        )
        if sha256_value(unsigned) != self.result_digest:
            raise ValueError("Builder result digest mismatch")
        return self


class BuilderModel(Protocol):
    def generate(self, request: BuilderPhaseRequestV1) -> BuilderPhaseResponseV1: ...


class HttpBuilderModel:
    """Narrow internal gateway port. Provider credentials never enter Studio API."""

    def __init__(self, base_url: str, *, timeout_seconds: float = 60.0) -> None:
        normalized = base_url.strip().rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            raise BuilderError("Model gateway URL must use HTTP or HTTPS")
        self.endpoint = normalized + "/model/v1/ontology-build"
        self.timeout_seconds = timeout_seconds

    def generate(self, request: BuilderPhaseRequestV1) -> BuilderPhaseResponseV1:
        body = request.model_dump_json(exclude_none=True).encode("utf-8")
        if len(body) > 2_000_000:
            raise BuilderError("Builder model request exceeds the product limit")
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
            raise BuilderUnavailable("Builder model gateway is unavailable") from exc
        if len(payload) > 5_000_000:
            raise BuilderError("Builder model response exceeds the product limit")
        try:
            return BuilderPhaseResponseV1.model_validate_json(payload)
        except ValueError as exc:
            raise BuilderError("Builder model violated the closed response") from exc


def _phase_request(
    *,
    run_id: str,
    workspace_id: str,
    phase: BuilderPhase,
    skill: LoadedSkillPackageV1,
    bundle: EvidenceBundleV1,
    package: OntologyPackage,
    prior_operations: tuple[PackageDraftOperation, ...],
) -> BuilderPhaseRequestV1:
    allowed = PHASE_COLLECTIONS[phase]
    unsigned = {
        "contract": "builder-phase-request/v1",
        "run_id": run_id,
        "workspace_id": workspace_id,
        "phase": phase,
        "skill_id": skill.manifest.skill_id,
        "skill_version": skill.manifest.version,
        "skill_checksum": skill.package_checksum,
        "source_set_digest": bundle.source_set_digest,
        "authoring_language": (
            package.authoring_policy.authoring_language
            if package.authoring_policy is not None
            else None
        ),
        "language_policy_digest": (
            package.authoring_policy.policy_digest
            if package.authoring_policy is not None
            else None
        ),
        "evidence_fragments": _phase_evidence_fragments(bundle, phase),
        "unsupported_sources": bundle.unsupported_sources,
        "draft_context": package.model_dump(mode="json"),
        "prior_operations": prior_operations,
        "allowed_collections": allowed,
        "asset_contract_schemas": package_collection_schemas(allowed),
        "max_proposals": PHASE_PROPOSAL_LIMITS[phase],
    }
    unsigned = {key: value for key, value in unsigned.items() if value is not None}
    return BuilderPhaseRequestV1(**unsigned, request_digest=sha256_value(unsigned))


def _captured_on(asset: dict[str, Any], fallback: date) -> date:
    raw = asset.get("registered_at")
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except ValueError:
            pass
    return fallback


def _source_operations(
    intake: Any,
    *,
    package: OntologyPackage,
) -> tuple[PackageDraftOperation, ...]:
    payload = intake.model_dump(mode="json") if hasattr(intake, "model_dump") else dict(intake)
    assets = payload.get("assets") or payload.get("source_files") or ()
    operations: list[PackageDraftOperation] = []
    for raw in sorted(
        (dict(item) for item in assets if isinstance(item, dict)),
        key=lambda item: str(item.get("asset_id") or item.get("file_id") or ""),
    ):
        source_id = str(raw.get("asset_id") or raw.get("file_id") or "")
        kind = str(raw.get("kind") or raw.get("role") or "other")
        checksum = str(raw.get("checksum") or raw.get("sha256") or "")
        version_id = str(raw.get("source_version_id") or "")
        locator = f"source-library:{version_id}" if version_id else str(raw.get("locator") or "")
        if not source_id or not locator or len(checksum) != 64:
            raise BuilderError("Selected source cannot be registered in the Draft")
        source_type = _SOURCE_TYPE_BY_KIND.get(kind, "public_reference")
        source_payload = {
            "id": source_id,
            "source_type": source_type,
            "title": str(raw.get("title") or raw.get("original_name") or source_id),
            "locator": locator,
            "owner": package.scenario.owner,
            "captured_on": _captured_on(raw, package.created_at.date()).isoformat(),
            "trust": "primary",
            "notes": (
                "Exact registered source version. Content checksum: " + checksum
            ),
        }
        operations.append(
            PackageDraftOperation(
                action="UPSERT",
                collection="sources",
                object_id=source_id,
                payload=source_payload,
            )
        )
    return tuple(operations)


class BoundedBuilderOrchestrator:
    """Bounded model loop that can create candidates but cannot write Draft."""

    def __init__(self, *, model: BuilderModel, skill: LoadedSkillPackageV1) -> None:
        if skill.manifest.role != "BUILDER":
            raise BuilderError("Builder requires a BUILDER Skill Package")
        if skill.manifest.direct_draft_write or not skill.manifest.human_review_required:
            raise BuilderError("Builder Skill authority is unsafe")
        if skill.manifest.max_model_calls < len(PHASE_COLLECTIONS):
            raise BuilderError("Builder Skill model-call budget cannot cover its phases")
        self.model = model
        self.skill = skill

    def build(
        self,
        *,
        run_id: str,
        workspace_id: str,
        intake: Any,
        package: OntologyPackage,
    ) -> BuilderRunResultV1:
        bundle = normalize_evidence(intake, workspace_id=workspace_id)
        source_operations = _source_operations(intake, package=package)
        working = apply_package_operations(package, source_operations)
        known_sources = {item.id for item in working.sources}
        known_decisions = {item.id for item in working.decisions}
        known_fragments = {item.fragment_id for item in bundle.fragments}
        fragment_sources = {
            item.fragment_id: item.source_id for item in bundle.fragments
        }
        proposals: list[BuilderProposalV1] = []
        gaps: list[BuildGapV1] = [
            BuildGapV1(
                gap_id=f"gap.unsupported.{item.source_id}",
                category="UNSUPPORTED_FORMAT",
                description=item.reason,
                evidence_fragment_ids=(),
                blocking=False,
                clarification_question="Can this material be provided as UTF-8 text, CSV or XLSX?",
            )
            for item in bundle.unsupported_sources
        ]
        if not bundle.fragments:
            gaps.append(
                BuildGapV1(
                    gap_id="gap.no_normalized_evidence",
                    category="MISSING_EVIDENCE",
                    description="No selected source produced a normalized evidence fragment.",
                    evidence_fragment_ids=(),
                    blocking=True,
                    clarification_question="Register at least one supported source version before building.",
                )
            )
            return self._result(bundle, source_operations, proposals, gaps, [])

        receipts: list[BuilderPhaseReceiptV1] = []
        seen_targets: set[tuple[str, str]] = set()
        for phase in ("SEMANTIC", "ANALYTICS", "DATA"):
            request = _phase_request(
                run_id=run_id,
                workspace_id=workspace_id,
                phase=phase,
                skill=self.skill,
                bundle=bundle,
                package=working,
                prior_operations=tuple(item.operation for item in proposals),
            )
            response = self.model.generate(request)
            output = response.output
            if (
                output.phase != phase
                or output.request_digest != request.request_digest
                or not output.done
            ):
                raise BuilderError("Builder phase did not close its exact request")
            allowed = set(PHASE_COLLECTIONS[phase])
            for proposal in output.proposals:
                operation = proposal.operation
                target = (operation.collection, operation.object_id)
                if operation.action != "UPSERT" or operation.collection not in allowed:
                    raise BuilderError("Builder proposal escaped its phase authority")
                if target in seen_targets:
                    raise BuilderError("Builder proposed one package target more than once")
                if not set(proposal.evidence_fragment_ids).issubset(known_fragments):
                    raise BuilderError("Builder cited an unknown evidence fragment")
                # Provenance is derived from exact cited fragments. A model may
                # choose evidence, but it cannot invent or omit source authority.
                exact_sources = sorted(
                    {
                        fragment_sources[fragment_id]
                        for fragment_id in proposal.evidence_fragment_ids
                    }
                )
                parsed_payload = dict(operation.payload or {})
                parsed_payload["sources"] = exact_sources
                operation = operation.model_copy(update={"payload": parsed_payload})
                proposal = proposal.model_copy(update={"operation": operation})
                status = parsed_payload.get("status")
                if status not in {"proposed", "needs_clarification"}:
                    raise BuilderError("Builder attempted to manufacture review status")
                source_refs = parsed_payload.get("sources")
                decision_refs = parsed_payload.get("decisions", ())
                if (
                    not isinstance(source_refs, (list, tuple))
                    or not set(source_refs).issubset(known_sources)
                    or not isinstance(decision_refs, (list, tuple))
                    or not set(decision_refs).issubset(known_decisions)
                ):
                    raise BuilderError("Builder invented source or decision authority")
                working = apply_package_operations(working, (operation,))
                seen_targets.add(target)
                proposals.append(proposal)
            for gap in output.gaps:
                if not set(gap.evidence_fragment_ids).issubset(known_fragments):
                    raise BuilderError("Builder gap cited an unknown evidence fragment")
                gaps.append(gap)
            receipts.append(
                BuilderPhaseReceiptV1(
                    phase=phase,
                    request_digest=request.request_digest,
                    output_digest=response.output_digest,
                    proposal_count=len(output.proposals),
                    gap_count=len(output.gaps),
                    requested_model=response.requested_model,
                    response_model=response.response_model,
                    provider_request_id=response.provider_request_id,
                )
            )
        return self._result(bundle, source_operations, proposals, gaps, receipts)

    def _result(
        self,
        bundle: EvidenceBundleV1,
        source_operations: tuple[PackageDraftOperation, ...],
        proposals: list[BuilderProposalV1],
        gaps: list[BuildGapV1],
        receipts: list[BuilderPhaseReceiptV1],
    ) -> BuilderRunResultV1:
        unsigned = {
            "contract": "builder-run-result/v1",
            "skill_id": self.skill.manifest.skill_id,
            "skill_version": self.skill.manifest.version,
            "skill_checksum": self.skill.package_checksum,
            "evidence_bundle": bundle,
            "source_operations": source_operations,
            "proposals": tuple(proposals),
            "gaps": tuple(gaps),
            "phase_receipts": tuple(receipts),
        }
        return BuilderRunResultV1(**unsigned, result_digest=sha256_value(unsigned))
