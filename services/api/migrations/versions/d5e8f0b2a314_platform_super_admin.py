"""organisations, SUPER_ADMIN, platform audit and integrations (Stage 11, M1)

Revision ID: d5e8f0b2a314
Revises: c4d7e9a1f203

NOT AUTHORIZED for the development database (or any database with real
records) until the owner explicitly approves it. Review:
docs/PHASE-2-PLATFORM.md ("Migration review").

Additive only. No existing row is changed and no permission row or STAFF
grant is touched:

1. userrole gains SUPER_ADMIN (outside the transaction, as PostgreSQL
   requires). users.campus_id becomes nullable with the check
   ck_user_campus_by_role (only SUPER_ADMIN has no campus); every existing
   user has a campus and is not SUPER_ADMIN, so all rows satisfy it.
   users.organization_id (nullable FK).
2. organizations; campuses.organization_id and campus contact details,
   created/updated/deactivated timestamps (all nullable); case-insensitive
   unique indexes on campus and organisation name and code (the upgrade
   stops with a clear message if existing campuses differ only in case).
3. platform_audit_logs with append-only triggers (UPDATE, DELETE, TRUNCATE).
4. campus_integrations, erp_sync_runs, erp_headcount_imports (Phase 3
   preparation; no rows are created).

Downgrade removes only what this migration added and refuses while any
SUPER_ADMIN user, organisation, platform audit row, integration setting or
ERP sync record exists. The enum value SUPER_ADMIN stays (PostgreSQL cannot
drop an enum value); it is harmless when unused.
"""

import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.models.platform import PG_FUNCTION, PG_ROW_TRIGGER, PG_TRUNCATE_TRIGGER


revision: str = "d5e8f0b2a314"
down_revision: Union[str, None] = "c4d7e9a1f203"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# The API container runs "alembic upgrade head" when it starts. This guard
# makes that refuse M1 (before changing anything) unless the operator has
# explicitly authorized it for the database being upgraded.
AUTHORIZATION_ENV = "KC_AUTHORIZE_M1"


def upgrade() -> None:
    if os.environ.get(AUTHORIZATION_ENV) != revision:
        raise RuntimeError(
            f"Migration {revision} (organisations, SUPER_ADMIN) is not authorized for this database. "
            f"After explicit approval and a verified backup, run it with {AUTHORIZATION_ENV}={revision}.")
    bind = op.get_bind()
    clash = bind.execute(sa.text(
        "SELECT lower(name) FROM campuses GROUP BY lower(name) HAVING count(*) > 1 "
        "UNION SELECT lower(code) FROM campuses GROUP BY lower(code) HAVING count(*) > 1")).fetchall()
    if clash:
        raise RuntimeError(f"Campuses differ only in letter case: {[r[0] for r in clash]}. Rename them first.")

    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'SUPER_ADMIN'")

    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(150), nullable=False, unique=True),
        sa.Column("code", sa.String(30), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("uq_organizations_name_ci", "organizations", [sa.text("lower(name)")], unique=True)
    op.create_index("uq_organizations_code_ci", "organizations", [sa.text("lower(code)")], unique=True)

    op.add_column("campuses", sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=True))
    for name, kind in (("address", sa.String(500)), ("contact_name", sa.String(150)), ("contact_email", sa.String(255)),
                       ("contact_phone", sa.String(40)), ("deactivation_reason", sa.String(500))):
        op.add_column("campuses", sa.Column(name, kind, nullable=True))
    for name in ("created_at", "updated_at", "deactivated_at"):
        op.add_column("campuses", sa.Column(name, sa.DateTime(timezone=True), nullable=True))
    op.create_index("uq_campuses_name_ci", "campuses", [sa.text("lower(name)")], unique=True)
    op.create_index("uq_campuses_code_ci", "campuses", [sa.text("lower(code)")], unique=True)

    op.add_column("users", sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=True))
    op.alter_column("users", "campus_id", existing_type=sa.Integer(), nullable=True)
    op.create_check_constraint("ck_user_campus_by_role", "users",
                               "(CAST(role AS VARCHAR) = 'SUPER_ADMIN') = (campus_id IS NULL)")

    op.create_table(
        "platform_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("actor_email", sa.String(255), nullable=True),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("target_type", sa.String(60), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("campus_id", sa.Integer(), sa.ForeignKey("campuses.id"), nullable=True),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
    )
    for column in ("occurred_at", "actor_user_id", "action", "campus_id"):
        op.create_index(f"ix_platform_audit_logs_{column}", "platform_audit_logs", [column])
    for statement in (PG_FUNCTION, PG_ROW_TRIGGER, PG_TRUNCATE_TRIGGER):
        op.execute(statement)

    op.create_table(
        "campus_integrations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("campus_id", sa.Integer(), sa.ForeignKey("campuses.id"), nullable=False, index=True),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("base_url", sa.String(500), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_status", sa.String(30), nullable=True),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.UniqueConstraint("campus_id", "kind", name="uq_campus_integration_kind"),
    )
    op.create_table(
        "erp_sync_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("campus_id", sa.Integer(), sa.ForeignKey("campuses.id"), nullable=False, index=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("records_received", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_applied", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("triggered_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_table(
        "erp_headcount_imports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("campus_id", sa.Integer(), sa.ForeignKey("campuses.id"), nullable=False),
        sa.Column("external_key", sa.String(200), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("sync_run_id", sa.Integer(), sa.ForeignKey("erp_sync_runs.id"), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("campus_id", "external_key", name="uq_erp_headcount_import_key"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    checks = {
        "SUPER_ADMIN users": "SELECT count(*) FROM users WHERE CAST(role AS VARCHAR) = 'SUPER_ADMIN'",
        "organisations": "SELECT count(*) FROM organizations",
        "platform audit rows": "SELECT count(*) FROM platform_audit_logs",
        "integration settings": "SELECT count(*) FROM campus_integrations",
        "ERP sync runs": "SELECT count(*) FROM erp_sync_runs",
        "ERP imports": "SELECT count(*) FROM erp_headcount_imports",
    }
    found = {label: bind.execute(sa.text(sql)).scalar() for label, sql in checks.items()}
    blocking = {label: n for label, n in found.items() if n}
    if blocking:
        raise RuntimeError(f"Refusing to downgrade M1 while platform data exists: {blocking}")

    op.drop_table("erp_headcount_imports")
    op.drop_table("erp_sync_runs")
    op.drop_table("campus_integrations")
    op.drop_table("platform_audit_logs")
    op.execute("DROP FUNCTION IF EXISTS platform_audit_logs_append_only()")

    op.drop_constraint("ck_user_campus_by_role", "users", type_="check")
    op.alter_column("users", "campus_id", existing_type=sa.Integer(), nullable=False)
    op.drop_column("users", "organization_id")

    op.drop_index("uq_campuses_code_ci", table_name="campuses")
    op.drop_index("uq_campuses_name_ci", table_name="campuses")
    for name in ("deactivated_at", "updated_at", "created_at", "deactivation_reason", "contact_phone",
                 "contact_email", "contact_name", "address", "organization_id"):
        op.drop_column("campuses", name)
    op.drop_table("organizations")
