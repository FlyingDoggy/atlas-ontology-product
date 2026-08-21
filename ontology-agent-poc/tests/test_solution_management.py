from __future__ import annotations

from pathlib import Path

import pytest

from ontology_agent.studio.solution_management import (
    FileSolutionDirectoryStore,
    SolutionDirectoryPatchV1,
    SolutionDirectoryService,
    SolutionManagementError,
)
from ontology_agent.studio.solutions import SolutionDisplayName


def test_solution_directory_supports_metadata_archive_restore_and_tombstone(
    tmp_path: Path,
) -> None:
    service = SolutionDirectoryService(
        FileSolutionDirectoryStore(tmp_path / "solution-directory.json")
    )
    created = service.create(
        solution_id="ontology.custom.market_activity",
        display_name=SolutionDisplayName(
            en="Market Activity Review", zh="市场活动分析"
        ),
        description="Initial description",
        owner="Market Analytics",
        template_solution_id="ontology.exchange_analytics.adt",
    )
    changed = service.patch(
        created,
        SolutionDirectoryPatchV1(
            display_name=SolutionDisplayName(
                en="Market Activity Analysis", zh="市场活动分析"
            ),
            description="Updated description",
            owner="Ontology Team",
        ),
    )
    archived = service.transition(changed, "ARCHIVED")
    restored = service.transition(archived, "ACTIVE")
    deleted = service.transition(service.transition(restored, "ARCHIVED"), "DELETED")

    assert changed.description == "Updated description"
    assert archived.status == "ARCHIVED"
    assert restored.status == "ACTIVE"
    assert service.store.get(created.solution_id) == deleted
    with pytest.raises(SolutionManagementError, match="cannot transition"):
        service.transition(deleted, "ACTIVE")


def test_solution_directory_rejects_duplicate_create(tmp_path: Path) -> None:
    service = SolutionDirectoryService(
        FileSolutionDirectoryStore(tmp_path / "solution-directory.json")
    )
    kwargs = {
        "solution_id": "ontology.custom.market_activity",
        "display_name": SolutionDisplayName(
            en="Market Activity Review", zh="市场活动分析"
        ),
        "description": "Initial description",
        "owner": "Market Analytics",
        "template_solution_id": "ontology.exchange_analytics.adt",
    }
    service.create(**kwargs)

    with pytest.raises(SolutionManagementError, match="already exists"):
        service.create(**kwargs)
