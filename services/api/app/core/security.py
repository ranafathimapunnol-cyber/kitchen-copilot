
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

import jwt  # type: ignore
from pwdlib import PasswordHash  # type: ignore

from app.core.config import settings

password_hash = PasswordHash.recommended()


# ============================================================
# PASSWORD HASHING
# ============================================================

# A stored password_hash that starts with this marker matches no password.
# Accounts that have not set their first password carry one. Real hashes
# start with "$" (e.g. "$argon2id$"), so the two can never be confused.
UNUSABLE_PASSWORD_PREFIX = "!"


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def make_unusable_password() -> str:
    """A password_hash value that no password can match.

    The random part makes each value distinct, so issuing a new setup link
    (which stores a new value) invalidates every earlier setup link.
    """
    return UNUSABLE_PASSWORD_PREFIX + secrets.token_urlsafe(32)


def is_password_usable(stored_hash: str | None) -> bool:
    return bool(stored_hash) and not stored_hash.startswith(
        UNUSABLE_PASSWORD_PREFIX
    )


def verify_password(password: str, hashed: str) -> bool:
    # An account still waiting for its first password cannot sign in, and
    # the marker is not a hash the hasher could parse.
    if not is_password_usable(hashed):
        return False

    return password_hash.verify(password, hashed)


# ============================================================
# KEY DERIVATION
# ============================================================

def _derived_key(label: str) -> bytes:
    """A key for one purpose, derived from SECRET_KEY.

    Separate keys mean a session token can never verify as a password link
    and vice versa, even though both are signed JWTs.
    """
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        label.encode("utf-8"),
        hashlib.sha256,
    ).digest()


def password_fingerprint(stored_hash: str) -> str:
    """A keyed fingerprint of the stored password hash.

    It changes whenever the password changes. Session tokens and password
    links carry it, so changing the password invalidates every existing
    session and every outstanding link at once. It reveals nothing about
    the hash without SECRET_KEY.
    """
    return hmac.new(
        _derived_key("kitchen-copilot:password-fingerprint:v1"),
        stored_hash.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def fingerprint_matches(payload: dict, stored_hash: str) -> bool:
    claim = payload.get("pwd")

    return isinstance(claim, str) and hmac.compare_digest(
        claim,
        password_fingerprint(stored_hash),
    )


# ============================================================
# SESSION TOKENS
# ============================================================

def create_access_token(user_id: int, stored_hash: str) -> str:
    now = datetime.now(UTC)

    payload = {
        "sub": str(user_id),
        "type": "access",
        "jti": secrets.token_urlsafe(16),
        "pwd": password_fingerprint(stored_hash),
        "iat": now,
        "exp": now + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        ),
    }

    return jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm="HS256",
    )


def create_refresh_token(user_id: int, stored_hash: str) -> str:
    now = datetime.now(UTC)

    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "jti": secrets.token_urlsafe(16),
        "pwd": password_fingerprint(stored_hash),
        "iat": now,
        "exp": now + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        ),
    }

    return jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm="HS256",
    )


def decode_access_token(token: str) -> dict:
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=["HS256"],
    )


# ============================================================
# PASSWORD SETUP AND RESET TOKENS
# ============================================================

PASSWORD_SETUP = "password_setup"
PASSWORD_RESET = "password_reset"

_PASSWORD_TOKEN_KEY_LABEL = "kitchen-copilot:password-token:v1"


class InvalidPasswordToken(Exception):
    """The link is malformed, tampered with, expired, used or not for this
    purpose. Callers report all of these the same way."""


def create_password_token(
    user_id: int,
    stored_hash: str,
    purpose: str,
    expires_in: timedelta,
) -> str:
    """A signed, expiring, single-use link token.

    Nothing is stored. The token is bound to the account's current password
    hash, so the moment the password is set or reset the token (and any
    other outstanding one) stops verifying: that is what makes it single
    use. The random jti makes every token unpredictable.
    """
    now = datetime.now(UTC)

    payload = {
        "sub": str(user_id),
        "purpose": purpose,
        "pwd": password_fingerprint(stored_hash),
        "jti": secrets.token_urlsafe(16),
        "iat": now,
        "exp": now + expires_in,
    }

    return jwt.encode(
        payload,
        _derived_key(_PASSWORD_TOKEN_KEY_LABEL),
        algorithm="HS256",
    )


def decode_password_token(token: str, purpose: str) -> dict:
    """Verifies signature, expiry and purpose. Does not check the account;
    the caller must still compare the fingerprint with the stored hash."""
    try:
        payload = jwt.decode(
            token,
            _derived_key(_PASSWORD_TOKEN_KEY_LABEL),
            algorithms=["HS256"],
            options={"require": ["exp", "iat", "sub", "purpose", "pwd"]},
        )
        int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        raise InvalidPasswordToken() from None

    if payload.get("purpose") != purpose:
        raise InvalidPasswordToken()

    return payload
