"""Add exact installable bundle metadata to Studio solution registrations.

Revision ID: 20260820_0006
Revises: 20260820_0005
Create Date: 2026-08-20
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260820_0006"
down_revision: str | None = "20260820_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable preserves exact historical registration rows. Registrations created
    # with a complete resource inventory require this value at the application layer.
    op.add_column(
        "studio_solution_registration",
        sa.Column(
            "bundle",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("studio_solution_registration", "bundle")
