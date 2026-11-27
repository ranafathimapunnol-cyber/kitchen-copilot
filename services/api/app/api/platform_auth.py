"""Platform (SUPER_ADMIN) authentication and audit — Stage 11.

Separation from campus sessions:
- Platform sessions live in their own cookie (PLATFORM_ACCESS_COOKIE_NAME)
  and are signed with their own derived key (core/security.py); a campus
  token is never accepted here and a platform token never by the campus API.
- get_current_user (campus) refuses every SUPER_ADMIN account, and
  require_permission / user_has_permission deny SUPER_ADMIN every campus
  permission, so a platform account has no campus operational access.
- Every platform route needs migration M1 (d5e8f0b2a314). Until it is
  applied the platform answers 503 and the campus application is unaffected.
"""

import jwt
from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_platform_token, fingerprint_matches
from app.db.session import get_db
from app.models.platform import PlatformAuditLog
from app.models.user import User, UserRole

PLATFORM_NOT_MIGRATED = ("Platform management is not available on this database yet: it needs migration "
                         "d5e8f0b2a314, which is awaiting authorization.")
_schema_ready = False


def platform_schema_ready(db: Session) -> bool:
    global _schema_ready
    if not _schema_ready:
        _schema_ready = inspect(db.get_bind()).has_table("platform_audit_logs")
    return _schema_ready


def require_platform_schema(db: Session = Depends(get_db)) -> None:
    if not platform_schema_ready(db):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=PLATFORM_NOT_MIGRATED)


def client_ip(request: Request | None) -> str | None:
    return request.client.host if request is not None and request.client else None


def record_platform_audit(db: Session, *, action: str, target_type: str, outcome: str = "SUCCESS",
                          actor: User | None = None, actor_email: str | None = None, target_id: int | None = None,
                          campus_id: int | None = None, request: Request | None = None,
                          details: dict | None = None) -> None:
    """Adds an append-only platform audit row (the caller commits)."""
    db.add(PlatformAuditLog(
        actor_user_id=actor.id if actor else None,
        actor_email=(actor.email if actor else actor_email),
        action=action, target_type=target_type, target_id=target_id, campus_id=campus_id,
        outcome=outcome, ip_address=client_ip(request), details=jsonable_encoder(details or {}),
    ))


def get_platform_user(
    _ready: None = Depends(require_platform_schema),
    platform_token: str | None = Cookie(default=None, alias=settings.PLATFORM_ACCESS_COOKIE_NAME),
    db: Session = Depends(get_db),
) -> User:
    from app.api.dependencies import session_revoked

    error = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Platform sign-in required",
                          headers={"WWW-Authenticate": "Cookie"})
    if not platform_token:
        raise error
    try:
        payload = decode_platform_token(platform_token)
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        raise error
    user = db.get(User, user_id)
    if (not user or not user.is_active or user.role != UserRole.SUPER_ADMIN or user.campus_id is not None
            or not fingerprint_matches(payload, user.password_hash) or session_revoked(user, payload)):
        raise error
    return user
