from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from ontology_agent.models import OntologyPackage
from ontology_agent.publisher import (
    ImmutableVersionError,
    PublicationError,
    list_published_snapshots,
    load_verified_snapshot,
    publish_package,
    verify_snapshot_handle,
)


def test_publish_is_immutable_idempotent_and_self_verifying(
    package: OntologyPackage, scenario_dir: Path, tmp_path: Path
) -> None:
    root = tmp_path / "published"
    first = publish_package(package, scenario_dir, root)
    assert first.idempotent is False
    second = publish_package(package, scenario_dir, root)
    assert second.idempotent is True
    snapshot = load_verified_snapshot(
        package.package_id,
        scenario_dir=scenario_dir,
        published_root=root,
    )
    verify_snapshot_handle(snapshot)
    assert snapshot.package == package
    assert snapshot.snapshot_checksum == first.snapshot_checksum
    assert snapshot.manifest["binding_checksum"]
    assert snapshot.manifest["certification"]["profile_id"] == "adt-golden-v1"
    assert (snapshot.snapshot_dir / "adapter-manifest.json").is_file()
    assert (snapshot.snapshot_dir / "binding-report.json").is_file()
    assert (snapshot.snapshot_dir / "dataset-manifest.json").is_file()
    assert (snapshot.snapshot_dir / "control-manifest.json").is_file()
    assert (snapshot.snapshot_dir / "runtime-identity.json").is_file()
    assert not (snapshot.snapshot_dir / "release" / "dataset-manifest.json").exists()
    assert not (snapshot.snapshot_dir / "release" / "control-manifest.json").exists()
    assert not (snapshot.snapshot_dir / "release" / "runtime-identity.json").exists()

    changed = package.model_copy(update={"created_at": package.created_at + timedelta(seconds=1)})
    with pytest.raises(ImmutableVersionError):
        publish_package(changed, scenario_dir, root)


def test_control_or_data_change_invalidates_existing_snapshot(
    package: OntologyPackage, scenario_dir: Path, tmp_path: Path
) -> None:
    root = tmp_path / "published"
    publish_package(package, scenario_dir, root)
    snapshot = load_verified_snapshot(
        package.package_id,
        scenario_dir=scenario_dir,
        published_root=root,
    )
    oracle_path = scenario_dir / "golden" / "oracle.json"
    oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
    oracle["comparison"]["turnover_delta_hkd_mn"] = -1
    oracle_path.write_text(json.dumps(oracle), encoding="utf-8")
    with pytest.raises(PublicationError):
        verify_snapshot_handle(snapshot)


def test_artifact_tampering_is_detected(
    package: OntologyPackage, scenario_dir: Path, tmp_path: Path
) -> None:
    root = tmp_path / "published"
    publish_package(package, scenario_dir, root)
    snapshot = load_verified_snapshot(
        package.package_id,
        scenario_dir=scenario_dir,
        published_root=root,
    )
    capability_path = snapshot.snapshot_dir / "adapter-manifest.json"
    capability_path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(PublicationError):
        verify_snapshot_handle(snapshot)


def test_snapshot_listing_uses_semver_and_does_not_leak_paths(
    package: OntologyPackage, scenario_dir: Path, tmp_path: Path
) -> None:
    root = tmp_path / "published"
    for version in ("1.9.0", "1.10.0"):
        publish_package(package.model_copy(update={"version": version}), scenario_dir, root)
    snapshots = list_published_snapshots(package.package_id, published_root=root)
    assert [item["version"] for item in snapshots] == ["1.10.0", "1.9.0"]
    assert all("path" not in item for item in snapshots)
