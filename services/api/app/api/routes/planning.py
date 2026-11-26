"""Meal planning (Stage 6: PLAN01–PLAN08, AT05, AT06), per
docs/STAGE-6-PLANNING-PLAN.md (decisions 6-1 to 6-9 and safeguards S6-1 to
S6-6, approved 24 November 2026; section 12 choices approved the same day).

Decisions applied:
- 6-2 versioned portion standards in their own table; menu main items are
  never changed. Copying them creates DRAFTS only; each is approved
  separately (S6-4).
- 6-3/6-4/6-5 planning is ADMIN and KITCHEN_MANAGER work: every endpoint
  needs that role and the module code; approving is a role check; approving
  one's own draft is allowed (INTERIM until client question Q3).
- 6-6 a DRAFT plan is calculated live from the standards in effect on its
  date; approval writes a snapshot and freezes it (S6-2); a correction is
  cancel-and-replace (INTERIM, proposal §4.2 historical corrections).
- 6-7 one expected total per plan; one live plan per campus, date and meal
  session; plans dated today or later.
- 6-8 only ADMIN and KITCHEN_MANAGER classify items (PUT /api/items/{id}/kind);
  a standard is approved only for a RAW or PREPARED item; OUTSOURCED items are
  not planned until the outsourced-food stage.
- 6-9 plan vs actual for in-house meals; received (outsourced) quantities
  come with Stage 8.
Safeguards:
- S6-1 plans and meal records link only on the exact campus, date and
  meal_session_id. A record or plan in another session with the same name
  (ignoring letter case and extra spaces) is reported, never linked.
- S6-3 a standard's or override's unit is the item's standard unit or has an
  explicit unit_conversions record to it; nothing else is converted.
- S6-5 planning reads stock balances and meal records only. It never writes a
  stock movement, kitchen issue or return, count, adjustment, purchase order,
  bill, receipt, supplier payment or supplier return.
Section 12 choices: corrections by a newer approved version (same effective
date: the higher version wins); effective dates today or later; item kind
can change but not be cleared; headcount ≥ 1; past-dated drafts can only be
cancelled; copies keep a plain reference to the menu main item.
Every query is limited to the user's campus.
"""

from datetime import date, datetime, timezone
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_roles, user_has_permission
from app.api.routes.kitchen import FACTOR_STEP, Reason, clean, names_of, next_number, page_meta
from app.api.routes.master_data import record_audit
from app.api.routes.stock import balances_subquery
from app.core.clock import campus_today, utc_iso
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.master_data import Item, MealSession, Menu, MenuMainItem, Unit, UnitConversion
from app.models.meals import LEFTOVER_CLASSES, MealDish, MealLeftover, MealRecord
from app.models.planning import PLANNABLE_KINDS, MealPlan, MealPlanLine, PortionStandard, PortionStandardBasis
from app.models.user import User, UserRole
from app.services.stock_ledger import quantity, quantity_text

standards_router = APIRouter(prefix="/api/portion-standards", tags=["Portion Standards"])
plans_router = APIRouter(prefix="/api/meal-plans", tags=["Meal Plans"])
items_router = APIRouter(prefix="/api/items", tags=["Items"])

STANDARD_ENTITY = "PORTION_STANDARD"
PLAN_ENTITY = "MEAL_PLAN"
ITEM_ENTITY = "ITEM"
ZERO = Decimal("0")
ONE = Decimal("1")
FINE_STEP = Decimal("0.000001")
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 200
AVAILABILITY_NOTE = "Current availability (today's stock balance), not a forecast."
C5_NOTE = "Meal sessions are used as stored until client question C5 is answered."

managers = require_roles(UserRole.ADMIN, UserRole.KITCHEN_MANAGER)


def planner(code: str):
    """ADMIN or KITCHEN_MANAGER holding the code (6-3: STAFF never plan,
    whatever grants exist)."""

    def check(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        if user.role not in (UserRole.ADMIN, UserRole.KITCHEN_MANAGER):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="Meal planning is handled by Admins and Kitchen Managers only.")
        if not user_has_permission(db, user, code):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="This permission has not been assigned to you.")
        return user

    return check


# ============================================================
# INPUT
# ============================================================

PerPerson = Field(gt=0, max_digits=15, decimal_places=3)


class StandardFields(BaseModel):
    quantity_per_person: Decimal = PerPerson
    unit_id: int = Field(gt=0)
    effective_from: date
    notes: str | None = Field(default=None, max_length=500)


class StandardCreate(StandardFields):
    menu_id: int = Field(gt=0)
    item_id: int = Field(gt=0)


class CopyInput(BaseModel):
    menu_id: int = Field(gt=0)
    effective_from: date


class SuggestionInput(BaseModel):
    menu_id: int = Field(gt=0)
    item_id: int = Field(gt=0)
    meal_record_ids: list[int] = Field(min_length=1, max_length=200)
    unit_id: int | None = Field(default=None, gt=0)

    @field_validator("meal_record_ids")
    @classmethod
    def distinct(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value):
            raise ValueError("Select each meal record once.")
        return value


class SuggestionSave(SuggestionInput):
    unit_id: int = Field(gt=0)
    effective_from: date
    notes: str | None = Field(default=None, max_length=500)


class LineInput(BaseModel):
    item_id: int = Field(gt=0)
    override_quantity_per_person: Decimal | None = Field(default=None, gt=0, max_digits=15, decimal_places=3)
    override_unit_id: int | None = Field(default=None, gt=0)
    override_reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def override_complete(self):
        reason = (self.override_reason or "").strip()
        self.override_reason = reason or None
        given = [self.override_quantity_per_person is not None, self.override_unit_id is not None, bool(reason)]
        if any(given) and not all(given):
            raise ValueError("A one-day override needs a quantity per person, a unit and a reason.")
        if reason and len(reason) < 3:
            raise ValueError("Give a reason for the override (at least 3 characters).")
        return self


class PlanFields(BaseModel):
    expected_headcount: int = Field(ge=1, le=100000)
    notes: str | None = Field(default=None, max_length=500)
    lines: list[LineInput] = Field(min_length=1, max_length=100)

    @field_validator("lines")
    @classmethod
    def distinct_items(cls, value: list[LineInput]) -> list[LineInput]:
        if len({line.item_id for line in value}) != len(value):
            raise ValueError("Choose each main item once.")
        return value


class PlanCreate(PlanFields):
    plan_date: date
    meal_session_id: int = Field(gt=0)
    menu_id: int = Field(gt=0)


class KindInput(BaseModel):
    item_kind: Literal["RAW", "PREPARED", "OUTSOURCED"]


# ============================================================
# UNITS AND CONVERSIONS (S6-3)
# ============================================================

class Units:
    """The campus's units and explicit conversion records, read once. A
    factor exists only for the same unit or an explicit record (either
    direction, as get_unit_conversion_factor reads it)."""

    def __init__(self, db: Session, campus_id: int):
        self.by_id = {u.id: u for u in db.query(Unit).filter(Unit.campus_id == campus_id)}
        self.direct = {(c.from_unit_id, c.to_unit_id): Decimal(str(c.factor))
                       for c in db.query(UnitConversion).filter(UnitConversion.campus_id == campus_id)}

    def factor(self, from_id: int, to_id: int) -> Decimal | None:
        if from_id == to_id:
            return ONE
        if (from_id, to_id) in self.direct:
            return self.direct[(from_id, to_id)].quantize(FACTOR_STEP)
        if (to_id, from_id) in self.direct:
            return (ONE / self.direct[(to_id, from_id)]).quantize(FACTOR_STEP)
        return None

    def symbol(self, unit_id) -> str | None:
        unit = self.by_id.get(unit_id)
        return unit.symbol if unit else None

    def check(self, item: Item, unit_id: int) -> tuple[Unit, Decimal]:
        """The unit of a standard or override for this item, with its factor
        to the item's standard unit; refused without an explicit record."""
        unit, base = self.by_id.get(unit_id), self.by_id.get(item.standard_unit_id)
        if unit is None:
            raise HTTPException(status_code=422, detail="Choose a unit of this campus.")
        if not unit.is_active:
            raise HTTPException(status_code=422, detail=f"{unit.name} is inactive.")
        if base is None or unit.dimension != base.dimension:
            raise HTTPException(status_code=422, detail=(
                f"{item.name} is measured in {base.symbol if base else '?'} ({base.dimension if base else '?'}); "
                f"{unit.symbol} is {unit.dimension}. Conversions between dimensions, such as weight to pieces, "
                "are never assumed."))
        factor = self.factor(unit.id, base.id)
        if factor is None:
            raise HTTPException(status_code=422, detail=(
                f"There is no approved conversion between {unit.symbol} and {base.symbol} (the standard unit of "
                f"{item.name}). Add an explicit unit conversion first."))
        return unit, factor

    def choices(self, item: Item) -> list[dict]:
        base = self.by_id.get(item.standard_unit_id)
        out = []
        for unit in sorted(self.by_id.values(), key=lambda u: u.id):
            if not unit.is_active or base is None or unit.dimension != base.dimension:
                continue
            factor = self.factor(unit.id, base.id)
            if factor is not None:
                out.append({"id": unit.id, "symbol": unit.symbol, "dimension": unit.dimension,
                            "factor_to_base": str(factor)})
        return out

    def display(self, amount: Decimal | None, unit_id) -> list[dict]:
        """Also in kg (from g) or L (from ml), only through an explicit
        record (PLAN04 gram-to-kilogram display)."""
        unit = self.by_id.get(unit_id)
        if amount is None or unit is None:
            return []
        larger = {"g": "kg", "ml": "l"}.get(unit.symbol.strip().lower())
        if not larger:
            return []
        for other in self.by_id.values():
            if other.symbol.strip().lower() == larger and other.dimension == unit.dimension:
                factor = self.factor(unit.id, other.id)
                if factor is not None:
                    return [{"quantity": quantity_text(amount * factor), "unit_symbol": other.symbol,
                             "factor": str(factor)}]
        return []


def fine_text(value: Decimal | None) -> str | None:
    """A per-person quantity with up to six decimals (at least three)."""
    if value is None:
        return None
    text = format(Decimal(value).quantize(FINE_STEP, rounding=ROUND_HALF_UP), "f")
    whole, _, decimals = text.partition(".")
    decimals = decimals.rstrip("0").ljust(3, "0")
    return f"{whole}.{decimals}"


# ============================================================
# MEAL-SESSION MATCHING (S6-1)
# ============================================================

def normal_name(name: str | None) -> str:
    return " ".join((name or "").split()).casefold()


def similar_sessions(db: Session, campus_id: int, session_id: int) -> list[MealSession]:
    """Other sessions of the campus whose name is the same ignoring letter
    case and extra spaces (plan section 12, choice 3)."""
    sessions = db.query(MealSession).filter(MealSession.campus_id == campus_id).all()
    mine = next((s for s in sessions if s.id == session_id), None)
    if mine is None:
        return []
    return [s for s in sessions if s.id != session_id and normal_name(s.name) == normal_name(mine.name)]


def day_text(value: date) -> str:
    return value.strftime("%d %b %Y")


def live_record(db: Session, campus_id: int, on_date: date, session_id: int) -> MealRecord | None:
    return db.query(MealRecord).filter(
        MealRecord.campus_id == campus_id, MealRecord.meal_date == on_date,
        MealRecord.meal_session_id == session_id, MealRecord.status != "CANCELLED").first()


def live_plan(db: Session, campus_id: int, on_date: date, session_id: int) -> MealPlan | None:
    return db.query(MealPlan).filter(
        MealPlan.campus_id == campus_id, MealPlan.plan_date == on_date,
        MealPlan.meal_session_id == session_id, MealPlan.status != "CANCELLED").first()


def record_warnings(db: Session, campus_id: int, on_date: date, session_id: int) -> list[str]:
    """Meal records on the date in a same-named other session: reported, not linked."""
    out = []
    for other in similar_sessions(db, campus_id, session_id):
        record = live_record(db, campus_id, on_date, other.id)
        if record:
            out.append(f"Meal record #{record.id} for “{other.name}” on {day_text(on_date)} is in a different meal "
                       f"session with the same name, so it is not linked to this plan. {C5_NOTE}")
    return out


def plan_warnings(db: Session, campus_id: int, on_date: date, session_id: int) -> list[str]:
    """Plans on the date in a same-named other session: reported, not linked."""
    out = []
    for other in similar_sessions(db, campus_id, session_id):
        plan = live_plan(db, campus_id, on_date, other.id)
        if plan:
            out.append(f"Meal plan {plan.plan_number} for “{other.name}” on {day_text(on_date)} is in a different "
                       f"meal session with the same name, so it is not linked to this meal record. {C5_NOTE}")
    return out


def session_notes(db: Session, campus_id: int, session_id: int) -> list[str]:
    others = similar_sessions(db, campus_id, session_id)
    if not others:
        return []
    names = ", ".join(f"“{s.name}” (#{s.id}{'' if s.is_active else ', inactive'})" for s in others)
    return [f"This campus has another meal session with the same name: {names}. Plans and meal records link only "
            f"within the same meal session. {C5_NOTE}"]


# ============================================================
# STANDARDS (PLAN02, PLAN06)
# ============================================================

def standard_state(standard: PortionStandard, approved: list[PortionStandard], today: date) -> str:
    """DRAFT / CANCELLED, or for an approved version: IN_EFFECT (today),
    SCHEDULED (a later date, not superseded) or SUPERSEDED."""
    if standard.status != "APPROVED":
        return standard.status
    current = best_version(approved, today)
    if current is not None and current.id == standard.id:
        return "IN_EFFECT"
    if standard.effective_from > today:
        same_day = [s for s in approved if s.effective_from == standard.effective_from]
        if max(same_day, key=lambda s: s.version_no).id == standard.id:
            return "SCHEDULED"
    return "SUPERSEDED"


def best_version(approved: list[PortionStandard], on_date: date) -> PortionStandard | None:
    """The approved version in effect on a date: latest effective date on or
    before it, then the highest version (section 12, choice 1)."""
    candidates = [s for s in approved if s.status == "APPROVED" and s.effective_from <= on_date]
    return max(candidates, key=lambda s: (s.effective_from, s.version_no)) if candidates else None


def approved_for_menu(db: Session, campus_id: int, menu_id: int, item_ids=None) -> dict[int, list[PortionStandard]]:
    query = db.query(PortionStandard).filter(
        PortionStandard.campus_id == campus_id, PortionStandard.menu_id == menu_id,
        PortionStandard.status == "APPROVED")
    if item_ids is not None:
        query = query.filter(PortionStandard.item_id.in_(list(item_ids) or [0]))
    found: dict[int, list[PortionStandard]] = {}
    for row in query:
        found.setdefault(row.item_id, []).append(row)
    return found


def in_effect(db: Session, campus_id: int, menu_id: int, on_date: date, item_ids=None) -> dict[int, PortionStandard]:
    return {item_id: best for item_id, rows in approved_for_menu(db, campus_id, menu_id, item_ids).items()
            if (best := best_version(rows, on_date)) is not None}


def campus_menu(db: Session, user: User, menu_id: int, active: bool = True) -> Menu:
    menu = db.query(Menu).filter(Menu.id == menu_id, Menu.campus_id == user.campus_id).first()
    if not menu:
        raise HTTPException(status_code=404, detail="Menu not found")
    if active and not menu.is_active:
        raise HTTPException(status_code=422, detail=f"The menu {menu.name} is inactive.")
    return menu


def campus_item(db: Session, user: User, item_id: int) -> Item:
    item = db.query(Item).filter(Item.id == item_id, Item.campus_id == user.campus_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


def plannable_item(item: Item, for_approval: bool) -> None:
    if not item.is_active:
        raise HTTPException(status_code=422, detail=f"{item.name} is inactive.")
    if item.item_kind == "OUTSOURCED":
        raise HTTPException(status_code=422, detail=(
            f"{item.name} is an outsourced item; outsourced items are not planned until the outsourced-food stage."))
    if for_approval and item.item_kind not in PLANNABLE_KINDS:
        raise HTTPException(status_code=422, detail=(
            f"Classify {item.name} as raw or prepared before approving its standard (Admin or Kitchen Manager)."))


def check_effective_date(value: date) -> None:
    if value < campus_today():
        raise HTTPException(status_code=422, detail=(
            f"The effective date must be today ({campus_today().isoformat()}) or later; standards are not back-dated."))


def lock_standard(db: Session, user: User, standard_id: int) -> PortionStandard:
    standard = (db.query(PortionStandard)
                .filter(PortionStandard.id == standard_id, PortionStandard.campus_id == user.campus_id)
                .with_for_update(key_share=True).first())
    if not standard:
        raise HTTPException(status_code=404, detail="Portion standard not found")
    return standard


def require_draft_standard(standard: PortionStandard) -> None:
    if standard.status == "APPROVED":
        raise HTTPException(status_code=409, detail=(
            "This standard is approved and cannot be changed. Approve a newer version instead."))
    if standard.status == "CANCELLED":
        raise HTTPException(status_code=409, detail="This draft was cancelled and cannot be changed.")


def standard_values(standard: PortionStandard) -> dict:
    return {"menu_id": standard.menu_id, "item_id": standard.item_id,
            "quantity_per_person": quantity_text(standard.quantity_per_person), "unit_id": standard.unit_id,
            "effective_from": standard.effective_from.isoformat(), "notes": standard.notes,
            "source": standard.source, "copied_from_menu_main_item_id": standard.copied_from_menu_main_item_id}


def standard_problems(db: Session, user: User, standard: PortionStandard, units: Units) -> list[str]:
    """Why a draft cannot be approved now (empty when it can)."""
    if standard.status != "DRAFT":
        return []
    problems = []
    for check in (
        lambda: campus_menu(db, user, standard.menu_id),
        lambda: plannable_item(campus_item(db, user, standard.item_id), True),
        lambda: units.check(campus_item(db, user, standard.item_id), standard.unit_id),
        lambda: check_effective_date(standard.effective_from),
    ):
        try:
            check()
        except HTTPException as exc:
            problems.append(str(exc.detail))
    return problems


def standard_row(standard: PortionStandard, state: str, menus: dict, items: dict, sessions: dict,
                 units: Units, names: dict) -> dict:
    menu, item = menus.get(standard.menu_id), items.get(standard.item_id)
    return {
        "id": standard.id,
        "menu_id": standard.menu_id, "menu_name": menu.name if menu else None,
        "meal_session_name": sessions.get(menu.meal_session_id) if menu else None,
        "item_id": standard.item_id, "item_name": item.name if item else None,
        "item_kind": standard.item_kind if standard.status == "APPROVED" else (item.item_kind if item else None),
        "quantity_per_person": quantity_text(standard.quantity_per_person),
        "unit_id": standard.unit_id, "unit_symbol": units.symbol(standard.unit_id),
        "base_unit_symbol": units.symbol(item.standard_unit_id) if item else None,
        "effective_from": standard.effective_from.isoformat(),
        "version_no": standard.version_no, "status": standard.status, "state": state, "source": standard.source,
        "copied_from_menu_main_item_id": standard.copied_from_menu_main_item_id,
        "notes": standard.notes,
        "created_by_name": names.get(standard.created_by), "created_at": utc_iso(standard.created_at),
        "approved_by_name": names.get(standard.approved_by),
        "approved_at": utc_iso(standard.approved_at) if standard.approved_at else None,
        "cancelled_by_name": names.get(standard.cancelled_by),
        "cancelled_at": utc_iso(standard.cancelled_at) if standard.cancelled_at else None,
        "cancellation_reason": standard.cancellation_reason,
    }


def lookups(db: Session, standards: list[PortionStandard]):
    menus = {m.id: m for m in db.query(Menu).filter(Menu.id.in_({s.menu_id for s in standards} or {0}))}
    items = {i.id: i for i in db.query(Item).filter(Item.id.in_({s.item_id for s in standards} or {0}))}
    sessions = dict(db.query(MealSession.id, MealSession.name).filter(
        MealSession.id.in_({m.meal_session_id for m in menus.values()} or {0})))
    names = names_of(db, [u for s in standards for u in (s.created_by, s.approved_by, s.cancelled_by)])
    return menus, items, sessions, names


def history_of(db: Session, user: User, entity: str, entity_id: int) -> list[dict]:
    rows = (db.query(AuditLog).filter(AuditLog.campus_id == user.campus_id, AuditLog.entity_type == entity,
                                      AuditLog.entity_id == entity_id).order_by(AuditLog.id).all())
    names = names_of(db, [r.user_id for r in rows])
    return [{"id": r.id, "action": r.action, "user_name": names.get(r.user_id),
             "created_at": utc_iso(r.created_at), "details": r.details} for r in rows]


def standard_detail(db: Session, user: User, standard: PortionStandard) -> dict:
    today = campus_today()
    units = Units(db, user.campus_id)
    versions = (db.query(PortionStandard)
                .filter(PortionStandard.campus_id == user.campus_id, PortionStandard.menu_id == standard.menu_id,
                        PortionStandard.item_id == standard.item_id)
                .all())
    approved = [v for v in versions if v.status == "APPROVED"]
    menus, items, sessions, names = lookups(db, versions)
    order = sorted(versions, key=lambda v: (v.status != "DRAFT", -(v.version_no or 0), -v.id))
    basis = (db.query(PortionStandardBasis, MealRecord)
             .join(MealRecord, MealRecord.id == PortionStandardBasis.meal_record_id)
             .filter(PortionStandardBasis.standard_id == standard.id).order_by(MealRecord.meal_date).all())
    basis_sessions = dict(db.query(MealSession.id, MealSession.name).filter(
        MealSession.id.in_({r.meal_session_id for _b, r in basis} or {0})))
    total_used = sum((Decimal(str(b.quantity_used)) for b, _r in basis), ZERO)
    total_people = sum(b.people_served for b, _r in basis)
    return {
        **standard_row(standard, standard_state(standard, approved, today), menus, items, sessions, units, names),
        "today": today.isoformat(),
        "approval_problems": standard_problems(db, user, standard, units),
        "versions": [standard_row(v, standard_state(v, approved, today), menus, items, sessions, units, names)
                     for v in order],
        "basis": [{
            "meal_record_id": r.id, "meal_date": r.meal_date.isoformat(),
            "meal_session_name": basis_sessions.get(r.meal_session_id),
            "quantity_used": quantity_text(b.quantity_used), "unit_symbol": units.symbol(b.unit_id),
            "people_served": b.people_served,
        } for b, r in basis],
        "basis_totals": None if not basis else {
            "quantity_used": quantity_text(total_used), "people_served": total_people,
            "per_person": fine_text(total_used / total_people),
            "unit_symbol": units.symbol(basis[0][0].unit_id),
        },
        "history": history_of(db, user, STANDARD_ENTITY, standard.id),
    }


# ---------- suggestions from closed meal records (PLAN03) ----------

def suggestion(db: Session, user: User, menu: Menu, item: Item, record_ids: list[int], units: Units,
               unit_id: int | None) -> dict:
    """Total net usage ÷ total actual people served over the selected
    records. Only CLOSED records with actual counts, people served and a net
    usage of the item recorded in its standard unit are used; the others are
    listed with the reason."""
    records = {r.id: r for r in db.query(MealRecord).filter(
        MealRecord.id.in_(record_ids), MealRecord.campus_id == user.campus_id)}
    missing = [i for i in record_ids if i not in records]
    if missing:
        raise HTTPException(status_code=422, detail=f"Meal record(s) not found: {', '.join(f'#{i}' for i in missing)}.")
    base_symbol = units.symbol(item.standard_unit_id)
    sessions = dict(db.query(MealSession.id, MealSession.name).filter(
        MealSession.id.in_({r.meal_session_id for r in records.values()} or {0})))
    rows, used_total, people_total = [], ZERO, 0
    for record in sorted(records.values(), key=lambda r: (r.meal_date, r.id)):
        people = None if record.actual_students is None else (
            record.actual_students + record.actual_staff + record.actual_guests)
        usage = (record.closed_usage or {}).get(str(item.id)) if record.status == "CLOSED" else None
        used = Decimal(usage["net_quantity"]) if usage else None
        reason = None
        if record.status != "CLOSED":
            reason = "Not closed" if record.status == "OPEN" else "Cancelled"
        elif not people:
            reason = "No people served were recorded"
        elif usage is None:
            reason = f"No net usage of {item.name} at closing"
        elif usage.get("unit_symbol") != base_symbol:
            reason = f"Usage recorded in {usage.get('unit_symbol')}, not {base_symbol}"
        elif used <= 0:
            reason = f"No net usage of {item.name} at closing"
        if reason is None:
            used_total += used
            people_total += people
        rows.append({"meal_record_id": record.id, "meal_date": record.meal_date.isoformat(),
                     "meal_session_name": sessions.get(record.meal_session_id), "status": record.status,
                     "people_served": people, "quantity_used": quantity_text(used) if used is not None else None,
                     "included": reason is None, "excluded_reason": reason})
    per_person = used_total / people_total if people_total else None
    result = {
        "menu_id": menu.id, "item_id": item.id, "item_name": item.name, "base_unit_symbol": base_symbol,
        "records": rows, "included_count": sum(1 for r in rows if r["included"]),
        "total_quantity_used": quantity_text(used_total), "total_people_served": people_total,
        "per_person_in_base_unit": fine_text(per_person),
        "unit_id": None, "unit_symbol": None, "per_person_in_unit": None, "suggested_quantity_per_person": None,
    }
    if per_person is not None and unit_id is not None:
        unit, factor = units.check(item, unit_id)  # factor: unit → base
        in_unit = per_person / factor
        result.update({"unit_id": unit.id, "unit_symbol": unit.symbol, "per_person_in_unit": fine_text(in_unit),
                       "suggested_quantity_per_person": quantity_text(in_unit)})
    return result


# ============================================================
# PLANS (PLAN01, PLAN04–PLAN07)
# ============================================================

def lock_plan(db: Session, user: User, plan_id: int) -> MealPlan:
    plan = (db.query(MealPlan).filter(MealPlan.id == plan_id, MealPlan.campus_id == user.campus_id)
            .with_for_update(key_share=True).first())
    if not plan:
        raise HTTPException(status_code=404, detail="Meal plan not found")
    return plan


def require_editable_plan(plan: MealPlan) -> None:
    if plan.status == "APPROVED":
        raise HTTPException(status_code=409, detail=(
            "This plan is approved and cannot be changed. Cancel it with a reason and create a new plan."))
    if plan.status == "CANCELLED":
        raise HTTPException(status_code=409, detail="This plan was cancelled and cannot be changed.")
    if plan.plan_date < campus_today():
        raise HTTPException(status_code=409, detail="The plan date has passed; a past-dated draft can only be cancelled.")


def lines_of(db: Session, plan_id: int) -> list[MealPlanLine]:
    return db.query(MealPlanLine).filter(MealPlanLine.plan_id == plan_id).order_by(MealPlanLine.id).all()


def stock_balances(db: Session, campus_id: int, item_ids) -> dict[int, Decimal]:
    sub = balances_subquery(db, campus_id)
    return {row.item_id: Decimal(str(row.balance or 0))
            for row in db.query(sub.c.item_id, sub.c.balance).filter(sub.c.item_id.in_(list(item_ids) or [0]))}


def compute(headcount: int, per_person: Decimal, unit: Unit, factor: Decimal | None, base: Unit) -> dict:
    """PLAN04: required = headcount × quantity per person; count units round
    up to whole pieces. The quantity in the item's standard unit uses the
    explicit factor only."""
    raw = Decimal(headcount) * Decimal(str(per_person))
    required = raw.to_integral_value(rounding=ROUND_CEILING) if unit.dimension == "count" else quantity(raw)
    rounded = required != raw
    base_quantity = None
    if factor is not None:
        in_base = required * factor
        base_quantity = (in_base.to_integral_value(rounding=ROUND_CEILING) if base.dimension == "count"
                         else quantity(in_base))
    return {"required": quantity(required), "rounded_up": rounded, "base": base_quantity}


def plan_lines(db: Session, user: User, plan: MealPlan, units: Units, live: bool | None = None) -> tuple[list[dict], list[str]]:
    """Each line, live (a draft) or from its snapshot; plus the reasons a
    draft cannot be approved now."""
    lines = lines_of(db, plan.id)
    if live is None:  # a draft, or a draft that was cancelled before approval
        live = plan.status == "DRAFT" or plan.approved_at is None
    items = {i.id: i for i in db.query(Item).filter(Item.id.in_({l.item_id for l in lines} or {0}))}
    standards = in_effect(db, plan.campus_id, plan.menu_id, plan.plan_date, items) if live else {
        s.id: s for s in db.query(PortionStandard).filter(
            PortionStandard.id.in_({l.standard_id for l in lines if l.standard_id} or {0}))}
    balances = stock_balances(db, plan.campus_id, items)
    out, problems = [], []
    if live and plan.plan_date < campus_today():
        problems.append("The plan date has passed; a past-dated draft can only be cancelled.")
    if live and not lines:
        problems.append("Choose at least one main item.")
    for line in lines:
        item = items[line.item_id]
        base = units.by_id.get(item.standard_unit_id)
        line_problems = []
        if live:
            standard = standards.get(item.id)
            if not item.is_active:
                line_problems.append(f"{item.name} is inactive.")
            if item.item_kind not in PLANNABLE_KINDS:
                line_problems.append(f"{item.name} is outsourced and is not planned until the outsourced-food stage."
                                     if item.item_kind == "OUTSOURCED" else
                                     f"Classify {item.name} as raw or prepared (Admin or Kitchen Manager).")
            if standard is None:
                line_problems.append(f"{item.name} has no approved standard for this menu on {day_text(plan.plan_date)}.")
            per_person, unit_id = ((line.override_quantity_per_person, line.override_unit_id)
                                   if line.override_quantity_per_person is not None else
                                   ((standard.quantity_per_person, standard.unit_id) if standard else (None, None)))
            figures, factor = None, None
            if per_person is not None:
                unit = units.by_id.get(unit_id)
                factor = units.factor(unit_id, item.standard_unit_id) if unit and base and unit.dimension == base.dimension else None
                if factor is None:
                    line_problems.append(f"{item.name}: no approved conversion from {units.symbol(unit_id)} to "
                                         f"{units.symbol(item.standard_unit_id)}.")
                figures = compute(plan.expected_headcount, per_person, unit, factor, base)
                if figures["base"] is not None and figures["base"] <= 0:
                    line_problems.append(f"{item.name}: the quantity is too small to express in {base.symbol}.")
            kind = item.item_kind
            standard_out = None if standard is None else {
                "id": standard.id, "version_no": standard.version_no,
                "quantity_per_person": quantity_text(standard.quantity_per_person),
                "unit_id": standard.unit_id, "unit_symbol": units.symbol(standard.unit_id),
                "effective_from": standard.effective_from.isoformat()}
            required = figures["required"] if figures else None
            rounded = figures["rounded_up"] if figures else False
            required_base = figures["base"] if figures else None
        else:
            standard = standards.get(line.standard_id)
            per_person, unit_id, factor = line.quantity_per_person, line.unit_id, line.conversion_factor
            kind = line.item_kind
            standard_out = None if line.standard_id is None else {
                "id": line.standard_id, "version_no": standard.version_no if standard else None,
                "quantity_per_person": quantity_text(line.standard_quantity_per_person),
                "unit_id": line.standard_unit_id, "unit_symbol": units.symbol(line.standard_unit_id),
                "effective_from": standard.effective_from.isoformat() if standard else None}
            required, rounded = line.required_quantity, bool(line.rounded_up)
            required_base = line.required_base_quantity
        available = balances.get(item.id, ZERO)
        gap = max(ZERO, Decimal(str(required_base)) - available) if required_base is not None else None
        problems.extend(line_problems)
        out.append({
            "id": line.id, "item_id": item.id, "item_name": item.name, "item_kind": kind,
            "base_unit_id": item.standard_unit_id, "base_unit_symbol": units.symbol(item.standard_unit_id),
            "standard": standard_out,
            "override": None if line.override_quantity_per_person is None else {
                "quantity_per_person": quantity_text(line.override_quantity_per_person),
                "unit_id": line.override_unit_id, "unit_symbol": units.symbol(line.override_unit_id),
                "reason": line.override_reason},
            "quantity_per_person": quantity_text(per_person) if per_person is not None else None,
            "unit_id": unit_id, "unit_symbol": units.symbol(unit_id),
            "per_person_in_base_unit": fine_text(Decimal(str(per_person)) * Decimal(str(factor)))
            if per_person is not None and factor is not None else None,
            "required_quantity": quantity_text(required) if required is not None else None,
            "required_display": units.display(Decimal(str(required)), unit_id) if required is not None else [],
            "rounded_up": rounded,
            "conversion_factor": str(factor) if factor is not None else None,
            "required_base_quantity": quantity_text(required_base) if required_base is not None else None,
            "available_stock": quantity_text(available),
            "procurement_gap": quantity_text(gap) if gap is not None else None,
            "unit_choices": units.choices(item) if live else [],
            "problems": line_problems,
        })
    out.sort(key=lambda r: r["item_name"].lower())
    return out, problems


def plan_ref(plan: MealPlan | None) -> dict | None:
    return None if plan is None else {"id": plan.id, "plan_number": plan.plan_number, "status": plan.status,
                                      "expected_headcount": plan.expected_headcount}


def record_ref(record: MealRecord | None) -> dict | None:
    if record is None:
        return None
    totals = [record.expected_students + record.expected_staff + record.expected_guests,
              None if record.actual_students is None else
              record.actual_students + record.actual_staff + record.actual_guests]
    return {"id": record.id, "status": record.status, "meal_date": record.meal_date.isoformat(),
            "expected_total": totals[0], "actual_total": totals[1]}


def plan_detail(db: Session, user: User, plan: MealPlan) -> dict:
    units = Units(db, user.campus_id)
    lines, problems = plan_lines(db, user, plan, units)
    session = db.get(MealSession, plan.meal_session_id)
    menu = db.get(Menu, plan.menu_id)
    names = names_of(db, [plan.created_by, plan.approved_by, plan.cancelled_by])
    record = live_record(db, plan.campus_id, plan.plan_date, plan.meal_session_id)
    today = campus_today()
    return {
        "id": plan.id, "plan_number": plan.plan_number, "plan_date": plan.plan_date.isoformat(),
        "meal_session_id": plan.meal_session_id, "meal_session_name": session.name if session else None,
        "menu_id": plan.menu_id, "menu_name": menu.name if menu else None,
        "expected_headcount": plan.expected_headcount, "status": plan.status, "notes": plan.notes,
        "calculation": "SNAPSHOT" if plan.approved_at else "LIVE",
        "editable": plan.status == "DRAFT" and plan.plan_date >= today,
        "created_by_name": names.get(plan.created_by), "created_at": utc_iso(plan.created_at),
        "updated_at": utc_iso(plan.updated_at) if plan.updated_at else None,
        "approved_by_name": names.get(plan.approved_by),
        "approved_at": utc_iso(plan.approved_at) if plan.approved_at else None,
        "cancelled_by_name": names.get(plan.cancelled_by),
        "cancelled_at": utc_iso(plan.cancelled_at) if plan.cancelled_at else None,
        "cancellation_reason": plan.cancellation_reason,
        "today": today.isoformat(),
        "availability_note": AVAILABILITY_NOTE,
        "lines": lines,
        "approval_problems": problems if plan.status == "DRAFT" else [],
        "meal_record": record_ref(record),
        "session_warnings": record_warnings(db, plan.campus_id, plan.plan_date, plan.meal_session_id)
        + session_notes(db, plan.campus_id, plan.meal_session_id),
        "history": history_of(db, user, PLAN_ENTITY, plan.id),
    }


def validated_lines(db: Session, user: User, menu_id: int, plan_date: date, lines: list[LineInput],
                    units: Units) -> list[tuple[Item, LineInput]]:
    items = {i.id: i for i in db.query(Item).filter(
        Item.id.in_([l.item_id for l in lines]), Item.campus_id == user.campus_id)}
    missing = [l.item_id for l in lines if l.item_id not in items]
    if missing:
        raise HTTPException(status_code=404, detail="Item not found")
    standards = in_effect(db, user.campus_id, menu_id, plan_date, items)
    out = []
    for line in lines:
        item = items[line.item_id]
        plannable_item(item, True)
        if line.item_id not in standards:
            raise HTTPException(status_code=422, detail=(
                f"{item.name} has no approved standard for this menu on {day_text(plan_date)}."))
        if line.override_unit_id is not None:
            units.check(item, line.override_unit_id)
        out.append((item, line))
    return out


def lines_snapshot(lines: list[MealPlanLine]) -> list[dict]:
    return [{"item_id": l.item_id,
             "override_quantity_per_person": quantity_text(l.override_quantity_per_person)
             if l.override_quantity_per_person is not None else None,
             "override_unit_id": l.override_unit_id, "override_reason": l.override_reason} for l in lines]


# ============================================================
# PLAN VS ACTUAL (PLAN08, MEAL02 criterion 4)
# ============================================================

def comparison(db: Session, user: User, plan: MealPlan, record: MealRecord | None, units: Units) -> dict:
    from app.api.routes.meals import linked_issues  # read-only helper (Stage 5)

    lines, _problems = plan_lines(db, user, plan, units)
    out = {
        "plan": {**plan_ref(plan), "plan_date": plan.plan_date.isoformat(),
                 "calculation": "SNAPSHOT" if plan.approved_at else "LIVE"},
        "meal_record": record_ref(record),
        "record_note": None, "headcounts": None, "items": [], "dishes": [],
        "notes": [
            "Carried retained food is shown separately and not counted as prepared (interim, client question Q11).",
            "Received (outsourced) food is listed as its own kind with the received quantity (Stage 8a).",
        ],
    }
    if record is None:
        out["record_note"] = "No meal record for this date and meal session yet."
        return out
    if record.status == "OPEN":
        out["record_note"] = "The meal record is not closed; figures may change."
    reference = record_ref(record)
    out["headcounts"] = {"plan_expected": plan.expected_headcount, "record_expected": reference["expected_total"],
                         "record_actual": reference["actual_total"]}
    if record.status == "CLOSED" and record.closed_usage is not None:
        usage = {int(k): v for k, v in record.closed_usage.items()}
        usage_source = "CLOSING"
    else:
        usage = {r["item_id"]: r for r in linked_issues(db, record)[1]}
        usage_source = "LIVE"
    out["usage_source"] = usage_source
    actual_people = reference["actual_total"]
    planned = {l["item_id"]: l for l in lines}
    item_names = dict(db.query(Item.id, Item.name).filter(Item.id.in_(set(usage) | set(planned) or {0})))
    rows = []
    for item_id in set(planned) | set(usage):
        line, used = planned.get(item_id), usage.get(item_id)
        planned_q = Decimal(line["required_base_quantity"]) if line and line["required_base_quantity"] else None
        actual_q = Decimal(used["net_quantity"]) if used else None
        rows.append({
            "item_id": item_id, "item_name": item_names.get(item_id),
            "unit_symbol": (line or {}).get("base_unit_symbol") or (used or {}).get("unit_symbol"),
            "planned": line is not None,
            "planned_quantity": quantity_text(planned_q) if planned_q is not None else None,
            "actual_net_quantity": quantity_text(actual_q) if actual_q is not None else None,
            "difference": quantity_text((actual_q or ZERO) - planned_q) if planned_q is not None else None,
            "planned_per_person": line["per_person_in_base_unit"] if line else None,
            "actual_per_person": fine_text(actual_q / actual_people) if actual_q is not None and actual_people else None,
        })
    out["items"] = sorted(rows, key=lambda r: (not r["planned"], (r["item_name"] or "").lower()))
    dishes = db.query(MealDish).filter(MealDish.meal_record_id == record.id).order_by(MealDish.id).all()
    leftovers: dict[int, dict[str, str]] = {}
    for row in db.query(MealLeftover).filter(MealLeftover.dish_id.in_([d.id for d in dishes] or [0])):
        leftovers.setdefault(row.dish_id, {})[row.classification] = quantity_text(row.quantity)
    out["dishes"] = [{
        "dish_name": d.dish_name, "unit_symbol": units.symbol(d.unit_id),
        "kind": "CARRIED" if d.source_leftover_id else ("RECEIVED" if d.source_delivery_line_id else "PREPARED"),
        "prepared_quantity": quantity_text(d.output_quantity), "carried_quantity": quantity_text(d.carried_quantity),
        "received_quantity": quantity_text(d.received_quantity),
        "distributed_quantity": quantity_text(d.distributed_quantity) if d.distributed_quantity is not None else None,
        "remaining_quantity": quantity_text(d.remaining_quantity) if d.remaining_quantity is not None else None,
        "leftovers": {c: leftovers.get(d.id, {}).get(c) for c in LEFTOVER_CLASSES},
    } for d in dishes]
    return out


def planning_for_record(db: Session, user: User, record: MealRecord) -> dict | None:
    """The meal record page's planning panel (MEAL02 criterion 4): only for
    ADMIN and KITCHEN_MANAGER holding meal_plan.read; None for anyone else."""
    if user.role not in (UserRole.ADMIN, UserRole.KITCHEN_MANAGER) or not user_has_permission(db, user, "meal_plan.read"):
        return None
    plan = live_plan(db, record.campus_id, record.meal_date, record.meal_session_id)
    units = Units(db, record.campus_id)
    return {
        "plan": plan_ref(plan),
        "session_warnings": plan_warnings(db, record.campus_id, record.meal_date, record.meal_session_id),
        "comparison": comparison(db, user, plan, record, units) if plan else None,
    }


# ============================================================
# ENDPOINTS — ITEM KIND (6-8)
# ============================================================

def refuse_kind_change(db: Session, item: Item, kind: str) -> None:
    """Stage 8a (P8-5): outsourced food never enters raw-ingredient stock,
    so an item with stock movements (or on a draft goods receipt, kitchen
    issue or count) is not classified OUTSOURCED; and an item on outsourced
    orders keeps that kind. The item row is locked by the caller, as every
    stock posting locks it, so the check cannot race a posting."""
    from app.models.outsourced import OutsourcedOrderLine
    from app.models.purchases import GoodsReceipt, GoodsReceiptItem, PurchaseItem, StockMovement
    from app.models.stock import KitchenIssue, KitchenIssueItem, StockCountItem, StockOpening

    if kind == "OUTSOURCED":
        if db.query(StockMovement.id).filter(StockMovement.item_id == item.id).first():
            raise HTTPException(status_code=409, detail=(
                f"{item.name} has raw-ingredient stock movements, so it cannot be classified as outsourced food: "
                "outsourced food never enters stock and the ledger must stay explainable. Create a separate item "
                "for the outsourced dish."))
        drafts = []
        if (db.query(GoodsReceiptItem.id).join(GoodsReceipt, GoodsReceipt.id == GoodsReceiptItem.receipt_id)
                .join(PurchaseItem, PurchaseItem.id == GoodsReceiptItem.purchase_item_id)
                .filter(PurchaseItem.item_id == item.id, GoodsReceipt.status == "DRAFT").first()):
            drafts.append("a draft goods receipt")
        if (db.query(KitchenIssueItem.id).join(KitchenIssue, KitchenIssue.id == KitchenIssueItem.issue_id)
                .filter(KitchenIssueItem.item_id == item.id, KitchenIssue.status == "DRAFT").first()):
            drafts.append("a draft kitchen issue")
        if db.query(StockOpening.id).filter(StockOpening.item_id == item.id).first():
            drafts.append("an opening stock entry")
        if db.query(StockCountItem.id).filter(StockCountItem.item_id == item.id).first():
            drafts.append("a stock count")
        if drafts:
            raise HTTPException(status_code=409, detail=(
                f"{item.name} is on {' and '.join(drafts)}, so it cannot be classified as outsourced food. "
                "Cancel those first, or create a separate item for the outsourced dish."))
    elif item.item_kind == "OUTSOURCED":
        if db.query(OutsourcedOrderLine.id).filter(OutsourcedOrderLine.item_id == item.id).first():
            raise HTTPException(status_code=409, detail=(
                f"{item.name} is on outsourced orders, so it stays classified as outsourced food."))


@items_router.put("/{item_id}/kind")
def set_item_kind(item_id: int, payload: KindInput, db: Session = Depends(get_db), user: User = Depends(managers)):
    """ADMIN or KITCHEN_MANAGER only, by role: no inventory.* grant
    classifies an item. The kind can change but not be cleared; approved
    standards and plan lines keep the kind they were approved with."""
    item = (db.query(Item).filter(Item.id == item_id, Item.campus_id == user.campus_id)
            .with_for_update(key_share=True).first())
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if not item.is_active:
        raise HTTPException(status_code=409, detail="Inactive records cannot be edited.")
    if item.item_kind != payload.item_kind:
        refuse_kind_change(db, item, payload.item_kind)
        before = item.item_kind
        item.item_kind = payload.item_kind
        record_audit(db, user, "SET_KIND", ITEM_ENTITY, item.id, {"before": {"item_kind": before},
                                                                 "after": {"item_kind": payload.item_kind}})
        db.commit()
        db.refresh(item)
    return {"id": item.id, "name": item.name, "item_kind": item.item_kind}


# ============================================================
# ENDPOINTS — PORTION STANDARDS
# ============================================================

@standards_router.get("/options")
def standard_options(db: Session = Depends(get_db), user: User = Depends(planner("portion_standard.read"))):
    units = Units(db, user.campus_id)
    sessions = dict(db.query(MealSession.id, MealSession.name).filter(MealSession.campus_id == user.campus_id))
    items = db.query(Item).filter(Item.campus_id == user.campus_id, Item.is_active.is_(True)).order_by(func.lower(Item.name)).all()
    return {
        "today": campus_today().isoformat(),
        "menus": [{"id": m.id, "name": m.name, "meal_session_id": m.meal_session_id,
                   "meal_session_name": sessions.get(m.meal_session_id)}
                  for m in db.query(Menu).filter(Menu.campus_id == user.campus_id, Menu.is_active.is_(True))
                  .order_by(func.lower(Menu.name))],
        "items": [{"id": i.id, "name": i.name, "item_kind": i.item_kind, "base_unit_id": i.standard_unit_id,
                   "base_unit_symbol": units.symbol(i.standard_unit_id), "unit_choices": units.choices(i)}
                  for i in items],
    }


@standards_router.get("")
def list_standards(
    menu_id: int | None = Query(default=None, gt=0),
    item_id: int | None = Query(default=None, gt=0),
    status_filter: str | None = Query(default=None, alias="status", pattern="^(DRAFT|APPROVED|CANCELLED)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
    user: User = Depends(planner("portion_standard.read")),
):
    query = db.query(PortionStandard).filter(PortionStandard.campus_id == user.campus_id)
    if menu_id:
        query = query.filter(PortionStandard.menu_id == menu_id)
    if item_id:
        query = query.filter(PortionStandard.item_id == item_id)
    counts = dict(query.with_entities(PortionStandard.status, func.count(PortionStandard.id))
                  .group_by(PortionStandard.status))
    if status_filter:
        query = query.filter(PortionStandard.status == status_filter)
    total = query.count()
    rows = (query.order_by(PortionStandard.menu_id, PortionStandard.item_id,
                           PortionStandard.status != "DRAFT", PortionStandard.version_no.desc(), PortionStandard.id.desc())
            .offset((page - 1) * page_size).limit(page_size).all())
    approved: dict[tuple, list] = {}
    for s in db.query(PortionStandard).filter(
            PortionStandard.campus_id == user.campus_id, PortionStandard.status == "APPROVED",
            PortionStandard.menu_id.in_({r.menu_id for r in rows} or {0})):
        approved.setdefault((s.menu_id, s.item_id), []).append(s)
    today = campus_today()
    units = Units(db, user.campus_id)
    menus, items, sessions, names = lookups(db, rows)
    return {
        "today": today.isoformat(),
        "items": [standard_row(s, standard_state(s, approved.get((s.menu_id, s.item_id), []), today),
                               menus, items, sessions, units, names) for s in rows],
        "status_counts": {k: counts.get(k, 0) for k in ("DRAFT", "APPROVED", "CANCELLED")},
        **page_meta(total, page, page_size),
    }


@standards_router.post("", status_code=201)
def create_standard(payload: StandardCreate, db: Session = Depends(get_db),
                    user: User = Depends(planner("portion_standard.create"))):
    menu = campus_menu(db, user, payload.menu_id)
    item = campus_item(db, user, payload.item_id)
    plannable_item(item, False)
    units = Units(db, user.campus_id)
    unit, _factor = units.check(item, payload.unit_id)
    check_effective_date(payload.effective_from)
    standard = PortionStandard(campus_id=user.campus_id, menu_id=menu.id, item_id=item.id,
                               quantity_per_person=quantity(payload.quantity_per_person), unit_id=unit.id,
                               effective_from=payload.effective_from, status="DRAFT", source="MANUAL",
                               notes=clean(payload.notes), created_by=user.id)
    db.add(standard)
    db.flush()
    record_audit(db, user, "CREATE", STANDARD_ENTITY, standard.id, standard_values(standard))
    db.commit()
    db.refresh(standard)
    return standard_detail(db, user, standard)


@standards_router.post("/copy-from-menu")
def copy_from_menu(payload: CopyInput, db: Session = Depends(get_db),
                   user: User = Depends(planner("portion_standard.create"))):
    """Draft standards from a menu's main items (6-2, S6-4). Nothing is
    approved; menu main items are not changed. Items that are inactive,
    outsourced, without an approved conversion, or already copied into a
    pending draft are skipped with the reason."""
    menu = campus_menu(db, user, payload.menu_id)
    check_effective_date(payload.effective_from)
    db.query(Menu).filter(Menu.id == menu.id).with_for_update(key_share=True).one()  # one copy at a time per menu
    units = Units(db, user.campus_id)
    created, skipped = [], []
    sources = db.query(MenuMainItem).filter(MenuMainItem.campus_id == user.campus_id,
                                            MenuMainItem.menu_id == menu.id).order_by(MenuMainItem.id).all()
    items = {i.id: i for i in db.query(Item).filter(Item.id.in_({s.item_id for s in sources} or {0}))}
    for source in sources:
        item = items[source.item_id]
        pending = db.query(PortionStandard.id).filter(
            PortionStandard.campus_id == user.campus_id, PortionStandard.status == "DRAFT",
            PortionStandard.copied_from_menu_main_item_id == source.id).scalar()
        reason = None
        if pending:
            reason = f"A draft copy already exists (#{pending})."
        else:
            try:
                plannable_item(item, False)
                units.check(item, source.unit_id)
            except HTTPException as exc:
                reason = str(exc.detail)
        if reason:
            skipped.append({"menu_main_item_id": source.id, "item_name": item.name, "reason": reason})
            continue
        standard = PortionStandard(campus_id=user.campus_id, menu_id=menu.id, item_id=item.id,
                                   quantity_per_person=quantity(source.quantity_per_person), unit_id=source.unit_id,
                                   effective_from=payload.effective_from, status="DRAFT", source="COPIED",
                                   copied_from_menu_main_item_id=source.id,
                                   notes=f"Copied from menu main item #{source.id}", created_by=user.id)
        db.add(standard)
        db.flush()
        record_audit(db, user, "CREATE", STANDARD_ENTITY, standard.id, standard_values(standard))
        created.append({"id": standard.id, "item_name": item.name,
                        "quantity_per_person": quantity_text(standard.quantity_per_person),
                        "unit_symbol": units.symbol(standard.unit_id)})
    db.commit()
    return {"menu_id": menu.id, "menu_name": menu.name, "created": created, "skipped": skipped,
            "note": "Copied standards are drafts. Each one needs approval by an Admin or Kitchen Manager."}


@standards_router.get("/suggestion/records")
def suggestion_records(
    item_id: int = Query(gt=0),
    meal_session_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
    user: User = Depends(planner("portion_standard.create")),
):
    """Closed meal records that used the item (net usage at closing), most
    recent first, for the user to select (PLAN03)."""
    item = campus_item(db, user, item_id)
    query = db.query(MealRecord).filter(MealRecord.campus_id == user.campus_id, MealRecord.status == "CLOSED")
    if meal_session_id:
        query = query.filter(MealRecord.meal_session_id == meal_session_id)
    records = [r for r in query.order_by(MealRecord.meal_date.desc(), MealRecord.id.desc()).limit(500)
               if str(item.id) in (r.closed_usage or {})][:200]
    sessions = dict(db.query(MealSession.id, MealSession.name).filter(
        MealSession.id.in_({r.meal_session_id for r in records} or {0})))
    return {
        "item_id": item.id, "item_name": item.name,
        "session_notes": session_notes(db, user.campus_id, meal_session_id) if meal_session_id else [],
        "items": [{
            "id": r.id, "meal_date": r.meal_date.isoformat(), "meal_session_name": sessions.get(r.meal_session_id),
            "actual_total": None if r.actual_students is None else r.actual_students + r.actual_staff + r.actual_guests,
            "net_quantity": r.closed_usage[str(item.id)]["net_quantity"],
            "unit_symbol": r.closed_usage[str(item.id)].get("unit_symbol"),
        } for r in records],
    }


@standards_router.post("/suggestion/preview")
def suggestion_preview(payload: SuggestionInput, db: Session = Depends(get_db),
                       user: User = Depends(planner("portion_standard.create"))):
    menu = campus_menu(db, user, payload.menu_id)
    item = campus_item(db, user, payload.item_id)
    return suggestion(db, user, menu, item, payload.meal_record_ids, Units(db, user.campus_id), payload.unit_id)


@standards_router.post("/suggestion", status_code=201)
def save_suggestion(payload: SuggestionSave, db: Session = Depends(get_db),
                    user: User = Depends(planner("portion_standard.create"))):
    """Saves the suggestion as a DRAFT standard with its basis records; it is
    applied only after a responsible user approves it (PLAN03)."""
    menu = campus_menu(db, user, payload.menu_id)
    item = campus_item(db, user, payload.item_id)
    plannable_item(item, False)
    check_effective_date(payload.effective_from)
    units = Units(db, user.campus_id)
    result = suggestion(db, user, menu, item, payload.meal_record_ids, units, payload.unit_id)
    if not result["included_count"]:
        raise HTTPException(status_code=422, detail="None of the selected meal records can be used for a suggestion.")
    value = Decimal(result["suggested_quantity_per_person"])
    if value <= 0:
        raise HTTPException(status_code=422, detail=f"The suggestion rounds to 0 {result['unit_symbol']}; choose a smaller unit.")
    standard = PortionStandard(campus_id=user.campus_id, menu_id=menu.id, item_id=item.id, quantity_per_person=value,
                               unit_id=payload.unit_id, effective_from=payload.effective_from, status="DRAFT",
                               source="SUGGESTED", notes=clean(payload.notes), created_by=user.id)
    db.add(standard)
    db.flush()
    for row in result["records"]:
        if row["included"]:
            db.add(PortionStandardBasis(campus_id=user.campus_id, standard_id=standard.id,
                                        meal_record_id=row["meal_record_id"],
                                        quantity_used=Decimal(row["quantity_used"]), unit_id=item.standard_unit_id,
                                        people_served=row["people_served"]))
    record_audit(db, user, "CREATE", STANDARD_ENTITY, standard.id, {
        **standard_values(standard),
        "suggestion": {k: result[k] for k in ("total_quantity_used", "total_people_served",
                                              "per_person_in_base_unit", "per_person_in_unit")},
        "basis_meal_record_ids": [r["meal_record_id"] for r in result["records"] if r["included"]],
        "excluded": [{"meal_record_id": r["meal_record_id"], "reason": r["excluded_reason"]}
                     for r in result["records"] if not r["included"]],
    })
    db.commit()
    db.refresh(standard)
    return standard_detail(db, user, standard)


@standards_router.get("/{standard_id}")
def get_standard(standard_id: int, db: Session = Depends(get_db),
                 user: User = Depends(planner("portion_standard.read"))):
    standard = db.query(PortionStandard).filter(PortionStandard.id == standard_id,
                                                PortionStandard.campus_id == user.campus_id).first()
    if not standard:
        raise HTTPException(status_code=404, detail="Portion standard not found")
    return standard_detail(db, user, standard)


@standards_router.put("/{standard_id}")
def update_standard(standard_id: int, payload: StandardFields, db: Session = Depends(get_db),
                    user: User = Depends(planner("portion_standard.update"))):
    standard = lock_standard(db, user, standard_id)
    require_draft_standard(standard)
    item = campus_item(db, user, standard.item_id)
    plannable_item(item, False)
    unit, _factor = Units(db, user.campus_id).check(item, payload.unit_id)
    check_effective_date(payload.effective_from)
    before = standard_values(standard)
    standard.quantity_per_person = quantity(payload.quantity_per_person)
    standard.unit_id = unit.id
    standard.effective_from = payload.effective_from
    standard.notes = clean(payload.notes)
    standard.updated_at = datetime.now(timezone.utc)
    record_audit(db, user, "UPDATE", STANDARD_ENTITY, standard.id, {"before": before, "after": standard_values(standard)})
    db.commit()
    db.refresh(standard)
    return standard_detail(db, user, standard)


@standards_router.post("/{standard_id}/cancel")
def cancel_standard(standard_id: int, payload: Reason, db: Session = Depends(get_db),
                    user: User = Depends(planner("portion_standard.update"))):
    standard = lock_standard(db, user, standard_id)
    require_draft_standard(standard)
    now = datetime.now(timezone.utc)
    standard.status, standard.cancelled_by, standard.cancelled_at = "CANCELLED", user.id, now
    standard.cancellation_reason, standard.updated_at = payload.reason, now
    record_audit(db, user, "CANCEL", STANDARD_ENTITY, standard.id, {"reason": payload.reason})
    db.commit()
    db.refresh(standard)
    return standard_detail(db, user, standard)


@standards_router.post("/{standard_id}/approve")
def approve_standard(standard_id: int, db: Session = Depends(get_db), user: User = Depends(managers)):
    """ADMIN or KITCHEN_MANAGER (6-5). The draft gets the next version number
    for its menu and item and becomes final (S6-2)."""
    if not user_has_permission(db, user, "portion_standard.update"):
        raise HTTPException(status_code=403, detail="This permission has not been assigned to you.")
    standard = lock_standard(db, user, standard_id)
    require_draft_standard(standard)
    menu = campus_menu(db, user, standard.menu_id)
    item = campus_item(db, user, standard.item_id)
    plannable_item(item, True)
    Units(db, user.campus_id).check(item, standard.unit_id)
    check_effective_date(standard.effective_from)
    db.query(Menu).filter(Menu.id == menu.id).with_for_update(key_share=True).one()  # serialises version numbers
    latest = db.query(func.max(PortionStandard.version_no)).filter(
        PortionStandard.campus_id == user.campus_id, PortionStandard.menu_id == menu.id,
        PortionStandard.item_id == item.id).scalar() or 0
    now = datetime.now(timezone.utc)
    standard.status, standard.version_no = "APPROVED", latest + 1
    standard.approved_by, standard.approved_at, standard.item_kind = user.id, now, item.item_kind
    standard.updated_at = now
    record_audit(db, user, "APPROVE", STANDARD_ENTITY, standard.id, {
        **standard_values(standard), "version_no": standard.version_no, "item_kind": standard.item_kind})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Another version of this standard was approved at the same time. Try again.")
    db.refresh(standard)
    return standard_detail(db, user, standard)


# ============================================================
# ENDPOINTS — MEAL PLANS
# ============================================================

@plans_router.get("/options")
def plan_options(db: Session = Depends(get_db), user: User = Depends(planner("meal_plan.create"))):
    sessions = db.query(MealSession).filter(MealSession.campus_id == user.campus_id).order_by(MealSession.id).all()
    return {
        "today": campus_today().isoformat(),
        "meal_sessions": [{"id": s.id, "name": s.name, "notes": session_notes(db, user.campus_id, s.id)}
                          for s in sessions if s.is_active],
        "menus": [{"id": m.id, "name": m.name, "meal_session_id": m.meal_session_id}
                  for m in db.query(Menu).filter(Menu.campus_id == user.campus_id, Menu.is_active.is_(True))
                  .order_by(func.lower(Menu.name))],
        "availability_note": AVAILABILITY_NOTE,
    }


@plans_router.get("/prefill")
def plan_prefill(
    plan_date: date,
    meal_session_id: int = Query(gt=0),
    menu_id: int = Query(gt=0),
    db: Session = Depends(get_db),
    user: User = Depends(planner("meal_plan.create")),
):
    """What the new-plan form needs for a date, session and menu: the meal
    record of the exact session (expected total), same-name warnings (S6-1),
    an existing plan for the slot, and the main items with a standard in
    effect, with the figures for live recalculation."""
    session = db.query(MealSession).filter(MealSession.id == meal_session_id,
                                           MealSession.campus_id == user.campus_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Meal session not found")
    menu = campus_menu(db, user, menu_id, active=False)
    if menu.meal_session_id != session.id:
        raise HTTPException(status_code=422, detail=f"The menu {menu.name} belongs to another meal session.")
    units = Units(db, user.campus_id)
    standards = in_effect(db, user.campus_id, menu.id, plan_date)
    drafts = {s.item_id for s in db.query(PortionStandard).filter(
        PortionStandard.campus_id == user.campus_id, PortionStandard.menu_id == menu.id,
        PortionStandard.status == "DRAFT")}
    items = {i.id: i for i in db.query(Item).filter(Item.id.in_(set(standards) | drafts or {0}))}
    balances = stock_balances(db, user.campus_id, items)
    record = live_record(db, user.campus_id, plan_date, session.id)
    available, unavailable = [], []
    for item_id, item in sorted(items.items(), key=lambda kv: kv[1].name.lower()):
        standard = standards.get(item_id)
        reason = None
        if standard is None:
            reason = "Only a draft standard exists (needs approval)."
        elif not item.is_active:
            reason = "Inactive item."
        elif item.item_kind not in PLANNABLE_KINDS:
            reason = ("Outsourced items are not planned until the outsourced-food stage."
                      if item.item_kind == "OUTSOURCED" else "Not classified as raw or prepared.")
        if reason:
            unavailable.append({"item_id": item_id, "item_name": item.name, "reason": reason})
            continue
        unit = units.by_id[standard.unit_id]
        base = units.by_id[item.standard_unit_id]
        larger = units.display(ONE, standard.unit_id)
        available.append({
            "item_id": item_id, "item_name": item.name, "item_kind": item.item_kind,
            "base_unit_id": base.id, "base_unit_symbol": base.symbol, "base_unit_dimension": base.dimension,
            "standard": {"id": standard.id, "version_no": standard.version_no,
                         "quantity_per_person": quantity_text(standard.quantity_per_person),
                         "unit_id": unit.id, "unit_symbol": unit.symbol, "unit_dimension": unit.dimension,
                         "effective_from": standard.effective_from.isoformat(),
                         "factor_to_base": str(units.factor(unit.id, base.id))},
            "display": {"unit_symbol": larger[0]["unit_symbol"], "factor": larger[0]["factor"]} if larger else None,
            "unit_choices": units.choices(item),
            "available_stock": quantity_text(balances.get(item_id, ZERO)),
        })
    return {
        "plan_date": plan_date.isoformat(), "today": campus_today().isoformat(),
        "meal_record": record_ref(record),
        "existing_plan": plan_ref(live_plan(db, user.campus_id, plan_date, session.id)),
        "session_warnings": record_warnings(db, user.campus_id, plan_date, session.id)
        + session_notes(db, user.campus_id, session.id),
        "items": available, "unavailable_items": unavailable,
        "availability_note": AVAILABILITY_NOTE,
    }


@plans_router.get("")
def list_plans(
    status_filter: str | None = Query(default=None, alias="status", pattern="^(DRAFT|APPROVED|CANCELLED)$"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    meal_session_id: int | None = Query(default=None, gt=0),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
    user: User = Depends(planner("meal_plan.read")),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from cannot be after date_to.")
    query = db.query(MealPlan).filter(MealPlan.campus_id == user.campus_id)
    if date_from:
        query = query.filter(MealPlan.plan_date >= date_from)
    if date_to:
        query = query.filter(MealPlan.plan_date <= date_to)
    if meal_session_id:
        query = query.filter(MealPlan.meal_session_id == meal_session_id)
    counts = dict(query.with_entities(MealPlan.status, func.count(MealPlan.id)).group_by(MealPlan.status))
    if status_filter:
        query = query.filter(MealPlan.status == status_filter)
    total = query.count()
    plans = (query.order_by(MealPlan.plan_date.desc(), MealPlan.meal_session_id, MealPlan.id.desc())
             .offset((page - 1) * page_size).limit(page_size).all())
    sessions = dict(db.query(MealSession.id, MealSession.name).filter(
        MealSession.id.in_({p.meal_session_id for p in plans} or {0})))
    menus = dict(db.query(Menu.id, Menu.name).filter(Menu.id.in_({p.menu_id for p in plans} or {0})))
    line_counts = dict(db.query(MealPlanLine.plan_id, func.count(MealPlanLine.id)).filter(
        MealPlanLine.plan_id.in_([p.id for p in plans] or [0])).group_by(MealPlanLine.plan_id))
    names = names_of(db, [p.created_by for p in plans] + [p.approved_by for p in plans])
    records = {(r.meal_date, r.meal_session_id): r.id for r in db.query(MealRecord).filter(
        MealRecord.campus_id == user.campus_id, MealRecord.status != "CANCELLED",
        MealRecord.meal_date.in_({p.plan_date for p in plans} or {date.min}))}
    return {
        "items": [{
            "id": p.id, "plan_number": p.plan_number, "plan_date": p.plan_date.isoformat(),
            "meal_session_name": sessions.get(p.meal_session_id), "menu_name": menus.get(p.menu_id),
            "expected_headcount": p.expected_headcount, "status": p.status, "line_count": line_counts.get(p.id, 0),
            "created_by_name": names.get(p.created_by), "approved_by_name": names.get(p.approved_by),
            "approved_at": utc_iso(p.approved_at) if p.approved_at else None,
            "meal_record_id": records.get((p.plan_date, p.meal_session_id)),
        } for p in plans],
        "status_counts": {k: counts.get(k, 0) for k in ("DRAFT", "APPROVED", "CANCELLED")},
        **page_meta(total, page, page_size),
    }


@plans_router.post("", status_code=201)
def create_plan(payload: PlanCreate, db: Session = Depends(get_db), user: User = Depends(planner("meal_plan.create"))):
    if payload.plan_date < campus_today():
        raise HTTPException(status_code=422, detail="Plans are made for today or a later date.")
    session = db.query(MealSession).filter(MealSession.id == payload.meal_session_id,
                                           MealSession.campus_id == user.campus_id).first()
    if not session or not session.is_active:
        raise HTTPException(status_code=422, detail="Choose an active meal session.")
    menu = campus_menu(db, user, payload.menu_id)
    if menu.meal_session_id != session.id:
        raise HTTPException(status_code=422, detail=f"The menu {menu.name} belongs to another meal session.")
    units = Units(db, user.campus_id)
    checked = validated_lines(db, user, menu.id, payload.plan_date, payload.lines, units)
    existing = live_plan(db, user.campus_id, payload.plan_date, session.id)
    if existing:
        raise HTTPException(status_code=409, detail=(
            f"A meal plan for {session.name} on {day_text(payload.plan_date)} already exists ({existing.plan_number})."))
    try:
        seq, number = next_number(db, user.campus_id, MealPlan, MealPlan.plan_seq, "MP")
        plan = MealPlan(campus_id=user.campus_id, plan_seq=seq, plan_number=number, plan_date=payload.plan_date,
                        meal_session_id=session.id, menu_id=menu.id, expected_headcount=payload.expected_headcount,
                        status="DRAFT", notes=clean(payload.notes), created_by=user.id)
        db.add(plan)
        db.flush()
        rows = [MealPlanLine(campus_id=user.campus_id, plan_id=plan.id, item_id=item.id,
                             override_quantity_per_person=quantity(line.override_quantity_per_person)
                             if line.override_quantity_per_person is not None else None,
                             override_unit_id=line.override_unit_id, override_reason=line.override_reason)
                for item, line in checked]
        db.add_all(rows)
        db.flush()
        record_audit(db, user, "CREATE", PLAN_ENTITY, plan.id, {
            "plan_number": number, "plan_date": payload.plan_date.isoformat(), "meal_session_id": session.id,
            "menu_id": menu.id, "expected_headcount": payload.expected_headcount, "notes": plan.notes,
            "lines": lines_snapshot(rows)})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=(
            f"A meal plan for {session.name} on {day_text(payload.plan_date)} was created at the same time."))
    db.refresh(plan)
    return plan_detail(db, user, plan)


@plans_router.get("/{plan_id}")
def get_plan(plan_id: int, db: Session = Depends(get_db), user: User = Depends(planner("meal_plan.read"))):
    plan = db.query(MealPlan).filter(MealPlan.id == plan_id, MealPlan.campus_id == user.campus_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Meal plan not found")
    return plan_detail(db, user, plan)


@plans_router.put("/{plan_id}")
def update_plan(plan_id: int, payload: PlanFields, db: Session = Depends(get_db),
                user: User = Depends(planner("meal_plan.update"))):
    """Headcount, notes, main items and one-day overrides of a DRAFT plan
    dated today or later. Date, session and menu are fixed."""
    plan = lock_plan(db, user, plan_id)
    require_editable_plan(plan)
    units = Units(db, user.campus_id)
    checked = validated_lines(db, user, plan.menu_id, plan.plan_date, payload.lines, units)
    existing = {l.item_id: l for l in lines_of(db, plan.id)}
    before = {"expected_headcount": plan.expected_headcount, "notes": plan.notes,
              "lines": lines_snapshot(list(existing.values()))}
    wanted = {item.id for item, _line in checked}
    for item_id, line in existing.items():
        if item_id not in wanted:
            db.delete(line)
    for item, line in checked:
        row = existing.get(item.id) or MealPlanLine(campus_id=user.campus_id, plan_id=plan.id, item_id=item.id)
        row.override_quantity_per_person = (quantity(line.override_quantity_per_person)
                                            if line.override_quantity_per_person is not None else None)
        row.override_unit_id, row.override_reason = line.override_unit_id, line.override_reason
        db.add(row)
    db.flush()
    plan.expected_headcount = payload.expected_headcount
    plan.notes = clean(payload.notes)
    plan.updated_at = datetime.now(timezone.utc)
    record_audit(db, user, "UPDATE", PLAN_ENTITY, plan.id, {
        "before": before, "after": {"expected_headcount": plan.expected_headcount, "notes": plan.notes,
                                    "lines": lines_snapshot(lines_of(db, plan.id))}})
    db.commit()
    db.refresh(plan)
    return plan_detail(db, user, plan)


@plans_router.post("/{plan_id}/approve")
def approve_plan(plan_id: int, db: Session = Depends(get_db), user: User = Depends(managers)):
    """ADMIN or KITCHEN_MANAGER (6-5). Writes each line's snapshot (standard
    used, quantity per person, required quantity, factor) and freezes the
    plan (6-6, S6-2). Never changes stock (PLAN07)."""
    if not user_has_permission(db, user, "meal_plan.update"):
        raise HTTPException(status_code=403, detail="This permission has not been assigned to you.")
    plan = lock_plan(db, user, plan_id)
    require_editable_plan(plan)
    units = Units(db, user.campus_id)
    lines, problems = plan_lines(db, user, plan, units, live=True)
    if problems:
        raise HTTPException(status_code=422, detail="The plan cannot be approved yet: " + " ".join(problems))
    rows = {l.id: l for l in lines_of(db, plan.id)}
    for line in lines:
        row = rows[line["id"]]
        standard = line["standard"]
        row.standard_id, row.item_kind = standard["id"], line["item_kind"]
        row.standard_quantity_per_person = Decimal(standard["quantity_per_person"])
        row.standard_unit_id = standard["unit_id"]
        row.quantity_per_person, row.unit_id = Decimal(line["quantity_per_person"]), line["unit_id"]
        row.required_quantity, row.rounded_up = Decimal(line["required_quantity"]), line["rounded_up"]
        row.base_unit_id, row.conversion_factor = line["base_unit_id"], Decimal(line["conversion_factor"])
        row.required_base_quantity = Decimal(line["required_base_quantity"])
    db.flush()  # lines first: they may change only while the plan is a draft
    now = datetime.now(timezone.utc)
    plan.status, plan.approved_by, plan.approved_at, plan.updated_at = "APPROVED", user.id, now, now
    db.flush()
    record_audit(db, user, "APPROVE", PLAN_ENTITY, plan.id, {
        "expected_headcount": plan.expected_headcount,
        "lines": [{k: line[k] for k in ("item_id", "item_kind", "quantity_per_person", "unit_id", "required_quantity",
                                        "rounded_up", "conversion_factor", "required_base_quantity")}
                  | {"standard_id": line["standard"]["id"], "standard_version": line["standard"]["version_no"],
                     "override": line["override"]} for line in lines],
    })
    db.commit()
    db.refresh(plan)
    return plan_detail(db, user, plan)


@plans_router.post("/{plan_id}/cancel")
def cancel_plan(plan_id: int, payload: Reason, db: Session = Depends(get_db),
                user: User = Depends(planner("meal_plan.update"))):
    """Cancel a draft, or an approved plan (ADMIN or KITCHEN_MANAGER, the only
    planners) as the correction route: cancel with a reason, then create a new
    plan (6-6). The approved figures stay as history."""
    plan = lock_plan(db, user, plan_id)
    if plan.status == "CANCELLED":
        raise HTTPException(status_code=409, detail="This plan is already cancelled.")
    previous = plan.status
    now = datetime.now(timezone.utc)
    plan.status, plan.cancelled_by, plan.cancelled_at = "CANCELLED", user.id, now
    plan.cancellation_reason, plan.updated_at = payload.reason, now
    record_audit(db, user, "CANCEL", PLAN_ENTITY, plan.id, {"reason": payload.reason, "previous_status": previous})
    db.commit()
    db.refresh(plan)
    return plan_detail(db, user, plan)


@plans_router.get("/{plan_id}/comparison")
def plan_comparison(plan_id: int, db: Session = Depends(get_db), user: User = Depends(planner("meal_plan.read"))):
    """Planned vs actual (PLAN08) against the meal record of the exact campus,
    date and meal session (S6-1); same-named sessions are reported only."""
    plan = db.query(MealPlan).filter(MealPlan.id == plan_id, MealPlan.campus_id == user.campus_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Meal plan not found")
    record = live_record(db, plan.campus_id, plan.plan_date, plan.meal_session_id)
    result = comparison(db, user, plan, record, Units(db, user.campus_id))
    result["session_warnings"] = record_warnings(db, plan.campus_id, plan.plan_date, plan.meal_session_id)
    return result
