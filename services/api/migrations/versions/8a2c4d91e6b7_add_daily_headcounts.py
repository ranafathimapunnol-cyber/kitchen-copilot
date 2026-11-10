"""add daily headcounts

Revision ID: 8a2c4d91e6b7
Revises: fb84dd6fb038
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8a2c4d91e6b7"
down_revision: Union[str, Sequence[str], None] = "fb84dd6fb038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "daily_headcounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("headcount_date", sa.Date(), nullable=False),
        sa.Column("student_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("campus_id", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "student_count >= 0",
            name="ck_daily_headcount_nonnegative",
        ),
        sa.ForeignKeyConstraint(["campus_id"], ["campuses.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "campus_id",
            "headcount_date",
            name="uq_daily_headcount_campus_date",
        ),
    )

    op.create_index(
        op.f("ix_daily_headcounts_campus_id"),
        "daily_headcounts",
        ["campus_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_daily_headcounts_campus_id"),
        table_name="daily_headcounts",
    )
    op.drop_table("daily_headcounts")
