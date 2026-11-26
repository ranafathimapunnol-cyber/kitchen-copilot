"""Spending analysis (Stage 9: DASH01–DASH05, AT07).

Every endpoint needs `purchase_bill.read` (supplier bills and their
amounts: ADMIN, KITCHEN_MANAGER, and STAFF only through an explicit grant)
and is limited to the user's campus. Calculations: see
app/services/purchase_analytics.py.
"""

from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.dependencies import require_permission
from app.core.clock import campus_today
from app.db.session import get_db
from app.models.master_data import Category, Item, Supplier, Unit
from app.models.purchases import Purchase, PurchaseAttachment
from app.models.user import User
from app.services import purchase_analytics as pa

router = APIRouter(prefix="/api/analytics", tags=["Spending analysis"])
MAX_DAYS = 366
TOP = 5


def check_period(date_from: date, date_to: date) -> None:
    if date_from > date_to:
        raise HTTPException(status_code=422, detail="The start date cannot be after the end date.")
    if (date_to - date_from).days >= MAX_DAYS:
        raise HTTPException(status_code=422, detail=f"Choose a period of at most {MAX_DAYS} days.")


def check_filters(db: Session, user: User, supplier_id, category_id, item_id) -> dict:
    found = {}
    for key, model, value in (("supplier", Supplier, supplier_id), ("category", Category, category_id),
                              ("item", Item, item_id)):
        if value:
            row = db.query(model).filter(model.id == value, model.campus_id == user.campus_id).first()
            if not row:
                raise HTTPException(status_code=404, detail=f"{key.title()} not found")
            found[key] = row.name
    return found


@router.get("/options")
def analytics_options(db: Session = Depends(get_db), user: User = Depends(require_permission("purchase_bill.read"))):
    campus_id = user.campus_id
    units = dict(db.query(Unit.id, Unit.symbol).filter(Unit.campus_id == campus_id))
    first_bill = db.query(func.min(Purchase.purchase_date)).filter(Purchase.campus_id == campus_id).scalar()
    return {
        "today": campus_today().isoformat(),
        "first_bill_date": first_bill.isoformat() if first_bill else None,
        "categories": [{"id": c.id, "name": c.name} for c in db.query(Category).filter(
            Category.campus_id == campus_id).order_by(func.lower(Category.name))],
        "items": [{"id": i.id, "name": i.name, "category_id": i.category_id,
                   "standard_unit_symbol": units.get(i.standard_unit_id)}
                  for i in db.query(Item).filter(Item.campus_id == campus_id).order_by(func.lower(Item.name))],
        "suppliers": [{"id": s.id, "name": s.name} for s in db.query(Supplier).filter(
            Supplier.campus_id == campus_id).order_by(func.lower(Supplier.name))],
    }


def build_spending(db: Session, user: User, date_from: date, date_to: date, compare: str,
                   supplier_id: int | None, category_id: int | None, item_id: int | None) -> dict:
    check_period(date_from, date_to)
    campus_id = user.campus_id
    filters = check_filters(db, user, supplier_id, category_id, item_id)
    periods = pa.comparison_periods(date_from, date_to, compare)
    cur, prev = periods["current"], periods["previous"]
    cur_from, cur_to = date.fromisoformat(cur["date_from"]), date.fromisoformat(cur["date_to"])
    prev_from, prev_to = date.fromisoformat(prev["date_from"]), date.fromisoformat(prev["date_to"])
    kwargs = {"supplier_id": supplier_id, "category_id": category_id, "item_id": item_id}
    cur_lines = pa.purchase_lines(db, campus_id, cur_from, cur_to, **kwargs)
    prev_lines = pa.purchase_lines(db, campus_id, prev_from, prev_to, **kwargs)
    n = pa.names(db, campus_id)
    item_level = bool(category_id or item_id)

    # Total expenditure: bill grand totals, unless a category or item is
    # chosen (bill-level charges belong to no category or item; DASH03).
    if item_level:
        cur_total = sum((l["line_total"] for l in cur_lines), pa.ZERO)
        prev_total = sum((l["line_total"] for l in prev_lines), pa.ZERO)
        bills_cur = bills_prev = None
    else:
        bills_cur = pa.bill_totals(db, campus_id, cur_from, cur_to, supplier_id)
        bills_prev = pa.bill_totals(db, campus_id, prev_from, prev_to, supplier_id)
        cur_total, prev_total = bills_cur["grand_total"], bills_prev["grand_total"]

    def bill_part(b):
        return None if b is None else {k: (pa.money_text(v) if isinstance(v, Decimal) else v) for k, v in b.items()}

    # Categories (line totals).
    cats: dict[int, dict] = {}
    for period, lines in (("current", cur_lines), ("previous", prev_lines)):
        for line in lines:
            entry = cats.setdefault(line["category_id"], {"current": pa.ZERO, "previous": pa.ZERO})
            entry[period] += line["line_total"]
    categories = sorted(({
        "category_id": cid, "category_name": n["categories"].get(cid),
        "current_value": pa.money_text(v["current"]), "previous_value": pa.money_text(v["previous"]),
        "value_change": pa.money_text(v["current"] - v["previous"]),
        "value_change_percent": pa.percent_change(v["current"], v["previous"]),
    } for cid, v in cats.items()), key=lambda r: Decimal(r["current_value"]), reverse=True)

    # Items side by side with price and quantity effects.
    cur_items, prev_items = pa.summarise_items(cur_lines), pa.summarise_items(prev_lines)
    rows = pa.compare_items(cur_items, prev_items)
    for row in rows:
        item = n["items"].get(row["item_id"])
        row["item_name"] = item.name if item else None
        row["category_name"] = n["categories"].get(item.category_id) if item else None
        row["standard_unit_symbol"] = n["units"].get(item.standard_unit_id) if item else None
    rows.sort(key=lambda r: abs(Decimal(r["value_change"])), reverse=True)
    increases = sorted((r for r in rows if r["status"] == "COMPARABLE" and r["price_change_percent"] is not None
                        and Decimal(r["price_change_percent"]) > 0),
                       key=lambda r: Decimal(r["price_change_percent"]), reverse=True)[:TOP]
    effects = {"price": sum((Decimal(r["price_effect"]) for r in rows if r["price_effect"]), pa.ZERO),
               "quantity": sum((Decimal(r["quantity_effect"]) for r in rows if r["quantity_effect"]), pa.ZERO)}
    excluded = sum(r["excluded_lines"] for r in rows)
    line_change = (sum((l["line_total"] for l in cur_lines), pa.ZERO) - sum((l["line_total"] for l in prev_lines), pa.ZERO))
    incompatible_value = sum((Decimal(r["current_value"]) - Decimal(r["previous_value"]) for r in rows
                              if r["status"] == "INCOMPATIBLE"), pa.ZERO)
    return {
        "periods": periods,
        "filters": {"supplier_id": supplier_id, "supplier_name": filters.get("supplier"),
                    "category_id": category_id, "category_name": filters.get("category"),
                    "item_id": item_id, "item_name": filters.get("item")},
        "totals": {
            "basis": "line totals of the chosen category or item" if item_level else "bill grand totals",
            "current": pa.money_text(cur_total), "previous": pa.money_text(prev_total),
            "change": pa.money_text(cur_total - prev_total),
            "change_percent": pa.percent_change(cur_total, prev_total),
            "current_bills": bill_part(bills_cur), "previous_bills": bill_part(bills_prev),
            "current_lines": len(cur_lines), "previous_lines": len(prev_lines),
            "line_change": pa.money_text(line_change),
            "price_effect": pa.money_text(effects["price"]), "quantity_effect": pa.money_text(effects["quantity"]),
            "excluded_lines": excluded,
            "unexplained_by_items": pa.money_text(line_change - effects["price"] - effects["quantity"]),
        },
        "categories": categories,
        "items": rows,
        "top_price_increases": increases,
        "monthly": pa.monthly_series(db, campus_id, cur_to, 12, **kwargs),
        "notes": [
            "Weighted average unit price = total comparable item purchase value ÷ total comparable quantity, "
            "in the item's standard unit (explicit conversions only; other lines are excluded and counted).",
            "Percentage change = ((current − previous) ÷ previous) × 100; shown as “Not comparable” when the "
            "previous value is zero or missing.",
            "Price effect = (current price − previous price) × current quantity; quantity effect = "
            "(current quantity − previous quantity) × previous price; together they make up each item's change.",
            "Bill-level discounts and extra charges are not allocated to items or categories (no approved "
            "allocation rule, client question Q5); they appear only in the bill totals.",
            "Supplier returns and credits are not recorded yet (client question Q6).",
        ],
    }


@router.get("/spending")
def spending_analysis(
    date_from: date = Query(...), date_to: date = Query(...),
    compare: Literal["elapsed", "full", "previous"] = Query(default="elapsed"),
    supplier_id: int | None = Query(default=None, gt=0), category_id: int | None = Query(default=None, gt=0),
    item_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db), user: User = Depends(require_permission("purchase_bill.read")),
):
    return build_spending(db, user, date_from, date_to, compare, supplier_id, category_id, item_id)


@router.get("/transactions")
def spending_transactions(
    date_from: date = Query(...), date_to: date = Query(...),
    supplier_id: int | None = Query(default=None, gt=0), category_id: int | None = Query(default=None, gt=0),
    item_id: int | None = Query(default=None, gt=0),
    page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db), user: User = Depends(require_permission("purchase_bill.read")),
):
    """DASH05: the bill lines behind a figure, with the bill's attachment
    count; the bill itself opens through the supplier-bill screens (their
    own permission checks apply)."""
    check_period(date_from, date_to)
    check_filters(db, user, supplier_id, category_id, item_id)
    lines = pa.purchase_lines(db, user.campus_id, date_from, date_to, supplier_id=supplier_id,
                              category_id=category_id, item_id=item_id)
    n = pa.names(db, user.campus_id)
    bill_ids = {l["purchase_id"] for l in lines}
    attachments = dict(db.query(PurchaseAttachment.purchase_id, func.count(PurchaseAttachment.id)).filter(
        PurchaseAttachment.campus_id == user.campus_id, PurchaseAttachment.purchase_id.in_(bill_ids or {0}))
        .group_by(PurchaseAttachment.purchase_id))
    total = len(lines)
    start = (page - 1) * page_size
    return {
        "items": [{
            "purchase_item_id": l["purchase_item_id"], "purchase_id": l["purchase_id"],
            "invoice_number": l["invoice_number"], "purchase_date": l["purchase_date"].isoformat(),
            "supplier_name": n["suppliers"].get(l["supplier_id"]),
            "item_name": n["items"][l["item_id"]].name if l["item_id"] in n["items"] else None,
            "category_name": n["categories"].get(l["category_id"]),
            "quantity": pa.qty_text(l["quantity"]), "unit_symbol": n["units"].get(l["unit_id"]),
            "standard_quantity": pa.qty_text(l["standard_quantity"]) if l["standard_quantity"] is not None else None,
            "standard_unit_symbol": n["units"].get(l["standard_unit_id"]),
            "unit_rate": pa.price_text(l["unit_rate"]), "line_total": pa.money_text(l["line_total"]),
            "attachment_count": attachments.get(l["purchase_id"], 0),
        } for l in lines[start:start + page_size]],
        "total": total, "page": page, "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
        "line_total": pa.money_text(sum((l["line_total"] for l in lines), pa.ZERO)),
    }
