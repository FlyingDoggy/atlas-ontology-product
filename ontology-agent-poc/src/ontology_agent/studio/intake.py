from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..io import file_checksum, sha256_value, write_json


INTAKE_SCHEMA = "adt-intake-submission/v1"
REFERENCE_SUBMISSION_ID = "submission.reference.adt.v1"


class IntakeError(RuntimeError):
    pass


class IntakeConflictError(IntakeError):
    pass


class IntakeParseError(IntakeError):
    pass


class IntakeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class IntakeAsset(IntakeModel):
    asset_id: str
    kind: Literal[
        "requirement_transcription",
        "metric_transcription",
        "data_model",
        "data_dictionary",
        "sql",
    ]
    locator: str
    media_type: str
    checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    disclosure_status: Literal["CLEARED_SYNTHETIC"] = "CLEARED_SYNTHETIC"
    allowed_use: Literal["ONTOLOGY_CANDIDATE"] = "ONTOLOGY_CANDIDATE"
    processing_mode: Literal["TRANSCRIBED", "REGISTERED_NOT_PARSED"]


class SourceAnchor(IntakeModel):
    field: Literal[
        "metric_definition",
        "eligibility_rule",
        "allowed_dimensions",
        "amount_mapping",
    ]
    asset_id: str
    locator: str


class IntakeGap(IntakeModel):
    gap_id: str
    status: Literal["OPEN", "RESOLVED"] = "OPEN"
    description: str
    blocks_synthetic_reference: bool


class ExtractedEligibility(IntakeModel):
    include_status: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    exclude_cancelled: bool


class ExtractedDraft(IntakeModel):
    metric_definition: str = Field(min_length=1)
    eligibility_rule: ExtractedEligibility
    allowed_dimensions: tuple[str, ...] = Field(min_length=1)
    amount_mapping: str


class IntakeSubmission(IntakeModel):
    schema_version: Literal["adt-intake-submission/v1"] = INTAKE_SCHEMA
    submission_id: str
    registered_at: datetime
    claim_ceiling: Literal["CONSTRUCTED_SYNTHETIC_NOT_HKEX_VALIDATED"]
    assets: tuple[IntakeAsset, ...]
    anchors: tuple[SourceAnchor, ...]
    gaps: tuple[IntakeGap, ...]
    extracted_draft: ExtractedDraft
    content_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")


_ASSETS = (
    (
        "asset.requirements",
        "requirement_transcription",
        "input/requirements_and_process.md",
        "text/markdown",
        "TRANSCRIBED",
    ),
    (
        "asset.metric_logic",
        "metric_transcription",
        "input/metric_logic.md",
        "text/markdown",
        "TRANSCRIBED",
    ),
    (
        "asset.data_model",
        "data_model",
        "input/data_model.md",
        "text/markdown",
        "REGISTERED_NOT_PARSED",
    ),
    (
        "asset.data_dictionary",
        "data_dictionary",
        "input/data_dictionary.csv",
        "text/csv",
        "REGISTERED_NOT_PARSED",
    ),
    (
        "asset.existing_sql",
        "sql",
        "sql/existing_adt.sql",
        "text/sql",
        "REGISTERED_NOT_PARSED",
    ),
)


def _safe_asset(scenario_dir: Path, locator: str) -> Path:
    candidate = PurePosixPath(locator)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise IntakeError(f"Unsafe intake locator: {locator}")
    root = scenario_dir.resolve()
    path = (root / candidate.as_posix()).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise IntakeError(f"Required intake asset is unavailable: {locator}")
    return path


def _metric_row(markdown: str, metric_id: str) -> list[str]:
    for line in markdown.splitlines():
        if line.lstrip().startswith(f"| {metric_id} |"):
            return [cell.strip() for cell in line.strip().strip("|").split("|")]
    raise IntakeParseError(f"Required metric row is missing: {metric_id}")


def _extract(requirements: str, metric_logic: str) -> ExtractedDraft:
    metric = _metric_row(metric_logic, "M-03")
    if len(metric) < 7:
        raise IntakeParseError("M-03 metric row is incomplete")

    amount = re.search(r"成交额字段：`([A-Za-z0-9_]+)`", requirements)
    eligibility = re.search(
        r"合资格成交：`status\s*=\s*'([A-Z0-9_]+)'`\s*且\s*`cancellation_flag\s*=\s*(true|false)`",
        requirements,
    )
    if amount is None or eligibility is None:
        raise IntakeParseError(
            "Required amount or eligibility assertion is missing from the transcription"
        )

    grain_and_dimensions = metric[5]
    dimensions: list[str] = []
    if "期间" in grain_and_dimensions:
        dimensions.append("dimension.period")
    if "板块" in grain_and_dimensions:
        dimensions.append("dimension.segment")
    if not dimensions:
        raise IntakeParseError("M-03 does not declare a supported dimension")

    cancellation_value = eligibility.group(2) == "true"
    return ExtractedDraft(
        metric_definition=metric[2],
        eligibility_rule=ExtractedEligibility(
            include_status=eligibility.group(1),
            exclude_cancelled=not cancellation_value,
        ),
        allowed_dimensions=tuple(dimensions),
        amount_mapping=amount.group(1),
    )


class ADTIntakeRegistry:
    """Registers fixed, cleared reference assets without pretending to parse arbitrary files."""

    def __init__(self, root: Path, scenario_dir: Path):
        self.root = root.resolve()
        self.scenario_dir = scenario_dir.resolve()

    def _path(self, submission_id: str) -> Path:
        if submission_id != REFERENCE_SUBMISSION_ID:
            raise IntakeError("Only the fixed ADT reference submission is supported")
        return self.root / submission_id / "submission.json"

    def register_reference(self) -> IntakeSubmission:
        assets = tuple(
            IntakeAsset(
                asset_id=asset_id,
                kind=kind,
                locator=locator,
                media_type=media_type,
                checksum=file_checksum(_safe_asset(self.scenario_dir, locator)),
                processing_mode=processing_mode,
            )
            for asset_id, kind, locator, media_type, processing_mode in _ASSETS
        )
        requirements = _safe_asset(
            self.scenario_dir, "input/requirements_and_process.md"
        ).read_text(encoding="utf-8")
        metric_logic = _safe_asset(
            self.scenario_dir, "input/metric_logic.md"
        ).read_text(encoding="utf-8")
        extracted = _extract(requirements, metric_logic)
        anchors = (
            SourceAnchor(
                field="metric_definition",
                asset_id="asset.metric_logic",
                locator="row=M-03 / column=业务定义",
            ),
            SourceAnchor(
                field="allowed_dimensions",
                asset_id="asset.metric_logic",
                locator="row=M-03 / column=粒度与可切分维度",
            ),
            SourceAnchor(
                field="eligibility_rule",
                asset_id="asset.requirements",
                locator="section=5 / assertion=合资格成交",
            ),
            SourceAnchor(
                field="amount_mapping",
                asset_id="asset.requirements",
                locator="section=5 / assertion=成交额字段",
            ),
        )
        gaps = (
            IntakeGap(
                gap_id="gap.real_hkex_definition_unconfirmed",
                description="The extracted definition is synthetic reference content, not an HKEX-confirmed business definition.",
                blocks_synthetic_reference=False,
            ),
            IntakeGap(
                gap_id="gap.sql_not_machine_reconciled",
                description="Existing SQL is checksum-registered for human comparison; no generic SQL parser or automatic truth claim is made.",
                blocks_synthetic_reference=False,
            ),
        )
        payload = {
            "schema_version": INTAKE_SCHEMA,
            "submission_id": REFERENCE_SUBMISSION_ID,
            "claim_ceiling": "CONSTRUCTED_SYNTHETIC_NOT_HKEX_VALIDATED",
            "assets": [asset.model_dump(mode="json") for asset in assets],
            "anchors": [anchor.model_dump(mode="json") for anchor in anchors],
            "gaps": [gap.model_dump(mode="json") for gap in gaps],
            "extracted_draft": extracted.model_dump(mode="json"),
        }
        submission = IntakeSubmission(
            **payload,
            registered_at=datetime.now(timezone.utc),
            content_checksum=sha256_value(payload),
        )
        path = self._path(REFERENCE_SUBMISSION_ID)
        if path.exists():
            existing = self.load(REFERENCE_SUBMISSION_ID)
            if existing.content_checksum != submission.content_checksum:
                raise IntakeConflictError(
                    "The fixed submission ID already exists with different source bytes"
                )
            return existing
        write_json(path, submission.model_dump(mode="json"))
        return submission

    def load(self, submission_id: str) -> IntakeSubmission:
        path = self._path(submission_id)
        if not path.is_file():
            raise IntakeError("Intake submission is not registered")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            submission = IntakeSubmission.model_validate(payload)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise IntakeError("Intake submission is invalid") from exc
        unsigned = submission.model_dump(
            mode="json", exclude={"registered_at", "content_checksum"}
        )
        if sha256_value(unsigned) != submission.content_checksum:
            raise IntakeError("Intake submission checksum mismatch")
        return submission

    def project_anchor_text(
        self,
        submission: IntakeSubmission,
        anchor: SourceAnchor,
    ) -> str:
        """Return one explicitly routed, cleared transcription fragment.

        This is an ADT adapter, not a generic document parser. Registered attachments
        marked REGISTERED_NOT_PARSED can never become model text through this method.
        """
        asset = next(
            (item for item in submission.assets if item.asset_id == anchor.asset_id),
            None,
        )
        if asset is None or asset.processing_mode != "TRANSCRIBED":
            raise IntakeError("The source anchor is not cleared for text projection")
        path = _safe_asset(self.scenario_dir, asset.locator)
        if file_checksum(path) != asset.checksum:
            raise IntakeError("Cleared intake asset checksum mismatch")
        content = path.read_text(encoding="utf-8")
        if asset.asset_id == "asset.metric_logic" and anchor.locator.startswith(
            "row=M-03"
        ):
            line = next(
                (
                    item.strip()
                    for item in content.splitlines()
                    if item.lstrip().startswith("| M-03 |")
                ),
                None,
            )
        elif (
            asset.asset_id == "asset.requirements"
            and "assertion=合资格成交" in anchor.locator
        ):
            line = next(
                (
                    item.strip()
                    for item in content.splitlines()
                    if item.strip().startswith("- 合资格成交：")
                ),
                None,
            )
        elif (
            asset.asset_id == "asset.requirements"
            and "assertion=成交额字段" in anchor.locator
        ):
            line = next(
                (
                    item.strip()
                    for item in content.splitlines()
                    if item.strip().startswith("- 成交额字段：")
                ),
                None,
            )
        else:
            line = None
        if not line:
            raise IntakeError("The routed source fragment is missing")
        return line
