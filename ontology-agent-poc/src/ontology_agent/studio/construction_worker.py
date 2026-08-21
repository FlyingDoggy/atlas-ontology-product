from __future__ import annotations

import socket
import time
import uuid
from typing import Callable, Protocol

from .construction import ConstructionError, ConstructionRunV1
from .construction_jobs import (
    ConstructionJobConflict,
    ConstructionJobError,
    ConstructionJobStore,
    ConstructionJobV1,
)
from .workspace import WorkspaceConflictError


class ConstructionServicePort(Protocol):
    def start(
        self,
        *,
        expected_revision: int,
        planned_run_id: str | None = None,
        attempt_id: str | None = None,
        lease_epoch: int = 1,
        commit_fence: Callable[[], None] | None = None,
    ) -> ConstructionRunV1: ...

    def get(self, run_id: str) -> ConstructionRunV1: ...


class ConstructionWorker:
    """One durable PostgreSQL job consumer; no in-process task authority."""

    def __init__(
        self,
        *,
        jobs: ConstructionJobStore,
        service_factory: Callable[[str, tuple[str, ...]], ConstructionServicePort],
        worker_id: str | None = None,
        lease_seconds: int = 120,
    ) -> None:
        self.jobs = jobs
        self.service_factory = service_factory
        self.worker_id = worker_id or f"{socket.gethostname()}-{uuid.uuid4().hex[:12]}"
        self.lease_seconds = lease_seconds

    def _finish_failure(
        self,
        job: ConstructionJobV1,
        *,
        error_code: str,
        stale: bool = False,
    ) -> ConstructionJobV1:
        try:
            return self.jobs.fail_attempt(
                job.job_id,
                self.worker_id,
                job.lease_epoch,
                error_code=error_code,
                stale=stale,
            )
        except ConstructionJobConflict:
            # Another epoch owns the job now. The old attempt is fenced and
            # must not reinterpret the current terminal outcome.
            return self.jobs.get(job.job_id)

    def process_one(self) -> ConstructionJobV1 | None:
        job = self.jobs.claim_next(
            self.worker_id, lease_seconds=self.lease_seconds
        )
        if job is None:
            return None
        service = self.service_factory(
            job.workspace_id, job.selected_source_version_ids
        )

        # Crash recovery: an immutable run may have committed just before the
        # previous worker lost its lease. Reconcile it instead of recomputing.
        try:
            existing = service.get(job.run_id)
        except ConstructionError:
            existing = None
        if existing is not None:
            try:
                self.jobs.begin_commit(job.job_id, self.worker_id, job.lease_epoch)
                return self.jobs.complete_success(
                    job.job_id,
                    self.worker_id,
                    job.lease_epoch,
                    run_id=existing.run_id,
                )
            except ConstructionJobConflict:
                return self.jobs.get(job.job_id)

        try:
            run = service.start(
                expected_revision=job.base_revision,
                planned_run_id=job.run_id,
                attempt_id=job.attempt_id,
                lease_epoch=job.lease_epoch,
                commit_fence=lambda: self.jobs.begin_commit(
                    job.job_id, self.worker_id, job.lease_epoch
                ),
            )
            return self.jobs.complete_success(
                job.job_id,
                self.worker_id,
                job.lease_epoch,
                run_id=run.run_id,
            )
        except WorkspaceConflictError:
            return self._finish_failure(
                job, error_code="DRAFT_CHANGED", stale=True
            )
        except ConstructionJobConflict:
            return self._finish_failure(job, error_code="CANCELLED_BY_USER")
        except (ConstructionError, ConstructionJobError, ValueError):
            return self._finish_failure(job, error_code="CONSTRUCTION_FAILED")

    def run_forever(self, *, poll_seconds: float = 1.0) -> None:
        while True:
            result = self.process_one()
            if result is None:
                time.sleep(poll_seconds)
