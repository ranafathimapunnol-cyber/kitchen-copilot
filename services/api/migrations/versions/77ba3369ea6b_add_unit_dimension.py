"""add unit dimension

Revision ID: 77ba3369ea6b
Revises: 1f304c2445e6
Create Date: 2026-11-07 14:56:47.353236
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "77ba3369ea6b"
down_revision: Union[str, Sequence[str], None] = "1f304c2445e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add the column as nullable to preserve existing records.
    op.add_column(
        "units",
        sa.Column("dimension", sa.String(length=20), nullable=True),
    )

    # Existing units with unknown dimensions are preserved as "other".
    op.execute(
        "UPDATE units SET dimension = 'other' WHERE dimension IS NULL"
    )

    # Require a dimension for all future units.
    op.alter_column(
        "units",
        "dimension",
        existing_type=sa.String(length=20),
        nullable=False,
    )


def downgrade() -> None:
    op.drop_column("units", "dimension")
