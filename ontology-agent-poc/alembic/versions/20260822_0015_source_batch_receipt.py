"""Add durable source intake batch receipts.

Revision ID: 20260822_0015
Revises: 20260822_0014
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260822_0015"
down_revision: str | None = "20260822_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "studio_source_batch_receipt",
        sa.Column("batch_id", sa.String(length=80), nullable=False),
        sa.Column("workspace_id", sa.String(length=255), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("request_digest", sa.String(length=64), nullable=False),
        sa.Column("subject_checksum", sa.String(length=64), nullable=False),
        sa.Column("subject", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("batch_id"),
        sa.UniqueConstraint(
            "workspace_id",
            "idempotency_key",
            name="uq_studio_source_batch_receipt_workspace_key",
        ),
        sa.UniqueConstraint("subject_checksum"),
    )
    op.create_index(
        "ix_studio_source_batch_receipt_workspace_id",
        "studio_source_batch_receipt",
        ["workspace_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_studio_source_batch_receipt_workspace_id",
        table_name="studio_source_batch_receipt",
    )
    op.drop_table("studio_source_batch_receipt")
