from __future__ import annotations

import hashlib
import fcntl
import json
import os
import shutil
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Literal, Protocol

import yaml
from pydantic import Field, model_validator
from sqlalchemy import DateTime, String, create_engine, func, select
from sqlalchemy.dialects.postgresql import JSONB, insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..contracts import Sha256
from ..io import canonical_bytes, file_checksum, load_package, sha256_value
from ..models import OntologyPackage, StrictModel
from ..product_context import (
    Base,
    ExactStoredArtifactRef,
    ProductInfrastructureError,
    ProductInfrastructureSettings,
    S3ArtifactStore,
)
from .editor import EditorDescriptorError, load_editor_descriptor


SOLUTION_REGISTRATION_CONTRACT = "ontology-solution-registration/v1"
SOLUTION_RECORD_CONTRACT = "ontology-solution-registration-record/v1"
REQUIRED_COMPONENT_KINDS = {
    "authoring_profile",
    "semantic_source",
    "agent_experience",
    "reference_evaluation",
}
_RESOURCE_MEDIA_TYPES = {
    ".csv": "text/csv",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".json": "application/json",
    ".md": "text/markdown",
    ".parquet": "application/vnd.apache.parquet",
    ".sql": "text/sql",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
}
_REGISTRATION_LOCATOR = "solution-registration.json"
_GENERIC_STUDIO_ADAPTER_ID = "studio-adapter.generic@1"


class SolutionCatalogError(RuntimeError):
    """A solution registration cannot be trusted or resolved."""


class SolutionDisplayName(StrictModel):
    en: str = Field(min_length=1, max_length=200)
    zh: str = Field(min_length=1, max_length=200)


class SolutionComponentDescriptor(StrictModel):
    component_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    kind: Literal[
        "authoring_profile",
        "semantic_source",
        "agent_experience",
        "reference_evaluation",
    ]
    locator: str = Field(min_length=1, max_length=500)
    media_type: Literal["application/json", "application/yaml"]
    sha256: Sha256

    @model_validator(mode="after")
    def validate_locator(self) -> SolutionComponentDescriptor:
        candidate = PurePosixPath(self.locator)
        if candidate.is_absolute() or not candidate.parts or ".." in candidate.parts:
            raise ValueError("Solution component locator is unsafe")
        return self


class SolutionResourceDescriptor(StrictModel):
    """One exact file shipped by a portable solution package."""

    locator: str = Field(min_length=1, max_length=500)
    media_type: Literal[
        "application/json",
        "application/yaml",
        "application/vnd.apache.parquet",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "image/jpeg",
        "text/csv",
        "text/markdown",
        "text/sql",
    ]
    sha256: Sha256
    size_bytes: int = Field(ge=1, le=50_000_000)

    @model_validator(mode="after")
    def validate_locator(self) -> SolutionResourceDescriptor:
        candidate = PurePosixPath(self.locator)
        if candidate.is_absolute() or not candidate.parts or ".." in candidate.parts:
            raise ValueError("Solution resource locator is unsafe")
        return self


class SolutionRegistrationSubjectV1(StrictModel):
    contract: Literal["ontology-solution-registration/v1"] = (
        SOLUTION_REGISTRATION_CONTRACT
    )
    solution_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    solution_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    # Registrations created before the component-version split omit this field.
    # Their exact artifact remains readable; new registrations must set it.
    semantic_source_version: str | None = Field(
        default=None, pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$"
    )
    scenario_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    workspace_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    studio_adapter_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._@-]*$")
    authoring_root_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    classification: Literal["constructed_synthetic"] = "constructed_synthetic"
    display_name: SolutionDisplayName
    components: tuple[SolutionComponentDescriptor, ...] = Field(
        min_length=4, max_length=16
    )
    # Historical registration artifacts did not carry a complete package inventory.
    # They remain readable, but only new registrations with resources are installable.
    resources: tuple[SolutionResourceDescriptor, ...] = Field(
        default=(), max_length=512
    )
    limitations: tuple[str, ...] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def validate_component_set(self) -> SolutionRegistrationSubjectV1:
        ids = [item.component_id for item in self.components]
        kinds = [item.kind for item in self.components]
        if len(ids) != len(set(ids)) or len(kinds) != len(set(kinds)):
            raise ValueError("Solution components must have unique IDs and kinds")
        if set(kinds) != REQUIRED_COMPONENT_KINDS:
            raise ValueError("Solution registration has an incomplete component set")
        resource_locators = [item.locator for item in self.resources]
        if len(resource_locators) != len(set(resource_locators)):
            raise ValueError("Solution resources must have unique locators")
        if self.resources:
            resources = {item.locator: item for item in self.resources}
            for component in self.components:
                resource = resources.get(component.locator)
                if (
                    resource is None
                    or resource.sha256 != component.sha256
                    or resource.media_type != component.media_type
                ):
                    raise ValueError(
                        "Every solution component must be the same exact package resource"
                    )
        if len(set(self.limitations)) != len(self.limitations):
            raise ValueError("Solution limitations must be unique")
        return self


class SolutionResourceArtifactV1(StrictModel):
    locator: str = Field(min_length=1, max_length=500)
    artifact: ExactStoredArtifactRef


class SolutionBundleSubjectV1(StrictModel):
    contract: Literal["ontology-solution-bundle/v1"] = "ontology-solution-bundle/v1"
    solution_id: str
    solution_version: str
    registration_checksum: Sha256
    resources: tuple[SolutionResourceDescriptor, ...] = Field(
        min_length=1, max_length=512
    )


class SolutionBundleRecordV1(StrictModel):
    contract: Literal["ontology-solution-bundle-record/v1"] = (
        "ontology-solution-bundle-record/v1"
    )
    subject_checksum: Sha256
    subject: SolutionBundleSubjectV1
    manifest_artifact: ExactStoredArtifactRef
    resource_artifacts: tuple[SolutionResourceArtifactV1, ...] = Field(
        min_length=1, max_length=512
    )

    @model_validator(mode="after")
    def validate_exact_inventory(self) -> SolutionBundleRecordV1:
        if sha256_value(self.subject) != self.subject_checksum:
            raise ValueError("Solution bundle subject checksum mismatch")
        if self.manifest_artifact.sha256 != self.subject_checksum:
            raise ValueError("Solution bundle manifest identity mismatch")
        expected = {item.locator: item for item in self.subject.resources}
        actual = {item.locator: item.artifact for item in self.resource_artifacts}
        if len(actual) != len(self.resource_artifacts) or set(actual) != set(expected):
            raise ValueError("Solution bundle artifact inventory mismatch")
        for locator, resource in expected.items():
            artifact = actual[locator]
            if (
                artifact.sha256 != resource.sha256
                or artifact.size_bytes != resource.size_bytes
                or artifact.media_type != resource.media_type
            ):
                raise ValueError("Solution bundle resource identity mismatch")
        return self


class SolutionRegistrationRecordV1(StrictModel):
    contract: Literal["ontology-solution-registration-record/v1"] = (
        SOLUTION_RECORD_CONTRACT
    )
    persistence: Literal["legacy-compatibility", "postgresql-s3"]
    subject_checksum: Sha256
    subject: SolutionRegistrationSubjectV1
    artifact: ExactStoredArtifactRef | None = None
    bundle: SolutionBundleRecordV1 | None = None

    @model_validator(mode="after")
    def validate_persistence(self) -> SolutionRegistrationRecordV1:
        if self.persistence == "postgresql-s3" and self.artifact is None:
            raise ValueError("Durable solution registration requires an exact artifact")
        if self.artifact is not None and self.artifact.sha256 != self.subject_checksum:
            raise ValueError("Solution registration and artifact digest do not match")
        if self.subject.resources and self.persistence == "postgresql-s3":
            if self.bundle is None:
                raise ValueError("Installable solution registration requires a bundle")
            if (
                self.bundle.subject.solution_id != self.subject.solution_id
                or self.bundle.subject.solution_version != self.subject.solution_version
                or self.bundle.subject.registration_checksum != self.subject_checksum
                or self.bundle.subject.resources != self.subject.resources
            ):
                raise ValueError("Solution registration and bundle do not match")
        return self


class StudioSolutionRegistrationRow(Base):
    __tablename__ = "studio_solution_registration"

    subject_checksum: Mapped[str] = mapped_column(String(64), primary_key=True)
    solution_id: Mapped[str] = mapped_column(String(255), nullable=False)
    solution_version: Mapped[str] = mapped_column(String(64), nullable=False)
    scenario_id: Mapped[str] = mapped_column(String(255), nullable=False)
    workspace_id: Mapped[str] = mapped_column(String(255), nullable=False)
    studio_adapter_id: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    artifact: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    bundle: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SolutionRegistrationRepository(Protocol):
    persistence: Literal["legacy-compatibility", "postgresql-s3"]

    def register(
        self,
        subject: SolutionRegistrationSubjectV1,
        artifact: ExactStoredArtifactRef,
        bundle: SolutionBundleRecordV1,
    ) -> None: ...

    def get(self, solution_id: str, solution_version: str) -> SolutionRegistrationRecordV1: ...

    def list(self) -> tuple[SolutionRegistrationRecordV1, ...]: ...


class PostgresSolutionRegistrationRepository:
    persistence: Literal["postgresql-s3"] = "postgresql-s3"

    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)

    @staticmethod
    def _record(row: StudioSolutionRegistrationRow) -> SolutionRegistrationRecordV1:
        return SolutionRegistrationRecordV1(
            persistence="postgresql-s3",
            subject_checksum=row.subject_checksum,
            subject=SolutionRegistrationSubjectV1.model_validate(row.subject),
            artifact=ExactStoredArtifactRef.model_validate(row.artifact),
            bundle=(
                SolutionBundleRecordV1.model_validate(row.bundle)
                if row.bundle is not None
                else None
            ),
        )

    def register(
        self,
        subject: SolutionRegistrationSubjectV1,
        artifact: ExactStoredArtifactRef,
        bundle: SolutionBundleRecordV1,
    ) -> None:
        checksum = sha256_value(subject)
        try:
            with Session(self.engine) as session, session.begin():
                alias = session.execute(
                    select(StudioSolutionRegistrationRow).where(
                        StudioSolutionRegistrationRow.solution_id == subject.solution_id,
                        StudioSolutionRegistrationRow.solution_version
                        == subject.solution_version,
                    )
                ).scalar_one_or_none()
                if alias is not None and alias.subject_checksum != checksum:
                    raise SolutionCatalogError(
                        "Solution ID and version already identify different content"
                    )
                session.execute(
                    pg_insert(StudioSolutionRegistrationRow)
                    .values(
                        subject_checksum=checksum,
                        solution_id=subject.solution_id,
                        solution_version=subject.solution_version,
                        scenario_id=subject.scenario_id,
                        workspace_id=subject.workspace_id,
                        studio_adapter_id=subject.studio_adapter_id,
                        subject=subject.model_dump(mode="json"),
                        artifact=artifact.model_dump(mode="json"),
                        bundle=bundle.model_dump(mode="json"),
                    )
                    .on_conflict_do_nothing(
                        index_elements=[StudioSolutionRegistrationRow.subject_checksum]
                    )
                )
                persisted = session.get(StudioSolutionRegistrationRow, checksum)
                if persisted is not None and persisted.bundle is None:
                    persisted.bundle = bundle.model_dump(mode="json")
                if persisted is None or self._record(persisted) != SolutionRegistrationRecordV1(
                    persistence="postgresql-s3",
                    subject_checksum=checksum,
                    subject=subject,
                    artifact=artifact,
                    bundle=bundle,
                ):
                    raise SolutionCatalogError("Solution registration identity conflict")
        except SolutionCatalogError:
            raise
        except SQLAlchemyError as exc:
            raise SolutionCatalogError(
                "Solution registration database commit failed"
            ) from exc

    def get(
        self, solution_id: str, solution_version: str
    ) -> SolutionRegistrationRecordV1:
        try:
            with Session(self.engine) as session:
                row = session.execute(
                    select(StudioSolutionRegistrationRow).where(
                        StudioSolutionRegistrationRow.solution_id == solution_id,
                        StudioSolutionRegistrationRow.solution_version
                        == solution_version,
                    )
                ).scalar_one_or_none()
                if row is not None:
                    session.expunge(row)
        except SQLAlchemyError as exc:
            raise SolutionCatalogError("Solution registration lookup failed") from exc
        if row is None:
            raise SolutionCatalogError("Solution registration is not installed")
        return self._record(row)

    def list(self) -> tuple[SolutionRegistrationRecordV1, ...]:
        try:
            with Session(self.engine) as session:
                rows = session.execute(
                    select(StudioSolutionRegistrationRow).order_by(
                        StudioSolutionRegistrationRow.solution_id,
                        StudioSolutionRegistrationRow.solution_version,
                    )
                ).scalars().all()
                for row in rows:
                    session.expunge(row)
        except SQLAlchemyError as exc:
            raise SolutionCatalogError("Solution registration listing failed") from exc
        return tuple(self._record(row) for row in rows)


class LocalSolutionRegistrationRepository:
    persistence: Literal["legacy-compatibility"] = "legacy-compatibility"

    def __init__(self, subject: SolutionRegistrationSubjectV1) -> None:
        self.subject = subject

    def register(
        self,
        subject: SolutionRegistrationSubjectV1,
        artifact: ExactStoredArtifactRef,
        bundle: SolutionBundleRecordV1,
    ) -> None:
        raise SolutionCatalogError("Local compatibility catalog is read-only")

    def get(
        self, solution_id: str, solution_version: str
    ) -> SolutionRegistrationRecordV1:
        if (
            self.subject.solution_id != solution_id
            or self.subject.solution_version != solution_version
        ):
            raise SolutionCatalogError("Solution registration is not installed")
        return SolutionRegistrationRecordV1(
            persistence="legacy-compatibility",
            subject_checksum=sha256_value(self.subject),
            subject=self.subject,
        )

    def list(self) -> tuple[SolutionRegistrationRecordV1, ...]:
        return (self.get(self.subject.solution_id, self.subject.solution_version),)


def load_solution_registration(path: Path) -> SolutionRegistrationSubjectV1:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        subject = SolutionRegistrationSubjectV1.model_validate(payload)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SolutionCatalogError("Solution registration manifest is invalid") from exc
    if subject.semantic_source_version is None:
        raise SolutionCatalogError(
            "New solution registrations must declare semantic source version separately"
        )
    if not subject.resources:
        raise SolutionCatalogError(
            "New solution registrations must declare the complete package resource inventory"
        )
    return subject


def _resource_paths(root: Path) -> dict[str, Path]:
    resources: dict[str, Path] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise SolutionCatalogError("Solution package cannot contain symbolic links")
        if not path.is_file():
            continue
        locator = path.relative_to(root).as_posix()
        if locator == _REGISTRATION_LOCATOR or any(
            part.startswith(".") or part == "__pycache__"
            for part in PurePosixPath(locator).parts
        ):
            continue
        if path.suffix.lower() not in _RESOURCE_MEDIA_TYPES:
            raise SolutionCatalogError(
                f"Solution resource media type is unsupported: {locator}"
            )
        resources[locator] = path
    return resources


def _write_blank_solution_files(
    root: Path,
    *,
    solution_id: str,
    scenario_id: str,
    workspace_id: str,
    display_name: SolutionDisplayName,
    description: str,
    owner: str,
) -> None:
    """Create the minimum real package envelope without copying domain semantics."""

    now = datetime.now(timezone.utc)
    source_id = "source.solution_brief"
    package = OntologyPackage.model_validate(
        {
            "package_id": solution_id,
            "version": "0.1.0",
            "status": "confirmed",
            "created_at": now,
            "scenario": {
                "id": scenario_id,
                "version": "0.1.0",
                "status": "confirmed",
                "name": display_name.model_dump(mode="json"),
                "definition": description,
                "owner": owner,
                "sources": [source_id],
                "decisions": [],
                "tags": ["solution:blank", "authority:draft"],
            },
            "actors": [],
            "processes": [],
            "sources": [
                {
                    "id": source_id,
                    "source_type": "assumption_register",
                    "title": "Solution brief",
                    "locator": "input/solution-brief.md",
                    "owner": owner,
                    "captured_on": date.today(),
                    "trust": "assumption",
                    "notes": (
                        "System-created bootstrap context only; it is not evidence "
                        "for any domain fact."
                    ),
                }
            ],
            "decisions": [],
            "entities": [],
            "properties": [],
            "relationships": [],
            "dimensions": [],
            "rules": [],
            "metrics": [],
            "data_sources": [],
            "bindings": [],
            "joins": [],
            "sql_contracts": [],
            "analysis_patterns": [],
            "policies": [],
            "questions": [],
        }
    )

    brief_path = root / "input" / "solution-brief.md"
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text(
        "\n".join(
            (
                f"# {display_name.en}",
                "",
                description,
                "",
                "This file initializes the Draft. It is not source evidence for domain semantics.",
                "",
            )
        ),
        encoding="utf-8",
    )

    package_path = root / "ontology" / "package.yaml"
    package_path.parent.mkdir(parents=True, exist_ok=True)
    package_path.write_text(
        yaml.safe_dump(
            package.model_dump(mode="json", exclude_none=True),
            allow_unicode=True,
            sort_keys=False,
            width=120,
        ),
        encoding="utf-8",
    )

    slot_path = root / "authoring" / "semantic-slot-manifest.json"
    slot_path.parent.mkdir(parents=True, exist_ok=True)
    slot_path.write_text(
        json.dumps(
            {
                "contract": "generic-semantic-slot-manifest/v1",
                "slots": [
                    {
                        "draft_path": "solution_intent",
                        "value_kind": "STRING",
                        "authority": "HUMAN_REVIEWED_DRAFT",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    descriptor_path = root / "authoring" / "editor-descriptor.json"
    descriptor_path.write_text(
        json.dumps(
            {
                "contract": "studio-editor-descriptor/v1",
                "descriptor_id": f"editor.{solution_id}",
                "version": "1.0.0",
                "workspace_id": workspace_id,
                "studio_adapter_id": _GENERIC_STUDIO_ADAPTER_ID,
                "draft_schema_version": "generic-draft-workspace/v1",
                "operations_contract": "studio-draft-operations/v1",
                "title": {
                    "en": f"{display_name.en} Draft",
                    "zh": f"{display_name.zh} Draft",
                },
                "description": {"en": description, "zh": description},
                "semantic_slot_manifest": {
                    "locator": "authoring/semantic-slot-manifest.json",
                    "sha256": file_checksum(slot_path),
                },
                "fields": [
                    {
                        "path": "solution_intent",
                        "label": {"en": "Solution intent", "zh": "解决方案目标"},
                        "help": {
                            "en": "The business outcome this ontology should support.",
                            "zh": "这套本体需要支持的业务结果。",
                        },
                        "control": "TEXTAREA",
                        "value_kind": "STRING",
                        "required": True,
                        "options": [],
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    agent_path = root / "agent" / "experience.json"
    agent_path.parent.mkdir(parents=True, exist_ok=True)
    agent_path.write_text(
        json.dumps(
            {
                "contract": "agent-experience/v1",
                "solution_id": solution_id,
                "status": "NOT_CONFIGURED",
                "question_families": [],
                "tools": [],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    evaluation_path = root / "evaluation" / "reference-evaluation.json"
    evaluation_path.parent.mkdir(parents=True, exist_ok=True)
    evaluation_path.write_text(
        json.dumps(
            {
                "contract": "reference-evaluation/v1",
                "solution_id": solution_id,
                "status": "NOT_CONFIGURED",
                "cases": [],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def verify_solution_components(
    subject: SolutionRegistrationSubjectV1, component_root: Path
) -> None:
    root = component_root.resolve()
    if not root.is_dir():
        raise SolutionCatalogError("Solution component root is unavailable")
    if subject.resources:
        paths = _resource_paths(root)
        declared = {item.locator: item for item in subject.resources}
        if set(paths) != set(declared):
            raise SolutionCatalogError(
                "Solution package resource inventory does not match the directory"
            )
        for locator, resource in declared.items():
            path = paths[locator]
            if (
                path.stat().st_size != resource.size_bytes
                or file_checksum(path) != resource.sha256
                or _RESOURCE_MEDIA_TYPES[path.suffix.lower()] != resource.media_type
            ):
                raise SolutionCatalogError(
                    f"Solution resource digest mismatch or media mismatch: {locator}"
                )
    component_paths: dict[str, Path] = {}
    for component in subject.components:
        candidate = PurePosixPath(component.locator)
        path = root.joinpath(*candidate.parts).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise SolutionCatalogError(
                f"Solution component is unavailable: {component.component_id}"
            )
        if file_checksum(path) != component.sha256:
            raise SolutionCatalogError(
                f"Solution component digest mismatch: {component.component_id}"
            )
        component_paths[component.kind] = path

    try:
        semantic_package = load_package(component_paths["semantic_source"])
    except (OSError, ValueError) as exc:
        raise SolutionCatalogError("Solution semantic source is invalid") from exc
    if (
        semantic_package.package_id != subject.solution_id
        or semantic_package.version
        != (subject.semantic_source_version or subject.solution_version)
        or semantic_package.scenario.id != subject.scenario_id
        or semantic_package.scenario.name.en != subject.display_name.en
        or semantic_package.scenario.name.zh != subject.display_name.zh
    ):
        raise SolutionCatalogError(
            "Solution registration identity does not match its semantic source"
        )
    if subject.semantic_source_version is not None:
        try:
            editor = load_editor_descriptor(
                component_paths["authoring_profile"], component_root=root
            )
        except EditorDescriptorError as exc:
            raise SolutionCatalogError("Solution authoring profile is invalid") from exc
        if (
            editor.workspace_id != subject.workspace_id
            or editor.studio_adapter_id != subject.studio_adapter_id
        ):
            raise SolutionCatalogError(
                "Solution registration identity does not match its authoring profile"
            )


def _build_bundle(
    subject: SolutionRegistrationSubjectV1,
    root: Path,
    artifacts: S3ArtifactStore,
) -> SolutionBundleRecordV1:
    resources = {item.locator: item for item in subject.resources}
    paths = _resource_paths(root)
    resource_artifacts: list[SolutionResourceArtifactV1] = []
    try:
        for locator in sorted(resources):
            resource = resources[locator]
            stored = artifacts.publish_blob(
                paths[locator].read_bytes(),
                namespace=(
                    "studio/solution-resource/"
                    f"{subject.solution_id}/{subject.solution_version}"
                ),
                media_type=resource.media_type,
                suffix=Path(locator).suffix.lstrip(".").lower(),
            )
            resource_artifacts.append(
                SolutionResourceArtifactV1(locator=locator, artifact=stored)
            )
        bundle_subject = SolutionBundleSubjectV1(
            solution_id=subject.solution_id,
            solution_version=subject.solution_version,
            registration_checksum=sha256_value(subject),
            resources=subject.resources,
        )
        bundle_checksum = sha256_value(bundle_subject)
        manifest_artifact = artifacts.publish_blob(
            canonical_bytes(bundle_subject),
            namespace="studio/solution-bundle",
            media_type="application/json",
            suffix="json",
        )
    except (OSError, ProductInfrastructureError) as exc:
        raise SolutionCatalogError("Solution bundle publish failed") from exc
    return SolutionBundleRecordV1(
        subject_checksum=bundle_checksum,
        subject=bundle_subject,
        manifest_artifact=manifest_artifact,
        resource_artifacts=tuple(resource_artifacts),
    )


class SolutionCatalogService:
    def __init__(
        self,
        repository: SolutionRegistrationRepository,
        artifacts: S3ArtifactStore | None,
        *,
        manifest_path: Path,
        component_root: Path,
    ) -> None:
        self.repository = repository
        self.artifacts = artifacts
        self.manifest_path = manifest_path.resolve()
        self.component_root = component_root.resolve()

    @classmethod
    def from_settings(
        cls,
        settings: ProductInfrastructureSettings,
        *,
        manifest_path: Path,
        component_root: Path,
    ) -> SolutionCatalogService:
        if settings.mode == "legacy-compatibility":
            subject = load_solution_registration(manifest_path)
            verify_solution_components(subject, component_root)
            return cls(
                LocalSolutionRegistrationRepository(subject),
                None,
                manifest_path=manifest_path,
                component_root=component_root,
            )
        if not settings.database_url:
            raise SolutionCatalogError("Durable solution catalog settings are incomplete")
        return cls(
            PostgresSolutionRegistrationRepository(settings.database_url),
            S3ArtifactStore(settings),
            manifest_path=manifest_path,
            component_root=component_root,
        )

    def bootstrap(self) -> SolutionRegistrationRecordV1:
        subject = load_solution_registration(self.manifest_path)
        verify_solution_components(subject, self.component_root)
        if self.artifacts is None:
            return self.repository.get(subject.solution_id, subject.solution_version)
        try:
            artifact = self.artifacts.publish_blob(
                canonical_bytes(subject),
                namespace="studio/solution-registration",
                media_type="application/json",
                suffix="json",
            )
        except ProductInfrastructureError as exc:
            raise SolutionCatalogError("Solution registration publish failed") from exc
        bundle = _build_bundle(subject, self.component_root, self.artifacts)
        self.repository.register(subject, artifact, bundle)
        return self.get(subject.solution_id, subject.solution_version)

    def install(
        self,
        subject: SolutionRegistrationSubjectV1,
        component_root: Path,
    ) -> SolutionRegistrationRecordV1:
        """Install one newly compiled immutable package into the durable catalog."""

        if self.artifacts is None:
            raise SolutionCatalogError(
                "Creating solutions requires the durable PostgreSQL/S3 catalog"
            )
        root = component_root.resolve()
        verify_solution_components(subject, root)
        try:
            artifact = self.artifacts.publish_blob(
                canonical_bytes(subject),
                namespace="studio/solution-registration",
                media_type="application/json",
                suffix="json",
            )
        except ProductInfrastructureError as exc:
            raise SolutionCatalogError("Solution registration publish failed") from exc
        bundle = _build_bundle(subject, root, self.artifacts)
        self.repository.register(subject, artifact, bundle)
        return self.get(subject.solution_id, subject.solution_version)

    def clone_template(
        self,
        template: SolutionRegistrationRecordV1,
        *,
        solution_id: str,
        scenario_id: str,
        workspace_id: str,
        display_name: SolutionDisplayName,
        description: str,
    ) -> SolutionRegistrationRecordV1:
        """Compile a new draft-capable solution from one installed template package.

        Template bytes are copied into an isolated staging directory. Only the bounded
        package/scenario/workspace identities and human-facing title are rewritten;
        the complete resource inventory is then recomputed before registration.
        """

        if template.subject.studio_adapter_id not in {
            "studio-adapter.adt.reference@1",
            "studio-adapter.cash-trading.reference@1",
            _GENERIC_STUDIO_ADAPTER_ID,
        }:
            raise SolutionCatalogError("The selected template adapter is not clonable")
        template_root = self.materialize(template, Path(tempfile.gettempdir()) / "ontology-template-cache")
        with tempfile.TemporaryDirectory(prefix="ontology-solution-create-") as temporary:
            root = Path(temporary) / "solution"
            shutil.copytree(
                template_root,
                root,
                ignore=shutil.ignore_patterns(".solution-bundle.json", "__pycache__"),
            )

            package_path = root / "ontology" / "package.yaml"
            descriptor_path = root / "authoring" / "editor-descriptor.json"
            package_path.chmod(0o644)
            descriptor_path.chmod(0o644)
            try:
                package_payload = yaml.safe_load(package_path.read_text(encoding="utf-8"))
                descriptor_payload = json.loads(descriptor_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
                raise SolutionCatalogError("Template identity files are invalid") from exc
            if not isinstance(package_payload, dict) or not isinstance(descriptor_payload, dict):
                raise SolutionCatalogError("Template identity files are invalid")

            package_payload["package_id"] = solution_id
            package_payload["version"] = "1.0.0"
            scenario = package_payload.get("scenario")
            if not isinstance(scenario, dict):
                raise SolutionCatalogError("Template scenario is unavailable")
            scenario["id"] = scenario_id
            scenario["name"] = display_name.model_dump(mode="json")
            scenario["definition"] = description
            package_path.write_text(
                yaml.safe_dump(
                    package_payload,
                    allow_unicode=True,
                    sort_keys=False,
                    width=120,
                ),
                encoding="utf-8",
            )

            descriptor_payload["workspace_id"] = workspace_id
            descriptor_payload["descriptor_id"] = f"editor.{solution_id}"
            descriptor_payload["title"] = {
                "en": f"{display_name.en} semantic draft",
                "zh": f"{display_name.zh}语义草稿",
            }
            descriptor_payload["description"] = {
                "en": description,
                "zh": description,
            }
            descriptor_path.write_text(
                json.dumps(
                    descriptor_payload,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            paths = _resource_paths(root)
            resources = tuple(
                SolutionResourceDescriptor(
                    locator=locator,
                    media_type=_RESOURCE_MEDIA_TYPES[path.suffix.lower()],
                    sha256=file_checksum(path),
                    size_bytes=path.stat().st_size,
                )
                for locator, path in sorted(paths.items())
            )
            resources_by_locator = {item.locator: item for item in resources}
            components = tuple(
                SolutionComponentDescriptor(
                    component_id=f"component.{solution_id}.{component.kind}",
                    kind=component.kind,
                    locator=component.locator,
                    media_type=component.media_type,
                    sha256=resources_by_locator[component.locator].sha256,
                )
                for component in template.subject.components
            )
            subject = SolutionRegistrationSubjectV1(
                solution_id=solution_id,
                solution_version="1.0.0",
                semantic_source_version="1.0.0",
                scenario_id=scenario_id,
                workspace_id=workspace_id,
                studio_adapter_id=template.subject.studio_adapter_id,
                authoring_root_id=f"solution-root.{solution_id}",
                display_name=display_name,
                components=components,
                resources=resources,
                limitations=tuple(
                    dict.fromkeys(
                        (
                            *template.subject.limitations,
                            f"Created from template {template.subject.solution_id}",
                        )
                    )
                ),
            )
            return self.install(subject, root)

    def create_blank(
        self,
        *,
        solution_id: str,
        scenario_id: str,
        workspace_id: str,
        display_name: SolutionDisplayName,
        description: str,
        owner: str,
    ) -> SolutionRegistrationRecordV1:
        """Install a genuinely empty, case-neutral Draft package.

        Only the lifecycle envelope and a clearly labelled bootstrap brief exist.
        No ADT, Cash Trading, template, metric or model-generated fact is copied.
        """

        if self.artifacts is None:
            raise SolutionCatalogError(
                "Creating solutions requires the durable PostgreSQL/S3 catalog"
            )
        with tempfile.TemporaryDirectory(prefix="ontology-solution-blank-") as temporary:
            root = Path(temporary) / "solution"
            _write_blank_solution_files(
                root,
                solution_id=solution_id,
                scenario_id=scenario_id,
                workspace_id=workspace_id,
                display_name=display_name,
                description=description,
                owner=owner,
            )
            paths = _resource_paths(root)
            resources = tuple(
                SolutionResourceDescriptor(
                    locator=locator,
                    media_type=_RESOURCE_MEDIA_TYPES[path.suffix.lower()],
                    sha256=file_checksum(path),
                    size_bytes=path.stat().st_size,
                )
                for locator, path in sorted(paths.items())
            )
            resources_by_locator = {item.locator: item for item in resources}
            component_locators = {
                "authoring_profile": "authoring/editor-descriptor.json",
                "semantic_source": "ontology/package.yaml",
                "agent_experience": "agent/experience.json",
                "reference_evaluation": "evaluation/reference-evaluation.json",
            }
            components = tuple(
                SolutionComponentDescriptor(
                    component_id=f"component.{solution_id}.{kind}",
                    kind=kind,  # type: ignore[arg-type]
                    locator=locator,
                    media_type=resources_by_locator[locator].media_type,  # type: ignore[arg-type]
                    sha256=resources_by_locator[locator].sha256,
                )
                for kind, locator in component_locators.items()
            )
            subject = SolutionRegistrationSubjectV1(
                solution_id=solution_id,
                solution_version="1.0.0",
                semantic_source_version="0.1.0",
                scenario_id=scenario_id,
                workspace_id=workspace_id,
                studio_adapter_id=_GENERIC_STUDIO_ADAPTER_ID,
                authoring_root_id=f"solution-root.{solution_id}",
                display_name=display_name,
                components=components,
                resources=resources,
                limitations=(
                    "Blank Draft: no domain semantics or Agent runtime are configured.",
                ),
            )
            return self.install(subject, root)

    def _verify_record(
        self, record: SolutionRegistrationRecordV1
    ) -> SolutionRegistrationRecordV1:
        if record.persistence == "legacy-compatibility":
            verify_solution_components(record.subject, self.component_root)
        if record.artifact is not None:
            if self.artifacts is None:
                raise SolutionCatalogError("Solution artifact store is unavailable")
            try:
                body = self.artifacts.get_exact(record.artifact)
            except ProductInfrastructureError as exc:
                raise SolutionCatalogError(
                    "Solution registration exact artifact is unavailable"
                ) from exc
            try:
                artifact_subject = SolutionRegistrationSubjectV1.model_validate_json(body)
            except ValueError as exc:
                raise SolutionCatalogError(
                    "Solution registration artifact mismatch"
                ) from exc
            if artifact_subject != record.subject:
                raise SolutionCatalogError("Solution registration artifact mismatch")
        if record.bundle is not None:
            if self.artifacts is None:
                raise SolutionCatalogError("Solution artifact store is unavailable")
            try:
                manifest = self.artifacts.get_exact(
                    record.bundle.manifest_artifact
                )
                if manifest != canonical_bytes(record.bundle.subject):
                    raise SolutionCatalogError("Solution bundle manifest mismatch")
                expected = {
                    item.locator: item for item in record.subject.resources
                }
                for item in record.bundle.resource_artifacts:
                    body = self.artifacts.get_exact(item.artifact)
                    resource = expected[item.locator]
                    if (
                        len(body) != resource.size_bytes
                        or hashlib.sha256(body).hexdigest() != resource.sha256
                    ):
                        raise SolutionCatalogError(
                            "Solution bundle resource mismatch"
                        )
            except (KeyError, ProductInfrastructureError) as exc:
                raise SolutionCatalogError(
                    "Solution bundle exact artifact is unavailable"
                ) from exc
        return record

    def materialize(
        self,
        record: SolutionRegistrationRecordV1,
        cache_root: Path,
    ) -> Path:
        """Materialize one exact installed bundle into a verified read-only cache."""

        verified = self._verify_record(record)
        if verified.bundle is None or self.artifacts is None:
            if verified.persistence == "legacy-compatibility":
                return self.component_root
            raise SolutionCatalogError("Solution registration is not installable")
        target = (
            cache_root.resolve()
            / verified.subject.solution_id
            / verified.subject.solution_version
            / verified.bundle.subject_checksum
        )

        def verify_cache(path: Path) -> bool:
            marker = path / ".solution-bundle.json"
            try:
                marker_payload = json.loads(marker.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                return False
            if marker_payload.get("bundle_subject_checksum") != verified.bundle.subject_checksum:
                return False
            for resource in verified.subject.resources:
                candidate = path.joinpath(*PurePosixPath(resource.locator).parts)
                if (
                    not candidate.is_file()
                    or candidate.stat().st_size != resource.size_bytes
                    or file_checksum(candidate) != resource.sha256
                ):
                    return False
            return True

        target.parent.mkdir(parents=True, exist_ok=True)
        lock_path = target.parent / f".{verified.bundle.subject_checksum}.install.lock"
        with lock_path.open("a+b") as lock_stream:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX)
            try:
                # Another process may have completed the exact install while this
                # caller was waiting. Verify the bytes again under the same lock.
                if target.exists():
                    if not verify_cache(target):
                        raise SolutionCatalogError("Installed solution cache is invalid")
                    return target

                temporary = Path(
                    tempfile.mkdtemp(prefix=".install-", dir=target.parent)
                )
                try:
                    artifacts_by_locator = {
                        item.locator: item.artifact
                        for item in verified.bundle.resource_artifacts
                    }
                    for resource in verified.subject.resources:
                        destination = temporary.joinpath(
                            *PurePosixPath(resource.locator).parts
                        )
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_bytes(
                            self.artifacts.get_exact(
                                artifacts_by_locator[resource.locator]
                            )
                        )
                        destination.chmod(0o444)
                    (temporary / ".solution-bundle.json").write_bytes(
                        canonical_bytes(
                            {
                                "contract": "installed-solution-cache/v1",
                                "bundle_subject_checksum": (
                                    verified.bundle.subject_checksum
                                ),
                            }
                        )
                    )
                    os.rename(temporary, target)
                    if not verify_cache(target):
                        raise SolutionCatalogError(
                            "Installed solution cache verification failed"
                        )
                    return target
                except (KeyError, OSError, ProductInfrastructureError):
                    if temporary.exists():
                        shutil.rmtree(temporary)
                    raise SolutionCatalogError(
                        "Solution bundle materialization failed"
                    )
            finally:
                fcntl.flock(lock_stream.fileno(), fcntl.LOCK_UN)

    def get(
        self, solution_id: str, solution_version: str
    ) -> SolutionRegistrationRecordV1:
        return self._verify_record(self.repository.get(solution_id, solution_version))

    def list(self) -> tuple[SolutionRegistrationRecordV1, ...]:
        return tuple(self._verify_record(record) for record in self.repository.list())


class CompositeLocalSolutionCatalog:
    """Read-only composition of exact local packages for the engineering demo.

    Durable deployments still use one PostgreSQL/S3 catalog. This small composition
    exists only because legacy-compatibility repositories deliberately contain one
    immutable local registration each.
    """

    def __init__(self, services: tuple[SolutionCatalogService, ...]) -> None:
        if not services:
            raise SolutionCatalogError("Composite solution catalog is empty")
        self.services = services
        index: dict[tuple[str, str], SolutionCatalogService] = {}
        for service in services:
            for record in service.list():
                key = (record.subject.solution_id, record.subject.solution_version)
                if key in index:
                    raise SolutionCatalogError(
                        "Composite solution catalog contains a duplicate alias"
                    )
                index[key] = service
        self._index = index

    def get(
        self, solution_id: str, solution_version: str
    ) -> SolutionRegistrationRecordV1:
        try:
            service = self._index[(solution_id, solution_version)]
        except KeyError as exc:
            raise SolutionCatalogError("Solution registration is not installed") from exc
        return service.get(solution_id, solution_version)

    def list(self) -> tuple[SolutionRegistrationRecordV1, ...]:
        return tuple(
            self.get(solution_id, solution_version)
            for solution_id, solution_version in sorted(self._index)
        )

    def materialize(
        self,
        record: SolutionRegistrationRecordV1,
        cache_root: Path,
    ) -> Path:
        key = (record.subject.solution_id, record.subject.solution_version)
        try:
            service = self._index[key]
        except KeyError as exc:
            raise SolutionCatalogError("Solution registration is not installed") from exc
        return service.materialize(record, cache_root)
