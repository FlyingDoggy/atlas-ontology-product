from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import zipfile
from io import BytesIO
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Mapping, Protocol

from pydantic import Field, model_validator
from openpyxl import load_workbook
from sqlalchemy import DateTime, ForeignKey, String, create_engine, func, select
from sqlalchemy.dialects.postgresql import JSONB, insert as pg_insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..contracts import Sha256
from ..io import sha256_value, write_json
from ..models import StrictModel
from ..product_context import (
    Base,
    ExactStoredArtifactRef,
    ProductInfrastructureError,
    ProductInfrastructureSettings,
    S3ArtifactStore,
)


SourceKind = Literal[
    "requirement_transcription",
    "metric_transcription",
    "data_model",
    "data_dictionary",
    "sql",
    "other",
]

_SINGLETON_SOURCE_IDS: dict[str, str] = {
    "requirement_transcription": "asset.requirements",
    "metric_transcription": "asset.metric_logic",
}
_TEXT_KINDS = {"requirement_transcription", "metric_transcription"}
_MAX_SOURCE_BYTES = 20 * 1024 * 1024

_INSTALLED_SOURCE_TITLES: dict[str, str] = {
    "requirement_transcription": "需求与分析流程",
    "metric_transcription": "指标逻辑",
    "data_model": "数据模型",
    "data_dictionary": "数据字典与样例",
    "sql": "现有计算 SQL",
    "other": "其他来源材料",
}


def _logical_source_id(kind: SourceKind, original_name: str) -> str:
    """Return the stable identity of one logical input document.

    The two template transcriptions are intentional singleton slots. Attachments are
    collections: two dictionaries or SQL files must coexist, while re-uploading the
    same filename (case-insensitively) creates a new immutable version of that one
    logical document.
    """

    singleton = _SINGLETON_SOURCE_IDS.get(kind)
    if singleton is not None:
        return singleton
    normalized = unicodedata.normalize("NFC", original_name).casefold()
    digest = hashlib.sha256(f"{kind}\0{normalized}".encode("utf-8")).hexdigest()[:24]
    return f"asset.{kind}.{digest}"


class SourceLibraryError(RuntimeError):
    """A source version cannot be registered or read with exact identity."""


class SourceLibraryConflict(SourceLibraryError):
    """An immutable source identity already names different bytes or metadata."""


class StudioSourceVersionV1(StrictModel):
    contract: Literal["studio-source-version/v1"] = "studio-source-version/v1"
    persistence: Literal["local-compatibility", "postgresql-s3"]
    source_version_id: str = Field(pattern=r"^source-version\.[0-9a-f]{32}$")
    workspace_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    source_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    kind: SourceKind
    title: str = Field(min_length=1, max_length=500)
    original_name: str = Field(min_length=1, max_length=500)
    media_type: str = Field(min_length=1, max_length=255)
    processing_mode: Literal[
        "TRANSCRIBED",
        "STRUCTURED_TRANSCRIPTION",
        "REGISTERED_NOT_PARSED",
    ]
    content_checksum: Sha256
    size_bytes: int = Field(ge=1, le=_MAX_SOURCE_BYTES)
    registered_at: datetime
    artifact: ExactStoredArtifactRef | None = None
    subject_checksum: Sha256

    @model_validator(mode="after")
    def validate_exact_identity(self) -> StudioSourceVersionV1:
        unsigned = self.model_dump(mode="json", exclude={"subject_checksum"})
        if sha256_value(unsigned) != self.subject_checksum:
            raise ValueError("Source version subject checksum mismatch")
        if self.persistence == "postgresql-s3":
            if self.artifact is None:
                raise ValueError("Durable source version requires an exact artifact")
            if (
                self.artifact.sha256 != self.content_checksum
                or self.artifact.size_bytes != self.size_bytes
                or self.artifact.media_type != self.media_type
            ):
                raise ValueError("Source artifact identity mismatch")
        elif self.artifact is not None:
            raise ValueError("Local source version cannot claim an S3 artifact")
        return self


class SourcePreviewLineV1(StrictModel):
    line_number: int = Field(ge=1)
    text: str
    snippet_checksum: Sha256


class SourcePreviewCellV1(StrictModel):
    cell: str = Field(pattern=r"^[A-Z]+[1-9][0-9]*$")
    display_value: str | int | float | bool | None
    raw_formula: str | None = None
    snippet_checksum: Sha256


class SourcePreviewSheetV1(StrictModel):
    sheet_name: str = Field(min_length=1, max_length=255)
    used_range: str = Field(min_length=1, max_length=100)
    cells: tuple[SourcePreviewCellV1, ...]
    truncated: bool


class StudioSourcePreviewV1(StrictModel):
    contract: Literal["studio-source-preview/v1"] = "studio-source-preview/v1"
    source_version_id: str = Field(pattern=r"^source-version\.[0-9a-f]{32}$")
    content_checksum: Sha256
    parser_build: Literal["ontology-studio/source-preview@1"] = (
        "ontology-studio/source-preview@1"
    )
    status: Literal["PARSED", "REGISTERED_NOT_PARSED"]
    text_lines: tuple[SourcePreviewLineV1, ...] = ()
    sheets: tuple[SourcePreviewSheetV1, ...] = ()
    limitation: str | None = None


class ReferenceSourcePackFileV1(StrictModel):
    file_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    locator: str = Field(min_length=1, max_length=500)
    original_name: str = Field(min_length=1, max_length=500)
    media_type: str = Field(min_length=1, max_length=255)
    sha256: Sha256
    size_bytes: int = Field(ge=1, le=_MAX_SOURCE_BYTES)

    @model_validator(mode="after")
    def validate_locator(self) -> ReferenceSourcePackFileV1:
        candidate = PurePosixPath(self.locator)
        if candidate.is_absolute() or not candidate.parts or ".." in candidate.parts:
            raise ValueError("Reference source locator is unsafe")
        if Path(self.original_name).name != self.original_name:
            raise ValueError("Reference source original name is unsafe")
        return self


class ReferenceSourcePackRegistrationV1(StrictModel):
    source_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    file_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    kind: SourceKind
    title: str = Field(min_length=1, max_length=500)


class ReferenceSourcePackV1(StrictModel):
    contract: Literal["ontology-reference-source-pack/v1"] = (
        "ontology-reference-source-pack/v1"
    )
    pack_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    title: str = Field(min_length=1, max_length=500)
    classification: Literal["constructed_synthetic"]
    claim_ceiling: Literal["CONSTRUCTED_SYNTHETIC_NOT_HKEX_VALIDATED"]
    physical_file_count: int = Field(ge=1, le=64)
    files: tuple[ReferenceSourcePackFileV1, ...] = Field(min_length=1, max_length=64)
    registrations: tuple[ReferenceSourcePackRegistrationV1, ...] = Field(
        min_length=1, max_length=128
    )
    limitations: tuple[str, ...] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def validate_inventory(self) -> ReferenceSourcePackV1:
        file_ids = [item.file_id for item in self.files]
        locators = [item.locator for item in self.files]
        source_ids = [item.source_id for item in self.registrations]
        if self.physical_file_count != len(self.files):
            raise ValueError("Reference source physical file count mismatch")
        if len(file_ids) != len(set(file_ids)) or len(locators) != len(set(locators)):
            raise ValueError("Reference source files must have unique identities")
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("Reference source registrations must have unique source IDs")
        referenced = {item.file_id for item in self.registrations}
        if referenced != set(file_ids):
            raise ValueError("Every reference source file must be registered")
        return self


class ReferenceSourcePackInstallV1(StrictModel):
    contract: Literal["ontology-reference-source-pack-install/v1"] = (
        "ontology-reference-source-pack-install/v1"
    )
    pack_id: str
    workspace_id: str
    physical_file_count: int
    registered_source_count: int
    source_version_ids: tuple[str, ...]
    source_content_checksums: tuple[Sha256, ...]
    manifest_checksum: Sha256
    subject_checksum: Sha256

    @model_validator(mode="after")
    def validate_subject_checksum(self) -> ReferenceSourcePackInstallV1:
        unsigned = self.model_dump(mode="json", exclude={"subject_checksum"})
        if sha256_value(unsigned) != self.subject_checksum:
            raise ValueError("Reference source install checksum mismatch")
        if self.registered_source_count != len(self.source_version_ids):
            raise ValueError("Reference source install count mismatch")
        return self


def _version(
    *,
    persistence: Literal["local-compatibility", "postgresql-s3"],
    workspace_id: str,
    source_id: str,
    kind: SourceKind,
    title: str,
    original_name: str,
    media_type: str,
    body: bytes,
    artifact: ExactStoredArtifactRef | None,
    registered_at: datetime | None = None,
) -> StudioSourceVersionV1:
    content_checksum = hashlib.sha256(body).hexdigest()
    identity = {
        "workspace_id": workspace_id,
        "source_id": source_id,
        "kind": kind,
        "title": title,
        "original_name": original_name,
        "media_type": media_type,
        "content_checksum": content_checksum,
    }
    timestamp = registered_at or datetime.now(timezone.utc)
    unsigned: dict[str, Any] = {
        "contract": "studio-source-version/v1",
        "persistence": persistence,
        "source_version_id": "source-version." + sha256_value(identity)[:32],
        **identity,
        "processing_mode": (
            "STRUCTURED_TRANSCRIPTION"
            if kind in _TEXT_KINDS
            and (
                media_type
                == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                or original_name.lower().endswith(".xlsx")
            )
            else "TRANSCRIBED"
            if kind in _TEXT_KINDS
            else "REGISTERED_NOT_PARSED"
        ),
        "size_bytes": len(body),
        "registered_at": timestamp.isoformat().replace("+00:00", "Z"),
        "artifact": artifact.model_dump(mode="json") if artifact is not None else None,
    }
    return StudioSourceVersionV1(
        **unsigned,
        subject_checksum=sha256_value(unsigned),
    )


class SourceLibraryStore(Protocol):
    def register(
        self,
        *,
        workspace_id: str,
        source_id: str,
        kind: SourceKind,
        title: str,
        original_name: str,
        media_type: str,
        body: bytes,
    ) -> StudioSourceVersionV1: ...

    def list_current(self, workspace_id: str) -> tuple[StudioSourceVersionV1, ...]: ...

    def list_versions(self, workspace_id: str) -> tuple[StudioSourceVersionV1, ...]: ...

    def read_exact(self, version: StudioSourceVersionV1) -> bytes: ...


class FileSourceLibraryStore:
    """Narrow compatibility store for tests and offline authoring."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _workspace(self, workspace_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", workspace_id):
            raise SourceLibraryError("Source workspace identity is invalid")
        return self.root / workspace_id

    def _record_path(self, workspace_id: str, source_version_id: str) -> Path:
        return self._workspace(workspace_id) / "versions" / f"{source_version_id}.json"

    def _blob_path(self, workspace_id: str, source_version_id: str) -> Path:
        return self._workspace(workspace_id) / "blobs" / f"{source_version_id}.bin"

    def _head_path(self, workspace_id: str) -> Path:
        return self._workspace(workspace_id) / "current.json"

    def register(
        self,
        *,
        workspace_id: str,
        source_id: str,
        kind: SourceKind,
        title: str,
        original_name: str,
        media_type: str,
        body: bytes,
    ) -> StudioSourceVersionV1:
        version = _version(
            persistence="local-compatibility",
            workspace_id=workspace_id,
            source_id=source_id,
            kind=kind,
            title=title,
            original_name=original_name,
            media_type=media_type,
            body=body,
            artifact=None,
        )
        record_path = self._record_path(workspace_id, version.source_version_id)
        blob_path = self._blob_path(workspace_id, version.source_version_id)
        if record_path.exists():
            existing = self._load(record_path)
            if existing.model_dump(
                mode="json", exclude={"registered_at", "subject_checksum"}
            ) != version.model_dump(
                mode="json", exclude={"registered_at", "subject_checksum"}
            ):
                raise SourceLibraryConflict("Source version identity conflict")
            if self.read_exact(existing) != body:
                raise SourceLibraryConflict("Source version bytes conflict")
            version = existing
        else:
            blob_path.parent.mkdir(parents=True, exist_ok=True)
            blob_path.write_bytes(body)
            write_json(record_path, version.model_dump(mode="json"))
        head_path = self._head_path(workspace_id)
        heads = json.loads(head_path.read_text(encoding="utf-8")) if head_path.exists() else {}
        for key, source_version_id in tuple(heads.items()):
            existing_head = self._load(self._record_path(workspace_id, source_version_id))
            if existing_head.source_id != source_id:
                continue
            if existing_head.kind != kind:
                raise SourceLibraryConflict("Logical source identity changed kind")
            del heads[key]
        heads[source_id] = version.source_version_id
        write_json(head_path, heads)
        return version

    @staticmethod
    def _load(path: Path) -> StudioSourceVersionV1:
        try:
            return StudioSourceVersionV1.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SourceLibraryError("Source version metadata is invalid") from exc

    def list_current(self, workspace_id: str) -> tuple[StudioSourceVersionV1, ...]:
        path = self._head_path(workspace_id)
        if not path.exists():
            return ()
        try:
            heads = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SourceLibraryError("Source head is invalid") from exc
        return tuple(
            self._load(self._record_path(workspace_id, source_version_id))
            for _, source_version_id in sorted(heads.items())
        )

    def list_versions(self, workspace_id: str) -> tuple[StudioSourceVersionV1, ...]:
        directory = self._workspace(workspace_id) / "versions"
        if not directory.is_dir():
            return ()
        return tuple(
            sorted(
                (self._load(path) for path in directory.glob("source-version.*.json")),
                key=lambda item: (item.registered_at, item.source_version_id),
                reverse=True,
            )
        )

    def read_exact(self, version: StudioSourceVersionV1) -> bytes:
        if version.persistence != "local-compatibility":
            raise SourceLibraryError("Source persistence mode mismatch")
        path = self._blob_path(version.workspace_id, version.source_version_id)
        try:
            body = path.read_bytes()
        except OSError as exc:
            raise SourceLibraryError("Source version bytes are unavailable") from exc
        if len(body) != version.size_bytes or hashlib.sha256(body).hexdigest() != version.content_checksum:
            raise SourceLibraryError("Source version bytes failed exact read-back")
        return body


class StudioSourceVersionRow(Base):
    __tablename__ = "studio_source_version"

    source_version_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    content_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_checksum: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    subject: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    artifact: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class StudioSourceHeadRow(Base):
    __tablename__ = "studio_source_head"

    workspace_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    kind: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_version_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("studio_source_version.source_version_id", ondelete="RESTRICT"), nullable=False
    )
    subject_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PostgresS3SourceLibraryStore:
    def __init__(self, database_url: str, artifacts: S3ArtifactStore) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.artifacts = artifacts

    @classmethod
    def from_settings(cls, settings: ProductInfrastructureSettings) -> PostgresS3SourceLibraryStore:
        if settings.mode != "postgresql-s3" or not settings.database_url:
            raise SourceLibraryError("Durable source library settings are incomplete")
        return cls(settings.database_url, S3ArtifactStore(settings))

    @staticmethod
    def _from_row(row: StudioSourceVersionRow) -> StudioSourceVersionV1:
        try:
            version = StudioSourceVersionV1.model_validate(row.subject)
            if version.artifact is None or version.artifact.model_dump(mode="json") != row.artifact:
                raise ValueError("artifact mismatch")
            if version.subject_checksum != row.subject_checksum:
                raise ValueError("subject mismatch")
            return version
        except ValueError as exc:
            raise SourceLibraryError("Durable source version is invalid") from exc

    def register(
        self,
        *,
        workspace_id: str,
        source_id: str,
        kind: SourceKind,
        title: str,
        original_name: str,
        media_type: str,
        body: bytes,
    ) -> StudioSourceVersionV1:
        try:
            artifact = self.artifacts.publish_blob(
                body,
                namespace=f"studio/source/{workspace_id}/{kind}",
                media_type=media_type,
                suffix="bin",
            )
            version = _version(
                persistence="postgresql-s3",
                workspace_id=workspace_id,
                source_id=source_id,
                kind=kind,
                title=title,
                original_name=original_name,
                media_type=media_type,
                body=body,
                artifact=artifact,
            )
            with Session(self.engine) as session, session.begin():
                existing = session.get(StudioSourceVersionRow, version.source_version_id)
                if existing is None:
                    session.add(
                        StudioSourceVersionRow(
                            source_version_id=version.source_version_id,
                            workspace_id=workspace_id,
                            source_id=source_id,
                            kind=kind,
                            content_checksum=version.content_checksum,
                            subject_checksum=version.subject_checksum,
                            subject=version.model_dump(mode="json"),
                            artifact=artifact.model_dump(mode="json"),
                            registered_at=version.registered_at,
                        )
                    )
                    session.flush()
                else:
                    persisted = self._from_row(existing)
                    if persisted.model_dump(
                        mode="json", exclude={"registered_at", "subject_checksum"}
                    ) != version.model_dump(
                        mode="json", exclude={"registered_at", "subject_checksum"}
                    ):
                        raise SourceLibraryConflict("Source version identity conflict")
                    version = persisted
                statement = pg_insert(StudioSourceHeadRow).values(
                    workspace_id=workspace_id,
                    source_id=source_id,
                    kind=kind,
                    source_version_id=version.source_version_id,
                    subject_checksum=version.subject_checksum,
                )
                statement = statement.on_conflict_do_update(
                    index_elements=[
                        StudioSourceHeadRow.workspace_id,
                        StudioSourceHeadRow.source_id,
                    ],
                    set_={
                        "source_version_id": version.source_version_id,
                        "subject_checksum": version.subject_checksum,
                        "updated_at": func.now(),
                    },
                    where=StudioSourceHeadRow.kind == kind,
                ).returning(StudioSourceHeadRow.source_id)
                committed_source_id = session.scalar(statement)
                if committed_source_id != source_id:
                    raise SourceLibraryConflict("Logical source identity changed kind")
            self.read_exact(version)
            return version
        except SourceLibraryError:
            raise
        except (IntegrityError, SQLAlchemyError, ProductInfrastructureError) as exc:
            raise SourceLibraryError("Durable source registration failed") from exc

    def list_current(self, workspace_id: str) -> tuple[StudioSourceVersionV1, ...]:
        try:
            with Session(self.engine) as session:
                rows = session.scalars(
                    select(StudioSourceVersionRow)
                    .join(
                        StudioSourceHeadRow,
                        StudioSourceHeadRow.source_version_id == StudioSourceVersionRow.source_version_id,
                    )
                    .where(StudioSourceHeadRow.workspace_id == workspace_id)
                    .order_by(
                        StudioSourceVersionRow.kind,
                        StudioSourceVersionRow.source_id,
                    )
                ).all()
            versions = tuple(self._from_row(row) for row in rows)
            for version in versions:
                self.read_exact(version)
            return versions
        except SourceLibraryError:
            raise
        except SQLAlchemyError as exc:
            raise SourceLibraryError("Durable source heads are unavailable") from exc

    def list_versions(self, workspace_id: str) -> tuple[StudioSourceVersionV1, ...]:
        try:
            with Session(self.engine) as session:
                rows = session.scalars(
                    select(StudioSourceVersionRow)
                    .where(StudioSourceVersionRow.workspace_id == workspace_id)
                    .order_by(StudioSourceVersionRow.registered_at.desc())
                ).all()
            return tuple(self._from_row(row) for row in rows)
        except SourceLibraryError:
            raise
        except SQLAlchemyError as exc:
            raise SourceLibraryError("Durable source history is unavailable") from exc

    def read_exact(self, version: StudioSourceVersionV1) -> bytes:
        if version.persistence != "postgresql-s3" or version.artifact is None:
            raise SourceLibraryError("Source persistence mode mismatch")
        try:
            return self.artifacts.get_exact(version.artifact)
        except ProductInfrastructureError as exc:
            raise SourceLibraryError("Durable source bytes failed exact read-back") from exc


class StudioSourceLibraryService:
    def __init__(self, store: SourceLibraryStore) -> None:
        self.store = store

    @classmethod
    def from_settings(
        cls,
        settings: ProductInfrastructureSettings,
        *,
        local_root: Path,
    ) -> StudioSourceLibraryService:
        store: SourceLibraryStore = (
            PostgresS3SourceLibraryStore.from_settings(settings)
            if settings.mode == "postgresql-s3"
            else FileSourceLibraryStore(local_root)
        )
        return cls(store)

    def register(
        self,
        *,
        workspace_id: str,
        kind: SourceKind,
        title: str,
        original_name: str,
        media_type: str,
        body: bytes,
        source_id: str | None = None,
    ) -> StudioSourceVersionV1:
        if not body:
            raise SourceLibraryError("Source body is empty")
        if len(body) > _MAX_SOURCE_BYTES:
            raise SourceLibraryError("Source body exceeds the 20 MiB limit")
        normalized_title = title.strip()
        normalized_name = Path(original_name.strip()).name
        normalized_type = media_type.split(";", 1)[0].strip().lower()
        if not normalized_title or not normalized_name or not normalized_type:
            raise SourceLibraryError("Source metadata is incomplete")
        if kind in _TEXT_KINDS:
            structured_xlsx = (
                normalized_type
                == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                or normalized_name.lower().endswith(".xlsx")
            )
            if not structured_xlsx and normalized_type not in {
                "text/plain",
                "text/markdown",
            }:
                raise SourceLibraryError(
                    "Transcribed sources must be UTF-8 text, Markdown or an XLSX template"
                )
            if structured_xlsx:
                self._xlsx_archive_is_bounded(body)
            else:
                try:
                    body.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise SourceLibraryError("Transcribed sources must be valid UTF-8") from exc
        effective_source_id = source_id or _logical_source_id(kind, normalized_name)
        if source_id is not None and not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]*", source_id
        ):
            raise SourceLibraryError("Logical source identity is invalid")
        # Preserve the identity written by the previous schema when upgrading an
        # existing attachment. This keeps immutable history connected across 0012.
        if source_id is None and kind not in _SINGLETON_SOURCE_IDS:
            existing = next(
                (
                    item
                    for item in self.list_current(workspace_id)
                    if item.kind == kind
                    and unicodedata.normalize("NFC", item.original_name).casefold()
                    == unicodedata.normalize("NFC", normalized_name).casefold()
                ),
                None,
            )
            if existing is not None:
                effective_source_id = existing.source_id
        return self.store.register(
            workspace_id=workspace_id,
            source_id=effective_source_id,
            kind=kind,
            title=normalized_title,
            original_name=normalized_name,
            media_type=normalized_type,
            body=body,
        )

    def install_reference_pack(
        self,
        *,
        workspace_id: str,
        component_root: Path,
        manifest_path: Path,
    ) -> ReferenceSourcePackInstallV1:
        root = component_root.resolve()
        exact_manifest = manifest_path.resolve()
        if not exact_manifest.is_relative_to(root) or not exact_manifest.is_file():
            raise SourceLibraryError("Reference source pack manifest is unavailable")
        try:
            manifest_body = exact_manifest.read_bytes()
            pack = ReferenceSourcePackV1.model_validate_json(manifest_body)
        except (OSError, ValueError) as exc:
            raise SourceLibraryError("Reference source pack manifest is invalid") from exc

        files: dict[str, tuple[ReferenceSourcePackFileV1, bytes]] = {}
        for declared in pack.files:
            candidate = root.joinpath(*PurePosixPath(declared.locator).parts).resolve()
            if not candidate.is_relative_to(root) or not candidate.is_file():
                raise SourceLibraryError(
                    f"Reference source file is unavailable: {declared.file_id}"
                )
            try:
                body = candidate.read_bytes()
            except OSError as exc:
                raise SourceLibraryError(
                    f"Reference source file is unreadable: {declared.file_id}"
                ) from exc
            if (
                len(body) != declared.size_bytes
                or hashlib.sha256(body).hexdigest() != declared.sha256
            ):
                raise SourceLibraryError(
                    f"Reference source file identity mismatch: {declared.file_id}"
                )
            files[declared.file_id] = (declared, body)

        installed: list[StudioSourceVersionV1] = []
        for item in pack.registrations:
            declared, body = files[item.file_id]
            installed.append(
                self.register(
                    workspace_id=workspace_id,
                    source_id=item.source_id,
                    kind=item.kind,
                    title=item.title,
                    original_name=declared.original_name,
                    media_type=declared.media_type,
                    body=body,
                )
            )
        unsigned = {
            "contract": "ontology-reference-source-pack-install/v1",
            "pack_id": pack.pack_id,
            "workspace_id": workspace_id,
            "physical_file_count": pack.physical_file_count,
            "registered_source_count": len(installed),
            "source_version_ids": tuple(item.source_version_id for item in installed),
            "source_content_checksums": tuple(
                item.content_checksum for item in installed
            ),
            "manifest_checksum": hashlib.sha256(manifest_body).hexdigest(),
        }
        return ReferenceSourcePackInstallV1(
            **unsigned,
            subject_checksum=sha256_value(unsigned),
        )

    def import_installed_assets(
        self,
        *,
        workspace_id: str,
        component_root: Path,
        assets: tuple[Mapping[str, Any], ...],
        resources: tuple[Mapping[str, Any], ...],
    ) -> tuple[StudioSourceVersionV1, ...]:
        """Version declared intake assets after exact package verification.

        Installed solution files predate the Source Library in some packages.  They
        are useful evidence, but a package locator or checksum alone is not a source
        version that the UI can preview and cite.  This explicit mutation verifies
        every intake asset against the signed package inventory and exact bytes
        before registering an immutable, idempotent source version.
        """

        root = component_root.resolve()
        declared_resources: dict[str, Mapping[str, Any]] = {}
        for resource in resources:
            locator = str(resource.get("locator", ""))
            if not locator or locator in declared_resources:
                raise SourceLibraryError(
                    "Installed solution resource inventory is incomplete or ambiguous"
                )
            declared_resources[locator] = resource

        if not assets:
            raise SourceLibraryError("Installed solution has no intake assets to version")

        installed: list[StudioSourceVersionV1] = []
        seen_source_ids: set[str] = set()
        for asset in assets:
            source_id = str(asset.get("asset_id") or asset.get("file_id") or "")
            kind = str(asset.get("kind") or "")
            locator = str(asset.get("locator") or "")
            media_type = str(asset.get("media_type") or "").lower()
            expected_checksum = str(asset.get("checksum") or asset.get("sha256") or "")
            if (
                not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", source_id)
                or source_id in seen_source_ids
                or kind not in _INSTALLED_SOURCE_TITLES
                or not locator
                or not media_type
                or not re.fullmatch(r"[0-9a-f]{64}", expected_checksum)
            ):
                raise SourceLibraryError("Installed intake asset metadata is invalid")
            seen_source_ids.add(source_id)

            candidate_locator = PurePosixPath(locator)
            candidate = root.joinpath(*candidate_locator.parts).resolve()
            if (
                candidate_locator.is_absolute()
                or ".." in candidate_locator.parts
                or not candidate.is_relative_to(root)
                or not candidate.is_file()
            ):
                raise SourceLibraryError(
                    f"Installed intake asset is unavailable or unsafe: {source_id}"
                )

            declared = declared_resources.get(locator)
            if declared is None:
                raise SourceLibraryError(
                    f"Installed intake asset is absent from the package inventory: {source_id}"
                )
            declared_type = str(declared.get("media_type") or "").lower()
            declared_checksum = str(declared.get("sha256") or "")
            try:
                declared_size = int(declared.get("size_bytes"))
                body = candidate.read_bytes()
            except (OSError, TypeError, ValueError) as exc:
                raise SourceLibraryError(
                    f"Installed intake asset cannot be read exactly: {source_id}"
                ) from exc
            actual_checksum = hashlib.sha256(body).hexdigest()
            if (
                declared_type != media_type
                or declared_checksum != expected_checksum
                or actual_checksum != expected_checksum
                or declared_size != len(body)
            ):
                raise SourceLibraryError(
                    f"Installed intake asset identity mismatch: {source_id}"
                )

            installed.append(
                self.register(
                    workspace_id=workspace_id,
                    source_id=source_id,
                    kind=kind,  # type: ignore[arg-type]
                    title=str(asset.get("title") or _INSTALLED_SOURCE_TITLES[kind]),
                    original_name=candidate.name,
                    media_type=media_type,
                    body=body,
                )
            )
        return tuple(installed)

    def list_current(self, workspace_id: str) -> tuple[StudioSourceVersionV1, ...]:
        return self.store.list_current(workspace_id)

    def list_versions(self, workspace_id: str) -> tuple[StudioSourceVersionV1, ...]:
        return self.store.list_versions(workspace_id)

    def read_exact(self, version: StudioSourceVersionV1) -> bytes:
        return self.store.read_exact(version)

    def _version_by_id(
        self, source_version_id: str, workspace_id: str
    ) -> StudioSourceVersionV1:
        match = next(
            (
                item
                for item in self.list_versions(workspace_id)
                if item.source_version_id == source_version_id
            ),
            None,
        )
        if match is None:
            raise SourceLibraryError("Source version is unavailable")
        return match

    @staticmethod
    def _xlsx_archive_is_bounded(body: bytes) -> None:
        try:
            with zipfile.ZipFile(BytesIO(body)) as archive:
                members = archive.infolist()
                if len(members) > 2_000:
                    raise SourceLibraryError("XLSX archive has too many members")
                total = 0
                for member in members:
                    if member.flag_bits & 0x1:
                        raise SourceLibraryError("Encrypted XLSX is unsupported")
                    path = Path(member.filename)
                    if path.is_absolute() or ".." in path.parts:
                        raise SourceLibraryError("XLSX archive contains an unsafe path")
                    total += member.file_size
                    if total > 100 * 1024 * 1024:
                        raise SourceLibraryError("XLSX expanded size exceeds the product limit")
                    if member.compress_size and member.file_size / member.compress_size > 200:
                        raise SourceLibraryError("XLSX compression ratio exceeds the product limit")
                if archive.testzip() is not None:
                    raise SourceLibraryError("XLSX archive checksum failed")
        except SourceLibraryError:
            raise
        except (OSError, zipfile.BadZipFile) as exc:
            raise SourceLibraryError("XLSX archive is invalid") from exc

    @staticmethod
    def _display_cell(value: Any) -> str | int | float | bool | None:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)

    def _xlsx_preview(
        self,
        version: StudioSourceVersionV1,
        body: bytes,
        *,
        max_cells_per_sheet: int = 500,
    ) -> StudioSourcePreviewV1:
        if max_cells_per_sheet < 1 or max_cells_per_sheet > 5_000:
            raise SourceLibraryError("XLSX preview cell limit is invalid")
        self._xlsx_archive_is_bounded(body)
        try:
            formulas = load_workbook(
                BytesIO(body), read_only=True, data_only=False, keep_links=False
            )
            values = load_workbook(
                BytesIO(body), read_only=True, data_only=True, keep_links=False
            )
        except Exception as exc:
            raise SourceLibraryError("XLSX workbook cannot be parsed safely") from exc
        try:
            if len(formulas.sheetnames) > 100:
                raise SourceLibraryError("XLSX sheet count exceeds the product limit")
            sheets: list[SourcePreviewSheetV1] = []
            for sheet_name in formulas.sheetnames:
                worksheet = formulas[sheet_name]
                value_sheet = values[sheet_name]
                if worksheet.max_row > 100_000 or worksheet.max_column > 1_000:
                    raise SourceLibraryError("XLSX declared range exceeds the product limit")
                cells: list[SourcePreviewCellV1] = []
                truncated = False
                for row, value_row in zip(
                    worksheet.iter_rows(),
                    value_sheet.iter_rows(),
                    strict=True,
                ):
                    for cell, value_cell in zip(row, value_row, strict=True):
                        if cell.value is None:
                            continue
                        if len(cells) >= max_cells_per_sheet:
                            truncated = True
                            break
                        raw_formula = (
                            cell.value
                            if isinstance(cell.value, str) and cell.value.startswith("=")
                            else None
                        )
                        display = self._display_cell(value_cell.value)
                        anchor = {
                            "source_version_id": version.source_version_id,
                            "content_checksum": version.content_checksum,
                            "sheet": sheet_name,
                            "cell": cell.coordinate,
                            "raw_formula": raw_formula,
                            "display_value": display,
                        }
                        cells.append(
                            SourcePreviewCellV1(
                                cell=cell.coordinate,
                                display_value=display,
                                raw_formula=raw_formula,
                                snippet_checksum=sha256_value(anchor),
                            )
                        )
                    if truncated:
                        break
                used_range = worksheet.calculate_dimension(force=True)
                sheets.append(
                    SourcePreviewSheetV1(
                        sheet_name=sheet_name,
                        used_range=used_range,
                        cells=tuple(cells),
                        truncated=truncated,
                    )
                )
            return StudioSourcePreviewV1(
                source_version_id=version.source_version_id,
                content_checksum=version.content_checksum,
                status="PARSED",
                sheets=tuple(sheets),
            )
        finally:
            formulas.close()
            values.close()

    @staticmethod
    def _text_preview(
        version: StudioSourceVersionV1, body: bytes
    ) -> StudioSourcePreviewV1:
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SourceLibraryError("Text source is not valid UTF-8") from exc
        all_lines = text.splitlines()
        lines = tuple(
            SourcePreviewLineV1(
                line_number=index,
                text=line,
                snippet_checksum=sha256_value(
                    {
                        "source_version_id": version.source_version_id,
                        "content_checksum": version.content_checksum,
                        "line_number": index,
                        "text": line,
                    }
                ),
            )
            for index, line in enumerate(all_lines[:400], start=1)
        )
        return StudioSourcePreviewV1(
            source_version_id=version.source_version_id,
            content_checksum=version.content_checksum,
            status="PARSED",
            text_lines=lines,
            limitation=(
                "Preview is limited to the first 400 lines."
                if len(all_lines) > 400
                else None
            ),
        )

    def preview(
        self, source_version_id: str, workspace_id: str
    ) -> StudioSourcePreviewV1:
        version = self._version_by_id(source_version_id, workspace_id)
        body = self.read_exact(version)
        if version.processing_mode == "TRANSCRIBED" or version.media_type in {
            "text/plain",
            "text/markdown",
            "text/sql",
            "text/csv",
            "application/json",
            "application/yaml",
        }:
            return self._text_preview(version, body)
        if (
            version.media_type
            == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            or version.original_name.lower().endswith(".xlsx")
        ):
            return self._xlsx_preview(version, body)
        return StudioSourcePreviewV1(
            source_version_id=version.source_version_id,
            content_checksum=version.content_checksum,
            status="REGISTERED_NOT_PARSED",
            limitation="This exact media type is registered but has no enabled preview parser.",
        )

    def current_intake_assets(
        self,
        workspace_id: str,
        *,
        include_parsed_attachments: bool = False,
    ) -> tuple[dict[str, Any], ...]:
        assets: list[dict[str, Any]] = []
        for version in self.list_current(workspace_id):
            asset: dict[str, Any] = {
                "asset_id": version.source_id,
                "kind": version.kind,
                "locator": f"source-library:{version.source_version_id}",
                "media_type": version.media_type,
                "checksum": version.content_checksum,
                "processing_mode": version.processing_mode,
                "source_version_id": version.source_version_id,
                "registered_at": version.registered_at.isoformat(),
                "title": version.title,
                "original_name": version.original_name,
            }
            if version.processing_mode == "TRANSCRIBED":
                try:
                    asset["content_text"] = self.read_exact(version).decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise SourceLibraryError("Transcribed source is no longer valid UTF-8") from exc
            elif version.processing_mode == "STRUCTURED_TRANSCRIPTION":
                asset["source_preview"] = self.preview(
                    version.source_version_id,
                    workspace_id,
                ).model_dump(mode="json")
            elif include_parsed_attachments and (
                version.media_type
                == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                or version.original_name.lower().endswith(".xlsx")
            ):
                body = self.read_exact(version)
                asset["source_preview"] = self._xlsx_preview(
                    version,
                    body,
                    max_cells_per_sheet=5_000,
                ).model_dump(mode="json")
            elif include_parsed_attachments and version.media_type in {
                "text/plain",
                "text/markdown",
                "text/sql",
                "text/csv",
                "application/json",
                "application/yaml",
            }:
                asset["source_preview"] = self._text_preview(
                    version,
                    self.read_exact(version),
                ).model_dump(mode="json")
            assets.append(asset)
        return tuple(assets)
