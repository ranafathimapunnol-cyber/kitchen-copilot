"""add kitchen issues, unused returns and the append-only stock ledger (Stage 4, migration M2b)

Revision ID: c7d2e9f4a816
Revises: b5e1d7c3a920

Approved 23 November 2026 (docs/STAGE-4-STOCK-PLAN.md section 9, decisions
4b-1 to 4b-5).

1. kitchen_issues and kitchen_issue_items: issues of stock to the kitchen
   for a meal session and menu, numbered KI-00001 per campus; status DRAFT,
   CONFIRMED, CANCELLED or REVERSED, each with exactly its own audit fields.
2. kitchen_returns and kitchen_return_items: unused stock returned against
   one issue's lines, numbered KR-00001 per campus, same statuses.
3. The stock ledger becomes append-only in the database (4b-5): triggers on
   stock_movements refuse every UPDATE and DELETE (per row) and TRUNCATE
   (per statement). Corrections are REVERSAL movements. A later migration
   that must change existing movement rows has to disable and re-enable
   these triggers explicitly, with its own approval.

Additive: no existing table, column or row is changed; no backfill; no
permission rows (the consumption.* codes already exist). The downgrade
refuses to run once kitchen issues or their movements exist.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c7d2e9f4a816"
down_revision: Union[str, Sequence[str], None] = "b5e1d7c3a920"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen copies of the trigger SQL in app/models/ledger_guard.py.
APPEND_ONLY_FUNCTION = """
CREATE OR REPLACE FUNCTION stock_movements_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION USING
        MESSAGE = 'stock_movements is append-only: ' || TG_OP
                  || ' is not allowed; post a reversal instead',
        HINT = 'Corrections are REVERSAL movements (decision 4b-5).';
END;
$$
"""
ROW_TRIGGER = """
CREATE TRIGGER stock_movements_no_update_delete
BEFORE UPDATE OR DELETE ON stock_movements
FOR EACH ROW EXECUTE FUNCTION stock_movements_append_only()
"""
TRUNCATE_TRIGGER = """
CREATE TRIGGER stock_movements_no_truncate
BEFORE TRUNCATE ON stock_movements
FOR EACH STATEMENT EXECUTE FUNCTION stock_movements_append_only()
"""


def document_checks(prefix: str) -> list:
    return [
        sa.CheckConstraint("status IN ('DRAFT', 'CONFIRMED', 'CANCELLED', 'REVERSED')", name=f"ck_{prefix}_status"),
        sa.CheckConstraint(
            "(status IN ('CONFIRMED', 'REVERSED')) = (confirmed_at IS NOT NULL) "
            "AND (confirmed_at IS NULL) = (confirmed_by IS NULL) "
            "AND (confirmed_at IS NULL) = (effective_at IS NULL)",
            name=f"ck_{prefix}_confirmation_complete",
        ),
        sa.CheckConstraint(
            "(status = 'CANCELLED') = (cancelled_at IS NOT NULL) "
            "AND (cancelled_at IS NULL) = (cancelled_by IS NULL) "
            "AND (cancelled_at IS NULL) = (cancellation_reason IS NULL)",
            name=f"ck_{prefix}_cancellation_complete",
        ),
        sa.CheckConstraint(
            "(status = 'REVERSED') = (reversed_at IS NOT NULL) "
            "AND (reversed_at IS NULL) = (reversed_by IS NULL) "
            "AND (reversed_at IS NULL) = (reversal_reason IS NULL)",
            name=f"ck_{prefix}_reversal_complete",
        ),
    ]


def document_columns() -> list:
    return [
        sa.Column("remarks", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by", sa.Integer(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by", sa.Integer(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.String(length=500), nullable=True),
        sa.Column("reversed_by", sa.Integer(), nullable=True),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reversal_reason", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["confirmed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["cancelled_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["reversed_by"], ["users.id"]),
    ]


def line_columns(prefix: str) -> list:
    return [
        sa.Column("quantity", sa.Numeric(precision=18, scale=3), nullable=False),
        sa.Column("unit_id", sa.Integer(), nullable=False),
        sa.Column("conversion_factor", sa.Numeric(precision=24, scale=12), nullable=False),
        sa.Column("standard_quantity", sa.Numeric(precision=18, scale=3), nullable=False),
        sa.Column("standard_unit_id", sa.Integer(), nullable=False),
        sa.Column("remarks", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"]),
        sa.ForeignKeyConstraint(["standard_unit_id"], ["units.id"]),
        sa.CheckConstraint("quantity > 0", name=f"ck_{prefix}_quantity"),
        sa.CheckConstraint("standard_quantity > 0", name=f"ck_{prefix}_standard_quantity"),
        sa.CheckConstraint("conversion_factor > 0", name=f"ck_{prefix}_conversion_factor"),
    ]


def upgrade() -> None:
    # ---------- kitchen issues ----------
    op.create_table(
        "kitchen_issues",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campus_id", sa.Integer(), nullable=False),
        sa.Column("issue_seq", sa.Integer(), nullable=False),
        sa.Column("issue_number", sa.String(length=20), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("meal_session_id", sa.Integer(), nullable=False),
        sa.Column("menu_id", sa.Integer(), nullable=False),
        *document_columns(),
        sa.ForeignKeyConstraint(["campus_id"], ["campuses.id"]),
        sa.ForeignKeyConstraint(["meal_session_id"], ["meal_sessions.id"]),
        sa.ForeignKeyConstraint(["menu_id"], ["menus.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campus_id", "issue_seq", name="uq_kitchen_issue_seq"),
        sa.UniqueConstraint("campus_id", "issue_number", name="uq_kitchen_issue_number"),
        *document_checks("kitchen_issue"),
    )
    op.create_index(op.f("ix_kitchen_issues_campus_id"), "kitchen_issues", ["campus_id"])
    op.create_index("ix_kitchen_issues_campus_date", "kitchen_issues", ["campus_id", "issue_date"])

    op.create_table(
        "kitchen_issue_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campus_id", sa.Integer(), nullable=False),
        sa.Column("issue_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        *line_columns("kitchen_issue_item"),
        sa.ForeignKeyConstraint(["campus_id"], ["campuses.id"]),
        sa.ForeignKeyConstraint(["issue_id"], ["kitchen_issues.id"]),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("issue_id", "item_id", name="uq_kitchen_issue_item"),
    )
    op.create_index(op.f("ix_kitchen_issue_items_campus_id"), "kitchen_issue_items", ["campus_id"])
    op.create_index(op.f("ix_kitchen_issue_items_issue_id"), "kitchen_issue_items", ["issue_id"])

    # ---------- unused returns ----------
    op.create_table(
        "kitchen_returns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campus_id", sa.Integer(), nullable=False),
        sa.Column("return_seq", sa.Integer(), nullable=False),
        sa.Column("return_number", sa.String(length=20), nullable=False),
        sa.Column("issue_id", sa.Integer(), nullable=False),
        sa.Column("return_date", sa.Date(), nullable=False),
        *document_columns(),
        sa.ForeignKeyConstraint(["campus_id"], ["campuses.id"]),
        sa.ForeignKeyConstraint(["issue_id"], ["kitchen_issues.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campus_id", "return_seq", name="uq_kitchen_return_seq"),
        sa.UniqueConstraint("campus_id", "return_number", name="uq_kitchen_return_number"),
        *document_checks("kitchen_return"),
    )
    op.create_index(op.f("ix_kitchen_returns_campus_id"), "kitchen_returns", ["campus_id"])
    op.create_index(op.f("ix_kitchen_returns_issue_id"), "kitchen_returns", ["issue_id"])

    op.create_table(
        "kitchen_return_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campus_id", sa.Integer(), nullable=False),
        sa.Column("return_id", sa.Integer(), nullable=False),
        sa.Column("issue_item_id", sa.Integer(), nullable=False),
        *line_columns("kitchen_return_item"),
        sa.ForeignKeyConstraint(["campus_id"], ["campuses.id"]),
        sa.ForeignKeyConstraint(["return_id"], ["kitchen_returns.id"]),
        sa.ForeignKeyConstraint(["issue_item_id"], ["kitchen_issue_items.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("return_id", "issue_item_id", name="uq_kitchen_return_item"),
    )
    op.create_index(op.f("ix_kitchen_return_items_campus_id"), "kitchen_return_items", ["campus_id"])
    op.create_index(op.f("ix_kitchen_return_items_return_id"), "kitchen_return_items", ["return_id"])

    # ---------- append-only stock ledger (4b-5) ----------
    op.execute(APPEND_ONLY_FUNCTION)
    op.execute(ROW_TRIGGER)
    op.execute(TRUNCATE_TRIGGER)


def downgrade() -> None:
    bind = op.get_bind()
    issues = bind.execute(sa.text("SELECT count(*) FROM kitchen_issues")).scalar_one()
    kitchen_movements = bind.execute(sa.text(
        "SELECT count(*) FROM stock_movements WHERE reference_type IN ('KITCHEN_ISSUE', 'KITCHEN_RETURN')"
    )).scalar_one()
    if issues or kitchen_movements:
        raise RuntimeError(
            f"Kitchen issue data exists ({issues} issues, {kitchen_movements} movements); "
            "downgrading would lose it. Restore the pre-migration backup instead."
        )

    op.execute("DROP TRIGGER IF EXISTS stock_movements_no_truncate ON stock_movements")
    op.execute("DROP TRIGGER IF EXISTS stock_movements_no_update_delete ON stock_movements")
    op.execute("DROP FUNCTION IF EXISTS stock_movements_append_only()")

    op.drop_index(op.f("ix_kitchen_return_items_return_id"), table_name="kitchen_return_items")
    op.drop_index(op.f("ix_kitchen_return_items_campus_id"), table_name="kitchen_return_items")
    op.drop_table("kitchen_return_items")
    op.drop_index(op.f("ix_kitchen_returns_issue_id"), table_name="kitchen_returns")
    op.drop_index(op.f("ix_kitchen_returns_campus_id"), table_name="kitchen_returns")
    op.drop_table("kitchen_returns")
    op.drop_index(op.f("ix_kitchen_issue_items_issue_id"), table_name="kitchen_issue_items")
    op.drop_index(op.f("ix_kitchen_issue_items_campus_id"), table_name="kitchen_issue_items")
    op.drop_table("kitchen_issue_items")
    op.drop_index("ix_kitchen_issues_campus_date", table_name="kitchen_issues")
    op.drop_index(op.f("ix_kitchen_issues_campus_id"), table_name="kitchen_issues")
    op.drop_table("kitchen_issues")
