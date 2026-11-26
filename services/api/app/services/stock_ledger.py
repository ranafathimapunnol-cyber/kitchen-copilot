"""The stock ledger (Stage 4): posting movements and reading balances.

Every stock posting goes through post(). It locks the affected item rows in
id order, so two postings for the same item never check the balance at the
same time, and it refuses any posting that would take a balance below zero
at any point in the item's history (decision S2, approved 23 November
2026).

Ledger order. Movements are replayed by effective time (when the stock
moved), then by id (posting order). A new posting is placed after the
existing movements with the same effective time. Backdated postings (an
opening entry, a late kitchen issue, a count adjustment effective at its
count time) can therefore change the balance at earlier points, which is
why the whole history from the new posting onwards is checked, not only
today's balance.

Balances are calculated from posted movements only (STK01, STK04):
balance = sum(direction x quantity), in the item's standard unit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.clock import campus_timezone, campus_today
from app.models.master_data import Item, Unit
from app.models.purchases import StockMovement
from app.models.user import User

QUANTITY_STEP = Decimal("0.001")
ZERO = Decimal("0")

INFLOW_TYPES = frozenset({"OPENING", "RECEIPT", "UNUSED_RETURN"})
OUTFLOW_TYPES = frozenset({"ISSUE", "SUPPLIER_RETURN"})


# ============================================================
# SMALL HELPERS
# ============================================================

def quantity(value) -> Decimal:
    return Decimal(str(value)).quantize(QUANTITY_STEP, rounding=ROUND_HALF_UP)


def quantity_text(value) -> str:
    """An exact quantity for JSON: "12.500", never a float."""
    return format(quantity(value or 0), "f")


def as_utc(moment: datetime) -> datetime:
    """Stored times are UTC; SQLite returns them without a zone."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def start_of_campus_day(day: date) -> datetime:
    """00:00 campus time on `day`, as UTC: the effective time of an entry
    dated `day` (opening stock), so it counts before that day's movements."""
    return datetime.combine(day, time.min, tzinfo=campus_timezone()).astimezone(
        timezone.utc
    )


def document_effective_at(day: date, now: datetime) -> datetime:
    """When a kitchen issue or unused return takes effect (decisions 4b-1
    and 4b-2, approved 23 November 2026): dated today, at its confirmation
    time `now`; dated earlier (entered late), at the end of that campus day
    (23:59:59.999999 campus time), so that day's receipts count first."""
    if day >= campus_today(now):
        return as_utc(now)
    end_of_day = datetime.combine(day, time.max, tzinfo=campus_timezone())
    return end_of_day.astimezone(timezone.utc)


def campus_moment_text(moment: datetime) -> str:
    local = as_utc(moment).astimezone(campus_timezone())
    return local.strftime("%d %b %Y %H:%M")


def signed_quantity(direction: int, amount) -> Decimal:
    return Decimal(direction) * Decimal(str(amount))


def balance_expression():
    """SUM(direction x quantity) for use in queries; 0 when no rows."""
    return func.coalesce(
        func.sum(StockMovement.direction * StockMovement.quantity), 0
    )


# ============================================================
# POSTINGS
# ============================================================

@dataclass
class Posting:
    """One movement to post. Quantity is positive, in the item's standard
    unit; direction carries the sign."""

    item_id: int
    movement_type: str
    direction: int
    quantity: Decimal
    unit_id: int
    effective_at: datetime
    source_key: str
    reference_type: str
    reference_id: int
    remarks: str | None = None
    reversal_of_id: int | None = None
    receipt_item_id: int | None = None


def lock_items(db: Session, campus_id: int, item_ids) -> dict[int, Item]:
    """Lock the item rows in id order (SELECT ... FOR UPDATE). Every posting
    that can lower stock takes these locks first, so checks for one item run
    one at a time. Ignored by SQLite, which serialises writers anyway."""
    ids = sorted(set(item_ids))
    rows = (
        db.query(Item)
        .filter(Item.campus_id == campus_id, Item.id.in_(ids))
        .order_by(Item.id)
        .with_for_update()
        .all()
    )
    found = {item.id: item for item in rows}
    if len(found) != len(ids):
        raise HTTPException(status_code=404, detail="Item not found")
    return found


def ledger_movements(db: Session, campus_id: int, item_id: int) -> list[StockMovement]:
    """Every movement of one item in ledger order."""
    rows = (
        db.query(StockMovement)
        .filter(
            StockMovement.campus_id == campus_id,
            StockMovement.item_id == item_id,
        )
        .all()
    )
    return sorted(rows, key=lambda m: (as_utc(m.effective_at), m.id))


def find_shortfall(
    existing: list[StockMovement], postings: list[Posting]
) -> tuple[datetime, Decimal] | None:
    """Replay the item's history with the new postings inserted and return
    the lowest negative balance (and when it occurs) from the first new
    posting onwards, or None if the balance never goes below zero there.

    Order: effective time, then existing movements by id, then the new
    postings in the order given. Points before the first new posting are
    unchanged by it and are not judged here."""
    entries = [
        (as_utc(m.effective_at), 0, m.id, signed_quantity(m.direction, m.quantity), False)
        for m in existing
    ] + [
        (as_utc(p.effective_at), 1, index, signed_quantity(p.direction, p.quantity), True)
        for index, p in enumerate(postings)
    ]
    entries.sort(key=lambda entry: entry[:3])

    balance = ZERO
    checking = False
    worst: tuple[datetime, Decimal] | None = None
    for moment, _order, _key, change, is_new in entries:
        balance += change
        checking = checking or is_new
        if checking and balance < 0 and (worst is None or balance < worst[1]):
            worst = (moment, balance)
    return worst


def post(db: Session, user: User, postings: list[Posting]) -> list[StockMovement]:
    """Validate, check and add the movements (flushed, not committed: the
    caller commits them together with its document and audit rows)."""
    if not postings:
        return []

    items = lock_items(db, user.campus_id, [p.item_id for p in postings])

    # Stage 8a (OUT01, P8-2): outsourced food never enters raw-ingredient
    # stock. The item rows are locked above, and PUT /api/items/{id}/kind
    # takes the same row lock, so the kind cannot change in between.
    outsourced = sorted({items[p.item_id].name for p in postings
                         if items[p.item_id].item_kind == "OUTSOURCED" and p.movement_type != "REVERSAL"})
    if outsourced:
        from app.services.outsourced_guard import outsourced_message

        raise HTTPException(status_code=422, detail=outsourced_message(outsourced, "posted to stock"))

    for p in postings:
        item = items[p.item_id]
        if p.direction not in (1, -1):
            raise ValueError(f"invalid direction {p.direction}")
        if p.movement_type in INFLOW_TYPES and p.direction != 1:
            raise ValueError(f"{p.movement_type} must add stock")
        if p.movement_type in OUTFLOW_TYPES and p.direction != -1:
            raise ValueError(f"{p.movement_type} must remove stock")
        if quantity(p.quantity) <= 0:
            raise ValueError("a posted quantity must be positive")
        if p.unit_id != item.standard_unit_id:
            raise ValueError("movements are posted in the item's standard unit")

    for item_id, item in items.items():
        own = [p for p in postings if p.item_id == item_id]
        if not any(p.direction < 0 for p in own):
            continue  # stock that only increases cannot go below zero
        shortfall = find_shortfall(ledger_movements(db, user.campus_id, item_id), own)
        if shortfall is not None:
            moment, lowest = shortfall
            unit = db.query(Unit.symbol).filter(Unit.id == item.standard_unit_id).scalar() or ""
            missing = quantity_text(-lowest)
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Not enough {item.name} in stock: this would take the "
                    f"balance to -{missing} {unit} on {campus_moment_text(moment)} "
                    f"(campus time). No stock balance may go below zero; record "
                    f"the missing stock first."
                ),
            )

    now = datetime.now(timezone.utc)
    rows = [
        StockMovement(
            campus_id=user.campus_id,
            item_id=p.item_id,
            movement_type=p.movement_type,
            direction=p.direction,
            quantity=quantity(p.quantity),
            unit_id=p.unit_id,
            effective_at=as_utc(p.effective_at),
            source_key=p.source_key,
            reference_type=p.reference_type,
            reference_id=p.reference_id,
            remarks=p.remarks,
            reversal_of_id=p.reversal_of_id,
            receipt_item_id=p.receipt_item_id,
            created_by=user.id,
            created_at=now,
        )
        for p in postings
    ]
    db.add_all(rows)
    db.flush()
    return rows


def reversal_of(original: StockMovement, reason: str, now: datetime) -> Posting:
    """The posting that undoes `original`: the same item, unit and quantity
    in the opposite direction, effective at the actual posting time `now`.
    The original keeps its own effective date and is never changed."""
    return Posting(
        item_id=original.item_id,
        movement_type="REVERSAL",
        direction=-original.direction,
        quantity=Decimal(str(original.quantity)),
        unit_id=original.unit_id,
        effective_at=now,
        source_key=f"REVERSAL:{original.id}",
        reference_type=original.reference_type,
        reference_id=original.reference_id,
        remarks=reason,
        reversal_of_id=original.id,
    )


# ============================================================
# READING
# ============================================================

def running_balances(movements: list[StockMovement]) -> list[tuple[StockMovement, Decimal]]:
    """Each movement (in ledger order) with the balance after it."""
    balance = ZERO
    result = []
    for movement in movements:
        balance += signed_quantity(movement.direction, movement.quantity)
        result.append((movement, balance))
    return result


def movement_documents(db: Session, campus_id: int, movements) -> dict:
    """For movements posted by kitchen issues and returns (slice 4b) and by
    count adjustments (slice 4c): {(reference_type, reference_id):
    (document number, kitchen issue id, stock count id)}."""
    from app.models.stock import KitchenIssue, KitchenReturn, StockAdjustment, StockCount

    issue_ids = {m.reference_id for m in movements if m.reference_type == "KITCHEN_ISSUE"}
    return_ids = {m.reference_id for m in movements if m.reference_type == "KITCHEN_RETURN"}
    adjustment_ids = {m.reference_id for m in movements if m.reference_type == "STOCK_ADJUSTMENT"}
    found = {}
    for issue_id, number in db.query(KitchenIssue.id, KitchenIssue.issue_number).filter(
            KitchenIssue.campus_id == campus_id, KitchenIssue.id.in_(issue_ids or {0})):
        found[("KITCHEN_ISSUE", issue_id)] = (number, issue_id, None)
    for return_id, number, issue_id in db.query(KitchenReturn.id, KitchenReturn.return_number, KitchenReturn.issue_id).filter(
            KitchenReturn.campus_id == campus_id, KitchenReturn.id.in_(return_ids or {0})):
        found[("KITCHEN_RETURN", return_id)] = (number, issue_id, None)
    for adjustment_id, number, count_id in (
            db.query(StockAdjustment.id, StockCount.count_number, StockCount.id)
            .join(StockCount, StockCount.id == StockAdjustment.count_id)
            .filter(StockAdjustment.campus_id == campus_id, StockAdjustment.id.in_(adjustment_ids or {0}))):
        found[("STOCK_ADJUSTMENT", adjustment_id)] = (number, None, count_id)
    return found


def balance_at(movements: list[StockMovement], moment: datetime) -> Decimal:
    """The balance after every movement effective at or before `moment`."""
    limit = as_utc(moment)
    return sum(
        (signed_quantity(m.direction, m.quantity) for m in movements if as_utc(m.effective_at) <= limit),
        ZERO,
    )


def item_balance(db: Session, campus_id: int, item_id: int) -> Decimal:
    value = (
        db.query(balance_expression())
        .filter(
            StockMovement.campus_id == campus_id,
            StockMovement.item_id == item_id,
        )
        .scalar()
    )
    return Decimal(str(value or 0))
