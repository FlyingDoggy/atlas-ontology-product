from __future__ import annotations

import io
import os
import tarfile
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Literal, Protocol

from sqlalchemy import DateTime, ForeignKey, Integer, String, create_engine, func, select, text
from sqlalchemy.dialects.postgresql import JSONB, insert as pg_insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Mapped, Session, mapped_column

from .contracts import (
    ActivationConflictError,
    ActivationReceipt,
    ImmutableVersionError,
    PublicationError,
    ReleaseRef,
    RuntimeSnapshotRef,
)
from .io import sha256_value
from .product_context import (
    ActiveProductContextRow,
    Base,
    ExactStoredArtifactRef,
    PostgresProductContextRepository,
    ProductContextSubjectV1,
    ProductInfrastructureError,
    ProductInfrastructureSettings,
    S3ObjectVersion,
    S3ArtifactStore,
)


MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MIN_GC_GRACE_SECONDS = 3600
ARTIFACT_GC_LOCK_KEY = "ontology-lifecycle-artifact-gc/v1"


class DurableLifecycleError(PublicationError):
    """PostgreSQL/S3 lifecycle state cannot be committed or reconstructed."""


@dataclass(frozen=True, slots=True)
class DurableLifecycleSettings:
    mode: Literal["legacy-filesystem", "postgresql-s3"]
    product: ProductInfrastructureSettings | None = None

    @classmethod
    def from_env(cls) -> DurableLifecycleSettings:
        mode = os.environ.get(
            "ONTOLOGY_LIFECYCLE_STATE_MODE", "legacy-filesystem"
        ).strip()
        if mode not in {"legacy-filesystem", "postgresql-s3"}:
            raise DurableLifecycleError("Unsupported lifecycle state mode")
        if mode == "legacy-filesystem":
            return cls(mode="legacy-filesystem")
        try:
            product = ProductInfrastructureSettings.from_env()
        except ProductInfrastructureError as exc:
            raise DurableLifecycleError(
                "PostgreSQL/S3 lifecycle settings are incomplete"
            ) from exc
        if product.mode != "postgresql-s3" or not product.database_url:
            raise DurableLifecycleError(
                "Durable lifecycle requires PostgreSQL/S3 product state"
            )
        return cls(mode="postgresql-s3", product=product)


class LifecycleReleaseRow(Base):
    __tablename__ = "lifecycle_release"

    release_checksum: Mapped[str] = mapped_column(String(64), primary_key=True)
    package_id: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    release_ref: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    artifact: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class LifecycleSnapshotRow(Base):
    __tablename__ = "lifecycle_runtime_snapshot"

    snapshot_checksum: Mapped[str] = mapped_column(String(64), primary_key=True)
    environment_id: Mapped[str] = mapped_column(String(255), nullable=False)
    package_id: Mapped[str] = mapped_column(String(255), nullable=False)
    release_checksum: Mapped[str] = mapped_column(
        String(64), ForeignKey("lifecycle_release.release_checksum"), nullable=False
    )
    context_subject_checksum: Mapped[str] = mapped_column(
        String(64), ForeignKey("product_context_version.subject_checksum"), nullable=False
    )
    snapshot_ref: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    artifact: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class LifecycleActiveHeadRow(Base):
    __tablename__ = "lifecycle_active_head"

    environment_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    package_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    snapshot_checksum: Mapped[str] = mapped_column(
        String(64), ForeignKey("lifecycle_runtime_snapshot.snapshot_checksum"), nullable=False
    )
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class LifecycleActivationEventRow(Base):
    __tablename__ = "lifecycle_activation_event"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    environment_id: Mapped[str] = mapped_column(String(255), nullable=False)
    package_id: Mapped[str] = mapped_column(String(255), nullable=False)
    previous_snapshot_checksum: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("lifecycle_runtime_snapshot.snapshot_checksum")
    )
    active_snapshot_checksum: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("lifecycle_runtime_snapshot.snapshot_checksum"),
        nullable=False,
    )
    expected_snapshot_checksum: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("lifecycle_runtime_snapshot.snapshot_checksum")
    )
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class LifecycleStorePort(Protocol):
    def persist_release(self, ref: ReleaseRef, directory: Path) -> ExactStoredArtifactRef: ...

    def materialize_release(self, ref: ReleaseRef, destination: Path) -> None: ...

    def resolve_release(self, package_id: str, version: str) -> ReleaseRef: ...

    def list_releases(self, package_id: str) -> tuple[ReleaseRef, ...]: ...

    def persist_snapshot(
        self,
        ref: RuntimeSnapshotRef,
        directory: Path,
        context: ProductContextSubjectV1,
    ) -> ExactStoredArtifactRef: ...

    def materialize_snapshot(self, ref: RuntimeSnapshotRef, destination: Path) -> None: ...

    def resolve_snapshot(
        self, environment_id: str, snapshot_checksum: str
    ) -> RuntimeSnapshotRef: ...

    def active_ref(self, environment_id: str, package_id: str) -> RuntimeSnapshotRef | None: ...

    def rollback_target(
        self, environment_id: str, package_id: str
    ) -> RuntimeSnapshotRef | None: ...

    def activate(
        self,
        snapshot: RuntimeSnapshotRef,
        *,
        expected_current: RuntimeSnapshotRef | None,
    ) -> ActivationReceipt: ...

    def cleanup_orphans(
        self, *, grace_seconds: int, delete: bool = False
    ) -> dict[str, object]: ...


def classify_artifact_versions(
    versions: tuple[S3ObjectVersion, ...],
    *,
    referenced: set[tuple[str, str]],
    now: datetime,
    grace_seconds: int,
) -> dict[str, tuple[S3ObjectVersion, ...]]:
    if now.tzinfo is None:
        raise DurableLifecycleError("Artifact GC clock must be timezone-aware")
    if grace_seconds < MIN_GC_GRACE_SECONDS:
        raise DurableLifecycleError("Artifact GC grace period is too short")
    cutoff = now - timedelta(seconds=grace_seconds)
    committed: list[S3ObjectVersion] = []
    leased: list[S3ObjectVersion] = []
    orphaned: list[S3ObjectVersion] = []
    for version in versions:
        if version.last_modified.tzinfo is None:
            raise DurableLifecycleError("Artifact version timestamp is invalid")
        identity = (version.key, version.version_id)
        if identity in referenced:
            committed.append(version)
        elif version.last_modified > cutoff:
            leased.append(version)
        else:
            orphaned.append(version)
    return {
        "committed": tuple(committed),
        "leased": tuple(leased),
        "orphaned": tuple(orphaned),
    }


def directory_archive_bytes(root: Path) -> bytes:
    root = root.resolve()
    if not root.is_dir():
        raise DurableLifecycleError("Artifact directory is missing")
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_symlink() or (not path.is_file() and not path.is_dir()):
                raise DurableLifecycleError("Artifact directory contains an unsafe entry")
            if path.is_dir():
                continue
            relative = path.relative_to(root).as_posix()
            candidate = PurePosixPath(relative)
            if candidate.is_absolute() or ".." in candidate.parts:
                raise DurableLifecycleError("Artifact directory path is unsafe")
            body = path.read_bytes()
            info = tarfile.TarInfo(relative)
            info.size = len(body)
            info.mode = 0o644
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            archive.addfile(info, io.BytesIO(body))
    payload = stream.getvalue()
    if not payload or len(payload) > MAX_ARCHIVE_BYTES:
        raise DurableLifecycleError("Artifact archive size is outside the supported range")
    return payload


def restore_directory_archive(payload: bytes, destination: Path) -> None:
    if not payload or len(payload) > MAX_ARCHIVE_BYTES:
        raise DurableLifecycleError("Artifact archive size is outside the supported range")
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise DurableLifecycleError("Artifact materialization destination already exists")
    staging = Path(tempfile.mkdtemp(prefix=".materialize-", dir=destination.parent))
    try:
        seen: set[str] = set()
        total = 0
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
            for member in archive.getmembers():
                candidate = PurePosixPath(member.name)
                if (
                    not member.isfile()
                    or candidate.is_absolute()
                    or not candidate.parts
                    or ".." in candidate.parts
                    or member.name in seen
                ):
                    raise DurableLifecycleError("Artifact archive contains an unsafe entry")
                seen.add(member.name)
                total += member.size
                if total > MAX_ARCHIVE_BYTES:
                    raise DurableLifecycleError("Artifact archive expands beyond its limit")
                source = archive.extractfile(member)
                if source is None:
                    raise DurableLifecycleError("Artifact archive member is unreadable")
                target = staging.joinpath(*candidate.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read())
        if not seen:
            raise DurableLifecycleError("Artifact archive is empty")
        os.replace(staging, destination)
    except Exception:
        if staging.exists():
            import shutil

            shutil.rmtree(staging)
        raise


class PostgresS3LifecycleStore:
    def __init__(self, product: ProductInfrastructureSettings) -> None:
        if product.mode != "postgresql-s3" or not product.database_url:
            raise DurableLifecycleError("Durable lifecycle settings are incomplete")
        self.engine = create_engine(product.database_url, pool_pre_ping=True)
        self.artifacts = S3ArtifactStore(product)
        self.contexts = PostgresProductContextRepository(product.database_url)

    def _publish_directory(
        self, directory: Path, *, namespace: str
    ) -> ExactStoredArtifactRef:
        try:
            return self.artifacts.publish_blob(
                directory_archive_bytes(directory),
                namespace=namespace,
                media_type="application/x-tar",
                suffix="tar",
            )
        except ProductInfrastructureError as exc:
            raise DurableLifecycleError("Lifecycle artifact publish failed") from exc

    @staticmethod
    def _artifact_lock(session: Session, *, exclusive: bool) -> None:
        function = (
            "pg_advisory_xact_lock" if exclusive else "pg_advisory_xact_lock_shared"
        )
        session.execute(
            text(f"SELECT {function}(hashtextextended(:key, 0))"),
            {"key": ARTIFACT_GC_LOCK_KEY},
        )

    def _verify_artifact_under_commit_lock(
        self, session: Session, artifact: ExactStoredArtifactRef
    ) -> None:
        self._artifact_lock(session, exclusive=False)
        try:
            self.artifacts.get_exact(artifact)
        except ProductInfrastructureError as exc:
            raise DurableLifecycleError(
                "Lifecycle artifact disappeared before database commit"
            ) from exc

    def persist_release(self, ref: ReleaseRef, directory: Path) -> ExactStoredArtifactRef:
        artifact = self._publish_directory(directory, namespace="lifecycle/releases")
        try:
            with Session(self.engine) as session, session.begin():
                self._verify_artifact_under_commit_lock(session, artifact)
                alias = session.execute(
                    select(LifecycleReleaseRow).where(
                        LifecycleReleaseRow.package_id == ref.package_id,
                        LifecycleReleaseRow.version == ref.version,
                    )
                ).scalar_one_or_none()
                if alias is not None and alias.release_checksum != ref.checksum:
                    raise ImmutableVersionError(
                        "Durable release version already identifies different content"
                    )
                session.execute(
                    pg_insert(LifecycleReleaseRow)
                    .values(
                        release_checksum=ref.checksum,
                        package_id=ref.package_id,
                        version=ref.version,
                        release_ref=ref.model_dump(mode="json"),
                        artifact=artifact.model_dump(mode="json"),
                    )
                    .on_conflict_do_nothing(
                        index_elements=[LifecycleReleaseRow.release_checksum]
                    )
                )
                persisted = session.get(LifecycleReleaseRow, ref.checksum)
                if (
                    persisted is None
                    or ReleaseRef.model_validate(persisted.release_ref) != ref
                    or ExactStoredArtifactRef.model_validate(persisted.artifact).sha256
                    != artifact.sha256
                ):
                    raise DurableLifecycleError("Durable release identity conflict")
        except ImmutableVersionError:
            raise
        except (IntegrityError, SQLAlchemyError) as exc:
            raise DurableLifecycleError("Durable release registration failed") from exc
        return artifact

    def _release_artifact(self, ref: ReleaseRef) -> ExactStoredArtifactRef:
        try:
            with Session(self.engine) as session:
                row = session.get(LifecycleReleaseRow, ref.checksum)
        except SQLAlchemyError as exc:
            raise DurableLifecycleError("Durable release lookup failed") from exc
        if row is None or ReleaseRef.model_validate(row.release_ref) != ref:
            raise DurableLifecycleError("Durable release is not registered")
        return ExactStoredArtifactRef.model_validate(row.artifact)

    def resolve_release(self, package_id: str, version: str) -> ReleaseRef:
        try:
            with Session(self.engine) as session:
                row = session.execute(
                    select(LifecycleReleaseRow).where(
                        LifecycleReleaseRow.package_id == package_id,
                        LifecycleReleaseRow.version == version,
                    )
                ).scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise DurableLifecycleError("Durable release lookup failed") from exc
        if row is None:
            raise DurableLifecycleError("Durable release alias is not registered")
        return ReleaseRef.model_validate(row.release_ref)

    def list_releases(self, package_id: str) -> tuple[ReleaseRef, ...]:
        try:
            with Session(self.engine) as session:
                rows = session.execute(
                    select(LifecycleReleaseRow).where(
                        LifecycleReleaseRow.package_id == package_id
                    )
                ).scalars().all()
        except SQLAlchemyError as exc:
            raise DurableLifecycleError("Durable release listing failed") from exc
        return tuple(ReleaseRef.model_validate(row.release_ref) for row in rows)

    def materialize_release(self, ref: ReleaseRef, destination: Path) -> None:
        artifact = self._release_artifact(ref)
        try:
            payload = self.artifacts.get_exact(artifact)
        except ProductInfrastructureError as exc:
            raise DurableLifecycleError("Durable release read-back failed") from exc
        restore_directory_archive(payload, destination)

    def persist_snapshot(
        self,
        ref: RuntimeSnapshotRef,
        directory: Path,
        context: ProductContextSubjectV1,
    ) -> ExactStoredArtifactRef:
        if (
            context.active_runtime.snapshot_checksum != ref.checksum
            or context.active_runtime.release_checksum != ref.release.checksum
            or context.active_runtime.environment_id != ref.environment_id
        ):
            raise DurableLifecycleError("Snapshot context identity does not close")
        try:
            context_artifact = self.artifacts.publish_subject(context)
            self.contexts.register_version(context, context_artifact)
        except ProductInfrastructureError as exc:
            raise DurableLifecycleError("Snapshot context registration failed") from exc
        artifact = self._publish_directory(directory, namespace="lifecycle/snapshots")
        context_checksum = sha256_value(context)
        try:
            with Session(self.engine) as session, session.begin():
                self._verify_artifact_under_commit_lock(session, artifact)
                release = session.get(LifecycleReleaseRow, ref.release.checksum)
                if release is None or ReleaseRef.model_validate(release.release_ref) != ref.release:
                    raise DurableLifecycleError("Snapshot release is not registered")
                session.execute(
                    pg_insert(LifecycleSnapshotRow)
                    .values(
                        snapshot_checksum=ref.checksum,
                        environment_id=ref.environment_id,
                        package_id=ref.release.package_id,
                        release_checksum=ref.release.checksum,
                        context_subject_checksum=context_checksum,
                        snapshot_ref=ref.model_dump(mode="json"),
                        artifact=artifact.model_dump(mode="json"),
                        state="READY",
                    )
                    .on_conflict_do_nothing(
                        index_elements=[LifecycleSnapshotRow.snapshot_checksum]
                    )
                )
                persisted = session.get(LifecycleSnapshotRow, ref.checksum)
                if (
                    persisted is None
                    or RuntimeSnapshotRef.model_validate(persisted.snapshot_ref) != ref
                    or persisted.context_subject_checksum != context_checksum
                    or persisted.state != "READY"
                    or ExactStoredArtifactRef.model_validate(persisted.artifact).sha256
                    != artifact.sha256
                ):
                    raise DurableLifecycleError("Durable snapshot identity conflict")
        except DurableLifecycleError:
            raise
        except SQLAlchemyError as exc:
            raise DurableLifecycleError("Durable snapshot registration failed") from exc
        return artifact

    def _snapshot_row(self, ref: RuntimeSnapshotRef) -> LifecycleSnapshotRow:
        try:
            with Session(self.engine) as session:
                row = session.get(LifecycleSnapshotRow, ref.checksum)
                if row is not None:
                    session.expunge(row)
        except SQLAlchemyError as exc:
            raise DurableLifecycleError("Durable snapshot lookup failed") from exc
        if row is None or RuntimeSnapshotRef.model_validate(row.snapshot_ref) != ref:
            raise DurableLifecycleError("Durable snapshot is not registered")
        return row

    def materialize_snapshot(self, ref: RuntimeSnapshotRef, destination: Path) -> None:
        artifact = ExactStoredArtifactRef.model_validate(self._snapshot_row(ref).artifact)
        try:
            payload = self.artifacts.get_exact(artifact)
        except ProductInfrastructureError as exc:
            raise DurableLifecycleError("Durable snapshot read-back failed") from exc
        restore_directory_archive(payload, destination)

    def resolve_snapshot(
        self, environment_id: str, snapshot_checksum: str
    ) -> RuntimeSnapshotRef:
        try:
            with Session(self.engine) as session:
                row = session.get(LifecycleSnapshotRow, snapshot_checksum)
        except SQLAlchemyError as exc:
            raise DurableLifecycleError("Durable snapshot lookup failed") from exc
        if row is None or row.environment_id != environment_id or row.state != "READY":
            raise DurableLifecycleError("Prepared durable snapshot is missing")
        ref = RuntimeSnapshotRef.model_validate(row.snapshot_ref)
        if ref.environment_id != environment_id or ref.checksum != snapshot_checksum:
            raise DurableLifecycleError("Prepared durable snapshot identity mismatch")
        return ref

    def active_ref(self, environment_id: str, package_id: str) -> RuntimeSnapshotRef | None:
        try:
            with Session(self.engine) as session:
                row = session.execute(
                    select(LifecycleSnapshotRow)
                    .join(
                        LifecycleActiveHeadRow,
                        LifecycleActiveHeadRow.snapshot_checksum
                        == LifecycleSnapshotRow.snapshot_checksum,
                    )
                    .where(
                        LifecycleActiveHeadRow.environment_id == environment_id,
                        LifecycleActiveHeadRow.package_id == package_id,
                    )
                ).scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise DurableLifecycleError("Durable active-head read failed") from exc
        if row is None:
            return None
        ref = RuntimeSnapshotRef.model_validate(row.snapshot_ref)
        if ref.environment_id != environment_id or ref.release.package_id != package_id:
            raise DurableLifecycleError("Durable active-head identity mismatch")
        return ref

    def rollback_target(
        self, environment_id: str, package_id: str
    ) -> RuntimeSnapshotRef | None:
        """Return the exact predecessor recorded by the current committed head."""
        try:
            with Session(self.engine) as session:
                head = session.get(
                    LifecycleActiveHeadRow,
                    {"environment_id": environment_id, "package_id": package_id},
                )
                if head is None:
                    return None
                event = session.execute(
                    select(LifecycleActivationEventRow).where(
                        LifecycleActivationEventRow.environment_id == environment_id,
                        LifecycleActivationEventRow.package_id == package_id,
                        LifecycleActivationEventRow.generation == head.generation,
                        LifecycleActivationEventRow.active_snapshot_checksum
                        == head.snapshot_checksum,
                    )
                ).scalar_one_or_none()
                if event is None:
                    raise DurableLifecycleError(
                        "Durable active head has no exact activation event"
                    )
                if event.previous_snapshot_checksum is None:
                    return None
                previous = session.get(
                    LifecycleSnapshotRow, event.previous_snapshot_checksum
                )
        except DurableLifecycleError:
            raise
        except SQLAlchemyError as exc:
            raise DurableLifecycleError("Durable rollback-target read failed") from exc
        if (
            previous is None
            or previous.state != "READY"
            or previous.environment_id != environment_id
            or previous.package_id != package_id
        ):
            raise DurableLifecycleError("Durable rollback target is not READY")
        ref = RuntimeSnapshotRef.model_validate(previous.snapshot_ref)
        if (
            ref.environment_id != environment_id
            or ref.release.package_id != package_id
            or ref.checksum != event.previous_snapshot_checksum
            or ref.checksum == head.snapshot_checksum
        ):
            raise DurableLifecycleError("Durable rollback-target identity mismatch")
        return ref

    def activate(
        self,
        snapshot: RuntimeSnapshotRef,
        *,
        expected_current: RuntimeSnapshotRef | None,
    ) -> ActivationReceipt:
        lock_key = f"{snapshot.environment_id}:{snapshot.release.package_id}"
        try:
            with Session(self.engine) as session, session.begin():
                session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                    {"key": lock_key},
                )
                candidate = session.get(LifecycleSnapshotRow, snapshot.checksum)
                if (
                    candidate is None
                    or candidate.state != "READY"
                    or RuntimeSnapshotRef.model_validate(candidate.snapshot_ref) != snapshot
                    or candidate.environment_id != snapshot.environment_id
                    or candidate.package_id != snapshot.release.package_id
                    or candidate.release_checksum != snapshot.release.checksum
                ):
                    raise DurableLifecycleError("Activation snapshot is not durably READY")
                head = session.execute(
                    select(LifecycleActiveHeadRow)
                    .where(
                        LifecycleActiveHeadRow.environment_id == snapshot.environment_id,
                        LifecycleActiveHeadRow.package_id == snapshot.release.package_id,
                    )
                    .with_for_update()
                ).scalar_one_or_none()
                current: RuntimeSnapshotRef | None = None
                if head is not None:
                    current_row = session.get(
                        LifecycleSnapshotRow, head.snapshot_checksum
                    )
                    if current_row is None:
                        raise DurableLifecycleError("Active snapshot row is missing")
                    current = RuntimeSnapshotRef.model_validate(current_row.snapshot_ref)
                    if (
                        current.environment_id != snapshot.environment_id
                        or current.release.package_id != snapshot.release.package_id
                    ):
                        raise DurableLifecycleError("Active snapshot subject mismatch")
                if expected_current is not None and current != expected_current:
                    raise ActivationConflictError(
                        "Durable active runtime changed before activation"
                    )
                if current == snapshot:
                    context_head = session.get(
                        ActiveProductContextRow, snapshot.environment_id
                    )
                    if (
                        context_head is None
                        or context_head.subject_checksum
                        != candidate.context_subject_checksum
                        or context_head.source_snapshot_checksum != snapshot.checksum
                    ):
                        raise DurableLifecycleError(
                            "Idempotent activation context head is inconsistent"
                        )
                    return ActivationReceipt(
                        environment_id=snapshot.environment_id,
                        active=snapshot,
                        previous=current,
                        idempotent=True,
                    )
                generation = (head.generation if head is not None else 0) + 1
                if head is None:
                    session.add(
                        LifecycleActiveHeadRow(
                            environment_id=snapshot.environment_id,
                            package_id=snapshot.release.package_id,
                            snapshot_checksum=snapshot.checksum,
                            generation=generation,
                        )
                    )
                else:
                    head.snapshot_checksum = snapshot.checksum
                    head.generation = generation
                    head.updated_at = func.now()
                session.execute(
                    pg_insert(ActiveProductContextRow)
                    .values(
                        environment_id=snapshot.environment_id,
                        subject_checksum=candidate.context_subject_checksum,
                        source_snapshot_checksum=snapshot.checksum,
                    )
                    .on_conflict_do_update(
                        index_elements=[ActiveProductContextRow.environment_id],
                        set_={
                            "subject_checksum": candidate.context_subject_checksum,
                            "source_snapshot_checksum": snapshot.checksum,
                            "updated_at": func.now(),
                        },
                    )
                )
                session.add(
                    LifecycleActivationEventRow(
                        event_id=str(uuid.uuid4()),
                        environment_id=snapshot.environment_id,
                        package_id=snapshot.release.package_id,
                        previous_snapshot_checksum=current.checksum if current else None,
                        active_snapshot_checksum=snapshot.checksum,
                        expected_snapshot_checksum=(
                            expected_current.checksum if expected_current else None
                        ),
                        generation=generation,
                    )
                )
        except (ActivationConflictError, DurableLifecycleError):
            raise
        except SQLAlchemyError as exc:
            raise DurableLifecycleError("Durable activation transaction failed") from exc
        return ActivationReceipt(
            environment_id=snapshot.environment_id,
            active=snapshot,
            previous=current,
            idempotent=False,
        )

    @staticmethod
    def _artifact_identity(value: dict[str, object]) -> tuple[str, str]:
        ref = ExactStoredArtifactRef.model_validate(value)
        return ref.key, ref.version_id

    def cleanup_orphans(
        self, *, grace_seconds: int, delete: bool = False
    ) -> dict[str, object]:
        if grace_seconds < MIN_GC_GRACE_SECONDS:
            raise DurableLifecycleError("Artifact GC grace period is too short")
        try:
            with Session(self.engine) as session, session.begin():
                self._artifact_lock(session, exclusive=True)
                release_artifacts = session.execute(
                    select(LifecycleReleaseRow.artifact)
                ).scalars().all()
                snapshot_artifacts = session.execute(
                    select(LifecycleSnapshotRow.artifact)
                ).scalars().all()
                referenced = {
                    self._artifact_identity(value)
                    for value in [*release_artifacts, *snapshot_artifacts]
                }
                versions = self.artifacts.list_versions(prefix="lifecycle/")
                groups = classify_artifact_versions(
                    versions,
                    referenced=referenced,
                    now=datetime.now(timezone.utc),
                    grace_seconds=grace_seconds,
                )
                deleted: list[S3ObjectVersion] = []
                if delete:
                    for version in groups["orphaned"]:
                        self.artifacts.delete_version(version)
                        deleted.append(version)
        except DurableLifecycleError:
            raise
        except (ProductInfrastructureError, SQLAlchemyError) as exc:
            raise DurableLifecycleError("Artifact GC failed") from exc

        def identities(items: tuple[S3ObjectVersion, ...] | list[S3ObjectVersion]) -> list[str]:
            return [f"{item.key}@{item.version_id}" for item in items]

        return {
            "contract": "lifecycle-artifact-gc-report/v1",
            "mode": "DELETE" if delete else "DRY_RUN",
            "grace_seconds": grace_seconds,
            "committed": identities(groups["committed"]),
            "leased": identities(groups["leased"]),
            "orphan_candidates": identities(groups["orphaned"]),
            "deleted": identities(deleted),
        }


def configured_lifecycle_store() -> LifecycleStorePort | None:
    settings = DurableLifecycleSettings.from_env()
    if settings.mode == "legacy-filesystem":
        return None
    assert settings.product is not None
    return PostgresS3LifecycleStore(settings.product)
