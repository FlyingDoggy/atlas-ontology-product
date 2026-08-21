from __future__ import annotations

import fcntl
import json
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Literal, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import Field, model_validator
from sqlalchemy import DateTime, String, create_engine, func, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..contracts import Sha256
from ..io import canonical_bytes, sha256_value, write_json
from ..models import OntologyPackage, StrictModel
from ..product_context import (
    Base,
    ExactStoredArtifactRef,
    ProductInfrastructureError,
    ProductInfrastructureSettings,
    S3ArtifactStore,
)
from .package_authoring import PackageDraftOperation, PackageDraftOperationsV1
from .builder import (
    BoundedBuilderOrchestrator,
    BuilderError,
    BuilderRunResultV1,
)
from .construction_jobs import ConstructionJobInputV1
from .evidence import EvidenceNormalizationError, normalize_evidence
from .source_projection import (
    SourceProjectionAnchorV1,
    StudioAuthoringProjectionV1,
)
from .source_observations import (
    SourceObservationError,
    build_source_observations,
)
from .workspace import WorkspaceConflictError
from .workspace_store import StudioWorkspaceHeadRow, WorkspaceStateSubjectV1
from .reviewer import (
    BoundedReviewerOrchestrator,
    ReviewerError,
    ReviewerFindingV1,
    ReviewerRunResultV1,
    deterministic_candidate_findings,
)


class ConstructionError(RuntimeError):
    """A construction run or review could not be completed safely."""


class ConstructionConflict(ConstructionError):
    """An immutable construction result already has a different decision."""


ConstructionCandidateType = Literal[
    "SOURCE",
    "GAP",
    "REQUIREMENT",
    "ACTOR",
    "PROCESS",
    "OBJECT",
    "LINK",
    "PROPERTY",
    "DIMENSION",
    "METRIC",
    "RULE",
    "DATA_SOURCE",
    "MAPPING",
    "JOIN",
    "ANALYSIS_PATTERN",
    "POLICY",
    "QUESTION",
]


class ConstructionSourceSettlementV1(StrictModel):
    contract: Literal["construction-source-settlement/v1"] = (
        "construction-source-settlement/v1"
    )
    source_id: str = Field(min_length=1, max_length=255)
    source_checksum: Sha256
    locator: str = Field(min_length=1, max_length=1000)
    source_kind: str = Field(min_length=1, max_length=100)
    outcome: Literal["SETTLED", "UNSUPPORTED", "FAILED"]
    detail: str = Field(min_length=1, max_length=1000)


class ConstructionStageReceiptV1(StrictModel):
    contract: Literal["construction-stage-receipt/v1"] = (
        "construction-stage-receipt/v1"
    )
    stage: Literal[
        "SOURCE_SETTLEMENT",
        "STRUCTURED_EXTRACTION",
        "BUILDER_AGENT",
        "PACKAGED_CASE_COMPILATION",
        "SEMANTICA_PROPOSAL",
        "CANDIDATE_PRECHECK",
        "REVIEWER_AGENT",
    ]
    status: Literal["PASS", "WARN", "SKIPPED", "FAIL"]
    input_digest: Sha256
    output_digest: Sha256
    item_count: int = Field(ge=0)
    implementation: str = Field(min_length=1, max_length=255)
    detail: str = Field(min_length=1, max_length=1000)


class SemanticaCandidateV1(StrictModel):
    """Closed worker output. It is never a canonical OntologyPackage object."""

    occurrence_id: str = Field(min_length=1, max_length=500)
    candidate_type: Literal["OBJECT", "LINK", "PROPERTY"]
    label: str = Field(min_length=1, max_length=500)
    definition: str = Field(min_length=1, max_length=4000)
    subject: str | None = Field(default=None, max_length=500)
    predicate: str | None = Field(default=None, max_length=500)
    object: str | None = Field(default=None, max_length=500)
    confidence: float = Field(ge=0, le=1)
    source_anchor_ids: tuple[str, ...] = ()


class SemanticaEngineResultV1(StrictModel):
    contract: Literal["semantica-construction-result/v1"] = (
        "semantica-construction-result/v1"
    )
    engine: str = Field(min_length=1, max_length=255)
    build_ref: str = Field(min_length=1, max_length=255)
    candidates: tuple[SemanticaCandidateV1, ...]
    raw_result_digest: Sha256


class SemanticaConstructionRequestV1(StrictModel):
    contract: Literal["semantica-construction-request/v1"] = (
        "semantica-construction-request/v1"
    )
    run_id: str = Field(pattern=r"^construction-run\.[0-9a-f]{32}$")
    workspace_id: str = Field(min_length=1, max_length=255)
    source_set_digest: Sha256
    requirements: tuple[dict[str, Any], ...]
    metric_candidates: tuple[dict[str, Any], ...]
    canonical_context: dict[str, Any]
    proposed_context: dict[str, Any] | None = None


class ConstructionEngine(Protocol):
    def propose(
        self, request: SemanticaConstructionRequestV1
    ) -> SemanticaEngineResultV1: ...


class ConstructionRunStore(Protocol):
    @contextmanager
    def lock(self, workspace_id: str) -> Iterator[None]: ...

    def put_run(self, run: ConstructionRunV1) -> None: ...

    def get_run(self, run_id: str) -> ConstructionRunV1: ...

    def list_runs(self, workspace_id: str) -> tuple[ConstructionRunV1, ...]: ...

    def put_decision(self, decision: ConstructionReviewDecisionV1) -> None: ...

    def get_decision(self, run_id: str) -> ConstructionReviewDecisionV1 | None: ...


class HttpSemanticaConstructionEngine:
    """Narrow HTTP port; Semantica stays outside the Studio API dependency tree."""

    def __init__(self, base_url: str, *, timeout_seconds: float = 20.0) -> None:
        normalized = base_url.strip().rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            raise ConstructionError("Semantica worker URL must use HTTP or HTTPS")
        self.endpoint = normalized + "/v1/proposals"
        self.timeout_seconds = timeout_seconds

    def propose(
        self, request: SemanticaConstructionRequestV1
    ) -> SemanticaEngineResultV1:
        body = request.model_dump_json(exclude_none=True).encode("utf-8")
        if len(body) > 2_000_000:
            raise ConstructionError("Semantica request exceeds the product limit")
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
            raise ConstructionError("Semantica worker is unavailable") from exc
        if len(payload) > 5_000_000:
            raise ConstructionError("Semantica response exceeds the product limit")
        try:
            return SemanticaEngineResultV1.model_validate_json(payload)
        except ValueError as exc:
            raise ConstructionError("Semantica worker violated the closed response") from exc


class CandidateDraftDiffV1(StrictModel):
    contract: Literal["candidate-draft-diff/v1"] = "candidate-draft-diff/v1"
    change_type: Literal[
        "CREATE", "UPDATE", "NO_CHANGE", "NON_COMPILABLE", "UNKNOWN"
    ]
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    changed_paths: tuple[str, ...] = Field(default=(), max_length=128)


class ConstructionCandidateV1(StrictModel):
    contract: Literal["construction-candidate/v1"] = "construction-candidate/v1"
    candidate_id: str = Field(pattern=r"^candidate\.[0-9a-f]{32}$")
    occurrence_key: Sha256
    revision_digest: Sha256
    candidate_type: ConstructionCandidateType
    label: str = Field(min_length=1, max_length=500)
    definition: str = Field(min_length=1, max_length=4000)
    support_class: Literal[
        "DIRECT_EXACT",
        "DERIVED_DETERMINISTIC",
        "MODEL_INFERRED",
        "HEURISTIC",
        "REVIEWER_AUTHORED",
        "SYNTHETIC",
        "MISSING",
    ]
    risk_class: Literal["LOW", "MEDIUM", "HIGH"]
    review_status: Literal["UNREVIEWED"] = "UNREVIEWED"
    compile_eligible: bool
    canonical_target: str | None = None
    proposal: dict[str, Any]
    proposed_operation: PackageDraftOperation | None = None
    source_anchors: tuple[SourceProjectionAnchorV1, ...] = ()
    impact_refs: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    draft_diff: CandidateDraftDiffV1 = Field(
        default_factory=lambda: CandidateDraftDiffV1(change_type="UNKNOWN")
    )

    @model_validator(mode="after")
    def compile_flag_matches_operation(self) -> ConstructionCandidateV1:
        if self.compile_eligible != (self.proposed_operation is not None):
            raise ValueError("Compile eligibility must match the typed operation")
        if not self.compile_eligible and self.draft_diff.change_type not in {
            "NON_COMPILABLE",
            "UNKNOWN",
        }:
            raise ValueError("A non-compilable candidate cannot have a Draft mutation")
        return self


class ConstructionRunV1(StrictModel):
    contract: Literal["construction-run/v1"] = "construction-run/v1"
    run_id: str = Field(pattern=r"^construction-run\.[0-9a-f]{32}$")
    attempt_id: str = Field(pattern=r"^construction-attempt\.[0-9a-f]{32}$")
    lease_epoch: int = Field(ge=1)
    workspace_id: str = Field(min_length=1, max_length=255)
    solution_id: str = Field(min_length=1, max_length=255)
    base_revision: int = Field(ge=1)
    base_draft_checksum: Sha256
    source_set_digest: Sha256
    profile_ref: str = Field(min_length=1, max_length=255)
    status: Literal[
        "QUEUED",
        "RUNNING",
        "NEEDS_REVIEW",
        "FAILED",
        "CANCEL_REQUESTED",
        "CANCELLED",
        "STALE",
    ]
    engine_status: Literal["COMPLETED", "NOT_CONFIGURED", "FAILED"]
    selected_sources: tuple[ConstructionSourceSettlementV1, ...]
    stage_receipts: tuple[ConstructionStageReceiptV1, ...]
    candidates: tuple[ConstructionCandidateV1, ...]
    machine_findings: tuple[ReviewerFindingV1, ...] = ()
    started_at: datetime
    completed_at: datetime | None
    run_checksum: Sha256


class ConstructionDispositionV1(StrictModel):
    candidate_id: str = Field(pattern=r"^candidate\.[0-9a-f]{32}$")
    action: Literal["ACCEPT", "EDIT", "REJECT", "DEFER"]
    note: str = Field(min_length=1, max_length=2000)
    blocks_release: bool
    edited_operation: PackageDraftOperation | None = None

    @model_validator(mode="after")
    def edit_requires_operation(self) -> ConstructionDispositionV1:
        if self.action == "EDIT" and self.edited_operation is None:
            raise ValueError("EDIT requires a typed edited operation")
        if self.action != "EDIT" and self.edited_operation is not None:
            raise ValueError("Only EDIT can carry an edited operation")
        return self


class ConstructionReviewRequestV1(StrictModel):
    contract: Literal["construction-review-request/v1"] = (
        "construction-review-request/v1"
    )
    expected_revision: int = Field(ge=1)
    reviewer: str = Field(min_length=1, max_length=255)
    dispositions: tuple[ConstructionDispositionV1, ...] = Field(min_length=1)
    review_batch_checksum: Sha256 | None = None


class ConstructionReviewDecisionV1(StrictModel):
    contract: Literal["construction-review-decision/v1"] = (
        "construction-review-decision/v1"
    )
    decision_id: str = Field(pattern=r"^construction-decision\.[0-9a-f]{32}$")
    run_id: str = Field(pattern=r"^construction-run\.[0-9a-f]{32}$")
    run_checksum: Sha256
    workspace_id: str = Field(min_length=1, max_length=255)
    base_revision: int = Field(ge=1)
    base_draft_checksum: Sha256
    reviewer: str = Field(min_length=1, max_length=255)
    dispositions: tuple[ConstructionDispositionV1, ...]
    review_batch_checksum: Sha256 | None = None
    request_digest: Sha256
    status: Literal["APPLIED", "APPLIED_WITH_DEFERRED", "REVIEWED_NO_CHANGE"]
    resulting_revision: int = Field(ge=1)
    resulting_draft_checksum: Sha256
    decided_at: datetime
    decision_checksum: Sha256


class ConstructionReviewResultV1(StrictModel):
    decision: ConstructionReviewDecisionV1
    workspace: dict[str, Any]


class FileConstructionRunStore:
    """Immutable local run store. Production can replace this port with PostgreSQL/S3."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    @contextmanager
    def lock(self, workspace_id: str) -> Iterator[None]:
        safe = sha256_value(workspace_id)[:24]
        path = self.root / "locks" / f"{safe}.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+b") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def _run_path(self, run_id: str) -> Path:
        if not run_id.startswith("construction-run."):
            raise ConstructionError("Invalid construction run id")
        return self.root / "runs" / f"{run_id}.json"

    def _decision_path(self, run_id: str) -> Path:
        if not run_id.startswith("construction-run."):
            raise ConstructionError("Invalid construction run id")
        return self.root / "decisions" / f"{run_id}.json"

    @staticmethod
    def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
        write_json(temporary, payload)
        os.replace(temporary, path)

    def put_run(self, run: ConstructionRunV1) -> None:
        path = self._run_path(run.run_id)
        if path.exists():
            if self.get_run(run.run_id) != run:
                raise ConstructionConflict("Construction run id collision")
            return
        self._atomic_write(path, run.model_dump(mode="json"))

    def get_run(self, run_id: str) -> ConstructionRunV1:
        try:
            run = ConstructionRunV1.model_validate_json(
                self._run_path(run_id).read_text(encoding="utf-8")
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise ConstructionError("Construction run is unavailable") from exc
        unsigned = run.model_dump(
            mode="json", exclude={"run_checksum"}, exclude_none=True
        )
        if sha256_value(unsigned) != run.run_checksum:
            raise ConstructionError("Construction run checksum mismatch")
        return run

    def list_runs(self, workspace_id: str) -> tuple[ConstructionRunV1, ...]:
        root = self.root / "runs"
        if not root.exists():
            return ()
        values = tuple(
            self.get_run(path.stem)
            for path in root.glob("construction-run.*.json")
        )
        return tuple(
            sorted(
                (item for item in values if item.workspace_id == workspace_id),
                key=lambda item: item.started_at,
                reverse=True,
            )
        )

    def put_decision(self, decision: ConstructionReviewDecisionV1) -> None:
        path = self._decision_path(decision.run_id)
        if path.exists():
            existing = self.get_decision(decision.run_id)
            if existing != decision:
                raise ConstructionConflict("Construction run already has a decision")
            return
        self._atomic_write(path, decision.model_dump(mode="json"))

    def get_decision(self, run_id: str) -> ConstructionReviewDecisionV1 | None:
        path = self._decision_path(run_id)
        if not path.is_file():
            return None
        try:
            decision = ConstructionReviewDecisionV1.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise ConstructionError("Construction review decision is invalid") from exc
        unsigned = decision.model_dump(
            mode="json", exclude={"decision_checksum"}, exclude_none=True
        )
        if sha256_value(unsigned) != decision.decision_checksum:
            raise ConstructionError("Construction review decision checksum mismatch")
        return decision


class StudioConstructionRunRow(Base):
    __tablename__ = "studio_construction_run"

    run_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    run_checksum: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    subject_checksum: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    subject: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    artifact: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class StudioConstructionDecisionRow(Base):
    __tablename__ = "studio_construction_decision"

    run_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    decision_id: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    workspace_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    decision_checksum: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    subject_checksum: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    subject: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    artifact: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PostgresConstructionRunStore:
    """PostgreSQL authority plus exact S3 run/decision artifacts.

    The run and decision JSON are immutable. Workspace apply can pass the
    decision hook into ``PostgresS3WorkspaceStateStore.commit`` so the new Draft
    head and final human Decision share one database transaction.
    """

    def __init__(self, database_url: str, artifacts: Any) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.artifacts = artifacts

    @classmethod
    def from_settings(
        cls, settings: ProductInfrastructureSettings
    ) -> PostgresConstructionRunStore:
        if settings.mode != "postgresql-s3" or not settings.database_url:
            raise ConstructionError("Construction durable settings are incomplete")
        return cls(settings.database_url, S3ArtifactStore(settings))

    @contextmanager
    def lock(self, workspace_id: str) -> Iterator[None]:
        try:
            with self.engine.connect() as connection:
                connection.execute(
                    text("SELECT pg_advisory_lock(hashtextextended(:key, 0))"),
                    {"key": f"studio-construction:{workspace_id}"},
                )
                try:
                    yield
                finally:
                    connection.execute(
                        text("SELECT pg_advisory_unlock(hashtextextended(:key, 0))"),
                        {"key": f"studio-construction:{workspace_id}"},
                    )
        except ConstructionError:
            raise
        except SQLAlchemyError as exc:
            raise ConstructionError("Construction workspace lock failed") from exc

    def _publish_subject(
        self,
        subject: ConstructionRunV1 | ConstructionReviewDecisionV1,
        *,
        namespace: str,
    ) -> ExactStoredArtifactRef:
        body = canonical_bytes(subject)
        try:
            artifact = self.artifacts.publish_blob(
                body,
                namespace=namespace,
                media_type="application/json",
                suffix="json",
            )
            if self.artifacts.get_exact(artifact) != body:
                raise ConstructionError("Construction artifact read-back mismatch")
        except ProductInfrastructureError as exc:
            raise ConstructionError("Construction artifact store is unavailable") from exc
        return artifact

    def _verify_artifact(
        self,
        subject: ConstructionRunV1 | ConstructionReviewDecisionV1,
        artifact_value: dict[str, object],
    ) -> None:
        try:
            artifact = ExactStoredArtifactRef.model_validate(artifact_value)
            body = self.artifacts.get_exact(artifact)
        except (ValueError, ProductInfrastructureError) as exc:
            raise ConstructionError("Construction exact artifact is unavailable") from exc
        if body != canonical_bytes(subject):
            raise ConstructionError("Construction exact artifact content mismatch")

    @staticmethod
    def _run_from_row(row: StudioConstructionRunRow) -> ConstructionRunV1:
        try:
            run = ConstructionRunV1.model_validate(row.subject)
        except ValueError as exc:
            raise ConstructionError("Construction run database subject is invalid") from exc
        if row.run_checksum != run.run_checksum or row.subject_checksum != sha256_value(run):
            raise ConstructionError("Construction run database identity mismatch")
        return run

    @staticmethod
    def _decision_from_row(
        row: StudioConstructionDecisionRow,
    ) -> ConstructionReviewDecisionV1:
        try:
            decision = ConstructionReviewDecisionV1.model_validate(row.subject)
        except ValueError as exc:
            raise ConstructionError("Construction decision database subject is invalid") from exc
        if (
            row.decision_checksum != decision.decision_checksum
            or row.subject_checksum != sha256_value(decision)
            or row.request_digest != decision.request_digest
        ):
            raise ConstructionError("Construction decision database identity mismatch")
        return decision

    def put_run(self, run: ConstructionRunV1) -> None:
        artifact = self._publish_subject(run, namespace="studio/construction-run")
        subject_checksum = sha256_value(run)
        try:
            with Session(self.engine) as session, session.begin():
                existing = session.get(StudioConstructionRunRow, run.run_id)
                if existing is not None:
                    if self._run_from_row(existing) != run:
                        raise ConstructionConflict("Construction run id collision")
                    return
                session.add(
                    StudioConstructionRunRow(
                        run_id=run.run_id,
                        workspace_id=run.workspace_id,
                        run_checksum=run.run_checksum,
                        subject_checksum=subject_checksum,
                        subject=run.model_dump(mode="json"),
                        artifact=artifact.model_dump(mode="json"),
                        started_at=run.started_at,
                    )
                )
        except ConstructionError:
            raise
        except IntegrityError as exc:
            raise ConstructionConflict("Construction run lost a concurrent insert") from exc
        except SQLAlchemyError as exc:
            raise ConstructionError("Construction run database write failed") from exc

    def get_run(self, run_id: str) -> ConstructionRunV1:
        try:
            with Session(self.engine) as session:
                row = session.get(StudioConstructionRunRow, run_id)
                if row is not None:
                    session.expunge(row)
        except SQLAlchemyError as exc:
            raise ConstructionError("Construction run database read failed") from exc
        if row is None:
            raise ConstructionError("Construction run is unavailable")
        run = self._run_from_row(row)
        self._verify_artifact(run, row.artifact)
        return run

    def list_runs(self, workspace_id: str) -> tuple[ConstructionRunV1, ...]:
        try:
            with Session(self.engine) as session:
                rows = session.execute(
                    select(StudioConstructionRunRow)
                    .where(StudioConstructionRunRow.workspace_id == workspace_id)
                    .order_by(StudioConstructionRunRow.started_at.desc())
                ).scalars().all()
                for row in rows:
                    session.expunge(row)
        except SQLAlchemyError as exc:
            raise ConstructionError("Construction run database list failed") from exc
        values: list[ConstructionRunV1] = []
        for row in rows:
            run = self._run_from_row(row)
            self._verify_artifact(run, row.artifact)
            values.append(run)
        return tuple(values)

    def _insert_decision(
        self,
        session: Session,
        decision: ConstructionReviewDecisionV1,
        artifact: ExactStoredArtifactRef,
    ) -> None:
        run_row = session.get(StudioConstructionRunRow, decision.run_id)
        if run_row is None or run_row.run_checksum != decision.run_checksum:
            raise ConstructionConflict("Construction decision has no exact run authority")
        existing = session.get(StudioConstructionDecisionRow, decision.run_id)
        if existing is not None:
            if self._decision_from_row(existing) != decision:
                raise ConstructionConflict("Construction run already has a decision")
            return
        session.add(
            StudioConstructionDecisionRow(
                run_id=decision.run_id,
                decision_id=decision.decision_id,
                workspace_id=decision.workspace_id,
                request_digest=decision.request_digest,
                decision_checksum=decision.decision_checksum,
                subject_checksum=sha256_value(decision),
                subject=decision.model_dump(mode="json"),
                artifact=artifact.model_dump(mode="json"),
                decided_at=decision.decided_at,
            )
        )

    def decision_transaction_hook(
        self,
        decision: ConstructionReviewDecisionV1,
        supplementary: Callable[[Session], None] | None = None,
    ) -> Callable[[Session], None]:
        artifact = self._publish_subject(
            decision, namespace="studio/construction-decision"
        )

        def insert(session: Session) -> None:
            self._insert_decision(session, decision, artifact)
            if supplementary is not None:
                supplementary(session)

        return insert

    def put_decision(self, decision: ConstructionReviewDecisionV1) -> None:
        artifact = self._publish_subject(
            decision, namespace="studio/construction-decision"
        )
        try:
            with Session(self.engine) as session, session.begin():
                self._insert_decision(session, decision, artifact)
        except ConstructionError:
            raise
        except IntegrityError as exc:
            raise ConstructionConflict("Construction decision lost a concurrent insert") from exc
        except SQLAlchemyError as exc:
            raise ConstructionError("Construction decision database write failed") from exc

    def put_decision_checked(
        self,
        decision: ConstructionReviewDecisionV1,
        supplementary: Callable[[Session], None] | None = None,
    ) -> None:
        """Commit a no-Draft-change decision while proving the same workspace head."""
        artifact = self._publish_subject(
            decision, namespace="studio/construction-decision"
        )
        try:
            with Session(self.engine) as session, session.begin():
                head = session.execute(
                    select(StudioWorkspaceHeadRow)
                    .where(StudioWorkspaceHeadRow.workspace_id == decision.workspace_id)
                    .with_for_update()
                ).scalar_one_or_none()
                if head is None:
                    raise ConstructionConflict("Workspace authority is unavailable")
                subject = WorkspaceStateSubjectV1.model_validate(head.subject)
                if (
                    subject.revision != decision.resulting_revision
                    or subject.payload.get("draft_checksum")
                    != decision.resulting_draft_checksum
                ):
                    raise ConstructionConflict("Workspace changed before review commit")
                self._insert_decision(session, decision, artifact)
                if supplementary is not None:
                    supplementary(session)
        except ConstructionError:
            raise
        except (IntegrityError, SQLAlchemyError, ValueError) as exc:
            raise ConstructionError("Construction no-change decision commit failed") from exc

    def get_decision(self, run_id: str) -> ConstructionReviewDecisionV1 | None:
        try:
            with Session(self.engine) as session:
                row = session.get(StudioConstructionDecisionRow, run_id)
                if row is not None:
                    session.expunge(row)
        except SQLAlchemyError as exc:
            raise ConstructionError("Construction decision database read failed") from exc
        if row is None:
            return None
        decision = self._decision_from_row(row)
        self._verify_artifact(decision, row.artifact)
        return decision


def _as_record(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return dict(value)
    raise ConstructionError("Construction input is not serializable")


def _candidate(
    *,
    candidate_type: ConstructionCandidateType,
    source_key: str,
    label: str,
    definition: str,
    support_class: Literal[
        "DIRECT_EXACT",
        "DERIVED_DETERMINISTIC",
        "MODEL_INFERRED",
        "HEURISTIC",
        "REVIEWER_AUTHORED",
        "SYNTHETIC",
        "MISSING",
    ],
    proposal: dict[str, Any],
    anchor: SourceProjectionAnchorV1 | None = None,
    anchors: tuple[SourceProjectionAnchorV1, ...] = (),
    operation: PackageDraftOperation | None,
    canonical_target: str | None,
    limitations: tuple[str, ...] = (),
) -> ConstructionCandidateV1:
    if anchor is not None and anchors:
        raise ConstructionError("Candidate cannot mix singular and plural anchors")
    source_anchors = anchors or ((anchor,) if anchor is not None else ())
    occurrence = sha256_value(
        {
            "candidate_type": candidate_type,
            "source_key": source_key,
            "source_anchors": source_anchors,
        }
    )
    revision = sha256_value(
        {
            "occurrence_key": occurrence,
            "proposal": proposal,
            "operation": operation,
            "limitations": limitations,
        }
    )
    return ConstructionCandidateV1(
        candidate_id="candidate." + occurrence[:32],
        occurrence_key=occurrence,
        revision_digest=revision,
        candidate_type=candidate_type,
        label=label,
        definition=definition,
        support_class=support_class,
        risk_class=(
            "HIGH"
            if candidate_type
            in {"METRIC", "RULE", "DATA_SOURCE", "MAPPING", "JOIN", "POLICY"}
            else "MEDIUM"
        ),
        compile_eligible=operation is not None,
        canonical_target=canonical_target,
        proposal=proposal,
        proposed_operation=operation,
        source_anchors=source_anchors,
        impact_refs=(canonical_target,) if canonical_target else (),
        limitations=limitations,
        draft_diff=CandidateDraftDiffV1(
            change_type="UNKNOWN" if operation is not None else "NON_COMPILABLE"
        ),
    )


def _changed_paths(before: Any, after: Any, prefix: str = "") -> tuple[str, ...]:
    if before == after:
        return ()
    if isinstance(before, dict) and isinstance(after, dict):
        output: list[str] = []
        for key in sorted(set(before) | set(after)):
            path = f"{prefix}.{key}" if prefix else str(key)
            output.extend(_changed_paths(before.get(key), after.get(key), path))
            if len(output) >= 128:
                break
        return tuple(output[:128])
    if isinstance(before, (list, tuple)) and isinstance(after, (list, tuple)):
        if len(before) != len(after):
            return (prefix or "$",)
        output = []
        for index, (left, right) in enumerate(zip(before, after, strict=True)):
            output.extend(_changed_paths(left, right, f"{prefix}[{index}]"))
            if len(output) >= 128:
                break
        return tuple(output[:128])
    return (prefix or "$",)


def _with_draft_diff(
    candidate: ConstructionCandidateV1,
    package: OntologyPackage,
) -> ConstructionCandidateV1:
    operation = candidate.proposed_operation
    if operation is None:
        return candidate.model_copy(
            update={"draft_diff": CandidateDraftDiffV1(change_type="NON_COMPILABLE")}
        )
    current = next(
        (
            item.model_dump(mode="json")
            for item in getattr(package, operation.collection)
            if item.id == operation.object_id
        ),
        None,
    )
    if operation.action == "UPSERT":
        after = operation.payload
    elif operation.action == "DEPRECATE":
        after = {**(current or {}), "status": "deprecated"}
    else:
        after = current
    change_type: Literal["CREATE", "UPDATE", "NO_CHANGE"] = (
        "CREATE" if current is None else "NO_CHANGE" if current == after else "UPDATE"
    )
    return candidate.model_copy(
        update={
            "draft_diff": CandidateDraftDiffV1(
                change_type=change_type,
                before=current,
                after=after,
                changed_paths=_changed_paths(current, after),
            )
        }
    )


class StudioConstructionService:
    """Product-owned source → candidate → human decision boundary."""

    PROFILE_REF = "construction-profile.generic-builder/v3"
    PACKAGED_COLLECTION_TYPES: dict[str, ConstructionCandidateType] = {
        "actors": "ACTOR",
        "processes": "PROCESS",
        "entities": "OBJECT",
        "properties": "PROPERTY",
        "relationships": "LINK",
        "dimensions": "DIMENSION",
        "rules": "RULE",
        "metrics": "METRIC",
        "data_sources": "DATA_SOURCE",
        "bindings": "MAPPING",
        "joins": "JOIN",
        "analysis_patterns": "ANALYSIS_PATTERN",
        "policies": "POLICY",
        "questions": "QUESTION",
    }

    def __init__(
        self,
        *,
        store: ConstructionRunStore,
        workspace: Any,
        package: OntologyPackage,
        intake: Any,
        authoring: StudioAuthoringProjectionV1,
        engine: ConstructionEngine | None,
        builder: BoundedBuilderOrchestrator | None = None,
        reviewer: BoundedReviewerOrchestrator | None = None,
        review_drafts: Any | None = None,
        selected_source_version_ids: tuple[str, ...] = (),
    ) -> None:
        self.store = store
        self.workspace = workspace
        self.package = package
        self.intake = intake
        self.authoring = authoring
        self.builder = builder
        self.reviewer = reviewer
        self.engine = engine
        self.review_drafts = review_drafts
        self.selected_source_version_ids = selected_source_version_ids

    def _source_settlements(self) -> tuple[ConstructionSourceSettlementV1, ...]:
        assets = tuple(_as_record(item) for item in _as_record(self.intake).get("assets", ()))
        if not assets:
            assets = tuple(
                _as_record(item)
                for item in _as_record(self.intake).get("source_files", ())
            )
        settlements = tuple(
            ConstructionSourceSettlementV1(
                source_id=str(
                    item.get("asset_id")
                    or item.get("file_id")
                    or item.get("source_id")
                ),
                source_checksum=str(item.get("checksum") or item.get("sha256")),
                locator=str(
                    item.get("locator")
                    or item.get("stored_locator")
                    or item.get("file_name")
                ),
                source_kind=str(
                    item.get("kind")
                    or item.get("role")
                    or item.get("media_type")
                ),
                outcome=(
                    "UNSUPPORTED"
                    if item.get("processing_mode") == "REGISTERED_NOT_PARSED"
                    and item.get("source_version_id")
                    and not item.get("source_preview")
                    else "SETTLED"
                ),
                detail=(
                    "Exact source version registered; parsed evidence projection is available."
                    if item.get("source_preview")
                    else "Exact transcribed source version registered."
                    if item.get("processing_mode") == "TRANSCRIBED"
                    else "Exact source version registered; parser stage not enabled for this media type."
                    if item.get("processing_mode") == "REGISTERED_NOT_PARSED"
                    else "Exact registered scenario source settled."
                ),
            )
            for item in assets
        )
        if not settlements:
            raise ConstructionError("No selected source can be settled")
        return settlements

    def _direct_candidates(self) -> tuple[ConstructionCandidateV1, ...]:
        metrics_by_id = {item.id: item for item in self.package.metrics}
        candidates: list[ConstructionCandidateV1] = []
        for requirement in self.authoring.requirements:
            candidates.append(
                _candidate(
                    candidate_type="REQUIREMENT",
                    source_key=requirement.requirement_key,
                    label=requirement.question,
                    definition=requirement.minimum_output,
                    support_class=(
                        "DIRECT_EXACT"
                        if requirement.support_class == "DIRECT_EXACT"
                        else "SYNTHETIC"
                    ),
                    proposal=requirement.model_dump(mode="json"),
                    anchor=requirement.source_anchor,
                    operation=None,
                    canonical_target=None,
                    limitations=("Requirement compiler mapping is not yet declared.",),
                )
            )
        for metric in self.authoring.metric_candidates:
            operation = None
            if metric.canonical_metric_id in metrics_by_id:
                canonical = metrics_by_id[metric.canonical_metric_id]
                replacement = canonical.model_copy(update={"definition": metric.definition})
                operation = PackageDraftOperation.model_validate(
                    {
                        "action": "UPSERT",
                        "collection": "metrics",
                        "object_id": canonical.id,
                        "payload": replacement.model_dump(mode="json"),
                    }
                )
            candidates.append(
                _candidate(
                    candidate_type="METRIC",
                    source_key=metric.metric_key,
                    label=metric.name,
                    definition=metric.definition,
                    support_class=(
                        "DIRECT_EXACT"
                        if metric.support_class == "DIRECT_EXACT"
                        else "SYNTHETIC"
                    ),
                    proposal=metric.model_dump(mode="json"),
                    anchor=metric.source_anchor,
                    operation=operation,
                    canonical_target=metric.canonical_metric_id,
                    limitations=(
                        ()
                        if operation is not None
                        else ("No supported Formula/Query compiler mapping exists yet.",)
                    ),
                )
            )
        try:
            source_observations = build_source_observations(self.intake)
        except SourceObservationError as exc:
            raise ConstructionError("Attachment source projection failed") from exc
        for observation in source_observations:
            candidates.append(
                _candidate(
                    candidate_type=observation.candidate_type,
                    source_key=observation.source_key,
                    label=observation.label,
                    definition=observation.definition,
                    support_class=observation.support_class,
                    proposal=observation.proposal,
                    anchors=observation.source_anchors,
                    operation=None,
                    canonical_target=None,
                    limitations=observation.limitations,
                )
            )
        return tuple(candidates)

    def _builder_candidates(
        self,
        result: BuilderRunResultV1,
    ) -> tuple[ConstructionCandidateV1, ...]:
        anchors_by_fragment = {
            item.fragment_id: item.anchor for item in result.evidence_bundle.fragments
        }
        anchors_by_source: dict[str, list[SourceProjectionAnchorV1]] = {}
        for fragment in result.evidence_bundle.fragments:
            anchors_by_source.setdefault(fragment.source_id, []).append(fragment.anchor)
        output: list[ConstructionCandidateV1] = []
        for operation in result.source_operations:
            payload = operation.payload or {}
            source_anchors = tuple(anchors_by_source.get(operation.object_id, ())[:3])
            output.append(
                _candidate(
                    candidate_type="SOURCE",
                    source_key=f"builder-source:{operation.object_id}",
                    label=str(payload.get("title") or operation.object_id),
                    definition=str(
                        payload.get("notes")
                        or "Exact registered source selected for this Build Run."
                    ),
                    support_class="DIRECT_EXACT",
                    proposal={
                        "contract": "builder-source-registration/v1",
                        "source_id": operation.object_id,
                        "skill_checksum": result.skill_checksum,
                    },
                    anchors=source_anchors,
                    operation=operation,
                    canonical_target=operation.object_id,
                    limitations=(
                        "Registration preserves source identity; it does not approve semantic claims.",
                    ),
                )
            )
        type_by_collection = {
            **self.PACKAGED_COLLECTION_TYPES,
            "sources": "SOURCE",
        }
        for proposal in result.proposals:
            operation = proposal.operation
            payload = operation.payload or {}
            name = payload.get("name")
            label = operation.object_id
            if isinstance(name, dict):
                label = str(name.get("zh") or name.get("en") or label)
            source_anchors = tuple(
                anchors_by_fragment[fragment_id]
                for fragment_id in proposal.evidence_fragment_ids
                if fragment_id in anchors_by_fragment
            )
            limitations = [
                "Builder output is a model-inferred Candidate and requires human disposition.",
                f"Rationale: {proposal.rationale}",
            ]
            limitations.extend(f"Assumption: {item}" for item in proposal.assumptions)
            output.append(
                _candidate(
                    candidate_type=type_by_collection[operation.collection],
                    source_key=f"builder:{proposal.proposal_id}",
                    label=label,
                    definition=str(payload.get("definition") or proposal.rationale),
                    support_class="MODEL_INFERRED",
                    proposal=proposal.model_dump(mode="json"),
                    anchors=source_anchors,
                    operation=operation,
                    canonical_target=operation.object_id,
                    limitations=tuple(limitations),
                )
            )
        for gap in result.gaps:
            source_anchors = tuple(
                anchors_by_fragment[fragment_id]
                for fragment_id in gap.evidence_fragment_ids
                if fragment_id in anchors_by_fragment
            )
            output.append(
                _candidate(
                    candidate_type="GAP",
                    source_key=f"builder:{gap.gap_id}",
                    label=gap.clarification_question or gap.category.replace("_", " ").title(),
                    definition=gap.description,
                    support_class="MISSING",
                    proposal=gap.model_dump(mode="json"),
                    anchors=source_anchors,
                    operation=None,
                    canonical_target=None,
                    limitations=(
                        "This gap remains open until a reviewer resolves or explicitly accepts the boundary.",
                    ),
                )
            )
        return tuple(output)

    @staticmethod
    def _candidate_anchor_score(
        candidate: ConstructionCandidateV1,
        *,
        collection: str,
        item: Any,
    ) -> int:
        if candidate.canonical_target == item.id:
            return 10_000
        proposal_text = json.dumps(
            candidate.proposal,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        ).casefold()
        hints = {
            token
            for token in str(item.id).casefold().replace("-", ".").split(".")
            if len(token) >= 4
        }
        if collection == "bindings":
            hints.add(str(getattr(item, "table", "")).casefold())
            hints.add(str(getattr(item, "column", "")).casefold())
        elif collection == "joins":
            hints.add(str(getattr(item, "left_table", "")).casefold())
            hints.add(str(getattr(item, "right_table", "")).casefold())
        elif collection == "data_sources":
            hints.update(
                str(table.name).casefold() for table in getattr(item, "tables", ())
            )
        return sum(4 for hint in hints if hint and hint in proposal_text)

    def _packaged_case_candidates(
        self,
        direct: tuple[ConstructionCandidateV1, ...],
    ) -> tuple[dict[str, Any] | None, bool, tuple[ConstructionCandidateV1, ...]]:
        """Compile a packaged reference case only when its exact source pack is present.

        The profile is product-owned prior engineering. It supplies typed proposal
        shape, never source truth or publication authority. Every emitted operation
        still requires one explicit human disposition before it reaches Draft.
        """

        intake = _as_record(self.intake)
        profile = intake.get("construction_profile")
        if not isinstance(profile, dict):
            return None, False, ()
        pack = intake.get("reference_source_pack")
        baseline = intake.get("reviewed_baseline")
        if not isinstance(pack, dict) or not isinstance(baseline, dict):
            raise ConstructionError(
                "Packaged construction profile has no source pack or reviewed baseline"
            )
        if (
            profile.get("contract") != "packaged-case-construction-profile/v1"
            or profile.get("package_id") != self.package.package_id
            or profile.get("required_pack_id") != pack.get("pack_id")
            or profile.get("reviewed_baseline_id") != baseline.get("baseline_id")
            or profile.get("human_review_required") is not True
            or profile.get("direct_publish_allowed") is not False
        ):
            raise ConstructionError("Packaged construction profile authority mismatch")

        files = {
            str(item.get("file_id")): item
            for item in pack.get("files", ())
            if isinstance(item, dict)
        }
        expected_sources: dict[str, str] = {}
        for registration in pack.get("registrations", ()):
            if not isinstance(registration, dict):
                raise ConstructionError("Packaged source registration is invalid")
            declared = files.get(str(registration.get("file_id")))
            if declared is None:
                raise ConstructionError("Packaged source registration has no exact file")
            expected_sources[str(registration.get("source_id"))] = str(
                declared.get("sha256")
            )
        assets = {
            str(item.get("asset_id") or item.get("file_id")): item
            for item in intake.get("assets", ())
            if isinstance(item, dict)
        }
        exact_pack_ready = bool(expected_sources) and all(
            source_id in assets
            and str(assets[source_id].get("checksum") or assets[source_id].get("sha256"))
            == checksum
            for source_id, checksum in expected_sources.items()
        )
        if not exact_pack_ready:
            return profile, False, ()

        configured_collections = tuple(profile.get("candidate_collections", ()))
        if (
            not configured_collections
            or len(configured_collections) != len(set(configured_collections))
            or any(
                collection not in self.PACKAGED_COLLECTION_TYPES
                for collection in configured_collections
            )
        ):
            raise ConstructionError("Packaged construction collections are invalid")
        aliases = profile.get("source_aliases")
        if not isinstance(aliases, dict):
            raise ConstructionError("Packaged construction source aliases are invalid")
        normalized_aliases = {
            str(source_ref): tuple(str(value) for value in values)
            for source_ref, values in aliases.items()
            if isinstance(values, (list, tuple))
        }
        if any(
            source_id not in expected_sources
            for source_ids in normalized_aliases.values()
            for source_id in source_ids
        ):
            raise ConstructionError("Packaged construction aliases escape the exact pack")

        existing_targets = {
            (candidate.proposed_operation.collection, candidate.proposed_operation.object_id)
            for candidate in direct
            if candidate.proposed_operation is not None
        }
        output: list[ConstructionCandidateV1] = []
        for collection in configured_collections:
            candidate_type = self.PACKAGED_COLLECTION_TYPES[collection]
            for item in getattr(self.package, collection):
                target = (collection, item.id)
                if target in existing_targets:
                    continue
                source_ids = tuple(
                    dict.fromkeys(
                        source_id
                        for source_ref in item.sources
                        for source_id in normalized_aliases.get(source_ref, ())
                    )
                )
                possible = [
                    candidate
                    for candidate in direct
                    if any(
                        anchor.source_id in source_ids
                        for anchor in candidate.source_anchors
                    )
                ]
                possible.sort(
                    key=lambda candidate: (
                        -self._candidate_anchor_score(
                            candidate,
                            collection=collection,
                            item=item,
                        ),
                        candidate.occurrence_key,
                    )
                )
                anchors: list[SourceProjectionAnchorV1] = []
                seen_anchor_ids: set[tuple[str, str]] = set()
                for candidate in possible:
                    for anchor in candidate.source_anchors:
                        identity = (anchor.source_id, anchor.snippet_checksum)
                        if identity in seen_anchor_ids:
                            continue
                        seen_anchor_ids.add(identity)
                        anchors.append(anchor)
                        if len(anchors) == 3:
                            break
                    if len(anchors) == 3:
                        break

                if collection in {
                    "actors",
                    "processes",
                    "analysis_patterns",
                    "policies",
                    "questions",
                }:
                    support_class = "REVIEWER_AUTHORED"
                elif item.decisions or any(
                    source_ref
                    in {
                        "source.assumption_register",
                        "source.compiler_sql",
                        "source.derived_oracle",
                    }
                    for source_ref in item.sources
                ):
                    support_class = "SYNTHETIC"
                else:
                    support_class = "DERIVED_DETERMINISTIC"
                limitations = [
                    "Typed proposal comes from a product-owned compiler profile plus the internally reviewed baseline; it is not a direct fact extracted from HKEX material.",
                    "Human review is mandatory before this proposal can modify Draft; review still does not publish or activate Agent runtime.",
                ]
                if item.decisions:
                    limitations.append(
                        "Assumption or decision refs: " + ", ".join(item.decisions)
                    )
                if not anchors:
                    limitations.append(
                        "No row-level customer-source anchor exists for this internally engineered object; its package source and decision refs remain explicit."
                    )
                proposal = {
                    "contract": "packaged-case-candidate/v1",
                    "profile_id": str(profile.get("profile_id")),
                    "reviewed_baseline_id": str(baseline.get("baseline_id")),
                    "target_collection": collection,
                    "target_object_id": item.id,
                    "package_source_refs": item.sources,
                    "decision_refs": item.decisions,
                    "claim_ceiling": profile.get("claim_ceiling"),
                    "direct_source_fact": False,
                }
                operation = PackageDraftOperation.model_validate(
                    {
                        "action": "UPSERT",
                        "collection": collection,
                        "object_id": item.id,
                        "payload": item.model_dump(mode="json"),
                    }
                )
                output.append(
                    _candidate(
                        candidate_type=candidate_type,
                        source_key=(
                            f"{profile.get('profile_id')}:{collection}:{item.id}"
                        ),
                        label=item.name.zh or item.name.en,
                        definition=item.definition,
                        support_class=support_class,
                        proposal=proposal,
                        anchors=tuple(anchors),
                        operation=operation,
                        canonical_target=item.id,
                        limitations=tuple(limitations),
                    )
                )
        return profile, True, tuple(output)

    def _engine_candidates(
        self,
        *,
        run_id: str,
        source_set_digest: str,
        builder_result: BuilderRunResultV1 | None,
    ) -> tuple[SemanticaEngineResultV1 | None, tuple[ConstructionCandidateV1, ...]]:
        if self.engine is None:
            return None, ()
        proposed_context = None
        anchors_by_id: dict[str, SourceProjectionAnchorV1] = {}
        if builder_result is not None:
            anchors_by_id = {
                item.fragment_id: item.anchor
                for item in builder_result.evidence_bundle.fragments
            }
            proposed_context = {
                "entities": [
                    item.operation.payload
                    for item in builder_result.proposals
                    if item.operation.collection == "entities"
                ],
                "relationships": [
                    item.operation.payload
                    for item in builder_result.proposals
                    if item.operation.collection == "relationships"
                ],
                "properties": [
                    item.operation.payload
                    for item in builder_result.proposals
                    if item.operation.collection == "properties"
                ],
                "source_anchor_ids": sorted(
                    {
                        fragment_id
                        for item in builder_result.proposals
                        if item.operation.collection
                        in {"entities", "relationships", "properties"}
                        for fragment_id in item.evidence_fragment_ids
                    }
                ),
            }
        request = SemanticaConstructionRequestV1(
            run_id=run_id,
            workspace_id=self.workspace.get().workspace_id,
            source_set_digest=source_set_digest,
            requirements=tuple(
                item.model_dump(mode="json") for item in self.authoring.requirements
            ),
            metric_candidates=tuple(
                item.model_dump(mode="json")
                for item in self.authoring.metric_candidates
            ),
            canonical_context={
                "entities": [item.model_dump(mode="json") for item in self.package.entities],
                "relationships": [
                    item.model_dump(mode="json") for item in self.package.relationships
                ],
            },
            proposed_context=proposed_context,
        )
        result = self.engine.propose(request)
        expected_digest = sha256_value(
            [item.model_dump(mode="json") for item in result.candidates]
        )
        if expected_digest != result.raw_result_digest:
            raise ConstructionError("Semantica worker result digest mismatch")
        projected = tuple(
            _candidate(
                candidate_type=item.candidate_type,
                source_key=f"semantica:{item.occurrence_id}",
                label=item.label,
                definition=item.definition,
                support_class="MODEL_INFERRED",
                proposal=item.model_dump(mode="json"),
                anchors=tuple(
                    anchors_by_id[anchor_id]
                    for anchor_id in item.source_anchor_ids
                    if anchor_id in anchors_by_id
                ),
                operation=None,
                canonical_target=None,
                limitations=(
                    "Semantica is a graph proposal tool; its output requires human compilation.",
                ),
            )
            for item in result.candidates
        )
        return result, projected

    def job_input(self, *, expected_revision: int) -> ConstructionJobInputV1:
        workspace = self.workspace.get()
        if workspace.revision != expected_revision:
            raise WorkspaceConflictError("Draft revision conflict")
        settlements = self._source_settlements()
        source_set_digest = sha256_value(
            [item.model_dump(mode="json") for item in settlements]
        )
        return ConstructionJobInputV1(
            workspace_id=workspace.workspace_id,
            solution_id=workspace.package_id,
            base_revision=workspace.revision,
            base_draft_checksum=workspace.draft_checksum,
            source_set_digest=source_set_digest,
            selected_source_version_ids=self.selected_source_version_ids,
            profile_ref=self.PROFILE_REF,
        )

    def start(
        self,
        *,
        expected_revision: int,
        planned_run_id: str | None = None,
        attempt_id: str | None = None,
        lease_epoch: int = 1,
        commit_fence: Callable[[], None] | None = None,
    ) -> ConstructionRunV1:
        workspace = self.workspace.get()
        if workspace.revision != expected_revision:
            raise WorkspaceConflictError("Draft revision conflict")
        settlements = self._source_settlements()
        source_set_digest = sha256_value(
            [item.model_dump(mode="json") for item in settlements]
        )
        existing = (
            next(
                (
                    item
                    for item in self.store.list_runs(workspace.workspace_id)
                    if item.base_revision == workspace.revision
                    and item.base_draft_checksum == workspace.draft_checksum
                    and item.source_set_digest == source_set_digest
                    and item.profile_ref == self.PROFILE_REF
                ),
                None,
            )
            if planned_run_id is None
            else None
        )
        if existing is not None:
            return existing
        with self.store.lock(workspace.workspace_id):
            # Recheck under the workspace-scoped generation lock.
            existing = (
                next(
                    (
                        item
                        for item in self.store.list_runs(workspace.workspace_id)
                        if item.base_revision == workspace.revision
                        and item.base_draft_checksum == workspace.draft_checksum
                        and item.source_set_digest == source_set_digest
                        and item.profile_ref == self.PROFILE_REF
                    ),
                    None,
                )
                if planned_run_id is None
                else None
            )
            if existing is not None:
                return existing
            started = datetime.now(timezone.utc)
            run_id = planned_run_id or "construction-run." + uuid.uuid4().hex
            direct = self._direct_candidates()
            builder_result: BuilderRunResultV1 | None = None
            builder_error: BuilderError | None = None
            builder_candidates: tuple[ConstructionCandidateV1, ...] = ()
            if self.builder is not None:
                try:
                    builder_result = self.builder.build(
                        run_id=run_id,
                        workspace_id=workspace.workspace_id,
                        intake=self.intake,
                        package=self.package,
                    )
                    builder_candidates = self._builder_candidates(builder_result)
                    direct_targets = {
                        (
                            item.proposed_operation.collection,
                            item.proposed_operation.object_id,
                        )
                        for item in direct
                        if item.proposed_operation is not None
                    }
                    builder_candidates = tuple(
                        item
                        for item in builder_candidates
                        if item.proposed_operation is None
                        or (
                            item.proposed_operation.collection,
                            item.proposed_operation.object_id,
                        )
                        not in direct_targets
                    )
                except BuilderError as exc:
                    builder_error = exc
            # The packaged compiler is a compatibility path for existing Reference
            # Solutions. A successful generic Builder Run must never be overwritten
            # by a reviewed baseline replay.
            if builder_result is None:
                packaged_profile, packaged_ready, packaged_candidates = (
                    self._packaged_case_candidates(direct)
                )
            else:
                packaged_profile, packaged_ready, packaged_candidates = (None, False, ())
            if builder_error is not None and not direct and not packaged_candidates:
                raise ConstructionError("Builder stage failed before producing candidates") from builder_error
            engine_error: Exception | None = None
            try:
                engine_result, engine_candidates = self._engine_candidates(
                    run_id=run_id,
                    source_set_digest=source_set_digest,
                    builder_result=builder_result,
                )
            except Exception as exc:
                engine_error = exc
                engine_result, engine_candidates = (None, ())
            candidates = tuple(
                _with_draft_diff(candidate, self.package)
                for candidate in (
                    *direct,
                    *builder_candidates,
                    *packaged_candidates,
                    *engine_candidates,
                )
            )
            if not candidates:
                raise ConstructionError("Construction produced no candidate denominator")
            evidence_bundle = (
                builder_result.evidence_bundle if builder_result is not None else None
            )
            if evidence_bundle is None:
                try:
                    evidence_bundle = normalize_evidence(
                        self.intake, workspace_id=workspace.workspace_id
                    )
                except EvidenceNormalizationError:
                    evidence_bundle = None
            deterministic_findings = deterministic_candidate_findings(
                candidates,
                package=self.package,
                evidence_bundle=evidence_bundle,
            )
            reviewer_result: ReviewerRunResultV1 | None = None
            reviewer_error: ReviewerError | None = None
            if self.reviewer is not None:
                if evidence_bundle is None:
                    reviewer_error = ReviewerError(
                        "Reviewer has no normalized evidence bundle"
                    )
                else:
                    try:
                        reviewer_result = self.reviewer.review(
                            run_id=run_id,
                            workspace_id=workspace.workspace_id,
                            base_draft_checksum=workspace.draft_checksum,
                            package=self.package,
                            candidates=candidates,
                            evidence_bundle=evidence_bundle,
                        )
                    except ReviewerError as exc:
                        reviewer_error = exc
            machine_findings = (
                reviewer_result.findings
                if reviewer_result is not None
                else deterministic_findings
            )
            structured_digest = sha256_value(
                [item.model_dump(mode="json") for item in direct]
            )
            packaged_digest = sha256_value(
                [item.model_dump(mode="json") for item in packaged_candidates]
                if packaged_candidates
                else {
                    "status": (
                        "NOT_CONFIGURED"
                        if packaged_profile is None
                        else "EXACT_PACK_NOT_INSTALLED"
                    )
                }
            )
            builder_digest = (
                builder_result.result_digest
                if builder_result is not None
                else sha256_value(
                    {
                        "status": "FAILED"
                        if builder_error is not None
                        else "NOT_CONFIGURED"
                    }
                )
            )
            engine_digest = (
                engine_result.raw_result_digest
                if engine_result is not None
                else sha256_value({"status": "NOT_CONFIGURED"})
            )
            reviewer_digest = (
                reviewer_result.result_digest
                if reviewer_result is not None
                else sha256_value(
                    {
                        "status": (
                            "FAILED"
                            if reviewer_error is not None
                            else "NOT_CONFIGURED"
                        ),
                        "deterministic_findings": deterministic_findings,
                    }
                )
            )
            receipts = (
                ConstructionStageReceiptV1(
                    stage="SOURCE_SETTLEMENT",
                    status=(
                        "WARN"
                        if any(item.outcome != "SETTLED" for item in settlements)
                        else "PASS"
                    ),
                    input_digest=source_set_digest,
                    output_digest=source_set_digest,
                    item_count=len(settlements),
                    implementation="ontology-studio/source-registry@1",
                    detail=(
                        "Every selected exact source has one terminal settlement; unsupported media remain explicit."
                    ),
                ),
                ConstructionStageReceiptV1(
                    stage="STRUCTURED_EXTRACTION",
                    status="PASS",
                    input_digest=source_set_digest,
                    output_digest=structured_digest,
                    item_count=len(direct),
                    implementation="ontology-studio/transcription-projector@1",
                    detail=(
                        "Requirements, metrics and supported attachments were projected with exact anchors."
                    ),
                ),
                ConstructionStageReceiptV1(
                    stage="BUILDER_AGENT",
                    status=(
                        "PASS"
                        if builder_result is not None
                        else "FAIL"
                        if builder_error is not None
                        else "SKIPPED"
                    ),
                    input_digest=source_set_digest,
                    output_digest=builder_digest,
                    item_count=len(builder_candidates),
                    implementation=(
                        f"{builder_result.skill_id}@{builder_result.skill_version}"
                        if builder_result is not None
                        else "not-configured"
                        if builder_error is None
                        else "configured-unavailable"
                    ),
                    detail=(
                        "The versioned Build Skill produced typed Candidates and explicit Gaps; Draft remains unchanged."
                        if builder_result is not None
                        else "The Builder failed; deterministic source candidates remain available."
                        if builder_error is not None
                        else "No Builder runtime is configured; compatibility construction remains available."
                    ),
                ),
                ConstructionStageReceiptV1(
                    stage="PACKAGED_CASE_COMPILATION",
                    status=(
                        "PASS"
                        if packaged_ready
                        else "SKIPPED"
                    ),
                    input_digest=structured_digest,
                    output_digest=packaged_digest,
                    item_count=len(packaged_candidates),
                    implementation=(
                        str(packaged_profile.get("profile_id"))
                        if packaged_profile is not None
                        else "not-configured"
                    ),
                    detail=(
                        "The exact reference pack matched; the product-owned case profile emitted typed candidates that still require human review."
                        if packaged_ready
                        else "No packaged case compiler is configured for this solution."
                        if packaged_profile is None
                        else "The packaged compiler stayed closed because the complete exact reference pack is not installed."
                    ),
                ),
                ConstructionStageReceiptV1(
                    stage="SEMANTICA_PROPOSAL",
                    status=(
                        "PASS"
                        if engine_result is not None
                        else "WARN"
                        if engine_error is not None
                        else "SKIPPED"
                    ),
                    input_digest=packaged_digest,
                    output_digest=engine_digest,
                    item_count=len(engine_candidates),
                    implementation=(
                        f"{engine_result.engine}/{engine_result.build_ref}"
                        if engine_result is not None
                        else "degraded-unavailable"
                        if engine_error is not None
                        else "not-configured"
                    ),
                    detail=(
                        "Semantica returned an isolated proposal; it has no Draft authority."
                        if engine_result is not None
                        else "Semantica was unavailable; Builder and source-supported candidates remain usable."
                        if engine_error is not None
                        else "Source-supported candidates remain usable; no Semantica success is claimed."
                    ),
                ),
                ConstructionStageReceiptV1(
                    stage="CANDIDATE_PRECHECK",
                    status="WARN" if any(not item.compile_eligible for item in candidates) else "PASS",
                    input_digest=sha256_value(
                        [item.revision_digest for item in candidates]
                    ),
                    output_digest=sha256_value(
                        {
                            "compile_eligible": sum(
                                item.compile_eligible for item in candidates
                            ),
                            "total": len(candidates),
                        }
                    ),
                    item_count=len(candidates),
                    implementation="ontology-studio/candidate-precheck@1",
                    detail="Compile-ineligible items remain explicit and cannot be accepted.",
                ),
                ConstructionStageReceiptV1(
                    stage="REVIEWER_AGENT",
                    status=(
                        "PASS"
                        if reviewer_result is not None
                        else "WARN"
                        if reviewer_error is not None
                        else "SKIPPED"
                    ),
                    input_digest=sha256_value(
                        [item.revision_digest for item in candidates]
                    ),
                    output_digest=reviewer_digest,
                    item_count=len(machine_findings),
                    implementation=(
                        f"{reviewer_result.skill_id}@{reviewer_result.skill_version}"
                        if reviewer_result is not None
                        else "deterministic-review-only"
                    ),
                    detail=(
                        "The independent Review Skill produced machine findings; only a human can disposition Candidates."
                        if reviewer_result is not None
                        else "The Reviewer model was unavailable; deterministic findings remain visible."
                        if reviewer_error is not None
                        else "No Reviewer model is configured; deterministic findings remain visible."
                    ),
                ),
            )
            unsigned = {
                "contract": "construction-run/v1",
                "run_id": run_id,
                "attempt_id": attempt_id or "construction-attempt." + uuid.uuid4().hex,
                "lease_epoch": lease_epoch,
                "workspace_id": workspace.workspace_id,
                "solution_id": workspace.package_id,
                "base_revision": workspace.revision,
                "base_draft_checksum": workspace.draft_checksum,
                "source_set_digest": source_set_digest,
                "profile_ref": self.PROFILE_REF,
                "status": "NEEDS_REVIEW",
                "engine_status": (
                    "COMPLETED"
                    if builder_result is not None or engine_result is not None
                    else "FAILED"
                    if builder_error is not None or engine_error is not None
                    else "NOT_CONFIGURED"
                ),
                "selected_sources": settlements,
                "stage_receipts": receipts,
                "candidates": candidates,
                "machine_findings": machine_findings,
                "started_at": started,
                "completed_at": datetime.now(timezone.utc),
            }
            provisional = ConstructionRunV1(**unsigned, run_checksum="0" * 64)
            checksum_payload = provisional.model_dump(
                mode="json", exclude={"run_checksum"}, exclude_none=True
            )
            run = provisional.model_copy(
                update={"run_checksum": sha256_value(checksum_payload)}
            )
            # Re-read the mutable Draft and acquire the external job commit
            # fence immediately before publishing the immutable run. A change
            # or user cancellation therefore wins before the run is visible;
            # after this fence, the result commit wins and cancellation becomes
            # a no-op rather than a misleading CANCELLED terminal state.
            current = self.workspace.get(workspace.workspace_id)
            if (
                current.revision != workspace.revision
                or current.draft_checksum != workspace.draft_checksum
            ):
                raise WorkspaceConflictError("Construction result is stale for the current draft")
            if commit_fence is not None:
                commit_fence()
            self.store.put_run(run)
            return run

    def get(self, run_id: str) -> ConstructionRunV1:
        return self.store.get_run(run_id)

    def list(self) -> tuple[tuple[ConstructionRunV1, ConstructionReviewDecisionV1 | None], ...]:
        workspace_id = self.workspace.get().workspace_id
        return tuple(
            (run, self.store.get_decision(run.run_id))
            for run in self.store.list_runs(workspace_id)
        )

    def review(
        self,
        run_id: str,
        request: ConstructionReviewRequestV1,
    ) -> ConstructionReviewResultV1:
        run = self.get(run_id)
        review_batch = None
        if self.review_drafts is not None:
            review_batch = self.review_drafts.get(run_id)
            if review_batch is None or request.review_batch_checksum is None:
                raise ConstructionConflict(
                    "Final review requires one persisted review batch"
                )
            if review_batch.status != "DRAFT":
                raise ConstructionConflict("Review batch is already final")
            if review_batch.batch_checksum != request.review_batch_checksum:
                raise ConstructionConflict("Review batch checksum mismatch")
            if review_batch.dispositions != request.dispositions:
                raise ConstructionConflict("Final dispositions differ from review batch")
        request_digest = sha256_value(request)
        with self.store.lock(run.workspace_id):
            existing = self.store.get_decision(run_id)
            if existing is not None:
                if existing.request_digest != request_digest:
                    raise ConstructionConflict(
                        "Construction run already has a different final decision"
                    )
                return ConstructionReviewResultV1(
                    decision=existing,
                    workspace=self.workspace.get(run.workspace_id).model_dump(mode="json"),
                )
            current = self.workspace.get(run.workspace_id)
            if (
                request.expected_revision != run.base_revision
                or current.revision != run.base_revision
                or current.draft_checksum != run.base_draft_checksum
            ):
                raise WorkspaceConflictError(
                    "Construction run is stale for the current draft"
                )
            by_id = {item.candidate_id: item for item in run.candidates}
            disposition_ids = tuple(item.candidate_id for item in request.dispositions)
            if len(disposition_ids) != len(set(disposition_ids)):
                raise ValueError("A candidate can have only one disposition")
            if set(disposition_ids) != set(by_id):
                raise ValueError("Every candidate requires one final disposition")
            operations: list[PackageDraftOperation] = []
            deferred = False
            for disposition in request.dispositions:
                candidate = by_id[disposition.candidate_id]
                if disposition.action == "ACCEPT":
                    if not candidate.compile_eligible or candidate.proposed_operation is None:
                        raise ValueError("Candidate is not compile eligible")
                    operations.append(candidate.proposed_operation)
                elif disposition.action == "EDIT":
                    assert disposition.edited_operation is not None
                    operations.append(disposition.edited_operation)
                elif disposition.action == "DEFER":
                    deferred = True
            if len({(item.collection, item.object_id) for item in operations}) != len(
                operations
            ):
                raise ValueError("Review would mutate one canonical target twice")
            status: Literal["APPLIED", "APPLIED_WITH_DEFERRED", "REVIEWED_NO_CHANGE"]
            if operations:
                status = "APPLIED_WITH_DEFERRED" if deferred else "APPLIED"
            else:
                status = "REVIEWED_NO_CHANGE"
            decided_at = datetime.now(timezone.utc)

            def decision_for(resulting_workspace: Any) -> ConstructionReviewDecisionV1:
                unsigned = {
                    "contract": "construction-review-decision/v1",
                    "decision_id": "construction-decision." + uuid.uuid4().hex,
                    "run_id": run.run_id,
                    "run_checksum": run.run_checksum,
                    "workspace_id": run.workspace_id,
                    "base_revision": run.base_revision,
                    "base_draft_checksum": run.base_draft_checksum,
                    "reviewer": request.reviewer,
                    "dispositions": request.dispositions,
                    "review_batch_checksum": request.review_batch_checksum,
                    "request_digest": request_digest,
                    "status": status,
                    "resulting_revision": resulting_workspace.revision,
                    "resulting_draft_checksum": resulting_workspace.draft_checksum,
                    "decided_at": decided_at,
                }
                provisional = ConstructionReviewDecisionV1(
                    **unsigned,
                    decision_checksum="0" * 64,
                )
                checksum_payload = provisional.model_dump(
                    mode="json", exclude={"decision_checksum"}, exclude_none=True
                )
                return provisional.model_copy(
                    update={"decision_checksum": sha256_value(checksum_payload)}
                )

            resulting = current
            decision: ConstructionReviewDecisionV1
            if operations and isinstance(self.store, PostgresConstructionRunStore):
                decision_holder: list[ConstructionReviewDecisionV1] = []

                def hook_factory(resulting_workspace: Any) -> Callable[[Session], None]:
                    built = decision_for(resulting_workspace)
                    decision_holder.append(built)
                    supplementary = (
                        self.review_drafts.finalization_hook(
                            run.run_id,
                            request.review_batch_checksum,
                            built.decision_id,
                        )
                        if review_batch is not None
                        and request.review_batch_checksum is not None
                        else None
                    )
                    return self.store.decision_transaction_hook(
                        built, supplementary=supplementary
                    )

                resulting = self.workspace.apply_package_operations(
                    PackageDraftOperationsV1(
                        expected_revision=current.revision,
                        operations=tuple(operations),
                    ),
                    workspace_id=run.workspace_id,
                    transaction_hook_factory=hook_factory,
                )
                if len(decision_holder) != 1:
                    raise ConstructionError("Review decision transaction was not formed")
                decision = decision_holder[0]
            elif operations:
                resulting = self.workspace.apply_package_operations(
                    PackageDraftOperationsV1(
                        expected_revision=current.revision,
                        operations=tuple(operations),
                    ),
                    workspace_id=run.workspace_id,
                )
                decision = decision_for(resulting)
                self.store.put_decision(decision)
                if review_batch is not None and request.review_batch_checksum is not None:
                    self.review_drafts.finalization_hook(
                        run.run_id,
                        request.review_batch_checksum,
                        decision.decision_id,
                    )(None)
            else:
                decision = decision_for(resulting)
                if isinstance(self.store, PostgresConstructionRunStore):
                    supplementary = (
                        self.review_drafts.finalization_hook(
                            run.run_id,
                            request.review_batch_checksum,
                            decision.decision_id,
                        )
                        if review_batch is not None
                        and request.review_batch_checksum is not None
                        else None
                    )
                    self.store.put_decision_checked(
                        decision, supplementary=supplementary
                    )
                else:
                    self.store.put_decision(decision)
                    if review_batch is not None and request.review_batch_checksum is not None:
                        self.review_drafts.finalization_hook(
                            run.run_id,
                            request.review_batch_checksum,
                            decision.decision_id,
                        )(None)
            return ConstructionReviewResultV1(
                decision=decision,
                workspace=resulting.model_dump(mode="json"),
            )
