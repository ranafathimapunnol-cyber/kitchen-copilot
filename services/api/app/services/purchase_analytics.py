"""Purchase analytics (Stage 9: DASH01–DASH05, AT03, AT07).

Source data: supplier bills (`purchases`) and their item lines
(`purchase_items`), dated by the bill date, limited to one campus.

Rules (PROPOSAL.md §5.6):
- Like-for-like (DASH03): an item is compared with itself only; every line
  quantity is converted to the item's standard unit through an explicit
  conversion record. A line without such a conversion is excluded and
  counted separately ("incompatible").
- Weighted average unit price = total comparable line value ÷ total
  comparable standard quantity (DASH02).
- Percentage change = ((current − previous) ÷ previous) × 100; when the
  previous value is zero or missing the result is None and is shown as
  "Not comparable" (DASH02, AT07).
- Price and quantity effects (DASH02): for an item bought in both periods,
  expenditure change = price effect + quantity effect, with
  price effect = (P1 − P0) × Q1 and quantity effect = (Q1 − Q0) × P0.
  An item bought in only one period has no price effect; its whole change
  is a quantity effect.
- Bill-level discounts and extra charges are not allocated to lines (no
  approved allocation rule, client question Q5): item and category figures
  use line totals; total expenditure uses bill grand totals; the difference
  is shown separately (DASH03).
- Incomplete months (DASH04): the default comparison uses the same elapsed
  days of the previous month; a full-month comparison is available.
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.master_data import Category, Item, Supplier, Unit, UnitConversion
from app.models.purchases import Purchase, PurchaseItem

ZERO = Decimal("0")
MONEY = Decimal("0.01")
PRICE = Decimal("0.0001")
QTY = Decimal("0.001")
COMPARE_MODES = ("elapsed", "full", "previous")


def money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)


def money_text(value) -> str:
    return format(money(value), "f")


def qty_text(value) -> str:
    return format(Decimal(str(value or 0)).quantize(QTY, rounding=ROUND_HALF_UP), "f")


def price_text(value) -> str | None:
    if value is None:
        return None
    return format(Decimal(str(value)).quantize(PRICE, rounding=ROUND_HALF_UP), "f")


def percent_change(current, previous) -> str | None:
    """((current − previous) ÷ previous) × 100 to one decimal; None when the
    previous value is zero or missing ("Not comparable")."""
    if previous is None or current is None:
        return None
    previous = Decimal(str(previous))
    if previous == 0:
        return None
    change = (Decimal(str(current)) - previous) / previous * 100
    return format(change.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP), "f")


# ============================================================
# PERIODS
# ============================================================

def month_end(day: date) -> date:
    return day.replace(day=calendar.monthrange(day.year, day.month)[1])


def shift_month(day: date, months: int) -> date:
    """The same day number `months` months away, clamped to that month's end."""
    index = day.year * 12 + (day.month - 1) + months
    year, month = divmod(index, 12)
    last = calendar.monthrange(year, month + 1)[1]
    return date(year, month + 1, min(day.day, last))


def comparison_periods(date_from: date, date_to: date, mode: str) -> dict:
    """Current and comparison periods.

    - elapsed: the same calendar days one month earlier (1–24 November
      against 1–24 October); for an incomplete month this compares equal
      elapsed-day ranges (DASH04). A period touching n months is compared
      with the same days n months earlier.
    - full: whole months — the months covering the period against the same
      number of whole months immediately before.
    - previous: the period of equal length immediately before.
    """
    if mode not in COMPARE_MODES:
        raise ValueError(mode)
    if mode == "elapsed":
        # Shift back by the number of months the period touches, so a
        # period longer than one month never overlaps its comparison.
        months = (date_to.year - date_from.year) * 12 + date_to.month - date_from.month + 1
        prev_from, prev_to = shift_month(date_from, -months), shift_month(date_to, -months)
        if date_to == month_end(date_to) and date_from.day == 1:
            prev_to = month_end(prev_to)
        cur_from, cur_to = date_from, date_to
    elif mode == "full":
        cur_from, cur_to = date_from.replace(day=1), month_end(date_to)
        months = (cur_to.year - cur_from.year) * 12 + cur_to.month - cur_from.month + 1
        prev_from = shift_month(cur_from, -months)
        prev_to = month_end(shift_month(cur_from, -1))
    else:
        cur_from, cur_to = date_from, date_to
        length = (date_to - date_from).days + 1
        prev_to = date_from - timedelta(days=1)
        prev_from = prev_to - timedelta(days=length - 1)
    return {"current": {"date_from": cur_from.isoformat(), "date_to": cur_to.isoformat(),
                        "days": (cur_to - cur_from).days + 1},
            "previous": {"date_from": prev_from.isoformat(), "date_to": prev_to.isoformat(),
                         "days": (prev_to - prev_from).days + 1},
            "mode": mode}


# ============================================================
# LINES
# ============================================================

class Conversions:
    """Explicit conversion records of one campus (either direction)."""

    def __init__(self, db: Session, campus_id: int):
        self.pairs: dict[tuple[int, int], Decimal] = {}
        for row in db.query(UnitConversion).filter(UnitConversion.campus_id == campus_id):
            factor = Decimal(str(row.factor))
            self.pairs[(row.from_unit_id, row.to_unit_id)] = factor
            if factor:
                self.pairs.setdefault((row.to_unit_id, row.from_unit_id), Decimal(1) / factor)

    def factor(self, from_id: int, to_id: int) -> Decimal | None:
        if from_id == to_id:
            return Decimal(1)
        return self.pairs.get((from_id, to_id))


def purchase_lines(db: Session, campus_id: int, date_from: date, date_to: date, *, supplier_id: int | None = None,
                   category_id: int | None = None, item_id: int | None = None) -> list[dict]:
    """Bill lines dated in the period, with the quantity in the item's
    standard unit (None when no explicit conversion exists)."""
    query = (db.query(PurchaseItem, Purchase, Item)
             .join(Purchase, Purchase.id == PurchaseItem.purchase_id)
             .join(Item, Item.id == PurchaseItem.item_id)
             .filter(Purchase.campus_id == campus_id, PurchaseItem.campus_id == campus_id, Item.campus_id == campus_id,
                     Purchase.purchase_date >= date_from, Purchase.purchase_date <= date_to))
    if supplier_id:
        query = query.filter(Purchase.supplier_id == supplier_id)
    if category_id:
        query = query.filter(Item.category_id == category_id)
    if item_id:
        query = query.filter(PurchaseItem.item_id == item_id)
    rows = query.order_by(Purchase.purchase_date, Purchase.id, PurchaseItem.id).all()
    conversions = Conversions(db, campus_id)
    out = []
    for line, bill, item in rows:
        factor = conversions.factor(line.unit_id, item.standard_unit_id)
        quantity = Decimal(str(line.quantity))
        out.append({
            "purchase_item_id": line.id, "purchase_id": bill.id, "invoice_number": bill.invoice_number,
            "purchase_date": bill.purchase_date, "supplier_id": bill.supplier_id, "item_id": item.id,
            "category_id": item.category_id, "quantity": quantity, "unit_id": line.unit_id,
            "unit_rate": Decimal(str(line.unit_rate)), "line_total": money(line.line_total),
            "standard_unit_id": item.standard_unit_id,
            "standard_quantity": (quantity * factor) if factor is not None else None,
        })
    return out


def bill_totals(db: Session, campus_id: int, date_from: date, date_to: date, supplier_id: int | None = None) -> dict:
    """Bill-level totals for the period: count, line subtotal, discounts,
    extra charges and grand total (purchase expenditure)."""
    query = db.query(func.count(Purchase.id), func.coalesce(func.sum(Purchase.subtotal), 0),
                     func.coalesce(func.sum(Purchase.discount), 0), func.coalesce(func.sum(Purchase.extra_charges), 0),
                     func.coalesce(func.sum(Purchase.grand_total), 0)).filter(
        Purchase.campus_id == campus_id, Purchase.purchase_date >= date_from, Purchase.purchase_date <= date_to)
    if supplier_id:
        query = query.filter(Purchase.supplier_id == supplier_id)
    count, subtotal, discount, extra, grand = query.one()
    return {"bill_count": int(count), "subtotal": money(subtotal), "discount": money(discount),
            "extra_charges": money(extra), "grand_total": money(grand)}


def summarise_items(lines: list[dict]) -> dict[int, dict]:
    """Per item: comparable standard quantity and value, weighted average
    price, and the lines excluded for lack of a conversion."""
    items: dict[int, dict] = {}
    for line in lines:
        entry = items.setdefault(line["item_id"], {"quantity": ZERO, "value": ZERO, "lines": 0,
                                                   "excluded_lines": 0, "excluded_value": ZERO,
                                                   "bills": set(), "days": set()})
        entry["lines"] += 1
        entry["bills"].add(line["purchase_id"])
        entry["days"].add(line["purchase_date"])
        if line["standard_quantity"] is None:
            entry["excluded_lines"] += 1
            entry["excluded_value"] += line["line_total"]
        else:
            entry["quantity"] += line["standard_quantity"]
            entry["value"] += line["line_total"]
    for entry in items.values():
        entry["price"] = (entry["value"] / entry["quantity"]) if entry["quantity"] > 0 else None
    return items


def compare_items(current: dict[int, dict], previous: dict[int, dict]) -> list[dict]:
    """Per item, the two periods side by side and the price / quantity
    effects (comparable standard-unit figures only)."""
    rows = []
    for item_id in sorted(set(current) | set(previous)):
        c, p = current.get(item_id), previous.get(item_id)
        q1, e1, p1 = (c["quantity"], c["value"], c["price"]) if c else (ZERO, ZERO, None)
        q0, e0, p0 = (p["quantity"], p["value"], p["price"]) if p else (ZERO, ZERO, None)
        if p1 is not None and p0 is not None:
            status = "COMPARABLE"
            price_effect = (p1 - p0) * q1
            quantity_effect = (q1 - q0) * p0
        elif p1 is not None:
            status, price_effect, quantity_effect = "NEW", None, e1
        elif p0 is not None:
            status, price_effect, quantity_effect = "NOT_BOUGHT_NOW", None, -e0
        else:
            status, price_effect, quantity_effect = "INCOMPATIBLE", None, None
        rows.append({
            "item_id": item_id, "status": status,
            "previous_quantity": qty_text(q0), "current_quantity": qty_text(q1),
            "quantity_change": qty_text(q1 - q0), "quantity_change_percent": percent_change(q1, q0 if p else None),
            "previous_price": price_text(p0), "current_price": price_text(p1),
            "price_change": price_text(p1 - p0) if p1 is not None and p0 is not None else None,
            "price_change_percent": percent_change(p1, p0) if p1 is not None else None,
            "previous_value": money_text(e0), "current_value": money_text(e1),
            "value_change": money_text(e1 - e0), "value_change_percent": percent_change(e1, e0 if p else None),
            "price_effect": money_text(price_effect) if price_effect is not None else None,
            "quantity_effect": money_text(quantity_effect) if quantity_effect is not None else None,
            "excluded_lines": (c or {}).get("excluded_lines", 0) + (p or {}).get("excluded_lines", 0),
        })
    return rows


def monthly_series(db: Session, campus_id: int, end: date, months: int = 12, supplier_id: int | None = None,
                   category_id: int | None = None, item_id: int | None = None) -> list[dict]:
    """Per month (oldest first): expenditure, and — when an item is chosen —
    its comparable standard quantity and weighted average price."""
    start = shift_month(end.replace(day=1), -(months - 1))
    out = []
    if category_id or item_id:
        lines = purchase_lines(db, campus_id, start, month_end(end), supplier_id=supplier_id,
                               category_id=category_id, item_id=item_id)
        by_month: dict[str, list[dict]] = defaultdict(list)
        for line in lines:
            by_month[line["purchase_date"].strftime("%Y-%m")].append(line)
    for index in range(months):
        first = shift_month(start, index)
        key = first.strftime("%Y-%m")
        if category_id or item_id:
            rows = by_month.get(key, [])
            value = sum((l["line_total"] for l in rows), ZERO)
            comparable = [l for l in rows if l["standard_quantity"] is not None]
            quantity = sum((l["standard_quantity"] for l in comparable), ZERO)
            comparable_value = sum((l["line_total"] for l in comparable), ZERO)
            entry = {"month": key, "expenditure": money_text(value), "basis": "line totals",
                     "quantity": qty_text(quantity) if item_id else None,
                     "average_price": price_text(comparable_value / quantity) if item_id and quantity > 0 else None}
        else:
            totals = bill_totals(db, campus_id, first, month_end(first), supplier_id)
            entry = {"month": key, "expenditure": money_text(totals["grand_total"]), "basis": "bill totals",
                     "quantity": None, "average_price": None}
        out.append(entry)
    return out


def names(db: Session, campus_id: int) -> dict:
    units = {u.id: u.symbol for u in db.query(Unit).filter(Unit.campus_id == campus_id)}
    items = {i.id: i for i in db.query(Item).filter(Item.campus_id == campus_id)}
    categories = dict(db.query(Category.id, Category.name).filter(Category.campus_id == campus_id))
    suppliers = dict(db.query(Supplier.id, Supplier.name).filter(Supplier.campus_id == campus_id))
    return {"units": units, "items": items, "categories": categories, "suppliers": suppliers}
