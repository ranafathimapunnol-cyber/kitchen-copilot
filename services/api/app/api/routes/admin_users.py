"""Campus user accounts (Stage 10). ADMIN only, own campus only.

Only ADMIN manages campus user authorization (approved role model): list
accounts, edit names, change between Kitchen Manager and Staff, deactivate
and reactivate (with a reason), sign a user out everywhere, and issue a
password reset link. STAFF permissions stay on the Staff Management screen
and are never changed here. An ADMIN never changes their own role or
status, and no account can become ADMIN here (ADMIN accounts are
provisioned by the platform: SUPER_ADMIN, Stage 11).
"""

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.api.routes.master_data import record_audit
from app.core.clock import utc_iso
from app.core.config import settings
from app.core.security import PASSWORD_RESET, create_password_token
from app.db.session import get_db
from app.models.authorization import StaffAccessAssignment
from app.models.security import LoginAttempt
from app.models.user import User, UserRole
from app.services.password_management import RESET_PATH, PasswordLinkConfigError, build_frontend_link

router = APIRouter(prefix="/api/admin/users", tags=["User accounts"])
admins = require_roles(UserRole.ADMIN)



class AccountUpdate(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    role: Literal["KITCHEN_MANAGER", "STAFF"] | None = None

    @field_validator("full_name")
    @classmethod
    def strip(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Enter the person's name.")
        return value


class ReasonInput(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


def revoke(user: User) -> None:
    user.sessions_revoked_at = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(seconds=1)


def campus_user(db: Session, admin: User, user_id: int) -> User:
    user = db.query(User).filter(User.id == user_id, User.campus_id == admin.campus_id).with_for_update().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def serialize(db: Session, user: User, failures: dict[int, int], grants: dict[int, int]) -> dict:
    return {
        "id": user.id, "full_name": user.full_name, "email": user.email, "role": user.role.value,
        "is_active": user.is_active, "last_login_at": utc_iso(user.last_login_at) if user.last_login_at else None,
        "sessions_revoked_at": utc_iso(user.sessions_revoked_at) if user.sessions_revoked_at else None,
        "failed_sign_ins_24h": failures.get(user.id, 0), "active_grants": grants.get(user.id, 0),
    }


def counts(db: Session, ids: list[int]) -> tuple[dict, dict]:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    failures = dict(db.query(LoginAttempt.user_id, func.count(LoginAttempt.id)).filter(
        LoginAttempt.user_id.in_(ids or [0]), LoginAttempt.succeeded.is_(False), LoginAttempt.created_at >= since)
        .group_by(LoginAttempt.user_id))
    grants = dict(db.query(StaffAccessAssignment.staff_user_id, func.count(StaffAccessAssignment.id)).filter(
        StaffAccessAssignment.staff_user_id.in_(ids or [0]), StaffAccessAssignment.is_active.is_(True))
        .group_by(StaffAccessAssignment.staff_user_id))
    return failures, grants


@router.get("")
def list_accounts(
    role: Literal["ADMIN", "KITCHEN_MANAGER", "STAFF"] | None = Query(default=None),
    status: Literal["active", "inactive"] | None = Query(default=None),
    search: str | None = Query(default=None, max_length=100),
    db: Session = Depends(get_db), admin: User = Depends(admins),
):
    query = db.query(User).filter(User.campus_id == admin.campus_id)
    if role:
        query = query.filter(User.role == UserRole(role))
    if status:
        query = query.filter(User.is_active.is_(status == "active"))
    term = (search or "").strip().lower()
    if term:
        query = query.filter(func.lower(User.full_name).contains(term) | func.lower(User.email).contains(term))
    users = query.order_by(User.is_active.desc(), func.lower(User.full_name)).all()
    failures, grants = counts(db, [u.id for u in users])
    return {"items": [serialize(db, u, failures, grants) for u in users], "self_id": admin.id}


@router.get("/{user_id}/sign-ins")
def sign_in_history(user_id: int, db: Session = Depends(get_db), admin: User = Depends(admins)):
    user = db.query(User).filter(User.id == user_id, User.campus_id == admin.campus_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    rows = (db.query(LoginAttempt).filter(LoginAttempt.user_id == user.id)
            .order_by(LoginAttempt.created_at.desc()).limit(50).all())
    return {"items": [{"id": r.id, "succeeded": r.succeeded, "ip_address": r.ip_address,
                       "created_at": utc_iso(r.created_at)} for r in rows]}


@router.patch("/{user_id}")
def update_account(user_id: int, payload: AccountUpdate, db: Session = Depends(get_db), admin: User = Depends(admins)):
    user = campus_user(db, admin, user_id)
    before = {"full_name": user.full_name, "role": user.role.value}
    if payload.role and payload.role != user.role.value:
        if user.id == admin.id:
            raise HTTPException(status_code=409, detail="You cannot change your own role.")
        if user.role == UserRole.ADMIN:
            raise HTTPException(status_code=409, detail="Admin accounts keep their role; they are managed by the platform.")
        user.role = UserRole(payload.role)
        # A role change ends every existing session, so the new rights apply at once.
        revoke(user)
    user.full_name = payload.full_name
    record_audit(db, admin, "UPDATE", "USER", user.id, {"before": before,
                                                         "after": {"full_name": user.full_name, "role": user.role.value}})
    db.commit()
    failures, grants = counts(db, [user.id])
    return serialize(db, user, failures, grants)


@router.post("/{user_id}/deactivate")
def deactivate_account(user_id: int, payload: ReasonInput, db: Session = Depends(get_db), admin: User = Depends(admins)):
    user = campus_user(db, admin, user_id)
    if user.id == admin.id:
        raise HTTPException(status_code=409, detail="You cannot deactivate your own account.")
    if not user.is_active:
        raise HTTPException(status_code=409, detail="This account is already inactive.")
    if user.role == UserRole.ADMIN:
        others = db.query(func.count(User.id)).filter(User.campus_id == admin.campus_id, User.role == UserRole.ADMIN,
                                                      User.is_active.is_(True), User.id != user.id).scalar()
        if not others:
            raise HTTPException(status_code=409, detail="The campus must keep at least one active Admin.")
    user.is_active = False
    revoke(user)
    record_audit(db, admin, "DEACTIVATE", "USER", user.id, {"reason": payload.reason.strip()})
    db.commit()
    failures, grants = counts(db, [user.id])
    return serialize(db, user, failures, grants)


@router.post("/{user_id}/reactivate")
def reactivate_account(user_id: int, payload: ReasonInput, db: Session = Depends(get_db), admin: User = Depends(admins)):
    user = campus_user(db, admin, user_id)
    if user.is_active:
        raise HTTPException(status_code=409, detail="This account is already active.")
    if user.role == UserRole.ADMIN:
        # One active Admin per campus (migration a7d3e9b1c4f2): a second one
        # is replaced through the platform, never reactivated here.
        raise HTTPException(status_code=409, detail="This campus already has its active Admin. A platform "
                                                    "administrator can replace the Admin if needed.")
    user.is_active = True
    record_audit(db, admin, "REACTIVATE", "USER", user.id, {"reason": payload.reason.strip()})
    db.commit()
    failures, grants = counts(db, [user.id])
    return serialize(db, user, failures, grants)


@router.post("/{user_id}/revoke-sessions")
def revoke_sessions(user_id: int, db: Session = Depends(get_db), admin: User = Depends(admins)):
    user = campus_user(db, admin, user_id)
    revoke(user)
    record_audit(db, admin, "REVOKE_SESSIONS", "USER", user.id, {})
    db.commit()
    failures, grants = counts(db, [user.id])
    return serialize(db, user, failures, grants)


@router.post("/{user_id}/reset-link")
def password_reset_link(user_id: int, db: Session = Depends(get_db), admin: User = Depends(admins)):
    """A single-use password reset link for an active account, to hand to
    the person (it stops working once the password changes or after the
    configured time). The password itself is never shown or set here."""
    user = campus_user(db, admin, user_id)
    if not user.is_active:
        raise HTTPException(status_code=409, detail="Reactivate the account first.")
    token = create_password_token(user.id, user.password_hash, PASSWORD_RESET,
                                  timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES))
    try:
        link = build_frontend_link(RESET_PATH, token)
    except PasswordLinkConfigError as exc:
        raise HTTPException(status_code=503, detail=f"Password links are not configured: {exc}") from None
    record_audit(db, admin, "PASSWORD_RESET_LINK", "USER", user.id, {})
    db.commit()
    return {"link": link, "expires_in_minutes": settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES}
