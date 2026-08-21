from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import sleep

from fastapi.testclient import TestClient
import ontology_agent.api as api_module
from ontology_agent.api import control_app
from ontology_agent.io import DEFAULT_SCENARIO_DIR, sha256_value
from ontology_agent.release import StudioReleases
from ontology_agent.studio.llm import (
    SemanticSlotManifest,
    StudioEgressDecision,
    StudioObservationDisposition,
    StudioRolloutRecord,
    StudioLLMError,
    StudioObservationService,
    StudioRunProfile,
    load_semantic_slot_manifest,
    load_studio_run_profile,
)
from ontology_agent.studio.workspace import (
    DraftUpdate,
    DraftWorkspaceService,
    WorkspaceConflictError,
)
import pytest


control_client = TestClient(control_app)


def _workspace(tmp_path: Path, scenario_dir: Path) -> DraftWorkspaceService:
    releases = StudioReleases(tmp_path / "registry" / "releases")
    return DraftWorkspaceService(
        tmp_path / "studio" / "workspaces",
        scenario_dir,
        releases,
    )


def _authority() -> tuple[
    StudioRunProfile,
    SemanticSlotManifest,
    StudioEgressDecision,
    StudioRolloutRecord,
    None,
]:
    root = DEFAULT_SCENARIO_DIR / "llm" / "studio"
    profile = load_studio_run_profile(root / "engineering-profile.json")
    manifest = load_semantic_slot_manifest(root / "semantic-slot-manifest.json")
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
        slot_manifest_digest=sha256_value(manifest),
        allowed_projection_contract="studio-cleared-input-projection/v1",
        approved_by="decision-owner",
        issued_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
        expires_at=datetime(2030, 8, 19, tzinfo=timezone.utc),
    )
    rollout = StudioRolloutRecord(
        contract="studio-task-rollout-record/v1",
        rollout_id="rollout.studio.adt.qwen.demo.v1",
        task="adt-observation-tracer",
        mode="shadow",
        epoch=1,
        status="ACTIVE",
        profile_digest=sha256_value(profile),
        slot_manifest_digest=sha256_value(manifest),
        egress_decision_digest=sha256_value(egress),
        approved_by="decision-owner",
        issued_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
        expires_at=datetime(2030, 8, 19, tzinfo=timezone.utc),
    )
    return profile, manifest, egress, rollout, None


def _model_boundary(request: dict[str, object], timeout: float) -> dict[str, object]:
    projection = request["projection"]
    assert isinstance(projection, dict)
    slots = projection["slots"]
    assert isinstance(slots, list)
    values = {
        "metric.definition": {
            "kind": "STRING",
            "string_value": "同期间的合资格成交额除以交易日数",
        },
        "eligibility.include_status": {
            "kind": "STRING",
            "string_value": "EXECUTED",
        },
        "eligibility.exclude_cancelled": {
            "kind": "BOOLEAN",
            "boolean_value": True,
        },
        "metric.allowed_dimensions": {
            "kind": "STRING_LIST",
            "string_list_value": ["dimension.period", "dimension.segment"],
        },
        "mapping.amount": {
            "kind": "STRING",
            "string_value": "executed_value_hkd_mn",
        },
    }
    return {
        "contract": "studio-observation-candidate-set/v1",
        "run_id": request["run_id"],
        "requested_model": "qwen3.8-max",
        "response_model": "qwen3.8-max",
        "provider_request_id": "provider-request.studio-observe",
        "observations": [
            {
                "slot_id": slot["slot_id"],
                "status": "PROPOSED",
                "support_code": "DIRECT_SOURCE",
                "source_fragment_checksum": slot["source_fragment"]["checksum"],
                "value": values[slot["slot_id"]],
            }
            for slot in slots
        ],
    }


def test_generate_observations_is_immutable_anchored_and_does_not_change_draft(
    scenario_dir: Path,
    tmp_path: Path,
) -> None:
    workspace_service = _workspace(tmp_path, scenario_dir)
    before = workspace_service.get()
    profile, manifest, egress, rollout, evaluation = _authority()

    service = StudioObservationService(
        root=tmp_path / "studio" / "llm",
        workspace=workspace_service,
        profile=profile,
        slot_manifest=manifest,
        egress=egress,
        rollout=rollout,
        evaluation=evaluation,
        model_boundary=_model_boundary,
    )

    observation_set = service.generate(expected_revision=before.revision)

    assert observation_set.base_revision == before.revision
    assert observation_set.base_draft_checksum == before.draft_checksum
    assert observation_set.intake_checksum == before.intake_checksum
    assert len(observation_set.observations) == len(manifest.slots) == 5
    assert all(item.source_anchor is not None for item in observation_set.observations)
    assert all(item.status == "PROPOSED" for item in observation_set.observations)
    assert len(observation_set.observation_set_checksum) == 64
    assert service.get(observation_set.observation_set_id) == observation_set
    assert service.list_for_workspace(before.workspace_id) == (observation_set,)
    assert workspace_service.get().revision == before.revision
    assert workspace_service.get().draft_checksum == before.draft_checksum
    assert workspace_service.get().last_published == before.last_published
    serialized = observation_set.model_dump_json().lower()
    assert "publish" not in serialized
    assert "api_key" not in serialized
    assert sha256_value(observation_set.projection) == observation_set.projection_digest


def test_generate_is_idempotent_while_the_exact_draft_has_a_pending_set(
    scenario_dir: Path,
    tmp_path: Path,
) -> None:
    workspace_service = _workspace(tmp_path, scenario_dir)
    before = workspace_service.get()
    profile, manifest, egress, rollout, evaluation = _authority()
    calls = 0

    def counted_boundary(
        request: dict[str, object], timeout: float
    ) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return _model_boundary(request, timeout)

    service = StudioObservationService(
        root=tmp_path / "studio" / "llm",
        workspace=workspace_service,
        profile=profile,
        slot_manifest=manifest,
        egress=egress,
        rollout=rollout,
        evaluation=evaluation,
        model_boundary=counted_boundary,
    )

    first = service.generate(expected_revision=before.revision)
    retry = service.generate(expected_revision=before.revision)

    assert retry == first
    assert calls == 1
    assert service.list_for_workspace() == (first,)


def test_concurrent_generate_commands_share_one_pending_set_and_one_model_call(
    scenario_dir: Path,
    tmp_path: Path,
) -> None:
    workspace_service = _workspace(tmp_path, scenario_dir)
    before = workspace_service.get()
    profile, manifest, egress, rollout, evaluation = _authority()
    calls = 0
    calls_lock = Lock()

    def slow_boundary(
        request: dict[str, object], timeout: float
    ) -> dict[str, object]:
        nonlocal calls
        with calls_lock:
            calls += 1
        sleep(0.05)
        return _model_boundary(request, timeout)

    def service() -> StudioObservationService:
        return StudioObservationService(
            root=tmp_path / "studio" / "llm",
            workspace=workspace_service,
            profile=profile,
            slot_manifest=manifest,
            egress=egress,
            rollout=rollout,
            evaluation=evaluation,
            model_boundary=slow_boundary,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(
            executor.map(
                lambda item: item.generate(expected_revision=before.revision),
                (service(), service()),
            )
        )

    assert results[0] == results[1]
    assert calls == 1
    assert service().list_for_workspace() == (results[0],)


def test_human_review_is_the_only_step_that_can_change_the_draft(
    scenario_dir: Path,
    tmp_path: Path,
) -> None:
    workspace_service = _workspace(tmp_path, scenario_dir)
    before = workspace_service.get()
    profile, manifest, egress, rollout, evaluation = _authority()
    service = StudioObservationService(
        root=tmp_path / "studio" / "llm",
        workspace=workspace_service,
        profile=profile,
        slot_manifest=manifest,
        egress=egress,
        rollout=rollout,
        evaluation=evaluation,
        model_boundary=_model_boundary,
    )
    observation_set = service.generate(expected_revision=before.revision)
    revised_definition = "经人工确认：同期间合资格成交额除以交易日数。"
    dispositions = tuple(
        StudioObservationDisposition(
            observation_id=item.observation_id,
            action="EDIT" if item.slot_id == "metric.definition" else "ACCEPT",
            reason_code=(
                "REVIEWER_CORRECTION"
                if item.slot_id == "metric.definition"
                else "SOURCE_SUPPORTED"
            ),
            edited_value=(
                {
                    "kind": "STRING",
                    "string_value": revised_definition,
                }
                if item.slot_id == "metric.definition"
                else None
            ),
        )
        for item in observation_set.observations
    )

    result = service.review(
        observation_set.observation_set_id,
        expected_revision=before.revision,
        reviewer="market-data-steward.demo",
        dispositions=dispositions,
    )

    assert result.decision.status == "APPLIED"
    assert result.decision.reviewer == "market-data-steward.demo"
    assert result.workspace.revision == before.revision + 1
    assert result.workspace.draft.metric_definition == revised_definition
    assert result.workspace.validation.status == "STALE"
    assert result.workspace.last_published == before.last_published
    assert service.get_decision(observation_set.observation_set_id) == result.decision
    assert "publish" not in result.decision.model_dump_json().lower()


def test_rejecting_every_observation_records_a_decision_without_mutating_draft(
    scenario_dir: Path,
    tmp_path: Path,
) -> None:
    workspace_service = _workspace(tmp_path, scenario_dir)
    before = workspace_service.get()
    profile, manifest, egress, rollout, evaluation = _authority()
    service = StudioObservationService(
        root=tmp_path / "studio" / "llm",
        workspace=workspace_service,
        profile=profile,
        slot_manifest=manifest,
        egress=egress,
        rollout=rollout,
        evaluation=evaluation,
        model_boundary=_model_boundary,
    )
    observation_set = service.generate(expected_revision=before.revision)
    dispositions = tuple(
        StudioObservationDisposition(
            observation_id=item.observation_id,
            action="REJECT",
            reason_code="NOT_SUPPORTED",
        )
        for item in observation_set.observations
    )

    result = service.review(
        observation_set.observation_set_id,
        expected_revision=before.revision,
        reviewer="market-data-steward.demo",
        dispositions=dispositions,
    )

    assert result.decision.status == "REVIEWED_NO_CHANGE"
    assert result.workspace.revision == before.revision
    assert result.workspace.draft_checksum == before.draft_checksum
    assert workspace_service.list_revisions()[0].revision == before.revision


def test_stale_observation_set_cannot_overwrite_a_newer_human_draft(
    scenario_dir: Path,
    tmp_path: Path,
) -> None:
    workspace_service = _workspace(tmp_path, scenario_dir)
    before = workspace_service.get()
    profile, manifest, egress, rollout, evaluation = _authority()
    service = StudioObservationService(
        root=tmp_path / "studio" / "llm",
        workspace=workspace_service,
        profile=profile,
        slot_manifest=manifest,
        egress=egress,
        rollout=rollout,
        evaluation=evaluation,
        model_boundary=_model_boundary,
    )
    observation_set = service.generate(expected_revision=before.revision)
    newer = workspace_service.patch(
        DraftUpdate(metric_definition="Newer human-authored definition."),
        expected_revision=before.revision,
    )
    dispositions = tuple(
        StudioObservationDisposition(
            observation_id=item.observation_id,
            action="ACCEPT",
            reason_code="SOURCE_SUPPORTED",
        )
        for item in observation_set.observations
    )

    with pytest.raises(WorkspaceConflictError, match="stale"):
        service.review(
            observation_set.observation_set_id,
            expected_revision=before.revision,
            reviewer="market-data-steward.demo",
            dispositions=dispositions,
        )

    current = workspace_service.get()
    assert current.revision == newer.revision
    assert current.draft.metric_definition == "Newer human-authored definition."


def test_model_cannot_move_a_value_to_an_unrelated_source_anchor(
    scenario_dir: Path,
    tmp_path: Path,
) -> None:
    workspace_service = _workspace(tmp_path, scenario_dir)
    before = workspace_service.get()
    profile, manifest, egress, rollout, evaluation = _authority()

    def swapped_anchor(
        request: dict[str, object], timeout: float
    ) -> dict[str, object]:
        payload = _model_boundary(request, timeout)
        observations = payload["observations"]
        assert isinstance(observations, list)
        observations[0]["source_fragment_checksum"] = "f" * 64
        return payload

    service = StudioObservationService(
        root=tmp_path / "studio" / "llm",
        workspace=workspace_service,
        profile=profile,
        slot_manifest=manifest,
        egress=egress,
        rollout=rollout,
        evaluation=evaluation,
        model_boundary=swapped_anchor,
    )

    with pytest.raises(StudioLLMError, match="source fragment checksum"):
        service.generate(expected_revision=before.revision)

    assert workspace_service.get().revision == before.revision
    assert service.list_for_workspace() == ()


def test_changed_cleared_input_bytes_block_before_any_model_call(
    scenario_dir: Path,
    tmp_path: Path,
) -> None:
    workspace_service = _workspace(tmp_path, scenario_dir)
    before = workspace_service.get()
    profile, manifest, egress, rollout, evaluation = _authority()
    calls = 0

    def counted_boundary(
        request: dict[str, object], timeout: float
    ) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return _model_boundary(request, timeout)

    service = StudioObservationService(
        root=tmp_path / "studio" / "llm",
        workspace=workspace_service,
        profile=profile,
        slot_manifest=manifest,
        egress=egress,
        rollout=rollout,
        evaluation=evaluation,
        model_boundary=counted_boundary,
    )
    metric_logic = scenario_dir / "input" / "metric_logic.md"
    metric_logic.write_text(
        metric_logic.read_text(encoding="utf-8") + "\nunauthorized mutation\n",
        encoding="utf-8",
    )

    with pytest.raises(StudioLLMError, match="Cleared input projection"):
        service.generate(expected_revision=before.revision)

    assert calls == 0


def test_control_api_exposes_generate_review_and_no_llm_publish_route(
    monkeypatch: pytest.MonkeyPatch,
    scenario_dir: Path,
    tmp_path: Path,
) -> None:
    workspace_service = _workspace(tmp_path, scenario_dir)
    before = workspace_service.get()
    profile, manifest, egress, rollout, evaluation = _authority()
    service = StudioObservationService(
        root=tmp_path / "studio" / "llm",
        workspace=workspace_service,
        profile=profile,
        slot_manifest=manifest,
        egress=egress,
        rollout=rollout,
        evaluation=evaluation,
        model_boundary=_model_boundary,
    )
    monkeypatch.setenv("ONTOLOGY_STUDIO_LLM_MODE", "active-observation-canary")
    monkeypatch.setattr(api_module, "_studio_observations", lambda: service)

    generated = control_client.post(
        "/control/workspaces/workspace.adt.reference/llm/observations",
        json={"expected_revision": before.revision},
    )

    assert generated.status_code == 200
    observation_set = generated.json()
    assert observation_set["base_revision"] == before.revision
    assert workspace_service.get().revision == before.revision
    dispositions = [
        {
            "observation_id": item["observation_id"],
            "action": "EDIT" if item["slot_id"] == "metric.definition" else "ACCEPT",
            "reason_code": (
                "REVIEWER_CORRECTION"
                if item["slot_id"] == "metric.definition"
                else "SOURCE_SUPPORTED"
            ),
            "edited_value": (
                {
                    "kind": "STRING",
                    "string_value": "Human-reviewed API definition.",
                }
                if item["slot_id"] == "metric.definition"
                else None
            ),
        }
        for item in observation_set["observations"]
    ]
    reviewed = control_client.post(
        "/control/workspaces/workspace.adt.reference/llm/observations/"
        + observation_set["observation_set_id"]
        + "/review",
        json={
            "expected_revision": before.revision,
            "dispositions": dispositions,
        },
    )

    assert reviewed.status_code == 200
    assert reviewed.json()["decision"]["reviewer"] == "market-data-steward.demo"
    assert reviewed.json()["workspace"]["revision"] == before.revision + 1
    assert reviewed.json()["workspace"]["last_published"] is None
    listed = control_client.get(
        "/control/workspaces/workspace.adt.reference/llm/observations"
    )
    assert listed.status_code == 200
    assert listed.json()["observation_sets"][0]["observation_set"][
        "observation_set_id"
    ] == observation_set["observation_set_id"]
    assert listed.json()["observation_sets"][0]["decision"]["status"] == "APPLIED"
    assert control_client.post(
        "/control/workspaces/workspace.adt.reference/llm/publish",
        json={},
    ).status_code == 404
