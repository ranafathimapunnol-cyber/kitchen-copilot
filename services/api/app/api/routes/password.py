"""Password setup and reset endpoints. All are public (no session): the
signed link is the proof of identity. Every POST still needs the CSRF
token, like the rest of the API."""

from collections.abc import Callable
from typing import Literal

from fastapi import (  # type: ignore
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    Response,
)
from pydantic import BaseModel, Field, model_validator  # type: ignore
from sqlalchemy.orm import Session  # type: ignore

from app.core.config import settings
from app.core.rate_limit import password_rate_limiter
from app.core.security import (
    PASSWORD_RESET,
    PASSWORD_SETUP,
    InvalidPasswordToken,
)
from app.db.session import SessionLocal, get_db
from app.schemas.auth import AppEmail
from app.services.password_management import (
    FORGOT_PASSWORD_MESSAGE,
    INVALID_LINK_MESSAGE,
    check_password_token,
    complete_password_change,
    process_password_reset_request,
    send_password_changed_email,
)

router = APIRouter(
    prefix="/api/auth/password",
    tags=["Password management"],
)

PURPOSES = {"setup": PASSWORD_SETUP, "reset": PASSWORD_RESET}

TOO_MANY_REQUESTS = (
    "Too many requests. Please wait a few minutes and try again."
)


# ============================================================
# REQUEST AND RESPONSE MODELS
# ============================================================

class ForgotPasswordRequest(BaseModel):
    email: AppEmail


class PasswordLinkCheck(BaseModel):
    token: str = Field(min_length=16, max_length=2048)
    purpose: Literal["setup", "reset"]


class SetPasswordRequest(BaseModel):
    token: str = Field(min_length=16, max_length=2048)
    # The existing password policy: at least 8 characters (UserCreate).
    new_password: str = Field(min_length=8)
    confirm_password: str

    @model_validator(mode="after")
    def passwords_match(self):
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match.")
        return self


class MessageResponse(BaseModel):
    message: str


class PasswordChangedResponse(BaseModel):
    message: str
    confirmation_email_sent: bool


# ============================================================
# HELPERS
# ============================================================

def get_session_factory() -> Callable[[], Session]:
    """Sessions for work that runs after the response is sent."""
    return SessionLocal


def _clear_session_cookies(response: Response) -> None:
    """Drops this browser's session cookies.

    Unlike logout's clear_auth_cookies, the CSRF cookie is kept: it is not
    a credential, and the page that just reset the password still holds the
    matching token for its next request (signing in).
    """
    for cookie_name in (
        settings.ACCESS_COOKIE_NAME,
        settings.REFRESH_COOKIE_NAME,
    ):
        response.delete_cookie(
            key=cookie_name,
            path="/",
            domain=settings.COOKIE_DOMAIN,
            secure=settings.COOKIE_SECURE,
            httponly=True,
            samesite=settings.COOKIE_SAMESITE,
        )


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _enforce_limit(key: str, limit: int) -> None:
    window = settings.PASSWORD_RATE_LIMIT_WINDOW_SECONDS

    if not password_rate_limiter.allow(key, limit, window):
        raise HTTPException(
            status_code=429,
            detail=TOO_MANY_REQUESTS,
            headers={"Retry-After": str(window)},
        )


def _complete(
    purpose: str,
    data: SetPasswordRequest,
    request: Request,
    response: Response,
    db: Session,
) -> PasswordChangedResponse:
    _enforce_limit(
        f"password-token:ip:{_client_ip(request)}",
        settings.PASSWORD_TOKEN_ATTEMPTS_PER_IP,
    )

    try:
        user = complete_password_change(
            db, data.token, data.new_password, purpose
        )
    except InvalidPasswordToken:
        db.rollback()
        raise HTTPException(status_code=400, detail=INVALID_LINK_MESSAGE)

    # Every session token already fails its fingerprint check; also drop
    # this browser's cookies so the user lands on a clean sign-in.
    _clear_session_cookies(response)

    emailed = send_password_changed_email(db, user, purpose)

    if purpose == PASSWORD_SETUP:
        message = "Your password is set. Sign in with your new password."
    else:
        message = (
            "Your password has been reset and every signed-in session has "
            "been signed out. Sign in with your new password."
        )

    return PasswordChangedResponse(
        message=message,
        confirmation_email_sent=emailed,
    )


# ============================================================
# ENDPOINTS
# ============================================================

@router.post("/forgot", status_code=202, response_model=MessageResponse)
def forgot_password(
    data: ForgotPasswordRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    session_factory: Callable[[], Session] = Depends(get_session_factory),
):
    _enforce_limit(
        f"password-reset:ip:{_client_ip(request)}",
        settings.PASSWORD_RESET_REQUESTS_PER_IP,
    )

    # The account lookup, the per-account limit and the email all run
    # after the response is sent. The response never depends on them.
    background_tasks.add_task(
        process_password_reset_request,
        session_factory,
        data.email,
    )

    return MessageResponse(message=FORGOT_PASSWORD_MESSAGE)


@router.post("/verify")
def verify_password_link(
    data: PasswordLinkCheck,
    request: Request,
    db: Session = Depends(get_db),
):
    """Lets the page tell the user a link is dead before they type."""
    _enforce_limit(
        f"password-token:ip:{_client_ip(request)}",
        settings.PASSWORD_TOKEN_ATTEMPTS_PER_IP,
    )

    try:
        check_password_token(db, data.token, PURPOSES[data.purpose])
    except InvalidPasswordToken:
        raise HTTPException(status_code=400, detail=INVALID_LINK_MESSAGE)

    return {"valid": True}


@router.post("/setup", response_model=PasswordChangedResponse)
def set_initial_password(
    data: SetPasswordRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    return _complete(PASSWORD_SETUP, data, request, response, db)


@router.post("/reset", response_model=PasswordChangedResponse)
def reset_password(
    data: SetPasswordRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    return _complete(PASSWORD_RESET, data, request, response, db)
