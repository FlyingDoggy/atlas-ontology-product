from __future__ import annotations

from datetime import datetime, timezone

from ontology_agent.io import DEFAULT_SCENARIO_DIR, sha256_value
from ontology_agent.llm_contracts import (
    DEMO_CLASS,
    EngineeringEvaluationManifest,
    EvaluationCaseResult,
    EvaluationSecurityGates,
    ModelEgressDecision,
    load_question_family,
    load_run_profile,
)


def _authority() -> tuple:
    family = load_question_family(DEFAULT_SCENARIO_DIR / "llm" / "question-family.json")
    profile = load_run_profile(DEFAULT_SCENARIO_DIR / "llm" / "engineering-profile.json")
    egress = ModelEgressDecision(
        contract="model-egress-decision/v1",
        decision_id="egress.adt.qwen.demo.v1",
        decision="ALLOW",
        product="ontology-analytic-agent",
        task="adt-engineering-demo",
        provider="qwen",
        provider_account_ref=profile.provider_account_ref,
        endpoint_ref=profile.endpoint_ref,
        region=profile.region,
        classification="constructed_synthetic",
        question_family_id=family.family_id,
        question_family_checksum=sha256_value(family),
        allowed_projection_contracts=(
            "model-question-projection/v1",
            "model-evidence-projection/v1",
        ),
        retention_profile="provider-default-demo",
        approved_by="decision-owner",
        issued_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
        expires_at=datetime(2030, 8, 19, tzinfo=timezone.utc),
    )
    return family, profile, egress


def _manifest() -> tuple:
    family, profile, egress = _authority()
    cases = tuple(
        EvaluationCaseResult(
            case_id=case.case_id,
            outcome="ANSWERED",
            committed=True,
            response_model="qwen3.8-max",
            provider_call_count=2,
            tool_sequence=case.required_tools,
            commit_digest=str(index + 1) * 64,
            latency_ms=1200 + index,
        )
        for index, case in enumerate(family.cases)
    )
    manifest = EngineeringEvaluationManifest(
        contract="engineering-evaluation-manifest/v1",
        manifest_id="eval-manifest.adt.llm.v1",
        demo_class=DEMO_CLASS,
        profile_digest=sha256_value(profile),
        question_family_checksum=sha256_value(family),
        egress_decision_digest=sha256_value(egress),
        provider="qwen",
        requested_model="qwen3.8-max",
        response_model="qwen3.8-max",
        case_results=cases,
        security_gates=EvaluationSecurityGates(),
        raw_content_retained=False,
        evaluated_at=datetime(2026, 8, 19, 10, tzinfo=timezone.utc),
        approved_by="decision-owner",
    )
    return family, profile, egress, manifest


def test_evaluation_manifest_closes_every_registered_case_and_security_gate() -> None:
    family, profile, egress, manifest = _manifest()

    assert manifest.permits(
        family=family,
        profile=profile,
        egress=egress,
        rollout_approved_by="decision-owner",
        rollout_issued_at=datetime(2026, 8, 19, 11, tzinfo=timezone.utc),
    )


def test_evaluation_manifest_rejects_missing_case_or_wrong_tool_sequence() -> None:
    family, profile, egress, manifest = _manifest()
    missing = manifest.model_copy(update={"case_results": manifest.case_results[:-1]})
    wrong_case = manifest.case_results[1].model_copy(
        update={"tool_sequence": ("compare_periods",)}
    )
    wrong = manifest.model_copy(
        update={
            "case_results": (
                manifest.case_results[0],
                wrong_case,
                *manifest.case_results[2:],
            )
        }
    )

    for candidate in (missing, wrong):
        assert not candidate.permits(
            family=family,
            profile=profile,
            egress=egress,
            rollout_approved_by="decision-owner",
            rollout_issued_at=datetime(2026, 8, 19, 11, tzinfo=timezone.utc),
        )
