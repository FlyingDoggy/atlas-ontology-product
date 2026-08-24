from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from ontology_agent import api as api_module
from ontology_agent.api import control_app
from ontology_agent.release import StudioReleases
from ontology_agent.solution_adapters.cash_trading_studio import (
    CashTradingStudioAdapter,
)
from ontology_agent.studio.cash_workspace import (
    CashTradingDraftWorkspaceService,
)
from ontology_agent.studio.editor import DraftOperationsV1, load_editor_descriptor
from ontology_agent.studio.solutions import (
    load_solution_registration,
    verify_solution_components,
)
from ontology_agent.studio.workspace_store import WorkspaceIdentity


PROJECT_ROOT = Path(__file__).parents[1]
SCENARIO = PROJECT_ROOT / "scenarios" / "cash_trading"
control_client = TestClient(control_app)


def _adapter(tmp_path: Path):
    service = CashTradingDraftWorkspaceService(
        tmp_path / "studio" / "workspaces",
        SCENARIO,
        StudioReleases(tmp_path / "releases"),
    )
    return (
        CashTradingStudioAdapter(
            workspace=service,
            descriptor_path=SCENARIO / "authoring" / "editor-descriptor.json",
            component_root=SCENARIO,
        ),
        service,
    )


def test_cash_solution_registration_and_editor_close_the_package() -> None:
    registration = load_solution_registration(SCENARIO / "solution-registration.json")
    verify_solution_components(registration, SCENARIO)
    descriptor = load_editor_descriptor(
        SCENARIO / "authoring" / "editor-descriptor.json",
        component_root=SCENARIO,
    )

    assert registration.solution_id == "ontology.exchange_analytics.cash_trading"
    assert registration.workspace_id == "workspace.cash_trading.reference"
    assert len(registration.resources) == 36
    assert registration.solution_version == "1.2.2"
    assert registration.semantic_source_version == "0.2.1"
    assert tuple(field.path for field in descriptor.fields) == (
        "self_trade_definition",
        "self_trade_identity_level",
        "exclude_corrections",
        "latency_percentile_method",
        "allowed_dimensions",
    )


def test_cash_workspace_exposes_intake_assumptions_and_confirmations(
    tmp_path: Path,
) -> None:
    _, service = _adapter(tmp_path)
    workspace = service.get()
    intake = service.get_intake()

    assert workspace.revision == 1
    assert workspace.target_version == "0.2.2"
    assert workspace.validation.status == "NOT_RUN"
    assert workspace.draft.exclude_corrections is True
    assert intake.classification == "constructed_synthetic"
    assert intake.source_file_count == 4
    assert intake.assumption_count == 20
    assert intake.confirmation_count == 14
    assert intake.response_required_count == 12
    assert intake.reference_source_pack["physical_file_count"] == 4
    assert intake.construction_profile["authority"] == "PRODUCT_OWNED_COMPILER_PROFILE"
    assert intake.reviewed_baseline["semantic_version"] == "0.2.1"
    assert intake.reviewed_baseline["review_status"] == (
        "INTERNAL_REVIEWED_WITH_PROVISIONAL_ASSUMPTIONS"
    )
    assert len(intake.reviewed_baseline["metric_set"]) == 8


def test_cash_workspace_rebases_an_existing_draft_when_the_reviewed_package_advances(
    tmp_path: Path,
) -> None:
    _, service = _adapter(tmp_path)
    initial = service.get()
    stale = initial.model_copy(
        update={
            "base_version": "0.1.0",
            "target_version": "0.1.1",
            "revision": initial.revision + 1,
            "draft": initial.draft.model_copy(
                update={
                    "self_trade_definition": (
                        "Preserved reviewer wording for synthetic triage only."
                    )
                }
            ),
        }
    )
    service._write(stale)

    rebased = service.get()

    assert rebased.base_version == "0.2.1"
    assert rebased.target_version == "0.2.2"
    assert rebased.revision == stale.revision + 1
    assert rebased.draft.self_trade_definition == stale.draft.self_trade_definition
    assert rebased.validation.status == "STALE"


def test_cash_template_workspace_uses_the_registered_custom_identity(
    tmp_path: Path,
) -> None:
    class CapturingStore:
        def __init__(self) -> None:
            self.payload: dict[str, object] | None = None

        def load(self, identity: WorkspaceIdentity) -> None:
            return None

        def commit(self, identity: WorkspaceIdentity, **kwargs: object) -> SimpleNamespace:
            self.payload = kwargs["payload"]  # type: ignore[assignment]
            return SimpleNamespace(token="captured")

        def list_revisions(self, identity: WorkspaceIdentity) -> tuple[()]:
            return ()

    store = CapturingStore()
    identity = WorkspaceIdentity(
        solution_id="ontology.exchange_analytics.cash_trading",
        solution_version="0.1.0",
        workspace_id="workspace.custom.cash_copy",
        studio_adapter_id="studio-adapter.cash-trading.reference@1",
    )
    service = CashTradingDraftWorkspaceService(
        tmp_path / "studio" / "workspaces",
        SCENARIO,
        StudioReleases(tmp_path / "releases"),
        state_store=store,  # type: ignore[arg-type]
        identity=identity,
    )

    # The common construction seam calls the bound service without repeating
    # its workspace ID.  A template clone must not silently fall back to the
    # bundled Cash Trading reference workspace.
    workspace = service.get()

    assert workspace.workspace_id == identity.workspace_id
    assert store.payload is not None
    assert store.payload["workspace_id"] == identity.workspace_id


def test_cash_descriptor_operations_validate_and_publish_a_new_semantic_release(
    tmp_path: Path,
) -> None:
    adapter, service = _adapter(tmp_path)
    initial = service.get()
    updated = adapter.apply_operations(
        DraftOperationsV1(
            expected_revision=initial.revision,
            operations=(
                {
                    "path": "self_trade_definition",
                    "value": "Both normalized side participant IDs are present and equal; this is a triage candidate only.",
                },
            ),
        ),
        workspace_id=initial.workspace_id,
    )
    validated = service.validate(expected_revision=updated.revision)
    published_workspace, release = service.publish(
        expected_revision=validated.revision
    )

    assert updated.revision == 2
    assert updated.modified_fields == ("self_trade_definition",)
    assert validated.validation.status == "PASS"
    assert release.ref.package_id == "ontology.exchange_analytics.cash_trading"
    assert release.ref.version == "0.2.2"
    assert published_workspace.last_published == release.ref


def test_cash_studio_blocks_claim_overreach_and_runtime_incompatible_rule(
    tmp_path: Path,
) -> None:
    adapter, service = _adapter(tmp_path)
    initial = service.get()
    updated = adapter.apply_operations(
        DraftOperationsV1(
            expected_revision=initial.revision,
            operations=(
                {
                    "path": "self_trade_definition",
                    "value": "This proves market abuse and misconduct.",
                },
                {"path": "exclude_corrections", "value": False},
            ),
        ),
        workspace_id=initial.workspace_id,
    )
    validated = service.validate(expected_revision=updated.revision)

    assert validated.validation.status == "FAIL"
    assert validated.validation.report is not None
    assert len(validated.validation.report["compatibility_defects"]) == 2


def test_cash_workspace_is_opened_through_the_common_studio_api(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("ONTOLOGY_PRODUCT_STATE_MODE", raising=False)
    monkeypatch.setattr(api_module, "DEFAULT_CASH_TRADING_SCENARIO_DIR", SCENARIO)
    monkeypatch.setattr(api_module, "DEFAULT_STUDIO_DIR", tmp_path / "studio")
    monkeypatch.setattr(api_module, "DEFAULT_PUBLISHED_DIR", tmp_path / "registry")

    opened = control_client.get(
        "/control/workspaces/workspace.cash_trading.reference/editor"
    )
    assert opened.status_code == 200
    payload = opened.json()
    assert payload["descriptor"]["studio_adapter_id"] == (
        "studio-adapter.cash-trading.reference@1"
    )
    assert payload["workspace"]["draft"]["exclude_corrections"] is True

    workbench = control_client.get(
        "/control/workspaces/workspace.cash_trading.reference/workbench"
    )
    assert workbench.status_code == 200
    workbench_payload = workbench.json()
    assert workbench_payload["contract"] == "studio-workbench/v1"
    assert workbench_payload["package"]["package_id"] == (
        "ontology.exchange_analytics.cash_trading"
    )
    assert workbench_payload["package"]["entities"]
    assert workbench_payload["package"]["metrics"]
    assert workbench_payload["package"]["bindings"]
    assert workbench_payload["intake"]["contract"] == (
        "cash-trading-intake-summary/v1"
    )

    relationship = dict(workbench_payload["package"]["relationships"][0])
    relationship["id"] = f"{relationship['id']}.studio_copy"
    relationship["name"] = {
        "en": "Studio-authored relationship copy",
        "zh": "Studio新增关系副本",
    }
    package_change = control_client.post(
        "/control/workspaces/workspace.cash_trading.reference/package-operations",
        json={
            "contract": "studio-package-operations/v1",
            "expected_revision": workbench_payload["workspace"]["revision"],
            "operations": [{
                "action": "UPSERT",
                "collection": "relationships",
                "object_id": relationship["id"],
                "payload": relationship,
            }],
        },
    )
    assert package_change.status_code == 200
    rematerialized = control_client.get(
        "/control/workspaces/workspace.cash_trading.reference/workbench"
    ).json()
    assert any(
        item["id"] == relationship["id"]
        for item in rematerialized["package"]["relationships"]
    )

    changed = control_client.post(
        "/control/workspaces/workspace.cash_trading.reference/draft-operations",
        json={
            "contract": "studio-draft-operations/v1",
            "expected_revision": package_change.json()["revision"],
            "operations": [
                {
                    "path": "self_trade_definition",
                    "value": "Participant-side equality used only for synthetic triage.",
                }
            ],
        },
    )
    assert changed.status_code == 200
    assert changed.json()["revision"] == package_change.json()["revision"] + 1


def test_cash_reference_source_pack_can_be_installed_through_the_common_studio_api(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("ONTOLOGY_PRODUCT_STATE_MODE", raising=False)
    monkeypatch.setattr(api_module, "DEFAULT_CASH_TRADING_SCENARIO_DIR", SCENARIO)
    monkeypatch.setattr(api_module, "DEFAULT_STUDIO_DIR", tmp_path / "studio")
    monkeypatch.setattr(api_module, "DEFAULT_PUBLISHED_DIR", tmp_path / "registry")

    installed = control_client.post(
        "/control/workspaces/workspace.cash_trading.reference/sources/install-reference-pack"
    )
    listed = control_client.get(
        "/control/workspaces/workspace.cash_trading.reference/sources"
    )

    assert installed.status_code == 200
    assert installed.json()["physical_file_count"] == 4
    assert installed.json()["registered_source_count"] == 6
    assert listed.status_code == 200
    assert len(listed.json()["current"]) == 6
