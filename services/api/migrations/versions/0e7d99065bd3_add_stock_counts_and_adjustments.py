"""add physical stock counts, adjustments and stock_count permissions (Stage 4, migration M2c)

Revision ID: 0e7d99065bd3
Revises: c7d2e9f4a816

Approved 23 November 2026 (docs/STAGE-4-STOCK-PLAN.md, decisions S1, S6
and S7, client question Q10 interim). Slice 4c authorised the same day.

1. stock_counts: a physical count, numbered SC-00001 per campus, with the
   count time (when it was saved), the counter and a reason. Never changed
   once saved.
2. stock_count_items: per counted item, the physical quantity (as entered
   and in the standard unit, with the conversion factor used), the system
   balance when the count was saved and the difference, stored and never
   recalculated (a check keeps difference = physical - system balance).
3. stock_adjustments: a request to correct stock by one count line's
   difference. One per count line; at most one PENDING per item per campus
   (partial unique index); status PENDING, APPROVED or REJECTED with the
   decider, time and reason. The counter is copied from the count through a
   composite foreign key, and a check refuses any decision by the counter
   (independent approval).
4. Permission module stock_count with stock_count.create and
   stock_count.read (permission rows only, decision S1). No grant is
   inserted, changed or deactivated.

Additive: no existing table, column or row is changed; stock_movements and
its append-only triggers (M2b) are not touched (ADJUSTMENT is already an
allowed movement type). The downgrade refuses to run once counts,
adjustment movements or stock_count grants exist.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0e7d99065bd3"
down_revision: Union[str, Sequence[str], None] = "c7d2e9f4a816"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MODULE_CODE = "stock_count"
MODULE_NAME = "Stock Counts"
ACTIONS = ("CREATE", "READ")


def upgrade() -> None:
    # ---------- counts ----------
    op.create_table(
        "stock_counts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campus_id", sa.Integer(), nullable=False),
        sa.Column("count_seq", sa.Integer(), nullable=False),
        sa.Column("count_number", sa.String(length=20), nullable=False),
        sa.Column("counted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("counted_by", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("remarks", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(["campus_id"], ["campuses.id"]),
        sa.ForeignKeyConstraint(["counted_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campus_id", "count_seq", name="uq_stock_count_seq"),
        sa.UniqueConstraint("campus_id", "count_number", name="uq_stock_count_number"),
        sa.UniqueConstraint("id", "counted_by", name="uq_stock_count_counter"),
    )
    op.create_index(op.f("ix_stock_counts_campus_id"), "stock_counts", ["campus_id"])
    op.create_index("ix_stock_counts_campus_counted_at", "stock_counts", ["campus_id", "counted_at"])

    op.create_table(
        "stock_count_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campus_id", sa.Integer(), nullable=False),
        sa.Column("count_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=18, scale=3), nullable=False),
        sa.Column("unit_id", sa.Integer(), nullable=False),
        sa.Column("conversion_factor", sa.Numeric(precision=24, scale=12), nullable=False),
        sa.Column("standard_quantity", sa.Numeric(precision=18, scale=3), nullable=False),
        sa.Column("standard_unit_id", sa.Integer(), nullable=False),
        sa.Column("system_balance", sa.Numeric(precision=18, scale=3), nullable=False),
        sa.Column("difference", sa.Numeric(precision=18, scale=3), nullable=False),
        sa.Column("remarks", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(["campus_id"], ["campuses.id"]),
        sa.ForeignKeyConstraint(["count_id"], ["stock_counts.id"]),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"]),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"]),
        sa.ForeignKeyConstraint(["standard_unit_id"], ["units.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("count_id", "item_id", name="uq_stock_count_item"),
        sa.UniqueConstraint("id", "count_id", "item_id", name="uq_stock_count_item_line"),
        sa.CheckConstraint("quantity >= 0", name="ck_stock_count_item_quantity"),
        sa.CheckConstraint("standard_quantity >= 0", name="ck_stock_count_item_standard_quantity"),
        sa.CheckConstraint("conversion_factor > 0", name="ck_stock_count_item_conversion_factor"),
        sa.CheckConstraint(
            "ABS(difference - (standard_quantity - system_balance)) < 0.0005",
            name="ck_stock_count_item_difference",
        ),
    )
    op.create_index(op.f("ix_stock_count_items_campus_id"), "stock_count_items", ["campus_id"])
    op.create_index(op.f("ix_stock_count_items_count_id"), "stock_count_items", ["count_id"])

    # ---------- adjustments ----------
    op.create_table(
        "stock_adjustments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campus_id", sa.Integer(), nullable=False),
        sa.Column("count_id", sa.Integer(), nullable=False),
        sa.Column("count_item_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("counted_by", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("raised_by", sa.Integer(), nullable=False),
        sa.Column("raised_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_by", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(["campus_id"], ["campuses.id"]),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"]),
        sa.ForeignKeyConstraint(["counted_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["raised_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["decided_by"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["count_item_id", "count_id", "item_id"],
            ["stock_count_items.id", "stock_count_items.count_id", "stock_count_items.item_id"],
            name="fk_stock_adjustment_count_line",
        ),
        sa.ForeignKeyConstraint(
            ["count_id", "counted_by"],
            ["stock_counts.id", "stock_counts.counted_by"],
            name="fk_stock_adjustment_counter",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("count_item_id", name="uq_stock_adjustment_count_item"),
        sa.CheckConstraint("status IN ('PENDING', 'APPROVED', 'REJECTED')", name="ck_stock_adjustment_status"),
        sa.CheckConstraint(
            "(status = 'PENDING') = (decided_at IS NULL) "
            "AND (decided_at IS NULL) = (decided_by IS NULL)",
            name="ck_stock_adjustment_decision_complete",
        ),
        sa.CheckConstraint(
            "status <> 'REJECTED' OR decision_reason IS NOT NULL",
            name="ck_stock_adjustment_rejection_reason",
        ),
        sa.CheckConstraint(
            "decided_by IS NULL OR decided_by <> counted_by",
            name="ck_stock_adjustment_independent_approver",
        ),
    )
    op.create_index(op.f("ix_stock_adjustments_campus_id"), "stock_adjustments", ["campus_id"])
    op.create_index(op.f("ix_stock_adjustments_count_id"), "stock_adjustments", ["count_id"])
    op.create_index(
        "uq_stock_adjustment_pending_item",
        "stock_adjustments",
        ["campus_id", "item_id"],
        unique=True,
        postgresql_where=sa.text("status = 'PENDING'"),
    )

    # ---------- permission rows (S1); no grants ----------
    bind = op.get_bind()
    module_id = bind.execute(
        sa.text("INSERT INTO modules (name, code) VALUES (:name, :code) RETURNING id"),
        {"name": MODULE_NAME, "code": MODULE_CODE},
    ).scalar_one()
    for action in ACTIONS:
        bind.execute(
            sa.text(
                "INSERT INTO permissions (module_id, action, permission_code) "
                "VALUES (:module_id, :action, :code)"
            ),
            {"module_id": module_id, "action": action, "code": f"{MODULE_CODE}.{action.lower()}"},
        )


def downgrade() -> None:
    bind = op.get_bind()
    counts = bind.execute(sa.text("SELECT count(*) FROM stock_counts")).scalar_one()
    adjustment_movements = bind.execute(sa.text(
        "SELECT count(*) FROM stock_movements WHERE reference_type = 'STOCK_ADJUSTMENT'"
    )).scalar_one()
    grants = bind.execute(sa.text(
        """
        SELECT count(*) FROM staff_access_assignments a
          JOIN permissions p ON p.id = a.permission_id
          JOIN modules m ON m.id = p.module_id
         WHERE m.code = :code
        """
    ), {"code": MODULE_CODE}).scalar_one()
    if counts or adjustment_movements or grants:
        raise RuntimeError(
            f"Stock count data exists ({counts} counts, {adjustment_movements} adjustment movements, "
            f"{grants} stock_count grants); downgrading would lose it. Restore the pre-migration "
            "backup instead."
        )

    bind.execute(
        sa.text(
            "DELETE FROM permissions WHERE module_id IN (SELECT id FROM modules WHERE code = :code)"
        ),
        {"code": MODULE_CODE},
    )
    bind.execute(sa.text("DELETE FROM modules WHERE code = :code"), {"code": MODULE_CODE})

    op.drop_index("uq_stock_adjustment_pending_item", table_name="stock_adjustments")
    op.drop_index(op.f("ix_stock_adjustments_count_id"), table_name="stock_adjustments")
    op.drop_index(op.f("ix_stock_adjustments_campus_id"), table_name="stock_adjustments")
    op.drop_table("stock_adjustments")
    op.drop_index(op.f("ix_stock_count_items_count_id"), table_name="stock_count_items")
    op.drop_index(op.f("ix_stock_count_items_campus_id"), table_name="stock_count_items")
    op.drop_table("stock_count_items")
    op.drop_index("ix_stock_counts_campus_counted_at", table_name="stock_counts")
    op.drop_index(op.f("ix_stock_counts_campus_id"), table_name="stock_counts")
    op.drop_table("stock_counts")
