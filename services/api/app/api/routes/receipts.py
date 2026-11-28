
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import require_any_permission
from app.api.routes.master_data import (
    get_unit_conversion_factor,
    record_audit,
)
from app.core.clock import campus_timezone, campus_today, utc_iso
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.master_data import Category, Item, Supplier, Unit
from app.models.purchases import (
    GoodsReceipt,
    GoodsReceiptItem,
    Purchase,
    PurchaseItem,
    PurchaseOrder,
    PurchaseOrderItem,
    StockMovement,
)
from app.models.user import User
from app.services.outsourced_guard import not_outsourced, refuse_outsourced

router = APIRouter(tags=["Goods Receipts"])

QUANTITY_STEP = Decimal("0.001")


# ============================================================
# QUANTITY HELPER
# ============================================================

def quantity(value: Decimal) -> Decimal:
    return value.quantize(
        QUANTITY_STEP,
        rounding=ROUND_HALF_UP,
    )


def quantity_text(value) -> str:
    """An exact quantity for JSON: "12.500", never a float."""
    return format(quantity(Decimal(str(value or 0))), "f")


# Receipt statuses. DRAFT reserves quantity and posts no stock; ACCEPTED
# has posted its accepted quantities; CANCELLED is a draft withdrawn before
# acceptance (kept, audited, reserving nothing).
RECEIPT_STATUSES = ("DRAFT", "ACCEPTED", "CANCELLED")
ZERO = Decimal("0")
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def page_meta(total: int, page: int, page_size: int) -> dict:
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


def like_contains(term: str) -> str:
    """A case-insensitive "contains" pattern; wildcards typed by the user
    are matched literally (use with escape="\\")."""
    escaped = (
        term.lower()
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    return f"%{escaped}%"


def check_receipt_date(value: date) -> None:
    if value > campus_today():
        raise HTTPException(
            status_code=422,
            detail="A receipt cannot be dated in the future.",
        )


def campus_purchase(
    db: Session, user: User, purchase_id: int, lock: bool = False
) -> Purchase:
    query = db.query(Purchase).filter(
        Purchase.id == purchase_id,
        Purchase.campus_id == user.campus_id,
    )
    if lock:
        # Serialises receipt entry per bill, so two drafts saved at the
        # same moment cannot together exceed the billed quantity.
        query = query.with_for_update()
    purchase = query.first()
    if not purchase:
        raise HTTPException(status_code=404, detail="Purchase not found")
    return purchase


def receipt_progress(
    db: Session,
    campus_id: int,
    purchase_item_ids: list[int],
    exclude_receipt_id: int | None = None,
) -> dict[int, dict[str, Decimal]]:
    """Per bill line: what accepted receipts recorded (received, accepted,
    rejected) and what drafts still hold. Cancelled receipts count for
    nothing."""
    progress = {
        line_id: {"received": ZERO, "accepted": ZERO, "rejected": ZERO, "in_draft": ZERO}
        for line_id in purchase_item_ids
    }
    if not purchase_item_ids:
        return progress

    query = (
        db.query(
            GoodsReceiptItem.purchase_item_id,
            GoodsReceipt.status,
            func.sum(GoodsReceiptItem.quantity_received),
            func.sum(GoodsReceiptItem.quantity_accepted),
            func.sum(GoodsReceiptItem.quantity_rejected),
        )
        .join(GoodsReceipt, GoodsReceipt.id == GoodsReceiptItem.receipt_id)
        .filter(
            GoodsReceiptItem.campus_id == campus_id,
            GoodsReceipt.campus_id == campus_id,
            GoodsReceiptItem.purchase_item_id.in_(purchase_item_ids),
            GoodsReceipt.status.in_(("DRAFT", "ACCEPTED")),
        )
    )
    if exclude_receipt_id is not None:
        query = query.filter(GoodsReceipt.id != exclude_receipt_id)

    for line_id, receipt_status, received, accepted, rejected in query.group_by(
        GoodsReceiptItem.purchase_item_id, GoodsReceipt.status
    ):
        entry = progress[line_id]
        if receipt_status == "ACCEPTED":
            entry["received"] += Decimal(str(received or 0))
            entry["accepted"] += Decimal(str(accepted or 0))
            entry["rejected"] += Decimal(str(rejected or 0))
        else:
            entry["in_draft"] += Decimal(str(received or 0))
    return progress


def prepare_lines(
    db: Session,
    user: User,
    purchase: Purchase,
    items: list,
    exclude_receipt_id: int | None = None,
) -> list[dict]:
    """Validate receipt lines against the bill and against what other
    receipts (drafts included) already hold."""
    line_ids = [line.purchase_item_id for line in items]
    if len(line_ids) != len(set(line_ids)):
        raise HTTPException(
            status_code=422,
            detail="A purchase item can appear only once in a receipt",
        )

    progress = receipt_progress(
        db, user.campus_id, line_ids, exclude_receipt_id=exclude_receipt_id
    )
    prepared = []

    for line in items:
        purchase_line = (
            db.query(PurchaseItem)
            .filter(
                PurchaseItem.id == line.purchase_item_id,
                PurchaseItem.purchase_id == purchase.id,
                PurchaseItem.campus_id == user.campus_id,
            )
            .first()
        )
        if not purchase_line:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Purchase item {line.purchase_item_id} "
                    "not found in this purchase"
                ),
            )

        # Stage 8a (P8-2): outsourced food is received as an outsourced
        # delivery, never through a goods receipt, and never enters stock.
        refuse_outsourced(db, user.campus_id, [purchase_line.item_id], "received into stock")

        received = quantity(line.quantity_received)
        accepted = quantity(line.quantity_accepted)
        rejected = quantity(line.quantity_rejected)

        if accepted + rejected > received:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Accepted and rejected quantities cannot "
                    "exceed received quantity"
                ),
            )

        # Drafts count too, so quantities already recorded are reserved.
        held = progress[purchase_line.id]
        already_recorded = held["received"] + held["in_draft"]
        if already_recorded + received > Decimal(str(purchase_line.quantity)):
            raise HTTPException(
                status_code=422,
                detail=(
                    "Receipt quantity exceeds the remaining "
                    f"purchased quantity for purchase item {purchase_line.id}"
                ),
            )

        prepared.append({
            "purchase_item_id": purchase_line.id,
            "quantity_received": received,
            "quantity_accepted": accepted,
            "quantity_rejected": rejected,
            "remarks": line.remarks,
        })

    return prepared


# ============================================================
# REQUEST SCHEMAS
# ============================================================

class ReceiptLineInput(BaseModel):
    purchase_item_id: int

    quantity_received: Decimal = Field(
        gt=0,
        max_digits=18,
        decimal_places=3,
    )

    quantity_accepted: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        max_digits=18,
        decimal_places=3,
    )

    quantity_rejected: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        max_digits=18,
        decimal_places=3,
    )

    remarks: str | None = Field(
        default=None,
        max_length=500,
    )


class ReceiptCreate(BaseModel):
    receipt_date: date | None = None
    remarks: str | None = None
    items: list[ReceiptLineInput] = Field(min_length=1)


class ReceiptUpdate(ReceiptCreate):
    """Corrects a draft before acceptance: its date, remarks and lines."""


class ReceiptCancel(BaseModel):
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def reason_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Give a reason for cancelling this draft.")
        return value


# ============================================================
# GET RECEIPT
# ============================================================

def get_receipt(
    receipt_id: int,
    db: Session,
    user: User,
) -> GoodsReceipt:

    receipt = (
        db.query(GoodsReceipt)
        .filter(
            GoodsReceipt.id == receipt_id,
            GoodsReceipt.campus_id == user.campus_id,
        )
        .first()
    )

    if not receipt:
        raise HTTPException(
            status_code=404,
            detail="Goods receipt not found",
        )

    return receipt


# ============================================================
# SERIALIZE RECEIPT
# ============================================================

def serialize_receipt(
    db: Session,
    receipt: GoodsReceipt,
) -> dict:

    campus_id = receipt.campus_id
    rows = (
        db.query(GoodsReceiptItem, PurchaseItem, Item, Unit)
        .outerjoin(
            PurchaseItem,
            (PurchaseItem.id == GoodsReceiptItem.purchase_item_id)
            & (PurchaseItem.campus_id == campus_id),
        )
        .outerjoin(
            Item, (Item.id == PurchaseItem.item_id) & (Item.campus_id == campus_id)
        )
        .outerjoin(
            Unit, (Unit.id == PurchaseItem.unit_id) & (Unit.campus_id == campus_id)
        )
        .filter(
            GoodsReceiptItem.receipt_id == receipt.id,
            GoodsReceiptItem.campus_id == campus_id,
        )
        .order_by(GoodsReceiptItem.id)
        .all()
    )

    result = [
        {
            "id": line.id,
            "purchase_item_id": line.purchase_item_id,
            "item_id": purchase_line.item_id if purchase_line else None,
            "item_name": item.name if item else None,
            "billed_quantity": (
                quantity_text(purchase_line.quantity) if purchase_line else None
            ),
            "unit_symbol": unit.symbol if unit else None,
            "quantity_received": quantity_text(line.quantity_received),
            "quantity_accepted": quantity_text(line.quantity_accepted),
            "quantity_rejected": quantity_text(line.quantity_rejected),
            "remarks": line.remarks,
        }
        for line, purchase_line, item, unit in rows
    ]

    purchase = (
        db.query(Purchase)
        .filter(Purchase.id == receipt.purchase_id, Purchase.campus_id == campus_id)
        .first()
    )
    supplier_name = None
    if purchase:
        supplier_name = db.query(Supplier.name).filter(
            Supplier.id == purchase.supplier_id, Supplier.campus_id == campus_id
        ).scalar()

    names = user_names(db, [receipt.created_by, receipt.accepted_by])

    cancellation = None
    if receipt.status == "CANCELLED":
        row = (
            db.query(AuditLog, User.full_name)
            .outerjoin(User, User.id == AuditLog.user_id)
            .filter(
                AuditLog.campus_id == campus_id,
                AuditLog.entity_type == "GOODS_RECEIPT",
                AuditLog.entity_id == receipt.id,
                AuditLog.action == "CANCEL",
            )
            .order_by(AuditLog.id.desc())
            .first()
        )
        if row:
            log, cancelled_by_name = row
            cancellation = {
                "reason": (log.details or {}).get("reason"),
                "cancelled_by": log.user_id,
                "cancelled_by_name": cancelled_by_name,
                "cancelled_at": utc_iso(log.created_at),
            }

    movements = []
    if receipt.status == "ACCEPTED":
        movements = [
            {
                "id": movement.id,
                "receipt_item_id": movement.receipt_item_id,
                "item_name": item_name,
                "quantity": quantity_text(movement.quantity),
                "unit_symbol": unit_symbol,
            }
            for movement, item_name, unit_symbol in (
                db.query(StockMovement, Item.name, Unit.symbol)
                .outerjoin(Item, Item.id == StockMovement.item_id)
                .outerjoin(Unit, Unit.id == StockMovement.unit_id)
                .filter(
                    StockMovement.campus_id == campus_id,
                    StockMovement.reference_type == "GOODS_RECEIPT",
                    StockMovement.reference_id == receipt.id,
                )
                .order_by(StockMovement.id)
            )
        ]

    return {
        "id": receipt.id,
        "purchase_id": receipt.purchase_id,
        "invoice_number": purchase.invoice_number if purchase else None,
        "purchase_date": purchase.purchase_date.isoformat() if purchase else None,
        "supplier_id": purchase.supplier_id if purchase else None,
        "supplier_name": supplier_name,
        "receipt_date": receipt.receipt_date.isoformat(),
        "status": receipt.status,
        "remarks": receipt.remarks,
        "accepted_by": receipt.accepted_by,
        "accepted_by_name": names.get(receipt.accepted_by),
        "accepted_at": utc_iso(receipt.accepted_at) if receipt.accepted_at else None,
        "created_by": receipt.created_by,
        "created_by_name": names.get(receipt.created_by),
        "created_at": utc_iso(receipt.created_at),
        "cancellation": cancellation,
        "items": result,
        "stock_movements": movements,
    }


def user_names(db: Session, user_ids) -> dict[int, str]:
    ids = {user_id for user_id in user_ids if user_id}
    if not ids:
        return {}
    return dict(db.query(User.id, User.full_name).filter(User.id.in_(ids)).all())


# ============================================================
# CREATE GOODS RECEIPT
# Permission: inventory.create
# ============================================================

@router.post(
    "/api/purchases/{purchase_id}/receipts",
    status_code=status.HTTP_201_CREATED,
)
def create_receipt(
    purchase_id: int,
    payload: ReceiptCreate,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_any_permission("goods_receipt.create", "inventory.create")
    ),
):
    purchase = campus_purchase(db, user, purchase_id, lock=True)

    receipt_date = payload.receipt_date or campus_today()
    check_receipt_date(receipt_date)

    prepared = prepare_lines(db, user, purchase, payload.items)

    receipt = GoodsReceipt(
        campus_id=user.campus_id,
        purchase_id=purchase.id,
        receipt_date=receipt_date,
        status="DRAFT",
        remarks=payload.remarks,
        created_by=user.id,
    )

    try:
        db.add(receipt)
        db.flush()

        for line in prepared:
            db.add(
                GoodsReceiptItem(
                    campus_id=user.campus_id,
                    receipt_id=receipt.id,
                    **line,
                )
            )

        record_audit(
            db,
            user,
            "CREATE",
            "GOODS_RECEIPT",
            receipt.id,
            {
                "purchase_id": purchase.id,
                "invoice_number": purchase.invoice_number,
                "receipt_date": receipt_date.isoformat(),
                "item_count": len(prepared),
            },
        )

        db.commit()
        db.refresh(receipt)

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="Goods receipt could not be saved",
        )

    return jsonable_encoder(
        serialize_receipt(db, receipt)
    )


# ============================================================
# LIST PURCHASE RECEIPTS
# Permission: inventory.read
# ============================================================

@router.get("/api/purchases/{purchase_id}/receipts")
def list_purchase_receipts(
    purchase_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_any_permission("goods_receipt.read", "inventory.read")
    ),
):
    purchase = (
        db.query(Purchase)
        .filter(
            Purchase.id == purchase_id,
            Purchase.campus_id == user.campus_id,
        )
        .first()
    )

    if not purchase:
        raise HTTPException(
            status_code=404,
            detail="Purchase not found",
        )

    receipts = (
        db.query(GoodsReceipt)
        .filter(
            GoodsReceipt.purchase_id == purchase.id,
            GoodsReceipt.campus_id == user.campus_id,
        )
        .order_by(GoodsReceipt.id.desc())
        .all()
    )

    return jsonable_encoder([
        serialize_receipt(db, receipt)
        for receipt in receipts
    ])


# ============================================================
# LIST ALL RECEIPTS
# Permission: inventory.read
# ============================================================

@router.get("/api/receipts")
def list_receipts(
    status_filter: str | None = Query(default=None, alias="status"),
    supplier_id: int | None = Query(default=None, gt=0),
    purchase_id: int | None = Query(default=None, gt=0),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    search: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
    user: User = Depends(require_any_permission("goods_receipt.read", "inventory.read")),
):
    """Every goods receipt of the campus, newest first, with its bill and
    supplier. No prices: receipts are about quantities."""
    if status_filter is not None and status_filter not in RECEIPT_STATUSES:
        raise HTTPException(status_code=422, detail="Unknown receipt status.")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from cannot be after date_to.")

    campus_id = user.campus_id
    query = (
        db.query(GoodsReceipt, Purchase, Supplier.name)
        .join(
            Purchase,
            (Purchase.id == GoodsReceipt.purchase_id) & (Purchase.campus_id == campus_id),
        )
        .outerjoin(
            Supplier,
            (Supplier.id == Purchase.supplier_id) & (Supplier.campus_id == campus_id),
        )
        .filter(GoodsReceipt.campus_id == campus_id)
    )
    if supplier_id is not None:
        query = query.filter(Purchase.supplier_id == supplier_id)
    if purchase_id is not None:
        query = query.filter(GoodsReceipt.purchase_id == purchase_id)
    if date_from is not None:
        query = query.filter(GoodsReceipt.receipt_date >= date_from)
    if date_to is not None:
        query = query.filter(GoodsReceipt.receipt_date <= date_to)
    term = search.strip() if search else ""
    if term:
        query = query.filter(
            func.lower(Purchase.invoice_number).like(like_contains(term), escape="\\")
        )

    # Counts per status for the current filters (before the status filter).
    status_counts = {name: 0 for name in RECEIPT_STATUSES}
    for name, count in (
        query.with_entities(GoodsReceipt.status, func.count(GoodsReceipt.id))
        .group_by(GoodsReceipt.status)
    ):
        status_counts[name] = count

    if status_filter is not None:
        query = query.filter(GoodsReceipt.status == status_filter)

    total = query.count()
    rows = (
        query.order_by(GoodsReceipt.receipt_date.desc(), GoodsReceipt.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    receipt_ids = [receipt.id for receipt, _purchase, _name in rows]
    line_counts = dict(
        db.query(GoodsReceiptItem.receipt_id, func.count(GoodsReceiptItem.id))
        .filter(
            GoodsReceiptItem.campus_id == campus_id,
            GoodsReceiptItem.receipt_id.in_(receipt_ids or [0]),
        )
        .group_by(GoodsReceiptItem.receipt_id)
        .all()
    )
    names = user_names(
        db,
        [r.created_by for r, _p, _n in rows] + [r.accepted_by for r, _p, _n in rows],
    )

    return {
        "items": [
            {
                "id": receipt.id,
                "purchase_id": purchase.id,
                "invoice_number": purchase.invoice_number,
                "supplier_id": purchase.supplier_id,
                "supplier_name": supplier_name,
                "receipt_date": receipt.receipt_date.isoformat(),
                "status": receipt.status,
                "line_count": line_counts.get(receipt.id, 0),
                "remarks": receipt.remarks,
                "created_by_name": names.get(receipt.created_by),
                "created_at": utc_iso(receipt.created_at),
                "accepted_by_name": names.get(receipt.accepted_by),
                "accepted_at": utc_iso(receipt.accepted_at) if receipt.accepted_at else None,
            }
            for receipt, purchase, supplier_name in rows
        ],
        "status_counts": status_counts,
        **page_meta(total, page, page_size),
    }


def reserved_per_line_subquery(db: Session, campus_id: int):
    """Quantity each bill line has in draft or accepted receipts."""
    return (
        db.query(
            GoodsReceiptItem.purchase_item_id.label("purchase_item_id"),
            func.sum(GoodsReceiptItem.quantity_received).label("reserved"),
        )
        .join(GoodsReceipt, GoodsReceipt.id == GoodsReceiptItem.receipt_id)
        .filter(
            GoodsReceiptItem.campus_id == campus_id,
            GoodsReceipt.campus_id == campus_id,
            GoodsReceipt.status.in_(("DRAFT", "ACCEPTED")),
        )
        .group_by(GoodsReceiptItem.purchase_item_id)
        .subquery()
    )


# ============================================================
# BILLS WITH QUANTITY STILL TO RECEIVE
# Permission: inventory.create
# ============================================================

@router.get("/api/receipts/receivable-bills")
def list_receivable_bills(
    search: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
    user: User = Depends(require_any_permission("goods_receipt.create", "inventory.create")),
):
    """Bills with at least one line not yet fully received, for choosing
    the bill a delivery belongs to. Quantities only, no amounts."""
    campus_id = user.campus_id
    reserved = reserved_per_line_subquery(db, campus_id)
    open_bills = (
        db.query(
            PurchaseItem.purchase_id.label("purchase_id"),
            func.count(PurchaseItem.id).label("open_lines"),
        )
        .outerjoin(reserved, reserved.c.purchase_item_id == PurchaseItem.id)
        .join(Item, Item.id == PurchaseItem.item_id)
        .filter(
            PurchaseItem.campus_id == campus_id,
            PurchaseItem.quantity - func.coalesce(reserved.c.reserved, 0) > 0,
            # Outsourced food is received as outsourced deliveries (Stage 8a).
            not_outsourced(Item.item_kind),
        )
        .group_by(PurchaseItem.purchase_id)
        .subquery()
    )
    query = (
        db.query(Purchase, Supplier.name, open_bills.c.open_lines)
        .join(open_bills, open_bills.c.purchase_id == Purchase.id)
        .outerjoin(
            Supplier,
            (Supplier.id == Purchase.supplier_id) & (Supplier.campus_id == campus_id),
        )
        .filter(Purchase.campus_id == campus_id)
    )
    term = search.strip() if search else ""
    if term:
        pattern = like_contains(term)
        query = query.filter(
            or_(
                func.lower(Purchase.invoice_number).like(pattern, escape="\\"),
                func.lower(Supplier.name).like(pattern, escape="\\"),
            )
        )

    total = query.count()
    rows = (
        query.order_by(Purchase.purchase_date.desc(), Purchase.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    line_totals = dict(
        db.query(PurchaseItem.purchase_id, func.count(PurchaseItem.id))
        .filter(
            PurchaseItem.campus_id == campus_id,
            PurchaseItem.purchase_id.in_([p.id for p, _n, _o in rows] or [0]),
        )
        .group_by(PurchaseItem.purchase_id)
        .all()
    )
    return {
        "items": [
            {
                "purchase_id": purchase.id,
                "invoice_number": purchase.invoice_number,
                "supplier_id": purchase.supplier_id,
                "supplier_name": supplier_name,
                "purchase_date": purchase.purchase_date.isoformat(),
                "line_count": line_totals.get(purchase.id, 0),
                "open_line_count": open_lines,
            }
            for purchase, supplier_name, open_lines in rows
        ],
        **page_meta(total, page, page_size),
    }


# ============================================================
# A BILL'S RECEIVING PROGRESS
# Permission: inventory.read
# ============================================================

@router.get("/api/purchases/{purchase_id}/receiving")
def purchase_receiving(
    purchase_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_any_permission("goods_receipt.read", "inventory.read")),
):
    """Per bill line: ordered (when the line bills a purchase-order line,
    converted into the bill line's unit), billed, received, accepted,
    rejected, held in drafts and still to receive."""
    from app.api.routes.purchase_orders import Converter

    purchase = campus_purchase(db, user, purchase_id)
    campus_id = user.campus_id
    rows = (
        db.query(PurchaseItem, Item, Category.name, Unit)
        .outerjoin(Item, (Item.id == PurchaseItem.item_id) & (Item.campus_id == campus_id))
        .outerjoin(
            Category, (Category.id == Item.category_id) & (Category.campus_id == campus_id)
        )
        .outerjoin(Unit, (Unit.id == PurchaseItem.unit_id) & (Unit.campus_id == campus_id))
        .filter(PurchaseItem.purchase_id == purchase.id, PurchaseItem.campus_id == campus_id)
        .order_by(PurchaseItem.id)
        .all()
    )
    progress = receipt_progress(db, campus_id, [line.id for line, _i, _c, _u in rows])
    supplier_name = db.query(Supplier.name).filter(
        Supplier.id == purchase.supplier_id, Supplier.campus_id == campus_id
    ).scalar()

    # Purchase-order information (order number, ordered quantities) only
    # for users with order access: not through inventory permissions.
    from app.api.dependencies import user_has_permission
    show_orders = user_has_permission(db, user, "purchase_order.read")
    order_lines = {} if not show_orders else {
        order_line.id: order_line
        for order_line in db.query(PurchaseOrderItem).filter(
            PurchaseOrderItem.campus_id == campus_id,
            PurchaseOrderItem.id.in_(
                [line.purchase_order_item_id for line, _i, _c, _u in rows
                 if line.purchase_order_item_id] or [0]
            ),
        )
    }
    order_number = (
        db.query(PurchaseOrder.order_number).filter(
            PurchaseOrder.id == purchase.purchase_order_id,
            PurchaseOrder.campus_id == campus_id,
        ).scalar()
        if purchase.purchase_order_id and show_orders else None
    )
    convert = Converter(db, user)

    lines = []
    outsourced_lines = []
    for line, item, category_name, unit in rows:
        if item is not None and item.item_kind == "OUTSOURCED":
            # Stage 8a: received as outsourced deliveries, never into stock.
            outsourced_lines.append({
                "purchase_item_id": line.id,
                "item_id": line.item_id,
                "item_name": item.name,
                "unit_symbol": unit.symbol if unit else None,
                "billed_quantity": quantity_text(line.quantity),
            })
            continue
        held = progress[line.id]
        billed = Decimal(str(line.quantity))
        remaining = billed - held["received"] - held["in_draft"]
        ordered = None
        order_line = order_lines.get(line.purchase_order_item_id)
        if order_line is not None and item is not None:
            ordered = convert.convert(
                order_line.quantity, order_line.unit_id, line.unit_id, item.standard_unit_id
            )
        lines.append({
            "purchase_item_id": line.id,
            "purchase_order_item_id": line.purchase_order_item_id if show_orders else None,
            "ordered_quantity": quantity_text(ordered) if ordered is not None else None,
            "item_id": line.item_id,
            "item_name": item.name if item else None,
            "category_name": category_name,
            "unit_id": line.unit_id,
            "unit_symbol": unit.symbol if unit else None,
            "billed_quantity": quantity_text(billed),
            "received_quantity": quantity_text(held["received"]),
            "accepted_quantity": quantity_text(held["accepted"]),
            "rejected_quantity": quantity_text(held["rejected"]),
            "in_draft_quantity": quantity_text(held["in_draft"]),
            "remaining_quantity": quantity_text(max(remaining, ZERO)),
        })

    counts = {name: 0 for name in RECEIPT_STATUSES}
    for name, count in (
        db.query(GoodsReceipt.status, func.count(GoodsReceipt.id))
        .filter(GoodsReceipt.campus_id == campus_id, GoodsReceipt.purchase_id == purchase.id)
        .group_by(GoodsReceipt.status)
    ):
        counts[name] = count

    return {
        "purchase_id": purchase.id,
        "invoice_number": purchase.invoice_number,
        "supplier_id": purchase.supplier_id,
        "supplier_name": supplier_name,
        "purchase_date": purchase.purchase_date.isoformat(),
        "purchase_order_id": purchase.purchase_order_id if show_orders else None,
        "purchase_order_number": order_number,
        "lines": lines,
        # Outsourced food on the bill: not received through goods receipts.
        "outsourced_lines": outsourced_lines,
        "receipt_counts": counts,
        # Every billed quantity is in an accepted receipt (drafts do not count).
        "fully_received": bool(lines) and all(
            Decimal(line["received_quantity"]) >= Decimal(line["billed_quantity"])
            for line in lines
        ),
    }


# ============================================================
# GET RECEIPT DETAILS
# Permission: inventory.read
# ============================================================

@router.get("/api/receipts/{receipt_id}")
def get_receipt_detail(
    receipt_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_any_permission("goods_receipt.read", "inventory.read")
    ),
):
    receipt = get_receipt(
        receipt_id,
        db,
        user,
    )

    return jsonable_encoder(
        serialize_receipt(db, receipt)
    )


# ============================================================
# ACCEPT RECEIPT AND POST STOCK
# Permission: inventory.update
# ============================================================

@router.post("/api/receipts/{receipt_id}/accept")
def accept_receipt(
    receipt_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_any_permission("goods_receipt.update", "inventory.update")
    ),
):
    receipt = (
        db.query(GoodsReceipt)
        .filter(
            GoodsReceipt.id == receipt_id,
            GoodsReceipt.campus_id == user.campus_id,
        )
        .with_for_update()
        .first()
    )

    if not receipt:
        raise HTTPException(
            status_code=404,
            detail="Goods receipt not found",
        )

    if receipt.status != "DRAFT":
        raise HTTPException(
            status_code=409,
            detail="Only draft receipts can be accepted",
        )

    lines = (
        db.query(GoodsReceiptItem)
        .filter(
            GoodsReceiptItem.receipt_id == receipt.id,
            GoodsReceiptItem.campus_id == user.campus_id,
        )
        .order_by(GoodsReceiptItem.id)
        .all()
    )

    if not lines:
        raise HTTPException(
            status_code=422,
            detail="Receipt has no items",
        )

    # Stage 8a (P8-2): no outsourced item is ever received into stock. The
    # item rows are locked (in id order) so a classification cannot change
    # before this acceptance commits.
    refuse_outsourced(
        db,
        user.campus_id,
        [
            item_id
            for (item_id,) in db.query(PurchaseItem.item_id).filter(
                PurchaseItem.id.in_([line.purchase_item_id for line in lines]),
                PurchaseItem.campus_id == user.campus_id,
            )
        ],
        "received into stock",
        lock=True,
    )

    # Validate every line and conversion before adding
    # any stock movements.
    movements = []
    # One moment for the acceptance and its stock: the receipt movements are
    # effective when the receipt is accepted (Stage 4 ledger, M2a).
    accepted_at = datetime.now(timezone.utc)

    for line in lines:

        received = Decimal(str(line.quantity_received))
        accepted = Decimal(str(line.quantity_accepted))
        rejected = Decimal(str(line.quantity_rejected))

        if accepted + rejected != received:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Accepted and rejected quantities must equal "
                    f"received quantity for receipt item {line.id}"
                ),
            )

        purchase_line = (
            db.query(PurchaseItem)
            .filter(
                PurchaseItem.id == line.purchase_item_id,
                PurchaseItem.campus_id == user.campus_id,
                PurchaseItem.purchase_id == receipt.purchase_id,
            )
            .first()
        )

        if not purchase_line:
            raise HTTPException(
                status_code=404,
                detail="Related purchase item not found",
            )

        item = (
            db.query(Item)
            .filter(
                Item.id == purchase_line.item_id,
                Item.campus_id == user.campus_id,
            )
            .first()
        )

        if not item:
            raise HTTPException(
                status_code=404,
                detail="Related item not found",
            )

        standard_unit = (
            db.query(Unit)
            .filter(
                Unit.id == item.standard_unit_id,
                Unit.campus_id == user.campus_id,
            )
            .first()
        )

        purchase_unit = (
            db.query(Unit)
            .filter(
                Unit.id == purchase_line.unit_id,
                Unit.campus_id == user.campus_id,
            )
            .first()
        )

        if not standard_unit or not purchase_unit:
            raise HTTPException(
                status_code=422,
                detail=f"Valid units are required for item {item.name}",
            )

        if accepted > 0:

            factor = get_unit_conversion_factor(
                db,
                user,
                purchase_unit.id,
                standard_unit.id,
            )

            standard_quantity = quantity(
                accepted * factor
            )

            if standard_quantity <= 0:
                raise HTTPException(
                    status_code=422,
                    detail=f"Converted quantity is invalid for item {item.name}",
                )

            existing_movement = (
                db.query(StockMovement)
                .filter(
                    StockMovement.campus_id == user.campus_id,
                    StockMovement.receipt_item_id == line.id,
                )
                .first()
            )

            if existing_movement:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Stock was already posted for "
                        f"receipt item {line.id}"
                    ),
                )

            movements.append({
                "item_id": item.id,
                "movement_type": "RECEIPT",
                "direction": 1,
                "quantity": standard_quantity,
                "unit_id": standard_unit.id,
                "receipt_item_id": line.id,
                "reference_type": "GOODS_RECEIPT",
                "reference_id": receipt.id,
                "source_key": f"RECEIPT_ITEM:{line.id}",
                "effective_at": accepted_at,
                "remarks": line.remarks or receipt.remarks,
                "created_by": user.id,
            })

    try:
        for movement in movements:
            db.add(
                StockMovement(
                    campus_id=user.campus_id,
                    **movement,
                )
            )

        receipt.status = "ACCEPTED"
        receipt.accepted_by = user.id
        receipt.accepted_at = accepted_at

        record_audit(
            db,
            user,
            "ACCEPT",
            "GOODS_RECEIPT",
            receipt.id,
            {
                "stock_movement_count": len(movements),
                "accepted_item_count": len(movements),
            },
        )

        db.commit()
        db.refresh(receipt)

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail=(
                "Receipt stock was already posted or "
                "the receipt could not be accepted"
            ),
        )

    return jsonable_encoder(
        serialize_receipt(db, receipt)
    )


def lock_draft(db: Session, user: User, receipt_id: int) -> GoodsReceipt:
    receipt = (
        db.query(GoodsReceipt)
        .filter(GoodsReceipt.id == receipt_id, GoodsReceipt.campus_id == user.campus_id)
        .with_for_update()
        .first()
    )
    if not receipt:
        raise HTTPException(status_code=404, detail="Goods receipt not found")
    if receipt.status != "DRAFT":
        raise HTTPException(
            status_code=409, detail="Only draft receipts can be changed or cancelled"
        )
    return receipt


def line_snapshot(lines) -> list[dict]:
    return [
        {
            "purchase_item_id": line.purchase_item_id,
            "quantity_received": quantity_text(line.quantity_received),
            "quantity_accepted": quantity_text(line.quantity_accepted),
            "quantity_rejected": quantity_text(line.quantity_rejected),
        }
        for line in lines
    ]


# ============================================================
# CORRECT A DRAFT RECEIPT
# Permission: inventory.update
# ============================================================

@router.put("/api/receipts/{receipt_id}")
def update_draft_receipt(
    receipt_id: int,
    payload: ReceiptUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_any_permission("goods_receipt.update", "inventory.update")),
):
    """Drafts post no stock, so their quantities may be corrected (for
    example, after inspecting a delivery) before acceptance. The change and
    the previous values are audited."""
    # Lock order is bill, then receipt: the same as receipt entry.
    purchase_id = db.query(GoodsReceipt.purchase_id).filter(
        GoodsReceipt.id == receipt_id, GoodsReceipt.campus_id == user.campus_id
    ).scalar()
    if purchase_id is None:
        raise HTTPException(status_code=404, detail="Goods receipt not found")
    purchase = campus_purchase(db, user, purchase_id, lock=True)
    receipt = lock_draft(db, user, receipt_id)

    receipt_date = payload.receipt_date or receipt.receipt_date
    check_receipt_date(receipt_date)
    prepared = prepare_lines(db, user, purchase, payload.items, exclude_receipt_id=receipt.id)

    existing = {
        line.purchase_item_id: line
        for line in db.query(GoodsReceiptItem)
        .filter(
            GoodsReceiptItem.receipt_id == receipt.id,
            GoodsReceiptItem.campus_id == user.campus_id,
        )
        .order_by(GoodsReceiptItem.id)
    }
    before = line_snapshot(existing.values())

    for values in prepared:
        line = existing.pop(values["purchase_item_id"], None)
        if line is None:
            db.add(GoodsReceiptItem(campus_id=user.campus_id, receipt_id=receipt.id, **values))
        else:
            for key, value in values.items():
                setattr(line, key, value)
    for removed in existing.values():
        # A draft line never posted stock, so removing it loses nothing;
        # its values stay in the audit row below.
        db.delete(removed)

    receipt.receipt_date = receipt_date
    receipt.remarks = payload.remarks
    db.flush()

    record_audit(
        db,
        user,
        "UPDATE",
        "GOODS_RECEIPT",
        receipt.id,
        {
            "purchase_id": purchase.id,
            "receipt_date": receipt_date.isoformat(),
            "before": before,
            "after": [
                {key: (quantity_text(v) if key.startswith("quantity") else v)
                 for key, v in values.items() if key != "remarks"}
                for values in prepared
            ],
        },
    )
    db.commit()
    db.refresh(receipt)
    return jsonable_encoder(serialize_receipt(db, receipt))


# ============================================================
# CANCEL A DRAFT RECEIPT
# Permission: inventory.update
# ============================================================

@router.post("/api/receipts/{receipt_id}/cancel")
def cancel_draft_receipt(
    receipt_id: int,
    payload: ReceiptCancel,
    db: Session = Depends(get_db),
    user: User = Depends(require_any_permission("goods_receipt.update", "inventory.update")),
):
    """Withdraw a draft entered by mistake. The receipt is kept with status
    CANCELLED, frees the quantity it reserved and never affects stock."""
    receipt = lock_draft(db, user, receipt_id)
    lines = (
        db.query(GoodsReceiptItem)
        .filter(
            GoodsReceiptItem.receipt_id == receipt.id,
            GoodsReceiptItem.campus_id == user.campus_id,
        )
        .order_by(GoodsReceiptItem.id)
        .all()
    )
    receipt.status = "CANCELLED"
    record_audit(
        db,
        user,
        "CANCEL",
        "GOODS_RECEIPT",
        receipt.id,
        {
            "purchase_id": receipt.purchase_id,
            "reason": payload.reason,
            "lines": line_snapshot(lines),
        },
    )
    db.commit()
    db.refresh(receipt)
    return jsonable_encoder(serialize_receipt(db, receipt))


# ============================================================
# STOCK MOVEMENT LOG (paginated)
# Permission: inventory.read
# ============================================================

@router.get("/api/stock-movements")
def stock_movement_log(
    item_id: int | None = Query(default=None, gt=0),
    movement_type: str | None = Query(default=None, max_length=30),
    receipt_id: int | None = Query(default=None, gt=0),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
    user: User = Depends(require_any_permission("goods_receipt.read", "inventory.read")),
):
    """Stock movements with item, unit, source and recorder, newest first.
    Dates are campus-local days."""
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from cannot be after date_to.")

    campus_id = user.campus_id
    query = (
        db.query(StockMovement, Item.name, Unit.symbol, User.full_name)
        .outerjoin(Item, (Item.id == StockMovement.item_id) & (Item.campus_id == campus_id))
        .outerjoin(Unit, (Unit.id == StockMovement.unit_id) & (Unit.campus_id == campus_id))
        .outerjoin(User, User.id == StockMovement.created_by)
        .filter(StockMovement.campus_id == campus_id)
    )
    if item_id is not None:
        query = query.filter(StockMovement.item_id == item_id)
    if movement_type:
        query = query.filter(StockMovement.movement_type == movement_type.upper())
    if receipt_id is not None:
        query = query.filter(
            StockMovement.reference_type == "GOODS_RECEIPT",
            StockMovement.reference_id == receipt_id,
        )
    zone = campus_timezone()
    if date_from is not None:
        start = datetime.combine(date_from, time.min, tzinfo=zone).astimezone(timezone.utc)
        query = query.filter(StockMovement.created_at >= start)
    if date_to is not None:
        end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=zone).astimezone(timezone.utc)
        query = query.filter(StockMovement.created_at < end)

    total = query.count()
    rows = (
        query.order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    receipt_ids = {
        movement.reference_id for movement, _i, _u, _n in rows
        if movement.reference_type == "GOODS_RECEIPT"
    }
    sources = {
        receipt_id_: (invoice, supplier_name)
        for receipt_id_, invoice, supplier_name in (
            db.query(GoodsReceipt.id, Purchase.invoice_number, Supplier.name)
            .join(Purchase, Purchase.id == GoodsReceipt.purchase_id)
            .outerjoin(Supplier, Supplier.id == Purchase.supplier_id)
            .filter(GoodsReceipt.campus_id == campus_id, GoodsReceipt.id.in_(receipt_ids or {0}))
        )
    }

    # Which of these movements were reversed, and by which movement.
    reversed_by = {
        original_id: reversal_id
        for reversal_id, original_id in db.query(StockMovement.id, StockMovement.reversal_of_id).filter(
            StockMovement.campus_id == campus_id,
            StockMovement.reversal_of_id.in_([m.id for m, _i, _u, _n in rows] or [0]),
        )
    }

    from app.services.stock_ledger import movement_documents
    documents = movement_documents(db, campus_id, [m for m, _i, _u, _n in rows])

    items = []
    for movement, item_name, unit_symbol, created_by_name in rows:
        source = sources.get(movement.reference_id) if movement.reference_type == "GOODS_RECEIPT" else None
        document = documents.get((movement.reference_type, movement.reference_id))
        items.append({
            "id": movement.id,
            "created_at": utc_iso(movement.created_at),
            "effective_at": utc_iso(movement.effective_at),
            "item_id": movement.item_id,
            "item_name": item_name,
            "movement_type": movement.movement_type,
            "direction": movement.direction,
            "quantity": quantity_text(movement.quantity),
            "unit_symbol": unit_symbol,
            "reference_type": movement.reference_type,
            "reference_id": movement.reference_id,
            "source_key": movement.source_key,
            "receipt_id": movement.reference_id if movement.reference_type == "GOODS_RECEIPT" else None,
            "opening_id": movement.reference_id if movement.reference_type == "STOCK_OPENING" else None,
            "document_number": document[0] if document else None,
            "kitchen_issue_id": document[1] if document else None,
            "stock_count_id": document[2] if document else None,
            "invoice_number": source[0] if source else None,
            "supplier_name": source[1] if source else None,
            "reversal_of_id": movement.reversal_of_id,
            "reversed_by_movement_id": reversed_by.get(movement.id),
            "remarks": movement.remarks,
            "created_by_name": created_by_name,
        })
    return {"items": items, **page_meta(total, page, page_size)}


# ============================================================
# LIST STOCK MOVEMENTS
# Permission: inventory.read
# ============================================================

@router.get("/api/stock/movements")
def list_stock_movements(
    db: Session = Depends(get_db),
    user: User = Depends(
        require_any_permission("goods_receipt.read", "inventory.read")
    ),
):
    movements = (
        db.query(StockMovement)
        .filter(
            StockMovement.campus_id == user.campus_id
        )
        .order_by(
            StockMovement.created_at.desc(),
            StockMovement.id.desc(),
        )
        .all()
    )

    return jsonable_encoder([
        {
            "id": movement.id,
            "item_id": movement.item_id,
            "movement_type": movement.movement_type,
            "direction": movement.direction,
            "quantity": movement.quantity,
            "unit_id": movement.unit_id,
            "receipt_item_id": movement.receipt_item_id,
            "reference_type": movement.reference_type,
            "reference_id": movement.reference_id,
            "source_key": movement.source_key,
            "reversal_of_id": movement.reversal_of_id,
            "remarks": movement.remarks,
            "created_by": movement.created_by,
            "created_at": movement.created_at,
            "effective_at": movement.effective_at,
        }
        for movement in movements
    ])
