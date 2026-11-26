"""Operational reports (Stage 9; PROPOSAL.md §5.8, AT03).

Every report returns the same shape — title, reporting period, filters,
columns (with kinds and units), rows, totals and notes — so the screen,
Excel, PDF and the print view all show the same figures. Each report has
its own permission (the module it reads); every query is limited to the
user's campus. Quantities are shown with their units; quantities in
different units are never added together.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.dependencies import user_has_permission
from app.core.clock import campus_timezone, campus_today
from app.models.campus import Campus
from app.models.master_data import Category, Item, MealSession, Supplier, Unit
from app.models.meals import MealDish, MealLeftover, MealRecord
from app.models.purchases import Purchase, StockMovement, SupplierPayment
from app.models.stock import KitchenIssue, KitchenIssueItem, StockAdjustment, StockCount, StockCountItem
from app.models.user import User, UserRole
from app.services import purchase_analytics as pa
from app.services.stock_ledger import start_of_campus_day

ZERO = Decimal("0")
MAX_DAYS = 366

AT03_RULE = (
    "Interim rule while client question Q4 is open (not a client decision): one transaction is one supplier "
    "bill containing the item, however many lines of that item the bill has; goods receipts do not create "
    "transactions. Purchase days are distinct bill dates. Quantities are converted to the item's standard unit "
    "through explicit conversions; lines without one are excluded and counted. Expenditure is the item's line "
    "totals; bill-level discounts and extra charges are not allocated (client question Q5)."
)


@dataclass
class Params:
    date_from: date | None = None
    date_to: date | None = None
    supplier_id: int | None = None
    category_id: int | None = None
    item_id: int | None = None
    meal_session_id: int | None = None
    compare: str = "elapsed"


@dataclass
class Report:
    key: str
    title: str
    description: str
    filters: tuple[str, ...]  # period, as_of, supplier, category, item, meal_session, compare
    allowed: Callable[[Session, User], bool]
    build: Callable
    group: str = "Reports"
    period_required: bool = True


def has(code: str):
    return lambda db, user: user_has_permission(db, user, code)


def planner(db: Session, user: User) -> bool:
    return user.role in (UserRole.ADMIN, UserRole.KITCHEN_MANAGER) and user_has_permission(db, user, "meal_plan.read")


def col(key, label, kind="text", unit=None):
    return {"key": key, "label": label, "kind": kind, "unit_key": unit}


def day_text(value) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def local_time(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(campus_timezone()).strftime("%Y-%m-%d %H:%M")


def q(value) -> str:
    return pa.qty_text(value)


class Lookups:
    def __init__(self, db: Session, campus_id: int):
        self.units = dict(db.query(Unit.id, Unit.symbol).filter(Unit.campus_id == campus_id))
        self.items = {i.id: i for i in db.query(Item).filter(Item.campus_id == campus_id)}
        self.categories = dict(db.query(Category.id, Category.name).filter(Category.campus_id == campus_id))
        self.suppliers = dict(db.query(Supplier.id, Supplier.name).filter(Supplier.campus_id == campus_id))
        self.sessions = dict(db.query(MealSession.id, MealSession.name).filter(MealSession.campus_id == campus_id))

    def item(self, item_id) -> str | None:
        item = self.items.get(item_id)
        return item.name if item else None

    def category_of(self, item_id) -> str | None:
        item = self.items.get(item_id)
        return self.categories.get(item.category_id) if item else None

    def std_unit(self, item_id) -> str | None:
        item = self.items.get(item_id)
        return self.units.get(item.standard_unit_id) if item else None


def per_unit_totals(rows: list[dict], quantity_key: str, unit_key: str, label: str) -> list[dict]:
    sums: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for row in rows:
        if row.get(quantity_key) not in (None, ""):
            sums[row.get(unit_key) or ""] += Decimal(row[quantity_key])
    return [{"label": f"{label} ({unit})", "value": q(v), "kind": "qty", "unit": unit} for unit, v in sorted(sums.items())]


# ============================================================
# PURCHASING (purchase_bill.read)
# ============================================================

def purchase_transactions(db, user, p: Params, lk: Lookups) -> dict:
    lines = pa.purchase_lines(db, user.campus_id, p.date_from, p.date_to, supplier_id=p.supplier_id,
                              category_id=p.category_id, item_id=p.item_id)
    rows = [{
        "purchase_date": day_text(l["purchase_date"]), "invoice_number": l["invoice_number"],
        "supplier": lk.suppliers.get(l["supplier_id"]), "item": lk.item(l["item_id"]),
        "category": lk.categories.get(l["category_id"]), "quantity": q(l["quantity"]), "unit": lk.units.get(l["unit_id"]),
        "standard_quantity": q(l["standard_quantity"]) if l["standard_quantity"] is not None else None,
        "standard_unit": lk.std_unit(l["item_id"]), "unit_rate": pa.price_text(l["unit_rate"]),
        "line_total": pa.money_text(l["line_total"]), "_purchase_id": l["purchase_id"],
    } for l in lines]
    totals = [{"label": "Lines", "value": str(len(rows)), "kind": "number"},
              {"label": "Bills", "value": str(len({l["purchase_id"] for l in lines})), "kind": "number"},
              {"label": "Line totals", "value": pa.money_text(sum((l["line_total"] for l in lines), ZERO)), "kind": "money"}]
    notes = []
    if not (p.category_id or p.item_id):
        bills = pa.bill_totals(db, user.campus_id, p.date_from, p.date_to, p.supplier_id)
        totals += [{"label": "Bill discounts (not allocated)", "value": pa.money_text(-bills["discount"]), "kind": "money"},
                   {"label": "Bill extra charges (not allocated)", "value": pa.money_text(bills["extra_charges"]), "kind": "money"},
                   {"label": "Purchase expenditure (bill grand totals)", "value": pa.money_text(bills["grand_total"]), "kind": "money"}]
    else:
        notes.append("Bill-level discounts and extra charges are not included when a category or item is chosen "
                      "(no approved allocation rule, client question Q5).")
    return {"columns": [col("purchase_date", "Bill date", "date"), col("invoice_number", "Invoice"),
                        col("supplier", "Supplier"), col("item", "Item"), col("category", "Category"),
                        col("quantity", "Quantity", "qty", "unit"), col("standard_quantity", "Standard qty", "qty", "standard_unit"),
                        col("unit_rate", "Rate", "money"), col("line_total", "Line total", "money")],
            "rows": rows, "totals": totals, "notes": notes}


def category_expenses(db, user, p: Params, lk: Lookups) -> dict:
    lines = pa.purchase_lines(db, user.campus_id, p.date_from, p.date_to, supplier_id=p.supplier_id)
    groups: dict[int, dict] = {}
    for l in lines:
        g = groups.setdefault(l["category_id"], {"value": ZERO, "lines": 0, "bills": set(), "items": set()})
        g["value"] += l["line_total"]
        g["lines"] += 1
        g["bills"].add(l["purchase_id"])
        g["items"].add(l["item_id"])
    total = sum((g["value"] for g in groups.values()), ZERO)
    rows = sorted(({"category": lk.categories.get(cid), "items": len(g["items"]), "lines": g["lines"],
                    "bills": len(g["bills"]), "value": pa.money_text(g["value"]),
                    "share": format((g["value"] / total * 100).quantize(Decimal("0.1")), "f") if total else None,
                    "_category_id": cid} for cid, g in groups.items()),
                  key=lambda r: Decimal(r["value"]), reverse=True)
    bills = pa.bill_totals(db, user.campus_id, p.date_from, p.date_to, p.supplier_id)
    return {"columns": [col("category", "Category"), col("items", "Items", "number"), col("lines", "Lines", "number"),
                        col("bills", "Bills", "number"), col("value", "Expenditure (line totals)", "money"),
                        col("share", "Share %", "percent")],
            "rows": rows,
            "totals": [{"label": "Line totals", "value": pa.money_text(total), "kind": "money"},
                       {"label": "Bill discounts (not allocated)", "value": pa.money_text(-bills["discount"]), "kind": "money"},
                       {"label": "Bill extra charges (not allocated)", "value": pa.money_text(bills["extra_charges"]), "kind": "money"},
                       {"label": "Purchase expenditure (bill grand totals)", "value": pa.money_text(bills["grand_total"]), "kind": "money"}],
            "notes": ["Bill-level discounts and extra charges are shown separately and not allocated to categories "
                      "(client question Q5)."]}


def item_purchases(db, user, p: Params, lk: Lookups) -> dict:
    """AT03 (monthly chicken purchase report) for any item or category."""
    lines = pa.purchase_lines(db, user.campus_id, p.date_from, p.date_to, supplier_id=p.supplier_id,
                              category_id=p.category_id, item_id=p.item_id)
    items = pa.summarise_items(lines)
    rows = sorted(({
        "item": lk.item(item_id), "category": lk.category_of(item_id),
        "transactions": len(e["bills"]), "purchase_days": len(e["days"]), "lines": e["lines"],
        "quantity": q(e["quantity"]), "unit": lk.std_unit(item_id),
        "expenditure": pa.money_text(e["value"] + e["excluded_value"]),
        "average_price": pa.price_text(e["price"]), "excluded_lines": e["excluded_lines"],
    } for item_id, e in items.items()), key=lambda r: (r["item"] or "").lower())
    totals = [{"label": "Transactions (bills)", "value": str(len({l["purchase_id"] for l in lines})), "kind": "number"},
              {"label": "Distinct purchase days", "value": str(len({l["purchase_date"] for l in lines})), "kind": "number"},
              *per_unit_totals(rows, "quantity", "unit", "Total quantity"),
              {"label": "Total purchase expenditure (line totals)",
               "value": pa.money_text(sum((l["line_total"] for l in lines), ZERO)), "kind": "money"}]
    return {"columns": [col("item", "Item"), col("category", "Category"), col("transactions", "Transactions", "number"),
                        col("purchase_days", "Purchase days", "number"), col("lines", "Lines", "number"),
                        col("quantity", "Quantity", "qty", "unit"), col("expenditure", "Expenditure", "money"),
                        col("average_price", "Weighted avg price", "money"), col("excluded_lines", "Excluded lines", "number")],
            "rows": rows, "totals": totals, "notes": [AT03_RULE]}


def price_comparison(db, user, p: Params, lk: Lookups) -> dict:
    from app.api.routes.analytics import build_spending

    data = build_spending(db, user, p.date_from, p.date_to, p.compare or "elapsed", p.supplier_id, p.category_id, p.item_id)
    labels = {"COMPARABLE": "Comparable", "NEW": "Not bought before", "NOT_BOUGHT_NOW": "Not bought now",
              "INCOMPATIBLE": "No conversion"}
    rows = [{
        "item": r["item_name"], "unit": r["standard_unit_symbol"], "previous_quantity": r["previous_quantity"],
        "current_quantity": r["current_quantity"], "previous_price": r["previous_price"], "current_price": r["current_price"],
        "price_change_percent": r["price_change_percent"], "previous_value": r["previous_value"],
        "current_value": r["current_value"], "value_change": r["value_change"],
        "value_change_percent": r["value_change_percent"], "price_effect": r["price_effect"],
        "quantity_effect": r["quantity_effect"], "status": labels[r["status"]],
    } for r in data["items"]]
    cur, prev = data["periods"]["current"], data["periods"]["previous"]
    t = data["totals"]
    return {"columns": [col("item", "Item"), col("previous_quantity", "Previous qty", "qty", "unit"),
                        col("current_quantity", "Current qty", "qty", "unit"), col("previous_price", "Previous avg price", "money"),
                        col("current_price", "Current avg price", "money"), col("price_change_percent", "Price change %", "percent"),
                        col("previous_value", "Previous value", "money"), col("current_value", "Current value", "money"),
                        col("value_change", "Change", "money"), col("price_effect", "Price effect", "money"),
                        col("quantity_effect", "Quantity effect", "money"), col("status", "Status")],
            "rows": rows,
            "totals": [{"label": f"Previous period {prev['date_from']} – {prev['date_to']}", "value": t["previous"], "kind": "money"},
                       {"label": f"Current period {cur['date_from']} – {cur['date_to']}", "value": t["current"], "kind": "money"},
                       {"label": "Change", "value": t["change"], "kind": "money"},
                       {"label": "Change %", "value": t["change_percent"], "kind": "percent"},
                       {"label": "Price effect (items)", "value": t["price_effect"], "kind": "money"},
                       {"label": "Quantity effect (items)", "value": t["quantity_effect"], "kind": "money"}],
            "notes": data["notes"], "comparison": data["periods"]}


def supplier_balances(db, user, p: Params, lk: Lookups) -> dict:
    as_of = p.date_to or campus_today()
    billed = dict(db.query(Purchase.supplier_id, func.sum(Purchase.grand_total)).filter(
        Purchase.campus_id == user.campus_id, Purchase.purchase_date <= as_of).group_by(Purchase.supplier_id))
    in_period = {}
    if p.date_from:
        in_period = dict(db.query(Purchase.supplier_id, func.sum(Purchase.grand_total)).filter(
            Purchase.campus_id == user.campus_id, Purchase.purchase_date >= p.date_from,
            Purchase.purchase_date <= as_of).group_by(Purchase.supplier_id))
    paid = dict(db.query(Purchase.supplier_id, func.sum(SupplierPayment.amount))
                .join(Purchase, Purchase.id == SupplierPayment.purchase_id)
                .filter(SupplierPayment.campus_id == user.campus_id, SupplierPayment.payment_date <= as_of)
                .group_by(Purchase.supplier_id))
    paid_period = {}
    if p.date_from:
        paid_period = dict(db.query(Purchase.supplier_id, func.sum(SupplierPayment.amount))
                           .join(Purchase, Purchase.id == SupplierPayment.purchase_id)
                           .filter(SupplierPayment.campus_id == user.campus_id, SupplierPayment.payment_date >= p.date_from,
                                   SupplierPayment.payment_date <= as_of).group_by(Purchase.supplier_id))
    ids = set(billed) | set(paid)
    if p.supplier_id:
        ids &= {p.supplier_id}
    rows = sorted(({"supplier": lk.suppliers.get(sid),
                    "billed_period": pa.money_text(in_period.get(sid, 0)), "paid_period": pa.money_text(paid_period.get(sid, 0)),
                    "billed": pa.money_text(billed.get(sid, 0)), "paid": pa.money_text(paid.get(sid, 0)),
                    "outstanding": pa.money_text(Decimal(str(billed.get(sid, 0) or 0)) - Decimal(str(paid.get(sid, 0) or 0)))}
                   for sid in ids), key=lambda r: (r["supplier"] or "").lower())
    total = lambda key: pa.money_text(sum((Decimal(r[key]) for r in rows), ZERO))  # noqa: E731
    return {"columns": [col("supplier", "Supplier"), col("billed_period", "Billed in period", "money"),
                        col("paid_period", "Paid in period", "money"), col("billed", "Billed to date", "money"),
                        col("paid", "Paid to date", "money"), col("outstanding", "Outstanding", "money")],
            "rows": rows,
            "totals": [{"label": "Billed in period", "value": total("billed_period"), "kind": "money"},
                       {"label": "Paid in period", "value": total("paid_period"), "kind": "money"},
                       {"label": f"Outstanding on {as_of.isoformat()}", "value": total("outstanding"), "kind": "money"}],
            "notes": ["Purchase expenditure (bills) and supplier payments are shown separately. A negative "
                      "outstanding balance is an overpayment (credit with the supplier). Supplier credits for returns "
                      "are not recorded yet (client question Q6)."]}


# ============================================================
# STOCK
# ============================================================

def stock_movements(db, user, p: Params, lk: Lookups) -> dict:
    start = start_of_campus_day(p.date_from)
    end = start_of_campus_day(p.date_to + timedelta(days=1))
    query = (db.query(StockMovement).filter(StockMovement.campus_id == user.campus_id,
                                            StockMovement.effective_at >= start, StockMovement.effective_at < end))
    if p.item_id:
        query = query.filter(StockMovement.item_id == p.item_id)
    if p.category_id:
        query = query.join(Item, Item.id == StockMovement.item_id).filter(Item.category_id == p.category_id)
    rows = []
    for m in query.order_by(StockMovement.effective_at, StockMovement.id).limit(5000):
        signed = Decimal(m.direction) * Decimal(str(m.quantity))
        rows.append({"effective_at": local_time(m.effective_at), "item": lk.item(m.item_id),
                     "category": lk.category_of(m.item_id), "movement_type": m.movement_type.replace("_", " ").title(),
                     "quantity_in": q(signed) if signed > 0 else None, "quantity_out": q(-signed) if signed < 0 else None,
                     "unit": lk.units.get(m.unit_id), "reference": f"{m.reference_type} #{m.reference_id}" if m.reference_type else "",
                     "remarks": m.remarks})
    return {"columns": [col("effective_at", "When (campus time)"), col("item", "Item"), col("category", "Category"),
                        col("movement_type", "Movement"), col("quantity_in", "In", "qty", "unit"),
                        col("quantity_out", "Out", "qty", "unit"), col("reference", "Source"), col("remarks", "Remarks")],
            "rows": rows,
            "totals": [{"label": "Movements", "value": str(len(rows)), "kind": "number"},
                       *per_unit_totals(rows, "quantity_in", "unit", "In"),
                       *per_unit_totals(rows, "quantity_out", "unit", "Out")],
            "notes": ["Movements in each item's standard unit, by the campus-time day they took effect."]}


def low_stock(db, user, p: Params, lk: Lookups) -> dict:
    from app.api.routes.stock import balances_subquery

    balances = balances_subquery(db, user.campus_id)
    query = (db.query(Item, balances.c.balance).outerjoin(balances, balances.c.item_id == Item.id)
             .filter(Item.campus_id == user.campus_id, Item.is_active.is_(True), Item.minimum_stock > 0,
                     (Item.item_kind.is_(None)) | (Item.item_kind != "OUTSOURCED")))
    if p.category_id:
        query = query.filter(Item.category_id == p.category_id)
    rows = []
    for item, balance in query.order_by(func.lower(Item.name)):
        balance = Decimal(str(balance or 0))
        minimum = Decimal(str(item.minimum_stock))
        if balance < minimum:
            rows.append({"item": item.name, "category": lk.categories.get(item.category_id), "balance": q(balance),
                         "minimum": q(minimum), "needed": q(minimum - balance), "unit": lk.units.get(item.standard_unit_id),
                         "level": "Out of stock" if balance <= 0 else "Below minimum"})
    return {"columns": [col("item", "Item"), col("category", "Category"), col("balance", "Balance", "qty", "unit"),
                        col("minimum", "Minimum", "qty", "unit"), col("needed", "Needed", "qty", "unit"), col("level", "Level")],
            "rows": rows,
            "totals": [{"label": "Items below minimum", "value": str(len(rows)), "kind": "number"},
                       {"label": "Out of stock", "value": str(sum(1 for r in rows if r["level"] == "Out of stock")), "kind": "number"}],
            "notes": ["Current balances (as of now), from posted stock movements; outsourced food is not stocked."]}


def ingredient_usage(db, user, p: Params, lk: Lookups) -> dict:
    from app.api.routes.kitchen import returned_by_line

    query = db.query(KitchenIssue).filter(KitchenIssue.campus_id == user.campus_id, KitchenIssue.status == "CONFIRMED",
                                          KitchenIssue.issue_date >= p.date_from, KitchenIssue.issue_date <= p.date_to)
    if p.meal_session_id:
        query = query.filter(KitchenIssue.meal_session_id == p.meal_session_id)
    usage: dict[tuple, dict] = {}
    for issue in query.order_by(KitchenIssue.issue_date, KitchenIssue.id):
        returned = returned_by_line(db, issue.id, ("CONFIRMED",))
        for line in db.query(KitchenIssueItem).filter(KitchenIssueItem.issue_id == issue.id):
            if p.item_id and line.item_id != p.item_id:
                continue
            if p.category_id and (lk.items.get(line.item_id) is None or lk.items[line.item_id].category_id != p.category_id):
                continue
            key = (issue.issue_date, issue.meal_session_id, line.item_id)
            entry = usage.setdefault(key, {"issued": ZERO, "returned": ZERO, "unit": line.standard_unit_id, "issues": set()})
            entry["issued"] += Decimal(str(line.standard_quantity))
            entry["returned"] += returned.get(line.id, ZERO)
            entry["issues"].add(issue.issue_number)
    rows = [{"issue_date": day_text(d), "meal_session": lk.sessions.get(s), "item": lk.item(i),
             "issued": q(e["issued"]), "returned": q(e["returned"]), "net": q(e["issued"] - e["returned"]),
             "unit": lk.units.get(e["unit"]), "issues": ", ".join(sorted(e["issues"]))}
            for (d, s, i), e in sorted(usage.items(), key=lambda kv: (kv[0][0], lk.sessions.get(kv[0][1]) or "", lk.item(kv[0][2]) or ""))]
    return {"columns": [col("issue_date", "Date", "date"), col("meal_session", "Meal session"), col("item", "Item"),
                        col("issued", "Issued", "qty", "unit"), col("returned", "Returned unused", "qty", "unit"),
                        col("net", "Net usage", "qty", "unit"), col("issues", "Issues")],
            "rows": rows, "totals": per_unit_totals(rows, "net", "unit", "Net usage"),
            "notes": ["Confirmed kitchen issues minus confirmed unused returns, in each item's standard unit."]}


def stock_differences(db, user, p: Params, lk: Lookups) -> dict:
    start = start_of_campus_day(p.date_from)
    end = start_of_campus_day(p.date_to + timedelta(days=1))
    query = (db.query(StockCountItem, StockCount).join(StockCount, StockCount.id == StockCountItem.count_id)
             .filter(StockCount.campus_id == user.campus_id, StockCount.counted_at >= start, StockCount.counted_at < end))
    if p.item_id:
        query = query.filter(StockCountItem.item_id == p.item_id)
    adjustments = {a.count_item_id: a for a in db.query(StockAdjustment).filter(StockAdjustment.campus_id == user.campus_id)}
    rows = []
    for line, count in query.order_by(StockCount.counted_at, StockCountItem.id):
        adj = adjustments.get(line.id)
        rows.append({"counted_at": local_time(count.counted_at), "count_number": count.count_number, "item": lk.item(line.item_id),
                     "system_balance": q(line.system_balance), "physical": q(line.standard_quantity),
                     "difference": q(line.difference), "unit": lk.units.get(line.standard_unit_id),
                     "adjustment": adj.status.title() if adj else "None raised"})
    return {"columns": [col("counted_at", "Counted (campus time)"), col("count_number", "Count"), col("item", "Item"),
                        col("system_balance", "System", "qty", "unit"), col("physical", "Physical", "qty", "unit"),
                        col("difference", "Difference", "qty", "unit"), col("adjustment", "Adjustment")],
            "rows": rows,
            "totals": [{"label": "Count lines", "value": str(len(rows)), "kind": "number"},
                       {"label": "Lines with a difference", "value": str(sum(1 for r in rows if Decimal(r["difference"]) != 0)),
                        "kind": "number"}],
            "notes": ["Difference = physical − system balance at the count time, in the item's standard unit."]}


# ============================================================
# MEALS AND PLANNING
# ============================================================

def records(db, user, p: Params):
    query = db.query(MealRecord).filter(MealRecord.campus_id == user.campus_id, MealRecord.status != "CANCELLED",
                                        MealRecord.meal_date >= p.date_from, MealRecord.meal_date <= p.date_to)
    if p.meal_session_id:
        query = query.filter(MealRecord.meal_session_id == p.meal_session_id)
    return {r.id: r for r in query}


def people(record: MealRecord, prefix: str):
    values = [getattr(record, f"{prefix}_{g}") for g in ("students", "staff", "guests")]
    return None if any(v is None for v in values) else sum(values)


def meal_distribution(db, user, p: Params, lk: Lookups) -> dict:
    recs = records(db, user, p)
    rows = []
    for dish in db.query(MealDish).filter(MealDish.meal_record_id.in_(list(recs) or [0])).order_by(MealDish.id):
        r = recs[dish.meal_record_id]
        kind = "Carried in" if dish.source_leftover_id else ("Received (outsourced)" if dish.source_delivery_line_id else "Prepared")
        rows.append({"meal_date": day_text(r.meal_date), "meal_session": lk.sessions.get(r.meal_session_id),
                     "status": r.status.title(), "expected": people(r, "expected"), "served": people(r, "actual"),
                     "dish": dish.dish_name, "kind": kind, "available": q(dish.available_quantity),
                     "distributed": q(dish.distributed_quantity) if dish.distributed_quantity is not None else None,
                     "remaining": q(dish.remaining_quantity) if dish.remaining_quantity is not None else None,
                     "unit": lk.units.get(dish.unit_id), "_record_id": r.id})
    rows.sort(key=lambda r: (r["meal_date"], r["meal_session"] or "", r["dish"].lower()))
    return {"columns": [col("meal_date", "Date", "date"), col("meal_session", "Meal session"), col("status", "Record"),
                        col("expected", "Expected people", "number"), col("served", "People served", "number"),
                        col("dish", "Dish"), col("kind", "Kind"), col("available", "Available", "qty", "unit"),
                        col("distributed", "Distributed", "qty", "unit"), col("remaining", "Remaining", "qty", "unit")],
            "rows": rows,
            "totals": [{"label": "Meal records", "value": str(len(recs)), "kind": "number"},
                       *per_unit_totals(rows, "available", "unit", "Available"),
                       *per_unit_totals(rows, "distributed", "unit", "Distributed")],
            "notes": ["Available = prepared + carried in + received; distributed + remaining = available once recorded. "
                      "Headcounts are people, never food quantities."]}


def leftovers(db, user, p: Params, lk: Lookups) -> dict:
    recs = records(db, user, p)
    labels = {"RETAINED": "Retained", "RETURNED_TO_SUPPLIER": "Returned to supplier", "WASTED": "Wasted",
              "DISPOSED": "Otherwise disposed"}
    rows = []
    for row, dish in (db.query(MealLeftover, MealDish).join(MealDish, MealDish.id == MealLeftover.dish_id)
                      .filter(MealLeftover.meal_record_id.in_(list(recs) or [0])).order_by(MealLeftover.id)):
        r = recs[row.meal_record_id]
        rows.append({"meal_date": day_text(r.meal_date), "meal_session": lk.sessions.get(r.meal_session_id),
                     "dish": dish.dish_name, "classification": labels.get(row.classification, row.classification),
                     "quantity": q(row.quantity), "unit": lk.units.get(row.unit_id), "remarks": row.remarks})
    rows.sort(key=lambda r: (r["meal_date"], r["meal_session"] or "", r["dish"].lower()))
    totals = []
    for label in labels.values():
        totals += per_unit_totals([r for r in rows if r["classification"] == label], "quantity", "unit", label)
    return {"columns": [col("meal_date", "Date", "date"), col("meal_session", "Meal session"), col("dish", "Dish"),
                        col("classification", "Classification"), col("quantity", "Quantity", "qty", "unit"),
                        col("remarks", "Remarks")],
            "rows": rows, "totals": totals,
            "notes": ["“Returned to supplier” is a classification only; no supplier credit is recorded (client question Q6)."]}


def planned_vs_actual(db, user, p: Params, lk: Lookups) -> dict:
    from app.api.routes.planning import Units, comparison, live_record
    from app.models.planning import MealPlan

    query = db.query(MealPlan).filter(MealPlan.campus_id == user.campus_id, MealPlan.status == "APPROVED",
                                      MealPlan.plan_date >= p.date_from, MealPlan.plan_date <= p.date_to)
    if p.meal_session_id:
        query = query.filter(MealPlan.meal_session_id == p.meal_session_id)
    units = Units(db, user.campus_id)
    rows = []
    for plan in query.order_by(MealPlan.plan_date, MealPlan.meal_session_id):
        record = live_record(db, user.campus_id, plan.plan_date, plan.meal_session_id)
        result = comparison(db, user, plan, record, units)
        heads = result.get("headcounts") or {}
        for item in result.get("items", []):
            if p.item_id and item["item_id"] != p.item_id:
                continue
            rows.append({"plan_date": day_text(plan.plan_date), "meal_session": lk.sessions.get(plan.meal_session_id),
                         "plan_number": plan.plan_number, "planned_people": plan.expected_headcount,
                         "served": heads.get("record_actual"), "item": item["item_name"],
                         "planned": item["planned_quantity"], "actual": item["actual_net_quantity"],
                         "difference": item["difference"], "unit": item["unit_symbol"],
                         "record": "No meal record" if record is None else record.status.title()})
    return {"columns": [col("plan_date", "Date", "date"), col("meal_session", "Meal session"), col("plan_number", "Plan"),
                        col("planned_people", "Planned people", "number"), col("served", "People served", "number"),
                        col("item", "Item"), col("planned", "Planned", "qty", "unit"), col("actual", "Actual net usage", "qty", "unit"),
                        col("difference", "Difference", "qty", "unit"), col("record", "Meal record")],
            "rows": rows, "totals": [{"label": "Plan lines", "value": str(len(rows)), "kind": "number"}],
            "notes": ["Approved plans only, against the meal record of the exact date and meal session; actual usage "
                      "is the closing snapshot once the record is closed. Difference = actual − planned."]}


# ============================================================
# CATALOGUE
# ============================================================

REPORTS: dict[str, Report] = {r.key: r for r in (
    Report("purchase_transactions", "Purchase transactions", "Every bill line in the period, with quantities in the "
           "bill unit and the item's standard unit.", ("period", "supplier", "category", "item"),
           has("purchase_bill.read"), purchase_transactions, "Purchasing"),
    Report("category_expenses", "Category-wise expenses", "Expenditure per category, with bill-level discounts and "
           "charges shown separately.", ("period", "supplier"), has("purchase_bill.read"), category_expenses, "Purchasing"),
    Report("item_purchases", "Item purchase report", "Transactions, purchase days, total quantity and expenditure per "
           "item (for example the monthly chicken report, AT03).", ("period", "supplier", "category", "item"),
           has("purchase_bill.read"), item_purchases, "Purchasing"),
    Report("price_comparison", "Purchase quantity and price comparison", "Two periods side by side: weighted average "
           "prices, quantities and the price and quantity effects.", ("period", "compare", "supplier", "category", "item"),
           has("purchase_bill.read"), price_comparison, "Purchasing"),
    Report("supplier_balances", "Supplier balances", "Billed and paid in the period and to date, and what is "
           "outstanding at the end date.", ("period", "supplier"), has("purchase_bill.read"), supplier_balances, "Purchasing"),
    Report("stock_movements", "Stock movements", "Every stock movement that took effect in the period.",
           ("period", "category", "item"), has("inventory.read"), stock_movements, "Stock"),
    Report("low_stock", "Low-stock items", "Items whose current balance is below their minimum stock.",
           ("category",), has("inventory.read"), low_stock, "Stock", period_required=False),
    Report("ingredient_usage", "Daily ingredient usage", "Net ingredient usage per day, meal session and item.",
           ("period", "meal_session", "category", "item"), has("consumption.read"), ingredient_usage, "Stock"),
    Report("stock_differences", "Physical stock differences", "Counted against system balances, with the adjustment "
           "status of each line.", ("period", "item"), has("stock_count.read"), stock_differences, "Stock"),
    Report("meal_distribution", "Food preparation and distribution", "Dishes prepared, carried in or received, and "
           "what was distributed and remained, with headcounts.", ("period", "meal_session"), has("meal.read"),
           meal_distribution, "Meals"),
    Report("leftovers", "Leftovers", "Leftover quantities by classification.", ("period", "meal_session"),
           has("meal.read"), leftovers, "Meals"),
    Report("planned_vs_actual", "Planned versus actual", "Approved plan quantities against actual net usage.",
           ("period", "meal_session", "item"), planner, planned_vs_actual, "Meals"),
)}

# Reports that have their own screens (kept, listed in the catalogue).
LINKED = (
    {"key": "purchases_vs_payments", "title": "Purchases vs payments", "group": "Purchasing",
     "description": "Purchase expenditure and supplier payments for a period, reported separately.",
     "href": "/dashboard/purchase-payment-report", "code": "purchase_bill.read"},
    {"key": "outsourced_food", "title": "Outsourced food", "group": "Meals",
     "description": "Ordered, received, rejected and accepted outsourced food, distribution and leftovers.",
     "href": "/dashboard/outsourced-food/report", "code": "outsourced_food.read"},
    {"key": "spending_analysis", "title": "Spending analysis", "group": "Purchasing",
     "description": "Dashboard comparisons: expenditure, categories, price increases, drill-down to bills.",
     "href": "/dashboard/analytics", "code": "purchase_bill.read"},
)


def catalogue(db: Session, user: User) -> list[dict]:
    out = [{"key": r.key, "title": r.title, "description": r.description, "group": r.group, "filters": list(r.filters),
            "period_required": r.period_required, "href": None} for r in REPORTS.values() if r.allowed(db, user)]
    out += [{"key": l["key"], "title": l["title"], "description": l["description"], "group": l["group"], "filters": [],
             "period_required": False, "href": l["href"]} for l in LINKED if user_has_permission(db, user, l["code"])]
    return out


def build(db: Session, user: User, key: str, p: Params) -> dict:
    report = REPORTS.get(key)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    if not report.allowed(db, user):
        raise HTTPException(status_code=403, detail="This report needs a permission you do not have.")
    if report.period_required or "period" in report.filters:
        if not (p.date_from and p.date_to):
            raise HTTPException(status_code=422, detail="Choose the reporting period (from and to dates).")
        if p.date_from > p.date_to:
            raise HTTPException(status_code=422, detail="The start date cannot be after the end date.")
        if (p.date_to - p.date_from).days >= MAX_DAYS:
            raise HTTPException(status_code=422, detail=f"Choose a period of at most {MAX_DAYS} days.")
    lk = Lookups(db, user.campus_id)
    for value, mapping, label in ((p.supplier_id, lk.suppliers, "Supplier"), (p.category_id, lk.categories, "Category"),
                                  (p.item_id, lk.items, "Item"), (p.meal_session_id, lk.sessions, "Meal session")):
        if value and value not in mapping:
            raise HTTPException(status_code=404, detail=f"{label} not found")
    body = report.build(db, user, p, lk)
    filters = []
    if p.supplier_id:
        filters.append({"label": "Supplier", "value": lk.suppliers[p.supplier_id]})
    if p.category_id:
        filters.append({"label": "Category", "value": lk.categories[p.category_id]})
    if p.item_id:
        filters.append({"label": "Item", "value": lk.item(p.item_id)})
    if p.meal_session_id:
        filters.append({"label": "Meal session", "value": lk.sessions[p.meal_session_id]})
    if "compare" in report.filters:
        filters.append({"label": "Comparison", "value": {"elapsed": "Same elapsed days, previous month",
                                                         "full": "Full months", "previous": "Previous equal period"}
                        .get(p.compare, p.compare)})
    campus = db.query(Campus.name).filter(Campus.id == user.campus_id).scalar()
    rows = body["rows"]
    return {
        "key": key, "title": report.title, "description": report.description, "group": report.group,
        "campus": {"id": user.campus_id, "name": campus},
        "period": ({"date_from": p.date_from.isoformat(), "date_to": p.date_to.isoformat()}
                   if p.date_from and p.date_to and "period" in report.filters else None),
        "as_of": None if "period" in report.filters else campus_today().isoformat(),
        "filters": filters, "columns": body["columns"],
        "rows": [{k: v for k, v in r.items()} for r in rows], "row_count": len(rows),
        "totals": body["totals"], "notes": body.get("notes", []), "comparison": body.get("comparison"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
