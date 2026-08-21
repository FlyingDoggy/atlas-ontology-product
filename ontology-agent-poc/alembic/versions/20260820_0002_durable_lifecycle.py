"""Add PostgreSQL/S3 release and runtime lifecycle heads.

Revision ID: 20260820_0002
Revises: 20260820_0001
Create Date: 2026-08-20
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260820_0002"
down_revision: str | None = "20260820_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lifecycle_release",
        sa.Column("release_checksum", sa.String(length=64), nullable=False),
        sa.Column("package_id", sa.String(length=255), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("release_ref", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("artifact", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(release_checksum) = 64",
            name="ck_lifecycle_release_checksum_length",
        ),
        sa.PrimaryKeyConstraint("release_checksum", name="pk_lifecycle_release"),
        sa.UniqueConstraint(
            "package_id", "version", name="uq_lifecycle_release_alias"
        ),
    )
    op.create_table(
        "lifecycle_runtime_snapshot",
        sa.Column("snapshot_checksum", sa.String(length=64), nullable=False),
        sa.Column("environment_id", sa.String(length=255), nullable=False),
        sa.Column("package_id", sa.String(length=255), nullable=False),
        sa.Column("release_checksum", sa.String(length=64), nullable=False),
        sa.Column("context_subject_checksum", sa.String(length=64), nullable=False),
        sa.Column("snapshot_ref", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("artifact", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(snapshot_checksum) = 64",
            name="ck_lifecycle_snapshot_checksum_length",
        ),
        sa.CheckConstraint(
            "state = 'READY'", name="ck_lifecycle_snapshot_ready_state"
        ),
        sa.ForeignKeyConstraint(
            ["release_checksum"],
            ["lifecycle_release.release_checksum"],
            name="fk_lifecycle_snapshot_release",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["context_subject_checksum"],
            ["product_context_version.subject_checksum"],
            name="fk_lifecycle_snapshot_context",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "snapshot_checksum", name="pk_lifecycle_runtime_snapshot"
        ),
    )
    op.create_index(
        "ix_lifecycle_snapshot_environment_package",
        "lifecycle_runtime_snapshot",
        ["environment_id", "package_id"],
        unique=False,
    )
    op.create_table(
        "lifecycle_active_head",
        sa.Column("environment_id", sa.String(length=255), nullable=False),
        sa.Column("package_id", sa.String(length=255), nullable=False),
        sa.Column("snapshot_checksum", sa.String(length=64), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("generation >= 1", name="ck_lifecycle_head_generation"),
        sa.ForeignKeyConstraint(
            ["snapshot_checksum"],
            ["lifecycle_runtime_snapshot.snapshot_checksum"],
            name="fk_lifecycle_head_snapshot",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "environment_id", "package_id", name="pk_lifecycle_active_head"
        ),
    )
    op.create_table(
        "lifecycle_activation_event",
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("environment_id", sa.String(length=255), nullable=False),
        sa.Column("package_id", sa.String(length=255), nullable=False),
        sa.Column("previous_snapshot_checksum", sa.String(length=64), nullable=True),
        sa.Column("active_snapshot_checksum", sa.String(length=64), nullable=False),
        sa.Column("expected_snapshot_checksum", sa.String(length=64), nullable=True),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("generation >= 1", name="ck_lifecycle_event_generation"),
        sa.PrimaryKeyConstraint("event_id", name="pk_lifecycle_activation_event"),
    )
    op.create_index(
        "ix_lifecycle_event_subject_generation",
        "lifecycle_activation_event",
        ["environment_id", "package_id", "generation"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_lifecycle_event_subject_generation",
        table_name="lifecycle_activation_event",
    )
    op.drop_table("lifecycle_activation_event")
    op.drop_table("lifecycle_active_head")
    op.drop_index(
        "ix_lifecycle_snapshot_environment_package",
        table_name="lifecycle_runtime_snapshot",
    )
    op.drop_table("lifecycle_runtime_snapshot")
    op.drop_table("lifecycle_release")
