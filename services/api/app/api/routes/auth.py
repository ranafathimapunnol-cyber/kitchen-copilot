import secrets
from datetime import datetime, timedelta, timezone

import jwt

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.dependencies import get_current_user, require_roles, session_revoked
from app.core.config import settings
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    fingerprint_matches,
)
from app.models.user import User, UserRole
from app.models.audit_log import AuditLog
from app.models.security import LoginAttempt
from app.schemas.auth import LoginRequest, UserCreate, UserResponse


router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# A campus ADMIN may create only these account types. ADMIN accounts are
# provisioned separately (by the platform owner), never by another ADMIN.
ADMIN_CREATABLE_ROLES = frozenset({
    UserRole.KITCHEN_MANAGER,
    UserRole.STAFF,
})


def set_auth_cookies(response: Response, user: User):
    response.set_cookie(
        key=settings.ACCESS_COOKIE_NAME,
        value=create_access_token(user.id, user.password_hash),
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        domain=settings.COOKIE_DOMAIN,
        path="/",
    )

    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=create_refresh_token(user.id, user.password_hash),
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        domain=settings.COOKIE_DOMAIN,
        path="/",
    )


def clear_auth_cookies(response: Response):
    for cookie_name in (
        settings.ACCESS_COOKIE_NAME,
        settings.REFRESH_COOKIE_NAME,
        settings.CSRF_COOKIE_NAME,
    ):
        response.delete_cookie(
            key=cookie_name,
            path="/",
            domain=settings.COOKIE_DOMAIN,
            secure=settings.COOKIE_SECURE,
            httponly=cookie_name != settings.CSRF_COOKIE_NAME,
            samesite=settings.COOKIE_SAMESITE,
        )


@router.get("/csrf")
def get_csrf_token(response: Response):
    csrf_token = secrets.token_urlsafe(32)

    response.set_cookie(
        key=settings.CSRF_COOKIE_NAME,
        value=csrf_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        httponly=False,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        domain=settings.COOKIE_DOMAIN,
        path="/",
    )

    return {"csrf_token": csrf_token}


# Stage 10 sign-in throttling — interim policy while client question Q19
# (session and recovery policy) is open: after 5 failed attempts for one
# e-mail, or 30 from one address, within 15 minutes, further attempts are
# refused until the window passes. Every attempt is recorded (no password).
FAILED_LIMIT_PER_EMAIL = 5
FAILED_LIMIT_PER_IP = 30
THROTTLE_WINDOW = timedelta(minutes=15)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _throttled(db: Session, email: str, ip: str | None) -> int | None:
    """Seconds until the next attempt is allowed, or None."""
    since = datetime.now(timezone.utc) - THROTTLE_WINDOW
    checks = [(LoginAttempt.email == email, FAILED_LIMIT_PER_EMAIL)]
    if ip:
        checks.append((LoginAttempt.ip_address == ip, FAILED_LIMIT_PER_IP))
    for condition, limit in checks:
        rows = (db.query(LoginAttempt.created_at)
                .filter(condition, LoginAttempt.succeeded.is_(False), LoginAttempt.created_at >= since)
                .order_by(LoginAttempt.created_at.desc()).limit(limit).all())
        if len(rows) >= limit:
            oldest = rows[-1][0]
            if oldest.tzinfo is None:
                oldest = oldest.replace(tzinfo=timezone.utc)
            return max(1, int((oldest + THROTTLE_WINDOW - datetime.now(timezone.utc)).total_seconds()))
    return None


@router.post("/login", response_model=UserResponse)
def login(
    data: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    email = str(data.email).lower()
    ip = _client_ip(request)
    wait = _throttled(db, email, ip)
    if wait is not None:
        minutes = max(1, (wait + 59) // 60)
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed sign-in attempts. Try again in {minutes} minute{'s' if minutes != 1 else ''}.",
            headers={"Retry-After": str(wait)},
        )

    user = db.query(User).filter(User.email == data.email).first()
    ok = bool(user) and verify_password(data.password, user.password_hash)
    db.add(LoginAttempt(email=email, ip_address=ip, succeeded=bool(ok and user.is_active),
                        user_id=user.id if user else None))

    if not ok:
        db.commit()
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
        )

    if not user.is_active:
        db.commit()
        raise HTTPException(
            status_code=403,
            detail="Account is inactive",
        )

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    set_auth_cookies(response, user)

    return user


@router.post("/logout-all")
def logout_everywhere(
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Sign out on every device: every token issued until now is refused."""
    user.sessions_revoked_at = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(seconds=1)
    if user.campus_id is not None:
        db.add(AuditLog(campus_id=user.campus_id, user_id=user.id, action="SIGN_OUT_EVERYWHERE",
                        entity_type="USER", entity_id=user.id, details={}))
    db.commit()
    clear_auth_cookies(response)
    return {"message": "Signed out on every device."}


@router.post("/refresh", response_model=UserResponse)
def refresh_token(
    response: Response,
    refresh_token: str | None = __import__("fastapi").Cookie(
        default=None,
        alias=settings.REFRESH_COOKIE_NAME,
    ),
    db: Session = Depends(get_db),
):
    if not refresh_token:
        raise HTTPException(
            status_code=401,
            detail="Refresh token missing",
        )

    try:
        payload = decode_access_token(refresh_token)

        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=401,
                detail="Invalid refresh token",
            )

        user_id = int(payload["sub"])

    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired refresh token",
        )

    user = db.query(User).filter(User.id == user_id).first()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=401,
            detail="User is unavailable",
        )

    # A refresh token issued before a password reset carries the old
    # password fingerprint and can no longer renew the session.
    if not fingerprint_matches(payload, user.password_hash) or session_revoked(user, payload):
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired refresh token",
        )

    # Rotate both authentication cookies.
    set_auth_cookies(response, user)

    return user


@router.post("/logout")
def logout(response: Response):
    clear_auth_cookies(response)
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/users", response_model=UserResponse, status_code=201)
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(UserRole.ADMIN)),
):
    if data.role not in ADMIN_CREATABLE_ROLES:
        raise HTTPException(
            status_code=403,
            detail=(
                "Admins can create only Kitchen Manager and Staff accounts."
            ),
        )

    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(
            status_code=409,
            detail="Email already exists",
        )

    user = User(
        # Always the creating ADMIN's campus; never taken from the request.
        campus_id=admin.campus_id,
        full_name=data.full_name,
        email=data.email,
        password_hash=hash_password(data.password),
        role=UserRole(data.role),
    )

    db.add(user)
    db.flush()

    db.add(
        AuditLog(
            campus_id=admin.campus_id,
            user_id=admin.id,
            action="CREATE",
            entity_type="USER",
            entity_id=user.id,
            details={
                "email": user.email,
                "role": user.role.value,
            },
        )
    )

    db.commit()
    db.refresh(user)

    return user
