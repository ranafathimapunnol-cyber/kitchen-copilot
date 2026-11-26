"""Physical stock counts and adjustments (Stage 4 slice 4c: STK05, AT02).

Decisions applied (docs/STAGE-4-STOCK-PLAN.md):
- S1: stock_count.create records a count and raises an adjustment from one
  of its lines; stock_count.read views counts and adjustments. Both codes
  are STAFF-assignable and in the KITCHEN_MANAGER set. Approving and
  rejecting are ADMIN and KITCHEN_MANAGER work, checked by role.
- S6, blind counts: the count form's options never carry a stock balance.
  When a count is saved the server records, per line, the system balance at
  that moment, the physical quantity and the difference; they are never
  recalculated and the count is never changed. An adjustment is raised from
  a line by an explicit action, never automatically; at most one is PENDING
  per item per campus. Only an ADMIN or KITCHEN_MANAGER who did not perform
  the count may approve or reject it (this API and a database check).
  Approval posts the difference measured at count time as one ADJUSTMENT
  movement, effective at the count time and created at approval. Rejection
  posts nothing, keeps the reason, and a new count is needed.
- S2: a negative adjustment goes through the shared posting check, so no
  balance goes below zero at any point from the count time onwards.
- Q10 (interim, no fallback): without an eligible approver the adjustment
  stays PENDING and the response says why.

Movements between the count and the approval:
- A movement effective after the count time (an issue, receipt or return
  recorded after the count) is kept as it is and follows the adjustment in
  the ledger, so after approval the balance at the count time equals the
  physical count and today's balance is that count plus everything since.
- A movement effective at or before the count time but posted after the
  count was saved (a late kitchen issue, an opening entry, another count's
  adjustment) changes the ledger at the count time, so the stored
  difference no longer reconciles it. Raising or approving is then refused
  and the item is counted again. The ledger is never edited.

Every query is limited to the signed-in user's campus. Lock order, as in
the kitchen routes: campus (numbering), adjustment, then items (posting).
"""

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import require_permission, require_roles, user_has_permission
from app.api.routes.kitchen import FACTOR_STEP, Reason, clean, names_of, next_number, page_meta
from app.api.routes.master_data import get_unit_conversion_factor, record_audit
from app.core.clock import campus_timezone, campus_today, utc_iso
from app.db.session import get_db
from app.models.master_data import Category, Item, Unit, UnitConversion
from app.models.purchases import StockMovement
from app.models.stock import StockAdjustment, StockCount, StockCountItem
from app.models.user import User, UserRole
from app.services.outsourced_guard import not_outsourced, outsourced_message
from app.services import stock_ledger
from app.services.stock_ledger import Posting, as_utc, quantity, quantity_text

router = APIRouter(tags=["Stock Counts and Adjustments"])

ZERO = Decimal("0")
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
MAX_COUNT_LINES = 500

stock_managers = require_roles(UserRole.ADMIN, UserRole.KITCHEN_MANAGER)

COUNTER_CANNOT_DECIDE = (
    "You performed this count, so another Admin or Kitchen Manager must approve or "
    "reject its adjustment (independent approval, STK05)."
)


# ============================================================
# INPUT
# ============================================================

class CountLineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: int = Field(gt=0)
    # The physical quantity found; 0 when none was found.
    quantity: Decimal = Field(ge=0, max_digits=15, decimal_places=3)
    unit_id: int | None = Field(default=None, gt=0)
    remarks: str | None = Field(default=None, max_length=500)


class CountInput(BaseModel):
    # extra="forbid": a client cannot send a system balance or a difference;
    # the server records them when the count is saved.
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=500)
    remarks: str | None = Field(default=None, max_length=500)
    lines: list[CountLineInput] = Field(min_length=1, max_length=MAX_COUNT_LINES)

    @field_validator("reason")
    @classmethod
    def at_least_three(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Give the reason for the count (at least 3 characters).")
        return value


class DecisionNote(BaseModel):
    note: str | None = Field(default=None, max_length=500)


# ============================================================
# HELPERS
# ============================================================

def count_conversion(db: Session, user: User, item: Item, unit_id: int | None, amount: Decimal):
    """(unit, factor, standard quantity) for a counted quantity entered in
    `unit_id` (the item's standard unit if omitted). Explicit conversions
    only (ADR-007). Zero is allowed: nothing was found."""
    unit = db.query(Unit).filter(Unit.id == (unit_id or item.standard_unit_id), Unit.campus_id == user.campus_id).first()
    if not unit:
        raise HTTPException(status_code=422, detail=f"Unit not found for {item.name}.")
    if unit.id != item.standard_unit_id and not unit.is_active:
        raise HTTPException(status_code=422, detail=f"{unit.name} is inactive.")
    factor = get_unit_conversion_factor(db, user, unit.id, item.standard_unit_id).quantize(FACTOR_STEP)
    if factor <= 0:
        raise HTTPException(status_code=422, detail=f"{item.name}: the unit conversion is not usable.")
    standard = quantity(amount * factor)
    if amount > 0 and standard <= 0:
        raise HTTPException(status_code=422, detail=f"{item.name}: the quantity is too small to record in its standard unit.")
    return unit, factor, standard


def balances_at(db: Session, campus_id: int, item_ids, moment: datetime) -> dict[int, Decimal]:
    """Each item's ledger balance after every movement effective at or before `moment`."""
    ids = set(item_ids)
    if not ids:
        return {}
    rows = (
        db.query(StockMovement.item_id, stock_ledger.balance_expression())
        .filter(
            StockMovement.campus_id == campus_id,
            StockMovement.item_id.in_(ids),
            StockMovement.effective_at <= as_utc(moment),
        )
        .group_by(StockMovement.item_id)
    )
    found = {item_id: Decimal(str(total or 0)) for item_id, total in rows}
    return {item_id: found.get(item_id, ZERO) for item_id in ids}


def count_lines(db: Session, count_id: int) -> list[StockCountItem]:
    return db.query(StockCountItem).filter(StockCountItem.count_id == count_id).order_by(StockCountItem.id).all()


def get_count(db: Session, user: User, count_id: int) -> StockCount:
    count = db.query(StockCount).filter(StockCount.id == count_id, StockCount.campus_id == user.campus_id).first()
    if not count:
        raise HTTPException(status_code=404, detail="Stock count not found")
    return count


def lock_adjustment(db: Session, user: User, adjustment_id: int) -> StockAdjustment:
    adjustment = (
        db.query(StockAdjustment)
        .filter(StockAdjustment.id == adjustment_id, StockAdjustment.campus_id == user.campus_id)
        .with_for_update()
        .first()
    )
    if not adjustment:
        raise HTTPException(status_code=404, detail="Stock adjustment not found")
    return adjustment


def item_label(db: Session, item_id: int) -> tuple[str, str]:
    name, unit_id = db.query(Item.name, Item.standard_unit_id).filter(Item.id == item_id).one()
    symbol = db.query(Unit.symbol).filter(Unit.id == unit_id).scalar() or ""
    return name, symbol


def ledger_changed_message(item_name: str, unit: str, count_number: str, recorded: Decimal, now_at_count: Decimal) -> str:
    return (
        f"The ledger for {item_name} at the time of {count_number} has changed since the count was saved: "
        f"the count recorded a system balance of {quantity_text(recorded)} {unit}, and the ledger now shows "
        f"{quantity_text(now_at_count)} {unit} at that time, because a movement dated on or before the count was "
        f"posted afterwards. The stored difference would no longer give the counted quantity. Count {item_name} again."
    )


def eligible_approver_count(db: Session, campus_id: int, counted_by: int) -> int:
    """Active ADMIN and KITCHEN_MANAGER users of the campus other than the counter."""
    return (
        db.query(func.count(User.id))
        .filter(
            User.campus_id == campus_id,
            User.is_active.is_(True),
            User.role.in_((UserRole.ADMIN, UserRole.KITCHEN_MANAGER)),
            User.id != counted_by,
        )
        .scalar()
        or 0
    )


def adjustment_posting(adjustment: StockAdjustment, line: StockCountItem, count: StockCount) -> Posting:
    """The difference measured at count time, effective at the count time."""
    difference = Decimal(str(line.difference))
    return Posting(
        item_id=adjustment.item_id,
        movement_type="ADJUSTMENT",
        direction=1 if difference > 0 else -1,
        quantity=abs(difference),
        unit_id=line.standard_unit_id,
        effective_at=count.counted_at,
        source_key=f"ADJUSTMENT:{adjustment.id}",
        reference_type="STOCK_ADJUSTMENT",
        reference_id=adjustment.id,
        remarks=adjustment.reason,
    )


def approval_state(db: Session, campus_id: int, adjustment: StockAdjustment, line: StockCountItem,
                   count: StockCount) -> dict:
    """What an approver needs to see, and what the approval would check:
    the balance at the count time then and now, today's balance, the
    movements posted since the count, and (while pending) whether the
    ledger at the count time changed or the adjustment would take a
    balance below zero."""
    movements = stock_ledger.ledger_movements(db, campus_id, adjustment.item_id)
    own_key = f"ADJUSTMENT:{adjustment.id}"
    counted_at = as_utc(count.counted_at)
    recorded = Decimal(str(line.system_balance))
    others = [m for m in movements if m.source_key != own_key]
    at_count_now = stock_ledger.balance_at(others, counted_at)
    balance_now = stock_ledger.balance_at(movements, datetime.max.replace(tzinfo=timezone.utc))
    since = [m for m in movements if as_utc(m.created_at) > counted_at and m.source_key != own_key]
    state = {
        "system_balance_at_count": quantity_text(recorded),
        "count_time_balance_now": quantity_text(at_count_now),
        "ledger_changed": at_count_now != recorded,
        "balance_now": quantity_text(balance_now),
        "balance_after_approval": None,
        "movements_since_count": since,
        "shortfall": None,
    }
    if adjustment.status == "PENDING":
        state["balance_after_approval"] = quantity_text(balance_now + Decimal(str(line.difference)))
        if not state["ledger_changed"] and Decimal(str(line.difference)) < 0:
            shortfall = stock_ledger.find_shortfall(movements, [adjustment_posting(adjustment, line, count)])
            if shortfall is not None:
                moment, lowest = shortfall
                state["shortfall"] = {"at": utc_iso(moment), "balance": quantity_text(lowest)}
    return state


# ============================================================
# SERIALISATION
# ============================================================

def adjustment_core(adjustment: StockAdjustment, names: dict, movement_id: int | None) -> dict:
    return {
        "id": adjustment.id,
        "status": adjustment.status,
        "reason": adjustment.reason,
        "raised_by_name": names.get(adjustment.raised_by),
        "raised_at": utc_iso(adjustment.raised_at),
        "decided_by_name": names.get(adjustment.decided_by),
        "decided_at": utc_iso(adjustment.decided_at) if adjustment.decided_at else None,
        "decision_reason": adjustment.decision_reason,
        "movement_id": movement_id,
    }


def adjustment_movements(db: Session, campus_id: int, adjustment_ids) -> dict[int, int]:
    keys = [f"ADJUSTMENT:{i}" for i in adjustment_ids]
    if not keys:
        return {}
    return {
        int(key.split(":")[1]): movement_id
        for movement_id, key in db.query(StockMovement.id, StockMovement.source_key).filter(
            StockMovement.campus_id == campus_id, StockMovement.source_key.in_(keys))
    }


def count_detail(db: Session, user: User, count: StockCount) -> dict:
    campus_id = count.campus_id
    lines = count_lines(db, count.id)
    item_ids = {l.item_id for l in lines}
    items = {i: (n, c) for i, n, c in db.query(Item.id, Item.name, Category.name)
             .outerjoin(Category, Category.id == Item.category_id).filter(Item.id.in_(item_ids or {0}))}
    units = dict(db.query(Unit.id, Unit.symbol).filter(
        Unit.id.in_({l.unit_id for l in lines} | {l.standard_unit_id for l in lines} or {0})))
    adjustments = {a.count_item_id: a for a in db.query(StockAdjustment).filter(StockAdjustment.count_id == count.id)}
    movement_ids = adjustment_movements(db, campus_id, [a.id for a in adjustments.values()])
    names = names_of(db, [count.counted_by] + [u for a in adjustments.values() for u in (a.raised_by, a.decided_by)])
    elsewhere = {
        item_id: {"id": adjustment_id, "count_id": other_count_id, "count_number": number}
        for item_id, adjustment_id, other_count_id, number in (
            db.query(StockAdjustment.item_id, StockAdjustment.id, StockCount.id, StockCount.count_number)
            .join(StockCount, StockCount.id == StockAdjustment.count_id)
            .filter(StockAdjustment.campus_id == campus_id, StockAdjustment.status == "PENDING",
                    StockAdjustment.item_id.in_(item_ids or {0}), StockAdjustment.count_id != count.id))
    }
    at_count_now = balances_at(db, campus_id, item_ids, count.counted_at)

    out_lines = []
    for l in lines:
        adjustment = adjustments.get(l.id)
        recorded = Decimal(str(l.system_balance))
        difference = Decimal(str(l.difference))
        # After an approval the ledger at the count time includes the adjustment itself.
        own = difference if adjustment and adjustment.status == "APPROVED" else ZERO
        changed = (at_count_now[l.item_id] - own) != recorded
        name, category = items.get(l.item_id, (None, None))
        out_lines.append({
            "id": l.id,
            "item_id": l.item_id,
            "item_name": name,
            "category_name": category,
            "quantity": quantity_text(l.quantity),
            "unit_id": l.unit_id,
            "unit_symbol": units.get(l.unit_id),
            "conversion_factor": format(Decimal(str(l.conversion_factor)).normalize(), "f"),
            "physical_quantity": quantity_text(l.standard_quantity),
            "standard_unit_id": l.standard_unit_id,
            "standard_unit_symbol": units.get(l.standard_unit_id),
            "system_balance": quantity_text(recorded),
            "difference": quantity_text(difference),
            "remarks": l.remarks,
            "ledger_changed": changed,
            "adjustment": adjustment_core(adjustment, names, movement_ids.get(adjustment.id)) if adjustment else None,
            "other_pending_adjustment": elsewhere.get(l.item_id),
            "can_raise": difference != 0 and adjustment is None and not changed and l.item_id not in elsewhere,
        })

    return {
        "id": count.id,
        "count_number": count.count_number,
        "counted_at": utc_iso(count.counted_at),
        "counted_by_id": count.counted_by,
        "counted_by_name": names.get(count.counted_by),
        "reason": count.reason,
        "remarks": count.remarks,
        "line_count": len(lines),
        "difference_count": sum(1 for l in lines if Decimal(str(l.difference)) != 0),
        "lines": out_lines,
    }


def adjustments_payload(db: Session, user: User, adjustments: list[StockAdjustment], detail: bool = False) -> list[dict]:
    if not adjustments:
        return []
    campus_id = user.campus_id
    lines = {l.id: l for l in db.query(StockCountItem).filter(StockCountItem.id.in_([a.count_item_id for a in adjustments]))}
    counts = {c.id: c for c in db.query(StockCount).filter(StockCount.id.in_({a.count_id for a in adjustments}))}
    items = dict(db.query(Item.id, Item.name).filter(Item.id.in_({a.item_id for a in adjustments})))
    units = dict(db.query(Unit.id, Unit.symbol).filter(
        Unit.id.in_({l.standard_unit_id for l in lines.values()} | {l.unit_id for l in lines.values()} or {0})))
    names = names_of(db, [u for a in adjustments for u in (a.counted_by, a.raised_by, a.decided_by)])
    movement_ids = adjustment_movements(db, campus_id, [a.id for a in adjustments])
    sees_stock = user_has_permission(db, user, "inventory.read")
    approvers = {}

    out = []
    for a in adjustments:
        line, count = lines[a.count_item_id], counts[a.count_id]
        unit = units.get(line.standard_unit_id)
        state = approval_state(db, campus_id, a, line, count)
        you_counted = a.counted_by == user.id
        manager = user.role in (UserRole.ADMIN, UserRole.KITCHEN_MANAGER)
        if a.status == "PENDING" and a.counted_by not in approvers:
            approvers[a.counted_by] = eligible_approver_count(db, campus_id, a.counted_by)
        row = {
            **adjustment_core(a, names, movement_ids.get(a.id)),
            "count_id": count.id,
            "count_number": count.count_number,
            "count_item_id": line.id,
            "counted_at": utc_iso(count.counted_at),
            "counted_by_name": names.get(a.counted_by),
            "item_id": a.item_id,
            "item_name": items.get(a.item_id),
            "unit_symbol": unit,
            "entered_quantity": quantity_text(line.quantity),
            "entered_unit_symbol": units.get(line.unit_id),
            "physical_quantity": quantity_text(line.standard_quantity),
            "system_balance_at_count": state["system_balance_at_count"],
            "difference": quantity_text(line.difference),
            "ledger_changed": state["ledger_changed"] if a.status == "PENDING" else False,
            "you_counted": you_counted,
            "can_decide": a.status == "PENDING" and manager and not you_counted,
            "eligible_approver_count": approvers.get(a.counted_by) if a.status == "PENDING" else None,
            # Current figures only for users who may read stock balances.
            "stock_visible": sees_stock,
            "count_time_balance_now": state["count_time_balance_now"] if sees_stock else None,
            "balance_now": state["balance_now"] if sees_stock else None,
            "balance_after_approval": state["balance_after_approval"] if sees_stock else None,
            "shortfall": state["shortfall"] if sees_stock else None,
            "would_go_negative": state["shortfall"] is not None,
            "movements_since_count_total": len(state["movements_since_count"]) if sees_stock else None,
        }
        if detail:
            row["movements_since_count"] = None
            if sees_stock:
                since = state["movements_since_count"]
                documents = stock_ledger.movement_documents(db, campus_id, since)
                creators = names_of(db, [m.created_by for m in since])
                row["movements_since_count"] = [{
                    "id": m.id,
                    "movement_type": m.movement_type,
                    "signed_quantity": quantity_text(stock_ledger.signed_quantity(m.direction, m.quantity)),
                    "effective_at": utc_iso(m.effective_at),
                    "created_at": utc_iso(m.created_at),
                    "dated_before_count": as_utc(m.effective_at) <= as_utc(count.counted_at),
                    "document_number": (documents.get((m.reference_type, m.reference_id)) or (None,))[0],
                    "created_by_name": creators.get(m.created_by),
                } for m in reversed(since)]
        out.append(row)
    return out


# ============================================================
# COUNT FORM OPTIONS (stock_count.create) — blind
# ============================================================

@router.get("/api/stock-counts/options")
def count_form_options(db: Session = Depends(get_db),
                       user: User = Depends(require_permission("stock_count.create"))):
    """The count form: active items with their category and standard unit,
    units and conversions. Never a stock balance, whatever other
    permissions the user holds (blind count, S6)."""
    campus_id = user.campus_id
    items = (
        db.query(Item, Category.name)
        .outerjoin(Category, Category.id == Item.category_id)
        .filter(Item.campus_id == campus_id, Item.is_active.is_(True), not_outsourced(Item.item_kind))
        .order_by(func.lower(func.coalesce(Category.name, "")), func.lower(Item.name), Item.id)
        .all()
    )
    return {
        "today": campus_today().isoformat(),
        "items": [{"id": i.id, "name": i.name, "category_name": c, "standard_unit_id": i.standard_unit_id,
                   "is_active": True} for i, c in items],
        "units": [{"id": u.id, "name": u.name, "symbol": u.symbol, "dimension": u.dimension,
                   "is_active": bool(u.is_active)}
                  for u in db.query(Unit).filter(Unit.campus_id == campus_id).order_by(Unit.name)],
        "conversions": [{"from_unit_id": c.from_unit_id, "to_unit_id": c.to_unit_id}
                        for c in db.query(UnitConversion).filter(UnitConversion.campus_id == campus_id)],
        "max_lines": MAX_COUNT_LINES,
    }


# ============================================================
# STOCK COUNTS
# ============================================================

@router.get("/api/stock-counts")
def list_counts(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    item_id: int | None = Query(default=None, gt=0),
    search: str | None = Query(default=None, max_length=30),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("stock_count.read")),
):
    """Counts, newest first. Dates are campus-local days of the count time."""
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from cannot be after date_to.")
    campus_id = user.campus_id
    query = db.query(StockCount).filter(StockCount.campus_id == campus_id)
    zone = campus_timezone()
    if date_from:
        query = query.filter(StockCount.counted_at >= datetime.combine(date_from, time.min, tzinfo=zone).astimezone(timezone.utc))
    if date_to:
        query = query.filter(StockCount.counted_at < datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=zone).astimezone(timezone.utc))
    if item_id:
        query = query.filter(StockCount.id.in_(db.query(StockCountItem.count_id).filter(StockCountItem.item_id == item_id)))
    if search and search.strip():
        query = query.filter(func.upper(StockCount.count_number).contains(search.strip().upper()))
    total = query.count()
    counts = query.order_by(StockCount.counted_at.desc(), StockCount.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

    ids = [c.id for c in counts] or [0]
    lines_by_count: dict[int, list] = {}
    for count_id, name, difference in (
            db.query(StockCountItem.count_id, Item.name, StockCountItem.difference)
            .join(Item, Item.id == StockCountItem.item_id)
            .filter(StockCountItem.count_id.in_(ids)).order_by(StockCountItem.id)):
        lines_by_count.setdefault(count_id, []).append((name, Decimal(str(difference))))
    adjustment_counts: dict[int, dict] = {}
    for count_id, state, number in (db.query(StockAdjustment.count_id, StockAdjustment.status, func.count(StockAdjustment.id))
                                    .filter(StockAdjustment.count_id.in_(ids))
                                    .group_by(StockAdjustment.count_id, StockAdjustment.status)):
        adjustment_counts.setdefault(count_id, {})[state] = number
    names = names_of(db, [c.counted_by for c in counts])

    out = []
    for c in counts:
        lines = lines_by_count.get(c.id, [])
        by_status = adjustment_counts.get(c.id, {})
        differences = sum(1 for _n, d in lines if d != 0)
        raised = sum(by_status.values())
        out.append({
            "id": c.id,
            "count_number": c.count_number,
            "counted_at": utc_iso(c.counted_at),
            "counted_by_name": names.get(c.counted_by),
            "reason": c.reason,
            "item_names": [n for n, _d in lines],
            "line_count": len(lines),
            "difference_count": differences,
            "not_raised_count": max(differences - raised, 0),
            "pending_count": by_status.get("PENDING", 0),
            "approved_count": by_status.get("APPROVED", 0),
            "rejected_count": by_status.get("REJECTED", 0),
        })
    return {"items": out, **page_meta(total, page, page_size)}


@router.post("/api/stock-counts", status_code=201)
def record_count(payload: CountInput, db: Session = Depends(get_db),
                 user: User = Depends(require_permission("stock_count.create"))):
    """Save a count (blind entry). The server takes the count time and, per
    line, the system balance at that moment while the items are locked, so
    no posting for these items can interleave. Nothing is posted: stock is
    unchanged until an adjustment is approved (AT02)."""
    campus_id = user.campus_id
    item_ids = [line.item_id for line in payload.lines]
    if len(item_ids) != len(set(item_ids)):
        raise HTTPException(status_code=422, detail="Each item can appear only once in a count.")
    items = {i.id: i for i in db.query(Item).filter(Item.campus_id == campus_id, Item.id.in_(item_ids))}
    prepared = []
    for line in payload.lines:
        item = items.get(line.item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        if not item.is_active:
            raise HTTPException(status_code=422, detail=f"{item.name} is inactive.")
        if item.item_kind == "OUTSOURCED":
            raise HTTPException(status_code=422, detail=outsourced_message([item.name], "counted as stock"))
        unit, factor, standard = count_conversion(db, user, item, line.unit_id, line.quantity)
        prepared.append((item, line, unit, factor, standard))

    try:
        seq, number = next_number(db, campus_id, StockCount, StockCount.count_seq, "SC")
        stock_ledger.lock_items(db, campus_id, item_ids)
        counted_at = datetime.now(timezone.utc)
        system = balances_at(db, campus_id, item_ids, counted_at)
        count = StockCount(campus_id=campus_id, count_seq=seq, count_number=number, counted_at=counted_at,
                           counted_by=user.id, reason=payload.reason, remarks=clean(payload.remarks))
        db.add(count)
        db.flush()
        snapshot = []
        for item, line, unit, factor, standard in prepared:
            balance = quantity(system[item.id])
            db.add(StockCountItem(
                campus_id=campus_id, count_id=count.id, item_id=item.id, quantity=quantity(line.quantity),
                unit_id=unit.id, conversion_factor=factor, standard_quantity=standard,
                standard_unit_id=item.standard_unit_id, system_balance=balance, difference=standard - balance,
                remarks=clean(line.remarks),
            ))
            snapshot.append({"item_id": item.id, "quantity": quantity_text(line.quantity), "unit_id": unit.id,
                             "physical_quantity": quantity_text(standard), "system_balance": quantity_text(balance),
                             "difference": quantity_text(standard - balance)})
        db.flush()
        record_audit(db, user, "CREATE", "STOCK_COUNT", count.id, {
            "count_number": number, "counted_at": utc_iso(counted_at), "reason": payload.reason, "lines": snapshot,
        })
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="The count could not be saved. Reload and try again.")
    db.refresh(count)
    if user_has_permission(db, user, "stock_count.read"):
        return count_detail(db, user, count)
    # A counter who may not view counts gets no balances back either.
    return {"id": count.id, "count_number": count.count_number, "counted_at": utc_iso(count.counted_at),
            "line_count": len(prepared)}


@router.get("/api/stock-counts/{count_id}")
def get_count_detail(count_id: int, db: Session = Depends(get_db),
                     user: User = Depends(require_permission("stock_count.read"))):
    return count_detail(db, user, get_count(db, user, count_id))


@router.post("/api/stock-counts/{count_id}/lines/{line_id}/adjustment", status_code=201)
def raise_adjustment(count_id: int, line_id: int, payload: Reason, db: Session = Depends(get_db),
                     user: User = Depends(require_permission("stock_count.create"))):
    """Raise an adjustment request from a count line with a difference
    (implementation choice 4: stock_count.create, ADMIN or KITCHEN_MANAGER).
    Raising only requests; nothing is posted."""
    count = get_count(db, user, count_id)
    line = db.query(StockCountItem).filter(StockCountItem.id == line_id, StockCountItem.count_id == count.id).first()
    if not line:
        raise HTTPException(status_code=404, detail="Count line not found")
    # Serialises raises and approvals for this item.
    stock_ledger.lock_items(db, user.campus_id, [line.item_id])
    item_name, unit = item_label(db, line.item_id)
    if Decimal(str(line.difference)) == 0:
        raise HTTPException(status_code=422, detail=f"{item_name} was counted at its system balance; there is nothing to adjust.")
    existing = db.query(StockAdjustment).filter(StockAdjustment.count_item_id == line.id).first()
    if existing:
        detail = {
            "PENDING": "An adjustment for this line is already waiting for approval.",
            "APPROVED": "The adjustment for this line has already been approved.",
            "REJECTED": f"The adjustment for this line was rejected. Count {item_name} again to raise a new one.",
        }[existing.status]
        raise HTTPException(status_code=409, detail=detail)
    pending = (
        db.query(StockCount.count_number)
        .join(StockAdjustment, StockAdjustment.count_id == StockCount.id)
        .filter(StockAdjustment.campus_id == user.campus_id, StockAdjustment.item_id == line.item_id,
                StockAdjustment.status == "PENDING")
        .first()
    )
    if pending:
        raise HTTPException(status_code=409, detail=(
            f"{item_name} already has an adjustment waiting for approval (from {pending[0]}). "
            "Only one can be pending per item; it must be approved or rejected first."))
    recorded = Decimal(str(line.system_balance))
    now_at_count = balances_at(db, user.campus_id, [line.item_id], count.counted_at)[line.item_id]
    if now_at_count != recorded:
        raise HTTPException(status_code=409, detail=ledger_changed_message(item_name, unit, count.count_number, recorded, now_at_count))

    try:
        adjustment = StockAdjustment(
            campus_id=user.campus_id, count_id=count.id, count_item_id=line.id, item_id=line.item_id,
            counted_by=count.counted_by, reason=payload.reason, status="PENDING", raised_by=user.id,
            raised_at=datetime.now(timezone.utc),
        )
        db.add(adjustment)
        db.flush()
        record_audit(db, user, "RAISE", "STOCK_ADJUSTMENT", adjustment.id, {
            "count_id": count.id, "count_number": count.count_number, "count_item_id": line.id,
            "item_id": line.item_id, "system_balance_at_count": quantity_text(recorded),
            "physical_quantity": quantity_text(line.standard_quantity), "difference": quantity_text(line.difference),
            "reason": payload.reason,
        })
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"An adjustment for {item_name} was raised at the same time. Reload and try again.")
    db.refresh(adjustment)
    if user_has_permission(db, user, "stock_count.read"):
        return adjustments_payload(db, user, [adjustment], detail=True)[0]
    return {"id": adjustment.id, "status": adjustment.status}


# ============================================================
# ADJUSTMENTS
# ============================================================

@router.get("/api/stock-adjustments")
def list_adjustments(
    status_filter: str | None = Query(default=None, alias="status", pattern="^(PENDING|APPROVED|REJECTED)$"),
    item_id: int | None = Query(default=None, gt=0),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("stock_count.read")),
):
    campus_id = user.campus_id
    query = db.query(StockAdjustment).filter(StockAdjustment.campus_id == campus_id)
    if item_id:
        query = query.filter(StockAdjustment.item_id == item_id)
    counts = dict(query.with_entities(StockAdjustment.status, func.count(StockAdjustment.id)).group_by(StockAdjustment.status))
    if status_filter:
        query = query.filter(StockAdjustment.status == status_filter)
    total = query.count()
    rows = (query.order_by(StockAdjustment.raised_at.desc(), StockAdjustment.id.desc())
            .offset((page - 1) * page_size).limit(page_size).all())
    return {
        "items": adjustments_payload(db, user, rows),
        "status_counts": {s: counts.get(s, 0) for s in ("PENDING", "APPROVED", "REJECTED")},
        **page_meta(total, page, page_size),
    }


@router.get("/api/stock-adjustments/{adjustment_id}")
def get_adjustment(adjustment_id: int, db: Session = Depends(get_db),
                   user: User = Depends(require_permission("stock_count.read"))):
    adjustment = db.query(StockAdjustment).filter(
        StockAdjustment.id == adjustment_id, StockAdjustment.campus_id == user.campus_id).first()
    if not adjustment:
        raise HTTPException(status_code=404, detail="Stock adjustment not found")
    return adjustments_payload(db, user, [adjustment], detail=True)[0]


@router.post("/api/stock-adjustments/{adjustment_id}/approve")
def approve_adjustment(adjustment_id: int, payload: DecisionNote | None = None, db: Session = Depends(get_db),
                       user: User = Depends(stock_managers)):
    """ADMIN or KITCHEN_MANAGER who did not count: post the difference
    measured at count time as one ADJUSTMENT movement, effective at the count
    time. Refused if the ledger at the count time changed since the count,
    or (S2) if the balance would go below zero at any point."""
    adjustment = lock_adjustment(db, user, adjustment_id)
    if adjustment.status != "PENDING":
        raise HTTPException(status_code=409, detail=f"This adjustment has already been {adjustment.status.lower()}.")
    if adjustment.counted_by == user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=COUNTER_CANNOT_DECIDE)
    line = db.query(StockCountItem).filter(StockCountItem.id == adjustment.count_item_id).one()
    count = db.query(StockCount).filter(StockCount.id == adjustment.count_id).one()
    item = stock_ledger.lock_items(db, user.campus_id, [adjustment.item_id])[adjustment.item_id]
    item_name, unit = item_label(db, item.id)
    if item.standard_unit_id != line.standard_unit_id:
        raise HTTPException(status_code=409, detail=(
            f"{item_name}'s standard unit has changed since {count.count_number}. Reject this adjustment and count again."))
    movements = stock_ledger.ledger_movements(db, user.campus_id, item.id)
    recorded = Decimal(str(line.system_balance))
    now_at_count = stock_ledger.balance_at(movements, count.counted_at)
    if now_at_count != recorded:
        raise HTTPException(status_code=409, detail=(
            ledger_changed_message(item_name, unit, count.count_number, recorded, now_at_count)
            + " Reject this adjustment; nothing has been posted."))
    balance_before = stock_ledger.balance_at(movements, datetime.max.replace(tzinfo=timezone.utc))
    since = [m.id for m in movements if as_utc(m.created_at) > as_utc(count.counted_at)]
    note = clean(payload.note if payload else None)
    now = datetime.now(timezone.utc)
    try:
        try:
            (movement,) = stock_ledger.post(db, user, [adjustment_posting(adjustment, line, count)])
        except HTTPException as refusal:
            if refusal.status_code != 409:
                raise
            # S2: if every movement had been recorded, a count-based
            # adjustment could not go below zero, so a record is missing.
            raise HTTPException(status_code=409, detail=(
                f"{refusal.detail} Nothing has been posted. Reject this adjustment, then record the "
                f"missing movement or count {item_name} again."))
        adjustment.status, adjustment.decided_by, adjustment.decided_at = "APPROVED", user.id, now
        adjustment.decision_reason = note
        record_audit(db, user, "APPROVE", "STOCK_ADJUSTMENT", adjustment.id, {
            "count_number": count.count_number, "item_id": item.id, "movement_id": movement.id,
            "difference": quantity_text(line.difference), "effective_at": utc_iso(count.counted_at),
            "system_balance_at_count": quantity_text(recorded),
            "physical_quantity": quantity_text(line.standard_quantity),
            "balance_before": quantity_text(balance_before),
            "balance_after": quantity_text(balance_before + Decimal(str(line.difference))),
            "movements_since_count": since, "note": note,
        })
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="This adjustment was decided at the same time by someone else. Reload.")
    db.refresh(adjustment)
    return adjustments_payload(db, user, [adjustment], detail=True)[0]


@router.post("/api/stock-adjustments/{adjustment_id}/reject")
def reject_adjustment(adjustment_id: int, payload: Reason, db: Session = Depends(get_db),
                      user: User = Depends(stock_managers)):
    """ADMIN or KITCHEN_MANAGER who did not count: reject with a reason.
    Nothing is posted; a new count is needed for this item."""
    adjustment = lock_adjustment(db, user, adjustment_id)
    if adjustment.status != "PENDING":
        raise HTTPException(status_code=409, detail=f"This adjustment has already been {adjustment.status.lower()}.")
    if adjustment.counted_by == user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=COUNTER_CANNOT_DECIDE)
    now = datetime.now(timezone.utc)
    try:
        adjustment.status, adjustment.decided_by, adjustment.decided_at = "REJECTED", user.id, now
        adjustment.decision_reason = payload.reason
        record_audit(db, user, "REJECT", "STOCK_ADJUSTMENT", adjustment.id, {
            "count_id": adjustment.count_id, "item_id": adjustment.item_id, "reason": payload.reason,
        })
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="This adjustment was decided at the same time by someone else. Reload.")
    db.refresh(adjustment)
    return adjustments_payload(db, user, [adjustment], detail=True)[0]
