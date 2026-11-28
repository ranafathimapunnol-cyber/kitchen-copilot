"""one active Admin per campus, staff tasks, new permission codes (M3)

Revision ID: a7d3e9b1c4f2
Revises: e2b7c4d9a5f1

Owner-approved 27 Nov 2026. Additive, no existing row changed and no STAFF
grant added or removed:

1. Partial unique index: at most one active ADMIN per campus. The upgrade
   stops first, changing nothing, if any campus has more than one.
2. New modules and permission codes: goods_receipt.create/read/update,
   report.read, task.read, task.update, copilot.read ("use Kitchen Copilot").
3. Table staff_tasks.

Needs KC_AUTHORIZE_MIGRATION=a7d3e9b1c4f2 (the API container runs
"alembic upgrade head" at start).
"""

import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7d3e9b1c4f2"
down_revision: Union[str, None] = "e2b7c4d9a5f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AUTHORIZATION_ENV = "KC_AUTHORIZE_MIGRATION"
NEW_MODULES = {
    "goods_receipt": ("Goods Receipts", ["CREATE", "READ", "UPDATE"]),
    "report": ("Reports", ["READ"]),
    "task": ("Tasks", ["READ", "UPDATE"]),
    "copilot": ("Kitchen Copilot", ["READ"]),
}


def upgrade() -> None:
    if os.environ.get(AUTHORIZATION_ENV) != revision:
        raise RuntimeError(f"Migration {revision} is not authorized for this database. After explicit approval and "
                           f"a verified backup, run it with {AUTHORIZATION_ENV}={revision}.")
    bind = op.get_bind()
    many = bind.execute(sa.text(
        "SELECT campus_id, count(*) FROM users WHERE CAST(role AS VARCHAR) = 'ADMIN' AND is_active "
        "GROUP BY campus_id HAVING count(*) > 1")).fetchall()
    if many:
        raise RuntimeError(f"Campuses with more than one active Admin: {[tuple(r) for r in many]}. Resolve them first.")
    op.create_index("uq_users_one_active_admin_per_campus", "users", ["campus_id"], unique=True,
                    postgresql_where=sa.text("role = 'ADMIN' AND is_active"))

    for code, (name, actions) in NEW_MODULES.items():
        if bind.execute(sa.text("SELECT 1 FROM modules WHERE code = :c"), {"c": code}).first():
            raise RuntimeError(f"Module {code} already exists.")
        module_id = bind.execute(sa.text("INSERT INTO modules (name, code) VALUES (:n, :c) RETURNING id"),
                                 {"n": name, "c": code}).scalar()
        for action in actions:
            bind.execute(sa.text("INSERT INTO permissions (module_id, action, permission_code) VALUES (:m, :a, :p)"),
                         {"m": module_id, "a": action, "p": f"{code}.{action.lower()}"})

    op.create_table(
        "staff_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("campus_id", sa.Integer(), sa.ForeignKey("campuses.id"), nullable=False, index=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.String(2000), nullable=True),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("priority", sa.String(10), nullable=False, server_default="NORMAL"),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column("assigned_to", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("staff_note", sa.String(1000), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("category IN ('PURCHASE','INVENTORY','STOCK_COUNT','GOODS_RECEIPT','MEAL_PREPARATION',"
                           "'CLEANING','WASTE','GENERAL')", name="ck_staff_task_category"),
        sa.CheckConstraint("priority IN ('LOW','NORMAL','HIGH')", name="ck_staff_task_priority"),
        sa.CheckConstraint("status IN ('OPEN','IN_PROGRESS','DONE','CANCELLED')", name="ck_staff_task_status"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    tasks = bind.execute(sa.text("SELECT count(*) FROM staff_tasks")).scalar()
    grants = bind.execute(sa.text(
        "SELECT count(*) FROM staff_access_assignments a JOIN permissions p ON p.id = a.permission_id "
        "JOIN modules m ON m.id = p.module_id WHERE m.code IN ('goods_receipt','report','task','copilot')")).scalar()
    if tasks or grants:
        raise RuntimeError(f"Refusing to downgrade: {tasks} task(s) and {grants} grant(s) of the new codes exist.")
    op.drop_table("staff_tasks")
    bind.execute(sa.text("DELETE FROM permissions WHERE module_id IN (SELECT id FROM modules WHERE code IN "
                         "('goods_receipt','report','task','copilot'))"))
    bind.execute(sa.text("DELETE FROM modules WHERE code IN ('goods_receipt','report','task','copilot')"))
    op.drop_index("uq_users_one_active_admin_per_campus", table_name="users")
