"""Stage 5 meal records (MEAL01–MEAL05; docs/STAGE-5-MEAL-PLAN.md).

A meal record is one meal session on one date in one campus. It holds the
expected and actual headcounts, the dishes prepared (with their output),
how much of each dish was available, distributed and left over, and how
the leftovers were classified. Prepared food never moves raw-ingredient
stock; raw usage is the kitchen issues of the same date and session.

Interim rules (not client decisions; see the plan): retained leftovers are
carried once, whole, into a later record as their own dish line (Q11);
closed records are corrected by reopening (proposal §4.2 note).
"""

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON, CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Index,
    Integer, Numeric, String, UniqueConstraint, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.master_data import CampusScoped

MEAL_STATUSES = ("OPEN", "CLOSED", "CANCELLED")
LEFTOVER_CLASSES = ("RETAINED", "RETURNED_TO_SUPPLIER", "WASTED", "DISPOSED")


class MealRecord(CampusScoped, Base):
    """One meal session on one date (MEAL01). At most one OPEN or CLOSED
    record per campus, date and session; a CANCELLED one stays as history."""

    __tablename__ = "meal_records"
    __table_args__ = (
        CheckConstraint("status IN ('OPEN', 'CLOSED', 'CANCELLED')", name="ck_meal_record_status"),
        CheckConstraint(
            "expected_students >= 0 AND expected_staff >= 0 AND expected_guests >= 0",
            name="ck_meal_record_expected",
        ),
        CheckConstraint(
            "(actual_students IS NULL OR actual_students >= 0) "
            "AND (actual_staff IS NULL OR actual_staff >= 0) "
            "AND (actual_guests IS NULL OR actual_guests >= 0)",
            name="ck_meal_record_actual_nonnegative",
        ),
        # Actual counts are recorded together (all three groups) or not at all.
        CheckConstraint(
            "(actual_students IS NULL) = (actual_staff IS NULL) "
            "AND (actual_staff IS NULL) = (actual_guests IS NULL)",
            name="ck_meal_record_actual_complete",
        ),
        CheckConstraint(
            "status <> 'CLOSED' OR (closed_at IS NOT NULL AND actual_students IS NOT NULL)",
            name="ck_meal_record_closed",
        ),
        CheckConstraint("(closed_at IS NULL) = (closed_by IS NULL)", name="ck_meal_record_closed_by"),
        CheckConstraint(
            "(status = 'CANCELLED') = (cancelled_at IS NOT NULL) "
            "AND (cancelled_at IS NULL) = (cancelled_by IS NULL) "
            "AND (cancelled_at IS NULL) = (cancellation_reason IS NULL)",
            name="ck_meal_record_cancelled",
        ),
        CheckConstraint(
            "(reopened_at IS NULL) = (reopened_by IS NULL) "
            "AND (reopened_at IS NULL) = (reopen_reason IS NULL) "
            "AND (reopened_at IS NULL) = (reopen_count = 0) AND reopen_count >= 0",
            name="ck_meal_record_reopened",
        ),
        Index(
            "uq_meal_record_session_date",
            "campus_id", "meal_date", "meal_session_id",
            unique=True,
            postgresql_where=text("status <> 'CANCELLED'"),
            sqlite_where=text("status <> 'CANCELLED'"),
        ),
        Index("ix_meal_records_campus_date", "campus_id", "meal_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    meal_date: Mapped[date] = mapped_column(Date, nullable=False)
    meal_session_id: Mapped[int] = mapped_column(ForeignKey("meal_sessions.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="OPEN", nullable=False)
    expected_students: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expected_staff: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expected_guests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    actual_students: Mapped[int | None] = mapped_column(Integer)
    actual_staff: Mapped[int | None] = mapped_column(Integer)
    actual_guests: Mapped[int | None] = mapped_column(Integer)
    remarks: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Latest closing; every closing is also in the audit history.
    closed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Net ingredient usage per item at the latest closing (for "issues changed
    # since closing"); also stored in the audit row of that closing.
    closed_usage: Mapped[dict | None] = mapped_column(JSON)
    # Latest reopening; every reopening is also in the audit history.
    reopened_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reopen_reason: Mapped[str | None] = mapped_column(String(500))
    reopen_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cancelled_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancellation_reason: Mapped[str | None] = mapped_column(String(500))


class MealDish(CampusScoped, Base):
    """A prepared dish of a meal record (MEAL02), retained food carried in
    from an earlier record (interim, Q11), or outsourced food received
    through a confirmed delivery (Stage 8a, OUT01). Quantities are in the
    dish's own unit; available = output + carried + received (MEAL03); once
    distribution is recorded, available = distributed + remaining (MEAL05)."""

    __tablename__ = "meal_dishes"
    __table_args__ = (
        CheckConstraint(
            "output_quantity >= 0 AND carried_quantity >= 0 AND received_quantity >= 0",
            name="ck_meal_dish_quantities",
        ),
        CheckConstraint(
            "ABS(available_quantity - (output_quantity + carried_quantity + received_quantity)) < 0.0005",
            name="ck_meal_dish_available",
        ),
        # A prepared dish has output only; a carried-in line has the carried
        # quantity and its source references; a received line (Stage 8a) has
        # the accepted quantity of one confirmed outsourced delivery line.
        CheckConstraint(
            "(source_leftover_id IS NULL AND source_delivery_line_id IS NULL AND output_quantity > 0 "
            " AND carried_quantity = 0 AND received_quantity = 0 "
            " AND source_dish_id IS NULL AND source_meal_record_id IS NULL AND source_classification IS NULL) "
            "OR (source_leftover_id IS NOT NULL AND source_delivery_line_id IS NULL AND output_quantity = 0 "
            " AND carried_quantity > 0 AND received_quantity = 0 "
            " AND source_dish_id IS NOT NULL AND source_meal_record_id IS NOT NULL "
            " AND source_classification = 'RETAINED') "
            "OR (source_delivery_line_id IS NOT NULL AND source_leftover_id IS NULL AND output_quantity = 0 "
            " AND carried_quantity = 0 AND received_quantity > 0 "
            " AND source_dish_id IS NULL AND source_meal_record_id IS NULL AND source_classification IS NULL)",
            name="ck_meal_dish_kind",
        ),
        CheckConstraint(
            "source_meal_record_id IS NULL OR source_meal_record_id <> meal_record_id",
            name="ck_meal_dish_not_own_source",
        ),
        CheckConstraint("(distributed_quantity IS NULL) = (remaining_quantity IS NULL)", name="ck_meal_dish_distribution_pair"),
        CheckConstraint(
            "distributed_quantity IS NULL OR (distributed_quantity >= 0 AND remaining_quantity >= 0 "
            "AND ABS(available_quantity - (distributed_quantity + remaining_quantity)) < 0.0005)",
            name="ck_meal_dish_reconciles",
        ),
        CheckConstraint("length(trim(dish_name)) > 0", name="ck_meal_dish_name"),
        # Each retained line is carried at most once.
        UniqueConstraint("source_leftover_id", name="uq_meal_dish_source_leftover"),
        # Each delivery line is received into at most one meal record (Stage 8a).
        UniqueConstraint("source_delivery_line_id", name="uq_meal_dish_source_delivery_line"),
        # Target of the leftover foreign key (a leftover is in its dish's unit).
        UniqueConstraint("id", "meal_record_id", "campus_id", "unit_id", name="uq_meal_dish_identity"),
        # The carried line matches its source exactly: same campus, record,
        # dish, RETAINED, quantity and unit. While it exists the database
        # refuses to change or delete the source line.
        ForeignKeyConstraint(
            ["source_leftover_id", "source_dish_id", "source_meal_record_id", "campus_id",
             "source_classification", "carried_quantity", "unit_id"],
            ["meal_leftovers.id", "meal_leftovers.dish_id", "meal_leftovers.meal_record_id",
             "meal_leftovers.campus_id", "meal_leftovers.classification", "meal_leftovers.quantity",
             "meal_leftovers.unit_id"],
            name="fk_meal_dish_carried_from",
            use_alter=True,
        ),
        # The received line matches its delivery line exactly: same campus,
        # unit and accepted quantity. While it exists the database refuses to
        # change or delete the delivery line.
        ForeignKeyConstraint(
            ["source_delivery_line_id", "received_quantity", "unit_id", "campus_id"],
            ["outsourced_delivery_lines.id", "outsourced_delivery_lines.accepted_quantity",
             "outsourced_delivery_lines.unit_id", "outsourced_delivery_lines.campus_id"],
            name="fk_meal_dish_received_from",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    meal_record_id: Mapped[int] = mapped_column(ForeignKey("meal_records.id"), nullable=False, index=True)
    dish_name: Mapped[str] = mapped_column(String(200), nullable=False)
    menu_id: Mapped[int | None] = mapped_column(ForeignKey("menus.id"))
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), nullable=False)
    output_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    carried_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal("0"), nullable=False)
    available_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    distributed_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 3))
    remaining_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 3))
    remarks: Mapped[str | None] = mapped_column(String(500))
    # Carried-in retained food (interim, Q11): where it came from.
    source_leftover_id: Mapped[int | None] = mapped_column()
    source_dish_id: Mapped[int | None] = mapped_column(ForeignKey("meal_dishes.id"))
    source_meal_record_id: Mapped[int | None] = mapped_column(ForeignKey("meal_records.id"))
    source_classification: Mapped[str | None] = mapped_column(String(30))
    # Received outsourced food (Stage 8a): the confirmed delivery line.
    received_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), default=Decimal("0"), server_default=text("0"), nullable=False
    )
    source_delivery_line_id: Mapped[int | None] = mapped_column()
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MealLeftover(CampusScoped, Base):
    """How part of a dish's remaining quantity was handled (MEAL04): one line
    per classification per dish, quantity in the dish's unit, remarks
    required. The lines of a dish add up to its remaining quantity before the
    record can be closed (MEAL05)."""

    __tablename__ = "meal_leftovers"
    __table_args__ = (
        CheckConstraint(
            "classification IN ('RETAINED', 'RETURNED_TO_SUPPLIER', 'WASTED', 'DISPOSED')",
            name="ck_meal_leftover_classification",
        ),
        CheckConstraint("quantity > 0", name="ck_meal_leftover_quantity"),
        CheckConstraint("length(trim(remarks)) > 0", name="ck_meal_leftover_remarks"),
        UniqueConstraint("dish_id", "classification", name="uq_meal_leftover_dish_class"),
        # Target of the carried-in line's foreign key.
        UniqueConstraint(
            "id", "dish_id", "meal_record_id", "campus_id", "classification", "quantity", "unit_id",
            name="uq_meal_leftover_identity",
        ),
        # Same record, campus and unit as its dish.
        ForeignKeyConstraint(
            ["dish_id", "meal_record_id", "campus_id", "unit_id"],
            ["meal_dishes.id", "meal_dishes.meal_record_id", "meal_dishes.campus_id", "meal_dishes.unit_id"],
            name="fk_meal_leftover_dish",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    meal_record_id: Mapped[int] = mapped_column(ForeignKey("meal_records.id"), nullable=False, index=True)
    dish_id: Mapped[int] = mapped_column(nullable=False, index=True)
    classification: Mapped[str] = mapped_column(String(30), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), nullable=False)
    remarks: Mapped[str] = mapped_column(String(500), nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
