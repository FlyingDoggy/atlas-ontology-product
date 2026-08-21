from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .io import canonical_bytes, sha256_value
from .llm_contracts import (
    AutomaticOffLatch,
    EngineeringDemoCommitReceipt,
    EngineeringDemoCommitSubject,
    EngineeringDemoResponse,
    RunCapability,
    TaskRolloutRecord,
)


class EngineeringCommitConflict(RuntimeError):
    """A private candidate is no longer eligible to become user-visible."""


class EngineeringDemoCommitStore:
    """Small transactional boundary for one single-host Engineering Demo.

    SQLite owns the rollout head and response commit in one serialization domain.
    It is intentionally not the Frozen Core ResultReleaseCommit implementation.
    """

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS rollout_control (
                    task TEXT PRIMARY KEY,
                    rollout_json TEXT NOT NULL,
                    rollout_digest TEXT NOT NULL,
                    epoch INTEGER NOT NULL,
                    status TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS response_commits (
                    run_id TEXT PRIMARY KEY,
                    candidate_digest TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    receipt_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS automatic_off_latches (
                    rollout_digest TEXT PRIMARY KEY,
                    latch_json TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def _latch_from_row(row: sqlite3.Row | None) -> AutomaticOffLatch | None:
        if row is None:
            return None
        return AutomaticOffLatch.model_validate_json(row["latch_json"])

    def automatic_off_latch(
        self, rollout: TaskRolloutRecord
    ) -> AutomaticOffLatch | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT latch_json FROM automatic_off_latches WHERE rollout_digest = ?",
                (sha256_value(rollout),),
            ).fetchone()
        return self._latch_from_row(row)

    def trip_automatic_off(
        self,
        rollout: TaskRolloutRecord,
        trigger: str,
        *,
        now: datetime | None = None,
    ) -> AutomaticOffLatch:
        if trigger not in rollout.auto_off_triggers:
            raise EngineeringCommitConflict("Trigger is not authorized for automatic off")
        instant = now or datetime.now(timezone.utc)
        rollout_digest = sha256_value(rollout)
        unsigned = {
            "contract": "engineering-automatic-off-latch/v1",
            "task": rollout.task,
            "rollout_id": rollout.rollout_id,
            "rollout_epoch": rollout.epoch,
            "rollout_digest": rollout_digest,
            "trigger": trigger,
            "tripped_at": instant,
        }
        latch = AutomaticOffLatch(
            **unsigned,
            latch_digest=sha256_value(unsigned),
        )
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                current = connection.execute(
                    "SELECT rollout_digest FROM rollout_control WHERE task = ?",
                    (rollout.task,),
                ).fetchone()
                if current is None or current["rollout_digest"] != rollout_digest:
                    raise EngineeringCommitConflict(
                        "Only the exact current rollout can be automatically stopped"
                    )
                existing = connection.execute(
                    "SELECT latch_json FROM automatic_off_latches WHERE rollout_digest = ?",
                    (rollout_digest,),
                ).fetchone()
                if existing is not None:
                    installed = self._latch_from_row(existing)
                    assert installed is not None
                    if installed.trigger != trigger:
                        raise EngineeringCommitConflict(
                            "The rollout is already stopped for another trigger"
                        )
                    connection.commit()
                    return installed
                connection.execute(
                    "INSERT INTO automatic_off_latches(rollout_digest, latch_json) VALUES (?, ?)",
                    (
                        rollout_digest,
                        canonical_bytes(latch).decode("utf-8"),
                    ),
                )
                connection.commit()
                return latch
            except Exception:
                connection.rollback()
                raise

    def install_rollout(self, rollout: TaskRolloutRecord) -> None:
        payload = canonical_bytes(rollout).decode("utf-8")
        digest = sha256_value(rollout)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                current = connection.execute(
                    "SELECT rollout_digest, epoch FROM rollout_control WHERE task = ?",
                    (rollout.task,),
                ).fetchone()
                if current is None:
                    connection.execute(
                        "INSERT INTO rollout_control(task, rollout_json, rollout_digest, epoch, status) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (rollout.task, payload, digest, rollout.epoch, rollout.status),
                    )
                elif current["rollout_digest"] == digest:
                    pass
                elif rollout.epoch != int(current["epoch"]) + 1:
                    raise EngineeringCommitConflict(
                        "A changed rollout must advance the epoch by exactly one"
                    )
                else:
                    connection.execute(
                        "UPDATE rollout_control SET rollout_json = ?, rollout_digest = ?, "
                        "epoch = ?, status = ? WHERE task = ?",
                        (payload, digest, rollout.epoch, rollout.status, rollout.task),
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def begin_run(
        self,
        *,
        rollout: TaskRolloutRecord,
        run_id: str,
        snapshot_checksum: str,
        question_case_id: str,
        principal: str,
        purpose: str,
        now: datetime | None = None,
    ) -> RunCapability:
        instant = now or datetime.now(timezone.utc)
        with self._connect() as connection:
            current = connection.execute(
                "SELECT rollout_json, rollout_digest FROM rollout_control WHERE task = ?",
                (rollout.task,),
            ).fetchone()
        if current is None or current["rollout_digest"] != sha256_value(rollout):
            raise EngineeringCommitConflict("The requested rollout is not current")
        if self.automatic_off_latch(rollout) is not None:
            raise EngineeringCommitConflict("The exact rollout is automatically off")
        installed = TaskRolloutRecord.model_validate_json(current["rollout_json"])
        if (
            installed.status != "ACTIVE"
            or not (installed.issued_at <= instant < installed.expires_at)
        ):
            raise EngineeringCommitConflict("The current rollout is off or expired")
        return RunCapability(
            contract="engineering-run-capability/v1",
            run_id=run_id,
            rollout_id=installed.rollout_id,
            rollout_epoch=installed.epoch,
            snapshot_checksum=snapshot_checksum,
            profile_digest=installed.profile_digest,
            question_family_checksum=installed.question_family_checksum,
            egress_decision_digest=installed.egress_decision_digest,
            question_case_id=question_case_id,
            principal=principal,
            purpose=purpose,
            tool_ids=("compare_periods", "rank_contributors", "decompose_change"),
            issued_at=instant,
            expires_at=min(installed.expires_at, instant + timedelta(seconds=15)),
        )

    def commit(
        self,
        capability: RunCapability,
        candidate: EngineeringDemoResponse,
        *,
        now: datetime | None = None,
    ) -> EngineeringDemoCommitReceipt:
        instant = now or datetime.now(timezone.utc)
        if (
            candidate.outcome != "ANSWERED"
            or candidate.committed
            or candidate.commit_digest is not None
            or candidate.run_id != capability.run_id
            or candidate.snapshot_checksum != capability.snapshot_checksum
            or candidate.profile_digest != capability.profile_digest
            or candidate.result is None
        ):
            raise EngineeringCommitConflict("The response candidate is not commit eligible")
        candidate_digest = sha256_value(candidate)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = connection.execute(
                    "SELECT candidate_digest, response_json, receipt_json "
                    "FROM response_commits WHERE run_id = ?",
                    (capability.run_id,),
                ).fetchone()
                if existing is not None:
                    if existing["candidate_digest"] != candidate_digest:
                        raise EngineeringCommitConflict(
                            "The run id is already committed to different response bytes"
                        )
                    connection.commit()
                    return EngineeringDemoCommitReceipt.model_validate_json(
                        existing["receipt_json"]
                    )

                current = connection.execute(
                    "SELECT rollout_json FROM rollout_control WHERE task = ?",
                    ("adt-engineering-demo",),
                ).fetchone()
                if current is None:
                    raise EngineeringCommitConflict("The rollout head is missing")
                rollout = TaskRolloutRecord.model_validate_json(current["rollout_json"])
                latched = connection.execute(
                    "SELECT 1 FROM automatic_off_latches WHERE rollout_digest = ?",
                    (sha256_value(rollout),),
                ).fetchone()
                if latched is not None:
                    raise EngineeringCommitConflict(
                        "The exact rollout is automatically off"
                    )
                if (
                    rollout.status != "ACTIVE"
                    or rollout.rollout_id != capability.rollout_id
                    or rollout.epoch != capability.rollout_epoch
                    or rollout.profile_digest != capability.profile_digest
                    or rollout.question_family_checksum
                    != capability.question_family_checksum
                    or rollout.egress_decision_digest
                    != capability.egress_decision_digest
                    or not (capability.issued_at <= instant < capability.expires_at)
                    or not (rollout.issued_at <= instant < rollout.expires_at)
                ):
                    raise EngineeringCommitConflict(
                        "The rollout changed or expired before final commit"
                    )

                response_without_commit_ref = candidate.model_copy(
                    update={"committed": True, "commit_digest": None}
                )
                response_digest = sha256_value(response_without_commit_ref)
                subject = EngineeringDemoCommitSubject(
                    contract="engineering-demo-response-commit/v1",
                    commit_id="commit." + capability.run_id.removeprefix("run."),
                    run_id=capability.run_id,
                    outcome="ANSWERED",
                    snapshot_checksum=capability.snapshot_checksum,
                    profile_digest=capability.profile_digest,
                    rollout_id=capability.rollout_id,
                    rollout_epoch=capability.rollout_epoch,
                    egress_decision_digest=capability.egress_decision_digest,
                    response_digest=response_digest,
                    committed_at=instant,
                )
                receipt = EngineeringDemoCommitReceipt(
                    **subject.model_dump(mode="python"),
                    commit_digest=sha256_value(subject),
                )
                final_response = response_without_commit_ref.model_copy(
                    update={"commit_digest": receipt.commit_digest}
                )
                connection.execute(
                    "INSERT INTO response_commits(run_id, candidate_digest, response_json, receipt_json) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        capability.run_id,
                        candidate_digest,
                        canonical_bytes(final_response).decode("utf-8"),
                        canonical_bytes(receipt).decode("utf-8"),
                    ),
                )
                connection.commit()
                return receipt
            except Exception:
                connection.rollback()
                raise

    def read_response(self, run_id: str) -> EngineeringDemoResponse:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT response_json FROM response_commits WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            raise KeyError(run_id)
        return EngineeringDemoResponse.model_validate_json(row["response_json"])

    def commit_count(self, run_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM response_commits WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return int(row["count"])
