"""Add mutable Studio solution directory metadata and lifecycle.

Revision ID: 20260820_0007
Revises: 20260820_0006
Create Date: 2026-08-20
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260820_0007"
down_revision: str | None = "20260820_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "studio_solution_directory",
        sa.Column("solution_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "display_name", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("description", sa.String(length=1000), nullable=False),
        sa.Column("owner", sa.String(length=200), nullable=False),
        sa.Column("creation_mode", sa.String(length=32), nullable=False),
        sa.Column("template_solution_id", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'ARCHIVED', 'DELETED')",
            name="ck_studio_solution_directory_status",
        ),
        sa.CheckConstraint(
            "creation_mode IN ('INSTALLED', 'TEMPLATE', 'IMPORT', 'BLANK')",
            name="ck_studio_solution_directory_creation_mode",
        ),
        sa.PrimaryKeyConstraint("solution_id", name="pk_studio_solution_directory"),
    )
    op.create_index(
        "ix_studio_solution_directory_status",
        "studio_solution_directory",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_studio_solution_directory_status",
        table_name="studio_solution_directory",
    )
    op.drop_table("studio_solution_directory")
