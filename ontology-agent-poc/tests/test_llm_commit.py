from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from ontology_agent.llm_commit import EngineeringCommitConflict, EngineeringDemoCommitStore
from ontology_agent.llm_contracts import (
    EngineeringDemoResponse,
    EngineeringDemoResult,
    SafeComparisonResult,
    SafePeriodResult,
    TaskRolloutRecord,
)


def _rollout() -> TaskRolloutRecord:
    return TaskRolloutRecord(
        contract="task-rollout-record/v1",
        rollout_id="rollout.adt.qwen.demo.v1",
        task="adt-engineering-demo",
        mode="shadow",
        epoch=1,
        status="ACTIVE",
        profile_digest="1" * 64,
        question_family_checksum="2" * 64,
        egress_decision_digest="3" * 64,
        evaluation_manifest_ref=None,
        evaluation_manifest_checksum=None,
        label_digest="4" * 64,
        auto_off_triggers=(
            "PROFILE_MISMATCH",
            "MODEL_IDENTITY_MISMATCH",
            "SCHEMA_FAILURE",
            "LEAK_DETECTED",
            "DEADLINE_EXCEEDED",
        ),
        approved_by="decision-owner",
        issued_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
        expires_at=datetime(2030, 8, 19, tzinfo=timezone.utc),
    )


def _candidate() -> EngineeringDemoResponse:
    previous = SafePeriodResult(
        period_id="2025-Q3",
        adt_hkd_mn_per_trading_day=Decimal("127109.91"),
        eligible_turnover_hkd_mn=Decimal("8210000"),
        trading_day_count=65,
    )
    current = SafePeriodResult(
        period_id="2025-Q4",
        adt_hkd_mn_per_trading_day=Decimal("107766.39"),
        eligible_turnover_hkd_mn=Decimal("6573700"),
        trading_day_count=61,
    )
    return EngineeringDemoResponse(
        outcome="ANSWERED",
        answer="Q4 ADT decreased versus Q3.",
        run_id="run." + "a" * 32,
        snapshot_checksum="5" * 64,
        model_called=True,
        provider_call_count=1,
        tool_call_count=1,
        fallback_used=False,
        committed=False,
        profile_digest="1" * 64,
        result=EngineeringDemoResult(
            comparison=SafeComparisonResult(
                previous=previous,
                current=current,
                adt_direction="decrease",
                adt_delta_hkd_mn_per_trading_day=Decimal("-19343.52"),
                adt_delta_pct=Decimal("-15.22"),
            ),
            clause_ids=("clause.adt.compare", "clause.adt.synthetic-limitation"),
        ),
    )


def test_atomic_commit_returns_only_the_exact_committed_response(tmp_path: Path) -> None:
    store = EngineeringDemoCommitStore(tmp_path / "llm-demo.sqlite3")
    rollout = _rollout()
    store.install_rollout(rollout)
    capability = store.begin_run(
        rollout=rollout,
        run_id="run." + "a" * 32,
        snapshot_checksum="5" * 64,
        question_case_id="adt.compare.en.v1",
        principal="demo.shared-account",
        purpose="constructed-synthetic-adt-analysis",
    )

    receipt = store.commit(capability, _candidate())
    committed = store.read_response(capability.run_id)

    assert receipt.outcome == "ANSWERED"
    assert committed.committed is True
    assert committed.commit_digest == receipt.commit_digest
    assert committed.answer == "Q4 ADT decreased versus Q3."
    assert committed.result is not None
    assert committed.result.comparison.current.period_id == "2025-Q4"
    assert store.commit_count(capability.run_id) == 1


def test_rollout_off_invalidates_an_in_flight_private_candidate(tmp_path: Path) -> None:
    store = EngineeringDemoCommitStore(tmp_path / "llm-demo.sqlite3")
    rollout = _rollout()
    store.install_rollout(rollout)
    capability = store.begin_run(
        rollout=rollout,
        run_id="run." + "a" * 32,
        snapshot_checksum="5" * 64,
        question_case_id="adt.compare.en.v1",
        principal="demo.shared-account",
        purpose="constructed-synthetic-adt-analysis",
    )
    store.install_rollout(rollout.model_copy(update={"epoch": 2, "status": "OFF"}))

    with pytest.raises(EngineeringCommitConflict):
        store.commit(capability, _candidate())

    assert store.commit_count(capability.run_id) == 0
    with pytest.raises(KeyError):
        store.read_response(capability.run_id)


def test_automatic_off_latch_blocks_the_exact_rollout_until_a_new_epoch(
    tmp_path: Path,
) -> None:
    store = EngineeringDemoCommitStore(tmp_path / "llm-demo.sqlite3")
    rollout = _rollout()
    store.install_rollout(rollout)
    capability = store.begin_run(
        rollout=rollout,
        run_id="run." + "b" * 32,
        snapshot_checksum="5" * 64,
        question_case_id="adt.compare.en.v1",
        principal="demo.shared-account",
        purpose="constructed-synthetic-adt-analysis",
    )

    latch = store.trip_automatic_off(rollout, "MODEL_IDENTITY_MISMATCH")

    assert latch.trigger == "MODEL_IDENTITY_MISMATCH"
    assert latch.rollout_id == rollout.rollout_id
    assert latch.rollout_epoch == rollout.epoch
    assert store.automatic_off_latch(rollout) == latch
    with pytest.raises(EngineeringCommitConflict, match="automatically off"):
        store.commit(
            capability,
            _candidate().model_copy(update={"run_id": capability.run_id}),
        )
    with pytest.raises(EngineeringCommitConflict, match="automatically off"):
        store.begin_run(
            rollout=rollout,
            run_id="run." + "c" * 32,
            snapshot_checksum="5" * 64,
            question_case_id="adt.compare.en.v1",
            principal="demo.shared-account",
            purpose="constructed-synthetic-adt-analysis",
        )

    recovered = rollout.model_copy(update={"epoch": 2})
    store.install_rollout(recovered)
    assert store.automatic_off_latch(recovered) is None
    next_capability = store.begin_run(
        rollout=recovered,
        run_id="run." + "d" * 32,
        snapshot_checksum="5" * 64,
        question_case_id="adt.compare.en.v1",
        principal="demo.shared-account",
        purpose="constructed-synthetic-adt-analysis",
    )
    assert next_capability.rollout_epoch == 2
