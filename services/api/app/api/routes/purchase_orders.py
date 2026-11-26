"""Purchase orders (Stage 3).

What was ordered from a supplier: items, quantities and units. Prices are
not kept here; they come from the supplier's bill.

Rules approved 18 November 2026:
- purchase_order.read to view, purchase_order.create to create a draft,
  purchase_order.update to edit a draft, place, close or cancel.
  ADMIN and KITCHEN_MANAGER hold all three; STAFF only by an existing
  explicit grant (the codes are not on the STAFF-assignable list).
- No approval step: the client has not said who approves purchases.
  Status changes go through PURCHASE_ORDER_TRANSITIONS so that an approval
  step can be added later without changing the rest.
- Only DRAFT orders are edited. A PLACED order may be billed against;
  bills may exceed the ordered quantity (recorded as the supplier issued
  them) and the excess is shown, not blocked.
- Receipts stay recorded against bills. An order's progress (billed,
  received, accepted, rejected, in drafts, left) is worked out from the
  bill lines linked to its lines, converted into the order line's unit.
- Every change is audited (entity PURCHASE_ORDER).
"""

from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.api.dependencies import require_permission, user_has_permission
from app.api.routes.master_data import get_unit_conversion_factor, record_audit
from app.core.clock import campus_today, utc_iso
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.campus import Campus
from app.models.master_data import Category, Item, Supplier, Unit
from app.models.purchases import (
    GoodsReceipt,
    GoodsReceiptItem,
    Purchase,
    PurchaseItem,
    PurchaseOrder,
    PurchaseOrderItem,
    PURCHASE_ORDER_STATUSES,
)
from app.models.user import User

router = APIRouter(prefix="/api/purchase-orders", tags=["Purchase Orders"])

QUANTITY_STEP = Decimal("0.001")
ZERO = Decimal("0")
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# action → (statuses it may start from, status it leads to). An approval
# step would add, for example, "submit": ({"DRAFT"}, "PENDING_APPROVAL") and
# "approve": ({"PENDING_APPROVAL"}, "APPROVED"), and "place" would start
# from APPROVED. Nothing else here would need to change.
PURCHASE_ORDER_TRANSITIONS = {
    "place": ({"DRAFT"}, "PLACED"),
    "close": ({"PLACED"}, "CLOSED"),
    "cancel": ({"DRAFT", "PLACED"}, "CANCELLED"),
}
EDITABLE_STATUSES = {"DRAFT"}
BILLABLE_STATUSES = {"PLACED"}


def quantity(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(QUANTITY_STEP, rounding=ROUND_HALF_UP)


def quantity_text(value) -> str:
    return format(quantity(value), "f")


def page_meta(total: int, page: int, page_size: int) -> dict:
    return {"total": total, "page": page, "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size}


def like_contains(term: str) -> str:
    escaped = term.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


# ============================================================
# REQUEST SCHEMAS
# ============================================================

class OrderLineInput(BaseModel):
    item_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    unit_id: int = Field(gt=0)
    remarks: str | None = Field(default=None, max_length=500)

    @field_validator("remarks")
    @classmethod
    def blank_to_none(cls, value):
        return value.strip() or None if value else None


class OrderInput(BaseModel):
    supplier_id: int = Field(gt=0)
    order_date: date
    expected_date: date | None = None
    remarks: str | None = Field(default=None, max_length=1000)
    items: list[OrderLineInput] = Field(min_length=1, max_length=200)

    @field_validator("remarks")
    @classmethod
    def blank_to_none(cls, value):
        return value.strip() or None if value else None


class ReasonInput(BaseModel):
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Give a reason.")
        return value


# ============================================================
# VALIDATION
# ============================================================

def active_supplier(db: Session, user: User, supplier_id: int) -> Supplier:
    supplier = db.query(Supplier).filter(
        Supplier.id == supplier_id,
        Supplier.campus_id == user.campus_id,
        Supplier.is_active.is_(True),
    ).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Active supplier not found in your campus")
    return supplier


def resolve_line(db: Session, user: User, item_id: int, unit_id: int) -> tuple[Item, Unit]:
    """The same item and unit rules as bill entry: an active item and unit
    of the campus, of the item's dimension, with a conversion to the item's
    standard unit."""
    item = db.query(Item).filter(
        Item.id == item_id, Item.campus_id == user.campus_id, Item.is_active.is_(True)
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail=f"Active item {item_id} not found in your campus")
    unit = db.query(Unit).filter(
        Unit.id == unit_id, Unit.campus_id == user.campus_id, Unit.is_active.is_(True)
    ).first()
    if not unit:
        raise HTTPException(status_code=404, detail=f"Active unit {unit_id} not found in your campus")
    standard = db.query(Unit).filter(
        Unit.id == item.standard_unit_id, Unit.campus_id == user.campus_id, Unit.is_active.is_(True)
    ).first()
    if not standard:
        raise HTTPException(status_code=422, detail=f"Item {item.name} has no valid active standard unit")
    if unit.dimension != standard.dimension:
        raise HTTPException(status_code=422, detail=f"Unit dimension mismatch for item {item.name}")
    get_unit_conversion_factor(db, user, unit.id, standard.id)
    return item, unit


def prepare_order(db: Session, user: User, payload: OrderInput) -> list[dict]:
    active_supplier(db, user, payload.supplier_id)
    if payload.order_date > campus_today():
        raise HTTPException(status_code=422, detail="An order cannot be dated in the future.")
    if payload.expected_date and payload.expected_date < payload.order_date:
        raise HTTPException(
            status_code=422, detail="The expected delivery date cannot be before the order date."
        )
    item_ids = [line.item_id for line in payload.items]
    if len(item_ids) != len(set(item_ids)):
        raise HTTPException(status_code=422, detail="An item can appear only once in an order.")
    prepared = []
    for line in payload.items:
        item, unit = resolve_line(db, user, line.item_id, line.unit_id)
        prepared.append({
            "item_id": item.id,
            "quantity": quantity(line.quantity),
            "unit_id": unit.id,
            "remarks": line.remarks,
        })
    return prepared


def campus_order(db: Session, user: User, order_id: int, lock: bool = False) -> PurchaseOrder:
    query = db.query(PurchaseOrder).filter(
        PurchaseOrder.id == order_id, PurchaseOrder.campus_id == user.campus_id
    )
    if lock:
        query = query.with_for_update()
    order = query.first()
    if not order:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    return order


def next_order_number(db: Session, campus_id: int) -> tuple[int, str]:
    """PO-00001, PO-00002, … per campus. The campus row is locked so two
    orders saved at the same moment cannot take the same number."""
    db.query(Campus).filter(Campus.id == campus_id).with_for_update().one()
    last = db.query(func.max(PurchaseOrder.order_seq)).filter(
        PurchaseOrder.campus_id == campus_id
    ).scalar() or 0
    seq = last + 1
    return seq, f"PO-{seq:05d}"


def order_lines(db: Session, order: PurchaseOrder) -> list[PurchaseOrderItem]:
    return db.query(PurchaseOrderItem).filter(
        PurchaseOrderItem.purchase_order_id == order.id,
        PurchaseOrderItem.campus_id == order.campus_id,
    ).order_by(PurchaseOrderItem.id).all()


def line_snapshot(lines) -> list[dict]:
    return [{"item_id": line.item_id, "quantity": quantity_text(line.quantity),
             "unit_id": line.unit_id} for line in lines]


# ============================================================
# PROGRESS: what has been billed and received against each order line
# ============================================================

class Converter:
    """Converts a quantity between two units of one item through the item's
    standard unit, using the campus's explicit conversions."""

    def __init__(self, db: Session, user: User):
        self.db, self.user, self.cache = db, user, {}

    def to_standard(self, unit_id: int, standard_id: int) -> Decimal:
        key = (unit_id, standard_id)
        if key not in self.cache:
            try:
                self.cache[key] = get_unit_conversion_factor(self.db, self.user, unit_id, standard_id)
            except HTTPException:
                self.cache[key] = None
        return self.cache[key]

    def convert(self, value, from_unit: int, to_unit: int, standard_id: int) -> Decimal | None:
        if from_unit == to_unit:
            return Decimal(str(value))
        a = self.to_standard(from_unit, standard_id)
        b = self.to_standard(to_unit, standard_id)
        if a is None or b is None or b == 0:
            return None
        return Decimal(str(value)) * a / b


def progress_for(db: Session, user: User, lines: list[PurchaseOrderItem]) -> dict[int, dict]:
    """Per order line, in the order line's unit: billed, received (accepted
    receipts), accepted, rejected, held in draft receipts, left to bill,
    left to receive, and any excess over the ordered quantity."""
    progress = {
        line.id: {"billed": ZERO, "received": ZERO, "accepted": ZERO, "rejected": ZERO,
                  "in_draft": ZERO, "unconvertible": False}
        for line in lines
    }
    if not lines:
        return progress
    by_id = {line.id: line for line in lines}
    standards = dict(db.query(Item.id, Item.standard_unit_id).filter(
        Item.id.in_({line.item_id for line in lines})
    ).all())
    convert = Converter(db, user)

    bill_lines = db.query(PurchaseItem).filter(
        PurchaseItem.campus_id == user.campus_id,
        PurchaseItem.purchase_order_item_id.in_(list(by_id)),
    ).all()
    bill_line_owner = {}
    for bill_line in bill_lines:
        order_line = by_id[bill_line.purchase_order_item_id]
        bill_line_owner[bill_line.id] = bill_line
        amount = convert.convert(bill_line.quantity, bill_line.unit_id, order_line.unit_id,
                                 standards.get(order_line.item_id))
        entry = progress[order_line.id]
        if amount is None:
            entry["unconvertible"] = True
        else:
            entry["billed"] += amount

    if bill_line_owner:
        sums = (
            db.query(
                GoodsReceiptItem.purchase_item_id,
                GoodsReceipt.status,
                func.sum(GoodsReceiptItem.quantity_received),
                func.sum(GoodsReceiptItem.quantity_accepted),
                func.sum(GoodsReceiptItem.quantity_rejected),
            )
            .join(GoodsReceipt, GoodsReceipt.id == GoodsReceiptItem.receipt_id)
            .filter(
                GoodsReceiptItem.campus_id == user.campus_id,
                GoodsReceipt.campus_id == user.campus_id,
                GoodsReceiptItem.purchase_item_id.in_(list(bill_line_owner)),
                GoodsReceipt.status.in_(("DRAFT", "ACCEPTED")),
            )
            .group_by(GoodsReceiptItem.purchase_item_id, GoodsReceipt.status)
        )
        for bill_line_id, receipt_status, received, accepted, rejected in sums:
            bill_line = bill_line_owner[bill_line_id]
            order_line = by_id[bill_line.purchase_order_item_id]
            entry = progress[order_line.id]

            def to_order_unit(value):
                return convert.convert(value or 0, bill_line.unit_id, order_line.unit_id,
                                       standards.get(order_line.item_id))

            values = [to_order_unit(v) for v in (received, accepted, rejected)]
            if any(v is None for v in values):
                entry["unconvertible"] = True
                continue
            if receipt_status == "ACCEPTED":
                entry["received"] += values[0]
                entry["accepted"] += values[1]
                entry["rejected"] += values[2]
            else:
                entry["in_draft"] += values[0]

    for line in lines:
        entry = progress[line.id]
        for key in ("billed", "received", "accepted", "rejected", "in_draft"):
            entry[key] = quantity(entry[key])
        ordered = quantity(line.quantity)
        entry["ordered"] = ordered
        entry["left_to_bill"] = max(ordered - entry["billed"], ZERO)
        entry["over_billed"] = max(entry["billed"] - ordered, ZERO)
        entry["left_to_receive"] = max(ordered - entry["received"] - entry["in_draft"], ZERO)
        entry["over_received"] = max(entry["received"] - ordered, ZERO)
    return progress


def receiving_state(lines, progress) -> str:
    if not lines:
        return "NOT_RECEIVED"
    if all(progress[line.id]["received"] >= progress[line.id]["ordered"] for line in lines):
        return "RECEIVED"
    if any(progress[line.id]["received"] > 0 for line in lines):
        return "PARTLY_RECEIVED"
    return "NOT_RECEIVED"


# ============================================================
# SERIALIZATION
# ============================================================

def user_names(db: Session, ids) -> dict[int, str]:
    ids = {i for i in ids if i}
    return dict(db.query(User.id, User.full_name).filter(User.id.in_(ids)).all()) if ids else {}


def linked_bills(db: Session, order: PurchaseOrder) -> list[Purchase]:
    return db.query(Purchase).filter(
        Purchase.campus_id == order.campus_id, Purchase.purchase_order_id == order.id
    ).order_by(Purchase.purchase_date, Purchase.id).all()


def allowed_actions(order: PurchaseOrder, bill_count: int) -> dict:
    def can(action):
        return order.status in PURCHASE_ORDER_TRANSITIONS[action][0]

    return {
        "edit": order.status in EDITABLE_STATUSES,
        "place": can("place"),
        "close": can("close"),
        # An order with bills against it is closed, not cancelled.
        "cancel": can("cancel") and bill_count == 0,
        "bill": order.status in BILLABLE_STATUSES,
    }


def serialize_order(db: Session, user: User, order: PurchaseOrder, detail: bool = False,
                    supplier_name: str | None = None) -> dict:
    lines = order_lines(db, order)
    progress = progress_for(db, user, lines)
    bills = linked_bills(db, order)
    if supplier_name is None:
        supplier_name = db.query(Supplier.name).filter(
            Supplier.id == order.supplier_id, Supplier.campus_id == order.campus_id
        ).scalar()
    names = user_names(db, [order.created_by, order.placed_by, order.closed_by, order.cancelled_by])
    result = {
        "id": order.id,
        "order_number": order.order_number,
        "supplier_id": order.supplier_id,
        "supplier_name": supplier_name,
        "order_date": order.order_date.isoformat(),
        "expected_date": order.expected_date.isoformat() if order.expected_date else None,
        "status": order.status,
        "remarks": order.remarks,
        "line_count": len(lines),
        "bill_count": len(bills),
        "receiving_state": receiving_state(lines, progress),
        "over_billed": any(progress[l.id]["over_billed"] > 0 for l in lines),
        "created_by": order.created_by,
        "created_by_name": names.get(order.created_by),
        "created_at": utc_iso(order.created_at),
        "updated_at": utc_iso(order.updated_at) if order.updated_at else None,
        "placed_by_name": names.get(order.placed_by),
        "placed_at": utc_iso(order.placed_at) if order.placed_at else None,
        "closed_by_name": names.get(order.closed_by),
        "closed_at": utc_iso(order.closed_at) if order.closed_at else None,
        "close_reason": order.close_reason,
        "cancelled_by_name": names.get(order.cancelled_by),
        "cancelled_at": utc_iso(order.cancelled_at) if order.cancelled_at else None,
        "cancel_reason": order.cancel_reason,
        "actions": allowed_actions(order, len(bills)),
    }
    if not detail:
        return result

    rows = {
        line_id: (item_name, category_name, unit_symbol)
        for line_id, item_name, category_name, unit_symbol in (
            db.query(PurchaseOrderItem.id, Item.name, Category.name, Unit.symbol)
            .outerjoin(Item, Item.id == PurchaseOrderItem.item_id)
            .outerjoin(Category, Category.id == Item.category_id)
            .outerjoin(Unit, Unit.id == PurchaseOrderItem.unit_id)
            .filter(PurchaseOrderItem.purchase_order_id == order.id)
        )
    }
    result["items"] = []
    for line in lines:
        item_name, category_name, unit_symbol = rows.get(line.id, (None, None, None))
        entry = progress[line.id]
        result["items"].append({
            "id": line.id,
            "item_id": line.item_id,
            "item_name": item_name,
            "category_name": category_name,
            "unit_id": line.unit_id,
            "unit_symbol": unit_symbol,
            "remarks": line.remarks,
            "ordered_quantity": quantity_text(entry["ordered"]),
            "billed_quantity": quantity_text(entry["billed"]),
            "received_quantity": quantity_text(entry["received"]),
            "accepted_quantity": quantity_text(entry["accepted"]),
            "rejected_quantity": quantity_text(entry["rejected"]),
            "in_draft_quantity": quantity_text(entry["in_draft"]),
            "left_to_bill": quantity_text(entry["left_to_bill"]),
            "left_to_receive": quantity_text(entry["left_to_receive"]),
            "over_billed": quantity_text(entry["over_billed"]),
            "over_received": quantity_text(entry["over_received"]),
            "unconvertible": entry["unconvertible"],
        })

    # Bills entered against the order: invoice and date only (amounts need
    # supplier-bill access).
    result["bills"] = [
        {"purchase_id": bill.id, "invoice_number": bill.invoice_number,
         "purchase_date": bill.purchase_date.isoformat()}
        for bill in bills
    ]
    history = (
        db.query(AuditLog, User.full_name)
        .outerjoin(User, User.id == AuditLog.user_id)
        .filter(AuditLog.campus_id == order.campus_id, AuditLog.entity_type == "PURCHASE_ORDER",
                AuditLog.entity_id == order.id)
        .order_by(AuditLog.created_at, AuditLog.id)
        .all()
    )
    result["history"] = [
        {"action": log.action, "user_name": name or "System", "at": utc_iso(log.created_at),
         "reason": (log.details or {}).get("reason")}
        for log, name in history
    ]
    return result


# ============================================================
# LIST
# Permission: purchase_order.read
# ============================================================

@router.get("")
def list_orders(
    status_filter: str | None = Query(default=None, alias="status"),
    supplier_id: int | None = Query(default=None, gt=0),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    search: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("purchase_order.read")),
):
    if status_filter is not None and status_filter not in PURCHASE_ORDER_STATUSES:
        raise HTTPException(status_code=422, detail="Unknown purchase order status.")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from cannot be after date_to.")

    query = (
        db.query(PurchaseOrder, Supplier.name)
        .outerjoin(Supplier, (Supplier.id == PurchaseOrder.supplier_id)
                   & (Supplier.campus_id == user.campus_id))
        .filter(PurchaseOrder.campus_id == user.campus_id)
    )
    if supplier_id is not None:
        query = query.filter(PurchaseOrder.supplier_id == supplier_id)
    if date_from is not None:
        query = query.filter(PurchaseOrder.order_date >= date_from)
    if date_to is not None:
        query = query.filter(PurchaseOrder.order_date <= date_to)
    term = search.strip() if search else ""
    if term:
        pattern = like_contains(term)
        query = query.filter(or_(
            func.lower(PurchaseOrder.order_number).like(pattern, escape="\\"),
            func.lower(Supplier.name).like(pattern, escape="\\"),
        ))

    status_counts = {name: 0 for name in PURCHASE_ORDER_STATUSES}
    for name, count in (query.with_entities(PurchaseOrder.status, func.count(PurchaseOrder.id))
                        .group_by(PurchaseOrder.status)):
        status_counts[name] = count

    if status_filter is not None:
        query = query.filter(PurchaseOrder.status == status_filter)
    total = query.count()
    rows = (query.order_by(PurchaseOrder.order_date.desc(), PurchaseOrder.id.desc())
            .offset((page - 1) * page_size).limit(page_size).all())
    return {
        "items": [serialize_order(db, user, order, supplier_name=name) for order, name in rows],
        "status_counts": status_counts,
        **page_meta(total, page, page_size),
    }


# ============================================================
# ORDERS A BILL MAY BE ENTERED AGAINST
# Permission: purchase_bill.create (entering a bill)
# ============================================================

@router.get("/billable")
def billable_orders(
    supplier_id: int = Query(..., gt=0),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("purchase_bill.create")),
):
    """Placed orders of one supplier, with what is left to bill per line,
    for linking a new bill. Quantities only. Listing orders also needs
    order access, so STAFF (who never have it) cannot read orders here."""
    if not user_has_permission(db, user, "purchase_order.read"):
        raise HTTPException(
            status_code=403,
            detail="Purchase orders are handled by Admins and Kitchen Managers only.",
        )
    orders = (
        db.query(PurchaseOrder)
        .filter(PurchaseOrder.campus_id == user.campus_id,
                PurchaseOrder.supplier_id == supplier_id,
                PurchaseOrder.status.in_(BILLABLE_STATUSES))
        .order_by(PurchaseOrder.order_date.desc(), PurchaseOrder.id.desc())
        .all()
    )
    result = []
    for order in orders:
        detail = serialize_order(db, user, order, detail=True)
        result.append({
            "id": order.id,
            "order_number": order.order_number,
            "order_date": detail["order_date"],
            "expected_date": detail["expected_date"],
            "items": [
                {key: line[key] for key in (
                    "id", "item_id", "item_name", "unit_id", "unit_symbol",
                    "ordered_quantity", "billed_quantity", "left_to_bill")}
                for line in detail["items"]
            ],
        })
    return {"items": result}


# ============================================================
# CREATE
# Permission: purchase_order.create
# ============================================================

@router.post("", status_code=status.HTTP_201_CREATED)
def create_order(
    payload: OrderInput,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("purchase_order.create")),
):
    prepared = prepare_order(db, user, payload)
    seq, number = next_order_number(db, user.campus_id)
    order = PurchaseOrder(
        campus_id=user.campus_id, order_seq=seq, order_number=number,
        supplier_id=payload.supplier_id, order_date=payload.order_date,
        expected_date=payload.expected_date, status="DRAFT",
        remarks=payload.remarks, created_by=user.id,
    )
    db.add(order)
    db.flush()
    for line in prepared:
        db.add(PurchaseOrderItem(campus_id=user.campus_id, purchase_order_id=order.id, **line))
    db.flush()
    record_audit(db, user, "CREATE", "PURCHASE_ORDER", order.id, {
        "order_number": number, "supplier_id": payload.supplier_id,
        "order_date": payload.order_date.isoformat(), "lines": line_snapshot(order_lines(db, order)),
    })
    db.commit()
    db.refresh(order)
    return serialize_order(db, user, order, detail=True)


# ============================================================
# DETAIL
# Permission: purchase_order.read
# ============================================================

@router.get("/{order_id}")
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("purchase_order.read")),
):
    return serialize_order(db, user, campus_order(db, user, order_id), detail=True)


# ============================================================
# EDIT A DRAFT
# Permission: purchase_order.update
# ============================================================

@router.put("/{order_id}")
def update_order(
    order_id: int,
    payload: OrderInput,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("purchase_order.update")),
):
    order = campus_order(db, user, order_id, lock=True)
    if order.status not in EDITABLE_STATUSES:
        raise HTTPException(status_code=409, detail="Only draft orders can be edited.")
    prepared = prepare_order(db, user, payload)

    existing = {line.item_id: line for line in order_lines(db, order)}
    before = line_snapshot(existing.values())
    before_header = {"supplier_id": order.supplier_id, "order_date": order.order_date.isoformat(),
                     "expected_date": order.expected_date.isoformat() if order.expected_date else None}
    for values in prepared:
        line = existing.pop(values["item_id"], None)
        if line is None:
            db.add(PurchaseOrderItem(campus_id=user.campus_id, purchase_order_id=order.id, **values))
        else:
            for key, value in values.items():
                setattr(line, key, value)
    for removed in existing.values():
        # A draft line was never billed against (only placed orders are).
        db.delete(removed)

    order.supplier_id = payload.supplier_id
    order.order_date = payload.order_date
    order.expected_date = payload.expected_date
    order.remarks = payload.remarks
    order.updated_at = datetime.now(timezone.utc)
    db.flush()
    record_audit(db, user, "UPDATE", "PURCHASE_ORDER", order.id, {
        "order_number": order.order_number,
        "before": {**before_header, "lines": before},
        "after": {"supplier_id": order.supplier_id, "order_date": order.order_date.isoformat(),
                  "expected_date": order.expected_date.isoformat() if order.expected_date else None,
                  "lines": line_snapshot(order_lines(db, order))},
    })
    db.commit()
    db.refresh(order)
    return serialize_order(db, user, order, detail=True)


# ============================================================
# STATUS CHANGES
# Permission: purchase_order.update
# ============================================================

def transition(db: Session, user: User, order_id: int, action: str) -> PurchaseOrder:
    order = campus_order(db, user, order_id, lock=True)
    allowed_from, _target = PURCHASE_ORDER_TRANSITIONS[action]
    if order.status not in allowed_from:
        raise HTTPException(
            status_code=409,
            detail=f"A {order.status.lower()} order cannot be {action}d."
            if action != "cancel" else f"A {order.status.lower()} order cannot be cancelled.",
        )
    return order


@router.post("/{order_id}/place")
def place_order(
    order_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("purchase_order.update")),
):
    """Record that the order was sent to the supplier. Its lines are
    checked again: an item, unit or supplier deactivated since the draft
    was saved stops the order being placed."""
    order = transition(db, user, order_id, "place")
    active_supplier(db, user, order.supplier_id)
    lines = order_lines(db, order)
    if not lines:
        raise HTTPException(status_code=422, detail="An order needs at least one line.")
    for line in lines:
        resolve_line(db, user, line.item_id, line.unit_id)
    order.status = PURCHASE_ORDER_TRANSITIONS["place"][1]
    order.placed_by = user.id
    order.placed_at = datetime.now(timezone.utc)
    record_audit(db, user, "PLACE", "PURCHASE_ORDER", order.id, {
        "order_number": order.order_number, "lines": line_snapshot(lines)})
    db.commit()
    db.refresh(order)
    return serialize_order(db, user, order, detail=True)


@router.post("/{order_id}/close")
def close_order(
    order_id: int,
    payload: ReasonInput,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("purchase_order.update")),
):
    """No more deliveries are expected against this order. What was still
    outstanding is recorded in the audit log."""
    order = transition(db, user, order_id, "close")
    lines = order_lines(db, order)
    progress = progress_for(db, user, lines)
    order.status = PURCHASE_ORDER_TRANSITIONS["close"][1]
    order.closed_by = user.id
    order.closed_at = datetime.now(timezone.utc)
    order.close_reason = payload.reason
    record_audit(db, user, "CLOSE", "PURCHASE_ORDER", order.id, {
        "order_number": order.order_number, "reason": payload.reason,
        "left_to_receive": {str(line.item_id): quantity_text(progress[line.id]["left_to_receive"])
                            for line in lines},
    })
    db.commit()
    db.refresh(order)
    return serialize_order(db, user, order, detail=True)


@router.post("/{order_id}/cancel")
def cancel_order(
    order_id: int,
    payload: ReasonInput,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("purchase_order.update")),
):
    order = transition(db, user, order_id, "cancel")
    if linked_bills(db, order):
        raise HTTPException(
            status_code=409,
            detail="Bills have been entered against this order; close it instead of cancelling.",
        )
    order.status = PURCHASE_ORDER_TRANSITIONS["cancel"][1]
    order.cancelled_by = user.id
    order.cancelled_at = datetime.now(timezone.utc)
    order.cancel_reason = payload.reason
    record_audit(db, user, "CANCEL", "PURCHASE_ORDER", order.id, {
        "order_number": order.order_number, "reason": payload.reason})
    db.commit()
    db.refresh(order)
    return serialize_order(db, user, order, detail=True)
