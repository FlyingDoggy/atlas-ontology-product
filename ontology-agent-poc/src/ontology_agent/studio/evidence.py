from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Any, Literal

from pydantic import Field, model_validator

from ..contracts import Sha256
from ..io import sha256_value
from ..models import StrictModel
from .source_projection import SourceProjectionAnchorV1


class EvidenceNormalizationError(RuntimeError):
    """Selected source material cannot be normalized without losing identity."""


class UnsupportedEvidenceSourceV1(StrictModel):
    contract: Literal["unsupported-evidence-source/v1"] = (
        "unsupported-evidence-source/v1"
    )
    source_id: str = Field(min_length=1, max_length=255)
    source_checksum: Sha256
    source_kind: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=1000)


class EvidenceFragmentV1(StrictModel):
    contract: Literal["evidence-fragment/v1"] = "evidence-fragment/v1"
    fragment_id: str = Field(pattern=r"^evidence\.[0-9a-f]{32}$")
    source_id: str = Field(min_length=1, max_length=255)
    source_version_id: str | None = Field(default=None, max_length=255)
    source_checksum: Sha256
    source_kind: str = Field(min_length=1, max_length=100)
    content_kind: Literal["TEXT_RANGE", "XLSX_ROW"]
    content: str = Field(min_length=1, max_length=8000)
    anchor: SourceProjectionAnchorV1
    truncated: bool = False

    @model_validator(mode="after")
    def exact_identity_matches_anchor(self) -> EvidenceFragmentV1:
        if (
            self.anchor.source_id != self.source_id
            or self.anchor.source_checksum != self.source_checksum
        ):
            raise ValueError("Evidence fragment and anchor identity differ")
        return self


class EvidenceBundleV1(StrictModel):
    contract: Literal["evidence-bundle/v1"] = "evidence-bundle/v1"
    workspace_id: str = Field(min_length=1, max_length=255)
    source_set_digest: Sha256
    fragments: tuple[EvidenceFragmentV1, ...]
    unsupported_sources: tuple[UnsupportedEvidenceSourceV1, ...]
    bundle_checksum: Sha256

    @model_validator(mode="after")
    def checksum_matches_content(self) -> EvidenceBundleV1:
        unsigned = self.model_dump(mode="json", exclude={"bundle_checksum"})
        if sha256_value(unsigned) != self.bundle_checksum:
            raise ValueError("Evidence bundle checksum mismatch")
        return self


def _record(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return dict(value)
    return {}


def _assets(intake: Any) -> tuple[dict[str, Any], ...]:
    payload = _record(intake)
    values = payload.get("assets") or payload.get("source_files") or ()
    assets = tuple(_record(item) for item in values)
    return tuple(
        sorted(
            assets,
            key=lambda item: (
                str(item.get("kind") or item.get("role") or ""),
                str(item.get("asset_id") or item.get("file_id") or ""),
                str(item.get("source_version_id") or ""),
            ),
        )
    )


def _identity(asset: dict[str, Any]) -> tuple[str, str | None, str, str]:
    source_id = str(
        asset.get("asset_id") or asset.get("file_id") or asset.get("source_id") or ""
    )
    source_version_id = (
        str(asset["source_version_id"]) if asset.get("source_version_id") else None
    )
    checksum = str(asset.get("checksum") or asset.get("sha256") or "")
    kind = str(asset.get("kind") or asset.get("role") or "other")
    if (
        not source_id
        or not re.fullmatch(r"[0-9a-f]{64}", checksum)
        or not kind
    ):
        raise EvidenceNormalizationError("Selected source identity is incomplete")
    return source_id, source_version_id, checksum, kind


def _fragment(
    *,
    source_id: str,
    source_version_id: str | None,
    source_checksum: str,
    source_kind: str,
    content_kind: Literal["TEXT_RANGE", "XLSX_ROW"],
    content: str,
    locator: str,
    line_number: int,
    sheet_name: str | None = None,
    cell_range: str | None = None,
    truncated: bool = False,
) -> EvidenceFragmentV1:
    normalized = content[:8000]
    clipped = truncated or len(content) > len(normalized)
    anchor = SourceProjectionAnchorV1(
        source_id=source_id,
        source_checksum=source_checksum,
        locator_kind=content_kind,
        locator=locator,
        line_number=line_number,
        sheet_name=sheet_name,
        cell_range=cell_range,
        snippet_checksum=sha256_value(
            {
                "source_id": source_id,
                "source_checksum": source_checksum,
                "locator": locator,
                "content": normalized,
            }
        ),
    )
    identity = {
        "source_id": source_id,
        "source_version_id": source_version_id,
        "source_checksum": source_checksum,
        "content_kind": content_kind,
        "locator": locator,
        "content": normalized,
    }
    return EvidenceFragmentV1(
        fragment_id="evidence." + sha256_value(identity)[:32],
        source_id=source_id,
        source_version_id=source_version_id,
        source_checksum=source_checksum,
        source_kind=source_kind,
        content_kind=content_kind,
        content=normalized,
        anchor=anchor,
        truncated=clipped,
    )


def _text_fragments(
    asset: dict[str, Any],
    *,
    lines_per_fragment: int,
) -> tuple[EvidenceFragmentV1, ...] | None:
    source_id, version_id, checksum, kind = _identity(asset)
    inline = asset.get("content_text")
    if inline is not None:
        if not isinstance(inline, str):
            raise EvidenceNormalizationError("Registered text source is not text")
        if hashlib.sha256(inline.encode("utf-8")).hexdigest() != checksum:
            raise EvidenceNormalizationError("Registered text checksum mismatch")
        lines = tuple(
            {"line_number": index, "text": line}
            for index, line in enumerate(inline.splitlines(), start=1)
        )
    else:
        preview = _record(asset.get("source_preview"))
        if not preview:
            return None
        if preview.get("sheets"):
            return None
        if (
            preview.get("contract") != "studio-source-preview/v1"
            or preview.get("status") != "PARSED"
            or preview.get("content_checksum") != checksum
            or (version_id and preview.get("source_version_id") != version_id)
        ):
            raise EvidenceNormalizationError("Text preview identity mismatch")
        preview_lines = preview.get("text_lines") or ()
        lines_list: list[dict[str, Any]] = []
        for raw in preview_lines:
            item = _record(raw)
            number = item.get("line_number")
            text = item.get("text")
            expected = item.get("snippet_checksum")
            if not isinstance(number, int) or number < 1 or not isinstance(text, str):
                raise EvidenceNormalizationError("Text preview line is invalid")
            exact = {
                "source_version_id": version_id,
                "content_checksum": checksum,
                "line_number": number,
                "text": text,
            }
            if expected != sha256_value(exact):
                raise EvidenceNormalizationError("Text preview line checksum mismatch")
            lines_list.append({"line_number": number, "text": text})
        lines = tuple(lines_list)
    output: list[EvidenceFragmentV1] = []
    for offset in range(0, len(lines), lines_per_fragment):
        chunk = lines[offset : offset + lines_per_fragment]
        if not chunk:
            continue
        content = "\n".join(str(item["text"]) for item in chunk).strip()
        if not content:
            continue
        first = int(chunk[0]["line_number"])
        last = int(chunk[-1]["line_number"])
        output.append(
            _fragment(
                source_id=source_id,
                source_version_id=version_id,
                source_checksum=checksum,
                source_kind=kind,
                content_kind="TEXT_RANGE",
                content=content,
                locator=f"lines={first}-{last}",
                line_number=first,
                truncated=bool(
                    _record(asset.get("source_preview")).get("limitation")
                    and offset + lines_per_fragment >= len(lines)
                ),
            )
        )
    return tuple(output)


def _xlsx_sheet_priority(source_kind: str, sheet_name: str) -> int:
    kind = source_kind.casefold()
    name = sheet_name.casefold()
    is_reference = any(
        marker in name
        for marker in (
            "reference",
            "example",
            "guide",
            "instruction",
            "submission",
            "参考",
            "示例",
            "说明",
            "指南",
        )
    )
    if "requirement" in kind:
        matches = any(
            keyword in name
            for keyword in ("requirement", "process", "business", "需求", "流程", "业务")
        )
        return 0 if matches and not is_reference else 2 if is_reference else 1
    if "metric" in kind or "indicator" in kind:
        matches = any(
            keyword in name
            for keyword in ("metric", "indicator", "kpi", "measure", "指标", "口径")
        )
        return 0 if matches and not is_reference else 2 if is_reference else 1
    if "model" in kind or "schema" in kind:
        matches = any(
            keyword in name
            for keyword in (
                "model",
                "schema",
                "overview",
                "entity",
                "table",
                "数据模型",
                "模型",
                "表",
            )
        )
        return 0 if matches and not is_reference else 2 if is_reference else 1
    if "dictionary" in kind or "sample" in kind:
        # A dictionary commonly names sheets after physical tables rather than
        # using the word "dictionary". Treat every non-guide/non-overview sheet
        # as a detail sheet and sample them fairly below.
        is_summary = is_reference or "overview" in name or "概览" in name
        return 2 if is_summary else 0
    return 1


def _xlsx_fragments(asset: dict[str, Any]) -> tuple[EvidenceFragmentV1, ...] | None:
    source_id, version_id, checksum, kind = _identity(asset)
    preview = _record(asset.get("source_preview"))
    if not preview:
        return None
    if (
        not version_id
        or preview.get("contract") != "studio-source-preview/v1"
        or preview.get("status") != "PARSED"
        or preview.get("source_version_id") != version_id
        or preview.get("content_checksum") != checksum
    ):
        raise EvidenceNormalizationError("XLSX preview identity mismatch")
    sheets = tuple(_record(raw) for raw in preview.get("sheets") or ())
    sheet_outputs: list[tuple[int, int, tuple[EvidenceFragmentV1, ...]]] = []
    for sheet_index, sheet in enumerate(sheets):
        sheet_name = sheet.get("sheet_name")
        if not isinstance(sheet_name, str) or not sheet_name:
            raise EvidenceNormalizationError("XLSX sheet identity is invalid")
        rows: dict[int, list[tuple[str, str]]] = defaultdict(list)
        for raw_cell in sheet.get("cells") or ():
            cell = _record(raw_cell)
            coordinate = cell.get("cell")
            match = re.fullmatch(r"([A-Z]+)([1-9][0-9]*)", str(coordinate))
            if match is None:
                raise EvidenceNormalizationError("XLSX cell coordinate is invalid")
            display = cell.get("display_value")
            formula = cell.get("raw_formula")
            exact = {
                "source_version_id": version_id,
                "content_checksum": checksum,
                "sheet": sheet_name,
                "cell": coordinate,
                "raw_formula": formula,
                "display_value": display,
            }
            if cell.get("snippet_checksum") != sha256_value(exact):
                raise EvidenceNormalizationError("XLSX cell checksum mismatch")
            rendered = str(display) if formula is None else f"{display!s} [formula: {formula}]"
            rows[int(match.group(2))].append((str(coordinate), rendered))
        projected_rows: list[EvidenceFragmentV1] = []
        for row_number, cells in sorted(rows.items()):
            cells.sort(key=lambda item: item[0])
            content = " | ".join(f"{coordinate}={value}" for coordinate, value in cells)
            if not content:
                continue
            cell_range = f"{cells[0][0]}:{cells[-1][0]}"
            projected_rows.append(
                _fragment(
                    source_id=source_id,
                    source_version_id=version_id,
                    source_checksum=checksum,
                    source_kind=kind,
                    content_kind="XLSX_ROW",
                    content=content,
                    locator=f"sheet={sheet_name};row={row_number}",
                    line_number=row_number,
                    sheet_name=sheet_name,
                    cell_range=cell_range,
                    truncated=bool(sheet.get("truncated")),
                )
            )
        sheet_outputs.append(
            (
                _xlsx_sheet_priority(kind, sheet_name),
                sheet_index,
                tuple(projected_rows),
            )
        )

    # Within one logical priority, sample rows across sheets instead of allowing
    # the first wide table to hide every later table from the global budget.
    output: list[EvidenceFragmentV1] = []
    for priority in sorted({item[0] for item in sheet_outputs}):
        group = [
            fragments
            for _, _, fragments in sorted(
                (item for item in sheet_outputs if item[0] == priority),
                key=lambda item: item[1],
            )
        ]
        group_depth = max((len(fragments) for fragments in group), default=0)
        for row_index in range(group_depth):
            for fragments in group:
                if row_index < len(fragments):
                    output.append(fragments[row_index])
    return tuple(output)


def normalize_evidence(
    intake: Any,
    *,
    workspace_id: str,
    max_fragments: int = 256,
    max_total_chars: int = 500_000,
    lines_per_fragment: int = 20,
) -> EvidenceBundleV1:
    """Turn exact selected source versions into bounded, traceable model input."""
    if (
        not 1 <= max_fragments <= 2_000
        or not 1 <= lines_per_fragment <= 100
        or not 1 <= max_total_chars <= 10_000_000
    ):
        raise EvidenceNormalizationError("Evidence normalization limits are invalid")
    fragments: list[EvidenceFragmentV1] = []
    unsupported: list[UnsupportedEvidenceSourceV1] = []
    source_identities: list[dict[str, Any]] = []
    projected_sources: list[tuple[EvidenceFragmentV1, ...]] = []
    for asset in _assets(intake):
        source_id, version_id, checksum, kind = _identity(asset)
        source_identities.append(
            {
                "source_id": source_id,
                "source_version_id": version_id,
                "source_checksum": checksum,
                "source_kind": kind,
            }
        )
        projected = _text_fragments(asset, lines_per_fragment=lines_per_fragment)
        if projected is None:
            projected = _xlsx_fragments(asset)
        if not projected:
            unsupported.append(
                UnsupportedEvidenceSourceV1(
                    source_id=source_id,
                    source_checksum=checksum,
                    source_kind=kind,
                    reason="Exact source is registered, but no supported normalized preview is available.",
                )
            )
            continue
        projected_sources.append(projected)

    # Evidence is sampled across sources, not source-by-source. This prevents one
    # large workbook from exhausting the global budget before requirements,
    # metrics, or executable logic receive any representation.
    total_chars = 0
    max_source_fragments = max((len(items) for items in projected_sources), default=0)
    for fragment_index in range(max_source_fragments):
        if len(fragments) >= max_fragments:
            break
        for projected in projected_sources:
            if len(fragments) >= max_fragments:
                break
            if fragment_index >= len(projected):
                continue
            fragment = projected[fragment_index]
            if total_chars + len(fragment.content) > max_total_chars:
                continue
            fragments.append(fragment)
            total_chars += len(fragment.content)
    source_set_digest = sha256_value(source_identities)
    unsigned = {
        "contract": "evidence-bundle/v1",
        "workspace_id": workspace_id,
        "source_set_digest": source_set_digest,
        "fragments": tuple(fragment.model_dump(mode="json") for fragment in fragments),
        "unsupported_sources": tuple(item.model_dump(mode="json") for item in unsupported),
    }
    return EvidenceBundleV1(**unsigned, bundle_checksum=sha256_value(unsigned))
