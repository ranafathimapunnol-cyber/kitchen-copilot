"""Audit viewer (Stage 10). Read-only; requires audit.read; own campus only.

Audit rows are never edited or deleted through the API. Money values inside
an entry's details (prices, costs, totals, balances, payments) are hidden
unless the reader also holds purchase_bill.read, the financial permission.
"""

import re
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.dependencies import require_permission, user_has_permission
from app.core.clock import utc_iso
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.user import User

router = APIRouter(prefix="/api/audit", tags=["Audit"])
readers = require_permission("audit.read")
MONEY_KEY = re.compile(r"(price|cost|amount|total|value|balance|paid|payment|discount|charge|rate|money|spend)", re.I)
HIDDEN = "hidden"
PAGE_MAX = 100


def redact(value):
    if isinstance(value, dict):
        return {k: (HIDDEN if MONEY_KEY.search(str(k)) and not isinstance(v, (dict, list)) and v is not None else redact(v))
                for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def bounds(date_from: date | None, date_to: date | None):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="The start date must be on or before the end date.")
    start = datetime.combine(date_from, time.min, tzinfo=timezone.utc) if date_from else None
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc) if date_to else None
    return start, end


@router.get("/options")
def audit_options(db: Session = Depends(get_db), user: User = Depends(readers)):
    campus = AuditLog.campus_id == user.campus_id
    actions = [a for (a,) in db.query(AuditLog.action).filter(campus).distinct().order_by(AuditLog.action)]
    entities = [e for (e,) in db.query(AuditLog.entity_type).filter(campus).distinct().order_by(AuditLog.entity_type)]
    people = db.query(User.id, User.full_name).filter(User.campus_id == user.campus_id).order_by(func.lower(User.full_name))
    return {"actions": actions, "entity_types": entities, "users": [{"id": i, "name": n} for i, n in people]}


@router.get("")
def list_audit(
    date_from: date | None = Query(default=None), date_to: date | None = Query(default=None),
    action: str | None = Query(default=None, max_length=50), entity_type: str | None = Query(default=None, max_length=100),
    entity_id: int | None = Query(default=None, gt=0), user_id: int | None = Query(default=None, gt=0),
    page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=PAGE_MAX),
    db: Session = Depends(get_db), user: User = Depends(readers),
):
    start, end = bounds(date_from, date_to)
    query = db.query(AuditLog).filter(AuditLog.campus_id == user.campus_id)
    if start:
        query = query.filter(AuditLog.created_at >= start)
    if end:
        query = query.filter(AuditLog.created_at < end)
    if action:
        query = query.filter(AuditLog.action == action)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.filter(AuditLog.entity_id == entity_id)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    total = query.count()
    rows = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    names = dict(db.query(User.id, User.full_name).filter(User.id.in_({r.user_id for r in rows if r.user_id} or {0})))
    financial = user_has_permission(db, user, "purchase_bill.read")
    return {
        "items": [{
            "id": r.id, "created_at": utc_iso(r.created_at), "action": r.action, "entity_type": r.entity_type,
            "entity_id": r.entity_id, "user_id": r.user_id, "user_name": names.get(r.user_id) if r.user_id else "System",
            "details": (r.details or {}) if financial else redact(r.details or {}),
        } for r in rows],
        "total": total, "page": page, "page_size": page_size, "financial_values": financial,
    }
