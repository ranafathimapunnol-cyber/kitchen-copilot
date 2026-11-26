"""Stock ledger (Stage 4, slice 4a): balances, low stock and the
replenishment list, the item ledger, and opening stock.

Permissions (decision S1, approved 23 November 2026):
- balances, replenishment list and item ledger: inventory.read;
- opening stock (record, list, reverse): ADMIN and KITCHEN_MANAGER only,
  checked by role, never assignable to STAFF (decision S3).
Every query is limited to the signed-in user's campus.
"""

from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import require_permission, require_roles
from app.api.routes.master_data import get_unit_conversion_factor, record_audit
from app.core.clock import campus_today, utc_iso
from app.db.session import get_db
from app.models.master_data import Category, Item, Supplier, Unit
from app.models.purchases import GoodsReceipt, Purchase, StockMovement
from app.models.stock import StockOpening
from app.models.user import User, UserRole
from app.services.outsourced_guard import outsourced_message
from app.services import stock_ledger
from app.services.stock_ledger import (
    Posting,
    balance_expression,
    quantity,
    quantity_text,
    start_of_campus_day,
)

router = APIRouter(prefix="/api/stock", tags=["Stock Ledger"])

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
FACTOR_STEP = Decimal("0.000000000001")  # stock_openings.conversion_factor scale 12

stock_managers = require_roles(UserRole.ADMIN, UserRole.KITCHEN_MANAGER)


def page_meta(total: int, page: int, page_size: int) -> dict:
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


def like_contains(term: str) -> str:
    escaped = term.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def user_names(db: Session, ids) -> dict[int, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return dict(db.query(User.id, User.full_name).filter(User.id.in_(ids)).all())


def balances_subquery(db: Session, campus_id: int):
    return (
        db.query(
            StockMovement.item_id.label("item_id"),
            balance_expression().label("balance"),
            func.max(StockMovement.effective_at).label("last_movement_at"),
        )
        .filter(StockMovement.campus_id == campus_id)
        .group_by(StockMovement.item_id)
        .subquery()
    )


def balance_row(item: Item, category_name, unit_symbol, balance, last_at) -> dict:
    balance = Decimal(str(balance or 0))
    minimum = Decimal(str(item.minimum_stock or 0))
    below = minimum > 0 and balance < minimum
    return {
        "item_id": item.id,
        "item_name": item.name,
        "category_id": item.category_id,
        "category_name": category_name,
        "unit_id": item.standard_unit_id,
        "unit_symbol": unit_symbol,
        "is_active": bool(item.is_active),
        "balance": quantity_text(balance),
        "minimum_stock": quantity_text(minimum),
        "has_minimum": minimum > 0,
        "below_minimum": below,
        "shortfall": quantity_text(minimum - balance) if below else "0.000",
        "last_movement_at": utc_iso(last_at) if last_at else None,
    }


# ============================================================
# BALANCES (STK04 criteria 1 and 2)
# Permission: inventory.read
# ============================================================

@router.get("/balances")
def stock_balances(
    search: str | None = Query(default=None, max_length=100),
    category_id: int | None = Query(default=None, gt=0),
    below_minimum: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("inventory.read")),
):
    """Every active item, and any inactive item still holding stock, with
    its balance calculated from posted movements, in its standard unit."""
    campus_id = user.campus_id
    sums = balances_subquery(db, campus_id)
    balance = func.coalesce(sums.c.balance, 0)
    below = and_(Item.minimum_stock > 0, balance < Item.minimum_stock)

    query = (
        db.query(Item, Category.name, Unit.symbol, balance, sums.c.last_movement_at)
        .outerjoin(sums, sums.c.item_id == Item.id)
        .outerjoin(Category, and_(Category.id == Item.category_id, Category.campus_id == campus_id))
        .outerjoin(Unit, and_(Unit.id == Item.standard_unit_id, Unit.campus_id == campus_id))
        .filter(Item.campus_id == campus_id)
        .filter(or_(Item.is_active.is_(True), balance != 0))
    )

    summary_base = query.order_by(None)
    summary = {
        "items": summary_base.count(),
        "below_minimum": summary_base.filter(below).count(),
        "zero_or_less": summary_base.filter(balance <= 0).count(),
        "without_minimum": summary_base.filter(Item.minimum_stock <= 0).count(),
    }

    if search and search.strip():
        query = query.filter(func.lower(Item.name).like(like_contains(search.strip()), escape="\\"))
    if category_id is not None:
        query = query.filter(Item.category_id == category_id)
    if below_minimum:
        query = query.filter(below)

    total = query.count()
    rows = (
        query.order_by(func.lower(Item.name), Item.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [balance_row(*row) for row in rows],
        "summary": summary,
        **page_meta(total, page, page_size),
    }


# ============================================================
# REPLENISHMENT LIST (STK04 criterion 3)
# Permission: inventory.read
# ============================================================

@router.get("/replenishment")
def replenishment_list(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("inventory.read")),
):
    """Active items below their configured minimum stock, with the quantity
    needed to reach the minimum, grouped by category. Items without a
    minimum (0) are never listed."""
    campus_id = user.campus_id
    sums = balances_subquery(db, campus_id)
    balance = func.coalesce(sums.c.balance, 0)
    rows = (
        db.query(Item, Category.name, Unit.symbol, balance, sums.c.last_movement_at)
        .outerjoin(sums, sums.c.item_id == Item.id)
        .outerjoin(Category, and_(Category.id == Item.category_id, Category.campus_id == campus_id))
        .outerjoin(Unit, and_(Unit.id == Item.standard_unit_id, Unit.campus_id == campus_id))
        .filter(
            Item.campus_id == campus_id,
            Item.is_active.is_(True),
            Item.minimum_stock > 0,
            balance < Item.minimum_stock,
        )
        .order_by(func.lower(func.coalesce(Category.name, "")), func.lower(Item.name), Item.id)
        .all()
    )
    return {
        "generated_at": utc_iso(datetime.now(timezone.utc)),
        "campus_date": campus_today().isoformat(),
        "items": [balance_row(*row) for row in rows],
        "total": len(rows),
    }


# ============================================================
# ITEM LEDGER (STK01)
# Permission: inventory.read
# ============================================================

def movement_sources(db: Session, campus_id: int, movements) -> dict:
    receipt_ids = {m.reference_id for m in movements if m.reference_type == "GOODS_RECEIPT"}
    receipts = {
        receipt_id: {"invoice_number": invoice, "supplier_name": supplier}
        for receipt_id, invoice, supplier in (
            db.query(GoodsReceipt.id, Purchase.invoice_number, Supplier.name)
            .join(Purchase, Purchase.id == GoodsReceipt.purchase_id)
            .outerjoin(Supplier, Supplier.id == Purchase.supplier_id)
            .filter(GoodsReceipt.campus_id == campus_id, GoodsReceipt.id.in_(receipt_ids or {0}))
        )
    }
    return receipts


def movement_payload(movement, balance_after, receipts, reversed_by, names, unit_symbol, documents=None) -> dict:
    receipt = receipts.get(movement.reference_id) if movement.reference_type == "GOODS_RECEIPT" else None
    document = (documents or {}).get((movement.reference_type, movement.reference_id))
    return {
        "id": movement.id,
        "movement_type": movement.movement_type,
        "direction": movement.direction,
        "quantity": quantity_text(movement.quantity),
        "signed_quantity": quantity_text(stock_ledger.signed_quantity(movement.direction, movement.quantity)),
        "balance_after": quantity_text(balance_after) if balance_after is not None else None,
        "unit_symbol": unit_symbol,
        "effective_at": utc_iso(movement.effective_at),
        "created_at": utc_iso(movement.created_at),
        "source_key": movement.source_key,
        "reference_type": movement.reference_type,
        "reference_id": movement.reference_id,
        "receipt_id": movement.reference_id if movement.reference_type == "GOODS_RECEIPT" else None,
        "opening_id": movement.reference_id if movement.reference_type == "STOCK_OPENING" else None,
        "invoice_number": receipt["invoice_number"] if receipt else None,
        "supplier_name": receipt["supplier_name"] if receipt else None,
        "document_number": document[0] if document else None,
        "kitchen_issue_id": document[1] if document else None,
        "stock_count_id": document[2] if document else None,
        "reversal_of_id": movement.reversal_of_id,
        "reversed_by_movement_id": reversed_by.get(movement.id),
        "remarks": movement.remarks,
        "created_by_name": names.get(movement.created_by),
    }


@router.get("/items/{item_id}/ledger")
def item_ledger(
    item_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("inventory.read")),
):
    """Every movement of one item, newest first, with the running balance
    after each (replayed in ledger order: effective time, then posting
    order)."""
    campus_id = user.campus_id
    item = db.query(Item).filter(Item.id == item_id, Item.campus_id == campus_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    unit_symbol = db.query(Unit.symbol).filter(Unit.id == item.standard_unit_id).scalar()
    category_name = db.query(Category.name).filter(Category.id == item.category_id).scalar()
    replayed = stock_ledger.running_balances(stock_ledger.ledger_movements(db, campus_id, item.id))
    balance = replayed[-1][1] if replayed else Decimal("0")

    newest_first = list(reversed(replayed))
    total = len(newest_first)
    window = newest_first[(page - 1) * page_size: page * page_size]
    movements = [m for m, _b in window]
    reversed_by = {
        original_id: reversal_id
        for reversal_id, original_id in db.query(StockMovement.id, StockMovement.reversal_of_id).filter(
            StockMovement.campus_id == campus_id,
            StockMovement.reversal_of_id.in_([m.id for m in movements] or [0]),
        )
    }
    receipts = movement_sources(db, campus_id, movements)
    documents = stock_ledger.movement_documents(db, campus_id, movements)
    names = user_names(db, [m.created_by for m in movements])

    summary = balance_row(item, category_name, unit_symbol, balance,
                          replayed[-1][0].effective_at if replayed else None)
    return {
        "item": summary,
        "movements": [
            movement_payload(m, b, receipts, reversed_by, names, unit_symbol, documents) for m, b in window
        ],
        **page_meta(total, page, page_size),
    }


# ============================================================
# OPENING STOCK (STK01, decision S3)
# ADMIN and KITCHEN_MANAGER only
# ============================================================

class OpeningLineInput(BaseModel):
    item_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, max_digits=15, decimal_places=3)
    # The unit the quantity was counted in; the item's standard unit if omitted.
    unit_id: int | None = Field(default=None, gt=0)
    remarks: str | None = Field(default=None, max_length=500)


class OpeningCreate(BaseModel):
    effective_date: date
    lines: list[OpeningLineInput] = Field(min_length=1, max_length=200)
    remarks: str | None = Field(default=None, max_length=500)


class ReverseInput(BaseModel):
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def reason_not_blank(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Give a reason for the reversal (at least 3 characters).")
        return value


def opening_payload(opening: StockOpening, items, units, names, movements) -> dict:
    movement = movements.get(f"OPENING:{opening.id}")
    reversal = movements.get(f"REVERSAL:{movement.id}") if movement else None
    return {
        "id": opening.id,
        "item_id": opening.item_id,
        "item_name": items.get(opening.item_id),
        "quantity": quantity_text(opening.quantity),
        "unit_id": opening.unit_id,
        "unit_symbol": units.get(opening.unit_id),
        "conversion_factor": format(Decimal(str(opening.conversion_factor)).normalize(), "f"),
        "standard_quantity": quantity_text(opening.standard_quantity),
        "standard_unit_symbol": units.get(opening.standard_unit_id),
        "effective_date": opening.effective_date.isoformat(),
        "remarks": opening.remarks,
        "status": opening.status,
        "created_by_name": names.get(opening.created_by),
        "created_at": utc_iso(opening.created_at),
        "movement_id": movement.id if movement else None,
        "reversed_by_name": names.get(opening.reversed_by),
        "reversed_at": utc_iso(opening.reversed_at) if opening.reversed_at else None,
        "reversal_reason": opening.reversal_reason,
        "reversal_movement_id": reversal.id if reversal else None,
    }


def openings_payload(db: Session, campus_id: int, openings: list[StockOpening]) -> list[dict]:
    if not openings:
        return []
    item_ids = {o.item_id for o in openings}
    unit_ids = {o.unit_id for o in openings} | {o.standard_unit_id for o in openings}
    items = dict(db.query(Item.id, Item.name).filter(Item.id.in_(item_ids)))
    units = dict(db.query(Unit.id, Unit.symbol).filter(Unit.id.in_(unit_ids)))
    names = user_names(db, [o.created_by for o in openings] + [o.reversed_by for o in openings])
    opening_keys = [f"OPENING:{o.id}" for o in openings]
    rows = db.query(StockMovement).filter(
        StockMovement.campus_id == campus_id,
        StockMovement.source_key.in_(opening_keys),
    ).all()
    reversal_keys = [f"REVERSAL:{m.id}" for m in rows]
    rows += db.query(StockMovement).filter(
        StockMovement.campus_id == campus_id,
        StockMovement.source_key.in_(reversal_keys or ["-"]),
    ).all()
    movements = {m.source_key: m for m in rows}
    return [opening_payload(o, items, units, names, movements) for o in openings]


@router.get("/openings")
def list_openings(
    status: str | None = Query(default=None, pattern="^(ACTIVE|REVERSED)$"),
    search: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
    user: User = Depends(stock_managers),
):
    campus_id = user.campus_id
    query = (
        db.query(StockOpening)
        .join(Item, Item.id == StockOpening.item_id)
        .filter(StockOpening.campus_id == campus_id)
    )
    counts = dict(
        db.query(StockOpening.status, func.count(StockOpening.id))
        .filter(StockOpening.campus_id == campus_id)
        .group_by(StockOpening.status)
    )
    if status:
        query = query.filter(StockOpening.status == status)
    if search and search.strip():
        query = query.filter(func.lower(Item.name).like(like_contains(search.strip()), escape="\\"))
    total = query.count()
    openings = (
        query.order_by(StockOpening.created_at.desc(), StockOpening.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    active_item_ids = [
        item_id for (item_id,) in db.query(StockOpening.item_id).filter(
            StockOpening.campus_id == campus_id, StockOpening.status == "ACTIVE"
        )
    ]
    return {
        "items": openings_payload(db, campus_id, openings),
        "status_counts": {"ACTIVE": counts.get("ACTIVE", 0), "REVERSED": counts.get("REVERSED", 0)},
        "items_with_active_opening": sorted(active_item_ids),
        **page_meta(total, page, page_size),
    }


@router.post("/openings", status_code=201)
def record_opening_stock(
    payload: OpeningCreate,
    db: Session = Depends(get_db),
    user: User = Depends(stock_managers),
):
    """Record opening stock for one or more items, all or nothing. Each line
    creates an opening entry and one OPENING movement effective at 00:00
    campus time on the effective date."""
    campus_id = user.campus_id
    if payload.effective_date > campus_today():
        raise HTTPException(status_code=422, detail="Opening stock cannot be dated in the future.")

    item_ids = [line.item_id for line in payload.lines]
    if len(item_ids) != len(set(item_ids)):
        raise HTTPException(status_code=422, detail="Each item can appear only once.")

    # Lock the items first: a second opening for the same item waits here and
    # then finds the first one (the partial unique index is the final guard).
    items = stock_ledger.lock_items(db, campus_id, item_ids)

    active = dict(
        db.query(StockOpening.item_id, StockOpening.id).filter(
            StockOpening.campus_id == campus_id,
            StockOpening.status == "ACTIVE",
            StockOpening.item_id.in_(item_ids),
        )
    )
    prepared = []
    for line in payload.lines:
        item = items[line.item_id]
        if not item.is_active:
            raise HTTPException(status_code=422, detail=f"{item.name} is inactive.")
        if item.item_kind == "OUTSOURCED":
            raise HTTPException(status_code=422, detail=outsourced_message([item.name], "given opening stock"))
        if item.id in active:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"{item.name} already has opening stock (entry #{active[item.id]}). "
                    "Reverse it first to enter a new one."
                ),
            )
        unit_id = line.unit_id or item.standard_unit_id
        unit = db.query(Unit).filter(Unit.id == unit_id, Unit.campus_id == campus_id).first()
        if not unit:
            raise HTTPException(status_code=422, detail=f"Unit not found for {item.name}.")
        if unit.id != item.standard_unit_id and not unit.is_active:
            raise HTTPException(status_code=422, detail=f"{unit.name} is inactive.")
        factor = get_unit_conversion_factor(db, user, unit.id, item.standard_unit_id)
        factor = factor.quantize(FACTOR_STEP)
        standard_quantity = quantity(line.quantity * factor)
        if factor <= 0 or standard_quantity <= 0:
            raise HTTPException(
                status_code=422,
                detail=f"{item.name}: the quantity is too small to record in its standard unit.",
            )
        prepared.append((item, line, unit, factor, standard_quantity))

    effective_at = start_of_campus_day(payload.effective_date)
    try:
        openings = []
        for item, line, unit, factor, standard_quantity in prepared:
            opening = StockOpening(
                campus_id=campus_id,
                item_id=item.id,
                quantity=quantity(line.quantity),
                unit_id=unit.id,
                conversion_factor=factor,
                standard_quantity=standard_quantity,
                standard_unit_id=item.standard_unit_id,
                effective_date=payload.effective_date,
                remarks=(line.remarks or payload.remarks or None),
                status="ACTIVE",
                created_by=user.id,
            )
            db.add(opening)
            openings.append(opening)
        db.flush()

        movements = stock_ledger.post(db, user, [
            Posting(
                item_id=o.item_id,
                movement_type="OPENING",
                direction=1,
                quantity=Decimal(str(o.standard_quantity)),
                unit_id=o.standard_unit_id,
                effective_at=effective_at,
                source_key=f"OPENING:{o.id}",
                reference_type="STOCK_OPENING",
                reference_id=o.id,
                remarks=o.remarks,
            )
            for o in openings
        ])
        for opening, movement in zip(openings, movements):
            record_audit(db, user, "CREATE", "STOCK_OPENING", opening.id, {
                "item_id": opening.item_id,
                "quantity": quantity_text(opening.quantity),
                "unit_id": opening.unit_id,
                "conversion_factor": format(Decimal(str(opening.conversion_factor)).normalize(), "f"),
                "standard_quantity": quantity_text(opening.standard_quantity),
                "standard_unit_id": opening.standard_unit_id,
                "effective_date": opening.effective_date.isoformat(),
                "movement_id": movement.id,
            })
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Opening stock was recorded for one of these items at the same time. Reload and try again.",
        )

    for opening in openings:
        db.refresh(opening)
    return {"items": openings_payload(db, campus_id, openings)}


@router.post("/openings/{opening_id}/reverse")
def reverse_opening_stock(
    opening_id: int,
    payload: ReverseInput,
    db: Session = Depends(get_db),
    user: User = Depends(stock_managers),
):
    """Reverse an opening entry (decision S3/S4): a REVERSAL movement,
    effective now, undoes its OPENING movement, which keeps its own date.
    The entry stays as history with status REVERSED; a new opening can
    then be entered. Refused if the balance would go below zero."""
    campus_id = user.campus_id
    opening = (
        db.query(StockOpening)
        .filter(StockOpening.id == opening_id, StockOpening.campus_id == campus_id)
        .with_for_update()
        .first()
    )
    if not opening:
        raise HTTPException(status_code=404, detail="Opening stock entry not found")
    if opening.status != "ACTIVE":
        raise HTTPException(status_code=409, detail="This opening stock entry has already been reversed.")

    original = (
        db.query(StockMovement)
        .filter(
            StockMovement.campus_id == campus_id,
            StockMovement.source_key == f"OPENING:{opening.id}",
        )
        .first()
    )
    if not original:
        raise HTTPException(status_code=409, detail="The opening movement for this entry was not found.")

    now = datetime.now(timezone.utc)
    try:
        (reversal,) = stock_ledger.post(db, user, [stock_ledger.reversal_of(original, payload.reason, now)])
        opening.status = "REVERSED"
        opening.reversed_by = user.id
        opening.reversed_at = now
        opening.reversal_reason = payload.reason
        record_audit(db, user, "REVERSE", "STOCK_OPENING", opening.id, {
            "item_id": opening.item_id,
            "reason": payload.reason,
            "movement_id": original.id,
            "reversal_movement_id": reversal.id,
            "standard_quantity": quantity_text(opening.standard_quantity),
            "original_effective_at": utc_iso(original.effective_at),
            "reversal_effective_at": utc_iso(now),
        })
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="This opening stock entry has already been reversed.")

    db.refresh(opening)
    return openings_payload(db, campus_id, [opening])[0]
