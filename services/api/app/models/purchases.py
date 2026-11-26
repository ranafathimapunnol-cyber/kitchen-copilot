from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    BigInteger, String, Boolean, ForeignKey, Numeric, Date, DateTime,
    Text, CheckConstraint, UniqueConstraint, SmallInteger, Index
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.master_data import CampusScoped


class Purchase(CampusScoped, Base):
    __tablename__ = "purchases"
    __table_args__ = (
        UniqueConstraint(
            "campus_id", "supplier_id", "invoice_number",
            name="uq_purchase_campus_supplier_invoice"
        ),
        CheckConstraint("discount >= 0", name="ck_purchase_discount"),
        CheckConstraint("extra_charges >= 0", name="ck_purchase_extra_charges"),
        CheckConstraint("subtotal >= 0", name="ck_purchase_subtotal"),
        CheckConstraint("grand_total >= 0", name="ck_purchase_grand_total"),
        CheckConstraint(
            "(duplicate_reviewed_at IS NULL) = (duplicate_reviewed_by IS NULL)",
            name="ck_purchase_duplicate_review_complete",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("suppliers.id"), nullable=False
    )
    invoice_number: Mapped[str] = mapped_column(String(100), nullable=False)
    purchase_date: Mapped[date] = mapped_column(Date, nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0"), nullable=False
    )
    discount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0"), nullable=False
    )
    extra_charges: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0"), nullable=False
    )
    grand_total: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0"), nullable=False
    )
    remarks: Mapped[str | None] = mapped_column(Text)
    # Unused: superseded by purchase_attachments (ADR-008). Kept because
    # existing columns are never dropped.
    bill_attachment_path: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(
        String(30), default="DRAFT", nullable=False
    )
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Review of a possible duplicate invoice (PUR01): set when an
    # authorised user confirms the bill is not a duplicate.
    duplicate_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    duplicate_reviewed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", name="fk_purchases_duplicate_reviewed_by_users")
    )
    duplicate_review_note: Mapped[str | None] = mapped_column(String(500))
    # The purchase order this bill was entered against, if any (Stage 3).
    purchase_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("purchase_orders.id", name="fk_purchases_purchase_order_id"),
        index=True,
    )


class PurchaseAttachment(CampusScoped, Base):
    """A file attached to a supplier bill (ADR-008). The file is kept in
    private storage under object_key; only its metadata is stored here.
    Attachments are permanent."""

    __tablename__ = "purchase_attachments"
    __table_args__ = (
        CheckConstraint("size_bytes > 0", name="ck_purchase_attachment_size"),
        UniqueConstraint("object_key", name="uq_purchase_attachment_object_key"),
        UniqueConstraint(
            "purchase_id", "checksum_sha256", name="uq_purchase_attachment_file"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_id: Mapped[int] = mapped_column(
        ForeignKey("purchases.id"), nullable=False, index=True
    )
    object_key: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    remarks: Mapped[str | None] = mapped_column(String(500))
    uploaded_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class PurchaseItem(CampusScoped, Base):
    __tablename__ = "purchase_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_purchase_item_quantity"),
        CheckConstraint("unit_rate >= 0", name="ck_purchase_item_rate"),
        CheckConstraint("line_total >= 0", name="ck_purchase_item_total"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_id: Mapped[int] = mapped_column(
        ForeignKey("purchases.id"), nullable=False, index=True
    )
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), nullable=False
    )
    unit_id: Mapped[int] = mapped_column(
        ForeignKey("units.id"), nullable=False
    )
    unit_rate: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    line_total: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False
    )
    remarks: Mapped[str | None] = mapped_column(String(500))
    # The purchase-order line this bill line bills for, if any (Stage 3).
    purchase_order_item_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "purchase_order_items.id",
            name="fk_purchase_items_purchase_order_item_id",
        ),
        index=True,
    )


# Purchase-order statuses (Stage 3). There is no approval step: the client
# has not said who approves purchases. A future approval step would add
# statuses between DRAFT and PLACED (see PURCHASE_ORDER_TRANSITIONS in
# app/api/routes/purchase_orders.py).
PURCHASE_ORDER_STATUSES = ("DRAFT", "PLACED", "CLOSED", "CANCELLED")


class PurchaseOrder(CampusScoped, Base):
    """What was ordered from a supplier: items and quantities, no prices
    (prices come from the supplier's bill)."""

    __tablename__ = "purchase_orders"
    __table_args__ = (
        UniqueConstraint("campus_id", "order_seq", name="uq_purchase_order_seq"),
        UniqueConstraint("campus_id", "order_number", name="uq_purchase_order_number"),
        CheckConstraint(
            "status IN ('DRAFT', 'PLACED', 'CLOSED', 'CANCELLED')",
            name="ck_purchase_order_status",
        ),
        CheckConstraint(
            "expected_date IS NULL OR expected_date >= order_date",
            name="ck_purchase_order_dates",
        ),
        CheckConstraint(
            "(placed_at IS NULL) = (placed_by IS NULL)", name="ck_purchase_order_placed"
        ),
        CheckConstraint(
            "(closed_at IS NULL) = (closed_by IS NULL)", name="ck_purchase_order_closed"
        ),
        CheckConstraint(
            "(cancelled_at IS NULL) = (cancelled_by IS NULL)",
            name="ck_purchase_order_cancelled",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_seq: Mapped[int] = mapped_column(nullable=False)
    order_number: Mapped[str] = mapped_column(String(30), nullable=False)
    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("suppliers.id"), nullable=False, index=True
    )
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", nullable=False)
    remarks: Mapped[str | None] = mapped_column(String(1000))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    placed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    placed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    close_reason: Mapped[str | None] = mapped_column(String(500))
    cancelled_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(String(500))


class PurchaseOrderItem(CampusScoped, Base):
    __tablename__ = "purchase_order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_purchase_order_item_quantity"),
        UniqueConstraint("purchase_order_id", "item_id", name="uq_purchase_order_item"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_order_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_orders.id"), nullable=False, index=True
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), nullable=False)
    remarks: Mapped[str | None] = mapped_column(String(500))


class GoodsReceipt(CampusScoped, Base):
    __tablename__ = "goods_receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_id: Mapped[int] = mapped_column(
        ForeignKey("purchases.id"), nullable=False, index=True
    )
    receipt_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), default="DRAFT", nullable=False
    )
    remarks: Mapped[str | None] = mapped_column(Text)
    accepted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class GoodsReceiptItem(CampusScoped, Base):
    __tablename__ = "goods_receipt_items"
    __table_args__ = (
        CheckConstraint(
            "quantity_received > 0",
            name="ck_receipt_quantity_received"
        ),
        CheckConstraint(
            "quantity_accepted >= 0",
            name="ck_receipt_quantity_accepted"
        ),
        CheckConstraint(
            "quantity_rejected >= 0",
            name="ck_receipt_quantity_rejected"
        ),
        CheckConstraint(
            "quantity_accepted + quantity_rejected <= quantity_received",
            name="ck_receipt_quantity_split"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(
        ForeignKey("goods_receipts.id"), nullable=False, index=True
    )
    purchase_item_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_items.id"), nullable=False
    )
    quantity_received: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), nullable=False
    )
    quantity_accepted: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), default=Decimal("0"), nullable=False
    )
    quantity_rejected: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), default=Decimal("0"), nullable=False
    )
    remarks: Mapped[str | None] = mapped_column(String(500))


STOCK_MOVEMENT_TYPES = (
    "OPENING", "RECEIPT", "ISSUE", "UNUSED_RETURN",
    "SUPPLIER_RETURN", "ADJUSTMENT", "REVERSAL",
)


class StockMovement(CampusScoped, Base):
    """One posting in the stock ledger (STK01). Posted rows are never edited
    or deleted: a mistake is corrected by a REVERSAL row that points at the
    original. `quantity` is always positive in the item's standard unit;
    `direction` (+1 in, -1 out) carries the sign. `effective_at` is when the
    stock moved (the transaction date); `created_at` is when it was posted.
    Balances replay rows in (effective_at, id) order."""

    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_stock_movement_quantity"),
        UniqueConstraint(
            "campus_id", "receipt_item_id",
            name="uq_stock_movement_receipt_item"
        ),
        CheckConstraint(
            "direction IN (1, -1)", name="ck_stock_movement_direction"
        ),
        CheckConstraint(
            "movement_type IN ("
            + ", ".join(f"'{t}'" for t in STOCK_MOVEMENT_TYPES)
            + ")",
            name="ck_stock_movement_type",
        ),
        CheckConstraint(
            "movement_type NOT IN ('OPENING', 'RECEIPT', 'UNUSED_RETURN') "
            "OR direction = 1",
            name="ck_stock_movement_inflow_direction",
        ),
        CheckConstraint(
            "movement_type NOT IN ('ISSUE', 'SUPPLIER_RETURN') "
            "OR direction = -1",
            name="ck_stock_movement_outflow_direction",
        ),
        CheckConstraint(
            "(movement_type = 'REVERSAL') = (reversal_of_id IS NOT NULL)",
            name="ck_stock_movement_reversal_link",
        ),
        UniqueConstraint(
            "campus_id", "source_key", name="uq_stock_movement_source_key"
        ),
        UniqueConstraint(
            "reversal_of_id", name="uq_stock_movement_reversal_of"
        ),
        Index(
            "ix_stock_movements_ledger_order",
            "campus_id", "item_id", "effective_at", "id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id"), nullable=False, index=True
    )
    movement_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), nullable=False
    )
    unit_id: Mapped[int] = mapped_column(
        ForeignKey("units.id"), nullable=False
    )
    receipt_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("goods_receipt_items.id"), nullable=True
    )
    reference_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )
    reference_id: Mapped[int] = mapped_column(nullable=False)
    remarks: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    # Stage 4 ledger columns (migration b5e1d7c3a920).
    direction: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # What posted this row, e.g. RECEIPT_ITEM:12, OPENING:3, REVERSAL:40.
    # Unique per campus, so the same source can never post twice.
    source_key: Mapped[str] = mapped_column(String(100), nullable=False)
    reversal_of_id: Mapped[int | None] = mapped_column(
        ForeignKey("stock_movements.id"), nullable=True
    )


class SupplierPayment(CampusScoped, Base):
    __tablename__ = "supplier_payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_supplier_payment_amount"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_id: Mapped[int] = mapped_column(
        ForeignKey("purchases.id"), nullable=False, index=True
    )
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False
    )
    payment_method: Mapped[str] = mapped_column(
        String(50), nullable=False
    )
    reference_number: Mapped[str | None] = mapped_column(String(100))
    remarks: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class SupplierReturn(CampusScoped, Base):
    __tablename__ = "supplier_returns"

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_id: Mapped[int] = mapped_column(
        ForeignKey("purchases.id"), nullable=False, index=True
    )
    return_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), default="DRAFT", nullable=False
    )
    credit_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0"), nullable=False
    )
    remarks: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class SupplierReturnItem(CampusScoped, Base):
    __tablename__ = "supplier_return_items"
    __table_args__ = (
        CheckConstraint(
            "quantity > 0", name="ck_supplier_return_quantity"
        ),
        CheckConstraint(
            "unit_rate >= 0", name="ck_supplier_return_rate"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    return_id: Mapped[int] = mapped_column(
        ForeignKey("supplier_returns.id"), nullable=False, index=True
    )
    purchase_item_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_items.id"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), nullable=False
    )
    unit_rate: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    line_total: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False
    )
    remarks: Mapped[str | None] = mapped_column(String(500))
