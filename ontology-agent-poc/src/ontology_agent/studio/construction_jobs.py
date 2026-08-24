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
from ..models import AuthoringLanguage, StrictModel
from ..product_context import Base, ProductInfrastructureSettings
from .agentic_contracts import AgentEngineContractV2, BuildObjectiveV1


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
ConstructionJobStage = Literal[
    "QUEUED",
    "SOURCE_SETTLEMENT",
    "BUILDING_CANDIDATES",
    "REVIEWING_CANDIDATES",
    "PERSISTING_RESULT",
    "COMPLETED",
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
    authoring_language: AuthoringLanguage | None = None
    language_policy_digest: Sha256 | None = None
    profile_ref: str = Field(min_length=1, max_length=255)
    engine_contract: AgentEngineContractV2 | None = None
    build_objective: BuildObjectiveV1 | None = None
    resume_from_attempt_id: str | None = Field(
        default=None, pattern=r"^construction-attempt\.[0-9a-f]{32}$"
    )

    @model_validator(mode="after")
    def frozen_agentic_inputs_are_paired(self) -> ConstructionJobInputV1:
        if (self.engine_contract is None) != (self.build_objective is None):
            raise ValueError(
                "Agent Engine Contract and Build Objective must be frozen together"
            )
        if self.engine_contract is not None and self.build_objective is not None:
            if (
                self.engine_contract.objective_checksum
                != self.build_objective.objective_checksum
            ):
                raise ValueError("Frozen Agent Engine does not match Build Objective")
            if self.engine_contract.source_set_digest != self.source_set_digest:
                raise ValueError("Frozen Agent Engine does not match source set")
            if (
                self.build_objective.selected_source_version_ids
                != self.selected_source_version_ids
            ):
                raise ValueError("Frozen Build Objective does not match source selection")
        if self.resume_from_attempt_id is not None and self.engine_contract is None:
            raise ValueError("Only an Agentic construction job can resume Candidates")
        return self


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
    authoring_language: AuthoringLanguage | None = None
    language_policy_digest: Sha256 | None = None
    profile_ref: str = Field(min_length=1, max_length=255)
    engine_contract: AgentEngineContractV2 | None = None
    build_objective: BuildObjectiveV1 | None = None
    resume_from_attempt_id: str | None = Field(
        default=None, pattern=r"^construction-attempt\.[0-9a-f]{32}$"
    )
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
    current_stage: ConstructionJobStage = "QUEUED"
    completed_stages: int = Field(default=0, ge=0, le=6)
    total_stages: int = Field(default=6, ge=1, le=20)
    progress_message: str = Field(default="JOB_QUEUED", min_length=1, max_length=100)
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime

    @model_validator(mode="after")
    def coherent_state(self) -> ConstructionJobV1:
        if self.resume_from_attempt_id is not None and self.engine_contract is None:
            raise ValueError("Only an Agentic construction job can resume Candidates")
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

    def list_all(self) -> tuple[ConstructionJobV1, ...]: ...

    def claim_next(
        self, worker_id: str, *, lease_seconds: int = 120
    ) -> ConstructionJobV1 | None: ...

    def begin_commit(
        self, job_id: str, worker_id: str, lease_epoch: int
    ) -> ConstructionJobV1: ...

    def report_progress(
        self,
        job_id: str,
        worker_id: str,
        lease_epoch: int,
        *,
        current_stage: ConstructionJobStage,
        completed_stages: int,
        progress_message: str,
    ) -> ConstructionJobV1: ...

    def renew_lease(
        self,
        job_id: str,
        worker_id: str,
        lease_epoch: int,
        *,
        lease_seconds: int,
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

    def defer_attempt(
        self,
        job_id: str,
        worker_id: str,
        lease_epoch: int,
        *,
        retry_after_seconds: int = 5,
    ) -> ConstructionJobV1: ...

    def cancel(self, job_id: str) -> ConstructionJobV1: ...

    def retry(
        self,
        job_id: str,
        *,
        engine_contract: AgentEngineContractV2 | None = None,
    ) -> ConstructionJobV1: ...


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
        authoring_language=value.authoring_language,
        language_policy_digest=value.language_policy_digest,
        profile_ref=value.profile_ref,
        engine_contract=value.engine_contract,
        build_objective=value.build_objective,
        resume_from_attempt_id=value.resume_from_attempt_id,
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
            job.authoring_language == value.authoring_language,
            job.language_policy_digest == value.language_policy_digest,
            job.profile_ref == value.profile_ref,
            job.engine_contract == value.engine_contract,
            job.build_objective == value.build_objective,
            job.resume_from_attempt_id == value.resume_from_attempt_id,
        )
    )


def validate_continuation_engine_contract(
    frozen: AgentEngineContractV2,
    continuation: AgentEngineContractV2,
) -> AgentEngineContractV2:
    """Accept only a budget-reduced copy of the frozen Agent authority.

    A continuation receives a fresh, bounded budget, so its engine checksum is
    intentionally different.  Model, Skill, tool policy, source scope and
    objective authority remain immutable.
    """

    budget_fields = {
        "max_model_calls",
        "max_tool_calls",
        "max_input_tokens",
        "max_output_tokens",
        "engine_checksum",
    }
    frozen_scope = {
        key: value
        for key, value in frozen.model_dump(mode="json").items()
        if key not in budget_fields
    }
    requested_scope = {
        key: value
        for key, value in continuation.model_dump(mode="json").items()
        if key not in budget_fields
    }
    if requested_scope != frozen_scope:
        raise ConstructionJobConflict(
            "Candidate continuation cannot change its model, Skill, tools or source scope"
        )
    if (
        continuation.max_model_calls > frozen.max_model_calls
        or continuation.max_tool_calls > frozen.max_tool_calls
        or continuation.max_input_tokens > frozen.max_input_tokens
        or continuation.max_output_tokens > frozen.max_output_tokens
    ):
        raise ConstructionJobConflict(
            "Candidate continuation may reduce but never expand the frozen budget"
        )
    return continuation


def _retry_engine(
    previous: ConstructionJobV1,
    requested: AgentEngineContractV2 | None,
) -> AgentEngineContractV2 | None:
    frozen = previous.engine_contract
    if requested is None:
        return frozen
    if frozen is None:
        raise ConstructionJobConflict(
            "A deterministic construction job cannot adopt an Agent engine on retry"
        )
    return validate_continuation_engine_contract(frozen, requested)


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

    def list_all(self) -> tuple[ConstructionJobV1, ...]:
        return tuple(
            sorted(
                self._jobs.values(),
                key=lambda item: item.created_at,
                reverse=True,
            )
        )

    def claim_next(
        self, worker_id: str, *, lease_seconds: int = 120
    ) -> ConstructionJobV1 | None:
        with self._lock:
            now = self.clock()
            # A cancellation request belongs to the running worker while its
            # lease is valid.  Once that lease expires there is no worker left
            # that can acknowledge the request, so the durable scheduler must
            # finish the cancellation before admitting more work.
            for job_id, job in tuple(self._jobs.items()):
                if (
                    job.status == "CANCEL_REQUESTED"
                    and job.lease_expires_at is not None
                    and job.lease_expires_at <= now
                ):
                    self._jobs[job_id] = job.model_copy(
                        update={
                            "status": "CANCELLED",
                            "error_code": "CANCELLED_BY_USER",
                            "current_stage": "CANCELLED",
                            "progress_message": "CANCELLED_BY_USER",
                            "completed_at": now,
                            "updated_at": now,
                        }
                    )
            eligible = sorted(self._jobs.values(), key=lambda item: item.created_at)
            for job in eligible:
                reclaim = (
                    job.status in {"RUNNING", "COMMITTING"}
                    and job.lease_expires_at is not None
                    and job.lease_expires_at <= now
                )
                if job.status != "QUEUED" and not reclaim:
                    continue
                attempt_id = (
                    job.attempt_id
                    if reclaim and job.engine_contract is not None and job.attempt_id
                    else "construction-attempt." + uuid.uuid4().hex
                )
                claimed = job.model_copy(
                    update={
                        "status": "RUNNING",
                        "attempt_id": attempt_id,
                        "lease_epoch": job.lease_epoch + 1,
                        "lease_owner": worker_id,
                        "lease_expires_at": now + timedelta(seconds=lease_seconds),
                        "started_at": job.started_at or now,
                        "current_stage": "SOURCE_SETTLEMENT",
                        "completed_stages": 1,
                        "progress_message": "SOURCE_VERSIONS_BOUND",
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
                update={
                    "status": "COMMITTING",
                    "current_stage": "PERSISTING_RESULT",
                    "completed_stages": 5,
                    "progress_message": "IMMUTABLE_RUN_COMMITTING",
                    "updated_at": self.clock(),
                }
            )
            self._jobs[job_id] = updated
            return updated

    def report_progress(
        self,
        job_id: str,
        worker_id: str,
        lease_epoch: int,
        *,
        current_stage: ConstructionJobStage,
        completed_stages: int,
        progress_message: str,
    ) -> ConstructionJobV1:
        with self._lock:
            job = self._leased(job_id, worker_id, lease_epoch)
            if job.status != "RUNNING":
                raise ConstructionJobConflict("Construction attempt is not running")
            if completed_stages < job.completed_stages or completed_stages >= job.total_stages:
                raise ConstructionJobConflict("Construction progress is not monotonic")
            updated = job.model_copy(
                update={
                    "current_stage": current_stage,
                    "completed_stages": completed_stages,
                    "progress_message": progress_message,
                    "updated_at": self.clock(),
                }
            )
            self._jobs[job_id] = updated
            return updated

    def renew_lease(
        self,
        job_id: str,
        worker_id: str,
        lease_epoch: int,
        *,
        lease_seconds: int,
    ) -> ConstructionJobV1:
        with self._lock:
            job = self._leased(job_id, worker_id, lease_epoch)
            if job.status not in {"RUNNING", "COMMITTING"}:
                raise ConstructionJobConflict(
                    "Construction attempt is not authorized to renew its lease"
                )
            now = self.clock()
            updated = job.model_copy(
                update={
                    "lease_expires_at": now + timedelta(seconds=lease_seconds),
                    "updated_at": now,
                }
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
                    "current_stage": "COMPLETED",
                    "completed_stages": job.total_stages,
                    "progress_message": "IMMUTABLE_RUN_COMMITTED",
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
                    "current_stage": (
                        "CANCELLED"
                        if status == "CANCELLED"
                        else "STALE"
                        if status == "STALE"
                        else "FAILED"
                    ),
                    "progress_message": error_code,
                    "completed_at": now,
                    "updated_at": now,
                }
            )
            self._jobs[job_id] = updated
            return updated

    def defer_attempt(
        self,
        job_id: str,
        worker_id: str,
        lease_epoch: int,
        *,
        retry_after_seconds: int = 5,
    ) -> ConstructionJobV1:
        with self._lock:
            job = self._leased(job_id, worker_id, lease_epoch)
            if job.status != "RUNNING":
                raise ConstructionJobConflict("Construction attempt is not running")
            now = self.clock()
            updated = job.model_copy(
                update={
                    "lease_expires_at": now
                    + timedelta(seconds=max(1, retry_after_seconds)),
                    "progress_message": "MODEL_GATEWAY_RETRY_PENDING",
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
                        "current_stage": "CANCELLED",
                        "progress_message": "CANCELLED_BY_USER",
                        "completed_at": now,
                        "updated_at": now,
                    }
                )
            elif job.status == "RUNNING":
                updated = job.model_copy(
                    update={
                        "status": "CANCEL_REQUESTED",
                        "progress_message": "CANCEL_REQUESTED",
                        "updated_at": now,
                    }
                )
            else:
                return job
            self._jobs[job_id] = updated
            return updated

    def retry(
        self,
        job_id: str,
        *,
        engine_contract: AgentEngineContractV2 | None = None,
    ) -> ConstructionJobV1:
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
                    authoring_language=job.authoring_language,
                    language_policy_digest=job.language_policy_digest,
                    profile_ref=job.profile_ref,
                    engine_contract=_retry_engine(job, engine_contract),
                    build_objective=job.build_objective,
                    resume_from_attempt_id=(
                        job.attempt_id
                        if job.engine_contract is not None and job.attempt_id is not None
                        else None
                    ),
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
    authoring_language: Mapped[str | None] = mapped_column(String(8))
    language_policy_digest: Mapped[str | None] = mapped_column(String(64))
    profile_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    engine_contract: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    build_objective: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    resume_from_attempt_id: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_id: Mapped[str | None] = mapped_column(String(80))
    lease_epoch: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(255))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_run_id: Mapped[str | None] = mapped_column(String(80))
    error_code: Mapped[str | None] = mapped_column(String(100))
    current_stage: Mapped[str] = mapped_column(String(64), nullable=False, default="QUEUED")
    completed_stages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_stages: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    progress_message: Mapped[str] = mapped_column(String(100), nullable=False, default="JOB_QUEUED")
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
            if name == "contract":
                continue
            if name == "selected_source_version_ids":
                setattr(row, name, list(field))
            elif name in {"engine_contract", "build_objective"}:
                setattr(row, name, field)
            else:
                setattr(row, name, field)

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
                    row_payload["engine_contract"] = (
                        job.engine_contract.model_dump(mode="json")
                        if job.engine_contract is not None
                        else None
                    )
                    row_payload["build_objective"] = (
                        job.build_objective.model_dump(mode="json")
                        if job.build_objective is not None
                        else None
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

    def list_all(self) -> tuple[ConstructionJobV1, ...]:
        try:
            from sqlalchemy.orm import Session

            with Session(self.engine) as session:
                rows = session.scalars(
                    select(StudioConstructionJobRow).order_by(
                        StudioConstructionJobRow.created_at.desc()
                    )
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
                abandoned_cancellations = session.scalars(
                    select(StudioConstructionJobRow)
                    .where(
                        StudioConstructionJobRow.status == "CANCEL_REQUESTED",
                        StudioConstructionJobRow.lease_expires_at <= now,
                    )
                    .with_for_update(skip_locked=True)
                ).all()
                for cancelled in abandoned_cancellations:
                    cancelled.status = "CANCELLED"
                    cancelled.error_code = "CANCELLED_BY_USER"
                    cancelled.current_stage = "CANCELLED"
                    cancelled.progress_message = "CANCELLED_BY_USER"
                    cancelled.completed_at = now
                    cancelled.updated_at = now
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
                reclaim = row.status in {"RUNNING", "COMMITTING"}
                row.status = "RUNNING"
                if not (reclaim and row.engine_contract and row.attempt_id):
                    row.attempt_id = "construction-attempt." + uuid.uuid4().hex
                row.lease_epoch += 1
                row.lease_owner = worker_id
                row.lease_expires_at = now + timedelta(seconds=lease_seconds)
                row.started_at = row.started_at or now
                row.current_stage = "SOURCE_SETTLEMENT"
                row.completed_stages = 1
                row.progress_message = "SOURCE_VERSIONS_BOUND"
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
                setattr(row, "current_stage", "PERSISTING_RESULT"),
                setattr(row, "completed_stages", 5),
                setattr(row, "progress_message", "IMMUTABLE_RUN_COMMITTING"),
                setattr(row, "updated_at", now),
            ),
        )

    def report_progress(
        self,
        job_id: str,
        worker_id: str,
        lease_epoch: int,
        *,
        current_stage: ConstructionJobStage,
        completed_stages: int,
        progress_message: str,
    ) -> ConstructionJobV1:
        def mutate(row: StudioConstructionJobRow, now: datetime) -> None:
            if completed_stages < row.completed_stages or completed_stages >= row.total_stages:
                raise ConstructionJobConflict("Construction progress is not monotonic")
            row.current_stage = current_stage
            row.completed_stages = completed_stages
            row.progress_message = progress_message
            row.updated_at = now

        return self._transition(
            job_id, worker_id, lease_epoch, {"RUNNING"}, mutate
        )

    def renew_lease(
        self,
        job_id: str,
        worker_id: str,
        lease_epoch: int,
        *,
        lease_seconds: int,
    ) -> ConstructionJobV1:
        def mutate(row: StudioConstructionJobRow, now: datetime) -> None:
            row.lease_expires_at = now + timedelta(seconds=lease_seconds)
            row.updated_at = now

        return self._transition(
            job_id,
            worker_id,
            lease_epoch,
            {"RUNNING", "COMMITTING"},
            mutate,
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
            row.current_stage = "COMPLETED"
            row.completed_stages = row.total_stages
            row.progress_message = "IMMUTABLE_RUN_COMMITTED"
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
            row.current_stage = (
                "CANCELLED"
                if row.status == "CANCELLED"
                else "STALE"
                if row.status == "STALE"
                else "FAILED"
            )
            row.progress_message = error_code
            row.completed_at = now
            row.updated_at = now

        return self._transition(
            job_id,
            worker_id,
            lease_epoch,
            {"RUNNING", "COMMITTING", "CANCEL_REQUESTED"},
            mutate,
        )

    def defer_attempt(
        self,
        job_id: str,
        worker_id: str,
        lease_epoch: int,
        *,
        retry_after_seconds: int = 5,
    ) -> ConstructionJobV1:
        def mutate(row: StudioConstructionJobRow, now: datetime) -> None:
            row.lease_expires_at = now + timedelta(
                seconds=max(1, retry_after_seconds)
            )
            row.progress_message = "MODEL_GATEWAY_RETRY_PENDING"
            row.updated_at = now

        return self._transition(
            job_id,
            worker_id,
            lease_epoch,
            {"RUNNING"},
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
                    row.current_stage = "CANCELLED"
                    row.progress_message = "CANCELLED_BY_USER"
                    row.completed_at = now
                    row.updated_at = now
                elif row.status == "RUNNING":
                    row.status = "CANCEL_REQUESTED"
                    row.progress_message = "CANCEL_REQUESTED"
                    row.updated_at = now
                session.flush()
                return self._value(row)
        except ConstructionJobError:
            raise
        except SQLAlchemyError as exc:
            raise ConstructionJobError("Construction job cancel failed") from exc

    def retry(
        self,
        job_id: str,
        *,
        engine_contract: AgentEngineContractV2 | None = None,
    ) -> ConstructionJobV1:
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
                authoring_language=previous.authoring_language,
                language_policy_digest=previous.language_policy_digest,
                profile_ref=previous.profile_ref,
                engine_contract=_retry_engine(previous, engine_contract),
                build_objective=previous.build_objective,
                resume_from_attempt_id=(
                    previous.attempt_id
                    if previous.engine_contract is not None
                    and previous.attempt_id is not None
                    else None
                ),
            )
        )
