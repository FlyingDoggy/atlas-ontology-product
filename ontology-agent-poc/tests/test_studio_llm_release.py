from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from ontology_agent.io import DEFAULT_SCENARIO_DIR, sha256_value
from ontology_agent.studio.llm import (
    StudioEgressDecision,
    StudioLLMError,
    StudioEvaluationManifest,
    StudioEvaluationSecurityGates,
    StudioRolloutRecord,
    load_semantic_slot_manifest,
    load_studio_run_profile,
)


def _authority():
    root = DEFAULT_SCENARIO_DIR / "llm" / "studio"
    profile = load_studio_run_profile(root / "engineering-profile.json")
    slots = load_semantic_slot_manifest(root / "semantic-slot-manifest.json")
    egress = StudioEgressDecision(
        contract="studio-model-egress-decision/v1",
        decision_id="egress.studio.adt.qwen.demo.v1",
        decision="ALLOW",
        product="ontology-studio",
        task="adt-observation-tracer",
        provider="qwen",
        provider_account_ref=profile.provider_account_ref,
        endpoint_ref=profile.endpoint_ref,
        region=profile.region,
        classification="constructed_synthetic",
        intake_submission_id="submission.reference.adt.v1",
        profile_digest=sha256_value(profile),
        slot_manifest_digest=sha256_value(slots),
        allowed_projection_contract="studio-cleared-input-projection/v1",
        approved_by="decision-owner",
        issued_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
        expires_at=datetime(2030, 8, 19, tzinfo=timezone.utc),
    )
    evaluation = StudioEvaluationManifest(
        contract="studio-evaluation-manifest/v1",
        manifest_id="eval-manifest.studio.adt.v1",
        demo_class="STUDIO_LLM_ENGINEERING_DEMO",
        profile_digest=sha256_value(profile),
        slot_manifest_digest=sha256_value(slots),
        egress_decision_digest=sha256_value(egress),
        provider="qwen",
        requested_model="qwen3.8-max",
        response_model="qwen3.8-max",
        observed_slot_ids=tuple(item.slot_id for item in slots.slots),
        observation_count=5,
        security_gates=StudioEvaluationSecurityGates(),
        raw_content_retained=False,
        evaluated_at=datetime(2026, 8, 20, 9, tzinfo=timezone.utc),
        approved_by="decision-owner",
    )
    rollout = StudioRolloutRecord(
        contract="studio-task-rollout-record/v1",
        rollout_id="rollout.studio.adt.qwen.demo.v1",
        task="adt-observation-tracer",
        mode="active-observation-canary",
        epoch=1,
        status="ACTIVE",
        profile_digest=sha256_value(profile),
        slot_manifest_digest=sha256_value(slots),
        egress_decision_digest=sha256_value(egress),
        evaluation_manifest_ref=evaluation.manifest_id,
        evaluation_manifest_digest=sha256_value(evaluation),
        approved_by="decision-owner",
        issued_at=datetime(2026, 8, 20, 10, tzinfo=timezone.utc),
        expires_at=datetime(2030, 8, 20, tzinfo=timezone.utc),
    )
    return profile, slots, egress, evaluation, rollout


def test_active_studio_rollout_closes_the_exact_evaluated_configuration() -> None:
    profile, slots, egress, evaluation, rollout = _authority()

    assert rollout.permits(
        profile=profile,
        slot_manifest=slots,
        egress=egress,
        evaluation=evaluation,
        now=datetime(2026, 8, 20, 11, tzinfo=timezone.utc),
    )
    assert not rollout.model_copy(
        update={"profile_digest": "f" * 64}
    ).permits(
        profile=profile,
        slot_manifest=slots,
        egress=egress,
        evaluation=evaluation,
        now=datetime(2026, 8, 20, 11, tzinfo=timezone.utc),
    )


def test_active_studio_rollout_cannot_exist_without_an_evaluation_manifest() -> None:
    _, _, _, _, rollout = _authority()

    with pytest.raises(ValueError, match="evaluation"):
        StudioRolloutRecord.model_validate(
            rollout.model_dump(
                exclude={"evaluation_manifest_ref", "evaluation_manifest_digest"}
            )
        )


def test_studio_evaluation_must_cover_the_frozen_five_slot_denominator() -> None:
    profile, slots, egress, evaluation, _ = _authority()

    assert evaluation.permits(
        profile=profile,
        slot_manifest=slots,
        egress=egress,
        rollout_approved_by="decision-owner",
        rollout_issued_at=datetime(2026, 8, 20, 10, tzinfo=timezone.utc),
    )
    assert not evaluation.model_copy(
        update={"observed_slot_ids": evaluation.observed_slot_ids[:-1]}
    ).permits(
        profile=profile,
        slot_manifest=slots,
        egress=egress,
        rollout_approved_by="decision-owner",
        rollout_issued_at=datetime(2026, 8, 20, 10, tzinfo=timezone.utc),
    )


def test_studio_profile_rejects_a_changed_prompt_dependency(tmp_path: Path) -> None:
    source = DEFAULT_SCENARIO_DIR / "llm" / "studio"
    for name in ("engineering-profile.json", "prompts.json", "projection-policy.json"):
        (tmp_path / name).write_bytes((source / name).read_bytes())
    prompt_path = tmp_path / "prompts.json"
    prompt = json.loads(prompt_path.read_text(encoding="utf-8"))
    prompt["prompts"][0]["text"] += " unapproved change"
    prompt_path.write_text(json.dumps(prompt), encoding="utf-8")

    with pytest.raises(StudioLLMError, match="dependency digest mismatch"):
        load_studio_run_profile(tmp_path / "engineering-profile.json")
