"""Add resumable construction review drafts.

Revision ID: 20260821_0011
Revises: 20260821_0010
Create Date: 2026-08-21
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260821_0011"
down_revision: str | None = "20260821_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "studio_construction_review_draft",
        sa.Column("run_id", sa.String(length=80), nullable=False),
        sa.Column("workspace_id", sa.String(length=255), nullable=False),
        sa.Column("run_checksum", sa.String(length=64), nullable=False),
        sa.Column("review_revision", sa.Integer(), nullable=False),
        sa.Column("batch_checksum", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("final_decision_id", sa.String(length=80), nullable=True),
        sa.Column("subject", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(run_checksum) = 64 AND char_length(batch_checksum) = 64",
            name="ck_studio_review_draft_checksum_lengths",
        ),
        sa.CheckConstraint(
            "review_revision >= 1 AND status IN ('DRAFT','FINAL')",
            name="ck_studio_review_draft_state",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["studio_construction_run.run_id"],
            name="fk_studio_review_draft_run",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("run_id", name="pk_studio_review_draft"),
        sa.UniqueConstraint(
            "batch_checksum", name="uq_studio_review_draft_checksum"
        ),
    )
    op.create_index(
        "ix_studio_review_draft_workspace",
        "studio_construction_review_draft",
        ["workspace_id", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_studio_review_draft_workspace",
        table_name="studio_construction_review_draft",
    )
    op.drop_table("studio_construction_review_draft")
