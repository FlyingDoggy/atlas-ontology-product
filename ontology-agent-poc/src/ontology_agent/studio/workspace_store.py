from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Literal, Protocol

from pydantic import Field, model_validator
from sqlalchemy import DateTime, Integer, String, create_engine, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..contracts import Sha256
from ..io import canonical_bytes, sha256_value
from ..models import StrictModel
from ..product_context import (
    Base,
    ExactStoredArtifactRef,
    ProductInfrastructureError,
    ProductInfrastructureSettings,
    S3ArtifactStore,
)


WORKSPACE_STATE_CONTRACT = "studio-workspace-state/v1"
WORKSPACE_STATE_RECORD_CONTRACT = "studio-workspace-state-record/v1"
WORKSPACE_REVISION_CONTRACT = "studio-draft-revision-artifact/v1"


class WorkspaceStoreError(RuntimeError):
    """Workspace authority cannot be read or committed safely."""


class WorkspaceStoreConflict(WorkspaceStoreError):
    """The expected workspace head no longer matches durable authority."""


class WorkspaceIdentity(StrictModel):
    solution_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    solution_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    workspace_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    studio_adapter_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._@-]*$")


class WorkspaceStateSubjectV1(StrictModel):
    contract: Literal["studio-workspace-state/v1"] = WORKSPACE_STATE_CONTRACT
    identity: WorkspaceIdentity
    generation: int = Field(ge=1)
    workspace_schema: str = Field(min_length=1, max_length=255)
    revision: int = Field(ge=1)
    payload_checksum: Sha256
    payload: dict[str, Any]

    @model_validator(mode="after")
    def validate_payload_identity(self) -> WorkspaceStateSubjectV1:
        if sha256_value(self.payload) != self.payload_checksum:
            raise ValueError("Workspace payload checksum mismatch")
        if self.payload.get("workspace_id") != self.identity.workspace_id:
            raise ValueError("Workspace payload has a different workspace identity")
        if self.payload.get("package_id") != self.identity.solution_id:
            raise ValueError("Workspace payload has a different solution identity")
        if self.payload.get("schema_version") != self.workspace_schema:
            raise ValueError("Workspace payload schema identity mismatch")
        if self.payload.get("revision") != self.revision:
            raise ValueError("Workspace payload revision mismatch")
        return self


class WorkspaceStateRecordV1(StrictModel):
    contract: Literal["studio-workspace-state-record/v1"] = (
        WORKSPACE_STATE_RECORD_CONTRACT
    )
    persistence: Literal["postgresql-s3"] = "postgresql-s3"
    subject_checksum: Sha256
    subject: WorkspaceStateSubjectV1
    artifact: ExactStoredArtifactRef

    @model_validator(mode="after")
    def validate_artifact_identity(self) -> WorkspaceStateRecordV1:
        if sha256_value(self.subject) != self.subject_checksum:
            raise ValueError("Workspace subject checksum mismatch")
        if self.artifact.sha256 != self.subject_checksum:
            raise ValueError("Workspace artifact identity mismatch")
        return self


class WorkspaceRevisionSubjectV1(StrictModel):
    contract: Literal["studio-draft-revision-artifact/v1"] = (
        WORKSPACE_REVISION_CONTRACT
    )
    identity: WorkspaceIdentity
    revision: int = Field(ge=1)
    draft_checksum: Sha256
    record_checksum: Sha256
    payload: dict[str, Any]

    @model_validator(mode="after")
    def validate_revision_payload(self) -> WorkspaceRevisionSubjectV1:
        if self.payload.get("workspace_id") != self.identity.workspace_id:
            raise ValueError("Draft revision has a different workspace identity")
        if self.payload.get("revision") != self.revision:
            raise ValueError("Draft revision number mismatch")
        if self.payload.get("draft_checksum") != self.draft_checksum:
            raise ValueError("Draft revision checksum identity mismatch")
        if self.payload.get("record_checksum") != self.record_checksum:
            raise ValueError("Draft revision record identity mismatch")
        return self


def _same_revision_content(
    left: WorkspaceRevisionSubjectV1,
    right: WorkspaceRevisionSubjectV1,
) -> bool:
    """Compare revision meaning across the pre-package-operations wire shape.

    v0.9 revision artifacts omitted the optional ``package_operations`` member;
    the first v0.10 serializer emitted it as JSON null.  Both represent the same
    immutable revision because the signed record checksum was calculated with
    the member omitted.  Keep this compatibility narrow: a non-null operation
    list is still a different immutable revision.
    """

    def normalized(subject: WorkspaceRevisionSubjectV1) -> dict[str, Any]:
        value = subject.model_dump(mode="json")
        payload = dict(value["payload"])
        if payload.get("package_operations") is None:
            payload.pop("package_operations", None)
        value["payload"] = payload
        return value

    return normalized(left) == normalized(right)


class WorkspaceRevisionRecordV1(StrictModel):
    persistence: Literal["postgresql-s3"] = "postgresql-s3"
    subject_checksum: Sha256
    subject: WorkspaceRevisionSubjectV1
    artifact: ExactStoredArtifactRef

    @model_validator(mode="after")
    def validate_artifact_identity(self) -> WorkspaceRevisionRecordV1:
        if sha256_value(self.subject) != self.subject_checksum:
            raise ValueError("Draft revision subject checksum mismatch")
        if self.artifact.sha256 != self.subject_checksum:
            raise ValueError("Draft revision artifact identity mismatch")
        return self


@dataclass(frozen=True, slots=True)
class LoadedWorkspaceState:
    record: WorkspaceStateRecordV1

    @property
    def payload(self) -> dict[str, Any]:
        return self.record.subject.payload

    @property
    def token(self) -> str:
        return self.record.subject_checksum


class WorkspaceArtifactStore(Protocol):
    def publish_blob(
        self,
        body: bytes,
        *,
        namespace: str,
        media_type: str,
        suffix: str,
    ) -> ExactStoredArtifactRef: ...

    def get_exact(self, ref: ExactStoredArtifactRef) -> bytes: ...


class WorkspaceStateStore(Protocol):
    def load(self, identity: WorkspaceIdentity) -> LoadedWorkspaceState | None: ...

    def commit(
        self,
        identity: WorkspaceIdentity,
        *,
        payload: dict[str, Any],
        revision_payload: dict[str, Any],
        expected_subject_checksum: str | None,
        transaction_hook: Callable[[Session], None] | None = None,
    ) -> LoadedWorkspaceState: ...

    def list_revisions(
        self, identity: WorkspaceIdentity
    ) -> tuple[WorkspaceRevisionRecordV1, ...]: ...


class StudioWorkspaceHeadRow(Base):
    __tablename__ = "studio_workspace_head"

    workspace_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    solution_id: Mapped[str] = mapped_column(String(255), nullable=False)
    solution_version: Mapped[str] = mapped_column(String(64), nullable=False)
    studio_adapter_id: Mapped[str] = mapped_column(String(255), nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    subject_checksum: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    subject: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    artifact: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class StudioDraftRevisionRow(Base):
    __tablename__ = "studio_draft_revision"

    workspace_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    solution_id: Mapped[str] = mapped_column(String(255), nullable=False)
    solution_version: Mapped[str] = mapped_column(String(64), nullable=False)
    studio_adapter_id: Mapped[str] = mapped_column(String(255), nullable=False)
    draft_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    record_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_checksum: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    subject: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    artifact: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PostgresS3WorkspaceStateStore:
    """One durable workspace authority: PostgreSQL CAS plus exact S3 bytes."""

    def __init__(
        self,
        database_url: str,
        artifacts: WorkspaceArtifactStore,
    ) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.artifacts = artifacts

    @classmethod
    def from_settings(
        cls, settings: ProductInfrastructureSettings
    ) -> PostgresS3WorkspaceStateStore:
        if settings.mode != "postgresql-s3" or not settings.database_url:
            raise WorkspaceStoreError("Durable workspace settings are incomplete")
        return cls(settings.database_url, S3ArtifactStore(settings))

    @staticmethod
    def _state_record(row: StudioWorkspaceHeadRow) -> WorkspaceStateRecordV1:
        return WorkspaceStateRecordV1(
            subject_checksum=row.subject_checksum,
            subject=WorkspaceStateSubjectV1.model_validate(row.subject),
            artifact=ExactStoredArtifactRef.model_validate(row.artifact),
        )

    @staticmethod
    def _revision_record(row: StudioDraftRevisionRow) -> WorkspaceRevisionRecordV1:
        return WorkspaceRevisionRecordV1(
            subject_checksum=row.subject_checksum,
            subject=WorkspaceRevisionSubjectV1.model_validate(row.subject),
            artifact=ExactStoredArtifactRef.model_validate(row.artifact),
        )

    @staticmethod
    def _assert_identity(actual: WorkspaceIdentity, expected: WorkspaceIdentity) -> None:
        # Registration/package delivery versions may advance while the installed
        # adapter and workspace authority remain the same. The stable ownership key
        # is solution + workspace + adapter; solution_version is retained as the
        # version that authored each exact record, not used to fork mutable authority.
        if (
            actual.solution_id != expected.solution_id
            or actual.workspace_id != expected.workspace_id
            or actual.studio_adapter_id != expected.studio_adapter_id
        ):
            raise WorkspaceStoreError("Workspace durable identity mismatch")

    def _verify_state_record(
        self, record: WorkspaceStateRecordV1, identity: WorkspaceIdentity
    ) -> LoadedWorkspaceState:
        self._assert_identity(record.subject.identity, identity)
        try:
            body = self.artifacts.get_exact(record.artifact)
        except ProductInfrastructureError as exc:
            raise WorkspaceStoreError("Workspace exact artifact is unavailable") from exc
        if body != canonical_bytes(record.subject):
            raise WorkspaceStoreError("Workspace exact artifact content mismatch")
        return LoadedWorkspaceState(record)

    def load(self, identity: WorkspaceIdentity) -> LoadedWorkspaceState | None:
        try:
            with Session(self.engine) as session:
                row = session.get(StudioWorkspaceHeadRow, identity.workspace_id)
                if row is not None:
                    session.expunge(row)
        except SQLAlchemyError as exc:
            raise WorkspaceStoreError("Workspace database read failed") from exc
        if row is None:
            return None
        try:
            record = self._state_record(row)
        except ValueError as exc:
            raise WorkspaceStoreError("Workspace database record is invalid") from exc
        return self._verify_state_record(record, identity)

    def commit(
        self,
        identity: WorkspaceIdentity,
        *,
        payload: dict[str, Any],
        revision_payload: dict[str, Any],
        expected_subject_checksum: str | None,
        transaction_hook: Callable[[Session], None] | None = None,
    ) -> LoadedWorkspaceState:
        try:
            with Session(self.engine) as session, session.begin():
                current = session.execute(
                    select(StudioWorkspaceHeadRow)
                    .where(StudioWorkspaceHeadRow.workspace_id == identity.workspace_id)
                    .with_for_update()
                ).scalar_one_or_none()
                if current is None:
                    if expected_subject_checksum is not None:
                        raise WorkspaceStoreConflict("Workspace head no longer exists")
                    generation = 1
                else:
                    persisted_identity = WorkspaceIdentity(
                        solution_id=current.solution_id,
                        solution_version=current.solution_version,
                        workspace_id=current.workspace_id,
                        studio_adapter_id=current.studio_adapter_id,
                    )
                    self._assert_identity(persisted_identity, identity)
                    if current.subject_checksum != expected_subject_checksum:
                        raise WorkspaceStoreConflict("Workspace head changed")
                    generation = current.generation + 1

                try:
                    subject = WorkspaceStateSubjectV1(
                        identity=identity,
                        generation=generation,
                        workspace_schema=str(payload["schema_version"]),
                        revision=int(payload["revision"]),
                        payload_checksum=sha256_value(payload),
                        payload=payload,
                    )
                    revision_subject = WorkspaceRevisionSubjectV1(
                        identity=identity,
                        revision=int(revision_payload["revision"]),
                        draft_checksum=str(revision_payload["draft_checksum"]),
                        record_checksum=str(revision_payload["record_checksum"]),
                        payload=revision_payload,
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    raise WorkspaceStoreError("Workspace commit payload is invalid") from exc

                if current is not None:
                    current_subject = WorkspaceStateSubjectV1.model_validate(current.subject)
                    if current_subject.payload == subject.payload:
                        session.expunge(current)
                        return self._verify_state_record(
                            self._state_record(current), identity
                        )
                    if subject.revision not in {
                        current_subject.revision,
                        current_subject.revision + 1,
                    }:
                        raise WorkspaceStoreConflict(
                            "Workspace revision is not a same-state update or next draft"
                        )

                revision_row = session.get(
                    StudioDraftRevisionRow,
                    (identity.workspace_id, revision_subject.revision),
                )
                revision_checksum = sha256_value(revision_subject)
                if revision_row is None:
                    revision_artifact = self.artifacts.publish_blob(
                        canonical_bytes(revision_subject),
                        namespace="studio/draft-revision",
                        media_type="application/json",
                        suffix="json",
                    )
                    if revision_artifact.sha256 != revision_checksum:
                        raise WorkspaceStoreError("Draft revision artifact digest mismatch")
                    session.add(
                        StudioDraftRevisionRow(
                            workspace_id=identity.workspace_id,
                            revision=revision_subject.revision,
                            solution_id=identity.solution_id,
                            solution_version=identity.solution_version,
                            studio_adapter_id=identity.studio_adapter_id,
                            draft_checksum=revision_subject.draft_checksum,
                            record_checksum=revision_subject.record_checksum,
                            subject_checksum=revision_checksum,
                            subject=revision_subject.model_dump(mode="json"),
                            artifact=revision_artifact.model_dump(mode="json"),
                        )
                    )
                else:
                    existing_revision = self._revision_record(revision_row)
                    self._assert_identity(existing_revision.subject.identity, identity)
                    existing_subject = existing_revision.subject.model_copy(
                        update={"identity": identity}
                    )
                    if not _same_revision_content(
                        existing_subject,
                        revision_subject,
                    ):
                        raise WorkspaceStoreConflict("Draft revision is immutable")

                state_checksum = sha256_value(subject)
                state_artifact = self.artifacts.publish_blob(
                    canonical_bytes(subject),
                    namespace="studio/workspace-state",
                    media_type="application/json",
                    suffix="json",
                )
                if state_artifact.sha256 != state_checksum:
                    raise WorkspaceStoreError("Workspace state artifact digest mismatch")
                if current is None:
                    session.add(
                        StudioWorkspaceHeadRow(
                            workspace_id=identity.workspace_id,
                            solution_id=identity.solution_id,
                            solution_version=identity.solution_version,
                            studio_adapter_id=identity.studio_adapter_id,
                            generation=generation,
                            revision=subject.revision,
                            subject_checksum=state_checksum,
                            subject=subject.model_dump(mode="json"),
                            artifact=state_artifact.model_dump(mode="json"),
                        )
                    )
                else:
                    current.generation = generation
                    current.revision = subject.revision
                    current.subject_checksum = state_checksum
                    current.subject = subject.model_dump(mode="json")
                    current.artifact = state_artifact.model_dump(mode="json")
                if transaction_hook is not None:
                    # The hook may only add/validate rows in this same authority
                    # transaction. Exact artifacts may already be staged; a rollback
                    # can leave an unreachable object, never a second mutable truth.
                    transaction_hook(session)
        except WorkspaceStoreError:
            raise
        except IntegrityError as exc:
            raise WorkspaceStoreConflict("Workspace commit lost a concurrent CAS") from exc
        except (ProductInfrastructureError, SQLAlchemyError) as exc:
            raise WorkspaceStoreError("Workspace durable commit failed") from exc

        loaded = self.load(identity)
        if loaded is None:
            raise WorkspaceStoreError("Committed workspace head is unavailable")
        return loaded

    def list_revisions(
        self, identity: WorkspaceIdentity
    ) -> tuple[WorkspaceRevisionRecordV1, ...]:
        try:
            with Session(self.engine) as session:
                rows = session.execute(
                    select(StudioDraftRevisionRow)
                    .where(StudioDraftRevisionRow.workspace_id == identity.workspace_id)
                    .order_by(StudioDraftRevisionRow.revision)
                ).scalars().all()
                for row in rows:
                    session.expunge(row)
        except SQLAlchemyError as exc:
            raise WorkspaceStoreError("Draft revision database read failed") from exc

        records: list[WorkspaceRevisionRecordV1] = []
        for row in rows:
            try:
                record = self._revision_record(row)
            except ValueError as exc:
                raise WorkspaceStoreError("Draft revision database record is invalid") from exc
            self._assert_identity(record.subject.identity, identity)
            try:
                body = self.artifacts.get_exact(record.artifact)
            except ProductInfrastructureError as exc:
                raise WorkspaceStoreError("Draft revision exact artifact is unavailable") from exc
            if body != canonical_bytes(record.subject):
                raise WorkspaceStoreError("Draft revision exact artifact content mismatch")
            records.append(record)
        return tuple(records)
