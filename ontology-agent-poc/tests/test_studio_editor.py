from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ontology_agent import api as api_module
from ontology_agent.api import control_app
from ontology_agent.io import sha256_value
from ontology_agent.release import StudioReleases
from ontology_agent.solution_adapters.adt_studio import ADTStudioAdapter
from ontology_agent.studio.editor import (
    DraftOperationsV1,
    EditorDescriptorError,
    load_editor_descriptor,
)
from ontology_agent.studio.workspace import DraftWorkspaceService, WorkspaceStateError


control_client = TestClient(control_app)


def _adapter(
    tmp_path: Path, scenario_dir: Path
) -> tuple[ADTStudioAdapter, DraftWorkspaceService]:
    service = DraftWorkspaceService(
        tmp_path / "studio" / "workspaces",
        scenario_dir,
        StudioReleases(tmp_path / "registry" / "releases"),
    )
    adapter = ADTStudioAdapter(
        workspace=service,
        descriptor_path=scenario_dir / "authoring" / "editor-descriptor.json",
        component_root=scenario_dir,
    )
    return adapter, service


def test_editor_descriptor_closes_the_registered_semantic_slots(
    scenario_dir: Path,
) -> None:
    descriptor = load_editor_descriptor(
        scenario_dir / "authoring" / "editor-descriptor.json",
        component_root=scenario_dir,
    )

    assert descriptor.workspace_id == "workspace.adt.reference"
    assert descriptor.operations_contract == "studio-draft-operations/v1"
    assert tuple(field.path for field in descriptor.fields) == (
        "metric_definition",
        "eligibility_rule.include_status",
        "eligibility_rule.exclude_cancelled",
        "allowed_dimensions",
        "amount_mapping",
    )


def test_editor_descriptor_rejects_changed_slot_bytes(scenario_dir: Path) -> None:
    slot_path = scenario_dir / "llm" / "studio" / "semantic-slot-manifest.json"
    slot_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(EditorDescriptorError, match="digest mismatch"):
        load_editor_descriptor(
            scenario_dir / "authoring" / "editor-descriptor.json",
            component_root=scenario_dir,
        )


def test_common_operations_are_translated_only_by_the_adt_adapter(
    scenario_dir: Path,
    tmp_path: Path,
) -> None:
    adapter, service = _adapter(tmp_path, scenario_dir)
    initial = service.get()

    updated = adapter.apply_operations(
        DraftOperationsV1(
            expected_revision=initial.revision,
            operations=(
                {
                    "path": "metric_definition",
                    "value": "Descriptor-driven reviewed ADT definition.",
                },
                {
                    "path": "eligibility_rule.exclude_cancelled",
                    "value": False,
                },
            ),
        ),
        workspace_id=initial.workspace_id,
    )

    assert updated.revision == initial.revision + 1
    assert updated.draft.metric_definition == "Descriptor-driven reviewed ADT definition."
    assert updated.draft.eligibility_rule.exclude_cancelled is False
    assert updated.validation.status == "STALE"


def test_adapter_rejects_unregistered_paths_and_values(
    scenario_dir: Path,
    tmp_path: Path,
) -> None:
    adapter, service = _adapter(tmp_path, scenario_dir)
    initial = service.get()

    with pytest.raises(WorkspaceStateError, match="path is not registered"):
        adapter.apply_operations(
            DraftOperationsV1(
                expected_revision=initial.revision,
                operations=({"path": "runtime.activation", "value": "ALLOW"},),
            ),
            workspace_id=initial.workspace_id,
        )
    with pytest.raises(WorkspaceStateError, match="unsupported value"):
        adapter.apply_operations(
            DraftOperationsV1(
                expected_revision=initial.revision,
                operations=({"path": "amount_mapping", "value": "raw_secret"},),
            ),
            workspace_id=initial.workspace_id,
        )


def test_workspace_editor_api_uses_descriptor_operations(
    monkeypatch: pytest.MonkeyPatch,
    scenario_dir: Path,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("ONTOLOGY_PRODUCT_STATE_MODE", raising=False)
    monkeypatch.setattr(api_module, "DEFAULT_SCENARIO_DIR", scenario_dir)
    monkeypatch.setattr(api_module, "DEFAULT_STUDIO_DIR", tmp_path / "studio")
    monkeypatch.setattr(api_module, "DEFAULT_PUBLISHED_DIR", tmp_path / "registry")

    opened = control_client.get(
        "/control/workspaces/workspace.adt.reference/editor"
    )
    assert opened.status_code == 200
    payload = opened.json()
    assert payload["contract"] == "studio-workspace-editor/v1"
    assert payload["persistence"] == "legacy-compatibility"
    assert len(payload["descriptor"]["fields"]) == 5

    changed = control_client.post(
        "/control/workspaces/workspace.adt.reference/draft-operations",
        json={
            "contract": "studio-draft-operations/v1",
            "expected_revision": payload["workspace"]["revision"],
            "operations": [
                {
                    "path": "metric_definition",
                    "value": "HTTP descriptor-driven ADT definition.",
                }
            ],
        },
    )
    assert changed.status_code == 200
    assert changed.json()["revision"] == payload["workspace"]["revision"] + 1
    assert changed.json()["draft"]["metric_definition"].startswith("HTTP descriptor")


def test_workspace_workbench_projects_the_exact_candidate_package(
    monkeypatch: pytest.MonkeyPatch,
    scenario_dir: Path,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("ONTOLOGY_PRODUCT_STATE_MODE", raising=False)
    monkeypatch.setattr(api_module, "DEFAULT_SCENARIO_DIR", scenario_dir)
    monkeypatch.setattr(api_module, "DEFAULT_STUDIO_DIR", tmp_path / "studio")
    monkeypatch.setattr(api_module, "DEFAULT_PUBLISHED_DIR", tmp_path / "registry")

    response = control_client.get(
        "/control/workspaces/workspace.adt.reference/workbench"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["contract"] == "studio-workbench/v1"
    assert payload["package"]["package_id"] == "ontology.exchange_analytics.adt"
    assert payload["package"]["version"] == payload["workspace"]["target_version"]
    assert len(payload["package_checksum"]) == 64
    assert len(payload["asset_checksums"]["metrics:metric.average_daily_turnover"]) == 64
    assert {item["id"] for item in payload["package"]["entities"]} >= {
        "entity.trade",
        "entity.instrument",
    }
    assert any(
        item["from_entity"] == "entity.trade"
        and item["to_entity"] == "entity.instrument"
        for item in payload["package"]["relationships"]
    )
    assert payload["package"]["bindings"]
    assert payload["package"]["joins"]
    assert payload["intake"]["assets"]
    assert len(payload["authoring"]["requirements"]) == 5
    assert len(payload["authoring"]["metric_candidates"]) == 8
    assert sum(
        item["compile_status"] == "EXECUTABLE"
        for item in payload["authoring"]["metric_candidates"]
    ) == 3
    assert len(payload["revisions"]) == 1


def test_common_package_operations_add_a_typed_link_to_the_exact_candidate(
    monkeypatch: pytest.MonkeyPatch,
    scenario_dir: Path,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("ONTOLOGY_PRODUCT_STATE_MODE", raising=False)
    monkeypatch.setattr(api_module, "DEFAULT_SCENARIO_DIR", scenario_dir)
    monkeypatch.setattr(api_module, "DEFAULT_STUDIO_DIR", tmp_path / "studio")
    monkeypatch.setattr(api_module, "DEFAULT_PUBLISHED_DIR", tmp_path / "registry")
    opened = control_client.get(
        "/control/workspaces/workspace.adt.reference/workbench"
    ).json()
    relationship = {
        "id": "relationship.trade.instrument.secondary",
        "version": "1.0.0",
        "status": "confirmed",
        "name": {"en": "Trade secondary instrument", "zh": "成交备用证券"},
        "definition": "A constructed-synthetic secondary relationship for Studio authoring tests.",
        "owner": "actor.market_analyst",
        "sources": ["source.requirements"],
        "decisions": [],
        "tags": ["studio-authored"],
        "from_entity": "entity.trade",
        "to_entity": "entity.instrument",
        "predicate": "referencesInstrument",
        "cardinality": "N:1",
    }

    changed = control_client.post(
        "/control/workspaces/workspace.adt.reference/package-operations",
        json={
            "contract": "studio-package-operations/v1",
            "expected_revision": opened["workspace"]["revision"],
            "operations": [{
                "action": "UPSERT",
                "collection": "relationships",
                "object_id": relationship["id"],
                "payload": relationship,
            }],
        },
    )
    assert changed.status_code == 200
    assert changed.json()["revision"] == opened["workspace"]["revision"] + 1
    assert changed.json()["validation"]["status"] == "STALE"

    workbench = control_client.get(
        "/control/workspaces/workspace.adt.reference/workbench"
    ).json()
    authored = next(
        item
        for item in workbench["package"]["relationships"]
        if item["id"] == relationship["id"]
    )
    assert authored["status"] == "proposed"
    assert workbench["workspace"]["package_operations"][-1]["object_id"] == (
        relationship["id"]
    )
    unreviewed = control_client.post(
        "/control/workspaces/workspace.adt.reference/validate",
        json={"expected_revision": changed.json()["revision"]},
    )
    assert unreviewed.status_code == 200
    assert unreviewed.json()["validation"]["status"] == "FAIL"

    confirmed = control_client.post(
        "/control/workspaces/workspace.adt.reference/package-operations",
        json={
            "contract": "studio-package-operations/v1",
            "expected_revision": changed.json()["revision"],
            "operations": [{
                "action": "CONFIRM",
                "collection": "relationships",
                "object_id": relationship["id"],
                "payload": {
                    "reviewer": "studio-reviewer",
                    "reviewed_at": "2026-08-21T12:00:00Z",
                    "asset_checksum": sha256_value(authored),
                },
            }],
        },
    )
    assert confirmed.status_code == 200
    validated = control_client.post(
        "/control/workspaces/workspace.adt.reference/validate",
        json={"expected_revision": confirmed.json()["revision"]},
    )
    assert validated.status_code == 200
    assert validated.json()["validation"]["status"] == "PASS"


def test_package_operations_reject_an_untyped_cardinality_without_advancing_revision(
    monkeypatch: pytest.MonkeyPatch,
    scenario_dir: Path,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("ONTOLOGY_PRODUCT_STATE_MODE", raising=False)
    monkeypatch.setattr(api_module, "DEFAULT_SCENARIO_DIR", scenario_dir)
    monkeypatch.setattr(api_module, "DEFAULT_STUDIO_DIR", tmp_path / "studio")
    monkeypatch.setattr(api_module, "DEFAULT_PUBLISHED_DIR", tmp_path / "registry")
    opened = control_client.get(
        "/control/workspaces/workspace.adt.reference/workbench"
    ).json()
    invalid = dict(opened["package"]["relationships"][0])
    invalid["cardinality"] = "1:X"

    response = control_client.post(
        "/control/workspaces/workspace.adt.reference/package-operations",
        json={
            "contract": "studio-package-operations/v1",
            "expected_revision": opened["workspace"]["revision"],
            "operations": [{
                "action": "UPSERT",
                "collection": "relationships",
                "object_id": invalid["id"],
                "payload": invalid,
            }],
        },
    )
    assert response.status_code == 422
    unchanged = control_client.get(
        "/control/workspaces/workspace.adt.reference/workbench"
    ).json()
    assert unchanged["workspace"]["revision"] == opened["workspace"]["revision"]
