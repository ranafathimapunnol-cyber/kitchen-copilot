"""add stock ledger columns and opening stock (Stage 4, migration M2a)

Revision ID: b5e1d7c3a920
Revises: a3c9e1f47b20

Approved 23 November 2026 (docs/STAGE-4-STOCK-PLAN.md, decisions S3 and S7).

1. stock_movements gains the ledger columns:
   - direction: +1 (stock in) or -1 (stock out); quantity stays positive;
   - effective_at: when the stock moved (the transaction date);
     created_at remains the posting time;
   - source_key: what posted the row (RECEIPT_ITEM:<id>, OPENING:<id>,
     REVERSAL:<movement id>), unique per campus so nothing posts twice;
   - reversal_of_id: the movement a REVERSAL row reverses (each at most once).
   Check constraints fix the allowed movement types and the direction of
   each fixed-direction type. An index serves the ledger replay order
   (campus, item, effective_at, id).
2. Backfill, limited by the approval to the existing RECEIPT movements:
   direction +1, effective_at = the goods receipt's acceptance time (the
   posting time if a receipt has none), source_key RECEIPT_ITEM:<receipt
   item id>. Any other existing movement stops the migration: it would need
   a separate decision.
3. stock_openings: opening stock per item (decision S3), with a partial
   unique index allowing one ACTIVE opening per item per campus.

Additive: no existing column, value or row is removed; the backfill only
fills the new columns. The downgrade refuses to run once Stage 4 data
exists (opening entries or non-receipt movements), because dropping the
columns would then lose their meaning.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b5e1d7c3a920"
down_revision: Union[str, Sequence[str], None] = "a3c9e1f47b20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MOVEMENT_TYPES = (
    "OPENING", "RECEIPT", "ISSUE", "UNUSED_RETURN",
    "SUPPLIER_RETURN", "ADJUSTMENT", "REVERSAL",
)

CHECKS = {
    "ck_stock_movement_direction": "direction IN (1, -1)",
    "ck_stock_movement_type": "movement_type IN ("
    + ", ".join(f"'{t}'" for t in MOVEMENT_TYPES) + ")",
    "ck_stock_movement_inflow_direction":
        "movement_type NOT IN ('OPENING', 'RECEIPT', 'UNUSED_RETURN') "
        "OR direction = 1",
    "ck_stock_movement_outflow_direction":
        "movement_type NOT IN ('ISSUE', 'SUPPLIER_RETURN') OR direction = -1",
    "ck_stock_movement_reversal_link":
        "(movement_type = 'REVERSAL') = (reversal_of_id IS NOT NULL)",
}


def upgrade() -> None:
    bind = op.get_bind()

    # ---------------------------------------------------------
    # 0. ONLY RECEIPT MOVEMENTS MAY EXIST (the approved backfill)
    # ---------------------------------------------------------
    others = bind.execute(sa.text(
        "SELECT count(*) FROM stock_movements WHERE movement_type <> 'RECEIPT'"
    )).scalar_one()
    if others:
        raise RuntimeError(
            f"{others} existing stock movement(s) are not RECEIPT movements. "
            "The approved backfill covers receipt movements only; stop and "
            "ask for a decision."
        )

    # ---------------------------------------------------------
    # 1. LEDGER COLUMNS (nullable until filled)
    # ---------------------------------------------------------
    op.add_column("stock_movements", sa.Column("direction", sa.SmallInteger(), nullable=True))
    op.add_column("stock_movements", sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("stock_movements", sa.Column("source_key", sa.String(length=100), nullable=True))
    op.add_column("stock_movements", sa.Column("reversal_of_id", sa.Integer(), nullable=True))

    # ---------------------------------------------------------
    # 2. BACKFILL THE EXISTING RECEIPT MOVEMENTS
    # ---------------------------------------------------------
    existing = bind.execute(sa.text("SELECT count(*) FROM stock_movements")).scalar_one()
    filled = bind.execute(sa.text(
        """
        UPDATE stock_movements AS m
           SET direction = 1,
               effective_at = COALESCE(
                   (SELECT g.accepted_at
                      FROM goods_receipts g
                     WHERE m.reference_type = 'GOODS_RECEIPT'
                       AND g.id = m.reference_id
                       AND g.campus_id = m.campus_id),
                   m.created_at),
               source_key = CASE
                   WHEN m.receipt_item_id IS NOT NULL
                   THEN 'RECEIPT_ITEM:' || m.receipt_item_id
                   ELSE 'MOVEMENT:' || m.id
               END
         WHERE m.movement_type = 'RECEIPT'
        """
    )).rowcount
    if filled != existing:
        raise RuntimeError(
            f"Backfill filled {filled} of {existing} stock movements; stopping."
        )

    op.alter_column("stock_movements", "direction", nullable=False)
    op.alter_column("stock_movements", "effective_at", nullable=False)
    op.alter_column("stock_movements", "source_key", nullable=False)

    # ---------------------------------------------------------
    # 3. CONSTRAINTS AND THE LEDGER INDEX
    # ---------------------------------------------------------
    for name, condition in CHECKS.items():
        op.create_check_constraint(name, "stock_movements", condition)
    op.create_unique_constraint(
        "uq_stock_movement_source_key", "stock_movements", ["campus_id", "source_key"]
    )
    op.create_unique_constraint(
        "uq_stock_movement_reversal_of", "stock_movements", ["reversal_of_id"]
    )
    op.create_foreign_key(
        "stock_movements_reversal_of_id_fkey",
        "stock_movements", "stock_movements", ["reversal_of_id"], ["id"],
    )
    op.create_index(
        "ix_stock_movements_ledger_order",
        "stock_movements",
        ["campus_id", "item_id", "effective_at", "id"],
    )

    # ---------------------------------------------------------
    # 4. OPENING STOCK (decision S3)
    # ---------------------------------------------------------
    op.create_table(
        "stock_openings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campus_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=18, scale=3), nullable=False),
        sa.Column("unit_id", sa.Integer(), nullable=False),
        sa.Column("conversion_factor", sa.Numeric(precision=24, scale=12), nullable=False),
        sa.Column("standard_quantity", sa.Numeric(precision=18, scale=3), nullable=False),
        sa.Column("standard_unit_id", sa.Integer(), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("remarks", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reversed_by", sa.Integer(), nullable=True),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reversal_reason", sa.String(length=500), nullable=True),
        sa.CheckConstraint("quantity > 0", name="ck_stock_opening_quantity"),
        sa.CheckConstraint("standard_quantity > 0", name="ck_stock_opening_standard_quantity"),
        sa.CheckConstraint("conversion_factor > 0", name="ck_stock_opening_conversion_factor"),
        sa.CheckConstraint("status IN ('ACTIVE', 'REVERSED')", name="ck_stock_opening_status"),
        sa.CheckConstraint(
            "(status = 'REVERSED') = (reversed_at IS NOT NULL) "
            "AND (reversed_at IS NULL) = (reversed_by IS NULL) "
            "AND (reversed_at IS NULL) = (reversal_reason IS NULL)",
            name="ck_stock_opening_reversal_complete",
        ),
        sa.ForeignKeyConstraint(["campus_id"], ["campuses.id"]),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"]),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"]),
        sa.ForeignKeyConstraint(["standard_unit_id"], ["units.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["reversed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_stock_openings_campus_id"), "stock_openings", ["campus_id"])
    op.create_index(op.f("ix_stock_openings_item_id"), "stock_openings", ["item_id"])
    op.create_index(
        "uq_stock_opening_active_item",
        "stock_openings",
        ["campus_id", "item_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
        sqlite_where=sa.text("status = 'ACTIVE'"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    openings = bind.execute(sa.text("SELECT count(*) FROM stock_openings")).scalar_one()
    others = bind.execute(sa.text(
        "SELECT count(*) FROM stock_movements WHERE movement_type <> 'RECEIPT'"
    )).scalar_one()
    if openings or others:
        raise RuntimeError(
            f"Stage 4 stock data exists ({openings} opening entries, {others} "
            "non-receipt movements); downgrading would lose its meaning. "
            "Restore the pre-migration backup instead."
        )

    op.drop_index("uq_stock_opening_active_item", table_name="stock_openings")
    op.drop_index(op.f("ix_stock_openings_item_id"), table_name="stock_openings")
    op.drop_index(op.f("ix_stock_openings_campus_id"), table_name="stock_openings")
    op.drop_table("stock_openings")

    op.drop_index("ix_stock_movements_ledger_order", table_name="stock_movements")
    op.drop_constraint(
        "stock_movements_reversal_of_id_fkey", "stock_movements", type_="foreignkey"
    )
    op.drop_constraint("uq_stock_movement_reversal_of", "stock_movements", type_="unique")
    op.drop_constraint("uq_stock_movement_source_key", "stock_movements", type_="unique")
    for name in reversed(list(CHECKS)):
        op.drop_constraint(name, "stock_movements", type_="check")
    op.drop_column("stock_movements", "reversal_of_id")
    op.drop_column("stock_movements", "source_key")
    op.drop_column("stock_movements", "effective_at")
    op.drop_column("stock_movements", "direction")
