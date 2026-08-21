from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from ..contracts import Sha256
from ..io import package_checksum, sha256_value
from ..models import OntologyPackage, StrictModel
from .source_projection import StudioAuthoringProjectionV1


class StudioWorkbenchV1(StrictModel):
    """One exact Studio read model; the browser never invents ontology objects."""

    contract: Literal["studio-workbench/v1"] = "studio-workbench/v1"
    persistence: Literal["legacy-compatibility", "postgresql-s3"]
    package_checksum: Sha256
    asset_checksums: dict[str, Sha256]
    package: OntologyPackage
    workspace: dict[str, Any]
    intake: dict[str, Any]
    authoring: StudioAuthoringProjectionV1
    revisions: tuple[dict[str, Any], ...] = Field(max_length=10_000)
    semantic_change_requests: tuple[dict[str, Any], ...] = Field(
        default=(), max_length=10_000
    )


def build_studio_workbench(
    *,
    persistence: Literal["legacy-compatibility", "postgresql-s3"],
    package: OntologyPackage,
    workspace: Any,
    intake: Any,
    authoring: StudioAuthoringProjectionV1,
    revisions: tuple[Any, ...],
    semantic_change_requests: tuple[Any, ...] = (),
) -> StudioWorkbenchV1:
    intake_payload = (
        intake.model_dump(mode="json")
        if hasattr(intake, "model_dump")
        else dict(intake)
    )
    return StudioWorkbenchV1(
        persistence=persistence,
        package_checksum=package_checksum(package),
        asset_checksums={
            f"{collection}:{item.id}": sha256_value(item.model_dump(mode="json"))
            for collection in (
                "actors",
                "processes",
                "entities",
                "properties",
                "relationships",
                "dimensions",
                "rules",
                "metrics",
                "data_sources",
                "bindings",
                "joins",
                "sql_contracts",
                "analysis_patterns",
                "policies",
                "questions",
            )
            for item in getattr(package, collection)
        },
        package=package,
        workspace=workspace.model_dump(mode="json"),
        intake=intake_payload,
        authoring=authoring,
        revisions=tuple(item.model_dump(mode="json") for item in revisions),
        semantic_change_requests=tuple(
            item.model_dump(mode="json") for item in semantic_change_requests
        ),
    )
