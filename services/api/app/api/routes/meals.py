"""Meal records (Stage 5: MEAL01–MEAL05), per docs/STAGE-5-MEAL-PLAN.md.

Decisions applied (approved 23 November 2026):
- 5-1 permissions: meal.read views; meal.create records a new meal; meal.update
  edits an OPEN record, closes it and cancels it. A CLOSED or CANCELLED record
  refuses every change. Reopening is ADMIN and KITCHEN_MANAGER only (role
  check, reason required); so is the change history (audit).
- 5-2 one record per campus, date and session; expected and actual counts by
  students, staff and guests, kept separate; expected counts up to 14 days
  ahead and actual counts on or after the meal date (interim, client
  question on headcount collection).
- 5-3/5-4 dishes with output and unit; available = distributed + remaining;
  leftovers split the remaining quantity (retained, returned to supplier,
  wasted, disposed) with remarks; closing needs exact reconciliation.
- 5-5 retained leftovers (INTERIM until client question Q11): carried once,
  whole, from a CLOSED record into a later OPEN record of the same campus,
  as their own dish line with the same name and unit; the source is locked.
- 5-6 no waste record, supplier return or credit is created.
- 5-7 linked kitchen issues are derived from campus, date and session; the
  meal record never changes an issue or posts stock.
- 5-8 actual net usage per item now; the planned side waits for planning.
- 5-9 OPEN / CLOSED / CANCELLED; reopening (INTERIM until the client's rule
  for historical corrections) with a full audit history.
Prepared food never creates a stock movement, purchase, receipt, supplier
return, credit or payment. Every query is limited to the user's campus.

Stage 8a (P8-4): confirmed outsourced deliveries add "received" dish lines
to the OPEN record of the same campus, date and exact meal session, when the
delivery is confirmed, when the record is created and when it is reopened. A
CLOSED record is never changed: the food waits (reconciliation pending)
until the record is reopened. Received lines keep their name, quantity and
unit (only remarks change); distribution and leftovers are recorded as for
prepared dishes; they are removed only by cancelling the delivery, or
released when the record is cancelled.
"""

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_permission, require_roles, user_has_permission
from app.api.routes.kitchen import Reason, clean, names_of, page_meta, returned_by_line
from app.api.routes.master_data import record_audit
from app.core.clock import campus_today, utc_iso
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.master_data import Item, MealSession, Menu, Unit
from app.models.meals import LEFTOVER_CLASSES, MealDish, MealLeftover, MealRecord
from app.models.stock import KitchenIssue, KitchenIssueItem
from app.models.user import User, UserRole
from app.services.stock_ledger import quantity, quantity_text

router = APIRouter(prefix="/api/meal-records", tags=["Meal Records"])

ZERO = Decimal("0")
AHEAD_DAYS = 14  # interim (5-2): how far ahead expected counts may be entered
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
ENTITY = "MEAL_RECORD"
CLASS_LABELS = {"RETAINED": "retained", "RETURNED_TO_SUPPLIER": "returned to supplier",
                "WASTED": "wasted", "DISPOSED": "disposed"}

managers = require_roles(UserRole.ADMIN, UserRole.KITCHEN_MANAGER)


def form_user(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
    """The meal forms: anyone who may record or edit a meal."""
    if user_has_permission(db, user, "meal.create") or user_has_permission(db, user, "meal.update"):
        return user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This permission has not been assigned to you.")


# ============================================================
# INPUT
# ============================================================

Count = Field(ge=0, le=100000)


class ExpectedCounts(BaseModel):
    expected_students: int = Count
    expected_staff: int = Count
    expected_guests: int = Count


class MealCreate(ExpectedCounts):
    meal_date: date
    meal_session_id: int = Field(gt=0)
    remarks: str | None = Field(default=None, max_length=500)


class MealUpdate(ExpectedCounts):
    actual_students: int | None = Field(default=None, ge=0, le=100000)
    actual_staff: int | None = Field(default=None, ge=0, le=100000)
    actual_guests: int | None = Field(default=None, ge=0, le=100000)
    remarks: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def actual_together(self):
        given = [v is not None for v in (self.actual_students, self.actual_staff, self.actual_guests)]
        if any(given) and not all(given):
            raise ValueError("Record the actual students, staff and guests served together (0 where none).")
        return self


class DishInput(BaseModel):
    dish_name: str = Field(min_length=1, max_length=200)
    menu_id: int | None = Field(default=None, gt=0)
    output_quantity: Decimal = Field(gt=0, max_digits=15, decimal_places=3)
    unit_id: int = Field(gt=0)
    remarks: str | None = Field(default=None, max_length=500)

    @field_validator("dish_name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Give the dish a name.")
        return value


class CarriedDishInput(BaseModel):
    remarks: str | None = Field(default=None, max_length=500)


class LeftoverInput(BaseModel):
    classification: Literal["RETAINED", "RETURNED_TO_SUPPLIER", "WASTED", "DISPOSED"]
    quantity: Decimal = Field(gt=0, max_digits=15, decimal_places=3)
    remarks: str = Field(min_length=1, max_length=500)

    @field_validator("remarks")
    @classmethod
    def remarks_given(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Give remarks for each leftover (at least 3 characters).")
        return value


class DistributionInput(BaseModel):
    distributed_quantity: Decimal = Field(ge=0, max_digits=15, decimal_places=3)
    remaining_quantity: Decimal = Field(ge=0, max_digits=15, decimal_places=3)
    leftovers: list[LeftoverInput] = Field(default_factory=list, max_length=4)


class CarryInput(BaseModel):
    leftover_id: int = Field(gt=0)
    remarks: str | None = Field(default=None, max_length=500)


# ============================================================
# HELPERS
# ============================================================

def lock_record(db: Session, user: User, record_id: int) -> MealRecord:
    """FOR NO KEY UPDATE: serialises changes to one record without blocking
    the foreign-key checks of rows that reference it."""
    record = (
        db.query(MealRecord)
        .filter(MealRecord.id == record_id, MealRecord.campus_id == user.campus_id)
        .with_for_update(key_share=True)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Meal record not found")
    return record


def require_open(record: MealRecord) -> None:
    if record.status == "CLOSED":
        raise HTTPException(status_code=409, detail=(
            "This meal record is closed and cannot be changed. An Admin or Kitchen Manager can reopen it with a reason."))
    if record.status == "CANCELLED":
        raise HTTPException(status_code=409, detail="This meal record was cancelled and cannot be changed.")


def get_dish(db: Session, record: MealRecord, dish_id: int) -> MealDish:
    dish = db.query(MealDish).filter(MealDish.id == dish_id, MealDish.meal_record_id == record.id).first()
    if not dish:
        raise HTTPException(status_code=404, detail="Dish not found on this meal record")
    return dish


def dishes_of(db: Session, record_id: int) -> list[MealDish]:
    return db.query(MealDish).filter(MealDish.meal_record_id == record_id).order_by(MealDish.id).all()


def leftovers_of(db: Session, dish_ids) -> dict[int, list[MealLeftover]]:
    found: dict[int, list[MealLeftover]] = {}
    order = {c: i for i, c in enumerate(LEFTOVER_CLASSES)}
    for row in db.query(MealLeftover).filter(MealLeftover.dish_id.in_(list(dish_ids) or [0])):
        found.setdefault(row.dish_id, []).append(row)
    for rows in found.values():
        rows.sort(key=lambda r: order[r.classification])
    return found


def carried_into(db: Session, leftover_ids) -> dict[int, MealDish]:
    """{source leftover id: the carried-in dish line that holds it}."""
    ids = list(leftover_ids)
    if not ids:
        return {}
    return {d.source_leftover_id: d for d in db.query(MealDish).filter(MealDish.source_leftover_id.in_(ids))}


def check_date_window(meal_date: date) -> None:
    limit = campus_today() + timedelta(days=AHEAD_DAYS)
    if meal_date > limit:
        raise HTTPException(status_code=422, detail=(
            f"Expected counts can be entered up to {AHEAD_DAYS} days ahead (until {limit.isoformat()})."))


def valid_unit(db: Session, user: User, unit_id: int) -> Unit:
    unit = db.query(Unit).filter(Unit.id == unit_id, Unit.campus_id == user.campus_id).first()
    if not unit or not unit.is_active:
        raise HTTPException(status_code=422, detail="Choose an active unit.")
    return unit


def valid_menu(db: Session, user: User, record: MealRecord, menu_id: int | None) -> int | None:
    if menu_id is None:
        return None
    menu = db.query(Menu).filter(Menu.id == menu_id, Menu.campus_id == user.campus_id).first()
    if not menu or not menu.is_active:
        raise HTTPException(status_code=422, detail="Choose an active menu.")
    if menu.meal_session_id != record.meal_session_id:
        raise HTTPException(status_code=422, detail=f"The menu {menu.name} belongs to another meal session.")
    return menu.id


def label_of(db: Session, record: MealRecord) -> str:
    session = db.query(MealSession.name).filter(MealSession.id == record.meal_session_id).scalar()
    return f"{session} on {record.meal_date.strftime('%d %b %Y')}"


def dish_snapshot(dish: MealDish, leftovers: list[MealLeftover]) -> dict:
    return {
        "dish_id": dish.id, "dish_name": dish.dish_name, "menu_id": dish.menu_id, "unit_id": dish.unit_id,
        "output_quantity": quantity_text(dish.output_quantity), "carried_quantity": quantity_text(dish.carried_quantity),
        "available_quantity": quantity_text(dish.available_quantity),
        "distributed_quantity": quantity_text(dish.distributed_quantity) if dish.distributed_quantity is not None else None,
        "remaining_quantity": quantity_text(dish.remaining_quantity) if dish.remaining_quantity is not None else None,
        "source_leftover_id": dish.source_leftover_id,
        "received_quantity": quantity_text(dish.received_quantity),
        "source_delivery_line_id": dish.source_delivery_line_id,
        "leftovers": [{"classification": l.classification, "quantity": quantity_text(l.quantity), "remarks": l.remarks}
                      for l in leftovers],
    }


def counts_snapshot(record: MealRecord) -> dict:
    return {k: getattr(record, k) for k in (
        "expected_students", "expected_staff", "expected_guests",
        "actual_students", "actual_staff", "actual_guests", "remarks")}


def touch(record: MealRecord) -> None:
    record.updated_at = datetime.now(timezone.utc)


# ---------- linked kitchen issues and actual usage (5-7, 5-8) ----------

def linked_issues(db: Session, record: MealRecord) -> tuple[list[dict], list[dict]]:
    """The kitchen issues of the record's campus, date and meal session, and
    the actual net usage per item from the confirmed ones (issued minus
    confirmed unused returns, in the item's standard unit)."""
    issues = (
        db.query(KitchenIssue)
        .filter(KitchenIssue.campus_id == record.campus_id, KitchenIssue.issue_date == record.meal_date,
                KitchenIssue.meal_session_id == record.meal_session_id, KitchenIssue.status != "CANCELLED")
        .order_by(KitchenIssue.id)
        .all()
    )
    menus = dict(db.query(Menu.id, Menu.name).filter(Menu.id.in_({i.menu_id for i in issues} or {0})))
    usage: dict[int, dict] = {}
    for issue in issues:
        if issue.status != "CONFIRMED":
            continue
        returned = returned_by_line(db, issue.id, ("CONFIRMED",))
        for line in db.query(KitchenIssueItem).filter(KitchenIssueItem.issue_id == issue.id):
            entry = usage.setdefault(line.item_id, {"issued": ZERO, "returned": ZERO, "unit_id": line.standard_unit_id})
            entry["issued"] += Decimal(str(line.standard_quantity))
            entry["returned"] += returned.get(line.id, ZERO)
    items = dict(db.query(Item.id, Item.name).filter(Item.id.in_(set(usage) or {0})))
    units = dict(db.query(Unit.id, Unit.symbol).filter(Unit.id.in_({u["unit_id"] for u in usage.values()} or {0})))
    usage_rows = sorted(({
        "item_id": item_id, "item_name": items.get(item_id), "unit_symbol": units.get(u["unit_id"]),
        "issued_quantity": quantity_text(u["issued"]), "returned_quantity": quantity_text(u["returned"]),
        "net_quantity": quantity_text(u["issued"] - u["returned"]),
    } for item_id, u in usage.items()), key=lambda r: (r["item_name"] or "").lower())
    issue_rows = [{"id": i.id, "issue_number": i.issue_number, "status": i.status,
                   "menu_name": menus.get(i.menu_id)} for i in issues]
    return issue_rows, usage_rows


def usage_map(usage_rows: list[dict]) -> dict:
    return {str(r["item_id"]): {"item_name": r["item_name"], "net_quantity": r["net_quantity"],
                                "unit_symbol": r["unit_symbol"]} for r in usage_rows}


def usage_changes(record: MealRecord, usage_rows: list[dict]) -> list[dict]:
    """Items whose net usage differs from the snapshot of the latest closing."""
    if record.status != "CLOSED" or record.closed_usage is None:
        return []
    now, then = usage_map(usage_rows), record.closed_usage
    changes = []
    for item_id in sorted(set(now) | set(then)):
        before = (then.get(item_id) or {}).get("net_quantity", "0.000")
        after = (now.get(item_id) or {}).get("net_quantity", "0.000")
        if before != after:
            entry = now.get(item_id) or then.get(item_id)
            changes.append({"item_id": int(item_id), "item_name": entry["item_name"], "unit_symbol": entry["unit_symbol"],
                            "net_at_closing": before, "net_now": after})
    return changes


# ---------- reconciliation (MEAL05) ----------

def reconciliation_problems(record: MealRecord, dishes: list[MealDish], leftovers: dict[int, list[MealLeftover]],
                            units: dict[int, str]) -> list[str]:
    problems = []
    if record.actual_students is None:
        problems.append("Record the actual people served (students, staff and guests).")
    for dish in dishes:
        unit = units.get(dish.unit_id, "")
        if dish.distributed_quantity is None:
            problems.append(f"{dish.dish_name}: record the distributed and remaining quantities.")
            continue
        remaining = Decimal(str(dish.remaining_quantity))
        classified = sum((Decimal(str(l.quantity)) for l in leftovers.get(dish.id, [])), ZERO)
        if classified != remaining:
            problems.append(f"{dish.dish_name}: leftovers classified {quantity_text(classified)} {unit}, "
                            f"remaining {quantity_text(remaining)} {unit}.")
    return problems


# ============================================================
# SERIALISATION
# ============================================================

def outsourced():
    from app.api.routes import outsourced as module  # avoids a circular import

    return module


def planning_for_record(db: Session, user: User, record: MealRecord):
    from app.api.routes.planning import planning_for_record as panel  # avoids a circular import

    return panel(db, user, record)


def record_detail(db: Session, user: User, record: MealRecord) -> dict:
    dishes = dishes_of(db, record.id)
    leftovers = leftovers_of(db, [d.id for d in dishes])
    all_leftover_ids = [l.id for rows in leftovers.values() for l in rows]
    outgoing = carried_into(db, all_leftover_ids)
    unit_ids = {d.unit_id for d in dishes}
    units = dict(db.query(Unit.id, Unit.symbol).filter(Unit.id.in_(unit_ids or {0})))
    menus = dict(db.query(Menu.id, Menu.name).filter(Menu.id.in_({d.menu_id for d in dishes if d.menu_id} or {0})))
    linked_record_ids = {d.source_meal_record_id for d in dishes if d.source_meal_record_id} | {
        d.meal_record_id for d in outgoing.values()}
    linked = {r.id: r for r in db.query(MealRecord).filter(MealRecord.id.in_(linked_record_ids or {0}))}
    sessions = dict(db.query(MealSession.id, MealSession.name).filter(
        MealSession.id.in_({record.meal_session_id} | {r.meal_session_id for r in linked.values()})))
    names = names_of(db, [record.created_by, record.closed_by, record.reopened_by, record.cancelled_by])
    issue_rows, usage_rows = linked_issues(db, record)
    received = outsourced().received_sources(db, dishes)

    def record_ref(rid):
        r = linked.get(rid)
        return {"id": r.id, "meal_date": r.meal_date.isoformat(), "meal_session_name": sessions.get(r.meal_session_id),
                "status": r.status} if r else None

    out_dishes = []
    for d in dishes:
        rows = leftovers.get(d.id, [])
        classified = sum((Decimal(str(l.quantity)) for l in rows), ZERO)
        out_dishes.append({
            "id": d.id, "dish_name": d.dish_name, "menu_id": d.menu_id, "menu_name": menus.get(d.menu_id),
            "unit_id": d.unit_id, "unit_symbol": units.get(d.unit_id),
            "output_quantity": quantity_text(d.output_quantity), "carried_quantity": quantity_text(d.carried_quantity),
            "received_quantity": quantity_text(d.received_quantity),
            "kind": "CARRIED" if d.source_leftover_id else ("RECEIVED" if d.source_delivery_line_id else "PREPARED"),
            "available_quantity": quantity_text(d.available_quantity),
            "distributed_quantity": quantity_text(d.distributed_quantity) if d.distributed_quantity is not None else None,
            "remaining_quantity": quantity_text(d.remaining_quantity) if d.remaining_quantity is not None else None,
            "classified_quantity": quantity_text(classified),
            "reconciled": d.distributed_quantity is not None and classified == Decimal(str(d.remaining_quantity)),
            "remarks": d.remarks,
            # Stage 8a: the outsourced delivery the received food came from.
            "received_from": received.get(d.id),
            "carried_in": None if d.source_leftover_id is None else {
                "leftover_id": d.source_leftover_id, "dish_id": d.source_dish_id,
                "record": record_ref(d.source_meal_record_id),
            },
            "leftovers": [{
                "id": l.id, "classification": l.classification, "quantity": quantity_text(l.quantity),
                "remarks": l.remarks,
                "carried_to": ({"dish_id": outgoing[l.id].id, "record": record_ref(outgoing[l.id].meal_record_id)}
                               if l.id in outgoing else None),
            } for l in rows],
        })

    def total(prefix):
        values = [getattr(record, f"{prefix}_{g}") for g in ("students", "staff", "guests")]
        return None if any(v is None for v in values) else sum(values)

    return {
        "id": record.id,
        "meal_date": record.meal_date.isoformat(),
        "meal_session_id": record.meal_session_id,
        "meal_session_name": sessions.get(record.meal_session_id),
        "status": record.status,
        "expected_students": record.expected_students, "expected_staff": record.expected_staff,
        "expected_guests": record.expected_guests, "expected_total": total("expected"),
        "actual_students": record.actual_students, "actual_staff": record.actual_staff,
        "actual_guests": record.actual_guests, "actual_total": total("actual"),
        "remarks": record.remarks,
        "created_by_name": names.get(record.created_by), "created_at": utc_iso(record.created_at),
        "updated_at": utc_iso(record.updated_at) if record.updated_at else None,
        "closed_by_name": names.get(record.closed_by),
        "closed_at": utc_iso(record.closed_at) if record.closed_at else None,
        "reopened_by_name": names.get(record.reopened_by),
        "reopened_at": utc_iso(record.reopened_at) if record.reopened_at else None,
        "reopen_reason": record.reopen_reason, "reopen_count": record.reopen_count,
        "cancelled_by_name": names.get(record.cancelled_by),
        "cancelled_at": utc_iso(record.cancelled_at) if record.cancelled_at else None,
        "cancellation_reason": record.cancellation_reason,
        "actual_allowed": record.meal_date <= campus_today(),
        "dishes": out_dishes,
        "reconciliation_problems": reconciliation_problems(record, dishes, leftovers, units)
        if record.status == "OPEN" else [],
        # Stage 8a: confirmed outsourced food of this date and exact session
        # not on the record (only while it is CLOSED: reconciliation pending).
        "outsourced_pending": outsourced().pending_for_record(db, record),
        "linked_issues": issue_rows,
        "usage": usage_rows,
        "usage_changes_since_closing": usage_changes(record, usage_rows),
        # Stage 6: the plan of the exact date and session, and plan vs actual
        # (MEAL02 criterion 4, PLAN08), for ADMIN and KITCHEN_MANAGER only;
        # None for anyone else.
        "planning": planning_for_record(db, user, record),
    }


# ============================================================
# FORM OPTIONS AND LISTS
# ============================================================

@router.get("/options")
def meal_form_options(db: Session = Depends(get_db), user: User = Depends(form_user)):
    """Sessions, menus and units for the meal forms, so a user with the meal
    codes does not need menu.read or inventory.read."""
    campus_id = user.campus_id
    return {
        "today": campus_today().isoformat(),
        "latest_date": (campus_today() + timedelta(days=AHEAD_DAYS)).isoformat(),
        "meal_sessions": [{"id": s.id, "name": s.name} for s in db.query(MealSession).filter(
            MealSession.campus_id == campus_id, MealSession.is_active.is_(True)).order_by(MealSession.id)],
        "menus": [{"id": m.id, "name": m.name, "meal_session_id": m.meal_session_id} for m in db.query(Menu).filter(
            Menu.campus_id == campus_id, Menu.is_active.is_(True)).order_by(func.lower(Menu.name))],
        "units": [{"id": u.id, "name": u.name, "symbol": u.symbol, "dimension": u.dimension} for u in db.query(Unit).filter(
            Unit.campus_id == campus_id, Unit.is_active.is_(True)).order_by(Unit.name)],
    }


@router.get("")
def list_meal_records(
    status_filter: str | None = Query(default=None, alias="status", pattern="^(OPEN|CLOSED|CANCELLED)$"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    meal_session_id: int | None = Query(default=None, gt=0),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("meal.read")),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from cannot be after date_to.")
    query = db.query(MealRecord).filter(MealRecord.campus_id == user.campus_id)
    if date_from:
        query = query.filter(MealRecord.meal_date >= date_from)
    if date_to:
        query = query.filter(MealRecord.meal_date <= date_to)
    if meal_session_id:
        query = query.filter(MealRecord.meal_session_id == meal_session_id)
    counts = dict(query.with_entities(MealRecord.status, func.count(MealRecord.id)).group_by(MealRecord.status))
    if status_filter:
        query = query.filter(MealRecord.status == status_filter)
    total = query.count()
    records = (query.order_by(MealRecord.meal_date.desc(), MealRecord.meal_session_id, MealRecord.id.desc())
               .offset((page - 1) * page_size).limit(page_size).all())
    ids = [r.id for r in records] or [0]
    sessions = dict(db.query(MealSession.id, MealSession.name).filter(
        MealSession.id.in_({r.meal_session_id for r in records} or {0})))
    dish_counts = dict(db.query(MealDish.meal_record_id, func.count(MealDish.id)).filter(
        MealDish.meal_record_id.in_(ids)).group_by(MealDish.meal_record_id))
    names = names_of(db, [r.created_by for r in records] + [r.closed_by for r in records])

    def total_of(r, prefix):
        values = [getattr(r, f"{prefix}_{g}") for g in ("students", "staff", "guests")]
        return None if any(v is None for v in values) else sum(values)

    return {
        "items": [{
            "id": r.id, "meal_date": r.meal_date.isoformat(), "meal_session_name": sessions.get(r.meal_session_id),
            "status": r.status, "expected_total": total_of(r, "expected"), "actual_total": total_of(r, "actual"),
            "dish_count": dish_counts.get(r.id, 0), "created_by_name": names.get(r.created_by),
            "closed_by_name": names.get(r.closed_by), "closed_at": utc_iso(r.closed_at) if r.closed_at else None,
            "reopen_count": r.reopen_count,
        } for r in records],
        "status_counts": {s: counts.get(s, 0) for s in ("OPEN", "CLOSED", "CANCELLED")},
        **page_meta(total, page, page_size),
    }


@router.get("/retained")
def open_retained_food(
    for_record: int = Query(gt=0),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("meal.update")),
):
    """Retained leftovers of CLOSED records, not yet carried, that may be
    carried into the given OPEN record (interim, Q11)."""
    record = db.query(MealRecord).filter(MealRecord.id == for_record, MealRecord.campus_id == user.campus_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Meal record not found")
    rows = (
        db.query(MealLeftover, MealDish, MealRecord)
        .join(MealDish, MealDish.id == MealLeftover.dish_id)
        .join(MealRecord, MealRecord.id == MealLeftover.meal_record_id)
        .filter(MealLeftover.campus_id == user.campus_id, MealLeftover.classification == "RETAINED",
                MealRecord.status == "CLOSED", MealRecord.id != record.id, MealRecord.meal_date <= record.meal_date,
                ~MealLeftover.id.in_(db.query(MealDish.source_leftover_id).filter(MealDish.source_leftover_id.isnot(None))))
        .order_by(MealRecord.meal_date.desc(), MealLeftover.id.desc())
        .all()
    )
    sessions = dict(db.query(MealSession.id, MealSession.name).filter(
        MealSession.id.in_({r.meal_session_id for _l, _d, r in rows} or {0})))
    units = dict(db.query(Unit.id, Unit.symbol).filter(Unit.id.in_({l.unit_id for l, _d, _r in rows} or {0})))
    return {"items": [{
        "leftover_id": l.id, "dish_name": d.dish_name, "quantity": quantity_text(l.quantity),
        "unit_symbol": units.get(l.unit_id), "remarks": l.remarks,
        "record": {"id": r.id, "meal_date": r.meal_date.isoformat(), "meal_session_name": sessions.get(r.meal_session_id)},
    } for l, d, r in rows]}


# ============================================================
# RECORDS
# ============================================================

@router.post("", status_code=201)
def create_meal_record(payload: MealCreate, db: Session = Depends(get_db),
                       user: User = Depends(require_permission("meal.create"))):
    check_date_window(payload.meal_date)
    session = db.query(MealSession).filter(MealSession.id == payload.meal_session_id,
                                           MealSession.campus_id == user.campus_id).first()
    if not session or not session.is_active:
        raise HTTPException(status_code=422, detail="Choose an active meal session.")
    # Serialises with confirming an outsourced delivery for this session, so
    # food confirmed at the same moment is never left waiting (Stage 8a).
    outsourced().lock_session(db, user.campus_id, session.id)
    existing = db.query(MealRecord.id).filter(
        MealRecord.campus_id == user.campus_id, MealRecord.meal_date == payload.meal_date,
        MealRecord.meal_session_id == session.id, MealRecord.status != "CANCELLED").scalar()
    if existing:
        raise HTTPException(status_code=409, detail=(
            f"A meal record for {session.name} on {payload.meal_date.strftime('%d %b %Y')} already exists (#{existing})."))
    try:
        record = MealRecord(campus_id=user.campus_id, meal_date=payload.meal_date, meal_session_id=session.id,
                            status="OPEN", expected_students=payload.expected_students,
                            expected_staff=payload.expected_staff, expected_guests=payload.expected_guests,
                            remarks=clean(payload.remarks), created_by=user.id)
        db.add(record)
        db.flush()
        record_audit(db, user, "CREATE", ENTITY, record.id, {
            "meal_date": payload.meal_date.isoformat(), "meal_session_id": session.id, **counts_snapshot(record)})
        outsourced().attach_received(db, user, record)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=(
            f"A meal record for {session.name} on {payload.meal_date.strftime('%d %b %Y')} was recorded at the same time."))
    db.refresh(record)
    return record_detail(db, user, record)


@router.get("/{record_id}")
def get_meal_record(record_id: int, db: Session = Depends(get_db),
                    user: User = Depends(require_permission("meal.read"))):
    record = db.query(MealRecord).filter(MealRecord.id == record_id, MealRecord.campus_id == user.campus_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Meal record not found")
    return record_detail(db, user, record)


@router.put("/{record_id}")
def update_counts(record_id: int, payload: MealUpdate, db: Session = Depends(get_db),
                  user: User = Depends(require_permission("meal.update"))):
    """Expected and actual counts and remarks of an OPEN record (MEAL01)."""
    record = lock_record(db, user, record_id)
    require_open(record)
    if payload.actual_students is not None and record.meal_date > campus_today():
        raise HTTPException(status_code=422, detail="Actual people served can be recorded on or after the meal date.")
    before = counts_snapshot(record)
    for key in ("expected_students", "expected_staff", "expected_guests", "actual_students", "actual_staff", "actual_guests"):
        setattr(record, key, getattr(payload, key))
    record.remarks = clean(payload.remarks)
    touch(record)
    record_audit(db, user, "UPDATE_COUNTS", ENTITY, record.id, {"before": before, "after": counts_snapshot(record)})
    db.commit()
    db.refresh(record)
    return record_detail(db, user, record)


# ============================================================
# DISHES
# ============================================================

@router.post("/{record_id}/dishes", status_code=201)
def add_dish(record_id: int, payload: DishInput, db: Session = Depends(get_db),
             user: User = Depends(require_permission("meal.update"))):
    record = lock_record(db, user, record_id)
    require_open(record)
    menu_id = valid_menu(db, user, record, payload.menu_id)
    unit = valid_unit(db, user, payload.unit_id)
    output = quantity(payload.output_quantity)
    dish = MealDish(campus_id=user.campus_id, meal_record_id=record.id, dish_name=payload.dish_name, menu_id=menu_id,
                    unit_id=unit.id, output_quantity=output, carried_quantity=ZERO, available_quantity=output,
                    remarks=clean(payload.remarks), created_by=user.id)
    db.add(dish)
    db.flush()
    touch(record)
    record_audit(db, user, "ADD_DISH", ENTITY, record.id, dish_snapshot(dish, []))
    db.commit()
    db.refresh(record)
    return record_detail(db, user, record)


@router.put("/{record_id}/dishes/{dish_id}")
def update_dish(record_id: int, dish_id: int, payload: DishInput, db: Session = Depends(get_db),
                user: User = Depends(require_permission("meal.update"))):
    """A prepared dish's name, menu, output, unit and remarks. Output and unit
    can change only before the distribution is recorded."""
    record = lock_record(db, user, record_id)
    require_open(record)
    dish = get_dish(db, record, dish_id)
    if dish.source_leftover_id is not None:
        raise HTTPException(status_code=409, detail=(
            "Carried-in retained food keeps its name, quantity and unit; only its remarks can change."))
    if dish.source_delivery_line_id is not None:
        raise HTTPException(status_code=409, detail=(
            "Received outsourced food keeps the name, quantity and unit of its confirmed delivery; only its "
            "remarks can change."))
    menu_id = valid_menu(db, user, record, payload.menu_id)
    unit = valid_unit(db, user, payload.unit_id)
    output = quantity(payload.output_quantity)
    if dish.distributed_quantity is not None and (output != Decimal(str(dish.output_quantity)) or unit.id != dish.unit_id):
        raise HTTPException(status_code=409, detail=(
            f"{dish.dish_name} already has its distribution recorded. Clear the distribution before changing the output or unit."))
    before = dish_snapshot(dish, leftovers_of(db, [dish.id]).get(dish.id, []))
    dish.dish_name, dish.menu_id, dish.unit_id = payload.dish_name, menu_id, unit.id
    dish.output_quantity, dish.available_quantity, dish.remarks = output, output, clean(payload.remarks)
    dish.updated_at = datetime.now(timezone.utc)
    touch(record)
    db.flush()
    record_audit(db, user, "UPDATE_DISH", ENTITY, record.id, {"before": before, "after": dish_snapshot(dish, [])})
    db.commit()
    db.refresh(record)
    return record_detail(db, user, record)


@router.put("/{record_id}/dishes/{dish_id}/remarks")
def update_carried_remarks(record_id: int, dish_id: int, payload: CarriedDishInput, db: Session = Depends(get_db),
                           user: User = Depends(require_permission("meal.update"))):
    record = lock_record(db, user, record_id)
    require_open(record)
    dish = get_dish(db, record, dish_id)
    before = dish.remarks
    dish.remarks = clean(payload.remarks)
    dish.updated_at = datetime.now(timezone.utc)
    touch(record)
    record_audit(db, user, "UPDATE_DISH_REMARKS", ENTITY, record.id, {"dish_id": dish.id, "before": before, "after": dish.remarks})
    db.commit()
    db.refresh(record)
    return record_detail(db, user, record)


def refuse_if_carried_out(db: Session, dish: MealDish, action: str) -> None:
    carried = carried_into(db, [l.id for l in leftovers_of(db, [dish.id]).get(dish.id, [])])
    if carried:
        destination = db.get(MealRecord, next(iter(carried.values())).meal_record_id)
        raise HTTPException(status_code=409, detail=(
            f"The retained {dish.dish_name} is carried into {label_of(db, destination)}. "
            f"Remove it there first (while that record is open) to {action}."))


@router.delete("/{record_id}/dishes/{dish_id}")
def remove_dish(record_id: int, dish_id: int, db: Session = Depends(get_db),
                user: User = Depends(require_permission("meal.update"))):
    """Remove a dish (and its leftovers) from an OPEN record. Removing a
    carried-in line frees its source retained leftover again."""
    record = lock_record(db, user, record_id)
    require_open(record)
    dish = get_dish(db, record, dish_id)
    if dish.source_delivery_line_id is not None:
        source = outsourced().received_sources(db, [dish]).get(dish.id) or {}
        raise HTTPException(status_code=409, detail=(
            f"{dish.dish_name} was received through outsourced delivery {source.get('delivery_number', '')}. It is "
            "removed only by cancelling that delivery (Admin or Kitchen Manager), not from the meal record."))
    refuse_if_carried_out(db, dish, "remove this dish")
    rows = leftovers_of(db, [dish.id]).get(dish.id, [])
    snapshot = dish_snapshot(dish, rows)
    for row in rows:
        db.delete(row)
    db.flush()
    db.delete(dish)
    touch(record)
    db.flush()
    record_audit(db, user, "REMOVE_CARRIED" if dish.source_leftover_id else "REMOVE_DISH", ENTITY, record.id, snapshot)
    if dish.source_leftover_id:
        record_audit(db, user, "CARRY_REMOVED", ENTITY, dish.source_meal_record_id, {
            "leftover_id": dish.source_leftover_id, "removed_from_record_id": record.id})
    db.commit()
    db.refresh(record)
    return record_detail(db, user, record)


@router.put("/{record_id}/dishes/{dish_id}/distribution")
def set_distribution(record_id: int, dish_id: int, payload: DistributionInput, db: Session = Depends(get_db),
                     user: User = Depends(require_permission("meal.update"))):
    """Distributed and remaining quantities and the leftover classification of
    one dish (MEAL03–MEAL05). Available = distributed + remaining exactly; the
    leftovers are either not classified yet (none) or add up exactly to the
    remaining quantity; one line per classification, each with remarks."""
    record = lock_record(db, user, record_id)
    require_open(record)
    dish = get_dish(db, record, dish_id)
    unit = db.query(Unit.symbol).filter(Unit.id == dish.unit_id).scalar() or ""
    available = Decimal(str(dish.available_quantity))
    distributed, remaining = quantity(payload.distributed_quantity), quantity(payload.remaining_quantity)
    if distributed + remaining != available:
        raise HTTPException(status_code=422, detail=(
            f"{dish.dish_name}: available {quantity_text(available)} {unit} must equal distributed + remaining "
            f"({quantity_text(distributed)} + {quantity_text(remaining)} = {quantity_text(distributed + remaining)} {unit})."))
    classes = [l.classification for l in payload.leftovers]
    if len(classes) != len(set(classes)):
        raise HTTPException(status_code=422, detail="Use each leftover classification once per dish.")
    classified = sum((quantity(l.quantity) for l in payload.leftovers), ZERO)
    if payload.leftovers and classified != remaining:
        raise HTTPException(status_code=422, detail=(
            f"{dish.dish_name}: the leftovers add up to {quantity_text(classified)} {unit} but "
            f"{quantity_text(remaining)} {unit} remains. Each remaining quantity is classified exactly once."))
    if remaining == 0 and payload.leftovers:
        raise HTTPException(status_code=422, detail=f"{dish.dish_name}: nothing remains, so there are no leftovers to classify.")

    existing = {l.classification: l for l in leftovers_of(db, [dish.id]).get(dish.id, [])}
    carried = carried_into(db, [l.id for l in existing.values()])
    locked = next((l for l in existing.values() if l.id in carried), None)
    if locked is not None:
        wanted = {l.classification: quantity(l.quantity) for l in payload.leftovers}
        if wanted.get(locked.classification) != Decimal(str(locked.quantity)):
            destination = db.get(MealRecord, carried[locked.id].meal_record_id)
            raise HTTPException(status_code=409, detail=(
                f"The retained {quantity_text(locked.quantity)} {unit} of {dish.dish_name} is carried into "
                f"{label_of(db, destination)} and cannot change. Remove it there first (while that record is open)."))

    before = dish_snapshot(dish, list(existing.values()))
    wanted_classes = {l.classification for l in payload.leftovers}
    for classification, row in existing.items():
        if classification not in wanted_classes:
            db.delete(row)
    db.flush()
    dish.distributed_quantity, dish.remaining_quantity = distributed, remaining
    dish.updated_at = datetime.now(timezone.utc)
    for item in payload.leftovers:
        row = existing.get(item.classification)
        if row is None:
            db.add(MealLeftover(campus_id=user.campus_id, meal_record_id=record.id, dish_id=dish.id,
                                classification=item.classification, quantity=quantity(item.quantity),
                                unit_id=dish.unit_id, remarks=item.remarks, created_by=user.id))
        else:
            row.quantity, row.remarks = quantity(item.quantity), item.remarks
    touch(record)
    try:
        db.flush()
        after = dish_snapshot(dish, leftovers_of(db, [dish.id]).get(dish.id, []))
        record_audit(db, user, "SET_DISTRIBUTION", ENTITY, record.id, {"before": before, "after": after})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="The distribution could not be saved. Reload and try again.")
    db.refresh(record)
    return record_detail(db, user, record)


@router.delete("/{record_id}/dishes/{dish_id}/distribution")
def clear_distribution(record_id: int, dish_id: int, db: Session = Depends(get_db),
                       user: User = Depends(require_permission("meal.update"))):
    record = lock_record(db, user, record_id)
    require_open(record)
    dish = get_dish(db, record, dish_id)
    refuse_if_carried_out(db, dish, "clear its distribution")
    rows = leftovers_of(db, [dish.id]).get(dish.id, [])
    before = dish_snapshot(dish, rows)
    for row in rows:
        db.delete(row)
    db.flush()
    dish.distributed_quantity = dish.remaining_quantity = None
    dish.updated_at = datetime.now(timezone.utc)
    touch(record)
    record_audit(db, user, "CLEAR_DISTRIBUTION", ENTITY, record.id, before)
    db.commit()
    db.refresh(record)
    return record_detail(db, user, record)


# ============================================================
# RETAINED FOOD CARRIED FORWARD (interim, client question Q11)
# ============================================================

@router.post("/{record_id}/carry", status_code=201)
def carry_retained(record_id: int, payload: CarryInput, db: Session = Depends(get_db),
                   user: User = Depends(require_permission("meal.update"))):
    """Carry one retained leftover of a CLOSED record, whole, into this OPEN
    record as its own dish line (same name and unit). Each retained line is
    carried once (database unique constraint); the source is locked by a
    composite foreign key while carried. No stock, purchase or credit."""
    source_leftover = db.query(MealLeftover).filter(
        MealLeftover.id == payload.leftover_id, MealLeftover.campus_id == user.campus_id).first()
    if not source_leftover:
        raise HTTPException(status_code=404, detail="Retained food not found")
    if source_leftover.meal_record_id == record_id:
        raise HTTPException(status_code=422, detail="Retained food is carried into another meal record, not its own.")
    # Both records are locked in id order, so two carries cannot deadlock.
    locked = {rid: lock_record(db, user, rid) for rid in sorted((record_id, source_leftover.meal_record_id))}
    record = locked[record_id]
    source = locked[source_leftover.meal_record_id]
    require_open(record)
    db.refresh(source_leftover)
    if source_leftover.classification != "RETAINED":
        raise HTTPException(status_code=422, detail="Only retained leftovers can be carried forward.")
    if source.status != "CLOSED":
        raise HTTPException(status_code=409, detail=(
            f"The meal record of {label_of(db, source)} is not closed, so its retained food is not final yet."))
    if record.meal_date < source.meal_date:
        raise HTTPException(status_code=422, detail="Retained food can be carried only into a meal on the same or a later date.")
    already = carried_into(db, [source_leftover.id])
    if already:
        destination = db.get(MealRecord, already[source_leftover.id].meal_record_id)
        raise HTTPException(status_code=409, detail=(
            f"This retained food was already carried into {label_of(db, destination)}; it can be carried only once."))
    source_dish = db.get(MealDish, source_leftover.dish_id)
    carried_qty = Decimal(str(source_leftover.quantity))
    try:
        dish = MealDish(
            campus_id=user.campus_id, meal_record_id=record.id, dish_name=source_dish.dish_name, menu_id=None,
            unit_id=source_leftover.unit_id, output_quantity=ZERO, carried_quantity=carried_qty,
            available_quantity=carried_qty, remarks=clean(payload.remarks), created_by=user.id,
            source_leftover_id=source_leftover.id, source_dish_id=source_dish.id,
            source_meal_record_id=source.id, source_classification="RETAINED",
        )
        db.add(dish)
        db.flush()
        touch(record)
        details = {"leftover_id": source_leftover.id, "source_record_id": source.id, "source_dish_id": source_dish.id,
                   "dish_name": source_dish.dish_name, "quantity": quantity_text(carried_qty),
                   "unit_id": source_leftover.unit_id, "destination_record_id": record.id, "dish_id": dish.id}
        record_audit(db, user, "CARRY_IN", ENTITY, record.id, details)
        record_audit(db, user, "CARRIED_OUT", ENTITY, source.id, details)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="This retained food was carried at the same time by someone else; it can be carried only once.")
    db.refresh(record)
    return record_detail(db, user, record)


# ============================================================
# CLOSE, CANCEL, REOPEN, HISTORY (5-1, 5-9)
# ============================================================

@router.post("/{record_id}/close")
def close_record(record_id: int, db: Session = Depends(get_db),
                 user: User = Depends(require_permission("meal.update"))):
    """Close a fully reconciled record (meal.update). It becomes read-only;
    a snapshot of the record and of the linked issues' net usage is kept."""
    record = lock_record(db, user, record_id)
    require_open(record)
    dishes = dishes_of(db, record.id)
    leftovers = leftovers_of(db, [d.id for d in dishes])
    units = dict(db.query(Unit.id, Unit.symbol).filter(Unit.id.in_({d.unit_id for d in dishes} or {0})))
    problems = reconciliation_problems(record, dishes, leftovers, units)
    if problems:
        raise HTTPException(status_code=422, detail="The meal record does not reconcile yet: " + " ".join(problems))
    issue_rows, usage_rows = linked_issues(db, record)
    now = datetime.now(timezone.utc)
    record.status, record.closed_by, record.closed_at = "CLOSED", user.id, now
    record.closed_usage = usage_map(usage_rows)
    touch(record)
    record_audit(db, user, "CLOSE", ENTITY, record.id, {
        "counts": counts_snapshot(record),
        "dishes": [dish_snapshot(d, leftovers.get(d.id, [])) for d in dishes],
        "linked_issues": issue_rows, "usage": usage_rows, "reopen_count": record.reopen_count,
    })
    db.commit()
    db.refresh(record)
    return record_detail(db, user, record)


@router.post("/{record_id}/cancel")
def cancel_record(record_id: int, payload: Reason, db: Session = Depends(get_db),
                  user: User = Depends(require_permission("meal.update"))):
    """Cancel an OPEN record made for the wrong date or session. Refused while
    retained food is carried into it or out of it."""
    record = lock_record(db, user, record_id)
    require_open(record)
    dishes = dishes_of(db, record.id)
    if any(d.source_leftover_id for d in dishes):
        raise HTTPException(status_code=409, detail="Retained food is carried into this record. Remove it first.")
    if carried_into(db, [l.id for rows in leftovers_of(db, [d.id for d in dishes]).values() for l in rows]):
        raise HTTPException(status_code=409, detail="Retained food from this record is carried into a later meal.")
    # Stage 8a: received outsourced food is released, to wait for the correct
    # record of this date and session (the delivery itself is unchanged).
    released = outsourced().detach_received(db, user, record)
    now = datetime.now(timezone.utc)
    record.status, record.cancelled_by, record.cancelled_at, record.cancellation_reason = "CANCELLED", user.id, now, payload.reason
    touch(record)
    record_audit(db, user, "CANCEL", ENTITY, record.id, {"reason": payload.reason,
                                                         "released_received_lines": len(released)})
    db.commit()
    db.refresh(record)
    return record_detail(db, user, record)


@router.post("/{record_id}/reopen")
def reopen_record(record_id: int, payload: Reason, db: Session = Depends(get_db),
                  user: User = Depends(managers)):
    """ADMIN or KITCHEN_MANAGER: reopen a CLOSED record with a reason
    (interim rule for historical corrections). Who, when and why are kept on
    the record and in the audit history; earlier closings stay in history."""
    record = lock_record(db, user, record_id)
    if record.status != "CLOSED":
        raise HTTPException(status_code=409, detail="Only a closed meal record can be reopened.")
    now = datetime.now(timezone.utc)
    previous = {"closed_by": record.closed_by, "closed_at": utc_iso(record.closed_at)}
    record.status = "OPEN"
    record.reopened_by, record.reopened_at, record.reopen_reason = user.id, now, payload.reason
    record.reopen_count = (record.reopen_count or 0) + 1
    touch(record)
    record_audit(db, user, "REOPEN", ENTITY, record.id, {
        "reason": payload.reason, "reopen_count": record.reopen_count, "previous_closing": previous})
    # Stage 8a: outsourced food confirmed while the record was closed is added now.
    outsourced().attach_received(db, user, record)
    db.commit()
    db.refresh(record)
    return record_detail(db, user, record)


@router.get("/{record_id}/history")
def record_history(record_id: int, db: Session = Depends(get_db), user: User = Depends(managers)):
    """Every audited action on the record, oldest first (ADMIN and
    KITCHEN_MANAGER, who hold audit.read)."""
    record = db.query(MealRecord).filter(MealRecord.id == record_id, MealRecord.campus_id == user.campus_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Meal record not found")
    rows = (db.query(AuditLog).filter(AuditLog.campus_id == user.campus_id, AuditLog.entity_type == ENTITY,
                                      AuditLog.entity_id == record.id).order_by(AuditLog.id).all())
    names = names_of(db, [r.user_id for r in rows])
    return {"items": [{"id": r.id, "action": r.action, "user_name": names.get(r.user_id),
                       "created_at": utc_iso(r.created_at), "details": r.details} for r in rows]}
