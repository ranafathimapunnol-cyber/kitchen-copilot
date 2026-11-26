"""Stage 8a outsourced food (OUT01–OUT03 criterion 1, AT04), per
docs/STAGE-8-IMPLEMENTATION-PLAN.md (project decisions P8-1 to P8-5, P8-7).

An outsourced order is food bought ready-made for one meal: a campus, a
meal date and an exact meal session, a supplier, and OUTSOURCED items with
ordered quantity, unit and rate. Deliveries record, per order line, what
arrived (received), what was refused (rejected, with a reason) and what was
kept (accepted = received - rejected). A confirmed delivery's accepted
quantities become "received" dish lines on the meal record of the same
campus, date and exact session, where distribution and leftovers are
recorded as for prepared dishes.

Outsourced food never enters raw-ingredient stock: nothing here creates a
stock movement, a goods receipt, a supplier return or a credit. Rejected
quantities are recorded only; their effect on what is owed waits for client
question Q6 (Stage 8b). Costs are planned on the order (rate x quantity) and
billed on the supplier bill line linked to the order line; the bill stays
the only payable.
"""

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Index, Numeric, String, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.master_data import CampusScoped

OUTSOURCED_ORDER_STATUSES = ("DRAFT", "ORDERED", "CANCELLED")
OUTSOURCED_DELIVERY_STATUSES = ("DRAFT", "CONFIRMED", "CANCELLED")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class OutsourcedOrder(CampusScoped, Base):
    """OO-00001 per campus. DRAFT (editable) -> ORDERED, or CANCELLED with a
    reason. Deliveries are recorded against an ORDERED order."""

    __tablename__ = "outsourced_orders"
    __table_args__ = (
        UniqueConstraint("campus_id", "order_seq", name="uq_outsourced_order_seq"),
        UniqueConstraint("campus_id", "order_number", name="uq_outsourced_order_number"),
        UniqueConstraint("id", "campus_id", name="uq_outsourced_order_identity"),
        CheckConstraint("status IN ('DRAFT', 'ORDERED', 'CANCELLED')", name="ck_outsourced_order_status"),
        CheckConstraint("(ordered_at IS NULL) = (ordered_by IS NULL)", name="ck_outsourced_order_ordered_by"),
        CheckConstraint("status <> 'ORDERED' OR ordered_at IS NOT NULL", name="ck_outsourced_order_ordered"),
        CheckConstraint(
            "(status = 'CANCELLED') = (cancelled_at IS NOT NULL) "
            "AND (cancelled_at IS NULL) = (cancelled_by IS NULL) "
            "AND (cancelled_at IS NULL) = (cancellation_reason IS NULL)",
            name="ck_outsourced_order_cancelled",
        ),
        Index("ix_outsourced_orders_campus_meal", "campus_id", "meal_date", "meal_session_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_seq: Mapped[int] = mapped_column(nullable=False)
    order_number: Mapped[str] = mapped_column(String(30), nullable=False)
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    meal_date: Mapped[date] = mapped_column(Date, nullable=False)
    meal_session_id: Mapped[int] = mapped_column(ForeignKey("meal_sessions.id"), nullable=False)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", nullable=False)
    notes: Mapped[str | None] = mapped_column(String(1000))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ordered_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    ordered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancellation_reason: Mapped[str | None] = mapped_column(String(500))


class OutsourcedOrderLine(CampusScoped, Base):
    """One OUTSOURCED item of an order: ordered quantity in an explicit unit
    (no conversion assumed, Q7), unit rate and line total (the planned cost).
    purchase_item_id is the supplier bill line that bills it (OUT01 criterion
    6): one bill line bills at most one order line."""

    __tablename__ = "outsourced_order_lines"
    __table_args__ = (
        CheckConstraint("ordered_quantity > 0", name="ck_outsourced_order_line_quantity"),
        CheckConstraint("unit_rate >= 0", name="ck_outsourced_order_line_rate"),
        CheckConstraint("line_total >= 0", name="ck_outsourced_order_line_total"),
        CheckConstraint(
            "(purchase_item_id IS NULL) = (linked_at IS NULL) AND (linked_at IS NULL) = (linked_by IS NULL)",
            name="ck_outsourced_order_line_bill_link",
        ),
        UniqueConstraint("order_id", "item_id", name="uq_outsourced_order_line_item"),
        UniqueConstraint("purchase_item_id", name="uq_outsourced_order_line_bill_line"),
        # Target of the delivery line's foreign key: same order, campus and unit.
        UniqueConstraint("id", "order_id", "campus_id", "unit_id", name="uq_outsourced_order_line_identity"),
        ForeignKeyConstraint(
            ["order_id", "campus_id"], ["outsourced_orders.id", "outsourced_orders.campus_id"],
            name="fk_outsourced_order_line_order",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(nullable=False, index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False)
    ordered_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), nullable=False)
    unit_rate: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    remarks: Mapped[str | None] = mapped_column(String(500))
    purchase_item_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_items.id"))
    linked_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    linked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OutsourcedDelivery(CampusScoped, Base):
    """OD-00001 per campus: one delivery against one order. DRAFT (editable)
    -> CONFIRMED once, or CANCELLED with a reason (a confirmed delivery only
    while none of its food has been distributed)."""

    __tablename__ = "outsourced_deliveries"
    __table_args__ = (
        UniqueConstraint("campus_id", "delivery_seq", name="uq_outsourced_delivery_seq"),
        UniqueConstraint("campus_id", "delivery_number", name="uq_outsourced_delivery_number"),
        UniqueConstraint("id", "order_id", "campus_id", name="uq_outsourced_delivery_identity"),
        CheckConstraint("status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')", name="ck_outsourced_delivery_status"),
        CheckConstraint("(confirmed_at IS NULL) = (confirmed_by IS NULL)", name="ck_outsourced_delivery_confirmed_by"),
        CheckConstraint("status <> 'CONFIRMED' OR confirmed_at IS NOT NULL", name="ck_outsourced_delivery_confirmed"),
        CheckConstraint(
            "(status = 'CANCELLED') = (cancelled_at IS NOT NULL) "
            "AND (cancelled_at IS NULL) = (cancelled_by IS NULL) "
            "AND (cancelled_at IS NULL) = (cancellation_reason IS NULL)",
            name="ck_outsourced_delivery_cancelled",
        ),
        ForeignKeyConstraint(
            ["order_id", "campus_id"], ["outsourced_orders.id", "outsourced_orders.campus_id"],
            name="fk_outsourced_delivery_order",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    delivery_seq: Mapped[int] = mapped_column(nullable=False)
    delivery_number: Mapped[str] = mapped_column(String(30), nullable=False)
    order_id: Mapped[int] = mapped_column(nullable=False, index=True)
    delivery_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", nullable=False)
    remarks: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancellation_reason: Mapped[str | None] = mapped_column(String(500))


class OutsourcedDeliveryLine(CampusScoped, Base):
    """Received, rejected and accepted quantities of one order line in one
    delivery, in the order line's unit (OUT01 criterion 2, OUT03 criterion
    1). A rejection needs a reason; no credit or return is recorded (Q6)."""

    __tablename__ = "outsourced_delivery_lines"
    __table_args__ = (
        CheckConstraint("received_quantity > 0", name="ck_outsourced_delivery_line_received"),
        CheckConstraint(
            "rejected_quantity >= 0 AND rejected_quantity <= received_quantity",
            name="ck_outsourced_delivery_line_rejected",
        ),
        CheckConstraint(
            "accepted_quantity >= 0 "
            "AND ABS(accepted_quantity - (received_quantity - rejected_quantity)) < 0.0005",
            name="ck_outsourced_delivery_line_accepted",
        ),
        CheckConstraint(
            "rejected_quantity = 0 OR (rejection_reason IS NOT NULL AND length(trim(rejection_reason)) > 0)",
            name="ck_outsourced_delivery_line_reason",
        ),
        UniqueConstraint("delivery_id", "order_line_id", name="uq_outsourced_delivery_line"),
        # Target of the received meal-dish line's foreign key.
        UniqueConstraint("id", "accepted_quantity", "unit_id", "campus_id", name="uq_outsourced_delivery_line_identity"),
        ForeignKeyConstraint(
            ["delivery_id", "order_id", "campus_id"],
            ["outsourced_deliveries.id", "outsourced_deliveries.order_id", "outsourced_deliveries.campus_id"],
            name="fk_outsourced_delivery_line_delivery",
        ),
        ForeignKeyConstraint(
            ["order_line_id", "order_id", "campus_id", "unit_id"],
            ["outsourced_order_lines.id", "outsourced_order_lines.order_id", "outsourced_order_lines.campus_id",
             "outsourced_order_lines.unit_id"],
            name="fk_outsourced_delivery_line_order_line",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    delivery_id: Mapped[int] = mapped_column(nullable=False, index=True)
    order_id: Mapped[int] = mapped_column(nullable=False)
    order_line_id: Mapped[int] = mapped_column(nullable=False, index=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), nullable=False)
    received_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    rejected_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal("0"), nullable=False)
    accepted_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(String(500))
    remarks: Mapped[str | None] = mapped_column(String(500))
