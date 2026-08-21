from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Literal, Mapping

from pydantic import Field, field_validator

from .models import OntologyPackage, StrictModel, ValidationCheck

if TYPE_CHECKING:
    from .scenario import ScenarioAdapter


Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class PublicationError(RuntimeError):
    """A governed release or runtime artifact cannot be trusted or used."""


class ImmutableVersionError(PublicationError):
    """A human version alias already points at different immutable content."""


class RuntimePreparationError(PublicationError):
    """A release could not be bound or certified for one Agent environment."""


class ActivationConflictError(PublicationError):
    """The active pointer changed since the caller last observed it."""


class ReleaseRef(StrictModel):
    package_id: str
    version: str
    checksum: Sha256


class SafeSourceAsset(StrictModel):
    source_id: str
    source_type: str
    title: str
    safe_locator: str
    trust: str | None = None
    sha256: Sha256 | None = None
    anchor: str | None = None

    @field_validator("safe_locator")
    @classmethod
    def locator_must_not_be_a_local_absolute_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        if (
            not value
            or "\n" in value
            or "\r" in value
            or normalized.startswith("/")
            or (len(normalized) >= 3 and normalized[1:3] == ":/")
            or ".." in normalized.split("/")
        ):
            raise ValueError("safe locator must not expose or escape a local filesystem path")
        return value


class DataResourceBinding(StrictModel):
    source_id: str
    resource_ref: str


class RuntimeBindingSpec(StrictModel):
    environment_id: str
    resource_root_id: str
    adapter_id: str
    adapter_version: str
    query_engine_id: str
    query_engine_version: str
    dataset_manifest_ref: str
    expected_dataset_id: str | None = None
    data_resources: tuple[DataResourceBinding, ...]


class CertificationSpec(StrictModel):
    profile_id: str
    profile_version: str
    resource_root_id: str
    controls_ref: str


class RuntimeSnapshotRef(StrictModel):
    environment_id: str
    release: ReleaseRef
    checksum: Sha256


class PublishedRelease(StrictModel):
    ref: ReleaseRef
    validation_status: Literal["PASS"]
    validation_check_count: int
    idempotent: bool
    artifacts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PublishedReleaseHandle:
    ref: ReleaseRef
    validation_status: Literal["PASS"]
    validation_check_count: int
    idempotent: bool
    artifacts: tuple[str, ...]
    path: Path


class RuntimeReadiness(StrictModel):
    status: Literal["READY"]
    checks: tuple[ValidationCheck, ...]
    certification_profile: str | None = None
    certification_checksum: str | None = None


@dataclass(frozen=True, slots=True)
class PreparedRuntime:
    ref: RuntimeSnapshotRef
    readiness: RuntimeReadiness
    path: Path
    idempotent: bool


class ActivationReceipt(StrictModel):
    environment_id: str
    active: RuntimeSnapshotRef
    previous: RuntimeSnapshotRef | None = None
    idempotent: bool = False


class VerificationCase(StrictModel):
    case_id: str
    status: Literal["PASS", "FAIL"]
    defects: tuple[str, ...] = ()
    execution_id: str | None = None


class ActiveRuntimeVerification(StrictModel):
    status: Literal["PASS", "FAIL"]
    snapshot: RuntimeSnapshotRef
    suite_id: str
    case_count: int
    cases: tuple[VerificationCase, ...]
    oracle: str
    oracle_defects: dict[str, Any]


@dataclass(frozen=True, slots=True)
class VerifiedSnapshot:
    """Verified Agent-local runtime input returned only by the lifecycle boundary."""

    package: OntologyPackage
    manifest: dict[str, Any]
    snapshot_dir: Path
    scenario_dir: Path
    resource_paths: Mapping[str, Path]
    dataset_manifest_path: Path
    control_dir: Path | None
    snapshot_checksum: str
    release_checksum: str
    dataset_checksum: str
    capability_checksum: str
    toolchain_checksum: str
    scenario_adapter: ScenarioAdapter


@dataclass(frozen=True, slots=True)
class ActiveRuntime:
    snapshot: VerifiedSnapshot

    @property
    def package(self) -> OntologyPackage:
        return self.snapshot.package
