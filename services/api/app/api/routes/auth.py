import secrets

import jwt

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.dependencies import get_current_user, require_roles
from app.core.config import settings
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_access_token,
)
from app.models.user import User, UserRole
from app.models.audit_log import AuditLog
from app.schemas.auth import LoginRequest, UserCreate, UserResponse


router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def set_auth_cookies(response: Response, user_id: int):
    response.set_cookie(
        key=settings.ACCESS_COOKIE_NAME,
        value=create_access_token(user_id),
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        domain=settings.COOKIE_DOMAIN,
        path="/",
    )

    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=create_refresh_token(user_id),
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


@router.post("/login", response_model=UserResponse)
def login(
    data: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == data.email).first()

    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="Account is inactive",
        )

    set_auth_cookies(response, user.id)

    return user


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

    # Rotate both authentication cookies.
    set_auth_cookies(response, user.id)

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
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(
            status_code=409,
            detail="Email already exists",
        )

    user = User(
        campus_id=admin.campus_id,
        full_name=data.full_name,
        email=data.email,
        password_hash=hash_password(data.password),
        role=data.role,
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
