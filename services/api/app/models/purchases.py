from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    String, Boolean, ForeignKey, Numeric, Date, DateTime,
    Text, CheckConstraint, UniqueConstraint
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


class StockMovement(CampusScoped, Base):
    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_stock_movement_quantity"),
        UniqueConstraint(
            "campus_id", "receipt_item_id",
            name="uq_stock_movement_receipt_item"
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
