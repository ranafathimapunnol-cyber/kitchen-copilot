"""Password setup and reset by email.

Applies to the roles in SELF_SERVICE_PASSWORD_ROLES: campus ADMIN and the
platform SUPER_ADMIN (Stage 11; the role exists in the database only after
migration M1). Kitchen Manager and Staff passwords stay with their campus
ADMIN, as before. Events of platform accounts (no campus) go to the
platform audit log.

Links are signed tokens bound to the account's current password hash (see
app.core.security), so nothing is stored and no migration is needed.
"""

import hashlib
import html
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.core import email as email_transport
from app.core.config import settings
from app.core.rate_limit import password_rate_limiter
from app.core.security import (
    PASSWORD_RESET,
    PASSWORD_SETUP,
    InvalidPasswordToken,
    create_password_token,
    decode_password_token,
    fingerprint_matches,
    hash_password,
    is_password_usable,
    make_unusable_password,
)
from app.models.audit_log import AuditLog
from app.models.campus import Campus
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)

SELF_SERVICE_PASSWORD_ROLES = frozenset({UserRole.ADMIN, UserRole.SUPER_ADMIN})

FORGOT_PASSWORD_MESSAGE = (
    "If an eligible account exists for this email address, password reset "
    "instructions will be sent."
)
INVALID_LINK_MESSAGE = (
    "This link is invalid or has expired. Request a new one."
)

SETUP_PATH = "/set-password"
RESET_PATH = "/reset-password"

# Audit actions. Same shape as existing entries: action + entity_type
# "USER" + entity_id. Details never hold a password, hash or token.
AUDIT_PASSWORD_RESET_REQUESTED = "PASSWORD_RESET_REQUESTED"
AUDIT_PASSWORD_SETUP = "PASSWORD_SETUP"
AUDIT_PASSWORD_RESET = "PASSWORD_RESET"
AUDIT_PASSWORD_EMAIL_SENT = "PASSWORD_EMAIL_SENT"
AUDIT_PASSWORD_EMAIL_FAILED = "PASSWORD_EMAIL_FAILED"

EMAIL_TYPE_SETUP = "password_setup"
EMAIL_TYPE_RESET = "password_reset"
EMAIL_TYPE_CHANGED = "password_changed"

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class PasswordLinkConfigError(Exception):
    """FRONTEND_BASE_URL is missing or unsafe. The message is safe to log."""


class AccountProvisioningError(Exception):
    """Provisioning was refused or could not finish. Nothing was saved."""


# ============================================================
# ELIGIBILITY, LINKS AND AUDIT
# ============================================================

def is_self_service_eligible(user: User | None) -> bool:
    return (
        user is not None
        and user.is_active
        and user.role in SELF_SERVICE_PASSWORD_ROLES
    )


def build_frontend_link(path: str, token: str) -> str:
    """The link sent by email.

    The token travels in the URL fragment (#token=...). Browsers never send
    the fragment to a server, so it stays out of web server access logs and
    Referer headers.
    """
    base = (settings.FRONTEND_BASE_URL or "").strip()

    if not base:
        raise PasswordLinkConfigError("FRONTEND_BASE_URL is not configured.")

    parsed = urlsplit(base)

    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise PasswordLinkConfigError(
            "FRONTEND_BASE_URL must be an absolute http(s) URL."
        )

    if parsed.scheme != "https" and parsed.hostname not in _LOCAL_HOSTS:
        raise PasswordLinkConfigError(
            "FRONTEND_BASE_URL must use https outside local development."
        )

    return f"{base.rstrip('/')}{path}#token={token}"


def record_password_event(
    db: Session,
    user: User,
    action: str,
    actor_id: int | None = None,
    details: dict | None = None,
) -> None:
    """actor_id is the person who acted: the user themselves when they
    complete a link, None for an anonymous request or the operator CLI."""
    if user.campus_id is None:
        from app.models.platform import PlatformAuditLog

        db.add(PlatformAuditLog(actor_user_id=actor_id, actor_email=user.email, action=action,
                                target_type="USER", target_id=user.id, outcome="SUCCESS", details=details or {}))
        return
    db.add(
        AuditLog(
            campus_id=user.campus_id,
            user_id=actor_id,
            action=action,
            entity_type="USER",
            entity_id=user.id,
            details=details or {},
        )
    )


# ============================================================
# EMAIL CONTENT
# ============================================================

def _render(
    name: str,
    paragraphs: list[str],
    footer: str,
    link: str | None = None,
    link_label: str | None = None,
) -> tuple[str, str]:
    text_parts = [f"Hello {name},", *paragraphs]
    if link:
        text_parts.append(link)
    text_parts.extend([footer, "Kitchen Copilot"])
    text = "\n\n".join(text_parts) + "\n"

    safe = html.escape
    html_parts = [f"<p>Hello {safe(name)},</p>"]
    html_parts += [f"<p>{safe(paragraph)}</p>" for paragraph in paragraphs]
    if link:
        html_parts.append(
            f'<p><a href="{safe(link, quote=True)}" '
            'style="display:inline-block;padding:10px 18px;'
            "background:#2268c2;color:#ffffff;border-radius:8px;"
            'text-decoration:none;font-weight:600">'
            f"{safe(link_label or 'Open link')}</a></p>"
            '<p style="color:#64748b;font-size:13px">If the button does not '
            "work, copy this address into your browser:<br>"
            f"{safe(link)}</p>"
        )
    html_parts.append(
        f'<p style="color:#64748b;font-size:13px">{safe(footer)}</p>'
    )
    html_parts.append("<p>Kitchen Copilot</p>")
    body = (
        '<div style="font-family:system-ui,-apple-system,Segoe UI,sans-serif;'
        'font-size:15px;line-height:1.5;color:#0f172a;max-width:560px">'
        + "".join(html_parts)
        + "</div>"
    )
    return text, body


def setup_email_content(
    user: User, campus_name: str | None, link: str
) -> tuple[str, str, str]:
    where = f" for {campus_name}" if campus_name else ""
    text, body = _render(
        user.full_name,
        [
            "An administrator account has been created for you on "
            f"Kitchen Copilot{where}.",
            "To activate it, choose your password using the secure link "
            "below. No password is ever sent by email.",
            f"The link expires in {settings.PASSWORD_SETUP_TOKEN_EXPIRE_HOURS} "
            "hours and can be used once.",
        ],
        "If you weren't expecting this email, you can ignore it. Nobody can "
        "sign in to the account until a password is set.",
        link=link,
        link_label="Set your password",
    )
    return "Set up your Kitchen Copilot password", text, body


def reset_email_content(user: User, link: str) -> tuple[str, str, str]:
    text, body = _render(
        user.full_name,
        [
            "We received a request to reset the password for your Kitchen "
            "Copilot account.",
            "Use the secure link below within "
            f"{settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes. It can "
            "be used once.",
        ],
        "If you didn't ask for this, ignore this email. Your password won't "
        "change unless the link is used.",
        link=link,
        link_label="Reset your password",
    )
    return "Reset your Kitchen Copilot password", text, body


def changed_email_content(
    user: User, purpose: str, when: datetime
) -> tuple[str, str, str]:
    stamp = when.strftime("%d %b %Y at %H:%M UTC")

    if purpose == PASSWORD_SETUP:
        subject = "Your Kitchen Copilot password is set"
        paragraphs = [
            f"The password for {user.email} was set on {stamp}. Your account "
            "is ready to use.",
        ]
    else:
        subject = "Your Kitchen Copilot password was changed"
        paragraphs = [
            f"The password for {user.email} was reset on {stamp}.",
            "For your security, every device that was signed in to this "
            "account has been signed out.",
        ]

    text, body = _render(
        user.full_name,
        paragraphs,
        "If this wasn't you, contact your administrator immediately and "
        "reset your password.",
    )
    return subject, text, body


# ============================================================
# DELIVERY
# ============================================================

def _deliver(
    db: Session,
    user: User,
    email_type: str,
    subject: str,
    text: str,
    body: str,
) -> bool:
    """Sends one password email and audits the outcome. Never raises for a
    delivery failure; returns whether the server accepted the message."""
    try:
        email_transport.send_email(user.email, subject, text, body)
    except email_transport.EmailDeliveryError as exc:
        reason = (
            "not_configured"
            if isinstance(exc, email_transport.EmailNotConfiguredError)
            else "delivery_failed"
        )
        logger.warning(
            "Password email not delivered: type=%s user_id=%s reason=%s (%s)",
            email_type,
            user.id,
            reason,
            exc,
        )
        record_password_event(
            db,
            user,
            AUDIT_PASSWORD_EMAIL_FAILED,
            details={"email_type": email_type, "reason": reason},
        )
        return False

    record_password_event(
        db,
        user,
        AUDIT_PASSWORD_EMAIL_SENT,
        details={"email_type": email_type},
    )
    return True


def _campus_name(db: Session, user: User) -> str | None:
    if user.campus_id is None:
        return None
    campus = db.get(Campus, user.campus_id)
    return campus.name if campus else None


# ============================================================
# ADMIN PROVISIONING (operator CLI)
# ============================================================

def provision_admin(
    db: Session,
    campus: Campus,
    full_name: str,
    email: str,
) -> tuple[User, bool]:
    """Creates an ADMIN with no usable password and emails a setup link.

    Returns (user, created). For an ADMIN who never finished setup, a new
    link is sent instead, and every earlier setup link stops working.

    The account is committed only after the mail server accepts the setup
    email. If sending fails, everything is rolled back and
    AccountProvisioningError is raised, so no account is left unusable.
    """
    existing = db.query(User).filter(User.email == email).first()

    if existing:
        if existing.role != UserRole.ADMIN or existing.campus_id != campus.id:
            raise AccountProvisioningError(
                "This email address already belongs to another account."
            )

        if is_password_usable(existing.password_hash):
            raise AccountProvisioningError(
                "This administrator has already set a password. They can "
                "use Forgot password on the sign-in page."
            )

        user = existing
        user.password_hash = make_unusable_password()
        created = False
    else:
        user = User(
            campus_id=campus.id,
            full_name=full_name,
            email=email,
            password_hash=make_unusable_password(),
            role=UserRole.ADMIN,
            is_active=True,
        )
        db.add(user)
        db.flush()

        record_password_event(
            db,
            user,
            "CREATE",
            details={
                "email": user.email,
                "role": user.role.value,
                "provisioned_by": "operator",
            },
        )
        created = True

    try:
        token = create_password_token(
            user.id,
            user.password_hash,
            PASSWORD_SETUP,
            timedelta(hours=settings.PASSWORD_SETUP_TOKEN_EXPIRE_HOURS),
        )
        link = build_frontend_link(SETUP_PATH, token)
        subject, text, body = setup_email_content(
            user, _campus_name(db, user), link
        )
        email_transport.send_email(user.email, subject, text, body)
    except (
        email_transport.EmailDeliveryError,
        PasswordLinkConfigError,
    ) as exc:
        db.rollback()
        raise AccountProvisioningError(
            f"The setup email could not be sent, so nothing was saved. {exc}"
        ) from None

    record_password_event(
        db,
        user,
        AUDIT_PASSWORD_EMAIL_SENT,
        details={"email_type": EMAIL_TYPE_SETUP},
    )
    db.commit()
    db.refresh(user)

    return user, created


# ============================================================
# FORGOT PASSWORD
# ============================================================

def process_password_reset_request(
    session_factory: Callable[[], Session],
    email: str,
) -> None:
    """Runs after the response has been sent, so the response is the same,
    in content and timing, whether or not the account exists."""
    db = session_factory()

    try:
        user = db.query(User).filter(User.email == email).first()

        if not is_self_service_eligible(user):
            return

        email_key = hashlib.sha256(email.encode("utf-8")).hexdigest()

        if not password_rate_limiter.allow(
            f"password-reset:email:{email_key}",
            settings.PASSWORD_RESET_REQUESTS_PER_EMAIL,
            settings.PASSWORD_RATE_LIMIT_WINDOW_SECONDS,
        ):
            logger.info(
                "Password reset email suppressed by the per-account limit "
                "(user_id=%s).",
                user.id,
            )
            return

        record_password_event(db, user, AUDIT_PASSWORD_RESET_REQUESTED)

        token = create_password_token(
            user.id,
            user.password_hash,
            PASSWORD_RESET,
            timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
        )

        try:
            link = build_frontend_link(RESET_PATH, token)
        except PasswordLinkConfigError as exc:
            logger.error(
                "Password reset email not sent (user_id=%s): %s",
                user.id,
                exc,
            )
            record_password_event(
                db,
                user,
                AUDIT_PASSWORD_EMAIL_FAILED,
                details={
                    "email_type": EMAIL_TYPE_RESET,
                    "reason": "link_not_configured",
                },
            )
            db.commit()
            return

        subject, text, body = reset_email_content(user, link)
        _deliver(db, user, EMAIL_TYPE_RESET, subject, text, body)
        db.commit()

    except Exception:
        db.rollback()
        logger.exception("Password reset request could not be processed.")
    finally:
        db.close()


# ============================================================
# USING A LINK
# ============================================================

def _load_token_user(
    db: Session, token: str, purpose: str, lock: bool
) -> User:
    payload = decode_password_token(token, purpose)

    query = db.query(User).filter(User.id == int(payload["sub"]))
    if lock:
        # Serialises two submissions of the same link: the second sees the
        # new hash and fails the fingerprint check.
        query = query.with_for_update()
    user = query.first()

    if not is_self_service_eligible(user):
        raise InvalidPasswordToken()

    # Already used (the password changed since the link was issued).
    if not fingerprint_matches(payload, user.password_hash):
        raise InvalidPasswordToken()

    # A setup link is only for an account that has no password yet.
    if purpose == PASSWORD_SETUP and is_password_usable(user.password_hash):
        raise InvalidPasswordToken()

    return user


def check_password_token(db: Session, token: str, purpose: str) -> None:
    """Raises InvalidPasswordToken unless the link can still be used.
    Changes nothing."""
    _load_token_user(db, token, purpose, lock=False)


def complete_password_change(
    db: Session,
    token: str,
    new_password: str,
    purpose: str,
) -> User:
    """Sets the password from a valid link.

    The new hash changes the account's password fingerprint, which makes
    this link and every other outstanding link unusable, and invalidates
    every existing session token.
    """
    user = _load_token_user(db, token, purpose, lock=True)

    user.password_hash = hash_password(new_password)

    record_password_event(
        db,
        user,
        AUDIT_PASSWORD_SETUP if purpose == PASSWORD_SETUP else AUDIT_PASSWORD_RESET,
        actor_id=user.id,
    )
    db.commit()
    db.refresh(user)

    return user


def send_password_changed_email(
    db: Session, user: User, purpose: str
) -> bool:
    subject, text, body = changed_email_content(
        user, purpose, datetime.now(UTC)
    )
    delivered = _deliver(db, user, EMAIL_TYPE_CHANGED, subject, text, body)
    db.commit()
    return delivered
