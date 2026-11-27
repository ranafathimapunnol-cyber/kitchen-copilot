"""Platform (organisation-level) records — Stage 11, migration M1.

- ``platform_audit_logs``: append-only record of platform sign-ins and every
  sensitive organisation-level action (who, what, when, target, outcome).
  Like the stock ledger it has two independent guards: database triggers
  refuse UPDATE, DELETE and TRUNCATE, and an ORM guard refuses changing or
  deleting a row from application code.
- ``campus_integrations``: per-campus integration settings (the campus ERP
  headcount feed). Never holds a secret: credentials come from the
  environment (settings.ERP_HEADCOUNT_API_TOKEN) and only "set / not set" is
  ever reported.
- ``erp_sync_runs``: one row per synchronisation attempt (status, counts,
  sanitised error).
- ``erp_headcount_imports``: one row per ERP record applied, unique per
  campus and ERP key, so a repeated or overlapping sync never applies the
  same record twice (idempotency).
"""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON, Boolean, DDL, DateTime, ForeignKey, Integer, String, UniqueConstraint, event,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PlatformAuditLog(Base):
    __tablename__ = "platform_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False, index=True)
    # The signed-in platform user; NULL for a failed sign-in by an unknown email.
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(60), nullable=False)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # The campus the action concerns, if any (platform audit is not campus audit).
    campus_id: Mapped[int | None] = mapped_column(ForeignKey("campuses.id"), nullable=True, index=True)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)  # SUCCESS | FAILURE | DENIED
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class CampusIntegration(Base):
    __tablename__ = "campus_integrations"
    __table_args__ = (UniqueConstraint("campus_id", "kind", name="uq_campus_integration_kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    campus_id: Mapped[int] = mapped_column(ForeignKey("campuses.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)  # ERP_HEADCOUNT
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class ErpSyncRun(Base):
    __tablename__ = "erp_sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    campus_id: Mapped[int] = mapped_column(ForeignKey("campuses.id"), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)  # RUNNING | SUCCEEDED | FAILED | NOT_CONFIGURED
    records_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_applied: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    triggered_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class ErpHeadcountImport(Base):
    __tablename__ = "erp_headcount_imports"
    __table_args__ = (UniqueConstraint("campus_id", "external_key", name="uq_erp_headcount_import_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    campus_id: Mapped[int] = mapped_column(ForeignKey("campuses.id"), nullable=False)
    external_key: Mapped[str] = mapped_column(String(200), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    sync_run_id: Mapped[int | None] = mapped_column(ForeignKey("erp_sync_runs.id"), nullable=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


# ---------- platform audit is append-only ----------

APPEND_ONLY_MESSAGE = "The platform audit log is append-only: rows are never changed or deleted."

PG_FUNCTION = """
CREATE OR REPLACE FUNCTION platform_audit_logs_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION USING
        MESSAGE = 'platform_audit_logs is append-only: ' || TG_OP || ' is not allowed';
END;
$$
"""
PG_ROW_TRIGGER = """
CREATE TRIGGER platform_audit_logs_no_update_delete
BEFORE UPDATE OR DELETE ON platform_audit_logs
FOR EACH ROW EXECUTE FUNCTION platform_audit_logs_append_only()
"""
PG_TRUNCATE_TRIGGER = """
CREATE TRIGGER platform_audit_logs_no_truncate
BEFORE TRUNCATE ON platform_audit_logs
FOR EACH STATEMENT EXECUTE FUNCTION platform_audit_logs_append_only()
"""

SQLITE_TRIGGERS = (
    "CREATE TRIGGER platform_audit_logs_no_update BEFORE UPDATE ON platform_audit_logs "
    "BEGIN SELECT RAISE(ABORT, 'platform_audit_logs is append-only: UPDATE is not allowed'); END",
    "CREATE TRIGGER platform_audit_logs_no_delete BEFORE DELETE ON platform_audit_logs "
    "BEGIN SELECT RAISE(ABORT, 'platform_audit_logs is append-only: DELETE is not allowed'); END",
)

for _statement in (PG_FUNCTION, PG_ROW_TRIGGER, PG_TRUNCATE_TRIGGER):
    event.listen(PlatformAuditLog.__table__, "after_create", DDL(_statement).execute_if(dialect="postgresql"))
for _statement in SQLITE_TRIGGERS:
    event.listen(PlatformAuditLog.__table__, "after_create", DDL(_statement).execute_if(dialect="sqlite"))


class PlatformAuditIsAppendOnly(RuntimeError):
    pass


@event.listens_for(Session, "before_flush")
def _refuse_changed_platform_audit(session, _flush_context, _instances):
    for obj in session.deleted:
        if isinstance(obj, PlatformAuditLog):
            raise PlatformAuditIsAppendOnly(APPEND_ONLY_MESSAGE)
    for obj in session.dirty:
        if isinstance(obj, PlatformAuditLog) and session.is_modified(obj, include_collections=False):
            raise PlatformAuditIsAppendOnly(APPEND_ONLY_MESSAGE)


@event.listens_for(Session, "do_orm_execute")
def _refuse_bulk_platform_audit(state):
    if state.is_update or state.is_delete:
        target = getattr(state.statement, "table", None)
        if getattr(target, "name", None) == PlatformAuditLog.__tablename__:
            raise PlatformAuditIsAppendOnly(APPEND_ONLY_MESSAGE)
