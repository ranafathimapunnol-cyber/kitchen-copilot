"""Kitchen issues and unused returns (Stage 4 slice 4b: STK02, STK03,
STK04 criterion 4).

Decisions applied (docs/STAGE-4-STOCK-PLAN.md):
- S1: consumption.create records a draft, consumption.update edits,
  cancels and confirms one (4b-3: including the user's own draft),
  consumption.read views; reversals are ADMIN and KITCHEN_MANAGER only.
- S2: confirming an issue, and reversing a return, lower stock and go
  through the shared posting check (no balance below zero at any point).
- S4: a whole confirmed document is reversed with a reason; an issue with a
  confirmed return is reversed only after the return.
- S5: an issue names its date, meal session and menu; "responsible user"
  is the user who records it.
- 4b-1/4b-2: effective at confirmation when dated today, at the end of the
  date when backdated; a return never before its issue.
- 4b-4: KI-00001 / KR-00001 per campus.
Every query is limited to the signed-in user's campus. Locks are taken in
one order everywhere: issue, then return, then campus (numbering), then
items (posting).
"""

from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_current_user,
    require_permission,
    require_roles,
    user_has_permission,
)
from app.api.routes.master_data import get_unit_conversion_factor, record_audit
from app.core.clock import campus_today, utc_iso
from app.db.session import get_db
from app.models.campus import Campus
from app.models.master_data import Category, Item, MealSession, Menu, Unit, UnitConversion
from app.models.purchases import StockMovement
from app.models.stock import KitchenIssue, KitchenIssueItem, KitchenReturn, KitchenReturnItem
from app.models.user import User, UserRole
from app.services.outsourced_guard import not_outsourced, outsourced_message
from app.services import stock_ledger
from app.services.stock_ledger import Posting, quantity, quantity_text

router = APIRouter(tags=["Kitchen Issues and Returns"])

ZERO = Decimal("0")
FACTOR_STEP = Decimal("0.000000000001")
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

stock_managers = require_roles(UserRole.ADMIN, UserRole.KITCHEN_MANAGER)


def entry_user(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """The issue and return forms: anyone who may record or edit a draft."""
    if user_has_permission(db, user, "consumption.create") or user_has_permission(db, user, "consumption.update"):
        return user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This permission has not been assigned to you.")


# ============================================================
# INPUT
# ============================================================

class Reason(BaseModel):
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def at_least_three(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Give a reason (at least 3 characters).")
        return value


class IssueLineInput(BaseModel):
    item_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, max_digits=15, decimal_places=3)
    unit_id: int | None = Field(default=None, gt=0)
    remarks: str | None = Field(default=None, max_length=500)


class IssueInput(BaseModel):
    issue_date: date
    meal_session_id: int = Field(gt=0)
    menu_id: int = Field(gt=0)
    remarks: str | None = Field(default=None, max_length=500)
    lines: list[IssueLineInput] = Field(min_length=1, max_length=100)


class ReturnLineInput(BaseModel):
    issue_item_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, max_digits=15, decimal_places=3)
    unit_id: int | None = Field(default=None, gt=0)
    remarks: str | None = Field(default=None, max_length=500)


class ReturnInput(BaseModel):
    return_date: date
    remarks: str | None = Field(default=None, max_length=500)
    lines: list[ReturnLineInput] = Field(min_length=1, max_length=100)


# ============================================================
# HELPERS
# ============================================================

def page_meta(total: int, page: int, page_size: int) -> dict:
    return {"total": total, "page": page, "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size}


def names_of(db: Session, ids) -> dict[int, str]:
    ids = {i for i in ids if i}
    return dict(db.query(User.id, User.full_name).filter(User.id.in_(ids))) if ids else {}


def clean(text: str | None) -> str | None:
    text = (text or "").strip()
    return text or None


def converted(db: Session, user: User, item: Item, unit_id: int | None, amount: Decimal):
    """(unit, factor, standard quantity) for a quantity entered in `unit_id`
    (the item's standard unit if omitted). Explicit conversions only."""
    unit = db.query(Unit).filter(Unit.id == (unit_id or item.standard_unit_id), Unit.campus_id == user.campus_id).first()
    if not unit:
        raise HTTPException(status_code=422, detail=f"Unit not found for {item.name}.")
    if unit.id != item.standard_unit_id and not unit.is_active:
        raise HTTPException(status_code=422, detail=f"{unit.name} is inactive.")
    factor = get_unit_conversion_factor(db, user, unit.id, item.standard_unit_id).quantize(FACTOR_STEP)
    standard = quantity(amount * factor)
    if factor <= 0 or standard <= 0:
        raise HTTPException(status_code=422, detail=f"{item.name}: the quantity is too small to record in its standard unit.")
    return unit, factor, standard


def check_date(value: date, what: str) -> None:
    if value > campus_today():
        raise HTTPException(status_code=422, detail=f"{what} cannot be dated in the future.")


def next_number(db: Session, campus_id: int, model, seq_column, prefix: str) -> tuple[int, str]:
    """KI-00001 / KR-00001 (4b-4), SC-00001 (slice 4c) per campus. The campus
    row is locked so two documents saved at once cannot take the same number.

    The lock is FOR NO KEY UPDATE, not FOR UPDATE: it still serialises
    numbering, but does not block the FOR KEY SHARE lock that every insert
    referencing the campus takes for its foreign key. With FOR UPDATE, a
    posting that already held an item lock waited here for the campus while
    the numbering transaction waited for that item: a deadlock (found by the
    slice 4c race tests: a count saved, or a draft issue recorded, while an
    issue for the same item was confirmed)."""
    db.query(Campus).filter(Campus.id == campus_id).with_for_update(key_share=True).one()
    last = db.query(func.max(seq_column)).filter(model.campus_id == campus_id).scalar() or 0
    return last + 1, f"{prefix}-{last + 1:05d}"


def lock_issue(db: Session, user: User, issue_id: int) -> KitchenIssue:
    issue = (
        db.query(KitchenIssue)
        .filter(KitchenIssue.id == issue_id, KitchenIssue.campus_id == user.campus_id)
        .with_for_update()
        .first()
    )
    if not issue:
        raise HTTPException(status_code=404, detail="Kitchen issue not found")
    return issue


def lock_return(db: Session, user: User, return_id: int) -> tuple[KitchenIssue, KitchenReturn]:
    issue_id = db.query(KitchenReturn.issue_id).filter(
        KitchenReturn.id == return_id, KitchenReturn.campus_id == user.campus_id
    ).scalar()
    if issue_id is None:
        raise HTTPException(status_code=404, detail="Unused return not found")
    issue = lock_issue(db, user, issue_id)
    record = (
        db.query(KitchenReturn)
        .filter(KitchenReturn.id == return_id, KitchenReturn.campus_id == user.campus_id)
        .with_for_update()
        .one()
    )
    return issue, record


def issue_lines(db: Session, issue_id: int) -> list[KitchenIssueItem]:
    return db.query(KitchenIssueItem).filter(KitchenIssueItem.issue_id == issue_id).order_by(KitchenIssueItem.id).all()


def return_lines(db: Session, return_id: int) -> list[KitchenReturnItem]:
    return db.query(KitchenReturnItem).filter(KitchenReturnItem.return_id == return_id).order_by(KitchenReturnItem.id).all()


def returned_by_line(db: Session, issue_id: int, statuses, exclude_return_id: int | None = None) -> dict[int, Decimal]:
    """Standard quantity already returned per issue line, by return status."""
    query = (
        db.query(KitchenReturnItem.issue_item_id, func.sum(KitchenReturnItem.standard_quantity))
        .join(KitchenReturn, KitchenReturn.id == KitchenReturnItem.return_id)
        .filter(KitchenReturn.issue_id == issue_id, KitchenReturn.status.in_(statuses))
    )
    if exclude_return_id is not None:
        query = query.filter(KitchenReturn.id != exclude_return_id)
    return {line_id: Decimal(str(total or 0)) for line_id, total in query.group_by(KitchenReturnItem.issue_item_id)}


def validate_header(db: Session, user: User, payload: IssueInput) -> tuple[MealSession, Menu]:
    check_date(payload.issue_date, "An issue")
    session = db.query(MealSession).filter(
        MealSession.id == payload.meal_session_id, MealSession.campus_id == user.campus_id
    ).first()
    menu = db.query(Menu).filter(Menu.id == payload.menu_id, Menu.campus_id == user.campus_id).first()
    if not session or not session.is_active:
        raise HTTPException(status_code=422, detail="Choose an active meal session.")
    if not menu or not menu.is_active:
        raise HTTPException(status_code=422, detail="Choose an active menu.")
    if menu.meal_session_id != session.id:
        raise HTTPException(status_code=422, detail=f"The menu {menu.name} belongs to another meal session.")
    return session, menu


def prepare_issue_lines(db: Session, user: User, lines: list[IssueLineInput]) -> list[dict]:
    item_ids = [line.item_id for line in lines]
    if len(item_ids) != len(set(item_ids)):
        raise HTTPException(status_code=422, detail="Each item can appear only once in an issue.")
    items = {i.id: i for i in db.query(Item).filter(Item.campus_id == user.campus_id, Item.id.in_(item_ids))}
    prepared = []
    for line in lines:
        item = items.get(line.item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        if not item.is_active:
            raise HTTPException(status_code=422, detail=f"{item.name} is inactive.")
        if item.item_kind == "OUTSOURCED":
            raise HTTPException(status_code=422, detail=outsourced_message([item.name], "issued from stock"))
        unit, factor, standard = converted(db, user, item, line.unit_id, line.quantity)
        prepared.append({
            "item_id": item.id, "quantity": quantity(line.quantity), "unit_id": unit.id,
            "conversion_factor": factor, "standard_quantity": standard,
            "standard_unit_id": item.standard_unit_id, "remarks": clean(line.remarks),
        })
    return prepared


def prepare_return_lines(db: Session, user: User, issue: KitchenIssue, lines: list[ReturnLineInput],
                         exclude_return_id: int | None = None) -> list[dict]:
    """Return lines against the issue's lines. A line may give back at most
    what was issued minus what other returns (confirmed or still in draft)
    already hold; confirmation checks again against confirmed returns."""
    ids = [line.issue_item_id for line in lines]
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=422, detail="Each issued item can appear only once in a return.")
    own = {line.id: line for line in issue_lines(db, issue.id)}
    held = returned_by_line(db, issue.id, ("CONFIRMED", "DRAFT"), exclude_return_id)
    items = {i.id: i for i in db.query(Item).filter(Item.id.in_([l.item_id for l in own.values()] or [0]))}
    units = dict(db.query(Unit.id, Unit.symbol).filter(Unit.id.in_([l.standard_unit_id for l in own.values()] or [0])))
    prepared = []
    for line in lines:
        issued = own.get(line.issue_item_id)
        if not issued:
            raise HTTPException(status_code=422, detail="A returned line must belong to this issue.")
        item = items[issued.item_id]
        unit, factor, standard = converted(db, user, item, line.unit_id, line.quantity)
        left = Decimal(str(issued.standard_quantity)) - held.get(issued.id, ZERO)
        if standard > left:
            raise HTTPException(
                status_code=422,
                detail=(f"Only {quantity_text(max(left, ZERO))} {units.get(issued.standard_unit_id, '')} of "
                        f"{item.name} can still be returned against {issue.issue_number}."),
            )
        prepared.append({
            "issue_item_id": issued.id, "quantity": quantity(line.quantity), "unit_id": unit.id,
            "conversion_factor": factor, "standard_quantity": standard,
            "standard_unit_id": issued.standard_unit_id, "remarks": clean(line.remarks),
        })
    return prepared


def lines_snapshot(lines) -> list[dict]:
    return [{"item_id": getattr(l, "item_id", None), "issue_item_id": getattr(l, "issue_item_id", None),
             "quantity": quantity_text(l.quantity), "unit_id": l.unit_id,
             "standard_quantity": quantity_text(l.standard_quantity)} for l in lines]


def document_movements(db: Session, campus_id: int, reference_type: str, reference_id: int) -> list[StockMovement]:
    return (
        db.query(StockMovement)
        .filter(StockMovement.campus_id == campus_id, StockMovement.reference_type == reference_type,
                StockMovement.reference_id == reference_id)
        .order_by(StockMovement.id)
        .all()
    )


def reverse_postings(db: Session, campus_id: int, reference_type: str, reference_id: int,
                     movement_type: str, reason: str, now: datetime) -> list[Posting]:
    originals = [m for m in document_movements(db, campus_id, reference_type, reference_id)
                 if m.movement_type == movement_type]
    reversed_ids = {m.reversal_of_id for m in document_movements(db, campus_id, reference_type, reference_id)
                    if m.reversal_of_id}
    return [stock_ledger.reversal_of(m, reason, now) for m in originals if m.id not in reversed_ids]


# ============================================================
# SERIALISATION
# ============================================================

def document_summary(doc, names: dict) -> dict:
    return {
        "status": doc.status,
        "remarks": doc.remarks,
        "effective_at": utc_iso(doc.effective_at) if doc.effective_at else None,
        "created_by_name": names.get(doc.created_by),
        "created_at": utc_iso(doc.created_at),
        "updated_at": utc_iso(doc.updated_at) if doc.updated_at else None,
        "confirmed_by_name": names.get(doc.confirmed_by),
        "confirmed_at": utc_iso(doc.confirmed_at) if doc.confirmed_at else None,
        "cancelled_by_name": names.get(doc.cancelled_by),
        "cancelled_at": utc_iso(doc.cancelled_at) if doc.cancelled_at else None,
        "cancellation_reason": doc.cancellation_reason,
        "reversed_by_name": names.get(doc.reversed_by),
        "reversed_at": utc_iso(doc.reversed_at) if doc.reversed_at else None,
        "reversal_reason": doc.reversal_reason,
    }


def doc_users(*docs) -> list[int]:
    return [u for d in docs for u in (d.created_by, d.confirmed_by, d.cancelled_by, d.reversed_by)]


def issue_detail(db: Session, issue: KitchenIssue) -> dict:
    campus_id = issue.campus_id
    lines = issue_lines(db, issue.id)
    returns = db.query(KitchenReturn).filter(KitchenReturn.issue_id == issue.id).order_by(KitchenReturn.id).all()
    rlines = {r.id: return_lines(db, r.id) for r in returns}
    item_ids = {l.item_id for l in lines}
    unit_ids = {l.unit_id for l in lines} | {l.standard_unit_id for l in lines} | {
        rl.unit_id for ls in rlines.values() for rl in ls}
    items = dict(db.query(Item.id, Item.name).filter(Item.id.in_(item_ids or {0})))
    units = dict(db.query(Unit.id, Unit.symbol).filter(Unit.id.in_(unit_ids or {0})))
    names = names_of(db, doc_users(issue, *returns))
    confirmed = returned_by_line(db, issue.id, ("CONFIRMED",))
    drafts = returned_by_line(db, issue.id, ("DRAFT",))
    movements = {m.source_key: m for m in db.query(StockMovement).filter(
        StockMovement.campus_id == campus_id,
        StockMovement.reference_type.in_(("KITCHEN_ISSUE", "KITCHEN_RETURN")),
        StockMovement.reference_id.in_([issue.id] + [r.id for r in returns]),
    )}
    session_name = db.query(MealSession.name).filter(MealSession.id == issue.meal_session_id).scalar()
    menu_name = db.query(Menu.name).filter(Menu.id == issue.menu_id).scalar()

    out_lines = []
    for l in lines:
        issued = Decimal(str(l.standard_quantity))
        returned = confirmed.get(l.id, ZERO)
        movement = movements.get(f"ISSUE_ITEM:{l.id}")
        reversal = movements.get(f"REVERSAL:{movement.id}") if movement else None
        net = (issued - returned) if issue.status == "CONFIRMED" else (ZERO if issue.status == "REVERSED" else None)
        returnable = (issued - returned - drafts.get(l.id, ZERO)) if issue.status == "CONFIRMED" else ZERO
        out_lines.append({
            "id": l.id, "item_id": l.item_id, "item_name": items.get(l.item_id),
            "quantity": quantity_text(l.quantity), "unit_id": l.unit_id, "unit_symbol": units.get(l.unit_id),
            "conversion_factor": format(Decimal(str(l.conversion_factor)).normalize(), "f"),
            "standard_quantity": quantity_text(issued), "standard_unit_id": l.standard_unit_id,
            "standard_unit_symbol": units.get(l.standard_unit_id), "remarks": l.remarks,
            "returned_quantity": quantity_text(returned),
            "in_draft_return_quantity": quantity_text(drafts.get(l.id, ZERO)),
            "returnable_quantity": quantity_text(max(returnable, ZERO)),
            "net_quantity": quantity_text(net) if net is not None else None,
            "movement_id": movement.id if movement else None,
            "reversal_movement_id": reversal.id if reversal else None,
        })

    line_items = {l.id: l.item_id for l in lines}
    out_returns = []
    for r in returns:
        out_returns.append({
            "id": r.id, "return_number": r.return_number, "return_date": r.return_date.isoformat(),
            **document_summary(r, names),
            "lines": [{
                "id": rl.id, "issue_item_id": rl.issue_item_id, "item_name": items.get(line_items.get(rl.issue_item_id)),
                "quantity": quantity_text(rl.quantity), "unit_id": rl.unit_id, "unit_symbol": units.get(rl.unit_id),
                "standard_quantity": quantity_text(rl.standard_quantity),
                "standard_unit_symbol": units.get(rl.standard_unit_id), "remarks": rl.remarks,
                "movement_id": getattr(movements.get(f"RETURN_ITEM:{rl.id}"), "id", None),
            } for rl in rlines[r.id]],
        })

    # Stage 5 (decision 5-7): the meal record of the same campus, date and
    # session, derived; the issue itself is unchanged.
    from app.models.meals import MealRecord
    meal = db.query(MealRecord.id, MealRecord.status).filter(
        MealRecord.campus_id == campus_id, MealRecord.meal_date == issue.issue_date,
        MealRecord.meal_session_id == issue.meal_session_id, MealRecord.status != "CANCELLED").first()

    return {
        "id": issue.id, "issue_number": issue.issue_number, "issue_date": issue.issue_date.isoformat(),
        "meal_record": {"id": meal.id, "status": meal.status} if meal else None,
        "meal_session_id": issue.meal_session_id, "meal_session_name": session_name,
        "menu_id": issue.menu_id, "menu_name": menu_name,
        **document_summary(issue, names),
        "lines": out_lines,
        "returns": out_returns,
    }


# ============================================================
# FORM OPTIONS (consumption.create or consumption.update)
# ============================================================

@router.get("/api/kitchen-issues/options")
def form_options(db: Session = Depends(get_db), user: User = Depends(entry_user)):
    """Everything the issue and return forms need, so a STAFF user with the
    approved consumption.* codes does not need menu.read or inventory.read.
    Stock balances are included only for users who hold inventory.read."""
    campus_id = user.campus_id
    items = (
        db.query(Item, Category.name)
        .outerjoin(Category, Category.id == Item.category_id)
        .filter(Item.campus_id == campus_id, Item.is_active.is_(True), not_outsourced(Item.item_kind))
        .order_by(func.lower(Item.name), Item.id)
        .all()
    )
    unit_rows = db.query(Unit).filter(Unit.campus_id == campus_id).order_by(Unit.name).all()
    stock_visible = user_has_permission(db, user, "inventory.read")
    balances = None
    if stock_visible:
        balances = {
            str(item_id): quantity_text(total)
            for item_id, total in db.query(StockMovement.item_id, stock_ledger.balance_expression())
            .filter(StockMovement.campus_id == campus_id)
            .group_by(StockMovement.item_id)
        }
    return {
        "today": campus_today().isoformat(),
        "meal_sessions": [{"id": s.id, "name": s.name} for s in db.query(MealSession).filter(
            MealSession.campus_id == campus_id, MealSession.is_active.is_(True)).order_by(MealSession.id)],
        "menus": [{"id": m.id, "name": m.name, "meal_session_id": m.meal_session_id} for m in db.query(Menu).filter(
            Menu.campus_id == campus_id, Menu.is_active.is_(True)).order_by(func.lower(Menu.name))],
        "items": [{"id": i.id, "name": i.name, "category_name": c, "standard_unit_id": i.standard_unit_id,
                   "is_active": True} for i, c in items],
        "units": [{"id": u.id, "name": u.name, "symbol": u.symbol, "dimension": u.dimension,
                   "is_active": bool(u.is_active)} for u in unit_rows],
        "conversions": [{"from_unit_id": c.from_unit_id, "to_unit_id": c.to_unit_id} for c in db.query(
            UnitConversion).filter(UnitConversion.campus_id == campus_id)],
        "stock_visible": stock_visible,
        "balances": balances,
    }


# ============================================================
# KITCHEN ISSUES
# ============================================================

@router.get("/api/kitchen-issues")
def list_issues(
    status_filter: str | None = Query(default=None, alias="status", pattern="^(DRAFT|CONFIRMED|CANCELLED|REVERSED)$"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    meal_session_id: int | None = Query(default=None, gt=0),
    menu_id: int | None = Query(default=None, gt=0),
    item_id: int | None = Query(default=None, gt=0),
    search: str | None = Query(default=None, max_length=30),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("consumption.read")),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from cannot be after date_to.")
    campus_id = user.campus_id
    query = db.query(KitchenIssue).filter(KitchenIssue.campus_id == campus_id)
    if date_from:
        query = query.filter(KitchenIssue.issue_date >= date_from)
    if date_to:
        query = query.filter(KitchenIssue.issue_date <= date_to)
    if meal_session_id:
        query = query.filter(KitchenIssue.meal_session_id == meal_session_id)
    if menu_id:
        query = query.filter(KitchenIssue.menu_id == menu_id)
    if item_id:
        query = query.filter(KitchenIssue.id.in_(
            db.query(KitchenIssueItem.issue_id).filter(KitchenIssueItem.item_id == item_id)))
    if search and search.strip():
        query = query.filter(func.upper(KitchenIssue.issue_number).contains(search.strip().upper()))
    counts = dict(query.with_entities(KitchenIssue.status, func.count(KitchenIssue.id)).group_by(KitchenIssue.status))
    if status_filter:
        query = query.filter(KitchenIssue.status == status_filter)
    total = query.count()
    issues = (query.order_by(KitchenIssue.issue_date.desc(), KitchenIssue.id.desc())
              .offset((page - 1) * page_size).limit(page_size).all())

    ids = [i.id for i in issues]
    sessions = dict(db.query(MealSession.id, MealSession.name).filter(MealSession.id.in_({i.meal_session_id for i in issues} or {0})))
    menus = dict(db.query(Menu.id, Menu.name).filter(Menu.id.in_({i.menu_id for i in issues} or {0})))
    names = names_of(db, doc_users(*issues))
    line_items: dict[int, list[str]] = {}
    for issue_id, name in (db.query(KitchenIssueItem.issue_id, Item.name).join(Item, Item.id == KitchenIssueItem.item_id)
                           .filter(KitchenIssueItem.issue_id.in_(ids or [0])).order_by(KitchenIssueItem.id)):
        line_items.setdefault(issue_id, []).append(name)
    return_counts = dict(db.query(KitchenReturn.issue_id, func.count(KitchenReturn.id)).filter(
        KitchenReturn.issue_id.in_(ids or [0]), KitchenReturn.status == "CONFIRMED").group_by(KitchenReturn.issue_id))
    return {
        "items": [{
            "id": i.id, "issue_number": i.issue_number, "issue_date": i.issue_date.isoformat(),
            "meal_session_name": sessions.get(i.meal_session_id), "menu_name": menus.get(i.menu_id),
            "item_names": line_items.get(i.id, []), "line_count": len(line_items.get(i.id, [])),
            "confirmed_return_count": return_counts.get(i.id, 0),
            **document_summary(i, names),
        } for i in issues],
        "status_counts": {s: counts.get(s, 0) for s in ("DRAFT", "CONFIRMED", "CANCELLED", "REVERSED")},
        **page_meta(total, page, page_size),
    }


@router.post("/api/kitchen-issues", status_code=201)
def create_issue(payload: IssueInput, db: Session = Depends(get_db),
                 user: User = Depends(require_permission("consumption.create"))):
    """Record a draft issue. Drafts change no stock and may be saved even
    when stock is short (client question Q9, interim)."""
    validate_header(db, user, payload)
    prepared = prepare_issue_lines(db, user, payload.lines)
    try:
        seq, number = next_number(db, user.campus_id, KitchenIssue, KitchenIssue.issue_seq, "KI")
        issue = KitchenIssue(campus_id=user.campus_id, issue_seq=seq, issue_number=number,
                             issue_date=payload.issue_date, meal_session_id=payload.meal_session_id,
                             menu_id=payload.menu_id, remarks=clean(payload.remarks), status="DRAFT",
                             created_by=user.id)
        db.add(issue)
        db.flush()
        for values in prepared:
            db.add(KitchenIssueItem(campus_id=user.campus_id, issue_id=issue.id, **values))
        db.flush()
        record_audit(db, user, "CREATE", "KITCHEN_ISSUE", issue.id, {
            "issue_number": number, "issue_date": payload.issue_date.isoformat(),
            "meal_session_id": payload.meal_session_id, "menu_id": payload.menu_id,
            "lines": lines_snapshot(issue_lines(db, issue.id)),
        })
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="The issue could not be saved. Reload and try again.")
    db.refresh(issue)
    return issue_detail(db, issue)


@router.get("/api/kitchen-issues/{issue_id}")
def get_issue(issue_id: int, db: Session = Depends(get_db),
              user: User = Depends(require_permission("consumption.read"))):
    issue = db.query(KitchenIssue).filter(KitchenIssue.id == issue_id, KitchenIssue.campus_id == user.campus_id).first()
    if not issue:
        raise HTTPException(status_code=404, detail="Kitchen issue not found")
    return issue_detail(db, issue)


@router.put("/api/kitchen-issues/{issue_id}")
def update_issue(issue_id: int, payload: IssueInput, db: Session = Depends(get_db),
                 user: User = Depends(require_permission("consumption.update"))):
    """Correct a draft: its date, session, menu, remarks and lines."""
    issue = lock_issue(db, user, issue_id)
    if issue.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Only draft issues can be changed. A confirmed issue is corrected by reversal.")
    validate_header(db, user, payload)
    prepared = prepare_issue_lines(db, user, payload.lines)
    before = lines_snapshot(issue_lines(db, issue.id))
    for line in issue_lines(db, issue.id):
        db.delete(line)  # a draft line never posted stock; its values stay in the audit row
    db.flush()
    for values in prepared:
        db.add(KitchenIssueItem(campus_id=user.campus_id, issue_id=issue.id, **values))
    issue.issue_date = payload.issue_date
    issue.meal_session_id = payload.meal_session_id
    issue.menu_id = payload.menu_id
    issue.remarks = clean(payload.remarks)
    issue.updated_at = datetime.now(timezone.utc)
    db.flush()
    record_audit(db, user, "UPDATE", "KITCHEN_ISSUE", issue.id, {
        "issue_number": issue.issue_number, "before": before, "after": lines_snapshot(issue_lines(db, issue.id)),
    })
    db.commit()
    db.refresh(issue)
    return issue_detail(db, issue)


@router.post("/api/kitchen-issues/{issue_id}/cancel")
def cancel_issue(issue_id: int, payload: Reason, db: Session = Depends(get_db),
                 user: User = Depends(require_permission("consumption.update"))):
    issue = lock_issue(db, user, issue_id)
    if issue.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Only draft issues can be cancelled.")
    now = datetime.now(timezone.utc)
    issue.status, issue.cancelled_by, issue.cancelled_at, issue.cancellation_reason = "CANCELLED", user.id, now, payload.reason
    record_audit(db, user, "CANCEL", "KITCHEN_ISSUE", issue.id, {"issue_number": issue.issue_number, "reason": payload.reason})
    db.commit()
    db.refresh(issue)
    return issue_detail(db, issue)


@router.post("/api/kitchen-issues/{issue_id}/confirm")
def confirm_issue(issue_id: int, db: Session = Depends(get_db),
                  user: User = Depends(require_permission("consumption.update"))):
    """Post the issue: one ISSUE movement per line, effective at confirmation
    (dated today) or at the end of the issue date (backdated). Refused if any
    item's balance would go below zero at any point (STK04 criterion 4, S2)."""
    issue = lock_issue(db, user, issue_id)
    if issue.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Only draft issues can be confirmed.")
    lines = issue_lines(db, issue.id)
    if not lines:
        raise HTTPException(status_code=422, detail="The issue has no items.")
    now = datetime.now(timezone.utc)
    effective = stock_ledger.document_effective_at(issue.issue_date, now)
    try:
        movements = stock_ledger.post(db, user, [Posting(
            item_id=l.item_id, movement_type="ISSUE", direction=-1, quantity=Decimal(str(l.standard_quantity)),
            unit_id=l.standard_unit_id, effective_at=effective, source_key=f"ISSUE_ITEM:{l.id}",
            reference_type="KITCHEN_ISSUE", reference_id=issue.id, remarks=l.remarks or issue.remarks,
        ) for l in lines])
        issue.status, issue.confirmed_by, issue.confirmed_at, issue.effective_at = "CONFIRMED", user.id, now, effective
        record_audit(db, user, "CONFIRM", "KITCHEN_ISSUE", issue.id, {
            "issue_number": issue.issue_number, "effective_at": utc_iso(effective),
            "movement_ids": [m.id for m in movements],
        })
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="This issue was already confirmed.")
    db.refresh(issue)
    return issue_detail(db, issue)


@router.post("/api/kitchen-issues/{issue_id}/reverse")
def reverse_issue(issue_id: int, payload: Reason, db: Session = Depends(get_db),
                  user: User = Depends(stock_managers)):
    """ADMIN and KITCHEN_MANAGER: reverse a whole confirmed issue (S4). The
    stock comes back with REVERSAL movements effective now; the issue and its
    movements stay unchanged as history. Refused while the issue has a
    confirmed, unreversed return."""
    issue = lock_issue(db, user, issue_id)
    if issue.status == "REVERSED":
        raise HTTPException(status_code=409, detail="This issue has already been reversed.")
    if issue.status != "CONFIRMED":
        raise HTTPException(status_code=409, detail="Only confirmed issues can be reversed.")
    open_returns = [n for (n,) in db.query(KitchenReturn.return_number).filter(
        KitchenReturn.issue_id == issue.id, KitchenReturn.status == "CONFIRMED").order_by(KitchenReturn.id)]
    if open_returns:
        raise HTTPException(status_code=409, detail=(
            f"Reverse its unused return{'s' if len(open_returns) > 1 else ''} first: {', '.join(open_returns)}."))
    now = datetime.now(timezone.utc)
    try:
        postings = reverse_postings(db, user.campus_id, "KITCHEN_ISSUE", issue.id, "ISSUE", payload.reason, now)
        movements = stock_ledger.post(db, user, postings)
        issue.status, issue.reversed_by, issue.reversed_at, issue.reversal_reason = "REVERSED", user.id, now, payload.reason
        record_audit(db, user, "REVERSE", "KITCHEN_ISSUE", issue.id, {
            "issue_number": issue.issue_number, "reason": payload.reason,
            "reversal_movement_ids": [m.id for m in movements], "original_effective_at": utc_iso(issue.effective_at),
        })
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="This issue has already been reversed.")
    db.refresh(issue)
    return issue_detail(db, issue)


# ============================================================
# UNUSED RETURNS
# ============================================================

@router.post("/api/kitchen-issues/{issue_id}/returns", status_code=201)
def create_return(issue_id: int, payload: ReturnInput, db: Session = Depends(get_db),
                  user: User = Depends(require_permission("consumption.create"))):
    """Record a draft return of unused ingredients against a confirmed issue."""
    issue = lock_issue(db, user, issue_id)
    if issue.status != "CONFIRMED":
        raise HTTPException(status_code=409, detail="Unused stock can be returned only against a confirmed issue.")
    check_date(payload.return_date, "A return")
    if payload.return_date < issue.issue_date:
        raise HTTPException(status_code=422, detail=f"A return cannot be dated before its issue ({issue.issue_date.isoformat()}).")
    prepared = prepare_return_lines(db, user, issue, payload.lines)
    try:
        seq, number = next_number(db, user.campus_id, KitchenReturn, KitchenReturn.return_seq, "KR")
        record = KitchenReturn(campus_id=user.campus_id, return_seq=seq, return_number=number, issue_id=issue.id,
                               return_date=payload.return_date, remarks=clean(payload.remarks), status="DRAFT",
                               created_by=user.id)
        db.add(record)
        db.flush()
        for values in prepared:
            db.add(KitchenReturnItem(campus_id=user.campus_id, return_id=record.id, **values))
        db.flush()
        record_audit(db, user, "CREATE", "KITCHEN_RETURN", record.id, {
            "return_number": number, "issue_id": issue.id, "issue_number": issue.issue_number,
            "return_date": payload.return_date.isoformat(), "lines": lines_snapshot(return_lines(db, record.id)),
        })
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="The return could not be saved. Reload and try again.")
    db.refresh(issue)
    return issue_detail(db, issue)


@router.put("/api/kitchen-returns/{return_id}")
def update_return(return_id: int, payload: ReturnInput, db: Session = Depends(get_db),
                  user: User = Depends(require_permission("consumption.update"))):
    issue, record = lock_return(db, user, return_id)
    if record.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Only draft returns can be changed.")
    check_date(payload.return_date, "A return")
    if payload.return_date < issue.issue_date:
        raise HTTPException(status_code=422, detail=f"A return cannot be dated before its issue ({issue.issue_date.isoformat()}).")
    prepared = prepare_return_lines(db, user, issue, payload.lines, exclude_return_id=record.id)
    before = lines_snapshot(return_lines(db, record.id))
    for line in return_lines(db, record.id):
        db.delete(line)
    db.flush()
    for values in prepared:
        db.add(KitchenReturnItem(campus_id=user.campus_id, return_id=record.id, **values))
    record.return_date, record.remarks, record.updated_at = payload.return_date, clean(payload.remarks), datetime.now(timezone.utc)
    db.flush()
    record_audit(db, user, "UPDATE", "KITCHEN_RETURN", record.id, {
        "return_number": record.return_number, "before": before, "after": lines_snapshot(return_lines(db, record.id)),
    })
    db.commit()
    db.refresh(issue)
    return issue_detail(db, issue)


@router.post("/api/kitchen-returns/{return_id}/cancel")
def cancel_return(return_id: int, payload: Reason, db: Session = Depends(get_db),
                  user: User = Depends(require_permission("consumption.update"))):
    issue, record = lock_return(db, user, return_id)
    if record.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Only draft returns can be cancelled.")
    now = datetime.now(timezone.utc)
    record.status, record.cancelled_by, record.cancelled_at, record.cancellation_reason = "CANCELLED", user.id, now, payload.reason
    record_audit(db, user, "CANCEL", "KITCHEN_RETURN", record.id, {"return_number": record.return_number, "reason": payload.reason})
    db.commit()
    db.refresh(issue)
    return issue_detail(db, issue)


@router.post("/api/kitchen-returns/{return_id}/confirm")
def confirm_return(return_id: int, db: Session = Depends(get_db),
                   user: User = Depends(require_permission("consumption.update"))):
    """Post the return: one UNUSED_RETURN movement per line. Effective by the
    same rule as issues, never before the issue it comes from (4b-2)."""
    issue, record = lock_return(db, user, return_id)
    if record.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Only draft returns can be confirmed.")
    if issue.status != "CONFIRMED":
        raise HTTPException(status_code=409, detail=f"{issue.issue_number} is no longer confirmed, so nothing can be returned against it.")
    lines = return_lines(db, record.id)
    confirmed = returned_by_line(db, issue.id, ("CONFIRMED",))
    own = {l.id: l for l in issue_lines(db, issue.id)}
    for line in lines:
        issued = own[line.issue_item_id]
        left = Decimal(str(issued.standard_quantity)) - confirmed.get(issued.id, ZERO)
        if Decimal(str(line.standard_quantity)) > left:
            item_name = db.query(Item.name).filter(Item.id == issued.item_id).scalar()
            unit = db.query(Unit.symbol).filter(Unit.id == issued.standard_unit_id).scalar() or ""
            raise HTTPException(status_code=409, detail=(
                f"Only {quantity_text(max(left, ZERO))} {unit} of {item_name} can still be returned "
                f"against {issue.issue_number}; other returns were confirmed in the meantime."))
    now = datetime.now(timezone.utc)
    effective = max(stock_ledger.document_effective_at(record.return_date, now), stock_ledger.as_utc(issue.effective_at))
    try:
        movements = stock_ledger.post(db, user, [Posting(
            item_id=own[l.issue_item_id].item_id, movement_type="UNUSED_RETURN", direction=1,
            quantity=Decimal(str(l.standard_quantity)), unit_id=l.standard_unit_id, effective_at=effective,
            source_key=f"RETURN_ITEM:{l.id}", reference_type="KITCHEN_RETURN", reference_id=record.id,
            remarks=l.remarks or record.remarks,
        ) for l in lines])
        record.status, record.confirmed_by, record.confirmed_at, record.effective_at = "CONFIRMED", user.id, now, effective
        record_audit(db, user, "CONFIRM", "KITCHEN_RETURN", record.id, {
            "return_number": record.return_number, "issue_number": issue.issue_number,
            "effective_at": utc_iso(effective), "movement_ids": [m.id for m in movements],
        })
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="This return was already confirmed.")
    db.refresh(issue)
    return issue_detail(db, issue)


@router.post("/api/kitchen-returns/{return_id}/reverse")
def reverse_return(return_id: int, payload: Reason, db: Session = Depends(get_db),
                   user: User = Depends(stock_managers)):
    """ADMIN and KITCHEN_MANAGER: reverse a whole confirmed return. This takes
    the returned stock back out, so it is refused if a balance would go below
    zero (S2)."""
    issue, record = lock_return(db, user, return_id)
    if record.status == "REVERSED":
        raise HTTPException(status_code=409, detail="This return has already been reversed.")
    if record.status != "CONFIRMED":
        raise HTTPException(status_code=409, detail="Only confirmed returns can be reversed.")
    now = datetime.now(timezone.utc)
    try:
        postings = reverse_postings(db, user.campus_id, "KITCHEN_RETURN", record.id, "UNUSED_RETURN", payload.reason, now)
        movements = stock_ledger.post(db, user, postings)
        record.status, record.reversed_by, record.reversed_at, record.reversal_reason = "REVERSED", user.id, now, payload.reason
        record_audit(db, user, "REVERSE", "KITCHEN_RETURN", record.id, {
            "return_number": record.return_number, "reason": payload.reason,
            "reversal_movement_ids": [m.id for m in movements], "original_effective_at": utc_iso(record.effective_at),
        })
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="This return has already been reversed.")
    db.refresh(issue)
    return issue_detail(db, issue)
