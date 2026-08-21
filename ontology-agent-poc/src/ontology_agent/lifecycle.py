from __future__ import annotations

import json
import os
import shutil
import tempfile
from contextlib import contextmanager
import fcntl
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .contracts import (
    ActivationConflictError,
    ActivationReceipt,
    ActiveRuntimeVerification,
    ActiveRuntime,
    CertificationSpec,
    PreparedRuntime,
    PublicationError,
    ReleaseRef,
    RuntimeBindingSpec,
    RuntimePreparationError,
    RuntimeReadiness,
    RuntimeSnapshotRef,
    VerificationCase,
    VerifiedSnapshot,
)
from .durable_lifecycle import LifecycleStorePort, configured_lifecycle_store
from .io import sha256_value, write_json
from .models import ValidationCheck
from .release import StudioReleases
from .product_context import product_context_subject
from .scenario import (
    ScenarioAdapterError,
    ScenarioAdapterRegistry,
    default_scenario_adapters,
)
from .runtime_snapshot import (
    RUNTIME_SCHEMA,
    adapter_manifest,
    control_identity,
    dataset_identity,
    runtime_identity,
    verify_snapshot_handle,
)


class FileResourceResolver:
    """Resolve opaque root aliases without persisting local absolute paths."""

    def __init__(self, roots: Mapping[str, Path]):
        self._roots = {key: value.resolve() for key, value in roots.items()}

    def resolve(self, root_id: str, resource_ref: str) -> Path:
        try:
            root = self._roots[root_id]
        except KeyError as exc:
            raise RuntimePreparationError(
                f"Unknown Agent-local resource root: {root_id}"
            ) from exc
        relative = PurePosixPath(resource_ref)
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimePreparationError("Agent-local resource reference is unsafe")
        path = (root / Path(*relative.parts)).resolve()
        if not path.is_relative_to(root):
            raise RuntimePreparationError("Agent-local resource escapes its configured root")
        return path

    def root(self, root_id: str) -> Path:
        try:
            return self._roots[root_id]
        except KeyError as exc:
            raise RuntimePreparationError(
                f"Unknown Agent-local resource root: {root_id}"
            ) from exc


def _checks_payload(checks: tuple[ValidationCheck, ...] | list[ValidationCheck]) -> list[dict[str, Any]]:
    return [
        {
            "check_id": check.check_id,
            "category": check.category,
            "status": check.status,
            "message": check.message,
            "details": check.details,
        }
        for check in checks
    ]


def _normalized_suite(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "suite_id": report.get("suite_id"),
        "status": report.get("status"),
        "case_count": report.get("case_count"),
        "cases": [
            {
                "id": case.get("id"),
                "status": case.get("status"),
                "defects": case.get("defects", []),
            }
            for case in report.get("cases", [])
        ],
        "oracle": report.get("oracle"),
        "oracle_defects": report.get("oracle_defects", {}),
    }


class AgentRuntime:
    """Deep Agent boundary for prepare, activate and active runtime loading."""

    def __init__(
        self,
        *,
        release_root: Path,
        runtime_root: Path,
        resources: FileResourceResolver,
        adapters: ScenarioAdapterRegistry | None = None,
        lifecycle_store: LifecycleStorePort | None = None,
    ):
        self.lifecycle_store = lifecycle_store or configured_lifecycle_store()
        self.releases = StudioReleases(
            release_root, lifecycle_store=self.lifecycle_store
        )
        self.runtime_root = runtime_root.resolve()
        self.resources = resources
        self.adapters = adapters or default_scenario_adapters()

    def _resolve_resources(
        self,
        binding: RuntimeBindingSpec,
    ) -> dict[str, Path]:
        if len({item.source_id for item in binding.data_resources}) != len(
            binding.data_resources
        ):
            raise RuntimePreparationError("Runtime data binding contains duplicate source IDs")
        return {
            item.source_id: self.resources.resolve(
                binding.resource_root_id, item.resource_ref
            )
            for item in binding.data_resources
        }

    def _snapshot_path(self, ref: RuntimeSnapshotRef) -> Path:
        return (
            self.runtime_root
            / "snapshots"
            / ref.environment_id
            / ref.checksum
        )

    def _active_path(self, environment_id: str, package_id: str) -> Path:
        return self.runtime_root / "active" / environment_id / f"{package_id}.json"

    def _handle(
        self,
        snapshot_dir: Path,
        *,
        resource_paths: Mapping[str, Path],
        dataset_manifest_path: Path,
        control_dir: Path | None,
    ) -> VerifiedSnapshot:
        try:
            manifest = json.loads(
                (snapshot_dir / "manifest.json").read_text(encoding="utf-8")
            )
            binding = RuntimeBindingSpec.model_validate(manifest["binding"])
            scenario_adapter = self.adapters.resolve(
                binding.adapter_id, binding.adapter_version
            )
            release_ref = ReleaseRef.model_validate(manifest["release"])
            package = self.releases.load(release_ref).package
        except Exception:
            # Persisted snapshots carry their own release copy. Loading from the producer
            # repository is intentionally not required after prepare.
            try:
                manifest = json.loads(
                    (snapshot_dir / "manifest.json").read_text(encoding="utf-8")
                )
                binding = RuntimeBindingSpec.model_validate(manifest["binding"])
                scenario_adapter = self.adapters.resolve(
                    binding.adapter_id, binding.adapter_version
                )
                release_ref = ReleaseRef.model_validate(manifest["release"])
                from .release import verify_release_directory

                package = verify_release_directory(
                    snapshot_dir / "release", release_ref
                ).package
            except Exception as exc:
                raise PublicationError("Runtime snapshot cannot load its release") from exc
        components = manifest.get("binding_components", {})
        return VerifiedSnapshot(
            package=package,
            manifest=manifest,
            snapshot_dir=snapshot_dir.resolve(),
            scenario_dir=self.resources.root(binding.resource_root_id),
            resource_paths=dict(resource_paths),
            dataset_manifest_path=dataset_manifest_path.resolve(),
            control_dir=control_dir.resolve() if control_dir is not None else None,
            snapshot_checksum=str(manifest.get("snapshot_checksum", "")),
            release_checksum=release_ref.checksum,
            dataset_checksum=str(components.get("dataset_checksum", "")),
            capability_checksum=str(components.get("adapter_checksum", "")),
            toolchain_checksum=str(components.get("adapter_checksum", "")),
            scenario_adapter=scenario_adapter,
        )

    def prepare(
        self,
        release: ReleaseRef,
        *,
        binding: RuntimeBindingSpec,
        certification: CertificationSpec | None = None,
    ) -> PreparedRuntime:
        bundle = self.releases.load(release)
        try:
            scenario_adapter = self.adapters.resolve(
                binding.adapter_id, binding.adapter_version
            )
        except ScenarioAdapterError as exc:
            raise RuntimePreparationError(str(exc)) from exc
        descriptor = scenario_adapter.descriptor
        if certification is not None and descriptor.certification_profiles.get(
            certification.profile_id
        ) != certification.profile_version:
            raise RuntimePreparationError("No compatible certification profile is installed")

        resource_paths = self._resolve_resources(binding)
        expected_sources = {source.id for source in bundle.package.data_sources}
        if (
            descriptor.data_binding_policy == "EXACT_PACKAGE_SOURCES"
            and set(resource_paths) != expected_sources
        ):
            raise RuntimePreparationError(
                "Runtime data binding must cover every release source exactly once"
            )
        if descriptor.data_binding_policy == "NONE" and resource_paths:
            raise RuntimePreparationError(
                "Semantic-only runtime cannot accept data resource bindings"
            )
        dataset_manifest_path = self.resources.resolve(
            binding.resource_root_id, binding.dataset_manifest_ref
        )
        try:
            validation = scenario_adapter.validate(
                bundle.package,
                binding=binding,
                resource_paths=resource_paths,
                dataset_manifest_path=dataset_manifest_path,
            )
        except ScenarioAdapterError as exc:
            raise RuntimePreparationError(str(exc)) from exc
        binding_checks = list(validation.checks)
        failed_binding = [
            check.check_id for check in binding_checks if check.status == "FAIL"
        ]
        if failed_binding:
            raise RuntimePreparationError(
                "Scenario adapter validation failed: " + ", ".join(failed_binding)
            )

        dataset = dataset_identity(
            resource_paths,
            dataset_manifest_path=dataset_manifest_path,
        )
        adapter = adapter_manifest(adapter=scenario_adapter)
        runtime = runtime_identity()
        binding_report = {
            "status": "PASS",
            "checks": _checks_payload(binding_checks),
        }
        binding_payload = binding.model_dump(mode="json")
        binding_components = {
            "release_checksum": release.checksum,
            "dataset_checksum": sha256_value(dataset),
            "adapter_checksum": sha256_value(adapter),
            "runtime_identity_checksum": sha256_value(runtime),
            "binding_report_checksum": sha256_value(binding_report),
            "binding_spec_checksum": sha256_value(binding_payload),
        }
        binding_checksum = sha256_value(binding_components)

        snapshots_root = self.runtime_root / "snapshots" / binding.environment_id
        snapshots_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".prepare-", dir=snapshots_root
        ) as temporary:
            staging = Path(temporary)
            shutil.copytree(bundle.path, staging / "release")
            write_json(staging / "dataset-manifest.json", dataset)
            write_json(staging / "adapter-manifest.json", adapter)
            write_json(staging / "runtime-identity.json", runtime)
            write_json(staging / "binding-report.json", binding_report)
            candidate_manifest = {
                "schema_version": RUNTIME_SCHEMA,
                "state": "binding_candidate",
                "environment_id": binding.environment_id,
                "release": release.model_dump(mode="json"),
                "binding": binding_payload,
                "binding_components": binding_components,
                "binding_checksum": binding_checksum,
                "certification_spec": (
                    certification.model_dump(mode="json")
                    if certification is not None
                    else None
                ),
                "certification": None,
                "snapshot_checksum": binding_checksum,
            }
            write_json(staging / "manifest.json", candidate_manifest)

            control_dir: Path | None = None
            certification_reference: dict[str, Any] | None = None
            certification_checksum: str | None = None
            certification_checks: list[ValidationCheck] = []
            if certification is not None:
                if certification.resource_root_id != binding.resource_root_id:
                    raise RuntimePreparationError(
                        "Certification controls must use the bound Agent resource root"
                    )
                control_dir = self.resources.resolve(
                    certification.resource_root_id, certification.controls_ref
                )
                candidate = self._handle(
                    staging,
                    resource_paths=resource_paths,
                    dataset_manifest_path=dataset_manifest_path,
                    control_dir=None,
                )
                verify_snapshot_handle(candidate)
                try:
                    with tempfile.TemporaryDirectory(prefix="ontology-cert-") as executions:
                        evaluation = scenario_adapter.evaluate(
                            candidate,
                            control_dir=control_dir,
                            execution_dir=Path(executions),
                        )
                except ScenarioAdapterError as exc:
                    raise RuntimePreparationError(
                        f"Scenario certification evidence is invalid: {exc}"
                    ) from exc
                certification_checks = list(evaluation.checks)
                failed_certification = [
                    check.check_id
                    for check in certification_checks
                    if check.status == "FAIL"
                ]
                if failed_certification:
                    raise RuntimePreparationError(
                        "Scenario certification failed: "
                        + ", ".join(failed_certification)
                    )

                try:
                    suite = _normalized_suite(
                        evaluation.validated_suite(descriptor)
                    )
                except ScenarioAdapterError as exc:
                    raise RuntimePreparationError(
                        f"Scenario certification evidence is invalid: {exc}"
                    ) from exc
                if suite["status"] != "PASS":
                    raise RuntimePreparationError("Scenario certification suite failed")
                report = {
                    "profile_id": certification.profile_id,
                    "profile_version": certification.profile_version,
                    "subject_binding_checksum": binding_checksum,
                    "status": "PASS",
                    "checks": _checks_payload(certification_checks),
                    "evaluation_suite": suite,
                }
                controls = control_identity(control_dir)
                write_json(staging / "certification-report.json", report)
                write_json(staging / "control-manifest.json", controls)
                certification_reference = {
                    "profile_id": certification.profile_id,
                    "profile_version": certification.profile_version,
                    "report_checksum": sha256_value(report),
                    "control_checksum": sha256_value(controls),
                }
                certification_checksum = sha256_value(certification_reference)

            snapshot_checksum = sha256_value(
                {
                    "binding_checksum": binding_checksum,
                    "certification_checksum": certification_checksum,
                }
            )
            final_manifest = {
                **candidate_manifest,
                "state": "ready",
                "certification": certification_reference,
                "snapshot_checksum": snapshot_checksum,
            }
            write_json(staging / "manifest.json", final_manifest)
            ref = RuntimeSnapshotRef(
                environment_id=binding.environment_id,
                release=release,
                checksum=snapshot_checksum,
            )
            destination = self._snapshot_path(ref)
            if destination.exists():
                existing = self._load_snapshot(ref)
                verify_snapshot_handle(existing)
                if self.lifecycle_store is not None:
                    self.lifecycle_store.persist_snapshot(
                        ref,
                        destination,
                        product_context_subject(existing),
                    )
                return PreparedRuntime(
                    ref=ref,
                    readiness=RuntimeReadiness(
                        status="READY",
                        checks=tuple([*binding_checks, *certification_checks]),
                        certification_profile=(
                            certification.profile_id
                            if certification is not None
                            else None
                        ),
                        certification_checksum=certification_checksum,
                    ),
                    path=destination,
                    idempotent=True,
                )
            try:
                os.replace(staging, destination)
            except OSError as exc:
                raise RuntimePreparationError(
                    f"Could not atomically persist runtime snapshot: {exc}"
                ) from exc

        verified = self._load_snapshot(ref)
        verify_snapshot_handle(verified)
        if self.lifecycle_store is not None:
            self.lifecycle_store.persist_snapshot(
                ref,
                destination,
                product_context_subject(verified),
            )
        return PreparedRuntime(
            ref=ref,
            readiness=RuntimeReadiness(
                status="READY",
                checks=tuple([*binding_checks, *certification_checks]),
                certification_profile=(
                    certification.profile_id if certification is not None else None
                ),
                certification_checksum=certification_checksum,
            ),
            path=destination,
            idempotent=False,
        )

    def _load_snapshot(self, ref: RuntimeSnapshotRef) -> VerifiedSnapshot:
        snapshot_dir = self._snapshot_path(ref)
        if not (snapshot_dir / "manifest.json").is_file() and self.lifecycle_store is not None:
            self.lifecycle_store.materialize_snapshot(ref, snapshot_dir)
        if not (snapshot_dir / "manifest.json").is_file():
            raise PublicationError("Prepared runtime snapshot is missing")
        try:
            manifest = json.loads(
                (snapshot_dir / "manifest.json").read_text(encoding="utf-8")
            )
            binding = RuntimeBindingSpec.model_validate(manifest["binding"])
            resource_paths = self._resolve_resources(binding)
            dataset_manifest_path = self.resources.resolve(
                binding.resource_root_id, binding.dataset_manifest_ref
            )
            raw_certification = manifest.get("certification_spec")
            certification = (
                CertificationSpec.model_validate(raw_certification)
                if raw_certification is not None
                else None
            )
            control_dir = (
                self.resources.resolve(
                    certification.resource_root_id, certification.controls_ref
                )
                if certification is not None
                else None
            )
        except PublicationError:
            raise
        except Exception as exc:
            raise PublicationError("Prepared runtime snapshot manifest is invalid") from exc
        handle = self._handle(
            snapshot_dir,
            resource_paths=resource_paths,
            dataset_manifest_path=dataset_manifest_path,
            control_dir=control_dir,
        )
        if handle.snapshot_checksum != ref.checksum:
            raise PublicationError("Prepared runtime snapshot identity mismatch")
        return handle

    def activate(
        self,
        snapshot: RuntimeSnapshotRef,
        *,
        expected_current: RuntimeSnapshotRef | None = None,
        require_certification: str | None = None,
    ) -> ActivationReceipt:
        handle = self._load_snapshot(snapshot)
        verify_snapshot_handle(handle)
        certification = handle.manifest.get("certification")
        if require_certification is not None and (
            not isinstance(certification, dict)
            or certification.get("profile_id") != require_certification
        ):
            raise PublicationError(
                f"Activation requires certification profile {require_certification}"
            )

        if self.lifecycle_store is not None:
            return self.lifecycle_store.activate(
                snapshot,
                expected_current=expected_current,
            )

        active_path = self._active_path(
            snapshot.environment_id, snapshot.release.package_id
        )
        active_path.parent.mkdir(parents=True, exist_ok=True)
        with self._activation_lock(active_path):
            current = self.active_ref(
                snapshot.environment_id, snapshot.release.package_id
            )
            if expected_current is not None and current != expected_current:
                raise ActivationConflictError("Active runtime changed before activation")
            if current == snapshot:
                return ActivationReceipt(
                    environment_id=snapshot.environment_id,
                    active=snapshot,
                    previous=current,
                    idempotent=True,
                )
            payload = {
                "schema_version": "runtime-activation/v1",
                "active": snapshot.model_dump(mode="json"),
                "previous": current.model_dump(mode="json") if current else None,
            }
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                prefix=".activate-",
                suffix=".json",
                dir=active_path.parent,
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
                stream.write("\n")
            try:
                os.replace(temporary, active_path)
            except OSError as exc:
                temporary.unlink(missing_ok=True)
                raise PublicationError(
                    f"Could not atomically activate runtime: {exc}"
                ) from exc
        return ActivationReceipt(
            environment_id=snapshot.environment_id,
            active=snapshot,
            previous=current,
            idempotent=False,
        )

    @contextmanager
    def _activation_lock(self, active_path: Path):
        lock_path = active_path.with_suffix(active_path.suffix + ".lock")
        with lock_path.open("a+", encoding="utf-8") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def active_ref(
        self,
        environment_id: str,
        package_id: str,
    ) -> RuntimeSnapshotRef | None:
        if self.lifecycle_store is not None:
            return self.lifecycle_store.active_ref(environment_id, package_id)
        active, _ = self._local_activation_refs(environment_id, package_id)
        return active

    def _local_activation_refs(
        self,
        environment_id: str,
        package_id: str,
    ) -> tuple[RuntimeSnapshotRef | None, RuntimeSnapshotRef | None]:
        path = self._active_path(environment_id, package_id)
        if not path.is_file():
            return None, None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if value.get("schema_version") != "runtime-activation/v1":
                raise ValueError("unknown activation pointer schema")
            active = RuntimeSnapshotRef.model_validate(value["active"])
            previous = (
                RuntimeSnapshotRef.model_validate(value["previous"])
                if value.get("previous") is not None
                else None
            )
            for ref in (active, previous):
                if ref is not None and (
                    ref.environment_id != environment_id
                    or ref.release.package_id != package_id
                ):
                    raise ValueError("activation pointer identity mismatch")
            if previous == active:
                raise ValueError("activation predecessor cannot equal the active ref")
            return active, previous
        except Exception as exc:
            raise PublicationError("Active runtime pointer is invalid") from exc

    def rollback_target(
        self,
        environment_id: str,
        package_id: str,
    ) -> RuntimeSnapshotRef | None:
        if self.lifecycle_store is not None:
            return self.lifecycle_store.rollback_target(environment_id, package_id)
        _, previous = self._local_activation_refs(environment_id, package_id)
        if previous is None:
            return None
        resolved = self.resolve_prepared(environment_id, previous.checksum)
        if resolved != previous or resolved.release.package_id != package_id:
            raise PublicationError("Rollback target identity is invalid")
        return previous

    def open_active(self, environment_id: str, package_id: str) -> ActiveRuntime:
        ref = self.active_ref(environment_id, package_id)
        if ref is None:
            raise PublicationError("No active runtime snapshot is configured")
        snapshot = self._load_snapshot(ref)
        verify_snapshot_handle(snapshot)
        return ActiveRuntime(snapshot=snapshot)

    def verify_active(
        self,
        environment_id: str,
        package_id: str,
        *,
        expected_snapshot: RuntimeSnapshotRef,
        execution_dir: Path,
    ) -> ActiveRuntimeVerification:
        """Run the fixed suite against one exact active ref and reject pointer races."""
        active = self.active_ref(environment_id, package_id)
        if active != expected_snapshot:
            raise ActivationConflictError(
                "Active runtime does not match the snapshot selected for verification"
            )
        snapshot = self._load_snapshot(expected_snapshot)
        verify_snapshot_handle(snapshot)
        try:
            evaluation = snapshot.scenario_adapter.evaluate(
                snapshot,
                control_dir=None,
                execution_dir=execution_dir,
            )
            report = evaluation.validated_suite(
                snapshot.scenario_adapter.descriptor
            )
        except ScenarioAdapterError as exc:
            raise PublicationError(
                f"Active runtime verification evidence is invalid: {exc}"
            ) from exc
        if self.active_ref(environment_id, package_id) != expected_snapshot:
            raise ActivationConflictError(
                "Active runtime changed during post-activation verification"
            )
        return ActiveRuntimeVerification(
            status=report["status"],
            snapshot=expected_snapshot,
            suite_id=str(report["suite_id"]),
            case_count=report["case_count"],
            cases=tuple(
                VerificationCase(
                    case_id=case["id"],
                    status=case["status"],
                    defects=tuple(case.get("defects", [])),
                    execution_id=case.get("execution_id"),
                )
                for case in report["cases"]
            ),
            oracle=report["oracle"],
            oracle_defects=report["oracle_defects"],
        )

    def prepared_for_release(self, release: ReleaseRef) -> tuple[RuntimeSnapshotRef, ...]:
        snapshots_root = self.runtime_root / "snapshots"
        if not snapshots_root.is_dir():
            return ()
        refs: list[RuntimeSnapshotRef] = []
        for manifest_path in snapshots_root.glob("*/*/manifest.json"):
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                candidate_release = ReleaseRef.model_validate(manifest["release"])
                if candidate_release == release and manifest.get("state") == "ready":
                    refs.append(
                        RuntimeSnapshotRef(
                            environment_id=str(manifest["environment_id"]),
                            release=candidate_release,
                            checksum=str(manifest["snapshot_checksum"]),
                        )
                    )
            except Exception:
                continue
        return tuple(sorted(refs, key=lambda item: item.checksum))

    def resolve_prepared(
        self,
        environment_id: str,
        snapshot_checksum: str,
    ) -> RuntimeSnapshotRef:
        manifest_path = (
            self.runtime_root
            / "snapshots"
            / environment_id
            / snapshot_checksum
            / "manifest.json"
        )
        if not manifest_path.is_file() and self.lifecycle_store is not None:
            ref = self.lifecycle_store.resolve_snapshot(
                environment_id, snapshot_checksum
            )
            self.lifecycle_store.materialize_snapshot(
                ref,
                manifest_path.parent,
            )
        if not manifest_path.is_file():
            raise PublicationError("Prepared runtime snapshot is missing")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            ref = RuntimeSnapshotRef(
                environment_id=environment_id,
                release=ReleaseRef.model_validate(manifest["release"]),
                checksum=str(manifest["snapshot_checksum"]),
            )
        except Exception as exc:
            raise PublicationError("Prepared runtime snapshot manifest is invalid") from exc
        if ref.checksum != snapshot_checksum:
            raise PublicationError("Prepared runtime snapshot checksum mismatch")
        return ref
