from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import Field
from sqlalchemy import DateTime, ForeignKey, String, create_engine, func, select
from sqlalchemy.dialects.postgresql import JSONB, insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from .contracts import Sha256, VerifiedSnapshot
from .io import canonical_bytes, sha256_value
from .models import StrictModel


class ProductInfrastructureError(RuntimeError):
    """The product context cannot be read or committed safely."""


class ProductContextConflict(ProductInfrastructureError):
    """The imported active context changed without an explicit lifecycle action."""


class ProductRouteLinks(StrictModel):
    studio: str = "/ontology-studio/"
    agent: str = "/ontology-agent/"


class ActiveRuntimeContext(StrictModel):
    environment_id: str
    release_checksum: Sha256
    snapshot_checksum: Sha256
    certification_profile: str | None = None


class ProductContextSubjectV1(StrictModel):
    contract: Literal["product-context-subject/v1"] = "product-context-subject/v1"
    context_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    product_family_id: Literal["ontology-analytics"] = "ontology-analytics"
    solution_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    solution_version: str
    scenario_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    scenario_name_en: str
    scenario_name_zh: str
    classification: Literal["constructed_synthetic"] = "constructed_synthetic"
    active_runtime: ActiveRuntimeContext
    navigation: ProductRouteLinks = ProductRouteLinks()
    limitations: tuple[str, ...] = (
        "Constructed synthetic reference; not HKEX validated",
        "Engineering demo; not production-ready",
    )


class ExactStoredArtifactRef(StrictModel):
    store: Literal["s3-compatible"] = "s3-compatible"
    bucket: str
    key: str
    version_id: str
    sha256: Sha256
    size_bytes: int = Field(ge=1)
    media_type: str = Field(min_length=1, max_length=255)


class ExactArtifactRef(ExactStoredArtifactRef):
    media_type: Literal["application/json"] = "application/json"


@dataclass(frozen=True, slots=True)
class S3ObjectVersion:
    bucket: str
    key: str
    version_id: str
    last_modified: datetime
    size_bytes: int


class ProductContextV1(StrictModel):
    contract: Literal["product-context/v1"] = "product-context/v1"
    persistence: Literal["legacy-compatibility", "postgresql-s3"]
    subject_checksum: Sha256
    subject: ProductContextSubjectV1
    artifact: ExactArtifactRef | None = None


@dataclass(frozen=True, slots=True)
class ProductInfrastructureSettings:
    mode: Literal["legacy-compatibility", "postgresql-s3"]
    database_url: str | None = None
    s3_bucket: str | None = None
    s3_endpoint_url: str | None = None
    s3_region: str = "us-east-1"
    s3_manage_bucket: bool = False

    @classmethod
    def from_env(cls) -> ProductInfrastructureSettings:
        mode = os.environ.get(
            "ONTOLOGY_PRODUCT_STATE_MODE", "legacy-compatibility"
        ).strip()
        if mode not in {"legacy-compatibility", "postgresql-s3"}:
            raise ProductInfrastructureError("Unsupported product state mode")
        if mode == "legacy-compatibility":
            return cls(mode="legacy-compatibility")
        database_url = os.environ.get("ONTOLOGY_DATABASE_URL", "").strip()
        bucket = os.environ.get("ONTOLOGY_S3_BUCKET", "").strip()
        if not database_url or not bucket:
            raise ProductInfrastructureError(
                "PostgreSQL/S3 product state requires database URL and artifact bucket"
            )
        endpoint_url = os.environ.get("ONTOLOGY_S3_ENDPOINT_URL", "").strip() or None
        manage_bucket_value = os.environ.get("ONTOLOGY_S3_MANAGE_BUCKET", "").strip().lower()
        if manage_bucket_value:
            if manage_bucket_value not in {"true", "false"}:
                raise ProductInfrastructureError(
                    "ONTOLOGY_S3_MANAGE_BUCKET must be true or false"
                )
            manage_bucket = manage_bucket_value == "true"
        else:
            # Local S3-compatible stores are self-managed by default. AWS S3 is
            # infrastructure-owned unless explicitly opted in.
            manage_bucket = endpoint_url is not None
        return cls(
            mode="postgresql-s3",
            database_url=database_url,
            s3_bucket=bucket,
            s3_endpoint_url=endpoint_url,
            s3_region=os.environ.get("ONTOLOGY_S3_REGION", "us-east-1").strip(),
            s3_manage_bucket=manage_bucket,
        )


def product_context_subject(snapshot: VerifiedSnapshot) -> ProductContextSubjectV1:
    package = snapshot.package
    certification = snapshot.manifest.get("certification") or {}
    return ProductContextSubjectV1(
        context_id="context.adt.reference",
        solution_id=package.package_id,
        solution_version=package.version,
        scenario_id=package.scenario.id,
        scenario_name_en=package.scenario.name.en,
        scenario_name_zh=package.scenario.name.zh,
        active_runtime=ActiveRuntimeContext(
            environment_id=str(snapshot.manifest["environment_id"]),
            release_checksum=snapshot.release_checksum,
            snapshot_checksum=snapshot.snapshot_checksum,
            certification_profile=certification.get("profile_id"),
        ),
    )


def legacy_product_context(snapshot: VerifiedSnapshot) -> ProductContextV1:
    subject = product_context_subject(snapshot)
    return ProductContextV1(
        persistence="legacy-compatibility",
        subject_checksum=sha256_value(subject),
        subject=subject,
    )


class ArtifactStorePort(Protocol):
    def publish_subject(self, subject: ProductContextSubjectV1) -> ExactArtifactRef: ...

    def get_exact(self, ref: ExactArtifactRef) -> bytes: ...


class S3ArtifactStore:
    def __init__(self, settings: ProductInfrastructureSettings) -> None:
        if settings.mode != "postgresql-s3" or not settings.s3_bucket:
            raise ProductInfrastructureError("S3 artifact settings are incomplete")
        self.bucket = settings.s3_bucket
        self.region = settings.s3_region
        self.manage_bucket = settings.s3_manage_bucket
        client_options: dict[str, object] = {
            "service_name": "s3",
            "region_name": self.region,
            "config": Config(
                signature_version="s3v4",
                connect_timeout=2,
                read_timeout=5,
                retries={"max_attempts": 2, "mode": "standard"},
                s3={
                    "addressing_style": "path"
                    if settings.s3_endpoint_url
                    else "auto"
                },
            ),
        }
        if settings.s3_endpoint_url:
            client_options["endpoint_url"] = settings.s3_endpoint_url
        self.client = boto3.client(**client_options)

    @staticmethod
    def _not_found(exc: ClientError) -> bool:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        return code in {"404", "NoSuchBucket", "NoSuchKey", "NotFound"}

    def ensure_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except BotoCoreError as exc:
            raise ProductInfrastructureError("Artifact bucket is not reachable") from exc
        except ClientError as exc:
            if not self._not_found(exc):
                raise ProductInfrastructureError("Artifact bucket is not accessible") from exc
            if not self.manage_bucket:
                raise ProductInfrastructureError(
                    "Artifact bucket does not exist and runtime bucket management is disabled"
                ) from exc
            create: dict[str, object] = {"Bucket": self.bucket}
            if self.region != "us-east-1":
                create["CreateBucketConfiguration"] = {
                    "LocationConstraint": self.region
                }
            try:
                self.client.create_bucket(**create)
            except (BotoCoreError, ClientError) as create_exc:
                raise ProductInfrastructureError(
                    "Artifact bucket could not be created"
                ) from create_exc
        try:
            status = self.client.get_bucket_versioning(Bucket=self.bucket).get("Status")
            if status != "Enabled" and self.manage_bucket:
                self.client.put_bucket_versioning(
                    Bucket=self.bucket, VersioningConfiguration={"Status": "Enabled"}
                )
                status = self.client.get_bucket_versioning(Bucket=self.bucket).get("Status")
        except (BotoCoreError, ClientError) as exc:
            raise ProductInfrastructureError(
                "Artifact bucket versioning could not be verified"
            ) from exc
        if status != "Enabled":
            raise ProductInfrastructureError("Artifact bucket versioning is not enabled")

    def publish_subject(self, subject: ProductContextSubjectV1) -> ExactArtifactRef:
        body = canonical_bytes(subject)
        digest = hashlib.sha256(body).hexdigest()
        stored = self.publish_blob(
            body,
            namespace="product-context",
            media_type="application/json",
            suffix="json",
        )
        if stored.sha256 != digest:
            raise ProductInfrastructureError("Artifact publish digest mismatch")
        return ExactArtifactRef.model_validate(stored.model_dump(mode="json"))

    def publish_blob(
        self,
        body: bytes,
        *,
        namespace: str,
        media_type: str,
        suffix: str,
    ) -> ExactStoredArtifactRef:
        self.ensure_bucket()
        if not body:
            raise ProductInfrastructureError("Empty artifacts are not publishable")
        if not namespace or any(
            part in {"", ".", ".."} for part in namespace.split("/")
        ):
            raise ProductInfrastructureError("Artifact namespace is invalid")
        if not suffix.isalnum() or not media_type or len(media_type) > 255:
            raise ProductInfrastructureError("Artifact media descriptor is invalid")
        digest = hashlib.sha256(body).hexdigest()
        key = f"{namespace}/sha256/{digest}.{suffix}"

        try:
            head = self.client.head_object(Bucket=self.bucket, Key=key)
        except BotoCoreError as exc:
            raise ProductInfrastructureError("Artifact lookup failed") from exc
        except ClientError as exc:
            if not self._not_found(exc):
                raise ProductInfrastructureError("Artifact lookup failed") from exc
            try:
                response = self.client.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=body,
                    ContentType=media_type,
                    Metadata={"sha256": digest},
                )
            except (BotoCoreError, ClientError) as put_exc:
                raise ProductInfrastructureError("Artifact publish failed") from put_exc
            version_id = response.get("VersionId")
        else:
            if int(head.get("ContentLength", -1)) != len(body):
                raise ProductInfrastructureError(
                    "Content-addressed artifact key contains another payload"
                )
            if (head.get("Metadata") or {}).get("sha256") != digest:
                raise ProductInfrastructureError("Artifact metadata digest mismatch")
            version_id = head.get("VersionId")

        if not isinstance(version_id, str) or not version_id or version_id == "null":
            raise ProductInfrastructureError("Artifact store did not return an exact version")
        ref = ExactStoredArtifactRef(
            bucket=self.bucket,
            key=key,
            version_id=version_id,
            sha256=digest,
            size_bytes=len(body),
            media_type=media_type,
        )
        self.get_exact(ref)
        return ref

    def get_exact(self, ref: ExactStoredArtifactRef) -> bytes:
        try:
            response = self.client.get_object(
                Bucket=ref.bucket, Key=ref.key, VersionId=ref.version_id
            )
            body = response["Body"].read()
        except (BotoCoreError, ClientError, KeyError, OSError) as exc:
            raise ProductInfrastructureError("Exact artifact read-back failed") from exc
        if len(body) != ref.size_bytes:
            raise ProductInfrastructureError("Exact artifact size mismatch")
        if hashlib.sha256(body).hexdigest() != ref.sha256:
            raise ProductInfrastructureError("Exact artifact digest mismatch")
        return body

    def list_versions(self, *, prefix: str) -> tuple[S3ObjectVersion, ...]:
        if not prefix or prefix.startswith("/") or ".." in prefix.split("/"):
            raise ProductInfrastructureError("Artifact listing prefix is invalid")
        try:
            paginator = self.client.get_paginator("list_object_versions")
            pages = paginator.paginate(Bucket=self.bucket, Prefix=prefix)
            versions = [
                S3ObjectVersion(
                    bucket=self.bucket,
                    key=str(item["Key"]),
                    version_id=str(item["VersionId"]),
                    last_modified=item["LastModified"],
                    size_bytes=int(item["Size"]),
                )
                for page in pages
                for item in page.get("Versions", [])
            ]
        except (BotoCoreError, ClientError, KeyError, TypeError, ValueError) as exc:
            raise ProductInfrastructureError("Artifact version listing failed") from exc
        return tuple(
            sorted(versions, key=lambda item: (item.key, item.last_modified, item.version_id))
        )

    def delete_version(self, version: S3ObjectVersion) -> None:
        if version.bucket != self.bucket:
            raise ProductInfrastructureError("Artifact deletion bucket mismatch")
        try:
            self.client.delete_object(
                Bucket=version.bucket,
                Key=version.key,
                VersionId=version.version_id,
            )
        except (BotoCoreError, ClientError) as exc:
            raise ProductInfrastructureError("Exact artifact version deletion failed") from exc


class Base(DeclarativeBase):
    pass


class ProductSolutionRow(Base):
    __tablename__ = "product_solution"

    solution_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    solution_version: Mapped[str] = mapped_column(String(64), primary_key=True)
    scenario_id: Mapped[str] = mapped_column(String(255), nullable=False)
    classification: Mapped[str] = mapped_column(String(64), nullable=False)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ProductContextVersionRow(Base):
    __tablename__ = "product_context_version"

    subject_checksum: Mapped[str] = mapped_column(String(64), primary_key=True)
    context_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    solution_id: Mapped[str] = mapped_column(String(255), nullable=False)
    solution_version: Mapped[str] = mapped_column(String(64), nullable=False)
    subject: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    artifact: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ActiveProductContextRow(Base):
    __tablename__ = "active_product_context"

    environment_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    subject_checksum: Mapped[str] = mapped_column(
        String(64), ForeignKey("product_context_version.subject_checksum"), nullable=False
    )
    source_snapshot_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ProductContextRepository(Protocol):
    def register_version(
        self, subject: ProductContextSubjectV1, artifact: ExactArtifactRef
    ) -> None: ...

    def import_initial(
        self, subject: ProductContextSubjectV1, artifact: ExactArtifactRef
    ) -> bool: ...

    def get_active(self, environment_id: str) -> ProductContextV1: ...


class PostgresProductContextRepository:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)

    def import_initial(
        self, subject: ProductContextSubjectV1, artifact: ExactArtifactRef
    ) -> bool:
        checksum = sha256_value(subject)
        environment_id = subject.active_runtime.environment_id
        try:
            with Session(self.engine) as session, session.begin():
                self._register_version(session, subject, artifact)
                current = session.execute(
                    select(ActiveProductContextRow)
                    .where(ActiveProductContextRow.environment_id == environment_id)
                    .with_for_update()
                ).scalar_one_or_none()
                if current is None:
                    session.execute(
                        pg_insert(ActiveProductContextRow).values(
                            environment_id=environment_id,
                            subject_checksum=checksum,
                            source_snapshot_checksum=subject.active_runtime.snapshot_checksum,
                        )
                    )
                    return False
                if (
                    current.subject_checksum != checksum
                    or current.source_snapshot_checksum
                    != subject.active_runtime.snapshot_checksum
                ):
                    raise ProductContextConflict(
                        "Active product context changed; use the lifecycle cutover path"
                    )
                return True
        except SQLAlchemyError as exc:
            raise ProductInfrastructureError(
                "Product context database transaction failed"
            ) from exc

    @staticmethod
    def _register_version(
        session: Session,
        subject: ProductContextSubjectV1,
        artifact: ExactArtifactRef,
    ) -> None:
        checksum = sha256_value(subject)
        session.execute(
            pg_insert(ProductSolutionRow)
            .values(
                solution_id=subject.solution_id,
                solution_version=subject.solution_version,
                scenario_id=subject.scenario_id,
                classification=subject.classification,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    ProductSolutionRow.solution_id,
                    ProductSolutionRow.solution_version,
                ]
            )
        )
        session.execute(
            pg_insert(ProductContextVersionRow)
            .values(
                subject_checksum=checksum,
                context_id=subject.context_id,
                solution_id=subject.solution_id,
                solution_version=subject.solution_version,
                subject=subject.model_dump(mode="json"),
                artifact=artifact.model_dump(mode="json"),
            )
            .on_conflict_do_nothing(
                index_elements=[ProductContextVersionRow.subject_checksum]
            )
        )

    def register_version(
        self, subject: ProductContextSubjectV1, artifact: ExactArtifactRef
    ) -> None:
        try:
            with Session(self.engine) as session, session.begin():
                self._register_version(session, subject, artifact)
        except SQLAlchemyError as exc:
            raise ProductInfrastructureError(
                "Product context version registration failed"
            ) from exc

    def get_active(self, environment_id: str) -> ProductContextV1:
        try:
            with Session(self.engine) as session:
                row = session.execute(
                    select(ProductContextVersionRow)
                    .join(
                        ActiveProductContextRow,
                        ActiveProductContextRow.subject_checksum
                        == ProductContextVersionRow.subject_checksum,
                    )
                    .where(ActiveProductContextRow.environment_id == environment_id)
                ).scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise ProductInfrastructureError(
                "Product context database read failed"
            ) from exc
        if row is None:
            raise ProductInfrastructureError("No active product context is registered")
        subject = ProductContextSubjectV1.model_validate(row.subject)
        artifact = ExactArtifactRef.model_validate(row.artifact)
        checksum = sha256_value(subject)
        if checksum != row.subject_checksum or checksum != artifact.sha256:
            raise ProductInfrastructureError("Product context identity mismatch")
        return ProductContextV1(
            persistence="postgresql-s3",
            subject_checksum=checksum,
            subject=subject,
            artifact=artifact,
        )


class ProductContextService:
    def __init__(
        self,
        repository: ProductContextRepository,
        artifacts: ArtifactStorePort,
    ) -> None:
        self.repository = repository
        self.artifacts = artifacts

    @classmethod
    def from_settings(
        cls, settings: ProductInfrastructureSettings
    ) -> ProductContextService:
        if settings.mode != "postgresql-s3" or not settings.database_url:
            raise ProductInfrastructureError("PostgreSQL/S3 mode is not configured")
        return cls(
            PostgresProductContextRepository(settings.database_url),
            S3ArtifactStore(settings),
        )

    def import_initial(self, snapshot: VerifiedSnapshot) -> tuple[ProductContextV1, bool]:
        subject = product_context_subject(snapshot)
        artifact = self.artifacts.publish_subject(subject)
        idempotent = self.repository.import_initial(subject, artifact)
        context = self.repository.get_active(subject.active_runtime.environment_id)
        self._verify_artifact(context)
        return context, idempotent

    def get_active(self, environment_id: str) -> ProductContextV1:
        context = self.repository.get_active(environment_id)
        self._verify_artifact(context)
        return context

    def _verify_artifact(self, context: ProductContextV1) -> None:
        if context.artifact is None:
            raise ProductInfrastructureError("Persisted product context has no artifact")
        body = self.artifacts.get_exact(context.artifact)
        if body != canonical_bytes(context.subject):
            raise ProductInfrastructureError("Product context artifact subject mismatch")
