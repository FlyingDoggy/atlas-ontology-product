from __future__ import annotations

from pathlib import Path

import pytest

from ontology_agent.release import StudioReleases
from ontology_agent.studio.construction import (
    ConstructionDispositionV1,
    FileConstructionRunStore,
    StudioConstructionService,
)
from ontology_agent.studio.intake import ADTIntakeRegistry
from ontology_agent.studio.review_drafts import (
    InMemoryReviewDraftStore,
    ReviewDraftConflict,
    ReviewDraftSaveV1,
)
from ontology_agent.studio.source_projection import build_authoring_projection
from ontology_agent.studio.workspace import DraftWorkspaceService


def _run(tmp_path: Path, scenario_dir: Path):
    workspace = DraftWorkspaceService(
        tmp_path / "workspaces",
        scenario_dir,
        StudioReleases(tmp_path / "releases"),
    )
    package = workspace.candidate_package()
    intake = ADTIntakeRegistry(tmp_path / "intake", scenario_dir).register_reference()
    service = StudioConstructionService(
        store=FileConstructionRunStore(tmp_path / "runs"),
        workspace=workspace,
        package=package,
        intake=intake,
        authoring=build_authoring_projection(
            package=package, intake=intake, scenario_dir=scenario_dir
        ),
        engine=None,
    )
    return service.start(expected_revision=workspace.get().revision)


def test_review_progress_is_resumable_cas_and_final_is_immutable(
    tmp_path: Path, scenario_dir: Path
) -> None:
    run = _run(tmp_path, scenario_dir)
    store = InMemoryReviewDraftStore()
    first_disposition = ConstructionDispositionV1(
        candidate_id=run.candidates[0].candidate_id,
        action="REJECT",
        note="Evidence is insufficient",
        blocks_release=False,
    )
    first = store.save(
        run,
        ReviewDraftSaveV1(
            expected_review_revision=0,
            reviewer="domain-owner.demo",
            dispositions=(first_disposition,),
        ),
    )

    assert first.review_revision == 1
    assert store.get(run.run_id) == first
    assert store.save(
        run,
        ReviewDraftSaveV1(
            expected_review_revision=1,
            reviewer="domain-owner.demo",
            dispositions=(first_disposition,),
        ),
    ) == first

    with pytest.raises(ReviewDraftConflict, match="revision conflict"):
        store.save(
            run,
            ReviewDraftSaveV1(
                expected_review_revision=0,
                reviewer="domain-owner.demo",
                dispositions=(first_disposition,),
            ),
        )

    decision_id = "construction-decision." + "d" * 32
    store.finalization_hook(run.run_id, first.batch_checksum, decision_id)(None)  # type: ignore[arg-type]
    final = store.get(run.run_id)
    assert final is not None
    assert final.status == "FINAL"
    assert final.final_decision_id == decision_id
    assert final.submitted_batch_checksum == first.batch_checksum
    with pytest.raises(ReviewDraftConflict, match="already final"):
        store.save(
            run,
            ReviewDraftSaveV1(
                expected_review_revision=1,
                reviewer="domain-owner.demo",
                dispositions=(first_disposition,),
            ),
        )
