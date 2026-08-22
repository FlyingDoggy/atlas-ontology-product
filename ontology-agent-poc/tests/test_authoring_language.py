from __future__ import annotations

from pathlib import Path

import pytest

from ontology_agent.language_policy import (
    create_authoring_policy,
    operation_language_violations,
)
from ontology_agent.release import StudioReleases
from ontology_agent.studio.generic_workspace import GenericDraftWorkspaceService
from ontology_agent.studio.package_authoring import PackageDraftOperationsV1
from ontology_agent.studio.solutions import SolutionDisplayName, _write_blank_solution_files
from ontology_agent.studio.workspace import WorkspaceConflictError


def _workspace(tmp_path: Path) -> GenericDraftWorkspaceService:
    solution = tmp_path / "solution"
    _write_blank_solution_files(
        solution,
        solution_id="ontology.custom.language_case",
        scenario_id="scenario.custom.language_case",
        workspace_id="workspace.custom.language_case",
        display_name=SolutionDisplayName(en="Language Case", zh="语言案例"),
        description="Build an ontology from evidence.",
        owner="actor.domain_owner",
    )
    return GenericDraftWorkspaceService(
        tmp_path / "workspaces",
        solution,
        StudioReleases(tmp_path / "releases"),
    )


def test_authoring_language_is_frozen_before_first_semantic_asset(tmp_path: Path) -> None:
    service = _workspace(tmp_path)
    initial = service.get("workspace.custom.language_case")

    configured = service.configure_authoring_language(
        "zh",
        expected_revision=initial.revision,
        workspace_id=initial.workspace_id,
    )
    package = service.candidate_package(initial.workspace_id)

    assert configured.authoring_language == "zh"
    assert configured.language_policy_digest == package.authoring_policy.policy_digest
    assert package.authoring_policy.authoring_language == "zh"

    same = service.configure_authoring_language(
        "zh",
        expected_revision=configured.revision,
        workspace_id=initial.workspace_id,
    )
    assert same.revision == configured.revision
    with pytest.raises(WorkspaceConflictError, match="locked"):
        service.configure_authoring_language(
            "en",
            expected_revision=configured.revision,
            workspace_id=initial.workspace_id,
        )


def test_authoring_language_cannot_be_changed_after_semantic_assets_exist(
    tmp_path: Path,
) -> None:
    service = _workspace(tmp_path)
    initial = service.get("workspace.custom.language_case")
    operation = PackageDraftOperationsV1.model_validate(
        {
            "expected_revision": initial.revision,
            "operations": [
                {
                    "action": "UPSERT",
                    "collection": "entities",
                    "object_id": "entity.request",
                    "payload": {
                        "id": "entity.request",
                        "status": "proposed",
                        "name": {"en": "Request"},
                        "definition": "A request submitted by a customer.",
                        "owner": "actor.domain_owner",
                        "sources": ["source.requirement"],
                        "primary_key": "property.request.id",
                        "grain": "one request",
                        "lifecycle": "submitted to closed",
                    },
                }
            ],
        }
    )
    changed = service.apply_package_operations(
        operation, workspace_id=initial.workspace_id
    )

    with pytest.raises(WorkspaceConflictError, match="before semantic assets"):
        service.configure_authoring_language(
            "en",
            expected_revision=changed.revision,
            workspace_id=initial.workspace_id,
        )


def test_language_policy_preserves_exact_values_but_blocks_mixed_prose() -> None:
    policy = create_authoring_policy("zh", allowed_verbatim_terms=("Cash Trading",))
    violations = operation_language_violations(
        {
            "id": "metric.cash_trading.adt",
            "name": {"zh": "平均每日成交额"},
            "definition": "Average daily traded value for eligible trades in the period.",
            "expression": "SUM(traded_value) / COUNT(DISTINCT trading_date)",
            "sql": "SELECT SUM(traded_value) FROM trade_activity",
            "physical_column": "traded_value",
            "notes": "Cash Trading 指标。",
        },
        policy,
    )

    assert len(violations) == 1
    assert violations[0].startswith("definition:")


def test_english_policy_rejects_chinese_primary_text() -> None:
    policy = create_authoring_policy("en")

    assert operation_language_violations(
        {
            "id": "entity.trade",
            "name": {"en": "成交活动"},
            "definition": "A normalized trade activity.",
        },
        policy,
    ) == (
        "name.en: contains Chinese text while the Solution authoring language is English",
    )
