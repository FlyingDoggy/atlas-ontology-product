from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ontology_agent.io import sha256_value
from ontology_agent.studio.agentic_contracts import (
    AgentEngineContractV2,
    BuildObjectiveV1,
)
from ontology_agent.studio.construction_jobs import (
    ConstructionJobConflict,
    ConstructionJobInputV1,
    InMemoryConstructionJobStore,
    validate_continuation_engine_contract,
)
from ontology_agent.studio.agentic_construction import continuation_engine_contract
from ontology_agent.studio.construction import ConstructionError
from ontology_agent.studio.construction_worker import ConstructionWorker


NOW = datetime(2026, 8, 21, 4, 0, tzinfo=timezone.utc)
DIGEST_A = "a" * 64
DIGEST_B = "b" * 64


def _agentic_contracts() -> tuple[AgentEngineContractV2, BuildObjectiveV1]:
    source_version_id = "source-version." + "1" * 32
    objective_raw = {
        "contract": "studio-build-objective/v1",
        "objective_id": "build-objective." + "2" * 32,
        "solution_id": "ontology.exchange_analytics.adt",
        "workspace_id": "workspace.adt.reference",
        "selected_source_version_ids": [source_version_id],
        "source_set_digest": DIGEST_B,
        "capabilities": ["SEMANTIC"],
        "output_language": "en",
        "obligations": [
            {
                "obligation_id": "obligation.source.coverage",
                "kind": "SOURCE_COVERAGE",
                "title": "Disposition the source",
                "source_version_ids": [source_version_id],
                "source_locator": "complete-source",
                "required": True,
            }
        ],
        "required_validators": ["candidate.materialize"],
    }
    objective_raw["objective_checksum"] = sha256_value(objective_raw)
    objective = BuildObjectiveV1.model_validate(objective_raw)
    engine_raw = {
        "contract": "studio-agent-engine/v2",
        "engine_id": "studio.agentic-builder",
        "engine_version": "2.0.0",
        "runtime_digest": "3" * 64,
        "provider": "qwen",
        "requested_model": "qwen3.8-max",
        "model_config_digest": "4" * 64,
        "skill_id": "ontology-build",
        "skill_version": "2.0.0",
        "skill_checksum": "5" * 64,
        "tool_registry_digest": "6" * 64,
        "tool_policy_digest": "7" * 64,
        "parser_contract_digest": "8" * 64,
        "source_set_digest": DIGEST_B,
        "max_model_calls": 10,
        "max_tool_calls": 20,
        "max_input_tokens": 10000,
        "max_output_tokens": 10000,
        "output_language": "en",
        "objective_checksum": objective.objective_checksum,
    }
    engine_raw["engine_checksum"] = sha256_value(engine_raw)
    return AgentEngineContractV2.model_validate(engine_raw), objective


def _input(*, revision: int = 1, agentic: bool = False) -> ConstructionJobInputV1:
    engine, objective = _agentic_contracts() if agentic else (None, None)
    return ConstructionJobInputV1(
        workspace_id="workspace.adt.reference",
        solution_id="ontology.exchange_analytics.adt",
        base_revision=revision,
        base_draft_checksum=DIGEST_A,
        source_set_digest=DIGEST_B,
        selected_source_version_ids=(
            objective.selected_source_version_ids if objective is not None else ()
        ),
        profile_ref="construction-profile.source-and-semantica/v1",
        engine_contract=engine,
        build_objective=objective,
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


def test_progress_is_monotonic_and_list_all_is_product_scoped() -> None:
    store = InMemoryConstructionJobStore(clock=lambda: NOW)
    claimed = store.claim_next_after_enqueue(_input(), "worker-a")
    progressed = store.report_progress(
        claimed.job_id,
        "worker-a",
        claimed.lease_epoch,
        current_stage="BUILDING_CANDIDATES",
        completed_stages=2,
        progress_message="BUILDING_REVIEW_CANDIDATES",
    )

    assert progressed.current_stage == "BUILDING_CANDIDATES"
    assert progressed.completed_stages == 2
    reviewing = store.report_progress(
        claimed.job_id,
        "worker-a",
        claimed.lease_epoch,
        current_stage="REVIEWING_CANDIDATES",
        completed_stages=4,
        progress_message="REVIEWER_RUNNING",
    )
    assert reviewing.current_stage == "REVIEWING_CANDIDATES"
    assert reviewing.completed_stages == 4
    assert store.list_all() == (reviewing,)
    with pytest.raises(ConstructionJobConflict, match="not monotonic"):
        store.report_progress(
            claimed.job_id,
            "worker-a",
            claimed.lease_epoch,
            current_stage="SOURCE_SETTLEMENT",
            completed_stages=1,
            progress_message="ROLLBACK_IS_NOT_PROGRESS",
        )


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


def test_worker_execution_fence_stops_agentic_work_at_cancel_boundary() -> None:
    store = InMemoryConstructionJobStore(clock=lambda: NOW)
    queued = store.enqueue(_input(agentic=True))
    reached_after_cancel = False

    class CancellingService:
        def get(self, run_id: str) -> object:
            del run_id
            raise ConstructionError("no committed run")

        def start_agentic(self, *, job: object, execution_fence: object, **_: object) -> object:
            nonlocal reached_after_cancel
            store.cancel(queued.job_id)
            assert callable(execution_fence)
            execution_fence()
            reached_after_cancel = True
            raise AssertionError("execution continued after cancellation")

    result = ConstructionWorker(
        jobs=store,
        service_factory=lambda _workspace, _sources: CancellingService(),
        worker_id="worker-cancel-fence",
    ).process_one()

    assert result is not None
    assert result.status == "CANCELLED"
    assert result.error_code == "CANCELLED_BY_USER"
    assert reached_after_cancel is False


def test_expired_cancel_request_is_terminalized_by_scheduler() -> None:
    current = [NOW]
    store = InMemoryConstructionJobStore(clock=lambda: current[0])
    claimed = store.claim_next_after_enqueue(_input(), "worker-a", lease_seconds=60)
    requested = store.cancel(claimed.job_id)

    assert requested.status == "CANCEL_REQUESTED"
    current[0] = NOW + timedelta(seconds=61)

    assert store.claim_next("worker-b") is None
    terminal = store.get(claimed.job_id)
    assert terminal.status == "CANCELLED"
    assert terminal.error_code == "CANCELLED_BY_USER"


def test_transient_failure_reclaims_same_agentic_attempt() -> None:
    current = [NOW]
    store = InMemoryConstructionJobStore(clock=lambda: current[0])
    claimed = store.claim_next_after_enqueue(
        _input(agentic=True), "worker-a", lease_seconds=60
    )

    deferred = store.defer_attempt(
        claimed.job_id,
        "worker-a",
        claimed.lease_epoch,
        retry_after_seconds=5,
    )
    assert deferred.status == "RUNNING"
    assert deferred.progress_message == "MODEL_GATEWAY_RETRY_PENDING"

    current[0] = NOW + timedelta(seconds=6)
    resumed = store.claim_next("worker-b", lease_seconds=60)
    assert resumed is not None
    assert resumed.job_id == claimed.job_id
    assert resumed.attempt_id == claimed.attempt_id
    assert resumed.lease_epoch == claimed.lease_epoch + 1


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


def test_expired_agentic_worker_reuses_attempt_journal_identity() -> None:
    clock = [NOW]
    store = InMemoryConstructionJobStore(clock=lambda: clock[0])
    first = store.claim_next_after_enqueue(
        _input(agentic=True), "worker-a", lease_seconds=5
    )
    clock[0] += timedelta(seconds=6)

    second = store.claim_next("worker-b", lease_seconds=30)

    assert second is not None
    assert second.lease_epoch == 2
    assert second.attempt_id == first.attempt_id
    assert second.engine_contract == first.engine_contract
    assert second.build_objective == first.build_objective


def test_retry_is_a_new_job_and_never_rewrites_terminal_history() -> None:
    store = InMemoryConstructionJobStore(clock=lambda: NOW)
    first = store.claim_next_after_enqueue(_input(agentic=True), "worker-a")
    failed = store.fail_attempt(
        first.job_id,
        "worker-a",
        first.lease_epoch,
        error_code="SEMANTICA_UNAVAILABLE",
    )
    assert failed.engine_contract is not None
    retry = store.retry(
        failed.job_id,
        engine_contract=continuation_engine_contract(failed.engine_contract),
    )

    assert failed.status == "FAILED"
    assert retry.job_id != failed.job_id
    assert retry.run_id != failed.run_id
    assert retry.resume_from_attempt_id == failed.attempt_id
    assert retry.engine_contract is not None
    assert retry.engine_contract.max_model_calls == 10
    assert retry.engine_contract.max_input_tokens == 10000
    assert store.get(failed.job_id).status == "FAILED"
    assert store.get(retry.job_id).status == "QUEUED"
