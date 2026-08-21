from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

import ontology_agent.runtime as runtime_module
from ontology_agent.evaluation import run_golden_suite
from ontology_agent.models import OntologyPackage
from ontology_agent.publisher import VerifiedSnapshot
from ontology_agent.runtime import analyze_snapshot
from ontology_agent.scenario import BoundAnalysisGoal


def test_single_runner_executes_every_golden_case_and_complete_oracle(
    snapshot: VerifiedSnapshot, tmp_path: Path
) -> None:
    report = run_golden_suite(snapshot, execution_dir=tmp_path / "executions")
    assert report["status"] == "PASS"
    assert report["case_count"] == 8
    assert report["oracle"] == "constructed synthetic control oracle"
    assert report["oracle_defects"] == {}
    assert all(case["status"] == "PASS" for case in report["cases"])


def test_driver_analysis_is_decimal_claim_first_and_fully_linked(
    snapshot: VerifiedSnapshot, tmp_path: Path
) -> None:
    response = analyze_snapshot(
        snapshot,
        question="2025年第四季度总成交额为什么较第三季度下降，哪个板块贡献最大？",
        role="MarketAnalyst",
        execution_dir=tmp_path / "executions",
    )
    assert response.status == "ANSWERED"
    assert response.plan is not None and response.plan.intent == "turnover_driver"
    assert response.facts["periods"]["2025-Q3"]["eligible_turnover_hkd_mn"] == Decimal(
        "8210000.000000"
    )
    assert response.facts["periods"]["2025-Q4"]["trading_day_count"] == 61
    assert response.facts["comparison"]["adt_delta_pct"] == pytest.approx(
        Decimal("-15.213354365927198")
    )
    assert response.facts["drivers"]["leading_segment"]["segment_id"] == "MB"
    assert response.facts["drivers"]["leading_segment"]["rank"] == 1
    assert response.facts["drivers"]["decomposition"]["residual_hkd_mn"] == 0
    assert "顺序相关" in response.answer and "非因果" in response.answer

    assert len(response.evidence) >= 20
    for record in response.evidence:
        assert record.execution_id == response.execution_id
        assert record.snapshot_checksum == snapshot.snapshot_checksum
        assert record.plan_hash == response.plan.plan_hash
        assert record.dataset_checksum == snapshot.dataset_checksum
        assert record.policy_id and record.policy_decision_id
        assert record.query_or_operator_hashes
        assert len(record.metric_ids) == len(record.metric_versions)
        assert record.mapping_ids and record.source_ids
        assert record.step_ids
    claim_types = {record.claim_type for record in response.evidence}
    assert {"numeric", "direction", "ranking", "limitation"}.issubset(claim_types)
    exposed_keys = {key for step in response.steps for row in step.rows for key in row}
    assert "trade_id" not in exposed_keys
    assert "instrument_id" not in exposed_keys


def test_plan_contract_carries_scope_policy_and_snapshot(
    snapshot: VerifiedSnapshot, tmp_path: Path
) -> None:
    response = analyze_snapshot(
        snapshot,
        question="Compare Q4 ADT with Q3 in 2025.",
        role="MarketAnalyst",
        execution_dir=tmp_path / "executions",
    )
    assert response.status == "ANSWERED" and response.plan is not None
    for step in response.plan.steps:
        contract = step.contract
        assert contract.snapshot_checksum == snapshot.snapshot_checksum
        assert contract.market_id == "SYNTH-CASH"
        assert contract.population_id.endswith(":SYNTH-CASH")
        assert contract.policy_id == "policy.aggregate_market_access"
        assert contract.policy_decision_id.startswith("policy-decision.")
        assert contract.result_grain == ("market-period",)
        assert contract.source_ids or step.operation in {"ExactPeriodCompare"}
        assert [period.id for period in contract.period_bounds] == ["2025-Q3", "2025-Q4"]


def test_registered_model_goal_drives_the_bounded_plan_without_keyword_routing(
    snapshot: VerifiedSnapshot, tmp_path: Path
) -> None:
    response = analyze_snapshot(
        snapshot,
        question="How did the daily market activity measure move between the two configured quarters?",
        role="MarketAnalyst",
        bound_goal=BoundAnalysisGoal(
            intent="period_compare",
            tool_ids=("compare_periods",),
            language="en",
        ),
        execution_dir=tmp_path / "executions",
    )

    assert response.status == "ANSWERED"
    assert response.plan is not None and response.plan.intent == "period_compare"
    assert response.plan.question.startswith("How did the daily market activity")
    assert set(response.facts["periods"]) == {"2025-Q3", "2025-Q4"}


def test_registered_model_goal_cannot_bypass_snapshot_role_policy(
    snapshot: VerifiedSnapshot, tmp_path: Path
) -> None:
    response = analyze_snapshot(
        snapshot,
        question="How did the daily market activity measure move between the two configured quarters?",
        role="ExternalUser",
        bound_goal=BoundAnalysisGoal(
            intent="period_compare",
            tool_ids=("compare_periods",),
            language="en",
        ),
        execution_dir=tmp_path / "executions",
    )

    assert response.status == "REFUSED"
    assert response.boundary_code == "ROLE_DENIED"
    assert response.plan is None


def test_registered_decomposition_goal_has_its_own_closed_answer_and_evidence(
    snapshot: VerifiedSnapshot, tmp_path: Path
) -> None:
    response = analyze_snapshot(
        snapshot,
        question="Break the net change into the trading-calendar effect and the change in daily activity.",
        role="MarketAnalyst",
        bound_goal=BoundAnalysisGoal(
            intent="sequential_decomposition",
            tool_ids=("compare_periods", "decompose_change"),
            language="en",
        ),
        execution_dir=tmp_path / "executions",
    )

    assert response.status == "ANSWERED"
    assert response.plan is not None and response.plan.intent == "sequential_decomposition"
    assert response.facts["decomposition"]["residual_hkd_mn"] == 0
    assert "order-dependent" in response.answer and "non-causal" in response.answer
    assert {record.claim_id for record in response.evidence} >= {
        "claim.decomposition.calendar_effect_hkd_mn",
        "claim.decomposition.activity_effect_hkd_mn",
        "claim.decomposition.order_dependent",
        "claim.decomposition.non_causal",
    }


@pytest.mark.parametrize(
    ("question", "role", "status", "code"),
    [
        ("What was ADT?", "MarketAnalyst", "CLARIFY", "MISSING_PERIOD"),
        ("Predict next quarter ADT.", "MarketAnalyst", "REFUSED", "UNSUPPORTED_PREDICTION"),
        ("List every trade ID for Q4 ADT.", "MarketAnalyst", "REFUSED", "RAW_DETAIL_DENIED"),
        ("Compare Q4 ADT with Q3.", "ExternalUser", "REFUSED", "ROLE_DENIED"),
        ("Tell me a joke.", "MarketAnalyst", "REFUSED", "UNSUPPORTED_INTENT"),
    ],
)
def test_boundaries_stop_before_duckdb(
    snapshot: VerifiedSnapshot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    question: str,
    role: str,
    status: str,
    code: str,
) -> None:
    class ForbiddenDuckDB:
        def __init__(self, *_: object, **__: object) -> None:
            raise AssertionError("DuckDB must not be opened for a boundary result")

    monkeypatch.setattr(runtime_module, "DuckDBContext", ForbiddenDuckDB)
    response = analyze_snapshot(
        snapshot,
        question=question,
        role=role,
        execution_dir=tmp_path / "executions",
    )
    assert response.status == status
    assert response.boundary_code == code
    assert response.plan is None and response.steps == ()


def test_same_question_produces_same_plan_but_distinct_execution(
    snapshot: VerifiedSnapshot, tmp_path: Path
) -> None:
    kwargs = {
        "question": "Compare Q4 ADT with Q3 in 2025.",
        "role": "MarketAnalyst",
        "execution_dir": tmp_path / "executions",
    }
    first = analyze_snapshot(snapshot, **kwargs)
    second = analyze_snapshot(snapshot, **kwargs)
    assert first.status == second.status == "ANSWERED"
    assert first.plan is not None and second.plan is not None
    assert first.plan.plan_hash == second.plan.plan_hash
    assert first.execution_id != second.execution_id


def test_snapshot_handle_cannot_mix_package_and_manifest(
    snapshot: VerifiedSnapshot, package: OntologyPackage, tmp_path: Path
) -> None:
    changed = package.model_copy(update={"version": "9.9.9"})
    mixed = replace(snapshot, package=changed)
    response = analyze_snapshot(
        mixed,
        question="Compare Q4 ADT with Q3 in 2025.",
        role="MarketAnalyst",
        execution_dir=tmp_path / "executions",
    )
    assert response.status == "FAILED"
    assert response.boundary_code == "SNAPSHOT_VERIFICATION_FAILED"
    assert response.plan is None
