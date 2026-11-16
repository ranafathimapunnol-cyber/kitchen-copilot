"""add waste tracking module and tables

Revision ID: d4e8a91b2c70
Revises: c91f7a2b4e60
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e8a91b2c70"
down_revision: Union[str, Sequence[str], None] = "c91f7a2b4e60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    # ---------------------------------------------------------
    # 1. WASTE RECORDS
    # ---------------------------------------------------------

    op.create_table(
        "waste_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("campus_id", sa.Integer(), nullable=False),
        sa.Column("waste_date", sa.Date(), nullable=False),
        sa.Column("meal_session_id", sa.Integer(), nullable=True),
        sa.Column("recorded_by", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["campus_id"], ["campuses.id"]),
        sa.ForeignKeyConstraint(
            ["meal_session_id"], ["meal_sessions.id"]
        ),
        sa.ForeignKeyConstraint(["recorded_by"], ["users.id"]),
    )

    op.create_index(
        "ix_waste_records_campus_id",
        "waste_records",
        ["campus_id"],
    )

    op.create_index(
        "ix_waste_records_campus_date",
        "waste_records",
        ["campus_id", "waste_date"],
    )

    # ---------------------------------------------------------
    # 2. WASTE ITEMS
    # ---------------------------------------------------------

    op.create_table(
        "waste_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("campus_id", sa.Integer(), nullable=False),
        sa.Column("waste_record_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=True),
        sa.Column("menu_id", sa.Integer(), nullable=True),
        sa.Column("unit_id", sa.Integer(), nullable=False),
        sa.Column("food_name", sa.String(length=150), nullable=False),
        sa.Column("waste_type", sa.String(length=30), nullable=False),
        sa.Column(
            "quantity",
            sa.Numeric(18, 3),
            nullable=False,
        ),
        sa.Column("waste_stage", sa.String(length=30), nullable=False),
        sa.Column("waste_reason", sa.String(length=30), nullable=False),
        sa.Column(
            "estimated_cost",
            sa.Numeric(18, 2),
            nullable=False,
            server_default="0",
        ),

        sa.ForeignKeyConstraint(["campus_id"], ["campuses.id"]),
        sa.ForeignKeyConstraint(
            ["waste_record_id"], ["waste_records.id"]
        ),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"]),
        sa.ForeignKeyConstraint(["menu_id"], ["menus.id"]),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"]),

        sa.CheckConstraint(
            "quantity > 0",
            name="ck_waste_item_quantity_positive",
        ),
        sa.CheckConstraint(
            "estimated_cost >= 0",
            name="ck_waste_item_cost_nonnegative",
        ),
        sa.CheckConstraint(
            "waste_type IN ('RAW_INGREDIENT', 'PREPARED_FOOD')",
            name="ck_waste_item_type",
        ),
        sa.CheckConstraint(
            """
            (
                waste_type = 'RAW_INGREDIENT'
                AND item_id IS NOT NULL
            )
            OR
            (
                waste_type = 'PREPARED_FOOD'
                AND item_id IS NULL
                AND length(trim(food_name)) > 0
            )
            """,
            name="ck_waste_item_type_reference",
        ),
        sa.CheckConstraint(
            """
            waste_stage IN (
                'STORAGE',
                'PREPARATION',
                'COOKING',
                'SERVING',
                'AFTER_MEAL'
            )
            """,
            name="ck_waste_item_stage",
        ),
        sa.CheckConstraint(
            """
            waste_reason IN (
                'SPOILED',
                'EXPIRED',
                'DAMAGED',
                'OVERPRODUCTION',
                'LEFTOVER',
                'PLATE_WASTE',
                'OTHER'
            )
            """,
            name="ck_waste_item_reason",
        ),
    )

    op.create_index(
        "ix_waste_items_campus_id",
        "waste_items",
        ["campus_id"],
    )

    op.create_index(
        "ix_waste_items_record_id",
        "waste_items",
        ["waste_record_id"],
    )

    op.create_index(
        "ix_waste_items_campus_type",
        "waste_items",
        ["campus_id", "waste_type"],
    )

    # ---------------------------------------------------------
    # 3. ADD WASTE TRACKING MODULE
    # ---------------------------------------------------------

    bind = op.get_bind()

    result = bind.execute(
        sa.text(
            """
            INSERT INTO modules (name, code)
            VALUES (:name, :code)
            RETURNING id
            """
        ),
        {
            "name": "Waste Tracking",
            "code": "waste_tracking",
        },
    )

    module_id = result.scalar_one()

    # ---------------------------------------------------------
    # 4. ADD THREE PERMISSIONS
    # ---------------------------------------------------------

    permissions = [
        ("CREATE", "waste_tracking.create"),
        ("READ", "waste_tracking.read"),
        ("UPDATE", "waste_tracking.update"),
    ]

    for action, permission_code in permissions:
        bind.execute(
            sa.text(
                """
                INSERT INTO permissions (
                    module_id,
                    action,
                    permission_code
                )
                VALUES (
                    :module_id,
                    :action,
                    :permission_code
                )
                """
            ),
            {
                "module_id": module_id,
                "action": action,
                "permission_code": permission_code,
            },
        )


def downgrade() -> None:

    # Remove only the permissions and module introduced here.
    op.execute(
        """
        DELETE FROM permissions
        WHERE permission_code IN (
            'waste_tracking.create',
            'waste_tracking.read',
            'waste_tracking.update'
        )
        """
    )

    op.execute(
        """
        DELETE FROM modules
        WHERE code = 'waste_tracking'
        """
    )

    op.drop_index(
        "ix_waste_items_campus_type",
        table_name="waste_items",
    )
    op.drop_index(
        "ix_waste_items_record_id",
        table_name="waste_items",
    )
    op.drop_index(
        "ix_waste_items_campus_id",
        table_name="waste_items",
    )
    op.drop_table("waste_items")

    op.drop_index(
        "ix_waste_records_campus_date",
        table_name="waste_records",
    )
    op.drop_index(
        "ix_waste_records_campus_id",
        table_name="waste_records",
    )
    op.drop_table("waste_records")
