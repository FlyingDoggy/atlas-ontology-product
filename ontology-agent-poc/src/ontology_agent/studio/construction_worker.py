from __future__ import annotations

import logging
import socket
import threading
import time
import uuid
from typing import Callable, Protocol

from .construction import (
    ConstructionError,
    ConstructionRetryableError,
    ConstructionRunV1,
)
from .construction_jobs import (
    ConstructionJobConflict,
    ConstructionJobError,
    ConstructionJobStage,
    ConstructionJobStore,
    ConstructionJobV1,
)
from .workspace import WorkspaceConflictError


logger = logging.getLogger(__name__)


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

    def start_agentic(
        self,
        *,
        job: ConstructionJobV1,
        commit_fence: Callable[[], None] | None = None,
        execution_fence: Callable[[], None] | None = None,
        progress_callback: (
            Callable[[ConstructionJobStage, int, str], None] | None
        ) = None,
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

    @staticmethod
    def _language_matches(job: ConstructionJobV1, run: ConstructionRunV1) -> bool:
        return (
            run.authoring_language == job.authoring_language
            and run.language_policy_digest == job.language_policy_digest
        )

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
        if existing is not None and not self._language_matches(job, existing):
            return self._finish_failure(job, error_code="LANGUAGE_POLICY_MISMATCH")
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
            self.jobs.report_progress(
                job.job_id,
                self.worker_id,
                job.lease_epoch,
                current_stage="BUILDING_CANDIDATES",
                completed_stages=2,
                progress_message="BUILDER_RUNNING",
            )
            stop_heartbeat = threading.Event()
            heartbeat_failure: list[Exception] = []

            def heartbeat() -> None:
                interval = max(1.0, self.lease_seconds / 3)
                while not stop_heartbeat.wait(interval):
                    try:
                        self.jobs.renew_lease(
                            job.job_id,
                            self.worker_id,
                            job.lease_epoch,
                            lease_seconds=self.lease_seconds,
                        )
                    except Exception as exc:  # fenced by the exact lease below
                        heartbeat_failure.append(exc)
                        logger.warning(
                            "Construction lease heartbeat stopped",
                            extra={"job_id": job.job_id, "run_id": job.run_id},
                        )
                        return

            heartbeat_thread = threading.Thread(
                target=heartbeat,
                name=f"construction-heartbeat-{job.job_id}",
                daemon=True,
            )
            heartbeat_thread.start()

            def commit_fence() -> None:
                if heartbeat_failure:
                    raise ConstructionJobConflict(
                        "Construction job lease heartbeat was lost"
                    )
                self.jobs.begin_commit(
                    job.job_id, self.worker_id, job.lease_epoch
                )

            def execution_fence() -> None:
                if heartbeat_failure:
                    raise ConstructionJobConflict(
                        "Construction job lease heartbeat was lost"
                    )
                current = self.jobs.get(job.job_id)
                if (
                    current.status != "RUNNING"
                    or current.lease_owner != self.worker_id
                    or current.lease_epoch != job.lease_epoch
                ):
                    raise ConstructionJobConflict(
                        "Construction execution was cancelled or fenced"
                    )

            def report_agentic_progress(
                stage: ConstructionJobStage,
                completed_stages: int,
                progress_message: str,
            ) -> None:
                if heartbeat_failure:
                    raise ConstructionJobConflict(
                        "Construction job lease heartbeat was lost"
                    )
                self.jobs.report_progress(
                    job.job_id,
                    self.worker_id,
                    job.lease_epoch,
                    current_stage=stage,
                    completed_stages=completed_stages,
                    progress_message=progress_message,
                )

            if job.engine_contract is not None:
                try:
                    run = service.start_agentic(
                        job=job,
                        commit_fence=commit_fence,
                        execution_fence=execution_fence,
                        progress_callback=report_agentic_progress,
                    )
                finally:
                    stop_heartbeat.set()
                    heartbeat_thread.join(timeout=1)
            else:
                try:
                    run = service.start(
                        expected_revision=job.base_revision,
                        planned_run_id=job.run_id,
                        attempt_id=job.attempt_id,
                        lease_epoch=job.lease_epoch,
                        commit_fence=commit_fence,
                    )
                finally:
                    stop_heartbeat.set()
                    heartbeat_thread.join(timeout=1)
            if not self._language_matches(job, run):
                return self._finish_failure(
                    job, error_code="LANGUAGE_POLICY_MISMATCH"
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
        except ConstructionRetryableError:
            # The Candidate Workspace and model/tool journal are already
            # durable.  Release this lease and let the same attempt resume the
            # exact uncommitted model turn instead of rebuilding from source.
            logger.warning(
                "Deferring construction after a transient model-gateway failure",
                extra={"job_id": job.job_id, "run_id": job.run_id},
            )
            if job.lease_epoch >= 8:
                return self._finish_failure(
                    job, error_code="MODEL_GATEWAY_UNAVAILABLE"
                )
            try:
                return self.jobs.defer_attempt(
                    job.job_id,
                    self.worker_id,
                    job.lease_epoch,
                    retry_after_seconds=5,
                )
            except ConstructionJobConflict:
                return self.jobs.get(job.job_id)
        except (ConstructionError, ConstructionJobError, ValueError):
            logger.exception(
                "Construction failed at a governed boundary",
                extra={"job_id": job.job_id, "run_id": job.run_id},
            )
            return self._finish_failure(job, error_code="CONSTRUCTION_FAILED")
        except Exception:
            # The durable task must reach a truthful terminal state even when a
            # parser, provider adapter, or tool implementation has an unexpected
            # defect.  The traceback stays in service logs; the product contract
            # exposes only a stable technical failure code and permits retry.
            logger.exception(
                "Unexpected construction worker failure",
                extra={"job_id": job.job_id, "run_id": job.run_id},
            )
            return self._finish_failure(job, error_code="INTERNAL_ERROR")

    def run_forever(self, *, poll_seconds: float = 1.0) -> None:
        while True:
            result = self.process_one()
            if result is None:
                time.sleep(poll_seconds)
