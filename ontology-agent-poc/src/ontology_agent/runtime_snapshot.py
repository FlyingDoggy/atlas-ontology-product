from __future__ import annotations

import importlib.metadata
import json
import platform
from pathlib import Path
from typing import Any, Mapping

from .contracts import PublicationError, ReleaseRef, RuntimeBindingSpec, VerifiedSnapshot
from .io import DEFAULT_PROJECT_ROOT, file_checksum, package_checksum, sha256_value
from .release import verify_release_directory
from .scenario import ScenarioAdapter, default_scenario_adapters


RUNTIME_SCHEMA = "bound-runtime/v1"


def _read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise PublicationError(f"Runtime snapshot is missing {label}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublicationError(f"Runtime snapshot has unreadable {label}") from exc
    if not isinstance(value, dict):
        raise PublicationError(f"Runtime snapshot has invalid {label}")
    return value


def runtime_identity() -> dict[str, Any]:
    dependencies: dict[str, str] = {}
    for distribution in ("duckdb", "pydantic", "pyshacl", "rdflib"):
        try:
            dependencies[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            dependencies[distribution] = "missing"
    return {
        "contract": "ontology-agent-runtime/v1",
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "system": platform.system(),
        "machine": platform.machine(),
        "dependencies": dependencies,
    }


def adapter_manifest(
    project_root: Path = DEFAULT_PROJECT_ROOT,
    *,
    adapter: ScenarioAdapter | None = None,
) -> dict[str, Any]:
    selected = adapter or default_scenario_adapters().resolve("adt-reference", "1.0.0")
    return dict(selected.build_manifest(project_root))


def dataset_identity(
    resource_paths: Mapping[str, Path],
    *,
    dataset_manifest_path: Path,
) -> dict[str, Any]:
    if not dataset_manifest_path.is_file():
        raise PublicationError("Runtime dataset manifest is missing")
    try:
        declared = json.loads(dataset_manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublicationError("Runtime dataset manifest is unreadable") from exc
    return {
        "dataset_id": declared.get("dataset_id"),
        "manifest_sha256": file_checksum(dataset_manifest_path),
        "resources": {
            source_id: {
                "name": path.name,
                "sha256": file_checksum(path),
                "size_bytes": path.stat().st_size,
            }
            for source_id, path in sorted(resource_paths.items())
            if path.is_file()
        },
    }


def control_identity(control_dir: Path) -> dict[str, str]:
    if not control_dir.is_dir():
        raise PublicationError("Runtime certification control directory is missing")
    files = {
        path.relative_to(control_dir).as_posix(): file_checksum(path)
        for path in sorted(control_dir.rglob("*"))
        if path.is_file()
    }
    if not files:
        raise PublicationError("Runtime certification control directory is empty")
    return files


def verify_snapshot_handle(snapshot: VerifiedSnapshot) -> None:
    manifest = _read_json(snapshot.snapshot_dir / "manifest.json", "manifest")
    if manifest != snapshot.manifest:
        raise PublicationError("Runtime snapshot handle manifest mismatch")
    if manifest.get("schema_version") != RUNTIME_SCHEMA:
        raise PublicationError("Runtime snapshot schema is unsupported")

    try:
        release_ref = ReleaseRef.model_validate(manifest.get("release"))
    except Exception as exc:
        raise PublicationError("Runtime snapshot release reference is invalid") from exc
    bundle = verify_release_directory(snapshot.snapshot_dir / "release", release_ref)
    if package_checksum(snapshot.package) != package_checksum(bundle.package):
        raise PublicationError("Runtime snapshot package does not match its release")
    if snapshot.release_checksum != release_ref.checksum:
        raise PublicationError("Runtime snapshot release checksum mismatch")

    expected_sources = {source.id for source in bundle.package.data_sources}
    if set(snapshot.resource_paths) != expected_sources:
        raise PublicationError("Runtime dataset bindings do not cover the release sources")
    for path in snapshot.resource_paths.values():
        if not path.is_file():
            raise PublicationError("Runtime dataset resource is missing")

    stored_dataset = _read_json(
        snapshot.snapshot_dir / "dataset-manifest.json", "dataset manifest"
    )
    current_dataset = dataset_identity(
        snapshot.resource_paths,
        dataset_manifest_path=snapshot.dataset_manifest_path,
    )
    if current_dataset != stored_dataset:
        raise PublicationError("Runtime dataset identity no longer matches the snapshot")
    dataset_checksum = sha256_value(stored_dataset)
    if snapshot.dataset_checksum != dataset_checksum:
        raise PublicationError("Runtime snapshot handle dataset checksum mismatch")

    stored_adapter = _read_json(
        snapshot.snapshot_dir / "adapter-manifest.json", "adapter manifest"
    )
    try:
        binding = RuntimeBindingSpec.model_validate(manifest.get("binding"))
    except Exception as exc:
        raise PublicationError("Runtime snapshot adapter binding is invalid") from exc
    descriptor = snapshot.scenario_adapter.descriptor
    if (
        binding.adapter_id != descriptor.adapter_id
        or binding.adapter_version != descriptor.adapter_version
    ):
        raise PublicationError("Runtime snapshot handle uses another scenario adapter")
    if sha256_value(stored_adapter) != sha256_value(
        adapter_manifest(adapter=snapshot.scenario_adapter)
    ):
        raise PublicationError("Runtime adapter build no longer matches the snapshot")
    adapter_checksum = sha256_value(stored_adapter)
    stored_runtime = _read_json(
        snapshot.snapshot_dir / "runtime-identity.json", "runtime identity"
    )
    if stored_runtime != runtime_identity():
        raise PublicationError("Runtime identity no longer matches the snapshot")
    runtime_checksum = sha256_value(stored_runtime)
    binding_report = _read_json(
        snapshot.snapshot_dir / "binding-report.json", "binding report"
    )
    if binding_report.get("status") != "PASS":
        raise PublicationError("Runtime binding report is not PASS")

    binding_components = {
        "release_checksum": release_ref.checksum,
        "dataset_checksum": dataset_checksum,
        "adapter_checksum": adapter_checksum,
        "runtime_identity_checksum": runtime_checksum,
        "binding_report_checksum": sha256_value(binding_report),
        "binding_spec_checksum": sha256_value(manifest.get("binding")),
    }
    binding_checksum = sha256_value(binding_components)
    if manifest.get("binding_components") != binding_components:
        raise PublicationError("Runtime binding components are inconsistent")
    if manifest.get("binding_checksum") != binding_checksum:
        raise PublicationError("Runtime binding checksum mismatch")

    certification = manifest.get("certification")
    certification_checksum: str | None = None
    if certification is not None:
        if not isinstance(certification, dict):
            raise PublicationError("Runtime certification reference is invalid")
        report = _read_json(
            snapshot.snapshot_dir / "certification-report.json",
            "certification report",
        )
        controls = _read_json(
            snapshot.snapshot_dir / "control-manifest.json",
            "control manifest",
        )
        if snapshot.control_dir is None:
            raise PublicationError("Runtime certification controls are not resolved")
        if controls != control_identity(snapshot.control_dir):
            raise PublicationError("Runtime certification inputs no longer match")
        report_checksum = sha256_value(report)
        control_checksum = sha256_value(controls)
        if report.get("status") != "PASS":
            raise PublicationError("Runtime certification report is not PASS")
        if report.get("subject_binding_checksum") != binding_checksum:
            raise PublicationError("Runtime certification is bound to another runtime")
        expected_certification = {
            "profile_id": report.get("profile_id"),
            "profile_version": report.get("profile_version"),
            "report_checksum": report_checksum,
            "control_checksum": control_checksum,
        }
        if certification != expected_certification:
            raise PublicationError("Runtime certification reference is inconsistent")
        certification_checksum = sha256_value(expected_certification)

    state = manifest.get("state")
    if state == "binding_candidate":
        expected_snapshot = binding_checksum
    elif state == "ready":
        expected_snapshot = sha256_value(
            {
                "binding_checksum": binding_checksum,
                "certification_checksum": certification_checksum,
            }
        )
    else:
        raise PublicationError("Runtime snapshot state is invalid")
    if manifest.get("snapshot_checksum") != expected_snapshot:
        raise PublicationError("Runtime snapshot checksum mismatch")
    if snapshot.snapshot_checksum != expected_snapshot:
        raise PublicationError("Runtime snapshot handle checksum mismatch")
    if snapshot.capability_checksum != adapter_checksum:
        raise PublicationError("Runtime snapshot handle adapter checksum mismatch")
    if snapshot.toolchain_checksum != adapter_checksum:
        raise PublicationError("Runtime snapshot handle toolchain compatibility mismatch")
