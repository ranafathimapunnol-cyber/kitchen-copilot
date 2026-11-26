"""add purchase orders and separate supplier-bill permissions (Stage 3)

Revision ID: a3c9e1f47b20
Revises: e7b3c5a19d42

Approved 18 November 2026.

1. Permission namespaces split. Until now purchase_order.* guarded supplier
   bills. From here purchase_order.* means genuine purchase orders and the
   new purchase_bill.* (module "Supplier Bills") guards bills, payments,
   balances, the purchases-versus-payments report and bill attachments.
2. Existing STAFF grants are preserved (decision: copy and keep originals).
   Every purchase_order.X assignment gets a matching purchase_bill.X
   assignment with the same staff user, assigning admin, active flag and
   date, so bill access is unchanged. The original row is not modified and
   stays as history, but it grants a STAFF user nothing: purchase orders
   are ADMIN and KITCHEN_MANAGER work, and the API refuses every
   purchase_order.* permission to STAFF whatever assignments exist
   (STAFF_EXCLUDED_PERMISSIONS in app/api/dependencies.py, decision of
   20 November 2026).
   Each copy is written to the audit log (action MIGRATE, no acting user).
3. purchase_orders and purchase_order_items: what was ordered, in what unit.
   No prices. Status DRAFT, PLACED, CLOSED or CANCELLED; no approval step.
4. Nullable links from bills and bill lines to the order they bill for.
   Existing bills, bill lines and receipts are not changed.

Additive: no existing row or column is changed or removed.
"""

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a3c9e1f47b20"
down_revision: Union[str, Sequence[str], None] = "e7b3c5a19d42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ACTIONS = ("CREATE", "READ", "UPDATE")


def upgrade() -> None:
    bind = op.get_bind()

    # ---------------------------------------------------------
    # 1. SUPPLIER BILLS MODULE AND ITS THREE PERMISSIONS
    # ---------------------------------------------------------

    module_id = bind.execute(
        sa.text(
            "INSERT INTO modules (name, code) VALUES (:name, :code) RETURNING id"
        ),
        {"name": "Supplier Bills", "code": "purchase_bill"},
    ).scalar_one()

    bill_permission_ids = {}
    for action in ACTIONS:
        code = f"purchase_bill.{action.lower()}"
        bill_permission_ids[code] = bind.execute(
            sa.text(
                """
                INSERT INTO permissions (module_id, action, permission_code)
                VALUES (:module_id, :action, :code)
                RETURNING id
                """
            ),
            {"module_id": module_id, "action": action, "code": code},
        ).scalar_one()

    # ---------------------------------------------------------
    # 2. COPY EXISTING purchase_order.* GRANTS TO purchase_bill.*
    # ---------------------------------------------------------

    grants = bind.execute(
        sa.text(
            """
            SELECT a.id, a.staff_user_id, a.assigned_by, a.is_active,
                   a.assigned_at, p.permission_code, u.campus_id
              FROM staff_access_assignments a
              JOIN permissions p ON p.id = a.permission_id
              JOIN users u ON u.id = a.staff_user_id
             WHERE p.permission_code IN (
                   'purchase_order.create',
                   'purchase_order.read',
                   'purchase_order.update')
             ORDER BY a.id
            """
        )
    ).all()

    for grant in grants:
        bill_code = grant.permission_code.replace("purchase_order.", "purchase_bill.")
        copy_id = bind.execute(
            sa.text(
                """
                INSERT INTO staff_access_assignments (
                    staff_user_id, permission_id, assigned_by, is_active,
                    assigned_at, updated_at)
                VALUES (:staff, :permission, :assigned_by, :active,
                        :assigned_at, now())
                RETURNING id
                """
            ),
            {
                "staff": grant.staff_user_id,
                "permission": bill_permission_ids[bill_code],
                "assigned_by": grant.assigned_by,
                "active": grant.is_active,
                "assigned_at": grant.assigned_at,
            },
        ).scalar_one()

        if grant.campus_id is not None:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO audit_logs (
                        campus_id, user_id, action, entity_type, entity_id,
                        details, created_at)
                    VALUES (:campus, NULL, 'MIGRATE', 'STAFF_ACCESS', :staff,
                            CAST(:details AS JSON), now())
                    """
                ),
                {
                    "campus": grant.campus_id,
                    "staff": grant.staff_user_id,
                    "details": json.dumps({
                        "migration": revision,
                        "reason": "purchase_order.* split into purchase orders "
                                  "and purchase_bill.* (supplier bills)",
                        "staff_user_id": grant.staff_user_id,
                        "copied_from_assignment_id": grant.id,
                        "copied_from": grant.permission_code,
                        "new_assignment_id": copy_id,
                        "new_permission": bill_code,
                        "is_active": grant.is_active,
                        "original_kept": True,
                    }),
                },
            )

    # ---------------------------------------------------------
    # 3. PURCHASE ORDERS
    # ---------------------------------------------------------

    op.create_table(
        "purchase_orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_seq", sa.Integer(), nullable=False),
        sa.Column("order_number", sa.String(length=30), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("order_date", sa.Date(), nullable=False),
        sa.Column("expected_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("remarks", sa.String(length=1000), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("placed_by", sa.Integer(), nullable=True),
        sa.Column("placed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", sa.Integer(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("close_reason", sa.String(length=500), nullable=True),
        sa.Column("cancelled_by", sa.Integer(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.String(length=500), nullable=True),
        sa.Column("campus_id", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'PLACED', 'CLOSED', 'CANCELLED')",
            name="ck_purchase_order_status",
        ),
        sa.CheckConstraint(
            "expected_date IS NULL OR expected_date >= order_date",
            name="ck_purchase_order_dates",
        ),
        sa.CheckConstraint(
            "(placed_at IS NULL) = (placed_by IS NULL)", name="ck_purchase_order_placed"
        ),
        sa.CheckConstraint(
            "(closed_at IS NULL) = (closed_by IS NULL)", name="ck_purchase_order_closed"
        ),
        sa.CheckConstraint(
            "(cancelled_at IS NULL) = (cancelled_by IS NULL)",
            name="ck_purchase_order_cancelled",
        ),
        sa.ForeignKeyConstraint(["campus_id"], ["campuses.id"]),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["placed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["closed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["cancelled_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campus_id", "order_seq", name="uq_purchase_order_seq"),
        sa.UniqueConstraint("campus_id", "order_number", name="uq_purchase_order_number"),
    )
    op.create_index(op.f("ix_purchase_orders_campus_id"), "purchase_orders", ["campus_id"])
    op.create_index(op.f("ix_purchase_orders_supplier_id"), "purchase_orders", ["supplier_id"])

    op.create_table(
        "purchase_order_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("purchase_order_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=18, scale=3), nullable=False),
        sa.Column("unit_id", sa.Integer(), nullable=False),
        sa.Column("remarks", sa.String(length=500), nullable=True),
        sa.Column("campus_id", sa.Integer(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_purchase_order_item_quantity"),
        sa.ForeignKeyConstraint(["campus_id"], ["campuses.id"]),
        sa.ForeignKeyConstraint(["purchase_order_id"], ["purchase_orders.id"]),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"]),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("purchase_order_id", "item_id", name="uq_purchase_order_item"),
    )
    op.create_index(
        op.f("ix_purchase_order_items_campus_id"), "purchase_order_items", ["campus_id"]
    )
    op.create_index(
        op.f("ix_purchase_order_items_purchase_order_id"),
        "purchase_order_items",
        ["purchase_order_id"],
    )

    # ---------------------------------------------------------
    # 4. LINKS FROM BILLS AND BILL LINES (nullable; existing rows untouched)
    # ---------------------------------------------------------

    op.add_column("purchases", sa.Column("purchase_order_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_purchases_purchase_order_id",
        "purchases", "purchase_orders", ["purchase_order_id"], ["id"],
    )
    op.create_index(
        op.f("ix_purchases_purchase_order_id"), "purchases", ["purchase_order_id"]
    )

    op.add_column(
        "purchase_items", sa.Column("purchase_order_item_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_purchase_items_purchase_order_item_id",
        "purchase_items", "purchase_order_items", ["purchase_order_item_id"], ["id"],
    )
    op.create_index(
        op.f("ix_purchase_items_purchase_order_item_id"),
        "purchase_items",
        ["purchase_order_item_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_purchase_items_purchase_order_item_id"), table_name="purchase_items")
    op.drop_constraint(
        "fk_purchase_items_purchase_order_item_id", "purchase_items", type_="foreignkey"
    )
    op.drop_column("purchase_items", "purchase_order_item_id")

    op.drop_index(op.f("ix_purchases_purchase_order_id"), table_name="purchases")
    op.drop_constraint("fk_purchases_purchase_order_id", "purchases", type_="foreignkey")
    op.drop_column("purchases", "purchase_order_id")

    op.drop_index(
        op.f("ix_purchase_order_items_purchase_order_id"), table_name="purchase_order_items"
    )
    op.drop_index(op.f("ix_purchase_order_items_campus_id"), table_name="purchase_order_items")
    op.drop_table("purchase_order_items")
    op.drop_index(op.f("ix_purchase_orders_supplier_id"), table_name="purchase_orders")
    op.drop_index(op.f("ix_purchase_orders_campus_id"), table_name="purchase_orders")
    op.drop_table("purchase_orders")

    # The purchase_bill.* grants (copies and any made since) cannot exist
    # without their permissions. The original purchase_order.* grants were
    # never changed, so bill access returns to them. Audit rows are kept.
    op.execute(
        """
        DELETE FROM staff_access_assignments
         WHERE permission_id IN (
               SELECT id FROM permissions
                WHERE permission_code IN (
                      'purchase_bill.create', 'purchase_bill.read', 'purchase_bill.update'))
        """
    )
    op.execute(
        """
        DELETE FROM permissions
         WHERE permission_code IN (
               'purchase_bill.create', 'purchase_bill.read', 'purchase_bill.update')
        """
    )
    op.execute("DELETE FROM modules WHERE code = 'purchase_bill'")
