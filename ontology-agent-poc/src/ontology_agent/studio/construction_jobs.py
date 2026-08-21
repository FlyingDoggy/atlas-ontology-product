from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable, Literal, Protocol

from pydantic import Field, model_validator
from sqlalchemy import DateTime, Integer, String, create_engine, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Mapped, mapped_column

from ..contracts import Sha256
from ..models import StrictModel
from ..product_context import Base, ProductInfrastructureSettings


class ConstructionJobError(RuntimeError):
    """A durable construction job could not be progressed safely."""


class ConstructionJobConflict(ConstructionJobError):
    """A job transition lost its lease or violated the terminal state."""


ConstructionJobStatus = Literal[
    "QUEUED",
    "RUNNING",
    "COMMITTING",
    "CANCEL_REQUESTED",
    "SUCCEEDED",
    "FAILED",
    "CANCELLED",
    "STALE",
]

ACTIVE_JOB_STATUSES = {
    "QUEUED",
    "RUNNING",
    "COMMITTING",
    "CANCEL_REQUESTED",
}
CLAIMABLE_JOB_STATUSES = {"QUEUED", "RUNNING", "COMMITTING"}
TERMINAL_JOB_STATUSES = {"SUCCEEDED", "FAILED", "CANCELLED", "STALE"}


class ConstructionJobInputV1(StrictModel):
    contract: Literal["construction-job-input/v1"] = "construction-job-input/v1"
    workspace_id: str = Field(min_length=1, max_length=255)
    solution_id: str = Field(min_length=1, max_length=255)
    base_revision: int = Field(ge=1)
    base_draft_checksum: Sha256
    source_set_digest: Sha256
    selected_source_version_ids: tuple[str, ...] = ()
    profile_ref: str = Field(min_length=1, max_length=255)


class ConstructionJobV1(StrictModel):
    contract: Literal["construction-job/v1"] = "construction-job/v1"
    job_id: str = Field(pattern=r"^construction-job\.[0-9a-f]{32}$")
    run_id: str = Field(pattern=r"^construction-run\.[0-9a-f]{32}$")
    workspace_id: str = Field(min_length=1, max_length=255)
    solution_id: str = Field(min_length=1, max_length=255)
    base_revision: int = Field(ge=1)
    base_draft_checksum: Sha256
    source_set_digest: Sha256
    selected_source_version_ids: tuple[str, ...] = ()
    profile_ref: str = Field(min_length=1, max_length=255)
    status: ConstructionJobStatus
    attempt_id: str | None = Field(
        default=None, pattern=r"^construction-attempt\.[0-9a-f]{32}$"
    )
    lease_epoch: int = Field(ge=0)
    lease_owner: str | None = Field(default=None, max_length=255)
    lease_expires_at: datetime | None = None
    result_run_id: str | None = Field(
        default=None, pattern=r"^construction-run\.[0-9a-f]{32}$"
    )
    error_code: str | None = Field(
        default=None, pattern=r"^[A-Z][A-Z0-9_]{2,99}$"
    )
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime

    @model_validator(mode="after")
    def coherent_state(self) -> ConstructionJobV1:
        if self.status in {"RUNNING", "COMMITTING", "CANCEL_REQUESTED"}:
            if not self.attempt_id or not self.lease_owner or not self.lease_expires_at:
                raise ValueError("Active worker state requires an exact lease")
        if self.status == "SUCCEEDED" and self.result_run_id != self.run_id:
            raise ValueError("Successful job must bind its planned immutable run")
        if self.status in TERMINAL_JOB_STATUSES and self.completed_at is None:
            raise ValueError("Terminal construction job requires completed_at")
        return self


class ConstructionJobStore(Protocol):
    def enqueue(self, value: ConstructionJobInputV1) -> ConstructionJobV1: ...

    def get(self, job_id: str) -> ConstructionJobV1: ...

    def list(self, workspace_id: str) -> tuple[ConstructionJobV1, ...]: ...

    def claim_next(
        self, worker_id: str, *, lease_seconds: int = 120
    ) -> ConstructionJobV1 | None: ...

    def begin_commit(
        self, job_id: str, worker_id: str, lease_epoch: int
    ) -> ConstructionJobV1: ...

    def complete_success(
        self,
        job_id: str,
        worker_id: str,
        lease_epoch: int,
        *,
        run_id: str,
    ) -> ConstructionJobV1: ...

    def fail_attempt(
        self,
        job_id: str,
        worker_id: str,
        lease_epoch: int,
        *,
        error_code: str,
        stale: bool = False,
    ) -> ConstructionJobV1: ...

    def cancel(self, job_id: str) -> ConstructionJobV1: ...

    def retry(self, job_id: str) -> ConstructionJobV1: ...


def _new_job(value: ConstructionJobInputV1, now: datetime) -> ConstructionJobV1:
    return ConstructionJobV1(
        job_id="construction-job." + uuid.uuid4().hex,
        run_id="construction-run." + uuid.uuid4().hex,
        workspace_id=value.workspace_id,
        solution_id=value.solution_id,
        base_revision=value.base_revision,
        base_draft_checksum=value.base_draft_checksum,
        source_set_digest=value.source_set_digest,
        selected_source_version_ids=value.selected_source_version_ids,
        profile_ref=value.profile_ref,
        status="QUEUED",
        lease_epoch=0,
        created_at=now,
        updated_at=now,
    )


def _same_input(job: ConstructionJobV1, value: ConstructionJobInputV1) -> bool:
    return all(
        (
            job.workspace_id == value.workspace_id,
            job.solution_id == value.solution_id,
            job.base_revision == value.base_revision,
            job.base_draft_checksum == value.base_draft_checksum,
            job.source_set_digest == value.source_set_digest,
            job.selected_source_version_ids == value.selected_source_version_ids,
            job.profile_ref == value.profile_ref,
        )
    )


class InMemoryConstructionJobStore:
    """Deterministic state-machine implementation used by contract tests."""

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._jobs: dict[str, ConstructionJobV1] = {}
        self._lock = threading.RLock()

    def enqueue(self, value: ConstructionJobInputV1) -> ConstructionJobV1:
        with self._lock:
            active = next(
                (
                    job
                    for job in self._jobs.values()
                    if job.workspace_id == value.workspace_id
                    and job.status in ACTIVE_JOB_STATUSES
                ),
                None,
            )
            if active:
                if not _same_input(active, value):
                    raise ConstructionJobConflict(
                        "Workspace already has an active construction job"
                    )
                return active
            job = _new_job(value, self.clock())
            self._jobs[job.job_id] = job
            return job

    def get(self, job_id: str) -> ConstructionJobV1:
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise ConstructionJobError("Construction job is unavailable") from exc

    def list(self, workspace_id: str) -> tuple[ConstructionJobV1, ...]:
        return tuple(
            sorted(
                (job for job in self._jobs.values() if job.workspace_id == workspace_id),
                key=lambda item: item.created_at,
                reverse=True,
            )
        )

    def claim_next(
        self, worker_id: str, *, lease_seconds: int = 120
    ) -> ConstructionJobV1 | None:
        with self._lock:
            now = self.clock()
            eligible = sorted(self._jobs.values(), key=lambda item: item.created_at)
            for job in eligible:
                reclaim = (
                    job.status in {"RUNNING", "COMMITTING"}
                    and job.lease_expires_at is not None
                    and job.lease_expires_at <= now
                )
                if job.status != "QUEUED" and not reclaim:
                    continue
                claimed = job.model_copy(
                    update={
                        "status": "RUNNING",
                        "attempt_id": "construction-attempt." + uuid.uuid4().hex,
                        "lease_epoch": job.lease_epoch + 1,
                        "lease_owner": worker_id,
                        "lease_expires_at": now + timedelta(seconds=lease_seconds),
                        "started_at": job.started_at or now,
                        "updated_at": now,
                    }
                )
                self._jobs[job.job_id] = claimed
                return claimed
            return None

    def claim_next_after_enqueue(
        self,
        value: ConstructionJobInputV1,
        worker_id: str,
        *,
        lease_seconds: int = 120,
    ) -> ConstructionJobV1:
        self.enqueue(value)
        claimed = self.claim_next(worker_id, lease_seconds=lease_seconds)
        assert claimed is not None
        return claimed

    def _leased(
        self, job_id: str, worker_id: str, lease_epoch: int
    ) -> ConstructionJobV1:
        job = self.get(job_id)
        if job.lease_owner != worker_id or job.lease_epoch != lease_epoch:
            raise ConstructionJobConflict("Construction job lease is no longer current")
        return job

    def begin_commit(
        self, job_id: str, worker_id: str, lease_epoch: int
    ) -> ConstructionJobV1:
        with self._lock:
            job = self._leased(job_id, worker_id, lease_epoch)
            if job.status != "RUNNING":
                raise ConstructionJobConflict("Construction attempt is not authorized to commit")
            updated = job.model_copy(
                update={"status": "COMMITTING", "updated_at": self.clock()}
            )
            self._jobs[job_id] = updated
            return updated

    def complete_success(
        self,
        job_id: str,
        worker_id: str,
        lease_epoch: int,
        *,
        run_id: str,
    ) -> ConstructionJobV1:
        with self._lock:
            job = self._leased(job_id, worker_id, lease_epoch)
            if job.status != "COMMITTING" or run_id != job.run_id:
                raise ConstructionJobConflict("Construction success has no commit authority")
            now = self.clock()
            updated = job.model_copy(
                update={
                    "status": "SUCCEEDED",
                    "result_run_id": run_id,
                    "completed_at": now,
                    "updated_at": now,
                }
            )
            self._jobs[job_id] = updated
            return updated

    def fail_attempt(
        self,
        job_id: str,
        worker_id: str,
        lease_epoch: int,
        *,
        error_code: str,
        stale: bool = False,
    ) -> ConstructionJobV1:
        with self._lock:
            job = self._leased(job_id, worker_id, lease_epoch)
            if job.status not in {"RUNNING", "COMMITTING", "CANCEL_REQUESTED"}:
                raise ConstructionJobConflict("Construction attempt is not active")
            now = self.clock()
            status: ConstructionJobStatus = (
                "CANCELLED"
                if job.status == "CANCEL_REQUESTED"
                else "STALE"
                if stale
                else "FAILED"
            )
            updated = job.model_copy(
                update={
                    "status": status,
                    "error_code": error_code,
                    "completed_at": now,
                    "updated_at": now,
                }
            )
            self._jobs[job_id] = updated
            return updated

    def cancel(self, job_id: str) -> ConstructionJobV1:
        with self._lock:
            job = self.get(job_id)
            now = self.clock()
            if job.status == "QUEUED":
                updated = job.model_copy(
                    update={
                        "status": "CANCELLED",
                        "error_code": "CANCELLED_BY_USER",
                        "completed_at": now,
                        "updated_at": now,
                    }
                )
            elif job.status == "RUNNING":
                updated = job.model_copy(
                    update={"status": "CANCEL_REQUESTED", "updated_at": now}
                )
            else:
                return job
            self._jobs[job_id] = updated
            return updated

    def retry(self, job_id: str) -> ConstructionJobV1:
        with self._lock:
            job = self.get(job_id)
            if job.status not in {"FAILED", "CANCELLED", "STALE"}:
                raise ConstructionJobConflict("Only failed, cancelled or stale jobs can retry")
            return self.enqueue(
                ConstructionJobInputV1(
                    workspace_id=job.workspace_id,
                    solution_id=job.solution_id,
                    base_revision=job.base_revision,
                    base_draft_checksum=job.base_draft_checksum,
                    source_set_digest=job.source_set_digest,
                    selected_source_version_ids=job.selected_source_version_ids,
                    profile_ref=job.profile_ref,
                )
            )


class StudioConstructionJobRow(Base):
    __tablename__ = "studio_construction_job"

    job_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    workspace_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    solution_id: Mapped[str] = mapped_column(String(255), nullable=False)
    base_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    base_draft_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    source_set_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    selected_source_version_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    profile_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_id: Mapped[str | None] = mapped_column(String(80))
    lease_epoch: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(255))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_run_id: Mapped[str | None] = mapped_column(String(80))
    error_code: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PostgresConstructionJobStore:
    """PostgreSQL job/outbox with lease and commit-fence CAS semantics."""

    def __init__(self, database_url: str, *, clock: Callable[[], datetime] | None = None) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @classmethod
    def from_settings(
        cls, settings: ProductInfrastructureSettings
    ) -> PostgresConstructionJobStore:
        if settings.mode != "postgresql-s3" or not settings.database_url:
            raise ConstructionJobError("Construction job storage requires PostgreSQL")
        return cls(settings.database_url)

    @staticmethod
    def _value(row: StudioConstructionJobRow) -> ConstructionJobV1:
        return ConstructionJobV1.model_validate(
            {column.name: getattr(row, column.name) for column in row.__table__.columns}
        )

    @staticmethod
    def _apply(row: StudioConstructionJobRow, value: ConstructionJobV1) -> None:
        for name, field in value.model_dump(mode="python").items():
            if name != "contract":
                setattr(row, name, list(field) if name == "selected_source_version_ids" else field)

    def enqueue(self, value: ConstructionJobInputV1) -> ConstructionJobV1:
        now = self.clock()
        try:
            with self.engine.begin() as connection:
                connection.exec_driver_sql(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (f"studio-construction-job:{value.workspace_id}",),
                )
                from sqlalchemy.orm import Session

                with Session(bind=connection) as session:
                    active = session.scalars(
                        select(StudioConstructionJobRow)
                        .where(
                            StudioConstructionJobRow.workspace_id == value.workspace_id,
                            StudioConstructionJobRow.status.in_(ACTIVE_JOB_STATUSES),
                        )
                        .order_by(StudioConstructionJobRow.created_at.desc())
                    ).first()
                    if active is not None:
                        job = self._value(active)
                        if not _same_input(job, value):
                            raise ConstructionJobConflict(
                                "Workspace already has an active construction job"
                            )
                        return job
                    job = _new_job(value, now)
                    row_payload = job.model_dump(mode="python", exclude={"contract"})
                    row_payload["selected_source_version_ids"] = list(
                        job.selected_source_version_ids
                    )
                    session.add(
                        StudioConstructionJobRow(**row_payload)
                    )
                    session.flush()
                    return job
        except ConstructionJobError:
            raise
        except (IntegrityError, SQLAlchemyError) as exc:
            raise ConstructionJobError("Construction job enqueue failed") from exc

    def get(self, job_id: str) -> ConstructionJobV1:
        try:
            from sqlalchemy.orm import Session

            with Session(self.engine) as session:
                row = session.get(StudioConstructionJobRow, job_id)
                if row is None:
                    raise ConstructionJobError("Construction job is unavailable")
                return self._value(row)
        except ConstructionJobError:
            raise
        except SQLAlchemyError as exc:
            raise ConstructionJobError("Construction job read failed") from exc

    def list(self, workspace_id: str) -> tuple[ConstructionJobV1, ...]:
        try:
            from sqlalchemy.orm import Session

            with Session(self.engine) as session:
                rows = session.scalars(
                    select(StudioConstructionJobRow)
                    .where(StudioConstructionJobRow.workspace_id == workspace_id)
                    .order_by(StudioConstructionJobRow.created_at.desc())
                ).all()
                return tuple(self._value(row) for row in rows)
        except SQLAlchemyError as exc:
            raise ConstructionJobError("Construction job list failed") from exc

    def claim_next(
        self, worker_id: str, *, lease_seconds: int = 120
    ) -> ConstructionJobV1 | None:
        now = self.clock()
        try:
            from sqlalchemy.orm import Session

            with Session(self.engine) as session, session.begin():
                row = session.scalars(
                    select(StudioConstructionJobRow)
                    .where(
                        or_(
                            StudioConstructionJobRow.status == "QUEUED",
                            (
                                StudioConstructionJobRow.status.in_(("RUNNING", "COMMITTING"))
                                & (StudioConstructionJobRow.lease_expires_at <= now)
                            ),
                        )
                    )
                    .order_by(StudioConstructionJobRow.created_at)
                    .with_for_update(skip_locked=True)
                    .limit(1)
                ).first()
                if row is None:
                    return None
                row.status = "RUNNING"
                row.attempt_id = "construction-attempt." + uuid.uuid4().hex
                row.lease_epoch += 1
                row.lease_owner = worker_id
                row.lease_expires_at = now + timedelta(seconds=lease_seconds)
                row.started_at = row.started_at or now
                row.updated_at = now
                session.flush()
                return self._value(row)
        except SQLAlchemyError as exc:
            raise ConstructionJobError("Construction job claim failed") from exc

    def _transition(
        self,
        job_id: str,
        worker_id: str,
        lease_epoch: int,
        allowed: set[str],
        mutate: Callable[[StudioConstructionJobRow, datetime], None],
    ) -> ConstructionJobV1:
        try:
            from sqlalchemy.orm import Session

            with Session(self.engine) as session, session.begin():
                row = session.scalar(
                    select(StudioConstructionJobRow)
                    .where(StudioConstructionJobRow.job_id == job_id)
                    .with_for_update()
                )
                if row is None:
                    raise ConstructionJobError("Construction job is unavailable")
                if row.lease_owner != worker_id or row.lease_epoch != lease_epoch:
                    raise ConstructionJobConflict(
                        "Construction job lease is no longer current"
                    )
                if row.status not in allowed:
                    raise ConstructionJobConflict(
                        "Construction attempt is not authorized to commit"
                    )
                mutate(row, self.clock())
                session.flush()
                return self._value(row)
        except ConstructionJobError:
            raise
        except SQLAlchemyError as exc:
            raise ConstructionJobError("Construction job transition failed") from exc

    def begin_commit(
        self, job_id: str, worker_id: str, lease_epoch: int
    ) -> ConstructionJobV1:
        return self._transition(
            job_id,
            worker_id,
            lease_epoch,
            {"RUNNING"},
            lambda row, now: (
                setattr(row, "status", "COMMITTING"),
                setattr(row, "updated_at", now),
            ),
        )

    def complete_success(
        self,
        job_id: str,
        worker_id: str,
        lease_epoch: int,
        *,
        run_id: str,
    ) -> ConstructionJobV1:
        def mutate(row: StudioConstructionJobRow, now: datetime) -> None:
            if row.run_id != run_id:
                raise ConstructionJobConflict("Construction result run identity mismatch")
            row.status = "SUCCEEDED"
            row.result_run_id = run_id
            row.completed_at = now
            row.updated_at = now

        return self._transition(
            job_id, worker_id, lease_epoch, {"COMMITTING"}, mutate
        )

    def fail_attempt(
        self,
        job_id: str,
        worker_id: str,
        lease_epoch: int,
        *,
        error_code: str,
        stale: bool = False,
    ) -> ConstructionJobV1:
        def mutate(row: StudioConstructionJobRow, now: datetime) -> None:
            row.status = (
                "CANCELLED"
                if row.status == "CANCEL_REQUESTED"
                else "STALE"
                if stale
                else "FAILED"
            )
            row.error_code = error_code
            row.completed_at = now
            row.updated_at = now

        return self._transition(
            job_id,
            worker_id,
            lease_epoch,
            {"RUNNING", "COMMITTING", "CANCEL_REQUESTED"},
            mutate,
        )

    def cancel(self, job_id: str) -> ConstructionJobV1:
        try:
            from sqlalchemy.orm import Session

            with Session(self.engine) as session, session.begin():
                row = session.scalar(
                    select(StudioConstructionJobRow)
                    .where(StudioConstructionJobRow.job_id == job_id)
                    .with_for_update()
                )
                if row is None:
                    raise ConstructionJobError("Construction job is unavailable")
                now = self.clock()
                if row.status == "QUEUED":
                    row.status = "CANCELLED"
                    row.error_code = "CANCELLED_BY_USER"
                    row.completed_at = now
                    row.updated_at = now
                elif row.status == "RUNNING":
                    row.status = "CANCEL_REQUESTED"
                    row.updated_at = now
                session.flush()
                return self._value(row)
        except ConstructionJobError:
            raise
        except SQLAlchemyError as exc:
            raise ConstructionJobError("Construction job cancel failed") from exc

    def retry(self, job_id: str) -> ConstructionJobV1:
        previous = self.get(job_id)
        if previous.status not in {"FAILED", "CANCELLED", "STALE"}:
            raise ConstructionJobConflict(
                "Only failed, cancelled or stale jobs can retry"
            )
        return self.enqueue(
            ConstructionJobInputV1(
                workspace_id=previous.workspace_id,
                solution_id=previous.solution_id,
                base_revision=previous.base_revision,
                base_draft_checksum=previous.base_draft_checksum,
                source_set_digest=previous.source_set_digest,
                selected_source_version_ids=previous.selected_source_version_ids,
                profile_ref=previous.profile_ref,
            )
        )
