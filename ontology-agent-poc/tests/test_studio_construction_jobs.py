from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ontology_agent.studio.construction_jobs import (
    ConstructionJobConflict,
    ConstructionJobInputV1,
    InMemoryConstructionJobStore,
)


NOW = datetime(2026, 8, 21, 4, 0, tzinfo=timezone.utc)
DIGEST_A = "a" * 64
DIGEST_B = "b" * 64


def _input(*, revision: int = 1) -> ConstructionJobInputV1:
    return ConstructionJobInputV1(
        workspace_id="workspace.adt.reference",
        solution_id="ontology.exchange_analytics.adt",
        base_revision=revision,
        base_draft_checksum=DIGEST_A,
        source_set_digest=DIGEST_B,
        profile_ref="construction-profile.source-and-semantica/v1",
    )


def test_active_job_is_deduplicated_and_claim_has_one_lease() -> None:
    store = InMemoryConstructionJobStore(clock=lambda: NOW)
    first = store.enqueue(_input())
    duplicate = store.enqueue(_input())

    assert duplicate.job_id == first.job_id
    assert first.status == "QUEUED"

    claimed = store.claim_next("worker-a", lease_seconds=60)
    assert claimed is not None
    assert claimed.status == "RUNNING"
    assert claimed.attempt_id is not None
    assert claimed.lease_epoch == 1
    assert store.claim_next("worker-b", lease_seconds=60) is None


def test_cancel_before_commit_wins_and_late_attempt_cannot_commit() -> None:
    store = InMemoryConstructionJobStore(clock=lambda: NOW)
    claimed = store.claim_next_after_enqueue(_input(), "worker-a")

    requested = store.cancel(claimed.job_id)
    assert requested.status == "CANCEL_REQUESTED"
    with pytest.raises(ConstructionJobConflict, match="not authorized to commit"):
        store.begin_commit(claimed.job_id, "worker-a", claimed.lease_epoch)

    terminal = store.fail_attempt(
        claimed.job_id,
        "worker-a",
        claimed.lease_epoch,
        error_code="CANCELLED_BY_USER",
    )
    assert terminal.status == "CANCELLED"


def test_commit_fence_before_cancel_makes_success_the_only_legal_outcome() -> None:
    store = InMemoryConstructionJobStore(clock=lambda: NOW)
    claimed = store.claim_next_after_enqueue(_input(), "worker-a")
    committing = store.begin_commit(claimed.job_id, "worker-a", claimed.lease_epoch)

    assert committing.status == "COMMITTING"
    assert store.cancel(claimed.job_id).status == "COMMITTING"

    completed = store.complete_success(
        claimed.job_id,
        "worker-a",
        claimed.lease_epoch,
        run_id=claimed.run_id,
    )
    assert completed.status == "SUCCEEDED"
    assert completed.result_run_id == claimed.run_id


def test_expired_worker_can_be_reclaimed_but_old_epoch_is_fenced() -> None:
    clock = [NOW]
    store = InMemoryConstructionJobStore(clock=lambda: clock[0])
    first = store.claim_next_after_enqueue(_input(), "worker-a", lease_seconds=5)
    clock[0] += timedelta(seconds=6)

    second = store.claim_next("worker-b", lease_seconds=30)
    assert second is not None
    assert second.job_id == first.job_id
    assert second.lease_epoch == 2
    assert second.attempt_id != first.attempt_id

    with pytest.raises(ConstructionJobConflict, match="lease is no longer current"):
        store.begin_commit(first.job_id, "worker-a", first.lease_epoch)


def test_retry_is_a_new_job_and_never_rewrites_terminal_history() -> None:
    store = InMemoryConstructionJobStore(clock=lambda: NOW)
    first = store.claim_next_after_enqueue(_input(), "worker-a")
    failed = store.fail_attempt(
        first.job_id,
        "worker-a",
        first.lease_epoch,
        error_code="SEMANTICA_UNAVAILABLE",
    )
    retry = store.retry(failed.job_id)

    assert failed.status == "FAILED"
    assert retry.job_id != failed.job_id
    assert retry.run_id != failed.run_id
    assert store.get(failed.job_id).status == "FAILED"
    assert store.get(retry.job_id).status == "QUEUED"
