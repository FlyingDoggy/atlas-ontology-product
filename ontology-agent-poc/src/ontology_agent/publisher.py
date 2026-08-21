from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .adt_scenario import (
    ADT_CERTIFICATION_PROFILE,
    adt_golden_certification,
    adt_synthetic_binding,
)
from .contracts import (
    ImmutableVersionError,
    PublicationError,
    VerifiedSnapshot,
)
from .io import DEFAULT_PUBLISHED_DIR, sha256_value
from .lifecycle import (
    AgentRuntime,
    FileResourceResolver,
)
from .models import OntologyPackage, ValidationReport
from .release import StudioReleases
from .runtime_snapshot import (
    adapter_manifest as toolchain_manifest,
    runtime_identity,
    verify_snapshot_handle,
)


@dataclass(frozen=True, slots=True)
class Publication:
    """Compatibility result for the legacy all-in-one demo command."""

    package_id: str
    version: str
    package_checksum: str
    snapshot_checksum: str
    path: Path
    idempotent: bool
    validation: ValidationReport

    @property
    def checksum(self) -> str:
        return self.snapshot_checksum


def toolchain_checksum() -> str:
    return sha256_value(toolchain_manifest())


def _composition(
    published_root: Path,
    scenario_dir: Path,
) -> tuple[StudioReleases, AgentRuntime]:
    release_root = published_root / "releases"
    runtime_root = published_root / "runtime"
    root_id = "adt-scenario"
    return (
        StudioReleases(release_root),
        AgentRuntime(
            release_root=release_root,
            runtime_root=runtime_root,
            resources=FileResourceResolver({root_id: scenario_dir}),
        ),
    )


def publish_package(
    package: OntologyPackage,
    scenario_dir: Path,
    published_root: Path = DEFAULT_PUBLISHED_DIR,
) -> Publication:
    """Legacy demo composition: publish → prepare → certify → activate.

    Product code must use ``StudioReleases`` and ``AgentRuntime`` separately.
    """

    studio, agent = _composition(published_root.resolve(), scenario_dir.resolve())
    release = studio.publish(
        package,
        limitations=("constructed synthetic; not HKEX validated",),
    )
    prepared = agent.prepare(
        release.ref,
        binding=adt_synthetic_binding(resource_root_id="adt-scenario"),
        certification=adt_golden_certification(
            resource_root_id="adt-scenario"
        ),
    )
    activation = agent.activate(
        prepared.ref,
        require_certification=ADT_CERTIFICATION_PROFILE,
    )
    bundle = studio.load(release.ref)
    validation = ValidationReport.model_validate(
        {
            **bundle.semantic_validation,
            "validated_at": package.created_at,
        }
    )
    return Publication(
        package_id=package.package_id,
        version=package.version,
        package_checksum=str(bundle.manifest["package_checksum"]),
        snapshot_checksum=prepared.ref.checksum,
        path=prepared.path,
        idempotent=release.idempotent and prepared.idempotent and activation.idempotent,
        validation=validation,
    )


def load_verified_snapshot(
    package_id: str,
    *,
    version: str | None = None,
    scenario_dir: Path,
    published_root: Path = DEFAULT_PUBLISHED_DIR,
) -> VerifiedSnapshot:
    studio, agent = _composition(published_root.resolve(), scenario_dir.resolve())
    if version is None:
        return agent.open_active("adt-poc", package_id).snapshot
    release_ref = studio.resolve(package_id, version)
    candidates = agent.prepared_for_release(release_ref)
    if not candidates:
        raise PublicationError(
            f"No prepared runtime snapshot exists for {package_id}@{version}"
        )
    active = agent.active_ref("adt-poc", package_id)
    selected = active if active in candidates else candidates[-1]
    snapshot = agent._load_snapshot(selected)
    verify_snapshot_handle(snapshot)
    return snapshot


def load_published_package(
    package_id: str,
    *,
    version: str | None = None,
    scenario_dir: Path,
    published_root: Path = DEFAULT_PUBLISHED_DIR,
) -> tuple[OntologyPackage, dict[str, object], Path]:
    snapshot = load_verified_snapshot(
        package_id,
        version=version,
        scenario_dir=scenario_dir,
        published_root=published_root,
    )
    return snapshot.package, snapshot.manifest, snapshot.snapshot_dir


def list_published_snapshots(
    package_id: str,
    *,
    published_root: Path = DEFAULT_PUBLISHED_DIR,
) -> list[dict[str, object]]:
    studio = StudioReleases(published_root / "releases")
    return [
        {
            "package_id": ref.package_id,
            "version": ref.version,
            "release_checksum": ref.checksum,
            "validation_status": "PASS",
        }
        for ref in studio.list(package_id)
    ]
