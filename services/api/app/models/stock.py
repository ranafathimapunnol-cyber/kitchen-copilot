"""Stage 4 stock documents. Ledger rows themselves are StockMovement
(app/models/purchases.py)."""

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Index,
    Numeric, String, UniqueConstraint, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.master_data import CampusScoped


class StockOpening(CampusScoped, Base):
    """Opening stock for one item (STK01, decision S3). Posting it creates
    one OPENING movement (source key OPENING:<id>). It is corrected only by
    reversing it, with a reason, and entering a new one: the row stays as
    history with status REVERSED, and at most one ACTIVE opening exists per
    item per campus (a partial unique index)."""

    __tablename__ = "stock_openings"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_stock_opening_quantity"),
        CheckConstraint(
            "standard_quantity > 0", name="ck_stock_opening_standard_quantity"
        ),
        CheckConstraint(
            "conversion_factor > 0", name="ck_stock_opening_conversion_factor"
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'REVERSED')", name="ck_stock_opening_status"
        ),
        CheckConstraint(
            "(status = 'REVERSED') = (reversed_at IS NOT NULL) "
            "AND (reversed_at IS NULL) = (reversed_by IS NULL) "
            "AND (reversed_at IS NULL) = (reversal_reason IS NULL)",
            name="ck_stock_opening_reversal_complete",
        ),
        Index(
            "uq_stock_opening_active_item",
            "campus_id", "item_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
            sqlite_where=text("status = 'ACTIVE'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id"), nullable=False, index=True
    )
    # As entered, and as posted in the item's standard unit with the factor
    # used (ADR-007), so a later change to a conversion cannot alter it.
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), nullable=False)
    conversion_factor: Mapped[Decimal] = mapped_column(
        Numeric(24, 12), nullable=False
    )
    standard_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), nullable=False
    )
    standard_unit_id: Mapped[int] = mapped_column(
        ForeignKey("units.id"), nullable=False
    )
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    remarks: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(
        String(20), default="ACTIVE", nullable=False
    )
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    reversed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reversal_reason: Mapped[str | None] = mapped_column(String(500))


# ============================================================
# KITCHEN ISSUES AND UNUSED RETURNS (Stage 4 slice 4b, migration M2b)
# ============================================================

DOCUMENT_STATUSES = ("DRAFT", "CONFIRMED", "CANCELLED", "REVERSED")


def document_checks(prefix: str) -> tuple:
    """Status and audit-field rules shared by kitchen issues and returns:
    each status carries exactly its own fields."""
    return (
        CheckConstraint(
            "status IN ('DRAFT', 'CONFIRMED', 'CANCELLED', 'REVERSED')",
            name=f"ck_{prefix}_status",
        ),
        CheckConstraint(
            "(status IN ('CONFIRMED', 'REVERSED')) = (confirmed_at IS NOT NULL) "
            "AND (confirmed_at IS NULL) = (confirmed_by IS NULL) "
            "AND (confirmed_at IS NULL) = (effective_at IS NULL)",
            name=f"ck_{prefix}_confirmation_complete",
        ),
        CheckConstraint(
            "(status = 'CANCELLED') = (cancelled_at IS NOT NULL) "
            "AND (cancelled_at IS NULL) = (cancelled_by IS NULL) "
            "AND (cancelled_at IS NULL) = (cancellation_reason IS NULL)",
            name=f"ck_{prefix}_cancellation_complete",
        ),
        CheckConstraint(
            "(status = 'REVERSED') = (reversed_at IS NOT NULL) "
            "AND (reversed_at IS NULL) = (reversed_by IS NULL) "
            "AND (reversed_at IS NULL) = (reversal_reason IS NULL)",
            name=f"ck_{prefix}_reversal_complete",
        ),
    )


def line_checks(prefix: str) -> tuple:
    return (
        CheckConstraint("quantity > 0", name=f"ck_{prefix}_quantity"),
        CheckConstraint("standard_quantity > 0", name=f"ck_{prefix}_standard_quantity"),
        CheckConstraint("conversion_factor > 0", name=f"ck_{prefix}_conversion_factor"),
    )


class DocumentFields:
    """Status, effective time and the audit trail of a kitchen document."""

    remarks: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", nullable=False)
    # When the stock moved (decisions 4b-1, 4b-2); set on confirmation.
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancellation_reason: Mapped[str | None] = mapped_column(String(500))
    reversed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reversal_reason: Mapped[str | None] = mapped_column(String(500))


class LineFields:
    """A quantity as entered and as posted in the item's standard unit, with
    the conversion factor used (ADR-007)."""

    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), nullable=False)
    conversion_factor: Mapped[Decimal] = mapped_column(Numeric(24, 12), nullable=False)
    standard_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    standard_unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), nullable=False)
    remarks: Mapped[str | None] = mapped_column(String(500))


class KitchenIssue(CampusScoped, DocumentFields, Base):
    """Ingredients issued from the store to the kitchen for a meal session
    and menu (STK02). A draft posts nothing; confirmation posts one ISSUE
    movement per line (source ISSUE_ITEM:<line>); a confirmed issue is
    corrected only by reversal and re-entry."""

    __tablename__ = "kitchen_issues"
    __table_args__ = (
        UniqueConstraint("campus_id", "issue_seq", name="uq_kitchen_issue_seq"),
        UniqueConstraint("campus_id", "issue_number", name="uq_kitchen_issue_number"),
        Index("ix_kitchen_issues_campus_date", "campus_id", "issue_date"),
        *document_checks("kitchen_issue"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    issue_seq: Mapped[int] = mapped_column(nullable=False)
    issue_number: Mapped[str] = mapped_column(String(20), nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    meal_session_id: Mapped[int] = mapped_column(ForeignKey("meal_sessions.id"), nullable=False)
    menu_id: Mapped[int] = mapped_column(ForeignKey("menus.id"), nullable=False)


class KitchenIssueItem(CampusScoped, LineFields, Base):
    __tablename__ = "kitchen_issue_items"
    __table_args__ = (
        UniqueConstraint("issue_id", "item_id", name="uq_kitchen_issue_item"),
        *line_checks("kitchen_issue_item"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("kitchen_issues.id"), nullable=False, index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False)


class KitchenReturn(CampusScoped, DocumentFields, Base):
    """Unused ingredients returned from the kitchen against one confirmed
    issue (STK03). Confirmation posts one UNUSED_RETURN movement per line
    (source RETURN_ITEM:<line>)."""

    __tablename__ = "kitchen_returns"
    __table_args__ = (
        UniqueConstraint("campus_id", "return_seq", name="uq_kitchen_return_seq"),
        UniqueConstraint("campus_id", "return_number", name="uq_kitchen_return_number"),
        *document_checks("kitchen_return"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    return_seq: Mapped[int] = mapped_column(nullable=False)
    return_number: Mapped[str] = mapped_column(String(20), nullable=False)
    issue_id: Mapped[int] = mapped_column(ForeignKey("kitchen_issues.id"), nullable=False, index=True)
    return_date: Mapped[date] = mapped_column(Date, nullable=False)


class KitchenReturnItem(CampusScoped, LineFields, Base):
    __tablename__ = "kitchen_return_items"
    __table_args__ = (
        UniqueConstraint("return_id", "issue_item_id", name="uq_kitchen_return_item"),
        *line_checks("kitchen_return_item"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    return_id: Mapped[int] = mapped_column(ForeignKey("kitchen_returns.id"), nullable=False, index=True)
    issue_item_id: Mapped[int] = mapped_column(ForeignKey("kitchen_issue_items.id"), nullable=False)


# ============================================================
# PHYSICAL COUNTS AND ADJUSTMENTS (Stage 4 slice 4c, migration M2c)
# ============================================================

class StockCount(CampusScoped, Base):
    """A physical stock count (STK05, decision S6), numbered SC-00001 per
    campus. Saved once and never changed: the time it was saved is the count
    time, the user who saved it is the counter (the verifier), and a reason
    is required. Entry is blind: the count screen never shows the system
    balance. Its state (differences, adjustments pending or decided) is read
    from its lines and adjustments, so the row itself never changes."""

    __tablename__ = "stock_counts"
    __table_args__ = (
        UniqueConstraint("campus_id", "count_seq", name="uq_stock_count_seq"),
        UniqueConstraint("campus_id", "count_number", name="uq_stock_count_number"),
        # Target of the composite foreign key on stock_adjustments, so the
        # counter copied onto an adjustment is always the real counter.
        UniqueConstraint("id", "counted_by", name="uq_stock_count_counter"),
        Index("ix_stock_counts_campus_counted_at", "campus_id", "counted_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    count_seq: Mapped[int] = mapped_column(nullable=False)
    count_number: Mapped[str] = mapped_column(String(20), nullable=False)
    counted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    counted_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    remarks: Mapped[str | None] = mapped_column(String(500))


class StockCountItem(CampusScoped, Base):
    """One counted item. The physical quantity as entered and in the item's
    standard unit (with the factor used, ADR-007), the system balance when
    the count was saved, and the difference: stored, never recalculated."""

    __tablename__ = "stock_count_items"
    __table_args__ = (
        UniqueConstraint("count_id", "item_id", name="uq_stock_count_item"),
        # Target of the composite foreign key on stock_adjustments.
        UniqueConstraint("id", "count_id", "item_id", name="uq_stock_count_item_line"),
        CheckConstraint("quantity >= 0", name="ck_stock_count_item_quantity"),
        CheckConstraint("standard_quantity >= 0", name="ck_stock_count_item_standard_quantity"),
        CheckConstraint("conversion_factor > 0", name="ck_stock_count_item_conversion_factor"),
        # Exact on PostgreSQL (all three are numeric(18,3)); the tolerance only
        # absorbs SQLite's floating-point storage in tests.
        CheckConstraint(
            "ABS(difference - (standard_quantity - system_balance)) < 0.0005",
            name="ck_stock_count_item_difference",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    count_id: Mapped[int] = mapped_column(ForeignKey("stock_counts.id"), nullable=False, index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False)
    # The physical quantity as counted (0 allowed: nothing found).
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), nullable=False)
    conversion_factor: Mapped[Decimal] = mapped_column(Numeric(24, 12), nullable=False)
    standard_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    standard_unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), nullable=False)
    system_balance: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    difference: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    remarks: Mapped[str | None] = mapped_column(String(500))


class StockAdjustment(CampusScoped, Base):
    """A request to correct stock by one count line's difference (STK05,
    decision S6). Raised by an explicit action, never automatically; at most
    one PENDING per item per campus. Approved or rejected by an ADMIN or
    KITCHEN_MANAGER who is not the counter (API and database check; no
    fallback while client question Q10 is open). Approval posts one
    ADJUSTMENT movement (source ADJUSTMENT:<id>) for the difference measured
    at count time, effective at the count time; rejection posts nothing."""

    __tablename__ = "stock_adjustments"
    __table_args__ = (
        UniqueConstraint("count_item_id", name="uq_stock_adjustment_count_item"),
        ForeignKeyConstraint(
            ["count_item_id", "count_id", "item_id"],
            ["stock_count_items.id", "stock_count_items.count_id", "stock_count_items.item_id"],
            name="fk_stock_adjustment_count_line",
        ),
        ForeignKeyConstraint(
            ["count_id", "counted_by"],
            ["stock_counts.id", "stock_counts.counted_by"],
            name="fk_stock_adjustment_counter",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED')", name="ck_stock_adjustment_status"
        ),
        CheckConstraint(
            "(status = 'PENDING') = (decided_at IS NULL) "
            "AND (decided_at IS NULL) = (decided_by IS NULL)",
            name="ck_stock_adjustment_decision_complete",
        ),
        CheckConstraint(
            "status <> 'REJECTED' OR decision_reason IS NOT NULL",
            name="ck_stock_adjustment_rejection_reason",
        ),
        CheckConstraint(
            "decided_by IS NULL OR decided_by <> counted_by",
            name="ck_stock_adjustment_independent_approver",
        ),
        Index(
            "uq_stock_adjustment_pending_item",
            "campus_id", "item_id",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
            sqlite_where=text("status = 'PENDING'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    count_id: Mapped[int] = mapped_column(nullable=False, index=True)
    count_item_id: Mapped[int] = mapped_column(nullable=False)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False)
    # Copied from the count (composite foreign key), for the database check.
    counted_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False)
    raised_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    raised_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str | None] = mapped_column(String(500))
