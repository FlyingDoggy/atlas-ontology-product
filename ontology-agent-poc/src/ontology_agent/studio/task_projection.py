from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from ..models import AuthoringLanguage, StrictModel
from .construction import ConstructionReviewDecisionV1, ConstructionRunV1
from .construction_jobs import ConstructionJobV1


BuildTaskOutcome = Literal[
    "TECHNICAL_FAILURE",
    "BLOCKED",
    "REVIEW_READY_WITH_WARNINGS",
    "REVIEW_READY",
    "NO_APPLICABLE_CHANGES",
]


class StudioBuildTaskDestinationV1(StrictModel):
    type: Literal["TASK", "REVIEW", "RESULT", "SOLUTION"]
    solution_id: str
    run_id: str | None = None
    decision_id: str | None = None


class StudioBuildTaskSummaryV1(StrictModel):
    contract: Literal["studio-build-task-summary/v1"] = (
        "studio-build-task-summary/v1"
    )
    task_id: str
    solution_id: str
    solution_name: str
    workspace_id: str
    authoring_language: AuthoringLanguage | None = None
    language_policy_digest: str | None = None
    execution_status: str
    attempt_id: str | None = None
    lease_epoch: int = Field(ge=0)
    current_stage: str
    completed_stages: int = Field(ge=0)
    total_stages: int = Field(ge=1)
    progress_message: str
    result_outcome: BuildTaskOutcome | None = None
    outcome_policy_version: Literal["studio-build-outcome/v1"] = (
        "studio-build-outcome/v1"
    )
    reason_codes: tuple[str, ...] = ()
    run_id: str | None = None
    run_checksum: str | None = None
    review_status: Literal["NOT_READY", "NEEDS_REVIEW", "APPLIED"]
    decision_id: str | None = None
    candidate_count: int = Field(ge=0)
    compilable_count: int = Field(ge=0)
    blocker_count: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    destination: StudioBuildTaskDestinationV1


def _outcome(
    job: ConstructionJobV1,
    run: ConstructionRunV1 | None,
) -> tuple[BuildTaskOutcome | None, tuple[str, ...]]:
    if job.status in {"QUEUED", "RUNNING", "COMMITTING", "CANCEL_REQUESTED"}:
        return None, ()
    if job.status == "FAILED":
        return "TECHNICAL_FAILURE", (job.error_code or "JOB_FAILED",)
    if job.status in {"CANCELLED", "STALE"}:
        return None, (job.error_code or job.status,)
    if run is None:
        return "TECHNICAL_FAILURE", ("IMMUTABLE_RUN_UNAVAILABLE",)
    required_failure = any(
        receipt.stage == "BUILDER_AGENT" and receipt.status == "FAIL"
        for receipt in run.stage_receipts
    )
    if run.status == "FAILED" or required_failure:
        return "TECHNICAL_FAILURE", ("REQUIRED_BUILDER_FAILED",)
    compilable = sum(candidate.compile_eligible for candidate in run.candidates)
    blockers = sum(finding.blocks_release for finding in run.machine_findings)
    if compilable == 0:
        no_change = bool(run.candidates) and all(
            candidate.draft_diff.change_type == "NO_CHANGE"
            for candidate in run.candidates
        )
        if no_change and blockers == 0:
            return "NO_APPLICABLE_CHANGES", ("NO_DRAFT_DIFF",)
        return "BLOCKED", ("NO_COMPILABLE_CANDIDATE",)
    warnings = blockers > 0 or any(
        receipt.status in {"WARN", "FAIL"}
        and receipt.stage in {"SEMANTICA_PROPOSAL", "REVIEWER_AGENT"}
        for receipt in run.stage_receipts
    )
    if warnings:
        reasons = []
        if blockers:
            reasons.append("MACHINE_REVIEW_FINDINGS")
        if any(
            receipt.status in {"WARN", "FAIL"}
            and receipt.stage in {"SEMANTICA_PROPOSAL", "REVIEWER_AGENT"}
            for receipt in run.stage_receipts
        ):
            reasons.append("OPTIONAL_STAGE_WARNING")
        return "REVIEW_READY_WITH_WARNINGS", tuple(reasons)
    return "REVIEW_READY", ()


def project_build_task(
    *,
    job: ConstructionJobV1,
    solution_name: str,
    run: ConstructionRunV1 | None,
    decision: ConstructionReviewDecisionV1 | None,
) -> StudioBuildTaskSummaryV1:
    outcome, reasons = _outcome(job, run)
    candidate_count = len(run.candidates) if run is not None else 0
    compilable_count = (
        sum(candidate.compile_eligible for candidate in run.candidates)
        if run is not None
        else 0
    )
    blocker_count = (
        sum(finding.blocks_release for finding in run.machine_findings)
        if run is not None
        else 0
    )
    if decision is not None:
        review_status: Literal["NOT_READY", "NEEDS_REVIEW", "APPLIED"] = "APPLIED"
        destination = StudioBuildTaskDestinationV1(
            type="RESULT",
            solution_id=job.solution_id,
            run_id=run.run_id if run is not None else job.run_id,
            decision_id=decision.decision_id,
        )
    elif outcome in {"REVIEW_READY", "REVIEW_READY_WITH_WARNINGS"} and run is not None:
        review_status = "NEEDS_REVIEW"
        destination = StudioBuildTaskDestinationV1(
            type="REVIEW", solution_id=job.solution_id, run_id=run.run_id
        )
    else:
        review_status = "NOT_READY"
        destination = StudioBuildTaskDestinationV1(
            type="TASK", solution_id=job.solution_id, run_id=job.run_id
        )
    return StudioBuildTaskSummaryV1(
        task_id=job.job_id,
        solution_id=job.solution_id,
        solution_name=solution_name,
        workspace_id=job.workspace_id,
        authoring_language=job.authoring_language,
        language_policy_digest=job.language_policy_digest,
        execution_status=job.status,
        attempt_id=job.attempt_id,
        lease_epoch=job.lease_epoch,
        current_stage=job.current_stage,
        completed_stages=job.completed_stages,
        total_stages=job.total_stages,
        progress_message=job.progress_message,
        result_outcome=outcome,
        reason_codes=reasons,
        run_id=run.run_id if run is not None else None,
        run_checksum=run.run_checksum if run is not None else None,
        review_status=review_status,
        decision_id=decision.decision_id if decision is not None else None,
        candidate_count=candidate_count,
        compilable_count=compilable_count,
        blocker_count=blocker_count,
        created_at=job.created_at,
        updated_at=job.updated_at,
        completed_at=job.completed_at,
        destination=destination,
    )
