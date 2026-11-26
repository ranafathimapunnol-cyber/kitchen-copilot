"""Outsourced food (Stage 8a: OUT01, OUT02, OUT03 criterion 1, AT04), per
docs/STAGE-8-IMPLEMENTATION-PLAN.md.

Project decisions applied (P8-1 to P8-5, P8-7):
- P8-1 separate outsourced orders and deliveries; purchase orders and goods
  receipts stay for raw ingredients. Nothing here creates a stock movement,
  goods receipt, supplier return, credit or payment.
- P8-2 goods receipts, kitchen issues, opening stock and counts refuse
  OUTSOURCED items (app/services/outsourced_guard.py).
- P8-3 option (b): orders are created, changed, placed and cancelled by
  ADMIN and KITCHEN_MANAGER (role check, plus the outsourced_food code);
  deliveries are recorded with outsourced_food.create and edited, confirmed
  and cancelled (drafts) with outsourced_food.update; viewing needs
  outsourced_food.read. Rates, totals, bill links and costs are returned
  only to users holding purchase_bill.read. No grant is changed.
- P8-4 a confirmed delivery's accepted quantities are added automatically
  to the meal record of the same campus, date and exact meal session, as
  "received" dish lines; never to a same-named other session (S6-1).
- P8-5 an item with stock movements cannot be classified OUTSOURCED.

Interim rules (not client decisions; see the plan, section 9):
- Rejected quantities are recorded with a reason; no credit, return or
  change to what is owed is recorded until client question Q6 is answered.
- A delivery for a date and session with no meal record waits until one is
  recorded; for a CLOSED record it waits ("reconciliation pending") until
  an Admin or Kitchen Manager reopens it. A closed record is never changed.
- Cancelling a confirmed delivery (ADMIN or KITCHEN_MANAGER, with a reason)
  is refused once any of its food has been distributed or the meal record
  is closed; otherwise its received lines are removed from the open record.
- Accepted quantities across a line's deliveries cannot exceed the ordered
  quantity: an excess is recorded as rejected or ordered separately.
- Units are explicit; no conversion is assumed (Q7).
Every query is limited to the user's campus.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_permission, user_has_permission
from app.api.routes.kitchen import Reason, clean, names_of, next_number, page_meta
from app.api.routes.master_data import record_audit
from app.core.clock import campus_today, utc_iso
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.campus import Campus
from app.models.master_data import Item, MealSession, Supplier, Unit
from app.models.meals import LEFTOVER_CLASSES, MealDish, MealLeftover, MealRecord
from app.models.outsourced import (
    OutsourcedDelivery, OutsourcedDeliveryLine, OutsourcedOrder, OutsourcedOrderLine,
)
from app.models.purchases import Purchase, PurchaseItem
from app.models.user import User, UserRole
from app.services.stock_ledger import quantity, quantity_text

orders_router = APIRouter(prefix="/api/outsourced-orders", tags=["Outsourced Food"])
deliveries_router = APIRouter(prefix="/api/outsourced-deliveries", tags=["Outsourced Food"])
lines_router = APIRouter(prefix="/api/outsourced-order-lines", tags=["Outsourced Food"])
report_router = APIRouter(prefix="/api/outsourced-food", tags=["Outsourced Food"])
bills_router = APIRouter(prefix="/api/purchases", tags=["Outsourced Food"])

ZERO = Decimal("0")
MONEY = Decimal("0.01")
ORDER_AHEAD_DAYS = 30  # interim: how far ahead a meal can be ordered
REPORT_MAX_DAYS = 366
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
ORDER_ENTITY = "OUTSOURCED_ORDER"
DELIVERY_ENTITY = "OUTSOURCED_DELIVERY"
MEAL_ENTITY = "MEAL_RECORD"
MANAGER_ROLES = (UserRole.ADMIN, UserRole.KITCHEN_MANAGER)
Q6_NOTE = "Credit not recorded because client question Q6 (supplier credits and rejected deliveries) remains unresolved."
C5_NOTE = "Meal sessions are matched exactly (client question C5)."
# Audit detail keys that carry costs: removed for users without purchase_bill.read.
COST_KEYS = frozenset({"unit_rate", "line_total", "planned_total", "purchase_item_id", "bill_line", "billed_total",
                       "invoice_number", "amount", "bill"})


# ============================================================
# PERMISSIONS (P8-3 option b)
# ============================================================

def order_manager(code: str):
    """ADMIN or KITCHEN_MANAGER holding the code: STAFF never order,
    change or cancel outsourced orders, whatever grants exist."""

    def check(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        if user.role not in MANAGER_ROLES:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="Outsourced orders are placed and managed by Admins and Kitchen Managers only.")
        if not user_has_permission(db, user, code):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="This permission has not been assigned to you.")
        return user

    return check


def both(*codes: str):
    """Every listed code (e.g. bill links need outsourced_food.read and purchase_bill.update)."""

    def check(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        for code in codes:
            if not user_has_permission(db, user, code):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                    detail="This permission has not been assigned to you.")
        return user

    return check


def sees_costs(db: Session, user: User) -> bool:
    return user_has_permission(db, user, "purchase_bill.read")


def is_manager(user: User) -> bool:
    return user.role in MANAGER_ROLES


def redact(value):
    """Audit details without cost fields."""
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items() if k not in COST_KEYS}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


# ============================================================
# INPUT
# ============================================================

class OutsourcedOrderLineInput(BaseModel):
    item_id: int = Field(gt=0)
    ordered_quantity: Decimal = Field(gt=0, max_digits=15, decimal_places=3)
    unit_id: int = Field(gt=0)
    unit_rate: Decimal = Field(ge=0, max_digits=14, decimal_places=4)
    remarks: str | None = Field(default=None, max_length=500)


class OutsourcedOrderInput(BaseModel):
    order_date: date | None = None
    meal_date: date
    meal_session_id: int = Field(gt=0)
    supplier_id: int = Field(gt=0)
    notes: str | None = Field(default=None, max_length=1000)
    lines: list[OutsourcedOrderLineInput] = Field(min_length=1, max_length=50)


class OutsourcedDeliveryLineInput(BaseModel):
    order_line_id: int = Field(gt=0)
    received_quantity: Decimal = Field(gt=0, max_digits=15, decimal_places=3)
    rejected_quantity: Decimal = Field(default=Decimal("0"), ge=0, max_digits=15, decimal_places=3)
    rejection_reason: str | None = Field(default=None, max_length=500)
    remarks: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def rejection_rules(self):
        if self.rejected_quantity > self.received_quantity:
            raise ValueError("The rejected quantity cannot be more than the received quantity.")
        reason = (self.rejection_reason or "").strip()
        if self.rejected_quantity > 0 and len(reason) < 3:
            raise ValueError("Give the reason for rejecting food (at least 3 characters).")
        self.rejection_reason = reason or None
        return self


class OutsourcedDeliveryInput(BaseModel):
    delivery_date: date
    remarks: str | None = Field(default=None, max_length=500)
    lines: list[OutsourcedDeliveryLineInput] = Field(min_length=1, max_length=50)


class OutsourcedBillLinkInput(BaseModel):
    purchase_item_id: int = Field(gt=0)


class OutsourcedReportExportInput(BaseModel):
    format: Literal["xlsx", "pdf"]
    date_from: date
    date_to: date
    supplier_id: int | None = Field(default=None, gt=0)
    item_id: int | None = Field(default=None, gt=0)
    meal_session_id: int | None = Field(default=None, gt=0)


# ============================================================
# SMALL HELPERS
# ============================================================

def money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)


def money_text(value) -> str:
    return format(money(value), "f")


def rate_text(value) -> str:
    return format(Decimal(str(value or 0)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP), "f")


def day_text(value: date) -> str:
    return value.strftime("%d %b %Y")


def touch(row) -> None:
    row.updated_at = datetime.now(timezone.utc)


def lock_order(db: Session, user: User, order_id: int) -> OutsourcedOrder:
    """FOR NO KEY UPDATE: serialises changes to one order (and the quantity
    checks of its deliveries) without blocking foreign-key checks."""
    order = (db.query(OutsourcedOrder)
             .filter(OutsourcedOrder.id == order_id, OutsourcedOrder.campus_id == user.campus_id)
             .with_for_update(key_share=True).first())
    if not order:
        raise HTTPException(status_code=404, detail="Outsourced order not found")
    return order


def get_order(db: Session, user: User, order_id: int) -> OutsourcedOrder:
    order = db.query(OutsourcedOrder).filter(OutsourcedOrder.id == order_id,
                                             OutsourcedOrder.campus_id == user.campus_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Outsourced order not found")
    return order


def lock_delivery(db: Session, user: User, delivery_id: int) -> OutsourcedDelivery:
    delivery = (db.query(OutsourcedDelivery)
                .filter(OutsourcedDelivery.id == delivery_id, OutsourcedDelivery.campus_id == user.campus_id)
                .with_for_update(key_share=True).first())
    if not delivery:
        raise HTTPException(status_code=404, detail="Outsourced delivery not found")
    return delivery


def order_lines(db: Session, order_id: int) -> list[OutsourcedOrderLine]:
    return db.query(OutsourcedOrderLine).filter(OutsourcedOrderLine.order_id == order_id).order_by(
        OutsourcedOrderLine.id).all()


def delivery_lines(db: Session, delivery_ids) -> dict[int, list[OutsourcedDeliveryLine]]:
    found: dict[int, list[OutsourcedDeliveryLine]] = {}
    ids = list(delivery_ids)
    if not ids:
        return found
    for line in db.query(OutsourcedDeliveryLine).filter(OutsourcedDeliveryLine.delivery_id.in_(ids)).order_by(
            OutsourcedDeliveryLine.id):
        found.setdefault(line.delivery_id, []).append(line)
    return found


def session_label(db: Session, session_id: int, on: date) -> str:
    name = db.query(MealSession.name).filter(MealSession.id == session_id).scalar()
    return f"{name} on {day_text(on)}"


def lock_session(db: Session, campus_id: int, session_id: int) -> None:
    """Serialises "attach received food" with meal-record creation for one
    meal session (FOR NO KEY UPDATE on the session row; foreign-key checks
    of other inserts are not blocked). Lock order everywhere: delivery,
    order, meal session, meal record."""
    db.query(MealSession.id).filter(MealSession.id == session_id, MealSession.campus_id == campus_id).with_for_update(
        key_share=True).first()


def live_meal_record(db: Session, campus_id: int, on: date, session_id: int, lock: bool = False) -> MealRecord | None:
    query = db.query(MealRecord).filter(MealRecord.campus_id == campus_id, MealRecord.meal_date == on,
                                        MealRecord.meal_session_id == session_id, MealRecord.status != "CANCELLED")
    if lock:
        query = query.with_for_update(key_share=True)
    return query.first()


def record_ref(db: Session, record: MealRecord | None) -> dict | None:
    if record is None:
        return None
    name = db.query(MealSession.name).filter(MealSession.id == record.meal_session_id).scalar()
    return {"id": record.id, "status": record.status, "meal_date": record.meal_date.isoformat(),
            "meal_session_name": name}


def same_name_warnings(db: Session, campus_id: int, on: date, session_id: int) -> list[str]:
    """Meal records on the date in a same-named other session (S6-1):
    reported, never linked."""
    from app.api.routes.planning import similar_sessions  # avoids a circular import

    out = []
    for other in similar_sessions(db, campus_id, session_id):
        record = live_meal_record(db, campus_id, on, other.id)
        if record:
            out.append(f"Meal record #{record.id} for “{other.name}” on {day_text(on)} is in a different meal "
                       f"session with the same name, so outsourced food is not added to it. {C5_NOTE}")
    return out


# ============================================================
# QUANTITIES
# ============================================================

def delivery_progress(db: Session, campus_id: int, line_ids, exclude_delivery_id: int | None = None) -> dict:
    """Per order line: received, rejected and accepted in CONFIRMED
    deliveries, and accepted in DRAFT ones (held). Cancelled deliveries count
    for nothing."""
    progress = {lid: {"received": ZERO, "rejected": ZERO, "accepted": ZERO, "held": ZERO} for lid in line_ids}
    if not progress:
        return progress
    query = (db.query(OutsourcedDeliveryLine.order_line_id, OutsourcedDelivery.status,
                      func.sum(OutsourcedDeliveryLine.received_quantity),
                      func.sum(OutsourcedDeliveryLine.rejected_quantity),
                      func.sum(OutsourcedDeliveryLine.accepted_quantity))
             .join(OutsourcedDelivery, OutsourcedDelivery.id == OutsourcedDeliveryLine.delivery_id)
             .filter(OutsourcedDeliveryLine.campus_id == campus_id,
                     OutsourcedDeliveryLine.order_line_id.in_(list(progress)),
                     OutsourcedDelivery.status.in_(("DRAFT", "CONFIRMED"))))
    if exclude_delivery_id is not None:
        query = query.filter(OutsourcedDelivery.id != exclude_delivery_id)
    for line_id, state, received, rejected, accepted in query.group_by(OutsourcedDeliveryLine.order_line_id,
                                                                        OutsourcedDelivery.status):
        entry = progress[line_id]
        if state == "CONFIRMED":
            entry["received"] += quantity(received or 0)
            entry["rejected"] += quantity(rejected or 0)
            entry["accepted"] += quantity(accepted or 0)
        else:
            entry["held"] += quantity(accepted or 0)
    return progress


def receiving_status(order: OutsourcedOrder, lines: list[OutsourcedOrderLine], progress: dict) -> str | None:
    if order.status != "ORDERED":
        return None
    accepted = [progress[l.id]["accepted"] for l in lines]
    if any(a > 0 for a in accepted) or any(progress[l.id]["received"] > 0 for l in lines):
        if all(progress[l.id]["accepted"] >= quantity(l.ordered_quantity) for l in lines):
            return "RECEIVED"
        return "PARTLY_RECEIVED"
    return "NOT_RECEIVED"


# ============================================================
# MEAL RECORDS (P8-4): received dish lines
# ============================================================

def unattached_lines(db: Session, campus_id: int, on: date, session_id: int) -> list:
    """Confirmed delivery lines with accepted food for this campus, date and
    exact session that are not yet on a meal record."""
    attached = db.query(MealDish.source_delivery_line_id).filter(MealDish.source_delivery_line_id.isnot(None))
    return (db.query(OutsourcedDeliveryLine, OutsourcedDelivery, OutsourcedOrder, OutsourcedOrderLine)
            .join(OutsourcedDelivery, OutsourcedDelivery.id == OutsourcedDeliveryLine.delivery_id)
            .join(OutsourcedOrder, OutsourcedOrder.id == OutsourcedDeliveryLine.order_id)
            .join(OutsourcedOrderLine, OutsourcedOrderLine.id == OutsourcedDeliveryLine.order_line_id)
            .filter(OutsourcedDeliveryLine.campus_id == campus_id, OutsourcedDelivery.status == "CONFIRMED",
                    OutsourcedOrder.meal_date == on, OutsourcedOrder.meal_session_id == session_id,
                    OutsourcedDeliveryLine.accepted_quantity > 0,
                    ~OutsourcedDeliveryLine.id.in_(attached))
            .order_by(OutsourcedDeliveryLine.id).all())


def attach_received(db: Session, user: User, record: MealRecord) -> list[MealDish]:
    """Add every waiting delivery line of the record's date and exact
    session to this OPEN record as a received dish line (flushed, not
    committed). Audited on the meal record and on each delivery."""
    if record.status != "OPEN":
        return []
    rows = unattached_lines(db, record.campus_id, record.meal_date, record.meal_session_id)
    if not rows:
        return []
    items = dict(db.query(Item.id, Item.name).filter(Item.id.in_({ol.item_id for _l, _d, _o, ol in rows})))
    added = []
    by_delivery: dict[int, list[dict]] = {}
    for line, delivery, order, order_line in rows:
        accepted = quantity(line.accepted_quantity)
        dish = MealDish(campus_id=record.campus_id, meal_record_id=record.id,
                        dish_name=(items.get(order_line.item_id) or f"Item #{order_line.item_id}")[:200],
                        menu_id=None, unit_id=line.unit_id, output_quantity=ZERO, carried_quantity=ZERO,
                        received_quantity=accepted, available_quantity=accepted, remarks=None,
                        source_delivery_line_id=line.id, created_by=user.id)
        db.add(dish)
        db.flush()
        added.append(dish)
        detail = {"delivery_id": delivery.id, "delivery_number": delivery.delivery_number, "order_id": order.id,
                  "order_number": order.order_number, "delivery_line_id": line.id, "dish_id": dish.id,
                  "dish_name": dish.dish_name, "quantity": quantity_text(accepted), "unit_id": line.unit_id}
        record_audit(db, user, "RECEIVE_OUTSOURCED", MEAL_ENTITY, record.id, detail)
        by_delivery.setdefault(delivery.id, []).append(detail)
    for delivery_id, details in by_delivery.items():
        record_audit(db, user, "ADDED_TO_MEAL_RECORD", DELIVERY_ENTITY, delivery_id,
                     {"meal_record_id": record.id, "lines": details})
    record.updated_at = datetime.now(timezone.utc)
    return added


def received_sources(db: Session, dishes: list[MealDish]) -> dict[int, dict]:
    """{dish id: where its received food came from} for the meal record page."""
    ids = {d.source_delivery_line_id for d in dishes if d.source_delivery_line_id}
    if not ids:
        return {}
    rows = (db.query(OutsourcedDeliveryLine, OutsourcedDelivery, OutsourcedOrder, Supplier.name)
            .join(OutsourcedDelivery, OutsourcedDelivery.id == OutsourcedDeliveryLine.delivery_id)
            .join(OutsourcedOrder, OutsourcedOrder.id == OutsourcedDeliveryLine.order_id)
            .outerjoin(Supplier, Supplier.id == OutsourcedOrder.supplier_id)
            .filter(OutsourcedDeliveryLine.id.in_(ids)).all())
    by_line = {line.id: {"delivery_id": delivery.id, "delivery_number": delivery.delivery_number,
                         "delivery_date": delivery.delivery_date.isoformat(), "order_id": order.id,
                         "order_number": order.order_number, "supplier_name": supplier,
                         "received_quantity": quantity_text(line.received_quantity),
                         "rejected_quantity": quantity_text(line.rejected_quantity),
                         "accepted_quantity": quantity_text(line.accepted_quantity)}
               for line, delivery, order, supplier in rows}
    return {d.id: by_line.get(d.source_delivery_line_id) for d in dishes if d.source_delivery_line_id}


def pending_for_record(db: Session, record: MealRecord) -> list[dict]:
    """Confirmed outsourced food of the record's date and exact session that
    is not on it: only possible while the record is CLOSED (reconciliation
    pending until it is reopened)."""
    if record.status == "CANCELLED":
        return []
    rows = unattached_lines(db, record.campus_id, record.meal_date, record.meal_session_id)
    units = dict(db.query(Unit.id, Unit.symbol).filter(Unit.id.in_({l.unit_id for l, _d, _o, _ol in rows} or {0})))
    items = dict(db.query(Item.id, Item.name).filter(Item.id.in_({ol.item_id for _l, _d, _o, ol in rows} or {0})))
    return [{"delivery_line_id": line.id, "delivery_id": delivery.id, "delivery_number": delivery.delivery_number,
             "order_id": order.id, "order_number": order.order_number, "item_name": items.get(order_line.item_id),
             "accepted_quantity": quantity_text(line.accepted_quantity), "unit_symbol": units.get(line.unit_id)}
            for line, delivery, order, order_line in rows]


def detach_received(db: Session, user: User, record: MealRecord) -> list[dict]:
    """Meal record cancellation: its received lines (and their leftovers) are
    removed, so the food waits for the correct record of the same date and
    session. The caller has already refused when leftovers are carried out."""
    dishes = db.query(MealDish).filter(MealDish.meal_record_id == record.id,
                                       MealDish.source_delivery_line_id.isnot(None)).all()
    removed = []
    for dish in dishes:
        leftovers = db.query(MealLeftover).filter(MealLeftover.dish_id == dish.id).all()
        snapshot = {"dish_id": dish.id, "dish_name": dish.dish_name, "delivery_line_id": dish.source_delivery_line_id,
                    "quantity": quantity_text(dish.received_quantity), "unit_id": dish.unit_id,
                    "distributed_quantity": quantity_text(dish.distributed_quantity)
                    if dish.distributed_quantity is not None else None,
                    "leftovers": [{"classification": l.classification, "quantity": quantity_text(l.quantity),
                                   "remarks": l.remarks} for l in leftovers]}
        for row in leftovers:
            db.delete(row)
        db.flush()
        db.delete(dish)
        db.flush()
        removed.append(snapshot)
    if removed:
        record_audit(db, user, "RECEIVED_RELEASED", MEAL_ENTITY, record.id, {"lines": removed})
    return removed


def meal_link(db: Session, order: OutsourcedOrder, line: OutsourcedDeliveryLine, delivery: OutsourcedDelivery,
              dishes: dict[int, MealDish], record: MealRecord | None) -> dict:
    """Where one delivery line's accepted food is (P8-4)."""
    if delivery.status != "CONFIRMED":
        return {"state": "NOT_CONFIRMED", "message": "Added to the meal record when the delivery is confirmed."}
    if quantity(line.accepted_quantity) <= 0:
        return {"state": "NOTHING_ACCEPTED", "message": "Nothing accepted, so nothing is added to the meal record."}
    dish = dishes.get(line.id)
    if dish is not None:
        target = db.get(MealRecord, dish.meal_record_id)
        return {"state": "ADDED", "message": "On the meal record.", "meal_record": record_ref(db, target),
                "dish_id": dish.id}
    label = session_label(db, order.meal_session_id, order.meal_date)
    if record is not None and record.status == "CLOSED":
        return {"state": "PENDING_CLOSED", "meal_record": record_ref(db, record), "message": (
            f"Reconciliation pending: the meal record of {label} is closed, so this food was not added to it. "
            "An Admin or Kitchen Manager can reopen the record; the food is then added automatically.")}
    return {"state": "PENDING_NO_RECORD", "meal_record": record_ref(db, record), "message": (
        f"Waiting for the meal record of {label}: the food is added when that record is created.")}


# ============================================================
# VALIDATION
# ============================================================

def valid_session(db: Session, user: User, session_id: int) -> MealSession:
    session = db.query(MealSession).filter(MealSession.id == session_id, MealSession.campus_id == user.campus_id).first()
    if not session or not session.is_active:
        raise HTTPException(status_code=422, detail="Choose an active meal session.")
    return session


def valid_supplier(db: Session, user: User, supplier_id: int) -> Supplier:
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id, Supplier.campus_id == user.campus_id).first()
    if not supplier or not supplier.is_active:
        raise HTTPException(status_code=422, detail="Choose an active supplier.")
    return supplier


def check_order_dates(order_date: date, meal_date: date) -> None:
    today = campus_today()
    if order_date > today:
        raise HTTPException(status_code=422, detail="The order date cannot be in the future.")
    if meal_date < order_date:
        raise HTTPException(status_code=422, detail="The meal date cannot be before the order date.")
    limit = today + timedelta(days=ORDER_AHEAD_DAYS)
    if meal_date > limit:
        raise HTTPException(status_code=422, detail=(
            f"Outsourced meals can be ordered up to {ORDER_AHEAD_DAYS} days ahead (until {limit.isoformat()})."))


def prepare_order_lines(db: Session, user: User, lines: list[OutsourcedOrderLineInput]) -> list[dict]:
    ids = [l.item_id for l in lines]
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=422, detail="List each item once per order.")
    items = {i.id: i for i in db.query(Item).filter(Item.campus_id == user.campus_id, Item.id.in_(ids))}
    units = {u.id: u for u in db.query(Unit).filter(Unit.campus_id == user.campus_id,
                                                    Unit.id.in_({l.unit_id for l in lines}))}
    prepared = []
    for line in lines:
        item = items.get(line.item_id)
        if not item or not item.is_active:
            raise HTTPException(status_code=422, detail="Choose active items.")
        if item.item_kind != "OUTSOURCED":
            raise HTTPException(status_code=422, detail=(
                f"{item.name} is not classified as outsourced food. Only items of kind Outsourced can be ordered "
                "here; an Admin or Kitchen Manager sets the kind under Items."))
        unit = units.get(line.unit_id)
        if not unit or not unit.is_active:
            raise HTTPException(status_code=422, detail=f"{item.name}: choose an active unit.")
        ordered = quantity(line.ordered_quantity)
        rate = Decimal(str(line.unit_rate))
        prepared.append({"item_id": item.id, "ordered_quantity": ordered, "unit_id": unit.id, "unit_rate": rate,
                         "line_total": money(ordered * rate), "remarks": clean(line.remarks)})
    return prepared


def order_snapshot(order: OutsourcedOrder, lines) -> dict:
    return {
        "order_number": order.order_number, "order_date": order.order_date.isoformat(),
        "meal_date": order.meal_date.isoformat(), "meal_session_id": order.meal_session_id,
        "supplier_id": order.supplier_id, "status": order.status, "notes": order.notes,
        "lines": [{"item_id": l.item_id if hasattr(l, "item_id") else l["item_id"],
                   "ordered_quantity": quantity_text(l.ordered_quantity if hasattr(l, "ordered_quantity")
                                                     else l["ordered_quantity"]),
                   "unit_id": l.unit_id if hasattr(l, "unit_id") else l["unit_id"],
                   "unit_rate": rate_text(l.unit_rate if hasattr(l, "unit_rate") else l["unit_rate"]),
                   "line_total": money_text(l.line_total if hasattr(l, "line_total") else l["line_total"])}
                  for l in lines],
    }


def prepare_delivery_lines(db: Session, user: User, order: OutsourcedOrder, payload: OutsourcedDeliveryInput,
                           exclude_delivery_id: int | None = None) -> list[dict]:
    if payload.delivery_date > campus_today():
        raise HTTPException(status_code=422, detail="A delivery cannot be dated in the future.")
    if payload.delivery_date < order.order_date:
        raise HTTPException(status_code=422, detail=(
            f"A delivery cannot be dated before the order date ({day_text(order.order_date)})."))
    ids = [l.order_line_id for l in payload.lines]
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=422, detail="List each ordered item once per delivery.")
    lines = {l.id: l for l in order_lines(db, order.id)}
    progress = delivery_progress(db, user.campus_id, list(lines), exclude_delivery_id=exclude_delivery_id)
    items = dict(db.query(Item.id, Item.name).filter(Item.id.in_({l.item_id for l in lines.values()} or {0})))
    units = dict(db.query(Unit.id, Unit.symbol).filter(Unit.id.in_({l.unit_id for l in lines.values()} or {0})))
    prepared = []
    for entry in payload.lines:
        line = lines.get(entry.order_line_id)
        if line is None:
            raise HTTPException(status_code=422, detail=f"Order line {entry.order_line_id} is not on {order.order_number}.")
        received, rejected = quantity(entry.received_quantity), quantity(entry.rejected_quantity)
        accepted = received - rejected
        name, unit = items.get(line.item_id), units.get(line.unit_id, "")
        ordered = quantity(line.ordered_quantity)
        held = progress[line.id]["accepted"] + progress[line.id]["held"]
        left = max(ordered - held, ZERO)
        if accepted > left:
            raise HTTPException(status_code=422, detail=(
                f"{name}: only {quantity_text(left)} {unit} remain to be received on {order.order_number} "
                f"(ordered {quantity_text(ordered)} {unit}, already accepted or in a draft delivery "
                f"{quantity_text(held)} {unit}), but {quantity_text(accepted)} {unit} would be accepted. "
                "Record the excess as rejected, or place an additional order for the extra quantity."))
        prepared.append({"order_line_id": line.id, "unit_id": line.unit_id, "received_quantity": received,
                         "rejected_quantity": rejected, "accepted_quantity": accepted,
                         "rejection_reason": entry.rejection_reason if rejected > 0 else None,
                         "remarks": clean(entry.remarks)})
    return prepared


def delivery_snapshot(delivery: OutsourcedDelivery, lines) -> dict:
    def get(l, key):
        return getattr(l, key) if not isinstance(l, dict) else l[key]

    return {"delivery_number": delivery.delivery_number, "delivery_date": delivery.delivery_date.isoformat(),
            "status": delivery.status, "remarks": delivery.remarks,
            "lines": [{"order_line_id": get(l, "order_line_id"),
                       "received_quantity": quantity_text(get(l, "received_quantity")),
                       "rejected_quantity": quantity_text(get(l, "rejected_quantity")),
                       "accepted_quantity": quantity_text(get(l, "accepted_quantity")),
                       "rejection_reason": get(l, "rejection_reason")} for l in lines]}


# ============================================================
# SERIALISATION
# ============================================================

def order_detail(db: Session, user: User, order: OutsourcedOrder) -> dict:
    costs = sees_costs(db, user)
    lines = order_lines(db, order.id)
    progress = delivery_progress(db, order.campus_id, [l.id for l in lines])
    items = dict(db.query(Item.id, Item.name).filter(Item.id.in_({l.item_id for l in lines} or {0})))
    deliveries = (db.query(OutsourcedDelivery).filter(OutsourcedDelivery.order_id == order.id)
                  .order_by(OutsourcedDelivery.id).all())
    d_lines = delivery_lines(db, [d.id for d in deliveries])
    unit_ids = {l.unit_id for l in lines}
    units = dict(db.query(Unit.id, Unit.symbol).filter(Unit.id.in_(unit_ids or {0})))
    session_name = db.query(MealSession.name).filter(MealSession.id == order.meal_session_id).scalar()
    supplier_name = db.query(Supplier.name).filter(Supplier.id == order.supplier_id).scalar()
    all_dline_ids = [l.id for rows in d_lines.values() for l in rows]
    dishes = {d.source_delivery_line_id: d for d in db.query(MealDish).filter(
        MealDish.source_delivery_line_id.in_(all_dline_ids or [0]))}
    record = live_meal_record(db, order.campus_id, order.meal_date, order.meal_session_id)
    names = names_of(db, [order.created_by, order.ordered_by, order.cancelled_by]
                     + [x for d in deliveries for x in (d.created_by, d.confirmed_by, d.cancelled_by)])
    bills = {}
    if costs:
        linked = [l.purchase_item_id for l in lines if l.purchase_item_id]
        for pi, bill in (db.query(PurchaseItem, Purchase).join(Purchase, Purchase.id == PurchaseItem.purchase_id)
                         .filter(PurchaseItem.id.in_(linked or [0]))):
            bills[pi.id] = {"purchase_item_id": pi.id, "purchase_id": bill.id, "invoice_number": bill.invoice_number,
                            "purchase_date": bill.purchase_date.isoformat(), "quantity": quantity_text(pi.quantity),
                            "unit_id": pi.unit_id, "unit_rate": rate_text(pi.unit_rate),
                            "line_total": money_text(pi.line_total)}
    order_by_line = {l.id: l for l in lines}

    out_lines = []
    for l in lines:
        p = progress[l.id]
        ordered = quantity(l.ordered_quantity)
        row = {
            "id": l.id, "item_id": l.item_id, "item_name": items.get(l.item_id), "unit_id": l.unit_id,
            "unit_symbol": units.get(l.unit_id), "ordered_quantity": quantity_text(ordered),
            "received_quantity": quantity_text(p["received"]), "rejected_quantity": quantity_text(p["rejected"]),
            "accepted_quantity": quantity_text(p["accepted"]), "in_draft_quantity": quantity_text(p["held"]),
            "remaining_quantity": quantity_text(max(ordered - p["accepted"] - p["held"], ZERO)),
            "remarks": l.remarks,
        }
        if costs:
            row.update({"unit_rate": rate_text(l.unit_rate), "line_total": money_text(l.line_total),
                        "bill_line": bills.get(l.purchase_item_id)})
        out_lines.append(row)

    out_deliveries = []
    any_rejected = False
    for d in reversed(deliveries):
        rows = []
        for dl in d_lines.get(d.id, []):
            ol = order_by_line.get(dl.order_line_id)
            if d.status != "CANCELLED" and quantity(dl.rejected_quantity) > 0:
                any_rejected = True
            rows.append({
                "id": dl.id, "order_line_id": dl.order_line_id, "item_name": items.get(ol.item_id) if ol else None,
                "unit_symbol": units.get(dl.unit_id), "received_quantity": quantity_text(dl.received_quantity),
                "rejected_quantity": quantity_text(dl.rejected_quantity),
                "accepted_quantity": quantity_text(dl.accepted_quantity), "rejection_reason": dl.rejection_reason,
                "remarks": dl.remarks,
                "meal_link": meal_link(db, order, dl, d, dishes, record) if d.status != "CANCELLED" else None,
            })
        out_deliveries.append({
            "id": d.id, "delivery_number": d.delivery_number, "delivery_date": d.delivery_date.isoformat(),
            "status": d.status, "remarks": d.remarks, "created_by_name": names.get(d.created_by),
            "created_at": utc_iso(d.created_at), "updated_at": utc_iso(d.updated_at) if d.updated_at else None,
            "confirmed_by_name": names.get(d.confirmed_by),
            "confirmed_at": utc_iso(d.confirmed_at) if d.confirmed_at else None,
            "cancelled_by_name": names.get(d.cancelled_by),
            "cancelled_at": utc_iso(d.cancelled_at) if d.cancelled_at else None,
            "cancellation_reason": d.cancellation_reason, "lines": rows,
        })

    links = [line["meal_link"]["state"] for d in out_deliveries for line in d["lines"] if line["meal_link"]]
    pending = [s for s in links if s.startswith("PENDING")]
    if not any(s in ("ADDED",) or s.startswith("PENDING") for s in links):
        link_state = None
    elif "PENDING_CLOSED" in pending:
        link_state = "PENDING_CLOSED"
    elif pending:
        link_state = "PENDING_NO_RECORD"
    else:
        link_state = "ADDED"

    remaining_total = sum((quantity(l["remaining_quantity"]) for l in out_lines), ZERO)
    can_update = user_has_permission(db, user, "outsourced_food.update")
    manage = is_manager(user) and can_update
    detail = {
        "id": order.id, "order_number": order.order_number, "order_date": order.order_date.isoformat(),
        "meal_date": order.meal_date.isoformat(), "meal_session_id": order.meal_session_id,
        "meal_session_name": session_name, "supplier_id": order.supplier_id, "supplier_name": supplier_name,
        "status": order.status, "notes": order.notes, "receiving_status": receiving_status(order, lines, progress),
        "created_by_name": names.get(order.created_by), "created_at": utc_iso(order.created_at),
        "updated_at": utc_iso(order.updated_at) if order.updated_at else None,
        "ordered_by_name": names.get(order.ordered_by),
        "ordered_at": utc_iso(order.ordered_at) if order.ordered_at else None,
        "cancelled_by_name": names.get(order.cancelled_by),
        "cancelled_at": utc_iso(order.cancelled_at) if order.cancelled_at else None,
        "cancellation_reason": order.cancellation_reason,
        "lines": out_lines,
        "deliveries": out_deliveries,
        "meal_record": record_ref(db, record),
        "meal_link_state": link_state,
        "session_warnings": same_name_warnings(db, order.campus_id, order.meal_date, order.meal_session_id),
        "rejection_note": Q6_NOTE if any_rejected else None,
        "costs_visible": costs,
        "permissions": {
            "can_edit": manage and order.status == "DRAFT",
            "can_place": manage and order.status == "DRAFT",
            "can_cancel": manage and order.status != "CANCELLED",
            "can_record_delivery": order.status == "ORDERED" and remaining_total > 0
            and user_has_permission(db, user, "outsourced_food.create"),
            "can_update_delivery": can_update,
            "can_cancel_confirmed_delivery": manage,
            "can_link_bill": order.status == "ORDERED" and costs
            and user_has_permission(db, user, "purchase_bill.update"),
        },
    }
    if costs:
        detail["planned_total"] = money_text(sum((money(l.line_total) for l in lines), ZERO))
        detail["billed_total"] = money_text(sum((money(b["line_total"]) for b in bills.values()), ZERO))
    return detail


# ============================================================
# OPTIONS AND LIST
# ============================================================

@orders_router.get("/options")
def outsourced_options(db: Session = Depends(get_db), user: User = Depends(require_permission("outsourced_food.read"))):
    """Sessions, suppliers, OUTSOURCED items and units for the forms and
    filters, so the screens need no master-data permission."""
    campus_id = user.campus_id
    units = {u.id: u for u in db.query(Unit).filter(Unit.campus_id == campus_id)}
    return {
        "today": campus_today().isoformat(),
        "latest_meal_date": (campus_today() + timedelta(days=ORDER_AHEAD_DAYS)).isoformat(),
        "meal_sessions": [{"id": s.id, "name": s.name, "is_active": s.is_active} for s in db.query(MealSession).filter(
            MealSession.campus_id == campus_id).order_by(MealSession.id)],
        "suppliers": [{"id": s.id, "name": s.name, "is_active": s.is_active} for s in db.query(Supplier).filter(
            Supplier.campus_id == campus_id).order_by(func.lower(Supplier.name))],
        "items": [{"id": i.id, "name": i.name, "is_active": i.is_active, "standard_unit_id": i.standard_unit_id,
                   "standard_unit_symbol": units[i.standard_unit_id].symbol if i.standard_unit_id in units else None}
                  for i in db.query(Item).filter(Item.campus_id == campus_id, Item.item_kind == "OUTSOURCED")
                  .order_by(func.lower(Item.name))],
        "units": [{"id": u.id, "name": u.name, "symbol": u.symbol} for u in sorted(
            (u for u in units.values() if u.is_active), key=lambda u: u.name.lower())],
        "can_manage_orders": is_manager(user) and user_has_permission(db, user, "outsourced_food.create"),
        "costs_visible": sees_costs(db, user),
    }


@orders_router.get("")
def list_orders(
    status_filter: str | None = Query(default=None, alias="status", pattern="^(DRAFT|ORDERED|CANCELLED)$"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    meal_session_id: int | None = Query(default=None, gt=0),
    supplier_id: int | None = Query(default=None, gt=0),
    item_id: int | None = Query(default=None, gt=0),
    search: str | None = Query(default=None, max_length=50),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("outsourced_food.read")),
):
    """Orders by meal date (newest first). Dates filter the meal date."""
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from cannot be after date_to.")
    query = db.query(OutsourcedOrder).filter(OutsourcedOrder.campus_id == user.campus_id)
    if date_from:
        query = query.filter(OutsourcedOrder.meal_date >= date_from)
    if date_to:
        query = query.filter(OutsourcedOrder.meal_date <= date_to)
    if meal_session_id:
        query = query.filter(OutsourcedOrder.meal_session_id == meal_session_id)
    if supplier_id:
        query = query.filter(OutsourcedOrder.supplier_id == supplier_id)
    if item_id:
        query = query.filter(OutsourcedOrder.id.in_(db.query(OutsourcedOrderLine.order_id).filter(
            OutsourcedOrderLine.item_id == item_id, OutsourcedOrderLine.campus_id == user.campus_id)))
    term = (search or "").strip()
    if term:
        query = query.filter(func.lower(OutsourcedOrder.order_number).like(f"%{term.lower()}%"))
    counts = dict(query.with_entities(OutsourcedOrder.status, func.count(OutsourcedOrder.id))
                  .group_by(OutsourcedOrder.status))
    if status_filter:
        query = query.filter(OutsourcedOrder.status == status_filter)
    total = query.count()
    orders = (query.order_by(OutsourcedOrder.meal_date.desc(), OutsourcedOrder.id.desc())
              .offset((page - 1) * page_size).limit(page_size).all())
    ids = [o.id for o in orders] or [0]
    lines_by_order: dict[int, list[OutsourcedOrderLine]] = {}
    for line in db.query(OutsourcedOrderLine).filter(OutsourcedOrderLine.order_id.in_(ids)).order_by(
            OutsourcedOrderLine.id):
        lines_by_order.setdefault(line.order_id, []).append(line)
    all_lines = [l for rows in lines_by_order.values() for l in rows]
    progress = delivery_progress(db, user.campus_id, [l.id for l in all_lines])
    items = dict(db.query(Item.id, Item.name).filter(Item.id.in_({l.item_id for l in all_lines} or {0})))
    sessions = dict(db.query(MealSession.id, MealSession.name).filter(
        MealSession.id.in_({o.meal_session_id for o in orders} or {0})))
    suppliers = dict(db.query(Supplier.id, Supplier.name).filter(Supplier.id.in_({o.supplier_id for o in orders} or {0})))
    deliveries = dict(db.query(OutsourcedDelivery.order_id, func.count(OutsourcedDelivery.id)).filter(
        OutsourcedDelivery.order_id.in_(ids), OutsourcedDelivery.status != "CANCELLED").group_by(
        OutsourcedDelivery.order_id))
    costs = sees_costs(db, user)

    def row(o: OutsourcedOrder) -> dict:
        lines = lines_by_order.get(o.id, [])
        out = {
            "id": o.id, "order_number": o.order_number, "order_date": o.order_date.isoformat(),
            "meal_date": o.meal_date.isoformat(), "meal_session_name": sessions.get(o.meal_session_id),
            "supplier_name": suppliers.get(o.supplier_id), "status": o.status,
            "receiving_status": receiving_status(o, lines, progress),
            "item_names": [items.get(l.item_id) for l in lines], "line_count": len(lines),
            "delivery_count": deliveries.get(o.id, 0),
        }
        if costs:
            out["planned_total"] = money_text(sum((money(l.line_total) for l in lines), ZERO))
        return out

    return {
        "items": [row(o) for o in orders],
        "status_counts": {s: counts.get(s, 0) for s in ("DRAFT", "ORDERED", "CANCELLED")},
        "costs_visible": costs,
        **page_meta(total, page, page_size),
    }


# ============================================================
# ORDERS (ADMIN and KITCHEN_MANAGER)
# ============================================================

@orders_router.post("", status_code=201)
def create_order(payload: OutsourcedOrderInput, db: Session = Depends(get_db),
                 user: User = Depends(order_manager("outsourced_food.create"))):
    order_date = payload.order_date or campus_today()
    check_order_dates(order_date, payload.meal_date)
    session = valid_session(db, user, payload.meal_session_id)
    supplier = valid_supplier(db, user, payload.supplier_id)
    lines = prepare_order_lines(db, user, payload.lines)
    seq, number = next_number(db, user.campus_id, OutsourcedOrder, OutsourcedOrder.order_seq, "OO")
    order = OutsourcedOrder(campus_id=user.campus_id, order_seq=seq, order_number=number, order_date=order_date,
                            meal_date=payload.meal_date, meal_session_id=session.id, supplier_id=supplier.id,
                            status="DRAFT", notes=clean(payload.notes), created_by=user.id)
    db.add(order)
    db.flush()
    for line in lines:
        db.add(OutsourcedOrderLine(campus_id=user.campus_id, order_id=order.id, **line))
    db.flush()
    record_audit(db, user, "CREATE", ORDER_ENTITY, order.id, order_snapshot(order, lines))
    db.commit()
    db.refresh(order)
    return order_detail(db, user, order)


@orders_router.get("/{order_id}")
def get_order_detail(order_id: int, db: Session = Depends(get_db),
                     user: User = Depends(require_permission("outsourced_food.read"))):
    return order_detail(db, user, get_order(db, user, order_id))


@orders_router.put("/{order_id}")
def update_order(order_id: int, payload: OutsourcedOrderInput, db: Session = Depends(get_db),
                 user: User = Depends(order_manager("outsourced_food.update"))):
    """A DRAFT order's dates, session, supplier, notes and lines."""
    order = lock_order(db, user, order_id)
    if order.status != "DRAFT":
        raise HTTPException(status_code=409, detail=(
            f"{order.order_number} is {order.status.lower()}; only a draft order can be changed."))
    order_date = payload.order_date or order.order_date
    check_order_dates(order_date, payload.meal_date)
    session = valid_session(db, user, payload.meal_session_id)
    supplier = valid_supplier(db, user, payload.supplier_id)
    lines = prepare_order_lines(db, user, payload.lines)
    before = order_snapshot(order, order_lines(db, order.id))
    for old in order_lines(db, order.id):
        db.delete(old)
    db.flush()
    order.order_date, order.meal_date, order.meal_session_id = order_date, payload.meal_date, session.id
    order.supplier_id, order.notes = supplier.id, clean(payload.notes)
    touch(order)
    for line in lines:
        db.add(OutsourcedOrderLine(campus_id=user.campus_id, order_id=order.id, **line))
    db.flush()
    record_audit(db, user, "UPDATE", ORDER_ENTITY, order.id, {"before": before, "after": order_snapshot(order, lines)})
    db.commit()
    db.refresh(order)
    return order_detail(db, user, order)


@orders_router.post("/{order_id}/place")
def place_order(order_id: int, db: Session = Depends(get_db),
                user: User = Depends(order_manager("outsourced_food.update"))):
    """DRAFT -> ORDERED. Deliveries can then be recorded against it."""
    order = lock_order(db, user, order_id)
    if order.status != "DRAFT":
        raise HTTPException(status_code=409, detail=f"{order.order_number} is already {order.status.lower()}.")
    valid_session(db, user, order.meal_session_id)
    valid_supplier(db, user, order.supplier_id)
    lines = order_lines(db, order.id)
    for line in lines:
        item = db.get(Item, line.item_id)
        if not item or not item.is_active or item.item_kind != "OUTSOURCED":
            raise HTTPException(status_code=422, detail=(
                f"{item.name if item else 'An item'} is no longer an active outsourced item; edit the order first."))
    now = datetime.now(timezone.utc)
    order.status, order.ordered_by, order.ordered_at = "ORDERED", user.id, now
    touch(order)
    record_audit(db, user, "PLACE", ORDER_ENTITY, order.id, order_snapshot(order, lines))
    db.commit()
    db.refresh(order)
    return order_detail(db, user, order)


@orders_router.post("/{order_id}/cancel")
def cancel_order(order_id: int, payload: Reason, db: Session = Depends(get_db),
                 user: User = Depends(order_manager("outsourced_food.update"))):
    """Cancel an order with a reason. Refused while it has a draft or
    confirmed delivery (cancel those first) or a linked bill line."""
    order = lock_order(db, user, order_id)
    if order.status == "CANCELLED":
        raise HTTPException(status_code=409, detail=f"{order.order_number} is already cancelled.")
    live = (db.query(OutsourcedDelivery).filter(OutsourcedDelivery.order_id == order.id,
                                                OutsourcedDelivery.status != "CANCELLED")
            .order_by(OutsourcedDelivery.id).all())
    if live:
        listed = ", ".join(f"{d.delivery_number} ({d.status.lower()})" for d in live)
        raise HTTPException(status_code=409, detail=(
            f"{order.order_number} has deliveries recorded: {listed}. Cancel those deliveries first. A confirmed "
            "delivery whose food has already been distributed on a meal record cannot be cancelled, so neither can "
            "its order."))
    if db.query(OutsourcedOrderLine.id).filter(OutsourcedOrderLine.order_id == order.id,
                                               OutsourcedOrderLine.purchase_item_id.isnot(None)).first():
        raise HTTPException(status_code=409, detail=(
            f"{order.order_number} has supplier bill lines linked to it. Unlink them first."))
    now = datetime.now(timezone.utc)
    previous = order.status
    order.status, order.cancelled_by, order.cancelled_at, order.cancellation_reason = (
        "CANCELLED", user.id, now, payload.reason)
    touch(order)
    record_audit(db, user, "CANCEL", ORDER_ENTITY, order.id, {"reason": payload.reason, "previous_status": previous})
    db.commit()
    db.refresh(order)
    return order_detail(db, user, order)


@orders_router.get("/{order_id}/history")
def order_history(order_id: int, db: Session = Depends(get_db),
                  user: User = Depends(require_permission("outsourced_food.read"))):
    """Every audited action on the order and its deliveries, oldest first.
    Cost fields are left out for users without purchase_bill.read."""
    order = get_order(db, user, order_id)
    delivery_ids = [i for (i,) in db.query(OutsourcedDelivery.id).filter(OutsourcedDelivery.order_id == order.id)]
    rows = (db.query(AuditLog).filter(
        AuditLog.campus_id == user.campus_id,
        or_((AuditLog.entity_type == ORDER_ENTITY) & (AuditLog.entity_id == order.id),
            (AuditLog.entity_type == DELIVERY_ENTITY) & (AuditLog.entity_id.in_(delivery_ids or [0]))),
    ).order_by(AuditLog.id).all())
    numbers = dict(db.query(OutsourcedDelivery.id, OutsourcedDelivery.delivery_number).filter(
        OutsourcedDelivery.id.in_(delivery_ids or [0])))
    names = names_of(db, [r.user_id for r in rows])
    costs = sees_costs(db, user)
    return {"items": [{
        "id": r.id, "action": r.action, "entity": "order" if r.entity_type == ORDER_ENTITY else "delivery",
        "delivery_number": numbers.get(r.entity_id) if r.entity_type == DELIVERY_ENTITY else None,
        "user_name": names.get(r.user_id), "created_at": utc_iso(r.created_at),
        "details": r.details if costs else redact(r.details),
    } for r in rows]}


# ============================================================
# DELIVERIES
# ============================================================

@orders_router.post("/{order_id}/deliveries", status_code=201)
def record_delivery(order_id: int, payload: OutsourcedDeliveryInput, db: Session = Depends(get_db),
                    user: User = Depends(require_permission("outsourced_food.create"))):
    """A DRAFT delivery: received, rejected (with reason) and accepted per
    ordered item. Partial deliveries are allowed; accepted quantities across
    deliveries never exceed what was ordered."""
    order = lock_order(db, user, order_id)
    if order.status != "ORDERED":
        raise HTTPException(status_code=409, detail=(
            f"{order.order_number} is {order.status.lower()}; deliveries are recorded against an ordered order."))
    lines = prepare_delivery_lines(db, user, order, payload)
    seq, number = next_number(db, user.campus_id, OutsourcedDelivery, OutsourcedDelivery.delivery_seq, "OD")
    delivery = OutsourcedDelivery(campus_id=user.campus_id, delivery_seq=seq, delivery_number=number,
                                  order_id=order.id, delivery_date=payload.delivery_date, status="DRAFT",
                                  remarks=clean(payload.remarks), created_by=user.id)
    db.add(delivery)
    db.flush()
    for line in lines:
        db.add(OutsourcedDeliveryLine(campus_id=user.campus_id, delivery_id=delivery.id, order_id=order.id, **line))
    db.flush()
    snapshot = delivery_snapshot(delivery, lines)
    record_audit(db, user, "CREATE", DELIVERY_ENTITY, delivery.id, {"order_number": order.order_number, **snapshot})
    db.commit()
    db.refresh(order)
    return order_detail(db, user, order)


@deliveries_router.put("/{delivery_id}")
def update_delivery(delivery_id: int, payload: OutsourcedDeliveryInput, db: Session = Depends(get_db),
                    user: User = Depends(require_permission("outsourced_food.update"))):
    delivery = lock_delivery(db, user, delivery_id)
    if delivery.status != "DRAFT":
        raise HTTPException(status_code=409, detail=(
            f"{delivery.delivery_number} is {delivery.status.lower()}; only a draft delivery can be changed."))
    order = lock_order(db, user, delivery.order_id)
    lines = prepare_delivery_lines(db, user, order, payload, exclude_delivery_id=delivery.id)
    old = delivery_lines(db, [delivery.id]).get(delivery.id, [])
    before = delivery_snapshot(delivery, old)
    for row in old:
        db.delete(row)
    db.flush()
    delivery.delivery_date, delivery.remarks = payload.delivery_date, clean(payload.remarks)
    touch(delivery)
    for line in lines:
        db.add(OutsourcedDeliveryLine(campus_id=user.campus_id, delivery_id=delivery.id, order_id=order.id, **line))
    db.flush()
    record_audit(db, user, "UPDATE", DELIVERY_ENTITY, delivery.id,
                 {"before": before, "after": delivery_snapshot(delivery, lines)})
    db.commit()
    db.refresh(order)
    return order_detail(db, user, order)


@deliveries_router.post("/{delivery_id}/confirm")
def confirm_delivery(delivery_id: int, db: Session = Depends(get_db),
                     user: User = Depends(require_permission("outsourced_food.update"))):
    """Confirm a draft delivery once. Its accepted food is added to the OPEN
    meal record of the same campus, date and exact session; with no record,
    or a CLOSED one, it waits (shown as pending). No stock is posted."""
    delivery = lock_delivery(db, user, delivery_id)
    if delivery.status != "DRAFT":
        raise HTTPException(status_code=409, detail=(
            f"{delivery.delivery_number} is already {delivery.status.lower()}."))
    order = lock_order(db, user, delivery.order_id)
    if order.status != "ORDERED":
        raise HTTPException(status_code=409, detail=f"{order.order_number} is {order.status.lower()}.")
    now = datetime.now(timezone.utc)
    delivery.status, delivery.confirmed_by, delivery.confirmed_at = "CONFIRMED", user.id, now
    touch(delivery)
    db.flush()
    lock_session(db, order.campus_id, order.meal_session_id)
    record = live_meal_record(db, order.campus_id, order.meal_date, order.meal_session_id, lock=True)
    added = attach_received(db, user, record) if record is not None and record.status == "OPEN" else []
    lines = delivery_lines(db, [delivery.id]).get(delivery.id, [])
    record_audit(db, user, "CONFIRM", DELIVERY_ENTITY, delivery.id, {
        **delivery_snapshot(delivery, lines), "order_number": order.order_number,
        "meal_record_id": record.id if record else None,
        "meal_record_status": record.status if record else None,
        "added_to_meal_record": len(added)})
    db.commit()
    db.refresh(order)
    return order_detail(db, user, order)


@deliveries_router.post("/{delivery_id}/cancel")
def cancel_delivery(delivery_id: int, payload: Reason, db: Session = Depends(get_db),
                    user: User = Depends(require_permission("outsourced_food.update"))):
    """Cancel a delivery with a reason. A draft: anyone with
    outsourced_food.update. A confirmed one: ADMIN or KITCHEN_MANAGER, only
    while none of its food has been distributed and its meal record is open;
    its received lines are then removed from that record."""
    delivery = lock_delivery(db, user, delivery_id)
    if delivery.status == "CANCELLED":
        raise HTTPException(status_code=409, detail=f"{delivery.delivery_number} is already cancelled.")
    lines = delivery_lines(db, [delivery.id]).get(delivery.id, [])
    removed = []
    if delivery.status == "CONFIRMED":
        if not is_manager(user):
            raise HTTPException(status_code=403, detail=(
                "A confirmed delivery can be cancelled only by an Admin or Kitchen Manager."))
        dishes = db.query(MealDish).filter(MealDish.source_delivery_line_id.in_([l.id for l in lines] or [0])).all()
        records = {}
        for rid in sorted({d.meal_record_id for d in dishes}):
            records[rid] = (db.query(MealRecord).filter(MealRecord.id == rid).with_for_update(key_share=True).one())
        units = dict(db.query(Unit.id, Unit.symbol).filter(Unit.id.in_({d.unit_id for d in dishes} or {0})))
        for dish in dishes:
            record = records[dish.meal_record_id]
            label = session_label(db, record.meal_session_id, record.meal_date)
            if record.status == "CLOSED":
                raise HTTPException(status_code=409, detail=(
                    f"{delivery.delivery_number} cannot be cancelled: its food is on the closed meal record of "
                    f"{label}, and a closed record is never changed. An Admin or Kitchen Manager must reopen that "
                    "record first."))
            has_leftovers = db.query(MealLeftover.id).filter(MealLeftover.dish_id == dish.id).first() is not None
            if dish.distributed_quantity is not None or has_leftovers:
                raise HTTPException(status_code=409, detail=(
                    f"{delivery.delivery_number} cannot be cancelled: {quantity_text(dish.received_quantity)} "
                    f"{units.get(dish.unit_id, '')} of {dish.dish_name} from this delivery already has its "
                    f"distribution recorded on the meal record of {label}. Food that has been served cannot be "
                    "un-delivered; clear the distribution on the meal record first if it was recorded by mistake."))
        for dish in dishes:
            record = records[dish.meal_record_id]
            removed.append({"meal_record_id": record.id, "dish_id": dish.id, "dish_name": dish.dish_name,
                            "quantity": quantity_text(dish.received_quantity), "unit_id": dish.unit_id,
                            "delivery_line_id": dish.source_delivery_line_id})
            db.delete(dish)
            db.flush()
            record.updated_at = datetime.now(timezone.utc)
        for rid in records:
            record_audit(db, user, "REMOVE_RECEIVED", MEAL_ENTITY, rid, {
                "delivery_id": delivery.id, "delivery_number": delivery.delivery_number, "reason": payload.reason,
                "lines": [r for r in removed if r["meal_record_id"] == rid]})
    previous = delivery.status
    now = datetime.now(timezone.utc)
    delivery.status, delivery.cancelled_by, delivery.cancelled_at, delivery.cancellation_reason = (
        "CANCELLED", user.id, now, payload.reason)
    touch(delivery)
    record_audit(db, user, "CANCEL", DELIVERY_ENTITY, delivery.id, {
        "reason": payload.reason, "previous_status": previous, "removed_from_meal_records": removed})
    db.commit()
    order = get_order(db, user, delivery.order_id)
    return order_detail(db, user, order)


# ============================================================
# SUPPLIER BILL LINKS (OUT01 criterion 6)
# ============================================================

def get_order_line(db: Session, user: User, line_id: int, lock: bool = False) -> OutsourcedOrderLine:
    query = db.query(OutsourcedOrderLine).filter(OutsourcedOrderLine.id == line_id,
                                                 OutsourcedOrderLine.campus_id == user.campus_id)
    if lock:
        query = query.with_for_update(key_share=True)
    line = query.first()
    if not line:
        raise HTTPException(status_code=404, detail="Outsourced order line not found")
    return line


def bill_candidates_query(db: Session, user: User, order: OutsourcedOrder, line: OutsourcedOrderLine):
    taken = db.query(OutsourcedOrderLine.purchase_item_id).filter(
        OutsourcedOrderLine.purchase_item_id.isnot(None), OutsourcedOrderLine.id != line.id)
    return (db.query(PurchaseItem, Purchase)
            .join(Purchase, Purchase.id == PurchaseItem.purchase_id)
            .filter(PurchaseItem.campus_id == user.campus_id, Purchase.campus_id == user.campus_id,
                    Purchase.supplier_id == order.supplier_id, PurchaseItem.item_id == line.item_id,
                    ~PurchaseItem.id.in_(taken)))


@lines_router.get("/{line_id}/bill-candidates")
def bill_candidates(line_id: int, db: Session = Depends(get_db),
                    user: User = Depends(both("outsourced_food.read", "purchase_bill.read"))):
    """Bill lines of the order's supplier for the same item that no other
    order line is linked to."""
    line = get_order_line(db, user, line_id)
    order = get_order(db, user, line.order_id)
    units = dict(db.query(Unit.id, Unit.symbol).filter(Unit.campus_id == user.campus_id))
    rows = bill_candidates_query(db, user, order, line).order_by(Purchase.purchase_date.desc(), PurchaseItem.id).all()
    return {"items": [{
        "purchase_item_id": pi.id, "purchase_id": bill.id, "invoice_number": bill.invoice_number,
        "purchase_date": bill.purchase_date.isoformat(), "quantity": quantity_text(pi.quantity),
        "unit_id": pi.unit_id, "unit_symbol": units.get(pi.unit_id), "unit_rate": rate_text(pi.unit_rate),
        "line_total": money_text(pi.line_total), "same_unit": pi.unit_id == line.unit_id,
        "linked_here": pi.id == line.purchase_item_id,
    } for pi, bill in rows]}


@lines_router.put("/{line_id}/bill-line")
def link_bill_line(line_id: int, payload: OutsourcedBillLinkInput, db: Session = Depends(get_db),
                   user: User = Depends(both("outsourced_food.read", "purchase_bill.update"))):
    """Link the supplier bill line that bills this order line: same campus,
    supplier, item and unit (no conversion assumed, Q7); one bill line per
    order line and one order line per bill line (database unique)."""
    line = get_order_line(db, user, line_id, lock=True)
    order = get_order(db, user, line.order_id)
    if order.status != "ORDERED":
        raise HTTPException(status_code=409, detail=(
            f"{order.order_number} is {order.status.lower()}; bill lines are linked to an ordered order."))
    if line.purchase_item_id is not None:
        if line.purchase_item_id == payload.purchase_item_id:
            return order_detail(db, user, order)
        raise HTTPException(status_code=409, detail="This order line is already linked to a bill line. Unlink it first.")
    found = (db.query(PurchaseItem, Purchase).join(Purchase, Purchase.id == PurchaseItem.purchase_id)
             .filter(PurchaseItem.id == payload.purchase_item_id, PurchaseItem.campus_id == user.campus_id,
                     Purchase.campus_id == user.campus_id).first())
    if not found:
        raise HTTPException(status_code=404, detail="Bill line not found")
    bill_line, bill = found
    item_name = db.query(Item.name).filter(Item.id == line.item_id).scalar()
    if bill.supplier_id != order.supplier_id:
        raise HTTPException(status_code=422, detail="That bill is from a different supplier than the order.")
    if bill_line.item_id != line.item_id:
        raise HTTPException(status_code=422, detail=f"That bill line is not for {item_name}.")
    if bill_line.unit_id != line.unit_id:
        units = dict(db.query(Unit.id, Unit.symbol).filter(Unit.id.in_({bill_line.unit_id, line.unit_id})))
        raise HTTPException(status_code=422, detail=(
            f"The bill line is in {units.get(bill_line.unit_id)} but the order line is in {units.get(line.unit_id)}. "
            "Link lines in the same unit; no conversion is assumed (client question Q7)."))
    line.purchase_item_id, line.linked_by, line.linked_at = bill_line.id, user.id, datetime.now(timezone.utc)
    try:
        db.flush()
        record_audit(db, user, "LINK_BILL", ORDER_ENTITY, order.id, {
            "order_line_id": line.id, "item_id": line.item_id, "purchase_item_id": bill_line.id,
            "bill": {"purchase_id": bill.id, "invoice_number": bill.invoice_number,
                     "line_total": money_text(bill_line.line_total)}})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="That bill line is already linked to another outsourced order line.")
    return order_detail(db, user, get_order(db, user, order.id))


@lines_router.delete("/{line_id}/bill-line")
def unlink_bill_line(line_id: int, db: Session = Depends(get_db),
                     user: User = Depends(both("outsourced_food.read", "purchase_bill.update"))):
    line = get_order_line(db, user, line_id, lock=True)
    order = get_order(db, user, line.order_id)
    if line.purchase_item_id is None:
        raise HTTPException(status_code=409, detail="This order line has no bill line linked.")
    previous = line.purchase_item_id
    line.purchase_item_id = line.linked_by = line.linked_at = None
    record_audit(db, user, "UNLINK_BILL", ORDER_ENTITY, order.id,
                 {"order_line_id": line.id, "purchase_item_id": previous})
    db.commit()
    return order_detail(db, user, get_order(db, user, order.id))


@bills_router.get("/{purchase_id}/outsourced-links")
def bill_outsourced_links(purchase_id: int, db: Session = Depends(get_db),
                          user: User = Depends(require_permission("purchase_bill.read"))):
    """The outsourced order lines this bill's lines are linked to (for the
    bill detail page)."""
    bill = db.query(Purchase).filter(Purchase.id == purchase_id, Purchase.campus_id == user.campus_id).first()
    if not bill:
        raise HTTPException(status_code=404, detail="Purchase not found")
    rows = (db.query(OutsourcedOrderLine, OutsourcedOrder, PurchaseItem)
            .join(OutsourcedOrder, OutsourcedOrder.id == OutsourcedOrderLine.order_id)
            .join(PurchaseItem, PurchaseItem.id == OutsourcedOrderLine.purchase_item_id)
            .filter(PurchaseItem.purchase_id == bill.id, OutsourcedOrderLine.campus_id == user.campus_id)
            .order_by(PurchaseItem.id).all())
    sessions = dict(db.query(MealSession.id, MealSession.name).filter(
        MealSession.id.in_({o.meal_session_id for _l, o, _p in rows} or {0})))
    return {"items": [{
        "purchase_item_id": pi.id, "order_line_id": line.id, "order_id": order.id,
        "order_number": order.order_number, "meal_date": order.meal_date.isoformat(),
        "meal_session_name": sessions.get(order.meal_session_id), "order_status": order.status,
    } for line, order, pi in rows]}


# ============================================================
# REPORT (OUT02, AT04)
# ============================================================

def build_report(db: Session, user: User, date_from: date, date_to: date, supplier_id: int | None = None,
                 item_id: int | None = None, meal_session_id: int | None = None) -> dict:
    """Ordered outsourced food by meal date: ordered, received, rejected and
    accepted (confirmed deliveries), what reached the meal records, and
    distributed, remaining and leftovers there. Costs (planned from the
    order, billed from linked bill lines) only with purchase_bill.read.
    Quantities are added up per unit only (no conversion, Q7)."""
    if date_from > date_to:
        raise HTTPException(status_code=422, detail="The start date cannot be after the end date.")
    if (date_to - date_from).days >= REPORT_MAX_DAYS:
        raise HTTPException(status_code=422, detail=f"Choose a period of at most {REPORT_MAX_DAYS} days.")
    campus_id = user.campus_id
    costs = sees_costs(db, user)
    query = (db.query(OutsourcedOrderLine, OutsourcedOrder)
             .join(OutsourcedOrder, OutsourcedOrder.id == OutsourcedOrderLine.order_id)
             .filter(OutsourcedOrder.campus_id == campus_id, OutsourcedOrder.status == "ORDERED",
                     OutsourcedOrder.meal_date >= date_from, OutsourcedOrder.meal_date <= date_to))
    if supplier_id:
        query = query.filter(OutsourcedOrder.supplier_id == supplier_id)
    if item_id:
        query = query.filter(OutsourcedOrderLine.item_id == item_id)
    if meal_session_id:
        query = query.filter(OutsourcedOrder.meal_session_id == meal_session_id)
    rows = query.order_by(OutsourcedOrder.meal_date, OutsourcedOrder.meal_session_id, OutsourcedOrder.id,
                          OutsourcedOrderLine.id).all()
    line_ids = [l.id for l, _o in rows]
    progress = delivery_progress(db, campus_id, line_ids)
    confirmed = (db.query(OutsourcedDeliveryLine.id, OutsourcedDeliveryLine.order_line_id)
                 .join(OutsourcedDelivery, OutsourcedDelivery.id == OutsourcedDeliveryLine.delivery_id)
                 .filter(OutsourcedDelivery.status == "CONFIRMED",
                         OutsourcedDeliveryLine.order_line_id.in_(line_ids or [0])).all())
    order_line_of = {dl_id: ol_id for dl_id, ol_id in confirmed}
    dishes = db.query(MealDish).filter(MealDish.source_delivery_line_id.in_(list(order_line_of) or [0])).all()
    leftovers: dict[int, dict[str, Decimal]] = {}
    for row in db.query(MealLeftover).filter(MealLeftover.dish_id.in_([d.id for d in dishes] or [0])):
        leftovers.setdefault(row.dish_id, {})[row.classification] = quantity(row.quantity)
    meal: dict[int, dict] = {}
    for dish in dishes:
        entry = meal.setdefault(order_line_of[dish.source_delivery_line_id], {
            "added": ZERO, "distributed": ZERO, "remaining": ZERO, "dishes": 0, "recorded": 0, "classified": 0,
            **{c: ZERO for c in LEFTOVER_CLASSES}, "records": set()})
        entry["added"] += quantity(dish.received_quantity)
        entry["dishes"] += 1
        entry["records"].add(dish.meal_record_id)
        if dish.distributed_quantity is not None:
            entry["recorded"] += 1
            entry["distributed"] += quantity(dish.distributed_quantity)
            entry["remaining"] += quantity(dish.remaining_quantity)
            classes = leftovers.get(dish.id, {})
            if sum(classes.values(), ZERO) == quantity(dish.remaining_quantity):
                entry["classified"] += 1
            for c, q in classes.items():
                entry[c] += q
    items = dict(db.query(Item.id, Item.name).filter(Item.id.in_({l.item_id for l, _o in rows} or {0})))
    units = dict(db.query(Unit.id, Unit.symbol).filter(Unit.campus_id == campus_id))
    sessions = dict(db.query(MealSession.id, MealSession.name).filter(MealSession.campus_id == campus_id))
    suppliers = dict(db.query(Supplier.id, Supplier.name).filter(Supplier.campus_id == campus_id))
    bills = {}
    if costs:
        linked = [l.purchase_item_id for l, _o in rows if l.purchase_item_id]
        for pi, bill in (db.query(PurchaseItem, Purchase).join(Purchase, Purchase.id == PurchaseItem.purchase_id)
                         .filter(PurchaseItem.id.in_(linked or [0]))):
            bills[pi.id] = (pi, bill)

    QTY = ("ordered", "received", "rejected", "accepted", "added", "pending", "distributed", "remaining",
           *(c.lower() for c in LEFTOVER_CLASSES))
    out_lines = []
    by_item: dict[tuple, dict] = {}
    by_unit: dict[int, dict] = {}
    planned_total = billed_total = ZERO
    unbilled = 0
    for line, order in rows:
        p = progress[line.id]
        m = meal.get(line.id)
        added = m["added"] if m else ZERO
        accepted = p["accepted"]
        values = {
            "ordered": quantity(line.ordered_quantity), "received": p["received"], "rejected": p["rejected"],
            "accepted": accepted, "added": added, "pending": max(accepted - added, ZERO),
            "distributed": m["distributed"] if m else ZERO, "remaining": m["remaining"] if m else ZERO,
            **{c.lower(): (m[c] if m else ZERO) for c in LEFTOVER_CLASSES},
        }
        if accepted <= 0:
            state = "NOT_DELIVERED" if p["received"] <= 0 else "ALL_REJECTED"
        elif added < accepted:
            state = "PENDING_MEAL_RECORD"
        elif m["recorded"] < m["dishes"]:
            state = "DISTRIBUTION_NOT_RECORDED"
        elif m["classified"] < m["dishes"]:
            state = "LEFTOVERS_NOT_CLASSIFIED"
        else:
            state = "RECONCILED"
        row = {
            "order_id": order.id, "order_number": order.order_number, "order_line_id": line.id,
            "meal_date": order.meal_date.isoformat(), "meal_session_id": order.meal_session_id,
            "meal_session_name": sessions.get(order.meal_session_id), "supplier_id": order.supplier_id,
            "supplier_name": suppliers.get(order.supplier_id), "item_id": line.item_id,
            "item_name": items.get(line.item_id), "unit_id": line.unit_id, "unit_symbol": units.get(line.unit_id),
            **{f"{k}_quantity": quantity_text(v) for k, v in values.items()},
            "distribution_recorded": bool(m) and m["recorded"] == m["dishes"],
            "meal_record_ids": sorted(m["records"]) if m else [],
            "status": state,
        }
        if costs:
            planned = money(line.line_total)
            bill = bills.get(line.purchase_item_id)
            planned_total += planned
            if bill:
                billed_total += money(bill[0].line_total)
            else:
                unbilled += 1
            row.update({"unit_rate": rate_text(line.unit_rate), "planned_cost": money_text(planned),
                        "billed_cost": money_text(bill[0].line_total) if bill else None,
                        "bill_invoice_number": bill[1].invoice_number if bill else None,
                        "bill_purchase_id": bill[1].id if bill else None})
        out_lines.append(row)
        key = (line.item_id, line.unit_id)
        group = by_item.setdefault(key, {"item_id": line.item_id, "item_name": items.get(line.item_id),
                                         "unit_id": line.unit_id, "unit_symbol": units.get(line.unit_id),
                                         "lines": 0, **{k: ZERO for k in QTY}, "planned": ZERO, "billed": ZERO})
        unit_group = by_unit.setdefault(line.unit_id, {"unit_id": line.unit_id, "unit_symbol": units.get(line.unit_id),
                                                       "lines": 0, **{k: ZERO for k in QTY}})
        for target in (group, unit_group):
            target["lines"] += 1
            for k, v in values.items():
                target[k] += v
        if costs:
            group["planned"] += money(line.line_total)
            if bills.get(line.purchase_item_id):
                group["billed"] += money(bills[line.purchase_item_id][0].line_total)

    def finish(group: dict, with_money: bool) -> dict:
        out = {k: v for k, v in group.items() if k not in QTY and k not in ("planned", "billed")}
        out.update({f"{k}_quantity": quantity_text(group[k]) for k in QTY})
        if with_money and costs:
            out.update({"planned_cost": money_text(group["planned"]), "billed_cost": money_text(group["billed"])})
        return out

    campus_name = db.query(Campus.name).filter(Campus.id == campus_id).scalar()
    report = {
        "campus": {"id": campus_id, "name": campus_name},
        "period": {"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
        "filters": {"supplier_id": supplier_id, "supplier_name": suppliers.get(supplier_id) if supplier_id else None,
                    "item_id": item_id, "item_name": db.query(Item.name).filter(
                        Item.id == item_id, Item.campus_id == campus_id).scalar() if item_id else None,
                    "meal_session_id": meal_session_id,
                    "meal_session_name": sessions.get(meal_session_id) if meal_session_id else None},
        "lines": out_lines,
        "by_item": [finish(g, True) for g in sorted(by_item.values(), key=lambda g: ((g["item_name"] or "").lower(),
                                                                                       g["unit_symbol"] or ""))],
        "totals_by_unit": [finish(g, False) for g in sorted(by_unit.values(), key=lambda g: g["unit_symbol"] or "")],
        "line_count": len(out_lines),
        "unreconciled_count": sum(1 for r in out_lines if r["status"] not in ("RECONCILED", "ALL_REJECTED")),
        "rejected_note": Q6_NOTE if any(quantity(r["rejected_quantity"]) > 0 for r in out_lines) else None,
        "costs_visible": costs,
        "basis": {
            "orders": "Ordered outsourced orders with a meal date in the period (drafts and cancelled orders are "
                      "not included).",
            "quantities": "Received, rejected and accepted from confirmed deliveries; added, distributed, remaining "
                          "and leftovers from the meal records of the exact meal session. Quantities are added up "
                          "per unit only; no conversion is assumed.",
            "costs": "Planned cost = ordered quantity × order rate. Purchase expenditure comes only from the "
                     "supplier bill lines linked to the order lines; the planned cost is never added to it.",
            "rejected": Q6_NOTE,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    if costs:
        report["cost_totals"] = {"planned_cost": money_text(planned_total), "billed_cost": money_text(billed_total),
                                 "lines_without_bill": unbilled}
    return report


@report_router.get("/report")
def outsourced_report(
    date_from: date = Query(...),
    date_to: date = Query(...),
    supplier_id: int | None = Query(default=None, gt=0),
    item_id: int | None = Query(default=None, gt=0),
    meal_session_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("outsourced_food.read")),
):
    return build_report(db, user, date_from, date_to, supplier_id, item_id, meal_session_id)


@report_router.post("/report/export")
def export_outsourced_report(payload: OutsourcedReportExportInput, db: Session = Depends(get_db),
                             user: User = Depends(require_permission("outsourced_food.read"))):
    """The same report as an Excel or PDF file, built by build_report with
    the same filters (and the same cost rule) as the screen. A POST so the
    CSRF check applies; every export writes an audit row."""
    from app.services.outsourced_exports import export_filename, render_pdf, render_xlsx
    from app.services.report_exports import EXPORT_MEDIA_TYPES

    report = build_report(db, user, payload.date_from, payload.date_to, payload.supplier_id, payload.item_id,
                          payload.meal_session_id)
    content = render_xlsx(report, user.full_name) if payload.format == "xlsx" else render_pdf(report, user.full_name)
    filename = export_filename(report, payload.format)
    record_audit(db, user, "EXPORT", "OUTSOURCED_REPORT", None, {
        "report": "outsourced_food", "format": payload.format, "file_name": filename, **report["period"],
        **{k: v for k, v in report["filters"].items()}, "lines": report["line_count"],
        "costs_included": report["costs_visible"], "bytes": len(content)})
    db.commit()
    return Response(content=content, media_type=EXPORT_MEDIA_TYPES[payload.format], headers={
        "Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"})
