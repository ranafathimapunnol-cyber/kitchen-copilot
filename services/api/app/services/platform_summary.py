"""Organisation-level figures for the platform (Stage 11).

The platform sees campus *aggregates* only (counts and totals) computed by
the same functions the campus dashboard uses; it never lists a campus's
bills, stock lines, meals or people's activity. Every figure is read from
the database at request time.
"""

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from app.api.routes.supplier_payments import balance_totals, supplier_balance_subquery
from app.models.audit_log import AuditLog
from app.models.campus import Campus
from app.models.platform import CampusIntegration
from app.models.purchases import Purchase
from app.models.user import User, UserRole
from app.services import dashboard_sections as sections
from app.services import erp_headcount
from app.services.purchase_analytics import money_text

CAMPUS_ROLES = (UserRole.ADMIN, UserRole.KITCHEN_MANAGER, UserRole.STAFF)


def users_by_campus(db: Session, campus_ids: list[int]) -> dict[int, dict]:
    out = {cid: {"total": 0, "active": 0, "ADMIN": 0, "KITCHEN_MANAGER": 0, "STAFF": 0} for cid in campus_ids}
    rows = (db.query(User.campus_id, User.role, User.is_active, func.count(User.id))
            .filter(User.campus_id.in_(campus_ids or [0])).group_by(User.campus_id, User.role, User.is_active).all())
    for cid, role, active, n in rows:
        entry = out[cid]
        entry["total"] += n
        if active:
            entry["active"] += n
            entry[role.value] = entry.get(role.value, 0) + n
    return out


def purchases_by_campus(db: Session, campus_ids: list[int], date_from: date, date_to: date) -> dict[int, dict]:
    rows = (db.query(Purchase.campus_id, func.count(Purchase.id), func.coalesce(func.sum(Purchase.grand_total), 0))
            .filter(Purchase.campus_id.in_(campus_ids or [0]), Purchase.purchase_date >= date_from,
                    Purchase.purchase_date <= date_to)
            .group_by(Purchase.campus_id).all())
    found = {cid: {"bill_count": int(n), "total": money_text(Decimal(total))} for cid, n, total in rows}
    return {cid: found.get(cid, {"bill_count": 0, "total": "0.00"}) for cid in campus_ids}


def last_activity(db: Session, campus_ids: list[int]) -> dict[int, datetime | None]:
    rows = (db.query(AuditLog.campus_id, func.max(AuditLog.created_at))
            .filter(AuditLog.campus_id.in_(campus_ids or [0])).group_by(AuditLog.campus_id).all())
    return dict(rows)


def integrations(db: Session, campus_ids: list[int]) -> dict[int, dict]:
    rows = {i.campus_id: i for i in db.query(CampusIntegration).filter(
        CampusIntegration.campus_id.in_(campus_ids or [0]), CampusIntegration.kind == erp_headcount.KIND)}
    return {cid: erp_headcount.status_of(rows.get(cid)) for cid in campus_ids}


def operations(db: Session, campus_id: int, today: date) -> dict:
    """Aggregates from the campus dashboard's own section functions."""
    stock = sections.stock(db, campus_id)
    meals = sections.meals(db, campus_id, today)
    planning = sections.planning(db, campus_id, today)
    payables = balance_totals(db, supplier_balance_subquery(db, campus_id))
    return {
        "stock": {k: stock[k] for k in ("items_tracked", "below_minimum", "out_of_stock")},
        "pending_adjustments": sections.counts(db, campus_id)["pending_adjustments"],
        "meals_awaiting_close": meals["awaiting_close_count"],
        "open_meal_records": meals["open_count"],
        "draft_plans": planning["draft_plans"],
        "outstanding_payables": payables["outstanding"],
        "open_bills": payables["open_bill_count"],
    }


def campus_rows(db: Session, campuses: list[Campus], date_from: date, date_to: date, today: date,
                with_operations: bool = True) -> list[dict]:
    ids = [c.id for c in campuses]
    users = users_by_campus(db, ids)
    purchases = purchases_by_campus(db, ids, date_from, date_to)
    activity = last_activity(db, ids)
    erp = integrations(db, ids)
    rows = []
    for c in campuses:
        row = {"id": c.id, "name": c.name, "code": c.code, "is_active": c.is_active is not False,
               "organization_id": c.organization_id, "users": users[c.id], "purchases": purchases[c.id],
               "last_activity_at": activity.get(c.id), "erp": erp[c.id]}
        if with_operations:
            row["operations"] = operations(db, c.id, today)
        rows.append(row)
    return rows


def alerts(rows: list[dict]) -> list[dict]:
    """Things a platform administrator should look at, worst first."""
    out = []
    for r in rows:
        def add(level: str, text: str):
            out.append({"campus_id": r["id"], "campus_name": r["name"], "level": level, "text": text})
        if not r["is_active"]:
            add("info", "Campus is deactivated; its users cannot sign in.")
            continue
        if r["users"]["ADMIN"] == 0:
            add("critical", "No active campus Admin.")
        ops = r.get("operations") or {}
        if ops.get("stock", {}).get("below_minimum"):
            add("warning", f"{ops['stock']['below_minimum']} items below minimum stock.")
        if ops.get("pending_adjustments"):
            add("warning", f"{ops['pending_adjustments']} stock adjustments waiting for approval.")
        if ops.get("meals_awaiting_close"):
            add("warning", f"{ops['meals_awaiting_close']} meal records from earlier days still open.")
        if r["erp"]["last_sync_status"] == "FAILED":
            add("warning", "Last ERP headcount sync failed.")
    rank = {"critical": 0, "warning": 1, "info": 2}
    return sorted(out, key=lambda a: (rank[a["level"]], a["campus_name"].lower()))


def monthly_purchases(db: Session, campus_ids: list[int], date_from: date, date_to: date) -> list[dict]:
    year = extract("year", Purchase.purchase_date)
    month = extract("month", Purchase.purchase_date)
    rows = (db.query(Purchase.campus_id, year, month, func.count(Purchase.id), func.coalesce(func.sum(Purchase.grand_total), 0))
            .filter(Purchase.campus_id.in_(campus_ids or [0]), Purchase.purchase_date >= date_from,
                    Purchase.purchase_date <= date_to)
            .group_by(Purchase.campus_id, year, month).order_by(year, month).all())
    return [{"campus_id": cid, "month": f"{int(y):04d}-{int(m):02d}", "bill_count": int(n), "total": money_text(Decimal(t))}
            for cid, y, m, n, t in rows]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
