"""Add durable Studio workspace heads and immutable draft revisions.

Revision ID: 20260820_0005
Revises: 20260820_0004
Create Date: 2026-08-20
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260820_0005"
down_revision: str | None = "20260820_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "studio_workspace_head",
        sa.Column("workspace_id", sa.String(length=255), nullable=False),
        sa.Column("solution_id", sa.String(length=255), nullable=False),
        sa.Column("solution_version", sa.String(length=64), nullable=False),
        sa.Column("studio_adapter_id", sa.String(length=255), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("subject_checksum", sa.String(length=64), nullable=False),
        sa.Column("subject", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("artifact", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "generation >= 1 AND revision >= 1",
            name="ck_studio_workspace_positive_versions",
        ),
        sa.CheckConstraint(
            "char_length(subject_checksum) = 64",
            name="ck_studio_workspace_subject_checksum_length",
        ),
        sa.PrimaryKeyConstraint("workspace_id", name="pk_studio_workspace_head"),
        sa.UniqueConstraint(
            "subject_checksum", name="uq_studio_workspace_subject_checksum"
        ),
    )
    op.create_index(
        "ix_studio_workspace_solution",
        "studio_workspace_head",
        ["solution_id", "solution_version"],
        unique=False,
    )

    op.create_table(
        "studio_draft_revision",
        sa.Column("workspace_id", sa.String(length=255), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("solution_id", sa.String(length=255), nullable=False),
        sa.Column("solution_version", sa.String(length=64), nullable=False),
        sa.Column("studio_adapter_id", sa.String(length=255), nullable=False),
        sa.Column("draft_checksum", sa.String(length=64), nullable=False),
        sa.Column("record_checksum", sa.String(length=64), nullable=False),
        sa.Column("subject_checksum", sa.String(length=64), nullable=False),
        sa.Column("subject", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("artifact", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "revision >= 1", name="ck_studio_draft_revision_positive"
        ),
        sa.CheckConstraint(
            "char_length(draft_checksum) = 64 AND "
            "char_length(record_checksum) = 64 AND "
            "char_length(subject_checksum) = 64",
            name="ck_studio_draft_revision_checksum_lengths",
        ),
        sa.PrimaryKeyConstraint(
            "workspace_id", "revision", name="pk_studio_draft_revision"
        ),
        sa.UniqueConstraint(
            "subject_checksum", name="uq_studio_draft_revision_subject_checksum"
        ),
    )
    op.create_index(
        "ix_studio_draft_revision_solution",
        "studio_draft_revision",
        ["solution_id", "solution_version"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_studio_draft_revision_solution", table_name="studio_draft_revision"
    )
    op.drop_table("studio_draft_revision")
    op.drop_index("ix_studio_workspace_solution", table_name="studio_workspace_head")
    op.drop_table("studio_workspace_head")
