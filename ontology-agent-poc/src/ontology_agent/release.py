from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .contracts import (
    ImmutableVersionError,
    PublicationError,
    PublishedReleaseHandle,
    ReleaseRef,
    SafeSourceAsset,
)
from .durable_lifecycle import LifecycleStorePort, configured_lifecycle_store
from .io import canonical_dict, file_checksum, package_checksum, sha256_value, write_json
from .models import FormulaNode, OntologyPackage, ValidationReport
from .rdf_projection import write_graph_artifacts
from .validation import failed_checks, validate_semantic_package


RELEASE_SCHEMA = "ontology-release/v1"


@dataclass(frozen=True, slots=True)
class ReleaseBundle:
    ref: ReleaseRef
    path: Path
    manifest: dict[str, Any]
    package: OntologyPackage
    semantic_validation: dict[str, Any]
    capability_requirements: dict[str, Any]


def _formula_operations(node: FormulaNode) -> set[str]:
    operations = {node.op}
    for child in node.args:
        operations.update(_formula_operations(child))
    return operations


def capability_requirements(package: OntologyPackage) -> dict[str, Any]:
    """Describe what a consumer must support without naming an implementation."""

    return {
        "contract": "ontology-runtime-requirements/v1",
        "analysis_operations": sorted(
            {pattern.operation for pattern in package.analysis_patterns}
        ),
        "formula_operations": sorted(
            {
                operation
                for metric in package.metrics
                for operation in _formula_operations(metric.formula)
            }
        ),
        "source_protocols": sorted(
            {source.protocol for source in package.data_sources}
        ),
        "binding_transformations": sorted(
            {binding.transformation for binding in package.bindings}
        ),
        "physical_data_types": sorted(
            {
                field.data_type
                for source in package.data_sources
                for table in source.tables
                for field in table.fields
            }
        ),
    }


def _validation_signature(report: ValidationReport) -> dict[str, Any]:
    return {
        "package_id": report.package_id,
        "package_version": report.package_version,
        "package_checksum": report.package_checksum,
        "status": report.status,
        "checks": [
            {
                "check_id": check.check_id,
                "category": check.category,
                "status": check.status,
                "message": check.message,
                "details": check.details,
            }
            for check in report.checks
        ],
    }


def _safe_sources(
    package: OntologyPackage,
    supplied: tuple[SafeSourceAsset | Mapping[str, Any], ...],
) -> list[dict[str, Any]]:
    if supplied:
        return [
            SafeSourceAsset.model_validate(item).model_dump(
                mode="json", exclude_none=True
            )
            for item in supplied
        ]
    return [
        SafeSourceAsset(
            source_id=source.id,
            source_type=source.source_type,
            title=source.title,
            safe_locator=source.locator,
            trust=source.trust,
        ).model_dump(mode="json", exclude_none=True)
        for source in package.sources
    ]


def _artifact_inventory(staging: Path) -> dict[str, str]:
    excluded = {"manifest.json", "artifact-inventory.json"}
    return {
        path.relative_to(staging).as_posix(): file_checksum(path)
        for path in sorted(staging.rglob("*"))
        if path.is_file() and path.name not in excluded
    }


def _manifest_payload(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in manifest.items()
        if key != "release_checksum"
    }


def _read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise PublicationError(f"Release is missing {label}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublicationError(f"Release has unreadable {label}") from exc
    if not isinstance(value, dict):
        raise PublicationError(f"Release has invalid {label}")
    return value


def verify_release_directory(path: Path, expected: ReleaseRef | None = None) -> ReleaseBundle:
    path = path.resolve()
    manifest = _read_json(path / "manifest.json", "manifest")
    if manifest.get("schema_version") != RELEASE_SCHEMA:
        raise PublicationError("Release schema is unsupported")
    inventory = _read_json(path / "artifact-inventory.json", "artifact inventory")
    if manifest.get("artifact_inventory_checksum") != sha256_value(inventory):
        raise PublicationError("Release artifact inventory checksum mismatch")

    actual_artifacts = {
        artifact.relative_to(path).as_posix()
        for artifact in path.rglob("*")
        if artifact.is_file()
        and artifact.name not in {"manifest.json", "artifact-inventory.json"}
    }
    if actual_artifacts != set(inventory):
        raise PublicationError("Release artifact inventory is not complete")
    for relative, checksum in inventory.items():
        if not isinstance(relative, str) or not isinstance(checksum, str):
            raise PublicationError("Release artifact inventory is malformed")
        candidate = PurePosixPath(relative)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise PublicationError("Release artifact path is unsafe")
        artifact = (path / relative).resolve()
        if not artifact.is_relative_to(path) or not artifact.is_file():
            raise PublicationError(f"Release artifact is missing: {relative}")
        if file_checksum(artifact) != checksum:
            raise PublicationError(f"Release artifact checksum mismatch: {relative}")

    actual_checksum = sha256_value(_manifest_payload(manifest))
    if manifest.get("release_checksum") != actual_checksum:
        raise PublicationError("Release checksum mismatch")
    ref = ReleaseRef(
        package_id=str(manifest.get("package_id", "")),
        version=str(manifest.get("version", "")),
        checksum=actual_checksum,
    )
    if expected is not None and ref != expected:
        raise PublicationError("Release identity does not match the requested reference")

    package = OntologyPackage.model_validate(_read_json(path / "package.json", "package"))
    if package.package_id != ref.package_id or package.version != ref.version:
        raise PublicationError("Release package identity does not match its manifest")
    if package_checksum(package) != manifest.get("package_checksum"):
        raise PublicationError("Release package checksum mismatch")
    semantic_validation = _read_json(
        path / "semantic-validation.json", "semantic validation"
    )
    requirements = _read_json(
        path / "capability-requirements.json", "capability requirements"
    )
    if sha256_value(semantic_validation) != manifest.get("semantic_validation_checksum"):
        raise PublicationError("Release semantic validation checksum mismatch")
    if sha256_value(requirements) != manifest.get("capability_requirements_checksum"):
        raise PublicationError("Release capability requirements checksum mismatch")
    if semantic_validation.get("status") != "PASS":
        raise PublicationError("Release semantic validation is not PASS")
    if requirements != capability_requirements(package):
        raise PublicationError("Release capability requirements do not match the package")
    return ReleaseBundle(
        ref=ref,
        path=path,
        manifest=manifest,
        package=package,
        semantic_validation=semantic_validation,
        capability_requirements=requirements,
    )


class StudioReleases:
    """Deep Studio boundary for deterministic, semantic-only publication."""

    def __init__(
        self,
        root: Path,
        *,
        lifecycle_store: LifecycleStorePort | None = None,
    ):
        self.root = root.resolve()
        self.lifecycle_store = lifecycle_store or configured_lifecycle_store()

    def _path(self, package_id: str, version: str) -> Path:
        return self.root / package_id / version

    def publish(
        self,
        package: OntologyPackage,
        *,
        safe_sources: tuple[SafeSourceAsset | Mapping[str, Any], ...] = (),
        limitations: tuple[str, ...] = (),
    ) -> PublishedReleaseHandle:
        validation = validate_semantic_package(package)
        if validation.status != "PASS":
            failures = ", ".join(
                check.check_id for check in failed_checks(validation)
            )
            raise PublicationError(
                f"Semantic publication blocked by validation failures: {failures}"
            )

        destination = self._path(package.package_id, package.version)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=f".{package.version}-", dir=destination.parent
        ) as temporary:
            staging = Path(temporary)
            validation_signature = _validation_signature(validation)
            requirements = capability_requirements(package)
            write_json(staging / "package.json", canonical_dict(package))
            write_json(staging / "semantic-validation.json", validation_signature)
            write_json(staging / "capability-requirements.json", requirements)
            write_graph_artifacts(package, staging / "graph")
            artifacts = _artifact_inventory(staging)
            write_json(staging / "artifact-inventory.json", artifacts)
            manifest = {
                "schema_version": RELEASE_SCHEMA,
                "package_id": package.package_id,
                "version": package.version,
                "package_checksum": package_checksum(package),
                "semantic_validation_checksum": sha256_value(validation_signature),
                "capability_requirements_checksum": sha256_value(requirements),
                "artifact_inventory_checksum": sha256_value(artifacts),
                "safe_sources": _safe_sources(package, safe_sources),
                "limitations": list(limitations),
            }
            release_checksum = sha256_value(manifest)
            manifest["release_checksum"] = release_checksum
            write_json(staging / "manifest.json", manifest)

            ref = ReleaseRef(
                package_id=package.package_id,
                version=package.version,
                checksum=release_checksum,
            )
            if destination.exists():
                try:
                    existing = verify_release_directory(destination, ref)
                except PublicationError as exc:
                    raise ImmutableVersionError(
                        f"Version {package.version} already exists with different or invalid content"
                    ) from exc
                if self.lifecycle_store is not None:
                    self.lifecycle_store.persist_release(existing.ref, destination)
                return PublishedReleaseHandle(
                    ref=existing.ref,
                    validation_status="PASS",
                    validation_check_count=len(validation.checks),
                    idempotent=True,
                    artifacts=tuple(sorted(artifacts)),
                    path=destination,
                )
            try:
                os.replace(staging, destination)
            except OSError as exc:
                raise PublicationError(
                    f"Could not atomically publish semantic release: {exc}"
                ) from exc

        verified = verify_release_directory(destination, ref)
        if self.lifecycle_store is not None:
            self.lifecycle_store.persist_release(verified.ref, destination)
        return PublishedReleaseHandle(
            ref=verified.ref,
            validation_status="PASS",
            validation_check_count=len(validation.checks),
            idempotent=False,
            artifacts=tuple(sorted(artifacts)),
            path=destination,
        )

    def resolve(self, package_id: str, version: str) -> ReleaseRef:
        path = self._path(package_id, version)
        if not path.is_dir() and self.lifecycle_store is not None:
            ref = self.lifecycle_store.resolve_release(package_id, version)
            self.lifecycle_store.materialize_release(ref, path)
        return verify_release_directory(path).ref

    def load(self, ref: ReleaseRef) -> ReleaseBundle:
        path = self._path(ref.package_id, ref.version)
        if not path.is_dir() and self.lifecycle_store is not None:
            self.lifecycle_store.materialize_release(ref, path)
        return verify_release_directory(path, ref)

    def list(self, package_id: str) -> tuple[ReleaseRef, ...]:
        package_root = self.root / package_id
        if not package_root.is_dir():
            return ()
        refs = [
            verify_release_directory(path).ref
            for path in package_root.iterdir()
            if path.is_dir() and (path / "manifest.json").is_file()
        ]
        if self.lifecycle_store is not None:
            refs.extend(self.lifecycle_store.list_releases(package_id))
        unique = {ref.checksum: ref for ref in refs}
        return tuple(
            sorted(unique.values(), key=lambda item: _semver_key(item.version), reverse=True)
        )


def _semver_key(value: str) -> tuple[int, int, int]:
    try:
        major, minor, patch = (int(part) for part in value.split("."))
        return major, minor, patch
    except ValueError:
        return 0, 0, 0
