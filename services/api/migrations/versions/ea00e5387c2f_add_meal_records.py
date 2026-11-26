"""add meal records, dishes, leftovers and meal permissions (Stage 5, migration M5)

Revision ID: ea00e5387c2f
Revises: 0e7d99065bd3

Approved 23 November 2026 (docs/STAGE-5-MEAL-PLAN.md, decisions 5-1 to
5-10; closing requires meal.update, reopening is ADMIN and KITCHEN_MANAGER).

1. meal_records: one meal session on one date per campus (at most one that
   is not CANCELLED: partial unique index); expected and actual students,
   staff and guests in separate columns; status OPEN, CLOSED or CANCELLED
   with the closing, reopening and cancellation fields kept consistent by
   checks.
2. meal_dishes: prepared dishes (output and unit) and carried-in retained
   food (interim, client question Q11); available = output + carried, and
   once recorded, available = distributed + remaining. A carried-in line
   references its source leftover through a composite foreign key that also
   fixes the record, dish, campus, RETAINED classification, quantity and
   unit, so the source cannot change or disappear while carried; a unique
   constraint carries each retained line at most once.
3. meal_leftovers: retained, returned to supplier, wasted or disposed, one
   line per classification per dish, in the dish's unit (composite foreign
   key), quantity > 0, remarks required.
4. Permission module `meal` with meal.create, meal.read and meal.update
   (permission rows only). No grant is inserted, changed or deactivated.

Additive: no existing table, column or row changes; stock_movements and its
append-only triggers are not touched. The downgrade refuses while meal
records or meal grants exist.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "ea00e5387c2f"
down_revision: Union[str, Sequence[str], None] = "0e7d99065bd3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MODULE_CODE = "meal"
MODULE_NAME = "Meals"
ACTIONS = ("CREATE", "READ", "UPDATE")


def upgrade() -> None:
    op.create_table(
        "meal_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campus_id", sa.Integer(), nullable=False),
        sa.Column("meal_date", sa.Date(), nullable=False),
        sa.Column("meal_session_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("expected_students", sa.Integer(), nullable=False),
        sa.Column("expected_staff", sa.Integer(), nullable=False),
        sa.Column("expected_guests", sa.Integer(), nullable=False),
        sa.Column("actual_students", sa.Integer(), nullable=True),
        sa.Column("actual_staff", sa.Integer(), nullable=True),
        sa.Column("actual_guests", sa.Integer(), nullable=True),
        sa.Column("remarks", sa.String(length=500), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", sa.Integer(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_usage", sa.JSON(), nullable=True),
        sa.Column("reopened_by", sa.Integer(), nullable=True),
        sa.Column("reopened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reopen_reason", sa.String(length=500), nullable=True),
        sa.Column("reopen_count", sa.Integer(), nullable=False),
        sa.Column("cancelled_by", sa.Integer(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(["campus_id"], ["campuses.id"]),
        sa.ForeignKeyConstraint(["meal_session_id"], ["meal_sessions.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["closed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["reopened_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["cancelled_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("status IN ('OPEN', 'CLOSED', 'CANCELLED')", name="ck_meal_record_status"),
        sa.CheckConstraint(
            "expected_students >= 0 AND expected_staff >= 0 AND expected_guests >= 0",
            name="ck_meal_record_expected",
        ),
        sa.CheckConstraint(
            "(actual_students IS NULL OR actual_students >= 0) "
            "AND (actual_staff IS NULL OR actual_staff >= 0) "
            "AND (actual_guests IS NULL OR actual_guests >= 0)",
            name="ck_meal_record_actual_nonnegative",
        ),
        sa.CheckConstraint(
            "(actual_students IS NULL) = (actual_staff IS NULL) "
            "AND (actual_staff IS NULL) = (actual_guests IS NULL)",
            name="ck_meal_record_actual_complete",
        ),
        sa.CheckConstraint(
            "status <> 'CLOSED' OR (closed_at IS NOT NULL AND actual_students IS NOT NULL)",
            name="ck_meal_record_closed",
        ),
        sa.CheckConstraint("(closed_at IS NULL) = (closed_by IS NULL)", name="ck_meal_record_closed_by"),
        sa.CheckConstraint(
            "(status = 'CANCELLED') = (cancelled_at IS NOT NULL) "
            "AND (cancelled_at IS NULL) = (cancelled_by IS NULL) "
            "AND (cancelled_at IS NULL) = (cancellation_reason IS NULL)",
            name="ck_meal_record_cancelled",
        ),
        sa.CheckConstraint(
            "(reopened_at IS NULL) = (reopened_by IS NULL) "
            "AND (reopened_at IS NULL) = (reopen_reason IS NULL) "
            "AND (reopened_at IS NULL) = (reopen_count = 0) AND reopen_count >= 0",
            name="ck_meal_record_reopened",
        ),
    )
    op.create_index(op.f("ix_meal_records_campus_id"), "meal_records", ["campus_id"])
    op.create_index("ix_meal_records_campus_date", "meal_records", ["campus_id", "meal_date"])
    op.create_index(
        "uq_meal_record_session_date", "meal_records", ["campus_id", "meal_date", "meal_session_id"],
        unique=True, postgresql_where=sa.text("status <> 'CANCELLED'"),
    )

    op.create_table(
        "meal_dishes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campus_id", sa.Integer(), nullable=False),
        sa.Column("meal_record_id", sa.Integer(), nullable=False),
        sa.Column("dish_name", sa.String(length=200), nullable=False),
        sa.Column("menu_id", sa.Integer(), nullable=True),
        sa.Column("unit_id", sa.Integer(), nullable=False),
        sa.Column("output_quantity", sa.Numeric(precision=18, scale=3), nullable=False),
        sa.Column("carried_quantity", sa.Numeric(precision=18, scale=3), nullable=False),
        sa.Column("available_quantity", sa.Numeric(precision=18, scale=3), nullable=False),
        sa.Column("distributed_quantity", sa.Numeric(precision=18, scale=3), nullable=True),
        sa.Column("remaining_quantity", sa.Numeric(precision=18, scale=3), nullable=True),
        sa.Column("remarks", sa.String(length=500), nullable=True),
        sa.Column("source_leftover_id", sa.Integer(), nullable=True),
        sa.Column("source_dish_id", sa.Integer(), nullable=True),
        sa.Column("source_meal_record_id", sa.Integer(), nullable=True),
        sa.Column("source_classification", sa.String(length=30), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["campus_id"], ["campuses.id"]),
        sa.ForeignKeyConstraint(["meal_record_id"], ["meal_records.id"]),
        sa.ForeignKeyConstraint(["menu_id"], ["menus.id"]),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"]),
        sa.ForeignKeyConstraint(["source_dish_id"], ["meal_dishes.id"]),
        sa.ForeignKeyConstraint(["source_meal_record_id"], ["meal_records.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_leftover_id", name="uq_meal_dish_source_leftover"),
        sa.UniqueConstraint("id", "meal_record_id", "campus_id", "unit_id", name="uq_meal_dish_identity"),
        sa.CheckConstraint("output_quantity >= 0 AND carried_quantity >= 0", name="ck_meal_dish_quantities"),
        sa.CheckConstraint(
            "ABS(available_quantity - (output_quantity + carried_quantity)) < 0.0005",
            name="ck_meal_dish_available",
        ),
        sa.CheckConstraint(
            "(source_leftover_id IS NULL AND output_quantity > 0 AND carried_quantity = 0 "
            " AND source_dish_id IS NULL AND source_meal_record_id IS NULL AND source_classification IS NULL) "
            "OR (source_leftover_id IS NOT NULL AND output_quantity = 0 AND carried_quantity > 0 "
            " AND source_dish_id IS NOT NULL AND source_meal_record_id IS NOT NULL "
            " AND source_classification = 'RETAINED')",
            name="ck_meal_dish_kind",
        ),
        sa.CheckConstraint(
            "source_meal_record_id IS NULL OR source_meal_record_id <> meal_record_id",
            name="ck_meal_dish_not_own_source",
        ),
        sa.CheckConstraint("(distributed_quantity IS NULL) = (remaining_quantity IS NULL)",
                           name="ck_meal_dish_distribution_pair"),
        sa.CheckConstraint(
            "distributed_quantity IS NULL OR (distributed_quantity >= 0 AND remaining_quantity >= 0 "
            "AND ABS(available_quantity - (distributed_quantity + remaining_quantity)) < 0.0005)",
            name="ck_meal_dish_reconciles",
        ),
        sa.CheckConstraint("length(trim(dish_name)) > 0", name="ck_meal_dish_name"),
    )
    op.create_index(op.f("ix_meal_dishes_campus_id"), "meal_dishes", ["campus_id"])
    op.create_index(op.f("ix_meal_dishes_meal_record_id"), "meal_dishes", ["meal_record_id"])

    op.create_table(
        "meal_leftovers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campus_id", sa.Integer(), nullable=False),
        sa.Column("meal_record_id", sa.Integer(), nullable=False),
        sa.Column("dish_id", sa.Integer(), nullable=False),
        sa.Column("classification", sa.String(length=30), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=18, scale=3), nullable=False),
        sa.Column("unit_id", sa.Integer(), nullable=False),
        sa.Column("remarks", sa.String(length=500), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campus_id"], ["campuses.id"]),
        sa.ForeignKeyConstraint(["meal_record_id"], ["meal_records.id"]),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["dish_id", "meal_record_id", "campus_id", "unit_id"],
            ["meal_dishes.id", "meal_dishes.meal_record_id", "meal_dishes.campus_id", "meal_dishes.unit_id"],
            name="fk_meal_leftover_dish",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dish_id", "classification", name="uq_meal_leftover_dish_class"),
        sa.UniqueConstraint(
            "id", "dish_id", "meal_record_id", "campus_id", "classification", "quantity", "unit_id",
            name="uq_meal_leftover_identity",
        ),
        sa.CheckConstraint(
            "classification IN ('RETAINED', 'RETURNED_TO_SUPPLIER', 'WASTED', 'DISPOSED')",
            name="ck_meal_leftover_classification",
        ),
        sa.CheckConstraint("quantity > 0", name="ck_meal_leftover_quantity"),
        sa.CheckConstraint("length(trim(remarks)) > 0", name="ck_meal_leftover_remarks"),
    )
    op.create_index(op.f("ix_meal_leftovers_meal_record_id"), "meal_leftovers", ["meal_record_id"])
    op.create_index(op.f("ix_meal_leftovers_dish_id"), "meal_leftovers", ["dish_id"])
    op.create_index(op.f("ix_meal_leftovers_campus_id"), "meal_leftovers", ["campus_id"])

    # The carried-in line's link to its source (added after both tables).
    op.create_foreign_key(
        "fk_meal_dish_carried_from", "meal_dishes", "meal_leftovers",
        ["source_leftover_id", "source_dish_id", "source_meal_record_id", "campus_id",
         "source_classification", "carried_quantity", "unit_id"],
        ["id", "dish_id", "meal_record_id", "campus_id", "classification", "quantity", "unit_id"],
    )

    # ---------- permission rows (5-1); no grants ----------
    bind = op.get_bind()
    module_id = bind.execute(
        sa.text("INSERT INTO modules (name, code) VALUES (:name, :code) RETURNING id"),
        {"name": MODULE_NAME, "code": MODULE_CODE},
    ).scalar_one()
    for action in ACTIONS:
        bind.execute(
            sa.text("INSERT INTO permissions (module_id, action, permission_code) VALUES (:module_id, :action, :code)"),
            {"module_id": module_id, "action": action, "code": f"{MODULE_CODE}.{action.lower()}"},
        )


def downgrade() -> None:
    bind = op.get_bind()
    records = bind.execute(sa.text("SELECT count(*) FROM meal_records")).scalar_one()
    grants = bind.execute(sa.text(
        """
        SELECT count(*) FROM staff_access_assignments a
          JOIN permissions p ON p.id = a.permission_id
          JOIN modules m ON m.id = p.module_id
         WHERE m.code = :code
        """
    ), {"code": MODULE_CODE}).scalar_one()
    if records or grants:
        raise RuntimeError(
            f"Meal data exists ({records} meal records, {grants} meal grants); downgrading would lose it. "
            "Restore the pre-migration backup instead."
        )
    bind.execute(sa.text("DELETE FROM permissions WHERE module_id IN (SELECT id FROM modules WHERE code = :code)"),
                 {"code": MODULE_CODE})
    bind.execute(sa.text("DELETE FROM modules WHERE code = :code"), {"code": MODULE_CODE})

    op.drop_constraint("fk_meal_dish_carried_from", "meal_dishes", type_="foreignkey")
    op.drop_index(op.f("ix_meal_leftovers_campus_id"), table_name="meal_leftovers")
    op.drop_index(op.f("ix_meal_leftovers_dish_id"), table_name="meal_leftovers")
    op.drop_index(op.f("ix_meal_leftovers_meal_record_id"), table_name="meal_leftovers")
    op.drop_table("meal_leftovers")
    op.drop_index(op.f("ix_meal_dishes_meal_record_id"), table_name="meal_dishes")
    op.drop_index(op.f("ix_meal_dishes_campus_id"), table_name="meal_dishes")
    op.drop_table("meal_dishes")
    op.drop_index("uq_meal_record_session_date", table_name="meal_records")
    op.drop_index("ix_meal_records_campus_date", table_name="meal_records")
    op.drop_index(op.f("ix_meal_records_campus_id"), table_name="meal_records")
    op.drop_table("meal_records")
