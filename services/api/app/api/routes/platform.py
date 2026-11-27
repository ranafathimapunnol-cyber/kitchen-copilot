"""Platform (organisation-level) API — Stage 11. SUPER_ADMIN only.

Hierarchy: organisation -> campuses -> campus users -> campus records.
A SUPER_ADMIN signs in here (separate cookie and key), manages the
organisation's campuses, provisions each campus's first Admin by emailed
setup link, and reads campus *aggregates*. It holds no campus permission:
every campus endpoint refuses its session (app/api/dependencies.py).
A SUPER_ADMIN with an organisation_id sees only that organisation's
campuses; one without sees every campus.

Every sensitive action and every platform sign-in attempt is written to the
append-only platform_audit_logs. All routes need migration M1.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session, undefer

from app.api.platform_auth import (
    get_platform_user,
    record_platform_audit,
    require_platform_schema,
)
from app.api.routes.auth import _client_ip, _throttled
from app.core.clock import campus_today, utc_iso
from app.core.config import settings
from app.core.security import create_platform_token, verify_password
from app.db.session import get_db
from app.models.campus import Campus
from app.models.organization import Organization
from app.models.platform import CampusIntegration, ErpSyncRun, PlatformAuditLog
from app.models.security import LoginAttempt
from app.models.user import User, UserRole
from app.schemas.auth import AppEmail
from app.services import campus_media, erp_headcount
from app.services.attachment_storage import AttachmentStorage, get_attachment_storage
from app.services import platform_summary as summary
from app.services.password_management import AccountProvisioningError, provision_admin

router = APIRouter(prefix="/api/platform", tags=["Platform"], dependencies=[Depends(require_platform_schema)])

CAMPUS_COLUMNS = (Campus.organization_id, Campus.address, Campus.contact_name, Campus.contact_email,
                  Campus.contact_phone, Campus.created_at, Campus.updated_at, Campus.deactivated_at,
                  Campus.deactivation_reason)


# ============================================================
# AUTHENTICATION
# ============================================================

class PlatformLogin(BaseModel):
    email: AppEmail
    password: str = Field(min_length=1, max_length=200)


def platform_user_out(user: User) -> dict:
    return {"id": user.id, "full_name": user.full_name, "email": user.email, "role": user.role.value,
            "organization_id": user.organization_id, "session_minutes": settings.PLATFORM_SESSION_MINUTES,
            "last_login_at": utc_iso(user.last_login_at) if user.last_login_at else None}


def set_platform_cookie(response: Response, user: User) -> None:
    response.set_cookie(key=settings.PLATFORM_ACCESS_COOKIE_NAME, value=create_platform_token(user.id, user.password_hash),
                        max_age=settings.PLATFORM_SESSION_MINUTES * 60, httponly=True, secure=settings.COOKIE_SECURE,
                        samesite=settings.COOKIE_SAMESITE, domain=settings.COOKIE_DOMAIN, path="/")


def clear_platform_cookie(response: Response) -> None:
    response.delete_cookie(key=settings.PLATFORM_ACCESS_COOKIE_NAME, path="/", domain=settings.COOKIE_DOMAIN,
                           secure=settings.COOKIE_SECURE, httponly=True, samesite=settings.COOKIE_SAMESITE)


@router.post("/auth/login")
def platform_login(data: PlatformLogin, request: Request, response: Response, db: Session = Depends(get_db)):
    """Platform sign-in: SUPER_ADMIN accounts only. Throttled like the campus
    sign-in (same attempts table); every attempt is in the platform audit."""
    email = str(data.email).lower()
    ip = _client_ip(request)
    wait = _throttled(db, email, ip)
    if wait is not None:
        record_platform_audit(db, action="LOGIN", target_type="PLATFORM_SESSION", outcome="DENIED", actor_email=email,
                              request=request, details={"reason": "throttled"})
        db.commit()
        minutes = max(1, (wait + 59) // 60)
        raise HTTPException(status_code=429, headers={"Retry-After": str(wait)},
                            detail=f"Too many failed sign-in attempts. Try again in {minutes} minute{'s' if minutes != 1 else ''}.")
    user = db.query(User).filter(func.lower(User.email) == email).first()
    ok = bool(user) and verify_password(data.password, user.password_hash)
    platform = bool(user) and user.role == UserRole.SUPER_ADMIN and user.campus_id is None
    success = ok and platform and user.is_active
    db.add(LoginAttempt(email=email, ip_address=ip, succeeded=success, user_id=user.id if user else None))
    if not success:
        # One answer for every failure, so the page reveals nothing about
        # which accounts exist or which are campus accounts.
        reason = "bad_credentials" if not ok else ("not_platform_account" if not platform else "inactive")
        record_platform_audit(db, action="LOGIN", target_type="PLATFORM_SESSION", outcome="FAILURE",
                              actor_email=email, request=request, details={"reason": reason})
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid email or password for a platform account.")
    user.last_login_at = datetime.now(timezone.utc)
    record_platform_audit(db, action="LOGIN", target_type="PLATFORM_SESSION", actor=user, request=request)
    db.commit()
    db.refresh(user)
    set_platform_cookie(response, user)
    return platform_user_out(user)


@router.post("/auth/logout")
def platform_logout(request: Request, response: Response, db: Session = Depends(get_db),
                    user: User = Depends(get_platform_user)):
    """Ends every platform session of this account (the token is refused
    from now on, not only removed from this browser)."""
    user.sessions_revoked_at = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(seconds=1)
    record_platform_audit(db, action="LOGOUT", target_type="PLATFORM_SESSION", actor=user, request=request)
    db.commit()
    clear_platform_cookie(response)
    return {"message": "Signed out."}


@router.get("/auth/me")
def platform_me(user: User = Depends(get_platform_user)):
    return platform_user_out(user)


# ============================================================
# SCOPE AND HELPERS
# ============================================================

def scoped_campuses(db: Session, user: User):
    query = db.query(Campus).options(*(undefer(c) for c in CAMPUS_COLUMNS))
    if user.organization_id:
        query = query.filter(Campus.organization_id == user.organization_id)
    return query


def campus_or_404(db: Session, user: User, campus_id: int) -> Campus:
    campus = scoped_campuses(db, user).filter(Campus.id == campus_id).first()
    if not campus:
        raise HTTPException(status_code=404, detail="Campus not found")
    return campus


def period(date_from: date | None, date_to: date | None) -> tuple[date, date, date]:
    today = campus_today()
    start, end = date_from or today.replace(day=1), date_to or today
    if start > end:
        raise HTTPException(status_code=422, detail="The start date must be on or before the end date.")
    if (end - start).days > 731:
        raise HTTPException(status_code=422, detail="Choose a period of at most two years.")
    return start, end, today


def org_names(db: Session) -> dict[int, str]:
    return dict(db.query(Organization.id, Organization.name))


def campus_detail_out(c: Campus, orgs: dict[int, str]) -> dict:
    return {"id": c.id, "name": c.name, "code": c.code, "is_active": c.is_active is not False,
            "organization_id": c.organization_id, "organization_name": orgs.get(c.organization_id),
            "address": c.address, "contact_name": c.contact_name, "contact_email": c.contact_email,
            "contact_phone": c.contact_phone, "created_at": utc_iso(c.created_at) if c.created_at else None,
            "updated_at": utc_iso(c.updated_at) if c.updated_at else None,
            "deactivated_at": utc_iso(c.deactivated_at) if c.deactivated_at else None,
            "deactivation_reason": c.deactivation_reason}


def with_media(db: Session, row: dict) -> dict:
    row["media"] = campus_media.media_info(db, row["id"])
    return row


def tidy(value: str | None) -> str | None:
    if value is None:
        return None
    value = " ".join(value.split())
    return value or None


# ============================================================
# ORGANISATION OVERVIEW AND ANALYTICS
# ============================================================

@router.get("/overview")
def overview(date_from: date | None = None, date_to: date | None = None, campus_id: int | None = Query(default=None, gt=0),
             db: Session = Depends(get_db), user: User = Depends(get_platform_user)):
    start, end, today = period(date_from, date_to)
    campuses = scoped_campuses(db, user).order_by(func.lower(Campus.name)).all()
    if campus_id:
        campuses = [c for c in campuses if c.id == campus_id]
        if not campuses:
            raise HTTPException(status_code=404, detail="Campus not found")
    rows = summary.campus_rows(db, campuses, start, end, today)
    orgs = org_names(db)
    for r in rows:
        r["organization_name"] = orgs.get(r["organization_id"])
        r["last_activity_at"] = utc_iso(r["last_activity_at"]) if r["last_activity_at"] else None
    active = [r for r in rows if r["is_active"]]
    spend = sum((float(r["purchases"]["total"]) for r in rows), 0.0)
    recent = (db.query(PlatformAuditLog).order_by(PlatformAuditLog.id.desc()).limit(12).all())
    return {
        "period": {"date_from": start.isoformat(), "date_to": end.isoformat()},
        "generated_at": utc_iso(datetime.now(timezone.utc)),
        "totals": {
            "campuses": len(rows), "active_campuses": len(active), "inactive_campuses": len(rows) - len(active),
            "users": sum(r["users"]["total"] for r in rows), "active_users": sum(r["users"]["active"] for r in rows),
            "admins": sum(r["users"]["ADMIN"] for r in rows),
            "kitchen_managers": sum(r["users"]["KITCHEN_MANAGER"] for r in rows),
            "staff": sum(r["users"]["STAFF"] for r in rows),
            "purchases_total": f"{spend:.2f}", "bills": sum(r["purchases"]["bill_count"] for r in rows),
            "outstanding_payables": f"{sum(float(r['operations']['outstanding_payables']) for r in rows):.2f}",
            "items_below_minimum": sum(r["operations"]["stock"]["below_minimum"] for r in rows),
            "items_out_of_stock": sum(r["operations"]["stock"]["out_of_stock"] for r in rows),
            "erp_configured": sum(1 for r in rows if r["erp"]["state"] != "NOT_CONFIGURED"),
        },
        "campuses": rows,
        "alerts": summary.alerts(rows),
        "activity": [audit_out(a) for a in recent],
    }


@router.get("/analytics")
def analytics(date_from: date | None = None, date_to: date | None = None, campus_id: int | None = Query(default=None, gt=0),
              db: Session = Depends(get_db), user: User = Depends(get_platform_user)):
    start, end, _today = period(date_from, date_to)
    campuses = scoped_campuses(db, user).order_by(func.lower(Campus.name)).all()
    if campus_id:
        campuses = [c for c in campuses if c.id == campus_id]
    ids = [c.id for c in campuses]
    purchases = summary.purchases_by_campus(db, ids, start, end)
    return {"period": {"date_from": start.isoformat(), "date_to": end.isoformat()},
            "campuses": [{"id": c.id, "name": c.name, "code": c.code, "is_active": c.is_active is not False,
                          **purchases[c.id]} for c in campuses],
            "monthly": summary.monthly_purchases(db, ids, start, end)}


# ============================================================
# ORGANISATIONS
# ============================================================

class OrgInput(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    code: str = Field(pattern=r"^[A-Za-z0-9_-]{2,30}$")

    @field_validator("name")
    @classmethod
    def clean(cls, v: str) -> str:
        v = tidy(v) or ""
        if len(v) < 2:
            raise ValueError("Enter at least two characters.")
        return v


@router.get("/organizations")
def list_organizations(db: Session = Depends(get_db), user: User = Depends(get_platform_user)):
    query = db.query(Organization)
    if user.organization_id:
        query = query.filter(Organization.id == user.organization_id)
    counts = dict(db.query(Campus.organization_id, func.count(Campus.id)).group_by(Campus.organization_id))
    return {"items": [{"id": o.id, "name": o.name, "code": o.code, "is_active": o.is_active,
                       "campus_count": counts.get(o.id, 0), "created_at": utc_iso(o.created_at)}
                      for o in query.order_by(func.lower(Organization.name))]}


@router.post("/organizations", status_code=201)
def create_organization(payload: OrgInput, request: Request, db: Session = Depends(get_db),
                        user: User = Depends(get_platform_user)):
    if user.organization_id:
        raise HTTPException(status_code=403, detail="Only an all-organisations platform administrator can add organisations.")
    code = payload.code.upper()
    if db.query(Organization.id).filter(or_(func.lower(Organization.name) == payload.name.lower(),
                                            func.lower(Organization.code) == code.lower())).first():
        raise HTTPException(status_code=409, detail="An organisation with this name or code already exists.")
    org = Organization(name=payload.name, code=code)
    db.add(org)
    db.flush()
    record_platform_audit(db, action="CREATE", target_type="ORGANIZATION", target_id=org.id, actor=user, request=request,
                          details={"name": org.name, "code": org.code})
    db.commit()
    return {"id": org.id, "name": org.name, "code": org.code, "is_active": org.is_active, "campus_count": 0,
            "created_at": utc_iso(org.created_at)}


# ============================================================
# CAMPUSES
# ============================================================

class CampusFields(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    organization_id: int | None = Field(default=None, gt=0)
    address: str | None = Field(default=None, max_length=500)
    contact_name: str | None = Field(default=None, max_length=150)
    contact_email: AppEmail | None = None
    contact_phone: str | None = Field(default=None, max_length=40, pattern=r"^[0-9+()\- ]{6,40}$")

    @field_validator("name", "address", "contact_name")
    @classmethod
    def clean(cls, v: str | None) -> str | None:
        return tidy(v)

    @field_validator("contact_phone", mode="before")
    @classmethod
    def blank_phone(cls, v):
        return None if v in ("", None) else v

    @field_validator("contact_email", mode="before")
    @classmethod
    def blank_email(cls, v):
        return None if v in ("", None) else v


class CampusCreate(CampusFields):
    code: str = Field(pattern=r"^[A-Za-z0-9_-]{2,30}$")


class Reason(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


def check_org(db: Session, user: User, organization_id: int | None) -> int | None:
    if user.organization_id:
        if organization_id not in (None, user.organization_id):
            raise HTTPException(status_code=403, detail="You manage only your own organisation's campuses.")
        return user.organization_id
    if organization_id and not db.get(Organization, organization_id):
        raise HTTPException(status_code=422, detail="Organisation not found.")
    return organization_id


def check_unique_name(db: Session, name: str, own_id: int | None = None):
    query = db.query(Campus.id).filter(func.lower(Campus.name) == name.lower())
    if own_id:
        query = query.filter(Campus.id != own_id)
    if query.first():
        raise HTTPException(status_code=409, detail="Another campus already uses this name.")


@router.get("/campuses")
def list_campuses(status: Literal["all", "active", "inactive"] = "all", q: str | None = Query(default=None, max_length=100),
                  db: Session = Depends(get_db), user: User = Depends(get_platform_user)):
    query = scoped_campuses(db, user)
    if status != "all":
        query = query.filter(Campus.is_active.is_(status == "active"))
    if q:
        like = f"%{q.strip().lower()}%"
        query = query.filter(or_(func.lower(Campus.name).like(like), func.lower(Campus.code).like(like)))
    campuses = query.order_by(func.lower(Campus.name)).all()
    today = campus_today()
    rows = summary.campus_rows(db, campuses, today.replace(day=1), today, today, with_operations=False)
    orgs = org_names(db)
    for r, c in zip(rows, campuses):
        r.update(campus_detail_out(c, orgs))
        r["last_activity_at"] = utc_iso(r["last_activity_at"]) if r["last_activity_at"] else None
        with_media(db, r)
    return {"items": rows}


@router.post("/campuses", status_code=201)
def create_campus(payload: CampusCreate, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(get_platform_user)):
    code = payload.code.upper()
    check_unique_name(db, payload.name)
    if db.query(Campus.id).filter(func.lower(Campus.code) == code.lower()).first():
        raise HTTPException(status_code=409, detail="Another campus already uses this code.")
    now = datetime.now(timezone.utc)
    campus = Campus(name=payload.name, code=code, is_active=True, organization_id=check_org(db, user, payload.organization_id),
                    address=payload.address, contact_name=payload.contact_name,
                    contact_email=str(payload.contact_email).lower() if payload.contact_email else None,
                    contact_phone=payload.contact_phone, created_at=now, updated_at=now)
    db.add(campus)
    db.flush()
    record_platform_audit(db, action="CREATE", target_type="CAMPUS", target_id=campus.id, campus_id=campus.id,
                          actor=user, request=request, details={"name": campus.name, "code": campus.code,
                                                                "organization_id": campus.organization_id})
    db.commit()
    return with_media(db, campus_detail_out(campus_or_404(db, user, campus.id), org_names(db)))


@router.get("/campuses/{campus_id}")
def campus_detail(campus_id: int, date_from: date | None = None, date_to: date | None = None,
                  db: Session = Depends(get_db), user: User = Depends(get_platform_user)):
    campus = campus_or_404(db, user, campus_id)
    start, end, today = period(date_from, date_to)
    row = summary.campus_rows(db, [campus], start, end, today)[0]
    row["last_activity_at"] = utc_iso(row["last_activity_at"]) if row["last_activity_at"] else None
    row.update(campus_detail_out(campus, org_names(db)))
    row["period"] = {"date_from": start.isoformat(), "date_to": end.isoformat()}
    row["alerts"] = summary.alerts([row])
    return with_media(db, row)


@router.patch("/campuses/{campus_id}")
def update_campus(campus_id: int, payload: CampusFields, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(get_platform_user)):
    """Edits the campus's details. The code is fixed once created (it
    appears on documents and in reports)."""
    campus = campus_or_404(db, user, campus_id)
    check_unique_name(db, payload.name, campus.id)
    fields = ("name", "organization_id", "address", "contact_name", "contact_email", "contact_phone")
    before = {f: getattr(campus, f) for f in fields}
    campus.name = payload.name
    campus.organization_id = check_org(db, user, payload.organization_id)
    campus.address, campus.contact_name, campus.contact_phone = payload.address, payload.contact_name, payload.contact_phone
    campus.contact_email = str(payload.contact_email).lower() if payload.contact_email else None
    after = {f: getattr(campus, f) for f in fields}
    changed = {f: {"from": before[f], "to": after[f]} for f in fields if before[f] != after[f]}
    if changed:
        campus.updated_at = datetime.now(timezone.utc)
        record_platform_audit(db, action="UPDATE", target_type="CAMPUS", target_id=campus.id, campus_id=campus.id,
                              actor=user, request=request, details={"changes": changed})
    db.commit()
    return with_media(db, campus_detail_out(campus_or_404(db, user, campus.id), org_names(db)))


@router.post("/campuses/{campus_id}/deactivate")
def deactivate_campus(campus_id: int, payload: Reason, request: Request, db: Session = Depends(get_db),
                      user: User = Depends(get_platform_user)):
    """Stops the campus's users from using the application. Nothing is
    deleted: users, records, stock, bills, attachments and audit history are
    kept and come back unchanged on activation."""
    campus = campus_or_404(db, user, campus_id)
    if campus.is_active is False:
        raise HTTPException(status_code=409, detail="The campus is already deactivated.")
    campus.is_active = False
    campus.deactivated_at = campus.updated_at = datetime.now(timezone.utc)
    campus.deactivation_reason = " ".join(payload.reason.split())
    record_platform_audit(db, action="DEACTIVATE", target_type="CAMPUS", target_id=campus.id, campus_id=campus.id,
                          actor=user, request=request, details={"reason": campus.deactivation_reason})
    db.commit()
    return with_media(db, campus_detail_out(campus_or_404(db, user, campus.id), org_names(db)))


@router.post("/campuses/{campus_id}/activate")
def activate_campus(campus_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(get_platform_user)):
    campus = campus_or_404(db, user, campus_id)
    if campus.is_active is not False:
        raise HTTPException(status_code=409, detail="The campus is already active.")
    campus.is_active = True
    campus.deactivated_at = None
    campus.updated_at = datetime.now(timezone.utc)
    record_platform_audit(db, action="ACTIVATE", target_type="CAMPUS", target_id=campus.id, campus_id=campus.id,
                          actor=user, request=request, details={"previous_reason": campus.deactivation_reason})
    campus.deactivation_reason = None
    db.commit()
    return with_media(db, campus_detail_out(campus_or_404(db, user, campus.id), org_names(db)))


# ============================================================
# CAMPUS LOGO AND PHOTO
# ============================================================

def media_kind(kind: str) -> campus_media.Kind:
    if kind not in campus_media.KINDS:
        raise HTTPException(status_code=404, detail="Unknown image type")
    return campus_media.KINDS[kind]


def require_media(db: Session) -> None:
    if not campus_media.media_ready(db):
        raise HTTPException(status_code=503, detail=campus_media.MEDIA_NOT_MIGRATED)


@router.put("/campuses/{campus_id}/media/{kind}")
def upload_campus_media(campus_id: int, kind: str, request: Request, file: UploadFile = File(...),
                        db: Session = Depends(get_db), user: User = Depends(get_platform_user),
                        storage: AttachmentStorage = Depends(get_attachment_storage)):
    """Sets or replaces the campus logo or photo. The image is re-encoded
    (resized, metadata removed) before it is stored."""
    spec = media_kind(kind)
    campus = campus_or_404(db, user, campus_id)
    require_media(db)
    data = file.file.read(campus_media.MAX_UPLOAD_BYTES + 1)
    try:
        clean = campus_media.process(spec, data)
    except campus_media.MediaRejected as exc:
        record_platform_audit(db, action="UPLOAD_MEDIA", target_type="CAMPUS", target_id=campus.id, campus_id=campus.id,
                              actor=user, request=request, outcome="FAILURE", details={"kind": kind, "error": str(exc)})
        db.commit()
        raise HTTPException(status_code=422, detail=str(exc)) from None
    key = campus_media.new_key(campus.id, spec)
    storage.save(key, clean)
    column = "logo_key" if kind == "logo" else "photo_key"
    previous = getattr(campus, column)
    try:
        setattr(campus, column, key)
        campus.media_updated_at = datetime.now(timezone.utc)
        record_platform_audit(db, action="UPLOAD_MEDIA", target_type="CAMPUS", target_id=campus.id, campus_id=campus.id,
                              actor=user, request=request,
                              details={"kind": kind, "bytes": len(clean), "replaced": bool(previous)})
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(key)
        raise
    if previous:
        try:
            storage.delete(previous)
        except (OSError, ValueError):
            pass
    return campus_media.media_info(db, campus.id)


@router.delete("/campuses/{campus_id}/media/{kind}")
def remove_campus_media(campus_id: int, kind: str, request: Request, db: Session = Depends(get_db),
                        user: User = Depends(get_platform_user),
                        storage: AttachmentStorage = Depends(get_attachment_storage)):
    media_kind(kind)
    campus = campus_or_404(db, user, campus_id)
    require_media(db)
    column = "logo_key" if kind == "logo" else "photo_key"
    previous = getattr(campus, column)
    if not previous:
        raise HTTPException(status_code=404, detail="This campus has no such image.")
    setattr(campus, column, None)
    campus.media_updated_at = datetime.now(timezone.utc)
    record_platform_audit(db, action="REMOVE_MEDIA", target_type="CAMPUS", target_id=campus.id, campus_id=campus.id,
                          actor=user, request=request, details={"kind": kind})
    db.commit()
    try:
        storage.delete(previous)
    except (OSError, ValueError):
        pass
    return campus_media.media_info(db, campus.id)


@router.get("/campuses/{campus_id}/media/{kind}")
def campus_media_file(campus_id: int, kind: str, db: Session = Depends(get_db), user: User = Depends(get_platform_user),
                      storage: AttachmentStorage = Depends(get_attachment_storage)):
    from app.api.routes.campus_media import serve

    media_kind(kind)
    campus = campus_or_404(db, user, campus_id)
    return serve(db, storage, campus.id, kind)


# ============================================================
# USERS (read-only, plus provisioning a campus's Admin)
# ============================================================

def user_row(u: User, campuses: dict[int, str]) -> dict:
    return {"id": u.id, "full_name": u.full_name, "email": u.email, "role": u.role.value, "is_active": u.is_active,
            "campus_id": u.campus_id, "campus_name": campuses.get(u.campus_id),
            "last_login_at": utc_iso(u.last_login_at) if u.last_login_at else None}


@router.get("/campuses/{campus_id}/users")
def campus_users(campus_id: int, db: Session = Depends(get_db), user: User = Depends(get_platform_user)):
    campus = campus_or_404(db, user, campus_id)
    users = db.query(User).filter(User.campus_id == campus.id).order_by(User.role, func.lower(User.full_name)).all()
    return {"items": [user_row(u, {campus.id: campus.name}) for u in users]}


@router.get("/users")
def platform_users(scope: Literal["campus", "platform"] = "campus", campus_id: int | None = Query(default=None, gt=0),
                   role: Literal["ADMIN", "KITCHEN_MANAGER", "STAFF"] | None = None,
                   q: str | None = Query(default=None, max_length=100),
                   db: Session = Depends(get_db), user: User = Depends(get_platform_user)):
    """Campus accounts across the organisation (read-only; each campus's
    Admin manages them), or the platform accounts."""
    if scope == "platform":
        rows = db.query(User).filter(User.role == UserRole.SUPER_ADMIN).order_by(func.lower(User.full_name)).all()
        return {"items": [user_row(u, {}) for u in rows]}
    campuses = {c.id: c.name for c in scoped_campuses(db, user)}
    query = db.query(User).filter(User.campus_id.in_(list(campuses) or [0]))
    if campus_id:
        query = query.filter(User.campus_id == campus_id)
    if role:
        query = query.filter(User.role == UserRole(role))
    if q:
        like = f"%{q.strip().lower()}%"
        query = query.filter(or_(func.lower(User.full_name).like(like), func.lower(User.email).like(like)))
    return {"items": [user_row(u, campuses) for u in query.order_by(func.lower(User.full_name)).limit(500)]}


class AdminInput(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: AppEmail

    @field_validator("full_name")
    @classmethod
    def clean(cls, v: str) -> str:
        return tidy(v) or ""


@router.post("/campuses/{campus_id}/admins", status_code=201)
def provision_campus_admin(campus_id: int, payload: AdminInput, request: Request, db: Session = Depends(get_db),
                           user: User = Depends(get_platform_user)):
    """Creates the campus's Admin with no usable password and emails a setup
    link; nothing is saved when the email cannot be sent. The platform never
    sees or sets the password."""
    campus = campus_or_404(db, user, campus_id)
    if campus.is_active is False:
        raise HTTPException(status_code=409, detail="Activate the campus first.")
    email = str(payload.email).strip().lower()
    try:
        admin, created = provision_admin(db, campus, payload.full_name, email)
    except AccountProvisioningError as exc:
        db.rollback()
        record_platform_audit(db, action="PROVISION_ADMIN", target_type="USER", campus_id=campus.id, actor=user,
                              request=request, outcome="FAILURE", details={"email": email, "error": str(exc)[:200]})
        db.commit()
        raise HTTPException(status_code=409 if "already" in str(exc) else 503, detail=str(exc)) from None
    record_platform_audit(db, action="PROVISION_ADMIN", target_type="USER", target_id=admin.id, campus_id=campus.id,
                          actor=user, request=request, details={"email": admin.email, "created": created})
    db.commit()
    return {"id": admin.id, "full_name": admin.full_name, "email": admin.email, "created": created,
            "message": "Setup link emailed." if created else "A new setup link was emailed."}


# ============================================================
# PLATFORM AUDIT LOG (read-only)
# ============================================================

def audit_out(a: PlatformAuditLog) -> dict:
    return {"id": a.id, "occurred_at": utc_iso(a.occurred_at), "actor_user_id": a.actor_user_id,
            "actor_email": a.actor_email, "action": a.action, "target_type": a.target_type, "target_id": a.target_id,
            "campus_id": a.campus_id, "outcome": a.outcome, "ip_address": a.ip_address, "details": a.details}


@router.get("/audit")
def platform_audit(action: str | None = Query(default=None, max_length=60),
                   outcome: Literal["SUCCESS", "FAILURE", "DENIED"] | None = None,
                   campus_id: int | None = Query(default=None, gt=0),
                   date_from: date | None = None, date_to: date | None = None,
                   page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=200),
                   db: Session = Depends(get_db), user: User = Depends(get_platform_user)):
    query = db.query(PlatformAuditLog)
    if user.organization_id:
        own = [c.id for c in scoped_campuses(db, user)]
        query = query.filter(or_(PlatformAuditLog.campus_id.is_(None), PlatformAuditLog.campus_id.in_(own or [0])))
    if action:
        query = query.filter(PlatformAuditLog.action == action.upper())
    if outcome:
        query = query.filter(PlatformAuditLog.outcome == outcome)
    if campus_id:
        query = query.filter(PlatformAuditLog.campus_id == campus_id)
    if date_from:
        query = query.filter(PlatformAuditLog.occurred_at >= datetime.combine(date_from, datetime.min.time(), timezone.utc))
    if date_to:
        query = query.filter(PlatformAuditLog.occurred_at < datetime.combine(date_to + timedelta(days=1), datetime.min.time(), timezone.utc))
    total = query.count()
    rows = query.order_by(PlatformAuditLog.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [audit_out(a) for a in rows], "total": total, "page": page, "page_size": page_size}


# ============================================================
# INTEGRATIONS (ERP headcount: prepared, contract pending)
# ============================================================

class ErpSettings(BaseModel):
    is_enabled: bool = False
    base_url: str | None = Field(default=None, max_length=500, pattern=r"^https://[^\s/@]+(:\d+)?(/[^\s]*)?$")
    timeout_seconds: int = Field(default=15, ge=1, le=120)
    max_retries: int = Field(default=2, ge=0, le=5)

    @field_validator("base_url", mode="before")
    @classmethod
    def blank(cls, v):
        return None if v in ("", None) else v


@router.get("/integrations")
def list_integrations(db: Session = Depends(get_db), user: User = Depends(get_platform_user)):
    campuses = scoped_campuses(db, user).order_by(func.lower(Campus.name)).all()
    statuses = summary.integrations(db, [c.id for c in campuses])
    runs = {}
    for run in (db.query(ErpSyncRun).filter(ErpSyncRun.campus_id.in_([c.id for c in campuses] or [0]))
                .order_by(ErpSyncRun.id.desc()).limit(200)):
        runs.setdefault(run.campus_id, run)
    return {"credential": "set" if erp_headcount.credential_set() else "not set",
            "contract": "pending",
            "items": [{"campus_id": c.id, "campus_name": c.name, "campus_active": c.is_active is not False,
                       **statuses[c.id],
                       "last_sync_at": utc_iso(statuses[c.id]["last_sync_at"]) if statuses[c.id]["last_sync_at"] else None,
                       "last_run": {"status": runs[c.id].status, "error": runs[c.id].error,
                                    "started_at": utc_iso(runs[c.id].started_at)} if c.id in runs else None}
                      for c in campuses]}


@router.put("/campuses/{campus_id}/integrations/erp-headcount")
def configure_erp(campus_id: int, payload: ErpSettings, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(get_platform_user)):
    campus = campus_or_404(db, user, campus_id)
    row = (db.query(CampusIntegration).filter(CampusIntegration.campus_id == campus.id,
                                              CampusIntegration.kind == erp_headcount.KIND).first())
    before = None if not row else {"is_enabled": row.is_enabled, "base_url": row.base_url,
                                   "timeout_seconds": row.timeout_seconds, "max_retries": row.max_retries}
    if not row:
        row = CampusIntegration(campus_id=campus.id, kind=erp_headcount.KIND)
        db.add(row)
    row.is_enabled, row.base_url = payload.is_enabled, payload.base_url
    row.timeout_seconds, row.max_retries = payload.timeout_seconds, payload.max_retries
    row.updated_at, row.updated_by = datetime.now(timezone.utc), user.id
    db.flush()
    record_platform_audit(db, action="CONFIGURE_INTEGRATION", target_type="CAMPUS_INTEGRATION", target_id=row.id,
                          campus_id=campus.id, actor=user, request=request,
                          details={"kind": erp_headcount.KIND, "before": before, "after": payload.model_dump()})
    db.commit()
    return erp_headcount.status_of(row)


@router.post("/campuses/{campus_id}/integrations/erp-headcount/sync")
def sync_erp(campus_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(get_platform_user)):
    """Runs one sync now. Until the ERP contract is supplied this fetches
    nothing and records why (not configured / contract pending)."""
    campus = campus_or_404(db, user, campus_id)
    today = campus_today()
    run = erp_headcount.sync_campus(db, campus.id, user.id, today - timedelta(days=1), today)
    record_platform_audit(db, action="ERP_SYNC", target_type="CAMPUS_INTEGRATION", campus_id=campus.id, actor=user,
                          request=request, outcome="SUCCESS" if run.status == "SUCCEEDED" else "FAILURE",
                          details={"run_id": run.id, "status": run.status})
    db.commit()
    return {"id": run.id, "status": run.status, "error": run.error, "records_received": run.records_received,
            "records_applied": run.records_applied, "records_skipped": run.records_skipped}


# ============================================================
# SYSTEM HEALTH
# ============================================================

@router.get("/health")
def system_health(db: Session = Depends(get_db), user: User = Depends(get_platform_user)):
    """Configuration and reachability only: no secret, key, password or
    connection string is ever included."""
    import os

    from app.agent.intent import llm_available
    from app.core import email as email_transport

    checks = []

    def add(key: str, label: str, state: str, detail: str):
        checks.append({"key": key, "label": label, "state": state, "detail": detail})

    add("api", "API", "ok", f"Answering (version {settings.APP_VERSION}).")
    try:
        started = datetime.now(timezone.utc)
        db.execute(text("SELECT 1"))
        ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        try:
            with db.begin_nested():
                version = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
        except Exception:  # noqa: BLE001 - no migration table (test databases)
            version = "unknown"
        add("database", "Database", "ok", f"Connected in {ms} ms; schema revision {version}.")
    except Exception:  # noqa: BLE001 - report, never leak
        db.rollback()
        add("database", "Database", "error", "The database did not answer.")
    add("jobs", "Background jobs", "not_configured", "No background jobs are configured; ERP sync runs on request.")
    if not settings.AGENT_ENABLED:
        add("ai", "Kitchen Copilot", "off", "Turned off (AGENT_ENABLED=false).")
    elif llm_available():
        add("ai", "Kitchen Copilot", "ok", f"On, external model {settings.GEMINI_MODEL} configured.")
    else:
        add("ai", "Kitchen Copilot", "ok", "On, built-in request reader (no external AI configured).")
    storage_dir = settings.ATTACHMENT_STORAGE_DIR
    writable = os.path.isdir(storage_dir) and os.access(storage_dir, os.W_OK)
    add("storage", "Attachment storage", "ok" if writable else "warning",
        f"{settings.ATTACHMENT_STORAGE_BACKEND} storage; folder {'present and writable' if writable else 'missing or not writable'}.")
    configured = email_transport.is_email_configured()
    add("email", "Email (setup links)", "ok" if configured else "not_configured",
        "Configured." if configured else "Not configured: campus Admin setup links cannot be sent.")
    campuses = scoped_campuses(db, user).all()
    erp = summary.integrations(db, [c.id for c in campuses])
    configured_erp = sum(1 for s in erp.values() if s["state"] != "NOT_CONFIGURED")
    add("erp", "ERP headcount", "not_configured" if not configured_erp else "warning",
        "ERP connection not configured; waiting for the campus ERP API documentation."
        if not configured_erp else f"{configured_erp} campus(es) configured; API contract still pending.")
    active = sum(1 for c in campuses if c.is_active is not False)
    add("campuses", "Campuses", "ok", f"{active} active, {len(campuses) - active} deactivated.")
    return {"checked_at": utc_iso(datetime.now(timezone.utc)), "checks": checks}
