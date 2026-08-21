from __future__ import annotations

import hashlib
import io
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
import tarfile

import pytest

from ontology_agent.adt_scenario import (
    ADT_CERTIFICATION_PROFILE,
    adt_golden_certification,
    adt_synthetic_binding,
)
from ontology_agent.contracts import (
    ActivationConflictError,
    ActivationReceipt,
    ReleaseRef,
    RuntimeSnapshotRef,
)
from ontology_agent.durable_lifecycle import (
    DurableLifecycleError,
    classify_artifact_versions,
    directory_archive_bytes,
    restore_directory_archive,
)
from ontology_agent.lifecycle import AgentRuntime, FileResourceResolver
from ontology_agent.models import OntologyPackage
from ontology_agent.product_context import (
    ExactStoredArtifactRef,
    ProductContextSubjectV1,
    S3ObjectVersion,
)
from ontology_agent.release import StudioReleases


class MemoryLifecycleStore:
    def __init__(self) -> None:
        self.releases: dict[str, tuple[ReleaseRef, bytes]] = {}
        self.release_aliases: dict[tuple[str, str], ReleaseRef] = {}
        self.snapshots: dict[str, tuple[RuntimeSnapshotRef, bytes]] = {}
        self.heads: dict[tuple[str, str], RuntimeSnapshotRef] = {}
        self.previous: dict[tuple[str, str], RuntimeSnapshotRef | None] = {}

    @staticmethod
    def _ref(payload: bytes, namespace: str) -> ExactStoredArtifactRef:
        digest = hashlib.sha256(payload).hexdigest()
        return ExactStoredArtifactRef(
            bucket="memory",
            key=f"{namespace}/sha256/{digest}.tar",
            version_id=f"version-{digest[:12]}",
            sha256=digest,
            size_bytes=len(payload),
            media_type="application/x-tar",
        )

    def persist_release(self, ref: ReleaseRef, directory: Path) -> ExactStoredArtifactRef:
        payload = directory_archive_bytes(directory)
        self.releases.setdefault(ref.checksum, (ref, payload))
        alias = (ref.package_id, ref.version)
        existing = self.release_aliases.setdefault(alias, ref)
        if existing != ref:
            raise DurableLifecycleError("release alias conflict")
        return self._ref(payload, "releases")

    def materialize_release(self, ref: ReleaseRef, destination: Path) -> None:
        restore_directory_archive(self.releases[ref.checksum][1], destination)

    def resolve_release(self, package_id: str, version: str) -> ReleaseRef:
        return self.release_aliases[(package_id, version)]

    def list_releases(self, package_id: str) -> tuple[ReleaseRef, ...]:
        return tuple(
            ref for (candidate, _), ref in self.release_aliases.items() if candidate == package_id
        )

    def persist_snapshot(
        self,
        ref: RuntimeSnapshotRef,
        directory: Path,
        context: ProductContextSubjectV1,
    ) -> ExactStoredArtifactRef:
        assert context.active_runtime.snapshot_checksum == ref.checksum
        payload = directory_archive_bytes(directory)
        self.snapshots.setdefault(ref.checksum, (ref, payload))
        return self._ref(payload, "snapshots")

    def materialize_snapshot(self, ref: RuntimeSnapshotRef, destination: Path) -> None:
        restore_directory_archive(self.snapshots[ref.checksum][1], destination)

    def resolve_snapshot(
        self, environment_id: str, snapshot_checksum: str
    ) -> RuntimeSnapshotRef:
        ref = self.snapshots[snapshot_checksum][0]
        assert ref.environment_id == environment_id
        return ref

    def active_ref(self, environment_id: str, package_id: str) -> RuntimeSnapshotRef | None:
        return self.heads.get((environment_id, package_id))

    def rollback_target(
        self, environment_id: str, package_id: str
    ) -> RuntimeSnapshotRef | None:
        return self.previous.get((environment_id, package_id))

    def activate(
        self,
        snapshot: RuntimeSnapshotRef,
        *,
        expected_current: RuntimeSnapshotRef | None,
    ) -> ActivationReceipt:
        key = (snapshot.environment_id, snapshot.release.package_id)
        current = self.heads.get(key)
        if expected_current is not None and current != expected_current:
            raise ActivationConflictError("stale durable head")
        if current == snapshot:
            return ActivationReceipt(
                environment_id=snapshot.environment_id,
                active=snapshot,
                previous=current,
                idempotent=True,
            )
        self.heads[key] = snapshot
        self.previous[key] = current
        return ActivationReceipt(
            environment_id=snapshot.environment_id,
            active=snapshot,
            previous=current,
            idempotent=False,
        )


def test_directory_archive_is_deterministic_and_restorable(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "z.json").write_text('{"z":1}\n', encoding="utf-8")
    (source / "nested").mkdir()
    (source / "nested" / "a.txt").write_text("alpha\n", encoding="utf-8")

    first = directory_archive_bytes(source)
    second = directory_archive_bytes(source)
    destination = tmp_path / "restored"
    restore_directory_archive(first, destination)

    assert first == second
    assert (destination / "z.json").read_bytes() == (source / "z.json").read_bytes()
    assert (destination / "nested" / "a.txt").read_bytes() == b"alpha\n"


def test_directory_restore_rejects_path_traversal(tmp_path: Path) -> None:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        info = tarfile.TarInfo("../escape.txt")
        info.size = 1
        archive.addfile(info, io.BytesIO(b"x"))

    with pytest.raises(DurableLifecycleError, match="unsafe entry"):
        restore_directory_archive(stream.getvalue(), tmp_path / "restored")

    assert not (tmp_path / "escape.txt").exists()


def test_artifact_gc_preserves_committed_and_recent_leased_versions() -> None:
    now = datetime(2026, 8, 20, tzinfo=timezone.utc)
    committed = S3ObjectVersion(
        bucket="memory",
        key="lifecycle/releases/sha256/a.tar",
        version_id="committed",
        last_modified=now - timedelta(days=3),
        size_bytes=10,
    )
    leased = S3ObjectVersion(
        bucket="memory",
        key="lifecycle/snapshots/sha256/b.tar",
        version_id="recent",
        last_modified=now - timedelta(minutes=5),
        size_bytes=10,
    )
    orphan = S3ObjectVersion(
        bucket="memory",
        key="lifecycle/snapshots/sha256/c.tar",
        version_id="orphan",
        last_modified=now - timedelta(days=3),
        size_bytes=10,
    )

    groups = classify_artifact_versions(
        (committed, leased, orphan),
        referenced={(committed.key, committed.version_id)},
        now=now,
        grace_seconds=3600,
    )

    assert groups == {
        "committed": (committed,),
        "leased": (leased,),
        "orphaned": (orphan,),
    }
    with pytest.raises(DurableLifecycleError, match="grace period is too short"):
        classify_artifact_versions(
            (orphan,), referenced=set(), now=now, grace_seconds=3599
        )


def test_agent_uses_one_durable_head_and_restores_exact_snapshot(
    package: OntologyPackage,
    scenario_dir: Path,
    tmp_path: Path,
) -> None:
    store = MemoryLifecycleStore()
    release_root = tmp_path / "registry" / "releases"
    runtime_root = tmp_path / "registry" / "runtime"
    studio = StudioReleases(release_root, lifecycle_store=store)
    agent = AgentRuntime(
        release_root=release_root,
        runtime_root=runtime_root,
        resources=FileResourceResolver({"adt-scenario": scenario_dir}),
        lifecycle_store=store,
    )
    first_release = studio.publish(package)
    first = agent.prepare(
        first_release.ref,
        binding=adt_synthetic_binding(resource_root_id="adt-scenario"),
        certification=adt_golden_certification(resource_root_id="adt-scenario"),
    )
    activated = agent.activate(
        first.ref,
        require_certification=ADT_CERTIFICATION_PROFILE,
    )

    assert activated.previous is None
    assert agent.active_ref("adt-poc", package.package_id) == first.ref
    assert not (runtime_root / "active").exists()

    second_package = package.model_copy(update={"version": "1.2.1"})
    second_release = studio.publish(second_package)
    second = agent.prepare(
        second_release.ref,
        binding=adt_synthetic_binding(resource_root_id="adt-scenario"),
        certification=adt_golden_certification(resource_root_id="adt-scenario"),
    )
    agent.activate(
        second.ref,
        expected_current=first.ref,
        require_certification=ADT_CERTIFICATION_PROFILE,
    )
    recreated = AgentRuntime(
        release_root=release_root,
        runtime_root=runtime_root,
        resources=FileResourceResolver({"adt-scenario": scenario_dir}),
        lifecycle_store=store,
    )
    assert recreated.rollback_target("adt-poc", package.package_id) == first.ref
    with pytest.raises(ActivationConflictError):
        agent.activate(
            first.ref,
            expected_current=first.ref,
            require_certification=ADT_CERTIFICATION_PROFILE,
        )
    rollback = agent.activate(
        first.ref,
        expected_current=second.ref,
        require_certification=ADT_CERTIFICATION_PROFILE,
    )
    assert rollback.previous == second.ref

    shutil.rmtree(release_root / package.package_id / package.version)
    shutil.rmtree(runtime_root / "snapshots" / "adt-poc" / first.ref.checksum)
    restored = agent.open_active("adt-poc", package.package_id).snapshot

    assert restored.snapshot_checksum == first.ref.checksum
    assert restored.release_checksum == first_release.ref.checksum
