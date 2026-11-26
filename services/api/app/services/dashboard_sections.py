"""Home dashboard sections added in Stage 9 (each shown only with its own
read permission; every query limited to one campus).

Headcount comes from meal records (expected and actual people per meal),
the single source of headcounts since Stage 5; the older
`daily_headcounts` table has no entry screen and is no longer read.
Display rule (not a client decision): a day's headcount is the largest
meal of the day — actual people served where recorded, otherwise
expected — because the same people eat several meals a day.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.master_data import Item, MealSession, Supplier, Unit
from app.models.meals import MealDish, MealRecord
from app.models.purchases import StockMovement
from app.models.stock import KitchenIssue, StockAdjustment
from app.services import purchase_analytics as pa

ZERO = Decimal("0")


def total(record: MealRecord, prefix: str) -> int | None:
    values = [getattr(record, f"{prefix}_{g}") for g in ("students", "staff", "guests")]
    return None if any(v is None for v in values) else sum(values)


def headcount(db: Session, campus_id: int, today: date) -> dict:
    week_start = today - timedelta(days=6)
    records = (db.query(MealRecord).filter(MealRecord.campus_id == campus_id, MealRecord.status != "CANCELLED",
                                           MealRecord.meal_date >= week_start, MealRecord.meal_date <= today + timedelta(days=1))
               .order_by(MealRecord.meal_date, MealRecord.meal_session_id).all())
    sessions = dict(db.query(MealSession.id, MealSession.name).filter(MealSession.campus_id == campus_id))
    by_day: dict[date, list[MealRecord]] = {}
    for r in records:
        by_day.setdefault(r.meal_date, []).append(r)

    def day_value(rows):
        actual = [total(r, "actual") for r in rows if total(r, "actual") is not None]
        expected = [total(r, "expected") for r in rows]
        return (max(actual) if actual else None), (max(expected) if expected else None)

    today_rows = by_day.get(today, [])
    actual_today, expected_today = day_value(today_rows)
    trend = []
    for day in sorted(d for d in by_day if week_start <= d <= today):
        actual, expected = day_value(by_day[day])
        trend.append({"date": day, "count": actual if actual is not None else expected, "actual": actual,
                      "expected": expected})
    return {
        "today": actual_today if actual_today is not None else expected_today,
        "today_basis": None if not today_rows else ("actual" if actual_today is not None else "expected"),
        "source": "meal_records",
        "sessions": [{"meal_record_id": r.id, "meal_session_name": sessions.get(r.meal_session_id), "status": r.status,
                      "expected": total(r, "expected"), "actual": total(r, "actual")} for r in today_rows],
        "tomorrow": [{"meal_record_id": r.id, "meal_session_name": sessions.get(r.meal_session_id),
                      "expected": total(r, "expected")} for r in by_day.get(today + timedelta(days=1), [])],
        "trend": trend,
    }


def meals(db: Session, campus_id: int, today: date) -> dict:
    sessions = dict(db.query(MealSession.id, MealSession.name).filter(MealSession.campus_id == campus_id))
    base = db.query(MealRecord).filter(MealRecord.campus_id == campus_id)
    awaiting = (base.filter(MealRecord.status == "OPEN", MealRecord.meal_date < today)
                .order_by(MealRecord.meal_date.desc()).limit(5).all())
    week = base.filter(MealRecord.meal_date >= today - timedelta(days=6), MealRecord.meal_date <= today)
    counts = dict(week.with_entities(MealRecord.status, func.count(MealRecord.id)).group_by(MealRecord.status))
    today_ids = [r.id for r in base.filter(MealRecord.meal_date == today, MealRecord.status != "CANCELLED")]
    dish_count = (db.query(func.count(MealDish.id)).filter(MealDish.meal_record_id.in_(today_ids or [0])).scalar() or 0)
    return {
        "open_count": base.filter(MealRecord.status == "OPEN").count(),
        "awaiting_close_count": base.filter(MealRecord.status == "OPEN", MealRecord.meal_date < today).count(),
        "awaiting_close": [{"id": r.id, "meal_date": r.meal_date, "meal_session_name": sessions.get(r.meal_session_id)}
                           for r in awaiting],
        "week_status_counts": {s: counts.get(s, 0) for s in ("OPEN", "CLOSED", "CANCELLED")},
        "dishes_today": int(dish_count),
    }


def planning(db: Session, campus_id: int, today: date) -> dict:
    from app.models.planning import MealPlan, PortionStandard

    sessions = dict(db.query(MealSession.id, MealSession.name).filter(MealSession.campus_id == campus_id))
    upcoming = (db.query(MealPlan).filter(MealPlan.campus_id == campus_id, MealPlan.status != "CANCELLED",
                                          MealPlan.plan_date >= today, MealPlan.plan_date <= today + timedelta(days=7))
                .order_by(MealPlan.plan_date, MealPlan.meal_session_id).limit(8).all())
    return {
        "upcoming": [{"id": p.id, "plan_number": p.plan_number, "plan_date": p.plan_date, "status": p.status,
                      "meal_session_name": sessions.get(p.meal_session_id), "expected_headcount": p.expected_headcount}
                     for p in upcoming],
        "draft_plans": db.query(func.count(MealPlan.id)).filter(MealPlan.campus_id == campus_id,
                                                                MealPlan.status == "DRAFT").scalar() or 0,
        "draft_standards": db.query(func.count(PortionStandard.id)).filter(
            PortionStandard.campus_id == campus_id, PortionStandard.status == "DRAFT").scalar() or 0,
        "approved_standards": db.query(func.count(PortionStandard.id)).filter(
            PortionStandard.campus_id == campus_id, PortionStandard.status == "APPROVED").scalar() or 0,
    }


def outsourced(db: Session, campus_id: int, today: date, costs: bool) -> dict:
    from app.api.routes.outsourced import delivery_progress, receiving_status
    from app.models.outsourced import OutsourcedDelivery, OutsourcedDeliveryLine, OutsourcedOrder, OutsourcedOrderLine

    sessions = dict(db.query(MealSession.id, MealSession.name).filter(MealSession.campus_id == campus_id))
    suppliers = dict(db.query(Supplier.id, Supplier.name).filter(Supplier.campus_id == campus_id))
    orders = (db.query(OutsourcedOrder).filter(OutsourcedOrder.campus_id == campus_id, OutsourcedOrder.status == "ORDERED",
                                               OutsourcedOrder.meal_date >= today - timedelta(days=1),
                                               OutsourcedOrder.meal_date <= today + timedelta(days=2))
              .order_by(OutsourcedOrder.meal_date, OutsourcedOrder.meal_session_id).limit(8).all())
    lines = db.query(OutsourcedOrderLine).filter(OutsourcedOrderLine.order_id.in_([o.id for o in orders] or [0])).all()
    progress = delivery_progress(db, campus_id, [l.id for l in lines])
    by_order: dict[int, list] = {}
    for l in lines:
        by_order.setdefault(l.order_id, []).append(l)
    attached = db.query(MealDish.source_delivery_line_id).filter(MealDish.source_delivery_line_id.isnot(None))
    pending_lines = (db.query(func.count(OutsourcedDeliveryLine.id))
                     .join(OutsourcedDelivery, OutsourcedDelivery.id == OutsourcedDeliveryLine.delivery_id)
                     .filter(OutsourcedDeliveryLine.campus_id == campus_id, OutsourcedDelivery.status == "CONFIRMED",
                             OutsourcedDeliveryLine.accepted_quantity > 0,
                             ~OutsourcedDeliveryLine.id.in_(attached)).scalar() or 0)
    out = {
        "orders": [{"id": o.id, "order_number": o.order_number, "meal_date": o.meal_date,
                    "meal_session_name": sessions.get(o.meal_session_id), "supplier_name": suppliers.get(o.supplier_id),
                    "receiving_status": receiving_status(o, by_order.get(o.id, []), progress)} for o in orders],
        "draft_orders": db.query(func.count(OutsourcedOrder.id)).filter(
            OutsourcedOrder.campus_id == campus_id, OutsourcedOrder.status == "DRAFT").scalar() or 0,
        "draft_deliveries": db.query(func.count(OutsourcedDelivery.id)).filter(
            OutsourcedDelivery.campus_id == campus_id, OutsourcedDelivery.status == "DRAFT").scalar() or 0,
        "waiting_for_meal_record": int(pending_lines),
    }
    if costs:
        month_start = today.replace(day=1)
        planned = (db.query(func.coalesce(func.sum(OutsourcedOrderLine.line_total), 0))
                   .join(OutsourcedOrder, OutsourcedOrder.id == OutsourcedOrderLine.order_id)
                   .filter(OutsourcedOrder.campus_id == campus_id, OutsourcedOrder.status == "ORDERED",
                           OutsourcedOrder.meal_date >= month_start, OutsourcedOrder.meal_date <= today).scalar())
        out["planned_cost_this_month"] = pa.money_text(planned)
    return out


def stock(db: Session, campus_id: int) -> dict:
    from app.api.routes.stock import balances_subquery

    balances = balances_subquery(db, campus_id)
    rows = (db.query(Item, balances.c.balance, Unit.symbol).outerjoin(balances, balances.c.item_id == Item.id)
            .outerjoin(Unit, Unit.id == Item.standard_unit_id)
            .filter(Item.campus_id == campus_id, Item.is_active.is_(True),
                    (Item.item_kind.is_(None)) | (Item.item_kind != "OUTSOURCED")).all())
    below, out_of_stock, tracked = [], 0, 0
    for item, balance, unit in rows:
        balance = Decimal(str(balance or 0))
        minimum = Decimal(str(item.minimum_stock or 0))
        tracked += 1
        if balance <= 0:
            out_of_stock += 1
        if minimum > 0 and balance < minimum:
            below.append({"item_id": item.id, "item_name": item.name, "balance": pa.qty_text(balance),
                          "minimum": pa.qty_text(minimum), "needed": pa.qty_text(minimum - balance), "unit": unit,
                          "_ratio": float(balance / minimum)})
    below.sort(key=lambda r: (r["_ratio"], r["item_name"].lower()))
    for row in below:
        row.pop("_ratio")
    last = db.query(func.max(StockMovement.effective_at)).filter(StockMovement.campus_id == campus_id).scalar()
    return {"items_tracked": tracked, "below_minimum": len(below), "out_of_stock": out_of_stock,
            "lowest": below[:6], "last_movement_at": last}


def kitchen(db: Session, campus_id: int, today: date) -> dict:
    base = db.query(KitchenIssue).filter(KitchenIssue.campus_id == campus_id)
    return {"issues_today": base.filter(KitchenIssue.issue_date == today, KitchenIssue.status != "CANCELLED").count(),
            "draft_issues": base.filter(KitchenIssue.status == "DRAFT").count()}


def counts(db: Session, campus_id: int) -> dict:
    return {"pending_adjustments": db.query(func.count(StockAdjustment.id)).filter(
        StockAdjustment.campus_id == campus_id, StockAdjustment.status == "PENDING").scalar() or 0}


def spending(db: Session, campus_id: int, today: date) -> dict:
    """Month to date against the same elapsed days of last month (DASH04)."""
    periods = pa.comparison_periods(today.replace(day=1), today, "elapsed")
    cur, prev = periods["current"], periods["previous"]
    current = pa.bill_totals(db, campus_id, date.fromisoformat(cur["date_from"]), date.fromisoformat(cur["date_to"]))
    previous = pa.bill_totals(db, campus_id, date.fromisoformat(prev["date_from"]), date.fromisoformat(prev["date_to"]))
    lines = pa.purchase_lines(db, campus_id, date.fromisoformat(cur["date_from"]), date.fromisoformat(cur["date_to"]))
    categories: dict[int, Decimal] = {}
    for line in lines:
        categories[line["category_id"]] = categories.get(line["category_id"], ZERO) + line["line_total"]
    names = pa.names(db, campus_id)["categories"]
    top = sorted(categories.items(), key=lambda kv: kv[1], reverse=True)[:5]
    return {"periods": periods, "current": pa.money_text(current["grand_total"]),
            "previous": pa.money_text(previous["grand_total"]),
            "change": pa.money_text(current["grand_total"] - previous["grand_total"]),
            "change_percent": pa.percent_change(current["grand_total"], previous["grand_total"]),
            "bills": current["bill_count"],
            "top_categories": [{"category_id": cid, "category_name": names.get(cid), "value": pa.money_text(v)}
                               for cid, v in top]}
