"""add outsourced orders, deliveries and received meal-dish lines (Stage 8a, migration M6)

Revision ID: b8e4c2a9d175
Revises: f3a8c2d61b47

Stage 8a (docs/STAGE-8-IMPLEMENTATION-PLAN.md; project decisions P8-1 to
P8-5 and P8-7, implemented 24 November 2026 with documented interim rules).

1. outsourced_orders: OO-numbered per campus; order date, meal date, exact
   meal session, supplier; DRAFT, ORDERED or CANCELLED (with who, when and
   why).
2. outsourced_order_lines: OUTSOURCED item, ordered quantity (> 0), explicit
   unit, unit rate (>= 0), line total; optional link to one supplier bill
   line (unique).
3. outsourced_deliveries: OD-numbered per campus; DRAFT, CONFIRMED or
   CANCELLED.
4. outsourced_delivery_lines: received (> 0), rejected (0..received, reason
   required when > 0) and accepted (= received - rejected) per order line,
   in the order line's unit (composite foreign key).
5. meal_dishes: received_quantity (NOT NULL, default 0) and
   source_delivery_line_id (unique), with a composite foreign key to the
   delivery line (id, accepted quantity, unit, campus). The checks
   ck_meal_dish_quantities, ck_meal_dish_available and ck_meal_dish_kind are
   dropped and recreated with a third kind, "received"; every existing row
   (prepared or carried, received_quantity 0) satisfies both the old and the
   new checks. The carried-from foreign key is not touched.

No permission row, grant or module changes (the existing outsourced_food.*
codes are used). No stock, purchase, receipt or planning table changes.
The downgrade refuses while outsourced orders or received meal-dish lines
exist.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8e4c2a9d175"
down_revision: Union[str, Sequence[str], None] = "f3a8c2d61b47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_QUANTITIES = "output_quantity >= 0 AND carried_quantity >= 0"
OLD_AVAILABLE = "ABS(available_quantity - (output_quantity + carried_quantity)) < 0.0005"
OLD_KIND = (
    "(source_leftover_id IS NULL AND output_quantity > 0 AND carried_quantity = 0 "
    " AND source_dish_id IS NULL AND source_meal_record_id IS NULL AND source_classification IS NULL) "
    "OR (source_leftover_id IS NOT NULL AND output_quantity = 0 AND carried_quantity > 0 "
    " AND source_dish_id IS NOT NULL AND source_meal_record_id IS NOT NULL "
    " AND source_classification = 'RETAINED')"
)

NEW_QUANTITIES = "output_quantity >= 0 AND carried_quantity >= 0 AND received_quantity >= 0"
NEW_AVAILABLE = "ABS(available_quantity - (output_quantity + carried_quantity + received_quantity)) < 0.0005"
NEW_KIND = (
    "(source_leftover_id IS NULL AND source_delivery_line_id IS NULL AND output_quantity > 0 "
    " AND carried_quantity = 0 AND received_quantity = 0 "
    " AND source_dish_id IS NULL AND source_meal_record_id IS NULL AND source_classification IS NULL) "
    "OR (source_leftover_id IS NOT NULL AND source_delivery_line_id IS NULL AND output_quantity = 0 "
    " AND carried_quantity > 0 AND received_quantity = 0 "
    " AND source_dish_id IS NOT NULL AND source_meal_record_id IS NOT NULL "
    " AND source_classification = 'RETAINED') "
    "OR (source_delivery_line_id IS NOT NULL AND source_leftover_id IS NULL AND output_quantity = 0 "
    " AND carried_quantity = 0 AND received_quantity > 0 "
    " AND source_dish_id IS NULL AND source_meal_record_id IS NULL AND source_classification IS NULL)"
)


def _who(prefix: str) -> list:
    return [
        sa.Column(f"{prefix}_by", sa.Integer(), nullable=True),
        sa.Column(f"{prefix}_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    # ---- 1. outsourced_orders ----
    op.create_table(
        "outsourced_orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campus_id", sa.Integer(), nullable=False),
        sa.Column("order_seq", sa.Integer(), nullable=False),
        sa.Column("order_number", sa.String(length=30), nullable=False),
        sa.Column("order_date", sa.Date(), nullable=False),
        sa.Column("meal_date", sa.Date(), nullable=False),
        sa.Column("meal_session_id", sa.Integer(), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        *_who("ordered"),
        *_who("cancelled"),
        sa.Column("cancellation_reason", sa.String(length=500), nullable=True),
        sa.CheckConstraint("status IN ('DRAFT', 'ORDERED', 'CANCELLED')", name="ck_outsourced_order_status"),
        sa.CheckConstraint("(ordered_at IS NULL) = (ordered_by IS NULL)", name="ck_outsourced_order_ordered_by"),
        sa.CheckConstraint("status <> 'ORDERED' OR ordered_at IS NOT NULL", name="ck_outsourced_order_ordered"),
        sa.CheckConstraint(
            "(status = 'CANCELLED') = (cancelled_at IS NOT NULL) "
            "AND (cancelled_at IS NULL) = (cancelled_by IS NULL) "
            "AND (cancelled_at IS NULL) = (cancellation_reason IS NULL)",
            name="ck_outsourced_order_cancelled",
        ),
        sa.ForeignKeyConstraint(["campus_id"], ["campuses.id"]),
        sa.ForeignKeyConstraint(["meal_session_id"], ["meal_sessions.id"]),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["ordered_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["cancelled_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campus_id", "order_seq", name="uq_outsourced_order_seq"),
        sa.UniqueConstraint("campus_id", "order_number", name="uq_outsourced_order_number"),
        sa.UniqueConstraint("id", "campus_id", name="uq_outsourced_order_identity"),
    )
    op.create_index(op.f("ix_outsourced_orders_campus_id"), "outsourced_orders", ["campus_id"])
    op.create_index("ix_outsourced_orders_campus_meal", "outsourced_orders",
                    ["campus_id", "meal_date", "meal_session_id"])

    # ---- 2. outsourced_order_lines ----
    op.create_table(
        "outsourced_order_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campus_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("ordered_quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("unit_id", sa.Integer(), nullable=False),
        sa.Column("unit_rate", sa.Numeric(18, 4), nullable=False),
        sa.Column("line_total", sa.Numeric(18, 2), nullable=False),
        sa.Column("remarks", sa.String(length=500), nullable=True),
        sa.Column("purchase_item_id", sa.Integer(), nullable=True),
        *_who("linked"),
        sa.CheckConstraint("ordered_quantity > 0", name="ck_outsourced_order_line_quantity"),
        sa.CheckConstraint("unit_rate >= 0", name="ck_outsourced_order_line_rate"),
        sa.CheckConstraint("line_total >= 0", name="ck_outsourced_order_line_total"),
        sa.CheckConstraint(
            "(purchase_item_id IS NULL) = (linked_at IS NULL) AND (linked_at IS NULL) = (linked_by IS NULL)",
            name="ck_outsourced_order_line_bill_link",
        ),
        sa.ForeignKeyConstraint(["campus_id"], ["campuses.id"]),
        sa.ForeignKeyConstraint(["order_id", "campus_id"], ["outsourced_orders.id", "outsourced_orders.campus_id"],
                                name="fk_outsourced_order_line_order"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"]),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"]),
        sa.ForeignKeyConstraint(["purchase_item_id"], ["purchase_items.id"]),
        sa.ForeignKeyConstraint(["linked_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", "item_id", name="uq_outsourced_order_line_item"),
        sa.UniqueConstraint("purchase_item_id", name="uq_outsourced_order_line_bill_line"),
        sa.UniqueConstraint("id", "order_id", "campus_id", "unit_id", name="uq_outsourced_order_line_identity"),
    )
    op.create_index(op.f("ix_outsourced_order_lines_campus_id"), "outsourced_order_lines", ["campus_id"])
    op.create_index(op.f("ix_outsourced_order_lines_order_id"), "outsourced_order_lines", ["order_id"])

    # ---- 3. outsourced_deliveries ----
    op.create_table(
        "outsourced_deliveries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campus_id", sa.Integer(), nullable=False),
        sa.Column("delivery_seq", sa.Integer(), nullable=False),
        sa.Column("delivery_number", sa.String(length=30), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("delivery_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("remarks", sa.String(length=500), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        *_who("confirmed"),
        *_who("cancelled"),
        sa.Column("cancellation_reason", sa.String(length=500), nullable=True),
        sa.CheckConstraint("status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')", name="ck_outsourced_delivery_status"),
        sa.CheckConstraint("(confirmed_at IS NULL) = (confirmed_by IS NULL)", name="ck_outsourced_delivery_confirmed_by"),
        sa.CheckConstraint("status <> 'CONFIRMED' OR confirmed_at IS NOT NULL", name="ck_outsourced_delivery_confirmed"),
        sa.CheckConstraint(
            "(status = 'CANCELLED') = (cancelled_at IS NOT NULL) "
            "AND (cancelled_at IS NULL) = (cancelled_by IS NULL) "
            "AND (cancelled_at IS NULL) = (cancellation_reason IS NULL)",
            name="ck_outsourced_delivery_cancelled",
        ),
        sa.ForeignKeyConstraint(["campus_id"], ["campuses.id"]),
        sa.ForeignKeyConstraint(["order_id", "campus_id"], ["outsourced_orders.id", "outsourced_orders.campus_id"],
                                name="fk_outsourced_delivery_order"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["confirmed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["cancelled_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campus_id", "delivery_seq", name="uq_outsourced_delivery_seq"),
        sa.UniqueConstraint("campus_id", "delivery_number", name="uq_outsourced_delivery_number"),
        sa.UniqueConstraint("id", "order_id", "campus_id", name="uq_outsourced_delivery_identity"),
    )
    op.create_index(op.f("ix_outsourced_deliveries_campus_id"), "outsourced_deliveries", ["campus_id"])
    op.create_index(op.f("ix_outsourced_deliveries_order_id"), "outsourced_deliveries", ["order_id"])

    # ---- 4. outsourced_delivery_lines ----
    op.create_table(
        "outsourced_delivery_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campus_id", sa.Integer(), nullable=False),
        sa.Column("delivery_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("order_line_id", sa.Integer(), nullable=False),
        sa.Column("unit_id", sa.Integer(), nullable=False),
        sa.Column("received_quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("rejected_quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("accepted_quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("rejection_reason", sa.String(length=500), nullable=True),
        sa.Column("remarks", sa.String(length=500), nullable=True),
        sa.CheckConstraint("received_quantity > 0", name="ck_outsourced_delivery_line_received"),
        sa.CheckConstraint("rejected_quantity >= 0 AND rejected_quantity <= received_quantity",
                           name="ck_outsourced_delivery_line_rejected"),
        sa.CheckConstraint(
            "accepted_quantity >= 0 "
            "AND ABS(accepted_quantity - (received_quantity - rejected_quantity)) < 0.0005",
            name="ck_outsourced_delivery_line_accepted",
        ),
        sa.CheckConstraint(
            "rejected_quantity = 0 OR (rejection_reason IS NOT NULL AND length(trim(rejection_reason)) > 0)",
            name="ck_outsourced_delivery_line_reason",
        ),
        sa.ForeignKeyConstraint(["campus_id"], ["campuses.id"]),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"]),
        sa.ForeignKeyConstraint(
            ["delivery_id", "order_id", "campus_id"],
            ["outsourced_deliveries.id", "outsourced_deliveries.order_id", "outsourced_deliveries.campus_id"],
            name="fk_outsourced_delivery_line_delivery",
        ),
        sa.ForeignKeyConstraint(
            ["order_line_id", "order_id", "campus_id", "unit_id"],
            ["outsourced_order_lines.id", "outsourced_order_lines.order_id", "outsourced_order_lines.campus_id",
             "outsourced_order_lines.unit_id"],
            name="fk_outsourced_delivery_line_order_line",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("delivery_id", "order_line_id", name="uq_outsourced_delivery_line"),
        sa.UniqueConstraint("id", "accepted_quantity", "unit_id", "campus_id",
                            name="uq_outsourced_delivery_line_identity"),
    )
    op.create_index(op.f("ix_outsourced_delivery_lines_campus_id"), "outsourced_delivery_lines", ["campus_id"])
    op.create_index(op.f("ix_outsourced_delivery_lines_delivery_id"), "outsourced_delivery_lines", ["delivery_id"])
    op.create_index(op.f("ix_outsourced_delivery_lines_order_line_id"), "outsourced_delivery_lines", ["order_line_id"])

    # ---- 5. meal_dishes: the received kind ----
    op.add_column("meal_dishes", sa.Column("received_quantity", sa.Numeric(18, 3), nullable=False,
                                           server_default=sa.text("0")))
    op.add_column("meal_dishes", sa.Column("source_delivery_line_id", sa.Integer(), nullable=True))
    op.drop_constraint("ck_meal_dish_quantities", "meal_dishes", type_="check")
    op.drop_constraint("ck_meal_dish_available", "meal_dishes", type_="check")
    op.drop_constraint("ck_meal_dish_kind", "meal_dishes", type_="check")
    op.create_check_constraint("ck_meal_dish_quantities", "meal_dishes", NEW_QUANTITIES)
    op.create_check_constraint("ck_meal_dish_available", "meal_dishes", NEW_AVAILABLE)
    op.create_check_constraint("ck_meal_dish_kind", "meal_dishes", NEW_KIND)
    op.create_unique_constraint("uq_meal_dish_source_delivery_line", "meal_dishes", ["source_delivery_line_id"])
    op.create_foreign_key(
        "fk_meal_dish_received_from", "meal_dishes", "outsourced_delivery_lines",
        ["source_delivery_line_id", "received_quantity", "unit_id", "campus_id"],
        ["id", "accepted_quantity", "unit_id", "campus_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    orders = bind.execute(sa.text("SELECT count(*) FROM outsourced_orders")).scalar_one()
    received = bind.execute(sa.text(
        "SELECT count(*) FROM meal_dishes WHERE source_delivery_line_id IS NOT NULL OR received_quantity <> 0"
    )).scalar_one()
    if orders or received:
        raise RuntimeError(
            f"Outsourced food data exists ({orders} outsourced orders, {received} received meal-dish lines); "
            "downgrading would lose it. Restore the pre-migration backup instead."
        )

    op.drop_constraint("fk_meal_dish_received_from", "meal_dishes", type_="foreignkey")
    op.drop_constraint("uq_meal_dish_source_delivery_line", "meal_dishes", type_="unique")
    op.drop_constraint("ck_meal_dish_kind", "meal_dishes", type_="check")
    op.drop_constraint("ck_meal_dish_available", "meal_dishes", type_="check")
    op.drop_constraint("ck_meal_dish_quantities", "meal_dishes", type_="check")
    op.drop_column("meal_dishes", "source_delivery_line_id")
    op.drop_column("meal_dishes", "received_quantity")
    op.create_check_constraint("ck_meal_dish_quantities", "meal_dishes", OLD_QUANTITIES)
    op.create_check_constraint("ck_meal_dish_available", "meal_dishes", OLD_AVAILABLE)
    op.create_check_constraint("ck_meal_dish_kind", "meal_dishes", OLD_KIND)

    op.drop_index(op.f("ix_outsourced_delivery_lines_order_line_id"), table_name="outsourced_delivery_lines")
    op.drop_index(op.f("ix_outsourced_delivery_lines_delivery_id"), table_name="outsourced_delivery_lines")
    op.drop_index(op.f("ix_outsourced_delivery_lines_campus_id"), table_name="outsourced_delivery_lines")
    op.drop_table("outsourced_delivery_lines")
    op.drop_index(op.f("ix_outsourced_deliveries_order_id"), table_name="outsourced_deliveries")
    op.drop_index(op.f("ix_outsourced_deliveries_campus_id"), table_name="outsourced_deliveries")
    op.drop_table("outsourced_deliveries")
    op.drop_index(op.f("ix_outsourced_order_lines_order_id"), table_name="outsourced_order_lines")
    op.drop_index(op.f("ix_outsourced_order_lines_campus_id"), table_name="outsourced_order_lines")
    op.drop_table("outsourced_order_lines")
    op.drop_index("ix_outsourced_orders_campus_meal", table_name="outsourced_orders")
    op.drop_index(op.f("ix_outsourced_orders_campus_id"), table_name="outsourced_orders")
    op.drop_table("outsourced_orders")
