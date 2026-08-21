"""Add durable Studio solution registrations.

Revision ID: 20260820_0004
Revises: 20260820_0003
Create Date: 2026-08-20
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260820_0004"
down_revision: str | None = "20260820_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "studio_solution_registration",
        sa.Column("subject_checksum", sa.String(length=64), nullable=False),
        sa.Column("solution_id", sa.String(length=255), nullable=False),
        sa.Column("solution_version", sa.String(length=64), nullable=False),
        sa.Column("scenario_id", sa.String(length=255), nullable=False),
        sa.Column("workspace_id", sa.String(length=255), nullable=False),
        sa.Column("studio_adapter_id", sa.String(length=255), nullable=False),
        sa.Column("subject", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("artifact", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(subject_checksum) = 64",
            name="ck_studio_solution_subject_checksum_length",
        ),
        sa.PrimaryKeyConstraint(
            "subject_checksum", name="pk_studio_solution_registration"
        ),
        sa.UniqueConstraint(
            "solution_id",
            "solution_version",
            name="uq_studio_solution_registration_alias",
        ),
    )
    op.create_index(
        "ix_studio_solution_registration_workspace",
        "studio_solution_registration",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_studio_solution_registration_scenario",
        "studio_solution_registration",
        ["scenario_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_studio_solution_registration_scenario",
        table_name="studio_solution_registration",
    )
    op.drop_index(
        "ix_studio_solution_registration_workspace",
        table_name="studio_solution_registration",
    )
    op.drop_table("studio_solution_registration")
