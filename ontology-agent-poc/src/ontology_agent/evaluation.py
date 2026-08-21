from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from .contracts import VerifiedSnapshot
from .runtime import analyze_snapshot


def _close(actual: Any, expected: Any, tolerance: Decimal) -> bool:
    try:
        return abs(Decimal(str(actual)) - Decimal(str(expected))) <= tolerance
    except Exception:
        return actual == expected


def _oracle_defects(response_facts: dict[str, Any], oracle: dict[str, Any]) -> dict[str, Any]:
    tolerance = Decimal(str(oracle.get("tolerances", {}).get("absolute", "0.000001")))
    defects: dict[str, Any] = {}
    actual_periods = response_facts.get("periods", {})
    for period_id, expected in oracle["periods"].items():
        actual = actual_periods.get(period_id, {})
        for field in (
            "eligible_turnover_hkd_mn",
            "trading_day_count",
            "adt_hkd_mn_per_trading_day",
        ):
            if not _close(actual.get(field), expected[field], tolerance):
                defects[f"periods/{period_id}/{field}"] = {
                    "actual": actual.get(field),
                    "expected": expected[field],
                }
        actual_segments = {
            segment["segment_id"]: segment["current_turnover_hkd_mn"]
            if period_id == response_facts["comparison"]["current_period"]
            else segment["previous_turnover_hkd_mn"]
            for segment in response_facts.get("drivers", {}).get("segments", [])
        }
        for segment_id, expected_value in expected["segments"].items():
            if not _close(actual_segments.get(segment_id), expected_value, tolerance):
                defects[f"periods/{period_id}/segments/{segment_id}"] = {
                    "actual": actual_segments.get(segment_id),
                    "expected": expected_value,
                }

    comparison = response_facts.get("comparison", {})
    drivers = response_facts.get("drivers", {})
    leading = drivers.get("leading_segment", {})
    decomposition = drivers.get("decomposition", {})
    actual_comparison = {
        **comparison,
        "largest_decline_segment": leading.get("segment_id"),
        "largest_decline_delta_hkd_mn": leading.get("delta_hkd_mn"),
        "largest_decline_contribution_pct": leading.get("net_change_contribution_pct"),
        "calendar_effect_hkd_mn": decomposition.get("calendar_effect_hkd_mn"),
        "activity_effect_hkd_mn": decomposition.get("activity_effect_hkd_mn"),
        "decomposition_residual_hkd_mn": decomposition.get("residual_hkd_mn"),
    }
    for field, expected in oracle["comparison"].items():
        if not _close(actual_comparison.get(field), expected, tolerance):
            defects[f"comparison/{field}"] = {
                "actual": actual_comparison.get(field),
                "expected": expected,
            }
    return defects


def run_golden_suite(
    snapshot: VerifiedSnapshot,
    *,
    execution_dir: Path,
) -> dict[str, Any]:
    questions_path = snapshot.scenario_dir / "golden" / "questions.yaml"
    oracle_path = snapshot.scenario_dir / "golden" / "oracle.json"
    questions = yaml.safe_load(questions_path.read_text(encoding="utf-8"))["questions"]
    oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
    cases: list[dict[str, Any]] = []
    driver_facts: dict[str, Any] | None = None
    for case in questions:
        response = analyze_snapshot(
            snapshot,
            question=case["question"],
            role=case["role"],
            execution_dir=execution_dir,
        )
        defects: list[str] = []
        if response.status != case["expected_status"]:
            defects.append(
                f"status {response.status!r} != {case['expected_status']!r}"
            )
        expected_intent = case.get("expected_intent")
        actual_intent = response.plan.intent if response.plan else None
        if expected_intent and actual_intent != expected_intent:
            defects.append(f"intent {actual_intent!r} != {expected_intent!r}")
        expected_boundary = case.get("expected_boundary_code")
        if expected_boundary and response.boundary_code != expected_boundary:
            defects.append(
                f"boundary {response.boundary_code!r} != {expected_boundary!r}"
            )
        if response.status == "ANSWERED" and not response.evidence:
            defects.append("answered response has no claims")
        if actual_intent == "turnover_driver" and response.status == "ANSWERED":
            driver_facts = response.facts
        cases.append(
            {
                "id": case["id"],
                "status": "PASS" if not defects else "FAIL",
                "defects": defects,
                "execution_id": response.execution_id,
            }
        )

    oracle_defects = (
        {"driver": "No answered turnover-driver case was produced"}
        if driver_facts is None
        else _oracle_defects(driver_facts, oracle)
    )
    passed = all(case["status"] == "PASS" for case in cases) and not oracle_defects
    return {
        "status": "PASS" if passed else "FAIL",
        "case_count": len(cases),
        "cases": cases,
        "oracle": "constructed synthetic control oracle",
        "oracle_defects": oracle_defects,
    }
