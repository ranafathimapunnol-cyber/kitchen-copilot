"""add three role authorization

Revision ID: c91f7a2b4e60
Revises: 8a2c4d91e6b7
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c91f7a2b4e60"
down_revision: Union[str, Sequence[str], None] = "8a2c4d91e6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


MODULES = [
    ("Dashboard", "dashboard"),
    ("Headcount", "headcount"),
    ("Inventory", "inventory"),
    ("Purchase Order", "purchase_order"),
    ("Consumption", "consumption"),
    ("Outsourced Food", "outsourced_food"),
    ("Menu", "menu"),
    ("Audit", "audit"),
]

PERMISSIONS = {
    "dashboard": ["READ"],
    "headcount": ["CREATE", "READ", "UPDATE"],
    "inventory": ["CREATE", "READ", "UPDATE"],
    "purchase_order": ["CREATE", "READ", "UPDATE"],
    "consumption": ["CREATE", "READ", "UPDATE"],
    "outsourced_food": ["CREATE", "READ", "UPDATE"],
    "menu": ["CREATE", "READ", "UPDATE"],
    "audit": ["READ"],
}


def upgrade() -> None:
    # ---------------------------------------------------------
    # 1. Convert the existing PostgreSQL user role enum.
    #    Existing user IDs and all other user fields are kept.
    # ---------------------------------------------------------

    op.execute(
        """
        CREATE TYPE userrole_new AS ENUM (
            'ADMIN',
            'KITCHEN_MANAGER',
            'STAFF'
        )
        """
    )

    op.execute(
        """
        ALTER TABLE users
        ALTER COLUMN role TYPE userrole_new
        USING (
            CASE role::text
                WHEN 'ADMIN' THEN 'ADMIN'
                WHEN 'KITCHEN_MANAGER' THEN 'KITCHEN_MANAGER'
                WHEN 'STORE_KEEPER' THEN 'STAFF'
                WHEN 'ACCOUNTS' THEN 'STAFF'
                ELSE role::text
            END
        )::userrole_new
        """
    )

    op.execute("DROP TYPE userrole")
    op.execute("ALTER TYPE userrole_new RENAME TO userrole")

    # ---------------------------------------------------------
    # 2. Create modules.
    # ---------------------------------------------------------

    op.create_table(
        "modules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
    )

    op.create_index(
        "ix_modules_code",
        "modules",
        ["code"],
        unique=True,
    )

    # ---------------------------------------------------------
    # 3. Create permissions.
    # ---------------------------------------------------------

    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("module_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=10), nullable=False),
        sa.Column(
            "permission_code",
            sa.String(length=150),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["module_id"],
            ["modules.id"],
        ),
        sa.UniqueConstraint(
            "module_id",
            "action",
            name="uq_permission_module_action",
        ),
        sa.CheckConstraint(
            "action IN ('CREATE', 'READ', 'UPDATE')",
            name="ck_permission_allowed_actions",
        ),
    )

    op.create_index(
        "ix_permissions_module_id",
        "permissions",
        ["module_id"],
        unique=False,
    )

    op.create_index(
        "ix_permissions_permission_code",
        "permissions",
        ["permission_code"],
        unique=True,
    )

    # ---------------------------------------------------------
    # 4. Create Staff permission assignments.
    #    Staff receives no assignments automatically.
    # ---------------------------------------------------------

    op.create_table(
        "staff_access_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("staff_user_id", sa.Integer(), nullable=False),
        sa.Column("permission_id", sa.Integer(), nullable=False),
        sa.Column("assigned_by", sa.Integer(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["staff_user_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["assigned_by"],
            ["users.id"],
        ),
        sa.UniqueConstraint(
            "staff_user_id",
            "permission_id",
            name="uq_staff_permission_assignment",
        ),
    )

    op.create_index(
        "ix_staff_access_assignments_staff_user_id",
        "staff_access_assignments",
        ["staff_user_id"],
        unique=False,
    )

    op.create_index(
        "ix_staff_access_assignments_permission_id",
        "staff_access_assignments",
        ["permission_id"],
        unique=False,
    )

    # ---------------------------------------------------------
    # 5. Seed modules and approved permissions.
    # Explicit IDs make this migration compatible with offline SQL mode.

    modules_table = sa.table(
        "modules",
        sa.column("id", sa.Integer()),
        sa.column("name", sa.String()),
        sa.column("code", sa.String()),
    )

    module_rows = [
        {"id": 1, "name": "Dashboard", "code": "dashboard"},
        {"id": 2, "name": "Headcount", "code": "headcount"},
        {"id": 3, "name": "Inventory", "code": "inventory"},
        {"id": 4, "name": "Purchase Order", "code": "purchase_order"},
        {"id": 5, "name": "Consumption", "code": "consumption"},
        {"id": 6, "name": "Outsourced Food", "code": "outsourced_food"},
        {"id": 7, "name": "Menu", "code": "menu"},
        {"id": 8, "name": "Audit", "code": "audit"},
    ]

    op.bulk_insert(modules_table, module_rows)

    # Synchronize the PostgreSQL sequence after explicit IDs.
    op.execute(
        """
        SELECT setval(
            pg_get_serial_sequence('modules', 'id'),
            (SELECT MAX(id) FROM modules)
        )
        """
    )

    permissions_table = sa.table(
        "permissions",
        sa.column("module_id", sa.Integer()),
        sa.column("action", sa.String()),
        sa.column("permission_code", sa.String()),
    )

    permission_rows = []

    for module_id, module_code in [
        (1, "dashboard"),
        (2, "headcount"),
        (3, "inventory"),
        (4, "purchase_order"),
        (5, "consumption"),
        (6, "outsourced_food"),
        (7, "menu"),
        (8, "audit"),
    ]:
        actions = PERMISSIONS[module_code]

        for action in actions:
            permission_rows.append(
                {
                    "module_id": module_id,
                    "action": action,
                    "permission_code": (
                        f"{module_code}.{action.lower()}"
                    ),
                }
            )

    op.bulk_insert(permissions_table, permission_rows)


def downgrade() -> None:
    # WARNING:
    # The original distinction between STORE_KEEPER and ACCOUNTS
    # cannot be recovered after both roles become STAFF.
    # This downgrade maps every STAFF account to STORE_KEEPER.

    op.drop_index(
        "ix_staff_access_assignments_permission_id",
        table_name="staff_access_assignments",
    )
    op.drop_index(
        "ix_staff_access_assignments_staff_user_id",
        table_name="staff_access_assignments",
    )
    op.drop_table("staff_access_assignments")

    op.drop_index(
        "ix_permissions_permission_code",
        table_name="permissions",
    )
    op.drop_index(
        "ix_permissions_module_id",
        table_name="permissions",
    )
    op.drop_table("permissions")

    op.drop_index(
        "ix_modules_code",
        table_name="modules",
    )
    op.drop_table("modules")

    op.execute(
        """
        CREATE TYPE userrole_old AS ENUM (
            'ADMIN',
            'KITCHEN_MANAGER',
            'STORE_KEEPER',
            'ACCOUNTS'
        )
        """
    )

    op.execute(
        """
        ALTER TABLE users
        ALTER COLUMN role TYPE userrole_old
        USING (
            CASE role::text
                WHEN 'STAFF' THEN 'STORE_KEEPER'
                ELSE role::text
            END
        )::userrole_old
        """
    )

    op.execute("DROP TYPE userrole")
    op.execute("ALTER TYPE userrole_old RENAME TO userrole")
