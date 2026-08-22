from __future__ import annotations

from pathlib import Path

import pytest

from ontology_agent.release import StudioReleases
from ontology_agent.studio.generic_workspace import GenericDraftWorkspaceService
from ontology_agent.studio.package_authoring import PackageDraftOperationsV1
from ontology_agent.studio.solutions import (
    SolutionDisplayName,
    _write_blank_solution_files,
)
from ontology_agent.studio.workspace import WorkspaceConflictError, WorkspaceStateError
from ontology_agent.validation import validate_semantic_package


@pytest.fixture()
def blank_solution_dir(tmp_path: Path) -> Path:
    root = tmp_path / "blank-solution"
    _write_blank_solution_files(
        root,
        solution_id="ontology.custom.blank_case",
        scenario_id="scenario.custom.blank_case",
        workspace_id="workspace.custom.blank_case",
        display_name=SolutionDisplayName(en="Blank Case", zh="空白案例"),
        description="Build a governed ontology from registered evidence.",
        owner="actor.domain_owner",
    )
    return root


def _service(
    tmp_path: Path, blank_solution_dir: Path
) -> GenericDraftWorkspaceService:
    return GenericDraftWorkspaceService(
        tmp_path / "workspaces",
        blank_solution_dir,
        StudioReleases(tmp_path / "releases"),
    )


def test_generic_workspace_starts_without_domain_assets(
    tmp_path: Path, blank_solution_dir: Path
) -> None:
    service = _service(tmp_path, blank_solution_dir)

    workspace = service.get("workspace.custom.blank_case")
    package = service.candidate_package("workspace.custom.blank_case")

    assert workspace.revision == 1
    assert workspace.validation.status == "NOT_RUN"
    assert package.scenario.definition == workspace.solution_intent
    assert package.entities == ()
    assert package.metrics == ()
    assert [item.id for item in package.actors] == ["actor.domain_owner"]
    owner_check = next(
        item
        for item in validate_semantic_package(package).checks
        if item.check_id == "OWNER_REFERENCES"
    )
    assert owner_check.status == "PASS"
    assert service.get_intake("workspace.custom.blank_case").assets == ()
    assert [item.revision for item in service.list_revisions("workspace.custom.blank_case")] == [1]


def test_generic_workspace_applies_typed_assets_with_revision_cas(
    tmp_path: Path, blank_solution_dir: Path
) -> None:
    service = _service(tmp_path, blank_solution_dir)
    initial = service.get("workspace.custom.blank_case")
    request = PackageDraftOperationsV1.model_validate(
        {
            "expected_revision": initial.revision,
            "operations": [
                {
                    "action": "UPSERT",
                    "collection": "actors",
                    "object_id": "actor.domain_owner",
                    "payload": {
                        "id": "actor.domain_owner",
                        "status": "proposed",
                        "name": {"en": "Domain owner", "zh": "领域负责人"},
                        "definition": "Accountable reviewer for this ontology.",
                        "owner": "actor.domain_owner",
                        "sources": ["source.solution_brief"],
                        "roles": ["ontology_author"],
                    },
                },
                {
                    "action": "UPSERT",
                    "collection": "entities",
                    "object_id": "entity.business_event",
                    "payload": {
                        "id": "entity.business_event",
                        "status": "proposed",
                        "name": {"en": "Business event", "zh": "业务事件"},
                        "definition": "A candidate event inferred from registered evidence.",
                        "owner": "actor.domain_owner",
                        "sources": ["source.solution_brief"],
                        "primary_key": "property.business_event.id",
                        "grain": "one observed business event",
                        "lifecycle": "draft until reviewed",
                    },
                },
            ],
        }
    )

    changed = service.apply_package_operations(
        request, workspace_id="workspace.custom.blank_case"
    )
    package = service.candidate_package("workspace.custom.blank_case")

    assert changed.revision == 2
    assert changed.validation.status == "STALE"
    assert [item.id for item in package.actors] == ["actor.domain_owner"]
    assert [item.id for item in package.entities] == ["entity.business_event"]
    assert [item.revision for item in service.list_revisions("workspace.custom.blank_case")] == [1, 2]
    with pytest.raises(WorkspaceConflictError):
        service.apply_package_operations(
            request, workspace_id="workspace.custom.blank_case"
        )

    validated = service.validate(
        expected_revision=changed.revision,
        workspace_id="workspace.custom.blank_case",
    )
    assert validated.validation.status == "FAIL"
    with pytest.raises(WorkspaceStateError, match="must pass validation"):
        service.publish(
            expected_revision=validated.revision,
            workspace_id="workspace.custom.blank_case",
        )
