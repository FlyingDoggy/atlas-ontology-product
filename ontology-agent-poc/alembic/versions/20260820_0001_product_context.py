"""Create the Phase 1 product context read model.

Revision ID: 20260820_0001
Revises:
Create Date: 2026-08-20
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260820_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_solution",
        sa.Column("solution_id", sa.String(length=255), nullable=False),
        sa.Column("solution_version", sa.String(length=64), nullable=False),
        sa.Column("scenario_id", sa.String(length=255), nullable=False),
        sa.Column("classification", sa.String(length=64), nullable=False),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "classification = 'constructed_synthetic'",
            name="ck_product_solution_phase1_classification",
        ),
        sa.PrimaryKeyConstraint(
            "solution_id", "solution_version", name="pk_product_solution"
        ),
    )
    op.create_table(
        "product_context_version",
        sa.Column("subject_checksum", sa.String(length=64), nullable=False),
        sa.Column("context_id", sa.String(length=255), nullable=False),
        sa.Column("solution_id", sa.String(length=255), nullable=False),
        sa.Column("solution_version", sa.String(length=64), nullable=False),
        sa.Column("subject", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("artifact", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(subject_checksum) = 64",
            name="ck_product_context_version_checksum_length",
        ),
        sa.PrimaryKeyConstraint(
            "subject_checksum", name="pk_product_context_version"
        ),
    )
    op.create_index(
        "ix_product_context_version_context_id",
        "product_context_version",
        ["context_id"],
        unique=False,
    )
    op.create_table(
        "active_product_context",
        sa.Column("environment_id", sa.String(length=255), nullable=False),
        sa.Column("subject_checksum", sa.String(length=64), nullable=False),
        sa.Column("source_snapshot_checksum", sa.String(length=64), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(source_snapshot_checksum) = 64",
            name="ck_active_product_context_snapshot_checksum_length",
        ),
        sa.ForeignKeyConstraint(
            ["subject_checksum"],
            ["product_context_version.subject_checksum"],
            name="fk_active_product_context_version",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "environment_id", name="pk_active_product_context"
        ),
    )


def downgrade() -> None:
    op.drop_table("active_product_context")
    op.drop_index(
        "ix_product_context_version_context_id",
        table_name="product_context_version",
    )
    op.drop_table("product_context_version")
    op.drop_table("product_solution")
