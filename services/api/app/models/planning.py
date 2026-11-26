"""Stage 6 meal planning (PLAN01–PLAN08, AT05, AT06; docs/STAGE-6-PLANNING-PLAN.md).

- PortionStandard: a per-person quantity of one item for one menu, with an
  effective date (PLAN02, PLAN06). Drafts are edited; an APPROVED version is
  final (S6-2). Approval gives it the next version number for its menu and
  item; the standard in effect on a date is the approved version with the
  latest effective date on or before it, then the highest version (plan
  section 12, choice 1).
- PortionStandardBasis: the closed meal records a suggested standard was
  calculated from (PLAN03), with the quantity used and people served copied
  at the time.
- MealPlan / MealPlanLine: a plan for one campus, date and meal session
  (one live plan per slot, 6-7). A DRAFT plan is calculated live from the
  standards in effect; approval writes each line's snapshot and freezes the
  plan (6-6). A plan never moves stock or creates any purchasing or supplier
  record (PLAN07, S6-5).

Database protection (S6-2), installed here for new schemas and by migration
M4 (f3a8c2d61b47) on existing databases: approved and cancelled standards,
suggestion basis rows, approved and cancelled plans, and the lines of any
plan that is not a draft refuse UPDATE and DELETE; an approved plan may only
become CANCELLED (cancellation fields only).
"""

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    DDL, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric,
    String, UniqueConstraint, event, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.master_data import CampusScoped

ITEM_KINDS = ("RAW", "PREPARED", "OUTSOURCED")
PLANNABLE_KINDS = ("RAW", "PREPARED")
STANDARD_STATUSES = ("DRAFT", "APPROVED", "CANCELLED")
STANDARD_SOURCES = ("MANUAL", "COPIED", "SUGGESTED")
PLAN_STATUSES = ("DRAFT", "APPROVED", "CANCELLED")


class PortionStandard(CampusScoped, Base):
    __tablename__ = "portion_standards"
    __table_args__ = (
        CheckConstraint("status IN ('DRAFT', 'APPROVED', 'CANCELLED')", name="ck_portion_standard_status"),
        CheckConstraint("source IN ('MANUAL', 'COPIED', 'SUGGESTED')", name="ck_portion_standard_source"),
        CheckConstraint("quantity_per_person > 0", name="ck_portion_standard_quantity"),
        CheckConstraint(
            "(source = 'COPIED') = (copied_from_menu_main_item_id IS NOT NULL)",
            name="ck_portion_standard_copied",
        ),
        # Only an approved version has a version number, an approver and the
        # item kind it was approved with (raw or prepared, 6-8).
        CheckConstraint(
            "(status = 'APPROVED') = (approved_at IS NOT NULL) "
            "AND (approved_at IS NULL) = (approved_by IS NULL) "
            "AND (approved_at IS NULL) = (version_no IS NULL) "
            "AND (approved_at IS NULL) = (item_kind IS NULL) "
            "AND (item_kind IS NULL OR item_kind IN ('RAW', 'PREPARED')) "
            "AND (version_no IS NULL OR version_no >= 1)",
            name="ck_portion_standard_approved",
        ),
        CheckConstraint(
            "(status = 'CANCELLED') = (cancelled_at IS NOT NULL) "
            "AND (cancelled_at IS NULL) = (cancelled_by IS NULL) "
            "AND (cancelled_at IS NULL) = (cancellation_reason IS NULL)",
            name="ck_portion_standard_cancelled",
        ),
        UniqueConstraint("campus_id", "menu_id", "item_id", "version_no", name="uq_portion_standard_version"),
        Index("ix_portion_standards_menu_item", "campus_id", "menu_id", "item_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    menu_id: Mapped[int] = mapped_column(ForeignKey("menus.id"), nullable=False)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False)
    quantity_per_person: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    version_no: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="MANUAL", nullable=False)
    # Plain reference, no foreign key (plan section 12, choice 7): deleting a
    # menu main item keeps working as it does today.
    copied_from_menu_main_item_id: Mapped[int | None] = mapped_column(Integer)
    item_kind: Mapped[str | None] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancellation_reason: Mapped[str | None] = mapped_column(String(500))


class PortionStandardBasis(CampusScoped, Base):
    """One closed meal record behind a suggested standard (PLAN03)."""

    __tablename__ = "portion_standard_basis"
    __table_args__ = (
        CheckConstraint("quantity_used > 0", name="ck_portion_standard_basis_quantity"),
        CheckConstraint("people_served > 0", name="ck_portion_standard_basis_people"),
        UniqueConstraint("standard_id", "meal_record_id", name="uq_portion_standard_basis"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    standard_id: Mapped[int] = mapped_column(ForeignKey("portion_standards.id"), nullable=False, index=True)
    meal_record_id: Mapped[int] = mapped_column(ForeignKey("meal_records.id"), nullable=False)
    # Net usage at the record's closing, in the item's standard unit.
    quantity_used: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), nullable=False)
    people_served: Mapped[int] = mapped_column(Integer, nullable=False)


class MealPlan(CampusScoped, Base):
    __tablename__ = "meal_plans"
    __table_args__ = (
        CheckConstraint("status IN ('DRAFT', 'APPROVED', 'CANCELLED')", name="ck_meal_plan_status"),
        CheckConstraint("expected_headcount >= 1", name="ck_meal_plan_headcount"),
        # An approved plan keeps its approval when it is later cancelled.
        CheckConstraint(
            "(approved_at IS NULL) = (approved_by IS NULL) "
            "AND (status <> 'APPROVED' OR approved_at IS NOT NULL) "
            "AND (status <> 'DRAFT' OR approved_at IS NULL)",
            name="ck_meal_plan_approved",
        ),
        CheckConstraint(
            "(status = 'CANCELLED') = (cancelled_at IS NOT NULL) "
            "AND (cancelled_at IS NULL) = (cancelled_by IS NULL) "
            "AND (cancelled_at IS NULL) = (cancellation_reason IS NULL)",
            name="ck_meal_plan_cancelled",
        ),
        UniqueConstraint("campus_id", "plan_seq", name="uq_meal_plan_seq"),
        UniqueConstraint("campus_id", "plan_number", name="uq_meal_plan_number"),
        Index(
            "uq_meal_plan_session_date",
            "campus_id", "plan_date", "meal_session_id",
            unique=True,
            postgresql_where=text("status <> 'CANCELLED'"),
            sqlite_where=text("status <> 'CANCELLED'"),
        ),
        Index("ix_meal_plans_campus_date", "campus_id", "plan_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_seq: Mapped[int] = mapped_column(nullable=False)
    plan_number: Mapped[str] = mapped_column(String(20), nullable=False)
    plan_date: Mapped[date] = mapped_column(Date, nullable=False)
    meal_session_id: Mapped[int] = mapped_column(ForeignKey("meal_sessions.id"), nullable=False)
    menu_id: Mapped[int] = mapped_column(ForeignKey("menus.id"), nullable=False)
    expected_headcount: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancellation_reason: Mapped[str | None] = mapped_column(String(500))


SNAPSHOT_COLUMNS = (
    "standard_id", "item_kind", "standard_quantity_per_person", "standard_unit_id", "quantity_per_person",
    "unit_id", "required_quantity", "rounded_up", "base_unit_id", "conversion_factor", "required_base_quantity",
)


class MealPlanLine(CampusScoped, Base):
    """A main item chosen for a plan (PLAN01). While the plan is a draft only
    the item and any one-day override are stored; approval writes the
    snapshot columns (PLAN04, PLAN06, AT06)."""

    __tablename__ = "meal_plan_lines"
    __table_args__ = (
        UniqueConstraint("plan_id", "item_id", name="uq_meal_plan_line_item"),
        # A one-day override has a quantity, a unit and a reason (PLAN06).
        CheckConstraint(
            "(override_quantity_per_person IS NULL) = (override_unit_id IS NULL) "
            "AND (override_quantity_per_person IS NULL) = (override_reason IS NULL) "
            "AND (override_quantity_per_person IS NULL OR override_quantity_per_person > 0) "
            "AND (override_reason IS NULL OR length(trim(override_reason)) > 0)",
            name="ck_meal_plan_line_override",
        ),
        # The snapshot is written whole, or not at all.
        CheckConstraint(
            " AND ".join(f"({c} IS NULL) = (standard_id IS NULL)" for c in SNAPSHOT_COLUMNS[1:]),
            name="ck_meal_plan_line_snapshot",
        ),
        CheckConstraint(
            "required_quantity IS NULL OR (required_quantity > 0 AND required_base_quantity > 0 "
            "AND quantity_per_person > 0 AND standard_quantity_per_person > 0 AND conversion_factor > 0 "
            "AND item_kind IN ('RAW', 'PREPARED'))",
            name="ck_meal_plan_line_values",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("meal_plans.id"), nullable=False, index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False)
    override_quantity_per_person: Mapped[Decimal | None] = mapped_column(Numeric(18, 3))
    override_unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id"))
    override_reason: Mapped[str | None] = mapped_column(String(500))
    # ---- snapshot written at approval ----
    standard_id: Mapped[int | None] = mapped_column(ForeignKey("portion_standards.id"))
    item_kind: Mapped[str | None] = mapped_column(String(20))
    standard_quantity_per_person: Mapped[Decimal | None] = mapped_column(Numeric(18, 3))
    standard_unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id"))
    quantity_per_person: Mapped[Decimal | None] = mapped_column(Numeric(18, 3))
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id"))
    required_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 3))
    rounded_up: Mapped[bool | None] = mapped_column(Boolean)
    base_unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id"))
    conversion_factor: Mapped[Decimal | None] = mapped_column(Numeric(24, 12))
    required_base_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 3))


# ============================================================
# DATABASE PROTECTION (S6-2)
# ============================================================
# Frozen copies live in migration f3a8c2d61b47 (M4).

PG_STATEMENTS = (
    """
CREATE OR REPLACE FUNCTION portion_standards_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION USING
            MESSAGE = 'portion_standards: a standard is never deleted; cancel a draft instead',
            HINT = 'Stage 6 safeguard S6-2.';
    END IF;
    IF OLD.status <> 'DRAFT' THEN
        RAISE EXCEPTION USING
            MESSAGE = 'portion_standards: an approved or cancelled standard cannot be changed',
            HINT = 'Approve a newer version instead (Stage 6 safeguard S6-2).';
    END IF;
    RETURN NEW;
END;
$$
""",
    """
CREATE TRIGGER portion_standards_final
BEFORE UPDATE OR DELETE ON portion_standards
FOR EACH ROW EXECUTE FUNCTION portion_standards_guard()
""",
    """
CREATE OR REPLACE FUNCTION portion_standard_basis_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION USING
            MESSAGE = 'portion_standard_basis: suggestion basis rows are never changed or deleted',
            HINT = 'Stage 6 safeguard S6-2.';
    END IF;
    IF (SELECT status FROM portion_standards WHERE id = NEW.standard_id) IS DISTINCT FROM 'DRAFT' THEN
        RAISE EXCEPTION USING
            MESSAGE = 'portion_standard_basis: basis rows are added only to a draft standard',
            HINT = 'Stage 6 safeguard S6-2.';
    END IF;
    RETURN NEW;
END;
$$
""",
    """
CREATE TRIGGER portion_standard_basis_final
BEFORE INSERT OR UPDATE OR DELETE ON portion_standard_basis
FOR EACH ROW EXECUTE FUNCTION portion_standard_basis_guard()
""",
    """
CREATE OR REPLACE FUNCTION meal_plans_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION USING
            MESSAGE = 'meal_plans: a plan is never deleted; cancel it instead',
            HINT = 'Stage 6 safeguard S6-2.';
    END IF;
    IF OLD.status = 'CANCELLED' THEN
        RAISE EXCEPTION USING
            MESSAGE = 'meal_plans: a cancelled plan cannot be changed',
            HINT = 'Stage 6 safeguard S6-2.';
    END IF;
    IF OLD.status = 'APPROVED' AND (
        NEW.status <> 'CANCELLED'
        OR (to_jsonb(NEW) - ARRAY['status', 'cancelled_by', 'cancelled_at', 'cancellation_reason', 'updated_at'])
           IS DISTINCT FROM
           (to_jsonb(OLD) - ARRAY['status', 'cancelled_by', 'cancelled_at', 'cancellation_reason', 'updated_at'])
    ) THEN
        RAISE EXCEPTION USING
            MESSAGE = 'meal_plans: an approved plan cannot be changed; cancel it with a reason and create a new plan',
            HINT = 'Stage 6 safeguard S6-2 and decision 6-6.';
    END IF;
    IF OLD.status = 'DRAFT' AND NEW.status = 'APPROVED' AND (
        NOT EXISTS (SELECT 1 FROM meal_plan_lines WHERE plan_id = NEW.id)
        OR EXISTS (SELECT 1 FROM meal_plan_lines WHERE plan_id = NEW.id AND required_base_quantity IS NULL)
    ) THEN
        RAISE EXCEPTION USING
            MESSAGE = 'meal_plans: a plan is approved only with at least one line and every line''s snapshot',
            HINT = 'Stage 6 safeguard S6-2.';
    END IF;
    RETURN NEW;
END;
$$
""",
    """
CREATE TRIGGER meal_plans_final
BEFORE UPDATE OR DELETE ON meal_plans
FOR EACH ROW EXECUTE FUNCTION meal_plans_guard()
""",
    """
CREATE OR REPLACE FUNCTION meal_plan_lines_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP <> 'INSERT' AND (SELECT status FROM meal_plans WHERE id = OLD.plan_id) IS DISTINCT FROM 'DRAFT' THEN
        RAISE EXCEPTION USING
            MESSAGE = 'meal_plan_lines: lines change only while their plan is a draft',
            HINT = 'Stage 6 safeguard S6-2.';
    END IF;
    IF TG_OP <> 'DELETE' AND (SELECT status FROM meal_plans WHERE id = NEW.plan_id) IS DISTINCT FROM 'DRAFT' THEN
        RAISE EXCEPTION USING
            MESSAGE = 'meal_plan_lines: lines change only while their plan is a draft',
            HINT = 'Stage 6 safeguard S6-2.';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$
""",
    """
CREATE TRIGGER meal_plan_lines_final
BEFORE INSERT OR UPDATE OR DELETE ON meal_plan_lines
FOR EACH ROW EXECUTE FUNCTION meal_plan_lines_guard()
""",
)

_APPROVED_PLAN_COLUMNS = (
    "campus_id", "plan_seq", "plan_number", "plan_date", "meal_session_id", "menu_id", "expected_headcount",
    "notes", "created_by", "created_at", "approved_by", "approved_at",
)

SQLITE_STATEMENTS = {
    "portion_standards": (
        "CREATE TRIGGER portion_standards_no_delete BEFORE DELETE ON portion_standards "
        "BEGIN SELECT RAISE(ABORT, 'portion_standards: a standard is never deleted; cancel a draft instead'); END",
        "CREATE TRIGGER portion_standards_final BEFORE UPDATE ON portion_standards WHEN OLD.status <> 'DRAFT' "
        "BEGIN SELECT RAISE(ABORT, 'portion_standards: an approved or cancelled standard cannot be changed'); END",
    ),
    "portion_standard_basis": (
        "CREATE TRIGGER portion_standard_basis_no_update BEFORE UPDATE ON portion_standard_basis "
        "BEGIN SELECT RAISE(ABORT, 'portion_standard_basis: suggestion basis rows are never changed or deleted'); END",
        "CREATE TRIGGER portion_standard_basis_no_delete BEFORE DELETE ON portion_standard_basis "
        "BEGIN SELECT RAISE(ABORT, 'portion_standard_basis: suggestion basis rows are never changed or deleted'); END",
        "CREATE TRIGGER portion_standard_basis_draft_only BEFORE INSERT ON portion_standard_basis "
        "WHEN (SELECT status FROM portion_standards WHERE id = NEW.standard_id) IS NOT 'DRAFT' "
        "BEGIN SELECT RAISE(ABORT, 'portion_standard_basis: basis rows are added only to a draft standard'); END",
    ),
    "meal_plans": (
        "CREATE TRIGGER meal_plans_no_delete BEFORE DELETE ON meal_plans "
        "BEGIN SELECT RAISE(ABORT, 'meal_plans: a plan is never deleted; cancel it instead'); END",
        "CREATE TRIGGER meal_plans_cancelled_final BEFORE UPDATE ON meal_plans WHEN OLD.status = 'CANCELLED' "
        "BEGIN SELECT RAISE(ABORT, 'meal_plans: a cancelled plan cannot be changed'); END",
        "CREATE TRIGGER meal_plans_approved_final BEFORE UPDATE ON meal_plans WHEN OLD.status = 'APPROVED' AND "
        "(NEW.status <> 'CANCELLED' OR " + " OR ".join(f"NEW.{c} IS NOT OLD.{c}" for c in _APPROVED_PLAN_COLUMNS) + ") "
        "BEGIN SELECT RAISE(ABORT, 'meal_plans: an approved plan cannot be changed; cancel it with a reason "
        "and create a new plan'); END",
        "CREATE TRIGGER meal_plans_approval_complete BEFORE UPDATE ON meal_plans "
        "WHEN OLD.status = 'DRAFT' AND NEW.status = 'APPROVED' AND ("
        "NOT EXISTS (SELECT 1 FROM meal_plan_lines WHERE plan_id = NEW.id) "
        "OR EXISTS (SELECT 1 FROM meal_plan_lines WHERE plan_id = NEW.id AND required_base_quantity IS NULL)) "
        "BEGIN SELECT RAISE(ABORT, 'meal_plans: a plan is approved only with at least one line and every "
        "line''s snapshot'); END",
    ),
    "meal_plan_lines": (
        "CREATE TRIGGER meal_plan_lines_draft_insert BEFORE INSERT ON meal_plan_lines "
        "WHEN (SELECT status FROM meal_plans WHERE id = NEW.plan_id) IS NOT 'DRAFT' "
        "BEGIN SELECT RAISE(ABORT, 'meal_plan_lines: lines change only while their plan is a draft'); END",
        "CREATE TRIGGER meal_plan_lines_draft_update BEFORE UPDATE ON meal_plan_lines "
        "WHEN (SELECT status FROM meal_plans WHERE id = OLD.plan_id) IS NOT 'DRAFT' OR NEW.plan_id IS NOT OLD.plan_id "
        "BEGIN SELECT RAISE(ABORT, 'meal_plan_lines: lines change only while their plan is a draft'); END",
        "CREATE TRIGGER meal_plan_lines_draft_delete BEFORE DELETE ON meal_plan_lines "
        "WHEN (SELECT status FROM meal_plans WHERE id = OLD.plan_id) IS NOT 'DRAFT' "
        "BEGIN SELECT RAISE(ABORT, 'meal_plan_lines: lines change only while their plan is a draft'); END",
    ),
}

# Each table gets its function and trigger when it is created (function
# bodies name other tables only at run time).
_PG_BY_TABLE = dict(zip(
    ("portion_standards", "portion_standard_basis", "meal_plans", "meal_plan_lines"),
    (PG_STATEMENTS[i:i + 2] for i in range(0, len(PG_STATEMENTS), 2)),
))
for _model in (PortionStandard, PortionStandardBasis, MealPlan, MealPlanLine):
    for _statement in _PG_BY_TABLE[_model.__tablename__]:
        event.listen(_model.__table__, "after_create", DDL(_statement).execute_if(dialect="postgresql"))
    for _statement in SQLITE_STATEMENTS[_model.__tablename__]:
        event.listen(_model.__table__, "after_create", DDL(_statement).execute_if(dialect="sqlite"))
