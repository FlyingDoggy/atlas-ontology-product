from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, ValidationInfo, model_validator

from ..models import (
    Actor,
    AnalysisPattern,
    BusinessQuestion,
    DataSource,
    Decision,
    Dimension,
    Entity,
    GovernedObject,
    JoinContract,
    Metric,
    OntologyPackage,
    PhysicalBinding,
    Policy,
    Process,
    Property,
    Relationship,
    Rule,
    Scenario,
    SqlContract,
    SourceReference,
    Status,
    StrictModel,
)
from ..io import sha256_value


PackageCollection = Literal[
    "scenario",
    "sources",
    "decisions",
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
]

_MODEL_BY_COLLECTION: dict[str, type[StrictModel]] = {
    "scenario": Scenario,
    "sources": SourceReference,
    "decisions": Decision,
    "actors": Actor,
    "processes": Process,
    "entities": Entity,
    "properties": Property,
    "relationships": Relationship,
    "dimensions": Dimension,
    "rules": Rule,
    "metrics": Metric,
    "data_sources": DataSource,
    "bindings": PhysicalBinding,
    "joins": JoinContract,
    "sql_contracts": SqlContract,
    "analysis_patterns": AnalysisPattern,
    "policies": Policy,
    "questions": BusinessQuestion,
}


def package_collection_schemas(
    collections: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    unknown = sorted(set(collections) - set(_MODEL_BY_COLLECTION))
    if unknown:
        raise ValueError("Unknown package collections: " + ", ".join(unknown))
    return {
        collection: _MODEL_BY_COLLECTION[collection].model_json_schema()
        for collection in collections
    }


class PackageDraftOperation(StrictModel):
    """One kind-exact package mutation; payloads are never accepted as arbitrary JSON."""

    action: Literal["UPSERT", "CONFIRM", "DEPRECATE"]
    collection: PackageCollection
    object_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    payload: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_typed_payload(self, info: ValidationInfo) -> PackageDraftOperation:
        if self.action == "DEPRECATE":
            if self.collection == "scenario":
                raise ValueError("The required package scenario cannot be deprecated")
            if self.payload is not None:
                raise ValueError("DEPRECATE does not accept a replacement payload")
            return self
        if self.action == "CONFIRM":
            if self.collection in {"sources", "decisions"}:
                raise ValueError(
                    "Exact sources and decision records do not use asset confirmation"
                )
            if self.payload is None:
                raise ValueError("CONFIRM requires an exact review receipt")
            AssetConfirmation.model_validate(self.payload, context=info.context)
            return self
        if self.payload is None:
            raise ValueError("UPSERT requires a typed replacement payload")
        parsed = _MODEL_BY_COLLECTION[self.collection].model_validate(
            self.payload,
            context=info.context,
        )
        if getattr(parsed, "id", None) != self.object_id:
            raise ValueError("Package operation identity does not match its payload")
        # Authoring and extraction can propose content, but they cannot manufacture
        # review authority by retaining or submitting a confirmed/published status.
        return self


class AssetConfirmation(StrictModel):
    reviewer: str = Field(min_length=1, max_length=200)
    reviewed_at: datetime
    asset_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")


def _dependency_paths(value: Any, target: str, path: str = "") -> list[str]:
    if isinstance(value, str):
        return [path] if value == target else []
    if isinstance(value, dict):
        return [
            dependency
            for key, item in value.items()
            for dependency in _dependency_paths(item, target, f"{path}.{key}" if path else key)
        ]
    if isinstance(value, (list, tuple)):
        return [
            dependency
            for index, item in enumerate(value)
            for dependency in _dependency_paths(item, target, f"{path}[{index}]")
        ]
    return []


def _blocking_dependencies(
    values: dict[str, Any],
    *,
    collection: str,
    object_id: str,
) -> list[str]:
    dependencies: list[str] = []
    for key, value in values.items():
        if key == collection:
            value = tuple(
                item
                for item in value
                if getattr(item, "id", None) != object_id
                and not (isinstance(item, dict) and item.get("id") == object_id)
            )
        dependencies.extend(_dependency_paths(value, object_id, key))
    return sorted(set(dependencies))


class PackageDraftOperationsV1(StrictModel):
    contract: Literal["studio-package-operations/v1"] = (
        "studio-package-operations/v1"
    )
    expected_revision: int = Field(ge=1)
    operations: tuple[PackageDraftOperation, ...] = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def reject_duplicate_targets(self) -> PackageDraftOperationsV1:
        targets = tuple((item.collection, item.object_id) for item in self.operations)
        if len(targets) != len(set(targets)):
            raise ValueError("One request cannot mutate the same package object twice")
        return self


class ReviewFinalizationOperationsV1(StrictModel):
    """Internal UPSERT+CONFIRM command formed only by the review authority.

    The public authoring API intentionally cannot construct this contract.
    """

    contract: Literal["studio-review-finalization-operations/v1"] = (
        "studio-review-finalization-operations/v1"
    )
    expected_revision: int = Field(ge=1)
    operations: tuple[PackageDraftOperation, ...] = Field(min_length=1, max_length=1024)

    @model_validator(mode="after")
    def exact_review_pairs(self) -> ReviewFinalizationOperationsV1:
        targets: set[tuple[str, str]] = set()
        index = 0
        while index < len(self.operations):
            upsert = self.operations[index]
            target = (upsert.collection, upsert.object_id)
            if upsert.action != "UPSERT":
                raise ValueError("Review finalization starts each target with UPSERT")
            if upsert.collection in {"sources", "decisions"}:
                index += 1
            else:
                if index + 1 >= len(self.operations):
                    raise ValueError("Governed review finalization requires confirmation")
                confirm = self.operations[index + 1]
                if (
                    confirm.action != "CONFIRM"
                    or target != (confirm.collection, confirm.object_id)
                ):
                    raise ValueError("Review finalization must pair UPSERT then CONFIRM")
                index += 2
            if target in targets:
                raise ValueError("Review finalization cannot mutate one target twice")
            targets.add(target)
        return self


def apply_package_operations(
    package: OntologyPackage,
    operations: tuple[PackageDraftOperation, ...],
) -> OntologyPackage:
    values = package.model_dump(mode="python")
    for operation in operations:
        model = _MODEL_BY_COLLECTION[operation.collection]
        singular = operation.collection == "scenario"
        current = (
            [values[operation.collection]]
            if singular
            else list(values[operation.collection])
        )
        index = next(
            (
                position
                for position, item in enumerate(current)
                if getattr(item, "id", None) == operation.object_id
                or (isinstance(item, dict) and item.get("id") == operation.object_id)
            ),
            None,
        )
        if singular and index is None:
            raise ValueError(
                "Scenario operations must preserve the package scenario identity"
            )
        if operation.action == "UPSERT":
            replacement = model.model_validate(operation.payload)
            if isinstance(replacement, GovernedObject) and replacement.status not in {
                Status.PROPOSED,
                Status.NEEDS_CLARIFICATION,
            }:
                replacement = replacement.model_copy(update={"status": Status.PROPOSED})
            if index is None:
                current.append(replacement)
            else:
                current[index] = replacement
        elif operation.action == "CONFIRM":
            if index is None:
                raise ValueError(
                    f"Cannot confirm missing {operation.collection} object "
                    f"{operation.object_id}"
                )
            existing = model.model_validate(current[index])
            if not isinstance(existing, GovernedObject):
                raise ValueError(
                    "Only governed ontology assets can use asset confirmation"
                )
            receipt = AssetConfirmation.model_validate(operation.payload)
            checksum = sha256_value(existing.model_dump(mode="json"))
            if checksum != receipt.asset_checksum:
                raise ValueError("Confirmation receipt does not match the exact asset")
            if existing.status not in {Status.PROPOSED, Status.NEEDS_CLARIFICATION}:
                raise ValueError("Only an unconfirmed draft asset can be confirmed")
            current[index] = existing.model_copy(update={"status": Status.CONFIRMED})
        else:
            if index is None:
                raise ValueError(
                    f"Cannot deprecate missing {operation.collection} object "
                    f"{operation.object_id}"
                )
            dependencies = _blocking_dependencies(
                values,
                collection=operation.collection,
                object_id=operation.object_id,
            )
            if dependencies:
                preview = ", ".join(dependencies[:8])
                suffix = "…" if len(dependencies) > 8 else ""
                raise ValueError(
                    f"Cannot deprecate {operation.object_id}; active references remain: "
                    f"{preview}{suffix}"
                )
            # The immutable operation is the tombstone. The materialized candidate
            # excludes the object so deprecated contracts cannot leak into runtime.
            current.pop(index)
        values[operation.collection] = current[0] if singular else tuple(current)
    return OntologyPackage.model_validate(values)


def package_collection_items(
    package: OntologyPackage,
    collection: PackageCollection,
) -> tuple[StrictModel, ...]:
    """Expose singular and plural package assets through one typed boundary."""

    value = getattr(package, collection)
    return (value,) if collection == "scenario" else tuple(value)
