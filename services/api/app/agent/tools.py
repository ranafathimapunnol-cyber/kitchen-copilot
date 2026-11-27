"""Controlled agent tools (Stage 12, PROPOSAL.md §7.3).

The agent reaches application data only through the tools registered here.
Every call:
- re-checks the user's role and permission (the same checks as the screens);
- runs with the user's own campus (campus isolation comes from the user);
- calls the existing, tested application functions for every figure (the
  model never calculates authoritative numbers);
- is recorded as an agent step (inputs, a compact result, success, time).

No tool writes business data. Consequential actions are only *proposed*
(see app/agent/executor.py for approval and execution).
"""

import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Callable

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.dependencies import user_has_permission
from app.models.agent import AgentStep
from app.models.user import User, UserRole

PLANNERS = (UserRole.ADMIN, UserRole.KITCHEN_MANAGER)
ANY_CAMPUS_ROLE = (UserRole.ADMIN, UserRole.KITCHEN_MANAGER, UserRole.STAFF)


class ToolDenied(Exception):
    """The user may not use this tool (role or permission)."""


@dataclass
class Tool:
    name: str
    description: str
    roles: tuple
    permissions: tuple[str, ...]          # all required
    handler: Callable[..., Any]


@dataclass
class Trace:
    db: Session
    user: User
    conversation_id: int
    steps: list[AgentStep] = field(default_factory=list)

    def record(self, kind: str, name: str, data_in: dict, data_out: dict, ok: bool = True, ms: int = 0) -> None:
        step = AgentStep(conversation_id=self.conversation_id, campus_id=self.user.campus_id, seq=len(self.steps) + 1,
                         kind=kind, name=name, input=jsonable_encoder(data_in), output=jsonable_encoder(data_out),
                         ok=ok, duration_ms=ms)
        self.db.add(step)
        self.steps.append(step)


REGISTRY: dict[str, Tool] = {}


def tool(name: str, description: str, permissions: tuple[str, ...], roles: tuple = ANY_CAMPUS_ROLE):
    def wrap(fn):
        if name in REGISTRY:
            raise ValueError(f"Tool already registered: {name}")
        REGISTRY[name] = Tool(name, description, roles, permissions, fn)
        return fn
    return wrap


def allowed(db: Session, user: User, name: str) -> bool:
    t = REGISTRY[name]
    return user.role in t.roles and all(user_has_permission(db, user, p) for p in t.permissions)


def summarise(value: Any, depth: int = 0) -> Any:
    """A compact copy of a tool result for the trace (long lists cut)."""
    if isinstance(value, dict):
        return {k: summarise(v, depth + 1) for k, v in value.items()} if depth < 4 else "…"
    if isinstance(value, list):
        out = [summarise(v, depth + 1) for v in value[:12]]
        return out + [f"… {len(value) - 12} more"] if len(value) > 12 else out
    return value


def call(trace: Trace, name: str, **kwargs) -> Any:
    """Runs a registered tool for the trace's user. Raises ToolDenied when
    the user lacks the role or permission; HTTP errors of the underlying
    application function are recorded and re-raised."""
    t = REGISTRY.get(name)
    if t is None:
        raise ToolDenied(f"Unknown tool {name}")
    started = time.monotonic()
    if trace.user.role not in t.roles or not all(user_has_permission(trace.db, trace.user, p) for p in t.permissions):
        trace.record("tool", name, kwargs, {"denied": True, "needs": list(t.permissions)}, ok=False)
        raise ToolDenied(name)
    try:
        result = t.handler(trace.db, trace.user, **kwargs)
    except HTTPException as exc:
        trace.record("tool", name, kwargs, {"error": exc.detail, "status": exc.status_code}, ok=False,
                     ms=int((time.monotonic() - started) * 1000))
        raise
    trace.record("tool", name, kwargs, summarise(jsonable_encoder(result)), ms=int((time.monotonic() - started) * 1000))
    return result


# ============================================================
# READ TOOLS
# ============================================================

@tool("meal_options", "Active meal sessions and menus of the campus.", ("meal_plan.create",), PLANNERS)
def meal_options(db: Session, user: User) -> dict:
    from app.api.routes.planning import plan_options
    return plan_options(db=db, user=user)


@tool("plan_requirements", "Approved standards in effect, required quantities, current stock and the "
      "procurement gap for a date, meal session, menu and headcount (PLAN04 calculation).",
      ("meal_plan.create",), PLANNERS)
def plan_requirements(db: Session, user: User, plan_date: date, meal_session_id: int, menu_id: int,
                      headcount: int | None) -> dict:
    from app.api.routes.planning import Units, compute, plan_prefill
    from app.services.stock_ledger import quantity_text

    prefill = plan_prefill(plan_date=plan_date, meal_session_id=meal_session_id, menu_id=menu_id, db=db, user=user)
    record = prefill.get("meal_record") or {}
    used = headcount or record.get("expected_total")
    units = Units(db, user.campus_id)
    lines = []
    for row in prefill["items"]:
        std = row["standard"]
        line = {"item_id": row["item_id"], "item_name": row["item_name"],
                "standard": f'{std["quantity_per_person"]} {std["unit_symbol"]} per person (v{std["version_no"]}, '
                            f'from {std["effective_from"]})',
                "base_unit_id": row["base_unit_id"], "base_unit_symbol": row["base_unit_symbol"],
                "available_stock": row["available_stock"], "required": None, "gap": None}
        if used:
            result = compute(used, Decimal(std["quantity_per_person"]), units.by_id[std["unit_id"]],
                             Decimal(std["factor_to_base"]), units.by_id[row["base_unit_id"]])
            base_need = result["base"]
            gap = max(base_need - Decimal(row["available_stock"]), Decimal("0")) if base_need is not None else None
            line.update(required=quantity_text(base_need) if base_need is not None else None,
                        required_in_standard_unit=f'{quantity_text(result["required"])} {std["unit_symbol"]}',
                        rounded_up=result["rounded_up"], gap=quantity_text(gap) if gap is not None else None)
        lines.append(line)
    return {"plan_date": plan_date.isoformat(), "headcount": used,
            "headcount_source": "your request" if headcount else ("meal record (expected total)" if used else None),
            "meal_record": prefill.get("meal_record"), "existing_plan": prefill.get("existing_plan"),
            "warnings": prefill.get("session_warnings", []), "lines": lines,
            "unavailable_items": prefill.get("unavailable_items", []),
            "availability_note": prefill.get("availability_note")}


@tool("last_suppliers", "The supplier each item was most recently bought from (supplier bills).",
      ("purchase_order.create",), PLANNERS)
def last_suppliers(db: Session, user: User, item_ids: list[int]) -> dict:
    from app.models.master_data import Supplier
    from app.models.purchases import Purchase, PurchaseItem

    rows = (db.query(PurchaseItem.item_id, Purchase.supplier_id, Purchase.purchase_date, Purchase.id)
            .join(Purchase, Purchase.id == PurchaseItem.purchase_id)
            .filter(Purchase.campus_id == user.campus_id, PurchaseItem.item_id.in_(item_ids or [0]))
            .order_by(Purchase.purchase_date.desc(), Purchase.id.desc()).all())
    latest: dict[int, int] = {}
    for item_id, supplier_id, _d, _i in rows:
        latest.setdefault(item_id, supplier_id)
    active = {s.id: s.name for s in db.query(Supplier).filter(
        Supplier.campus_id == user.campus_id, Supplier.id.in_(set(latest.values()) or {0}),
        Supplier.is_active.is_(True))}
    return {"by_item": {i: {"supplier_id": s, "supplier_name": active[s]} for i, s in latest.items() if s in active}}


@tool("procedures", "Approved kitchen procedure documents matching a topic.", (), ANY_CAMPUS_ROLE)
def procedures(db: Session, user: User, topic: str) -> dict:
    from app.agent import knowledge
    return knowledge.search(topic)


@tool("spending_comparison", "Spending of a period against the comparison period, with weighted average "
      "prices and the price and quantity effects (DASH01-DASH04 calculations).", ("purchase_bill.read",))
def spending_comparison(db: Session, user: User, date_from: date, date_to: date, compare: str,
                        category_id: int | None = None, item_id: int | None = None) -> dict:
    from app.api.routes.analytics import build_spending
    return build_spending(db, user, date_from, date_to, compare, None, category_id, item_id)


OVERVIEW_SECTIONS = ("campus_name", "headcount", "stock", "meals", "planning", "outsourced", "kitchen", "counts",
                     "spending", "payments")


@tool("operations_overview", "The campus operational overview: the same figures, and the same per-section "
      "permission checks, as the dashboard.", ("dashboard.read",))
def operations_overview(db: Session, user: User) -> dict:
    from app.api.routes.dashboard import dashboard_overview
    data = dashboard_overview(db=db, user=user)
    return {key: data[key] for key in OVERVIEW_SECTIONS if key in data}


@tool("headcount_summary", "Average daily headcount from meal records for two periods.", ("meal.read",))
def headcount_summary(db: Session, user: User, periods: dict) -> dict:
    from app.models.meals import MealRecord
    from app.services.dashboard_sections import total

    out = {}
    for key, p in periods.items():
        start, end = date.fromisoformat(p["date_from"]), date.fromisoformat(p["date_to"])
        days: dict[date, int] = {}
        for r in db.query(MealRecord).filter(MealRecord.campus_id == user.campus_id, MealRecord.status != "CANCELLED",
                                             MealRecord.meal_date >= start, MealRecord.meal_date <= end):
            value = total(r, "actual")
            value = value if value is not None else total(r, "expected")
            if value is not None:
                days[r.meal_date] = max(days.get(r.meal_date, 0), value)
        out[key] = {"days_with_records": len(days),
                    "average_daily_headcount": round(sum(days.values()) / len(days)) if days else None}
    return {"rule": "A day's headcount is its largest meal (actual if recorded, otherwise expected).", **out}


@tool("find_item", "Items of the campus whose name matches.", ("inventory.read",))
def find_item(db: Session, user: User, item_id: int) -> dict:
    from app.models.master_data import Item, Unit
    item = db.query(Item).filter(Item.id == item_id, Item.campus_id == user.campus_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    unit = db.query(Unit.symbol).filter(Unit.id == item.standard_unit_id).scalar()
    return {"id": item.id, "name": item.name, "unit": unit}


@tool("latest_count_line", "The most recent physical count line for an item (on or before a date).",
      ("stock_count.read",))
def latest_count_line(db: Session, user: User, item_id: int, on_or_before: date | None) -> dict:
    from app.api.routes.stock_counts import count_detail
    from app.core.clock import campus_timezone
    from app.models.stock import StockCount, StockCountItem

    query = (db.query(StockCount).join(StockCountItem, StockCountItem.count_id == StockCount.id)
             .filter(StockCount.campus_id == user.campus_id, StockCountItem.item_id == item_id))
    if on_or_before:
        end = datetime.combine(on_or_before + timedelta(days=1), datetime.min.time(), tzinfo=campus_timezone())
        query = query.filter(StockCount.counted_at < end)
    count = query.order_by(StockCount.counted_at.desc(), StockCount.id.desc()).first()
    if not count:
        return {"count": None}
    detail = count_detail(db, user, count)
    line = next(l for l in detail["lines"] if l["item_id"] == item_id)
    return {"count": {k: detail[k] for k in ("id", "count_number", "counted_at", "counted_by_id", "counted_by_name",
                                             "reason")}, "line": line}


@tool("item_movements", "Stock movements of one item with the running balance (stock ledger).", ("inventory.read",))
def item_movements(db: Session, user: User, item_id: int, since: datetime, until: datetime) -> dict:
    from app.api.routes.stock import item_ledger
    from app.services.stock_ledger import as_utc

    ledger = item_ledger(item_id=item_id, page=1, page_size=500, db=db, user=user)
    keep = [m for m in ledger["movements"]
            if since <= as_utc(datetime.fromisoformat(m["effective_at"].replace("Z", "+00:00"))) <= until]
    return {"item": ledger["item"], "movements": keep}


@tool("unposted_documents", "Draft goods receipts, kitchen issues and kitchen returns for an item "
      "(recorded but not yet posted to stock).", ("inventory.read",))
def unposted_documents(db: Session, user: User, item_id: int) -> dict:
    from app.models.purchases import GoodsReceipt, GoodsReceiptItem, PurchaseItem
    from app.models.stock import KitchenIssue, KitchenIssueItem, KitchenReturn, KitchenReturnItem

    campus = user.campus_id
    receipts = (db.query(GoodsReceipt.id, GoodsReceipt.receipt_date, GoodsReceiptItem.quantity_accepted)
                .join(GoodsReceiptItem, GoodsReceiptItem.receipt_id == GoodsReceipt.id)
                .join(PurchaseItem, PurchaseItem.id == GoodsReceiptItem.purchase_item_id)
                .filter(GoodsReceipt.campus_id == campus, GoodsReceipt.status == "DRAFT", PurchaseItem.item_id == item_id)
                .all())
    issues = (db.query(KitchenIssue.id, KitchenIssue.created_at, KitchenIssueItem.standard_quantity)
              .join(KitchenIssueItem, KitchenIssueItem.issue_id == KitchenIssue.id)
              .filter(KitchenIssue.campus_id == campus, KitchenIssue.status == "DRAFT", KitchenIssueItem.item_id == item_id)
              .all())
    returns = (db.query(KitchenReturn.id, KitchenReturn.created_at, KitchenReturnItem.standard_quantity)
               .join(KitchenReturnItem, KitchenReturnItem.return_id == KitchenReturn.id)
               .join(KitchenIssueItem, KitchenIssueItem.id == KitchenReturnItem.issue_item_id)
               .filter(KitchenReturn.campus_id == campus, KitchenReturn.status == "DRAFT",
                       KitchenIssueItem.item_id == item_id).all())
    return {
        "draft_receipts": [{"receipt_id": i, "date": d.isoformat(), "accepted": str(q)} for i, d, q in receipts],
        "draft_issues": [{"issue_id": i, "created_at": c.isoformat(), "quantity": str(q)} for i, c, q in issues],
        "draft_returns": [{"return_id": i, "created_at": c.isoformat(), "quantity": str(q)} for i, c, q in returns],
    }


def count_rows(db: Session, model, campus_id: int) -> int:
    return db.query(func.count(model.id)).filter(model.campus_id == campus_id).scalar() or 0
