from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
import re
from typing import Any, Literal

from pydantic import Field

from ..contracts import Sha256
from ..io import file_checksum, sha256_value
from ..models import OntologyPackage, StrictModel


class SourceProjectionError(RuntimeError):
    """A registered source could not be projected without losing exact identity."""


class SourceProjectionAnchorV1(StrictModel):
    contract: Literal["source-anchor/v1"] = "source-anchor/v1"
    source_id: str = Field(min_length=1, max_length=255)
    source_checksum: Sha256
    locator_kind: Literal[
        "MARKDOWN_TABLE_ROW", "TEXT_RANGE", "XLSX_ROW", "XLSX_RANGE"
    ] = "MARKDOWN_TABLE_ROW"
    locator: str = Field(min_length=1, max_length=500)
    line_number: int = Field(ge=1)
    sheet_name: str | None = None
    cell_range: str | None = None
    snippet_checksum: Sha256


class RequirementProjectionV1(StrictModel):
    contract: Literal["requirement-projection/v1"] = "requirement-projection/v1"
    requirement_key: str = Field(pattern=r"^O-[0-9]{2}$")
    question: str = Field(min_length=1)
    minimum_output: str = Field(min_length=1)
    presentation: str = Field(min_length=1)
    status: Literal["SOURCE_SUPPORTED", "CANONICAL_DRAFT"]
    support_class: Literal["DIRECT_EXACT", "CANONICAL_DRAFT"]
    source_anchor: SourceProjectionAnchorV1 | None


class MetricCandidateProjectionV1(StrictModel):
    contract: Literal["metric-candidate-projection/v1"] = (
        "metric-candidate-projection/v1"
    )
    metric_key: str = Field(pattern=r"^M-[0-9]{2}$")
    name: str = Field(min_length=1)
    definition: str = Field(min_length=1)
    calculation_logic: str = Field(min_length=1)
    filters_and_scope: str = Field(min_length=1)
    grain_and_dimensions: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    null_and_zero_policy: str = Field(min_length=1)
    primary_sources: str = Field(min_length=1)
    source_status: str = Field(min_length=1)
    support_class: Literal["DIRECT_EXACT", "CANONICAL_DRAFT"]
    compile_status: Literal["EXECUTABLE", "SOURCE_CANDIDATE"]
    canonical_metric_id: str | None = None
    ontology_status: Literal["REVIEWED", "DRAFT", "UNMAPPED"]
    runtime_status: Literal["SUPPORTED", "NOT_YET_SUPPORTED", "NOT_APPLICABLE"]
    governance_status: Literal[
        "REVIEWED", "REVIEWED_WITH_ASSUMPTIONS", "UNREVIEWED"
    ]
    source_anchor: SourceProjectionAnchorV1 | None


class StudioAuthoringProjectionV1(StrictModel):
    contract: Literal["studio-authoring-projection/v1"] = (
        "studio-authoring-projection/v1"
    )
    requirements: tuple[RequirementProjectionV1, ...]
    metric_candidates: tuple[MetricCandidateProjectionV1, ...]
    source_mode: Literal["EXACT_TRANSCRIPTION", "CANONICAL_FALLBACK"]


def _record(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return dict(value)
    return {}


def _assets(intake: Any) -> tuple[dict[str, Any], ...]:
    payload = _record(intake)
    values = payload.get("assets") or payload.get("source_files") or ()
    return tuple(_record(item) for item in values)


def _exact_source_text(
    *,
    scenario_dir: Path,
    asset: dict[str, Any],
) -> tuple[str, str, str]:
    source_id = str(asset.get("asset_id") or asset.get("file_id") or "")
    locator = str(asset.get("locator") or asset.get("stored_locator") or "")
    expected = str(asset.get("checksum") or asset.get("sha256") or "")
    inline_text = asset.get("content_text")
    if inline_text is not None:
        if not source_id or not locator or not isinstance(inline_text, str):
            raise SourceProjectionError("Registered transcription projection is invalid")
        encoded = inline_text.encode("utf-8")
        actual = hashlib.sha256(encoded).hexdigest()
        if expected != actual:
            raise SourceProjectionError("Registered transcription checksum mismatch")
        return source_id, actual, inline_text
    candidate = PurePosixPath(locator)
    if not source_id or not locator or candidate.is_absolute() or ".." in candidate.parts:
        raise SourceProjectionError("Registered transcription locator is unsafe")
    root = scenario_dir.resolve()
    path = root.joinpath(*candidate.parts).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise SourceProjectionError("Registered transcription is unavailable")
    actual = file_checksum(path)
    if expected != actual:
        raise SourceProjectionError("Registered transcription checksum mismatch")
    try:
        return source_id, actual, path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise SourceProjectionError("Registered transcription cannot be read") from exc


def _markdown_rows(text: str, prefix: str) -> tuple[tuple[int, str, list[str]], ...]:
    rows: list[tuple[int, str, list[str]]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped.startswith(f"| {prefix}"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if cells and cells[0].startswith(prefix):
            rows.append((line_number, stripped, cells))
    return tuple(rows)


def _anchor(
    *,
    source_id: str,
    source_checksum: str,
    line_number: int,
    snippet: str,
    key: str,
) -> SourceProjectionAnchorV1:
    return SourceProjectionAnchorV1(
        source_id=source_id,
        source_checksum=source_checksum,
        locator=f"row={key};line={line_number}",
        line_number=line_number,
        snippet_checksum=sha256_value(snippet),
    )


def _normalized_metric_name(value: str | None) -> str:
    """Normalize one available label without requiring a fabricated translation."""

    if value is None:
        return ""
    return re.sub(r"[^a-z0-9\u3400-\u9fff]+", "", value.casefold())


def _canonical_metric_target(
    package: OntologyPackage,
    *,
    metric_key: str,
    name: str,
) -> str | None:
    normalized = _normalized_metric_name(name)
    exact_matches = [
        item.id
        for item in package.metrics
        if normalized
        in {
            _normalized_metric_name(item.name.en),
            _normalized_metric_name(item.name.zh),
        }
    ]
    if len(exact_matches) == 1:
        return exact_matches[0]
    # A source label may append a well-known acronym or clarification while still
    # naming the same existing metric (for example, a full name followed by an
    # acronym in parentheses).  Accept only one unambiguous containment match; this
    # is generic label reconciliation, not a scenario-specific key map.
    contained_matches = [
        item.id
        for item in package.metrics
        if len(normalized) >= 4
        and any(
            candidate
            and len(candidate) >= 4
            and (candidate in normalized or normalized in candidate)
            for candidate in (
                _normalized_metric_name(item.name.en),
                _normalized_metric_name(item.name.zh),
            )
        )
    ]
    if len(contained_matches) == 1:
        return contained_matches[0]
    tagged = [
        item.id
        for item in package.metrics
        if f"source_metric:{metric_key}" in item.tags
    ]
    return tagged[0] if len(tagged) == 1 else None


def _metric_states(
    package: OntologyPackage, canonical_metric_id: str | None
) -> tuple[
    Literal["REVIEWED", "DRAFT", "UNMAPPED"],
    Literal["SUPPORTED", "NOT_YET_SUPPORTED", "NOT_APPLICABLE"],
    Literal["REVIEWED", "REVIEWED_WITH_ASSUMPTIONS", "UNREVIEWED"],
]:
    if canonical_metric_id is None:
        return "UNMAPPED", "NOT_APPLICABLE", "UNREVIEWED"
    metric = next(item for item in package.metrics if item.id == canonical_metric_id)
    reviewed = metric.status.value in {"confirmed", "published"}
    runtime_metric_ids = {
        metric_id
        for pattern in package.analysis_patterns
        for metric_id in pattern.required_metrics
    }
    ontology_status: Literal["REVIEWED", "DRAFT", "UNMAPPED"] = (
        "REVIEWED" if reviewed else "DRAFT"
    )
    runtime_status: Literal[
        "SUPPORTED", "NOT_YET_SUPPORTED", "NOT_APPLICABLE"
    ] = (
        "SUPPORTED"
        if canonical_metric_id in runtime_metric_ids
        else "NOT_YET_SUPPORTED"
    )
    governance_status: Literal[
        "REVIEWED", "REVIEWED_WITH_ASSUMPTIONS", "UNREVIEWED"
    ] = (
        "REVIEWED_WITH_ASSUMPTIONS"
        if reviewed and metric.decisions
        else "REVIEWED"
        if reviewed
        else "UNREVIEWED"
    )
    return ontology_status, runtime_status, governance_status


def _structured_rows(
    asset: dict[str, Any],
    *,
    sheet_name: str,
) -> tuple[str, str, dict[int, dict[str, tuple[Any, str]]]]:
    source_id = str(asset.get("asset_id") or asset.get("file_id") or "")
    source_checksum = str(asset.get("checksum") or asset.get("sha256") or "")
    source_version_id = str(asset.get("source_version_id") or "")
    preview = _record(asset.get("source_preview"))
    if (
        not source_id
        or not source_version_id
        or preview.get("status") != "PARSED"
        or preview.get("source_version_id") != source_version_id
        or preview.get("content_checksum") != source_checksum
    ):
        raise SourceProjectionError("Structured transcription identity is invalid")
    match = next(
        (
            _record(item)
            for item in preview.get("sheets", ())
            if _record(item).get("sheet_name") == sheet_name
        ),
        None,
    )
    if match is None:
        raise SourceProjectionError(
            f"Structured transcription is missing sheet {sheet_name}"
        )
    rows: dict[int, dict[str, tuple[Any, str]]] = {}
    for raw_cell in match.get("cells", ()):
        cell = _record(raw_cell)
        coordinate = str(cell.get("cell") or "")
        coordinate_match = re.fullmatch(r"([A-Z]+)([1-9][0-9]*)", coordinate)
        if coordinate_match is None:
            raise SourceProjectionError("Structured transcription cell is invalid")
        expected = sha256_value(
            {
                "source_version_id": source_version_id,
                "content_checksum": source_checksum,
                "sheet": sheet_name,
                "cell": coordinate,
                "raw_formula": cell.get("raw_formula"),
                "display_value": cell.get("display_value"),
            }
        )
        if cell.get("snippet_checksum") != expected:
            raise SourceProjectionError("Structured transcription cell anchor mismatch")
        column, row_text = coordinate_match.groups()
        rows.setdefault(int(row_text), {})[column] = (
            cell.get("display_value"),
            expected,
        )
    return source_id, source_checksum, rows


def _required_text(
    row: dict[str, tuple[Any, str]],
    column: str,
    *,
    detail: str,
) -> str:
    value = row.get(column, (None, ""))[0]
    text = str(value).strip() if value is not None else ""
    if not text:
        raise SourceProjectionError(f"Structured transcription {detail} is incomplete")
    return text


def _xlsx_anchor(
    *,
    source_id: str,
    source_checksum: str,
    sheet_name: str,
    row_number: int,
    end_column: str,
    row: dict[str, tuple[Any, str]],
) -> SourceProjectionAnchorV1:
    cell_range = f"A{row_number}:{end_column}{row_number}"
    return SourceProjectionAnchorV1(
        source_id=source_id,
        source_checksum=source_checksum,
        locator_kind="XLSX_ROW",
        locator=f"sheet={sheet_name};range={cell_range}",
        line_number=row_number,
        sheet_name=sheet_name,
        cell_range=cell_range,
        snippet_checksum=sha256_value(
            {
                "source_id": source_id,
                "source_checksum": source_checksum,
                "sheet_name": sheet_name,
                "cell_range": cell_range,
                "cell_snippet_checksums": [
                    row[column][1]
                    for column in sorted(row)
                    if column <= end_column
                ],
            }
        ),
    )


def _structured_projection(
    *,
    package: OntologyPackage,
    requirement_asset: dict[str, Any],
    metric_asset: dict[str, Any],
) -> StudioAuthoringProjectionV1:
    requirement_sheet = "01_Requirements_Process"
    metric_sheet = "02_Metric_Logic"
    requirement_id, requirement_checksum, requirement_rows = _structured_rows(
        requirement_asset,
        sheet_name=requirement_sheet,
    )
    metric_id, metric_checksum, metric_rows = _structured_rows(
        metric_asset,
        sheet_name=metric_sheet,
    )
    requirement_header = next(
        (
            row_number
            for row_number, row in sorted(requirement_rows.items())
            if "business question" in str(row.get("B", ("", ""))[0]).casefold()
        ),
        None,
    )
    metric_header = next(
        (
            row_number
            for row_number, row in sorted(metric_rows.items())
            if str(row.get("A", ("", ""))[0]).strip().casefold() == "metric name"
        ),
        None,
    )
    if requirement_header is None or metric_header is None:
        raise SourceProjectionError("Structured transcription template headers are missing")

    requirements: list[RequirementProjectionV1] = []
    for row_number, row in sorted(requirement_rows.items()):
        if row_number <= requirement_header or row.get("A", (None, ""))[0] is None:
            continue
        question = str(row.get("B", ("", ""))[0] or "").strip()
        if not question:
            continue
        requirements.append(
            RequirementProjectionV1(
                requirement_key=f"O-{len(requirements) + 1:02d}",
                question=question,
                minimum_output=_required_text(row, "C", detail="requirement output"),
                presentation=_required_text(row, "D", detail="requirement use"),
                status="SOURCE_SUPPORTED",
                support_class="DIRECT_EXACT",
                source_anchor=_xlsx_anchor(
                    source_id=requirement_id,
                    source_checksum=requirement_checksum,
                    sheet_name=requirement_sheet,
                    row_number=row_number,
                    end_column="D",
                    row=row,
                ),
            )
        )

    metrics: list[MetricCandidateProjectionV1] = []
    for row_number, row in sorted(metric_rows.items()):
        if row_number <= metric_header:
            continue
        name = str(row.get("A", ("", ""))[0] or "").strip()
        if not name or name.casefold().startswith("example"):
            continue
        metric_key = f"M-{len(metrics) + 1:02d}"
        definition = _required_text(row, "B", detail="metric definition")
        calculation = _required_text(row, "C", detail="metric calculation")
        scope = _required_text(row, "D", detail="metric scope")
        output_policy = _required_text(row, "E", detail="metric output policy")
        canonical_id = _canonical_metric_target(
            package,
            metric_key=metric_key,
            name=name,
        )
        ontology_status, runtime_status, governance_status = _metric_states(
            package, canonical_id
        )
        metrics.append(
            MetricCandidateProjectionV1(
                metric_key=metric_key,
                name=name,
                definition=definition,
                calculation_logic=calculation,
                filters_and_scope=scope,
                grain_and_dimensions=scope,
                unit=output_policy,
                null_and_zero_policy=output_policy,
                primary_sources="Data dependencies stated in the exact calculation row",
                source_status="Transcribed input; domain confirmation is still required",
                support_class="DIRECT_EXACT",
                compile_status="EXECUTABLE" if canonical_id else "SOURCE_CANDIDATE",
                canonical_metric_id=canonical_id,
                ontology_status=ontology_status,
                runtime_status=runtime_status,
                governance_status=governance_status,
                source_anchor=_xlsx_anchor(
                    source_id=metric_id,
                    source_checksum=metric_checksum,
                    sheet_name=metric_sheet,
                    row_number=row_number,
                    end_column="E",
                    row=row,
                ),
            )
        )
    if not requirements or not metrics:
        raise SourceProjectionError("Structured transcription contains no formal rows")
    return StudioAuthoringProjectionV1(
        requirements=tuple(requirements),
        metric_candidates=tuple(metrics),
        source_mode="EXACT_TRANSCRIPTION",
    )


def _transcription_projection(
    *,
    package: OntologyPackage,
    intake: Any,
    scenario_dir: Path,
) -> StudioAuthoringProjectionV1 | None:
    assets = _assets(intake)
    requirement_asset = next(
        (item for item in assets if item.get("kind") == "requirement_transcription"),
        None,
    )
    metric_asset = next(
        (item for item in assets if item.get("kind") == "metric_transcription"),
        None,
    )
    if requirement_asset is not None and requirement_asset.get("source_preview"):
        preview = _record(requirement_asset.get("source_preview"))
        if any(
            _record(item).get("sheet_name") == "02_Metric_Logic"
            for item in preview.get("sheets", ())
        ):
            metric_asset = requirement_asset
    if requirement_asset is None or metric_asset is None:
        return None
    if requirement_asset.get("source_preview") or metric_asset.get("source_preview"):
        if not requirement_asset.get("source_preview") or not metric_asset.get(
            "source_preview"
        ):
            raise SourceProjectionError(
                "Mixed text and structured transcription pair is unsupported"
            )
        return _structured_projection(
            package=package,
            requirement_asset=requirement_asset,
            metric_asset=metric_asset,
        )
    requirement_id, requirement_checksum, requirement_text = _exact_source_text(
        scenario_dir=scenario_dir, asset=requirement_asset
    )
    metric_id, metric_checksum, metric_text = _exact_source_text(
        scenario_dir=scenario_dir, asset=metric_asset
    )
    requirements: list[RequirementProjectionV1] = []
    for line_number, snippet, cells in _markdown_rows(requirement_text, "O-"):
        if len(cells) != 4:
            # IDs can legitimately appear in narrative/dependency tables.  A
            # row is an exact legacy transcription only when its full schema
            # is present; otherwise it remains raw Builder evidence.
            continue
        requirements.append(
            RequirementProjectionV1(
                requirement_key=cells[0],
                question=cells[1],
                minimum_output=cells[2],
                presentation=cells[3],
                status="SOURCE_SUPPORTED",
                support_class="DIRECT_EXACT",
                source_anchor=_anchor(
                    source_id=requirement_id,
                    source_checksum=requirement_checksum,
                    line_number=line_number,
                    snippet=snippet,
                    key=cells[0],
                ),
            )
        )
    metrics: list[MetricCandidateProjectionV1] = []
    for line_number, snippet, cells in _markdown_rows(metric_text, "M-"):
        if len(cells) != 10:
            continue
        canonical_id = _canonical_metric_target(
            package,
            metric_key=cells[0],
            name=cells[1],
        )
        ontology_status, runtime_status, governance_status = _metric_states(
            package, canonical_id
        )
        metrics.append(
            MetricCandidateProjectionV1(
                metric_key=cells[0],
                name=cells[1],
                definition=cells[2],
                calculation_logic=cells[3],
                filters_and_scope=cells[4],
                grain_and_dimensions=cells[5],
                unit=cells[6],
                null_and_zero_policy=cells[7],
                primary_sources=cells[8],
                source_status=cells[9],
                support_class="DIRECT_EXACT",
                compile_status="EXECUTABLE" if canonical_id else "SOURCE_CANDIDATE",
                canonical_metric_id=canonical_id,
                ontology_status=ontology_status,
                runtime_status=runtime_status,
                governance_status=governance_status,
                source_anchor=_anchor(
                    source_id=metric_id,
                    source_checksum=metric_checksum,
                    line_number=line_number,
                    snippet=snippet,
                    key=cells[0],
                ),
            )
        )
    # A generic Solution is allowed to provide narrative requirement and metric
    # documents instead of the legacy exact-transcription table shape.  Those
    # documents remain exact Builder evidence, but they do not populate this
    # optional compatibility projection.  Falling back here keeps free-form
    # customer material buildable without pretending that rows were parsed.
    if not requirements and not metrics:
        return None
    if not requirements or not metrics:
        raise SourceProjectionError("Transcription tables contain no supported rows")
    return StudioAuthoringProjectionV1(
        requirements=tuple(requirements),
        metric_candidates=tuple(metrics),
        source_mode="EXACT_TRANSCRIPTION",
    )


def _canonical_projection(package: OntologyPackage) -> StudioAuthoringProjectionV1:
    requirements = tuple(
        RequirementProjectionV1(
            requirement_key=f"O-{index:02d}",
            question=item.name.zh or item.name.en,
            minimum_output=item.definition,
            presentation="由 Agent Experience 合同定义",
            status="CANONICAL_DRAFT",
            support_class="CANONICAL_DRAFT",
            source_anchor=None,
        )
        for index, item in enumerate(package.questions, start=1)
    )
    metrics = tuple(
        MetricCandidateProjectionV1(
            metric_key=f"M-{index:02d}",
            name=item.name.zh or item.name.en,
            definition=item.definition,
            calculation_logic=str(item.formula.model_dump(mode="json")),
            filters_and_scope=", ".join(item.query.filters) or "无额外过滤",
            grain_and_dimensions=", ".join(item.result_grain) or "总体",
            unit=item.unit,
            null_and_zero_policy=f"{item.null_policy}; {item.zero_denominator_policy}",
            primary_sources=", ".join(item.sources),
            source_status=item.status,
            support_class="CANONICAL_DRAFT",
            compile_status="EXECUTABLE",
            canonical_metric_id=item.id,
            ontology_status=(
                "REVIEWED"
                if item.status.value in {"confirmed", "published"}
                else "DRAFT"
            ),
            runtime_status=(
                "SUPPORTED"
                if any(
                    item.id in pattern.required_metrics
                    for pattern in package.analysis_patterns
                )
                else "NOT_YET_SUPPORTED"
            ),
            governance_status=(
                "REVIEWED_WITH_ASSUMPTIONS"
                if item.status.value in {"confirmed", "published"} and item.decisions
                else "REVIEWED"
                if item.status.value in {"confirmed", "published"}
                else "UNREVIEWED"
            ),
            source_anchor=None,
        )
        for index, item in enumerate(package.metrics, start=1)
    )
    return StudioAuthoringProjectionV1(
        requirements=requirements,
        metric_candidates=metrics,
        source_mode="CANONICAL_FALLBACK",
    )


def build_authoring_projection(
    *,
    package: OntologyPackage,
    intake: Any,
    scenario_dir: Path,
) -> StudioAuthoringProjectionV1:
    """Build an exact source projection, or an explicitly non-source fallback.

    The fallback is useful for installed solutions that have a canonical package but
    no product-supported transcription adapter. It never claims source support.
    """
    return _transcription_projection(
        package=package,
        intake=intake,
        scenario_dir=scenario_dir,
    ) or _canonical_projection(package)
