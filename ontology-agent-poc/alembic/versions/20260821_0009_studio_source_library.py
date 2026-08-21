"""Add immutable Studio source versions and one current head per source kind.

Revision ID: 20260821_0009
Revises: 20260821_0008
Create Date: 2026-08-21
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260821_0009"
down_revision: str | None = "20260821_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "studio_source_version",
        sa.Column("source_version_id", sa.String(length=80), nullable=False),
        sa.Column("workspace_id", sa.String(length=255), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("content_checksum", sa.String(length=64), nullable=False),
        sa.Column("subject_checksum", sa.String(length=64), nullable=False),
        sa.Column("subject", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("artifact", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(content_checksum) = 64 AND char_length(subject_checksum) = 64",
            name="ck_studio_source_version_checksum_lengths",
        ),
        sa.PrimaryKeyConstraint("source_version_id", name="pk_studio_source_version"),
        sa.UniqueConstraint("subject_checksum", name="uq_studio_source_version_subject"),
    )
    op.create_index(
        "ix_studio_source_version_workspace",
        "studio_source_version",
        ["workspace_id", "registered_at"],
        unique=False,
    )
    op.create_table(
        "studio_source_head",
        sa.Column("workspace_id", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("source_version_id", sa.String(length=80), nullable=False),
        sa.Column("subject_checksum", sa.String(length=64), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(subject_checksum) = 64",
            name="ck_studio_source_head_checksum_length",
        ),
        sa.ForeignKeyConstraint(
            ["source_version_id"],
            ["studio_source_version.source_version_id"],
            name="fk_studio_source_head_version",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("workspace_id", "kind", name="pk_studio_source_head"),
    )


def downgrade() -> None:
    op.drop_table("studio_source_head")
    op.drop_index("ix_studio_source_version_workspace", table_name="studio_source_version")
    op.drop_table("studio_source_version")
