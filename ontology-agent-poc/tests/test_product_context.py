from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

import ontology_agent.api as api_module
from ontology_agent.api import app
from ontology_agent.contracts import VerifiedSnapshot
from ontology_agent.io import canonical_bytes, sha256_value
from ontology_agent.models import OntologyPackage
from ontology_agent.product_context import (
    ExactArtifactRef,
    ProductContextService,
    ProductContextSubjectV1,
    ProductContextV1,
    ProductInfrastructureError,
    ProductInfrastructureSettings,
    PostgresProductContextRepository,
    legacy_product_context,
    product_context_subject,
)
from ontology_agent.publisher import publish_package


class MemoryArtifacts:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str, str], bytes] = {}

    def publish_subject(self, subject: ProductContextSubjectV1) -> ExactArtifactRef:
        body = canonical_bytes(subject)
        digest = hashlib.sha256(body).hexdigest()
        ref = ExactArtifactRef(
            bucket="test-artifacts",
            key=f"product-context/sha256/{digest}.json",
            version_id="version-1",
            sha256=digest,
            size_bytes=len(body),
        )
        self.objects[(ref.bucket, ref.key, ref.version_id)] = body
        return ref

    def get_exact(self, ref: ExactArtifactRef) -> bytes:
        return self.objects[(ref.bucket, ref.key, ref.version_id)]


class MemoryRepository:
    def __init__(self) -> None:
        self.context: ProductContextV1 | None = None

    def import_initial(
        self, subject: ProductContextSubjectV1, artifact: ExactArtifactRef
    ) -> bool:
        context = ProductContextV1(
            persistence="postgresql-s3",
            subject_checksum=sha256_value(subject),
            subject=subject,
            artifact=artifact,
        )
        if self.context is None:
            self.context = context
            return False
        if self.context != context:
            raise AssertionError("test repository received a conflicting context")
        return True

    def register_version(
        self, subject: ProductContextSubjectV1, artifact: ExactArtifactRef
    ) -> None:
        self.import_initial(subject, artifact)

    def get_active(self, environment_id: str) -> ProductContextV1:
        if self.context is None:
            raise ProductInfrastructureError("No context")
        assert self.context.subject.active_runtime.environment_id == environment_id
        return self.context


def test_product_context_subject_is_deterministic(snapshot: VerifiedSnapshot) -> None:
    first = product_context_subject(snapshot)
    second = product_context_subject(snapshot)

    assert first == second
    assert sha256_value(first) == hashlib.sha256(canonical_bytes(first)).hexdigest()
    assert first.classification == "constructed_synthetic"
    assert first.navigation.agent == "/ontology-agent/"
    assert first.navigation.studio == "/ontology-studio/"


def test_product_context_import_is_idempotent_and_readback_verified(
    snapshot: VerifiedSnapshot,
) -> None:
    repository = MemoryRepository()
    artifacts = MemoryArtifacts()
    service = ProductContextService(repository, artifacts)

    first, first_idempotent = service.import_initial(snapshot)
    second, second_idempotent = service.import_initial(snapshot)

    assert first_idempotent is False
    assert second_idempotent is True
    assert second == first
    assert first.artifact is not None
    assert first.artifact.sha256 == first.subject_checksum


def test_product_context_rejects_modified_artifact(snapshot: VerifiedSnapshot) -> None:
    repository = MemoryRepository()
    artifacts = MemoryArtifacts()
    service = ProductContextService(repository, artifacts)
    context, _ = service.import_initial(snapshot)
    assert context.artifact is not None
    artifacts.objects[
        (context.artifact.bucket, context.artifact.key, context.artifact.version_id)
    ] = b"{}"

    with pytest.raises(ProductInfrastructureError, match="artifact subject mismatch"):
        service.get_active(context.subject.active_runtime.environment_id)


def test_settings_fail_closed_when_postgres_s3_is_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ONTOLOGY_PRODUCT_STATE_MODE", "postgresql-s3")
    monkeypatch.delenv("ONTOLOGY_DATABASE_URL", raising=False)
    monkeypatch.delenv("ONTOLOGY_S3_BUCKET", raising=False)

    with pytest.raises(ProductInfrastructureError, match="requires database URL"):
        ProductInfrastructureSettings.from_env()


def test_managed_aws_bucket_is_verify_only_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ONTOLOGY_PRODUCT_STATE_MODE", "postgresql-s3")
    monkeypatch.setenv("ONTOLOGY_DATABASE_URL", "postgresql+psycopg://example")
    monkeypatch.setenv("ONTOLOGY_S3_BUCKET", "managed-artifacts")
    monkeypatch.delenv("ONTOLOGY_S3_ENDPOINT_URL", raising=False)
    monkeypatch.delenv("ONTOLOGY_S3_MANAGE_BUCKET", raising=False)

    settings = ProductInfrastructureSettings.from_env()

    assert settings.s3_endpoint_url is None
    assert settings.s3_manage_bucket is False


def test_local_s3_bucket_management_can_be_explicitly_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ONTOLOGY_PRODUCT_STATE_MODE", "postgresql-s3")
    monkeypatch.setenv("ONTOLOGY_DATABASE_URL", "postgresql+psycopg://example")
    monkeypatch.setenv("ONTOLOGY_S3_BUCKET", "local-artifacts")
    monkeypatch.setenv("ONTOLOGY_S3_ENDPOINT_URL", "http://minio:9000")
    monkeypatch.setenv("ONTOLOGY_S3_MANAGE_BUCKET", "false")

    assert ProductInfrastructureSettings.from_env().s3_manage_bucket is False


def test_postgres_repository_wraps_database_outage_as_product_unavailable() -> None:
    repository = PostgresProductContextRepository("sqlite+pysqlite:///:memory:")

    with pytest.raises(ProductInfrastructureError, match="database read failed"):
        repository.get_active("adt-poc")


def test_product_context_api_preserves_legacy_runtime_as_compatibility_source(
    monkeypatch: pytest.MonkeyPatch,
    package: OntologyPackage,
    scenario_dir: Path,
    tmp_path: Path,
) -> None:
    published = tmp_path / "published"
    publish_package(package, scenario_dir, published)
    monkeypatch.setattr(api_module, "DEFAULT_PUBLISHED_DIR", published)
    monkeypatch.setattr(api_module, "DEFAULT_SCENARIO_DIR", scenario_dir)
    monkeypatch.setenv("ONTOLOGY_PRODUCT_STATE_MODE", "legacy-compatibility")

    response = TestClient(app).get("/api/product/context")

    assert response.status_code == 200
    payload = response.json()
    assert payload["contract"] == "product-context/v1"
    assert payload["persistence"] == "legacy-compatibility"
    assert payload["artifact"] is None
    assert payload["subject"]["solution_id"] == package.package_id
    assert payload["subject"]["active_runtime"]["snapshot_checksum"]


def test_legacy_product_context_does_not_claim_s3(snapshot: VerifiedSnapshot) -> None:
    context = legacy_product_context(snapshot)

    assert context.persistence == "legacy-compatibility"
    assert context.artifact is None
