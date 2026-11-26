"""
Requirement 1 (ADMIN scope): account emails and secure password setup/reset.

Self-contained: an in-memory SQLite database and a mocked mailer, so these
tests need no PostgreSQL and send no email. Run them in isolation with

    pytest --noconftest tests/test_password_management.py

They define their own fixtures, which take precedence over conftest's
when the file runs as part of the full suite.

SUPER_ADMIN is not covered: the role does not exist yet (see
app/services/password_management.py).
"""

import json
import logging
import re
import smtplib
from datetime import timedelta
from types import SimpleNamespace

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.password import get_session_factory
from app.core import email as email_transport
from app.core.config import settings
from app.core.rate_limit import password_rate_limiter
from app.core.security import (
    PASSWORD_RESET,
    PASSWORD_SETUP,
    create_access_token,
    create_password_token,
    hash_password,
    is_password_usable,
    make_unusable_password,
    verify_password,
)
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import AuditLog, Campus, User, UserRole
from app.services import password_management as pm

PASSWORD = "CorrectHorse!42"
NEW_PASSWORD = "BatteryStaple#2026"
FRONTEND = "https://kitchen.example.com"
TOKEN_IN_LINK = re.compile(r"#token=([A-Za-z0-9_\-.]+)")


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _foreign_keys_on(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture
def db(session_factory):
    session = session_factory()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    """Email and links configured; nothing real is contacted."""
    monkeypatch.setattr(settings, "FRONTEND_BASE_URL", FRONTEND)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.mail.invalid")
    monkeypatch.setattr(settings, "EMAIL_FROM", "no-reply@test.com")
    password_rate_limiter.reset()
    yield
    password_rate_limiter.reset()


@pytest.fixture
def outbox(monkeypatch):
    sent = []

    def fake_send(to_address, subject, text_body, html_body=None):
        sent.append(
            {"to": to_address, "subject": subject,
             "text": text_body, "html": html_body}
        )

    monkeypatch.setattr(email_transport, "send_email", fake_send)
    return sent


def break_mailer(monkeypatch):
    def failing_send(*_args, **_kwargs):
        raise email_transport.EmailDeliveryError(
            "SMTP delivery failed (SMTPServerDisconnected)."
        )

    monkeypatch.setattr(email_transport, "send_email", failing_send)


@pytest.fixture
def people(db):
    campus = Campus(name="Zaitoon Test Campus", code="ZT-TEST")
    db.add(campus)
    db.flush()

    def make(role, email, active=True, usable=True):
        user = User(
            campus_id=campus.id,
            full_name=f"Test {role.value.title()}",
            email=email,
            password_hash=(
                hash_password(PASSWORD) if usable else make_unusable_password()
            ),
            role=role,
            is_active=active,
        )
        db.add(user)
        return user

    people = SimpleNamespace(
        campus=campus,
        admin=make(UserRole.ADMIN, "admin@test.com"),
        pending=make(UserRole.ADMIN, "new.admin@test.com", usable=False),
        manager=make(UserRole.KITCHEN_MANAGER, "manager@test.com"),
        staff=make(UserRole.STAFF, "staff@test.com"),
        inactive=make(UserRole.ADMIN, "former.admin@test.com", active=False),
    )
    db.commit()
    return people


@pytest.fixture
def client(db, session_factory):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_session_factory] = lambda: session_factory

    try:
        with TestClient(app) as test_client:
            csrf = test_client.get("/api/auth/csrf").json()["csrf_token"]
            test_client.headers.update({settings.CSRF_HEADER_NAME: csrf})
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_session_factory, None)


# ============================================================
# HELPERS
# ============================================================

def token_from(message) -> str:
    match = TOKEN_IN_LINK.search(message["text"])
    assert match, "no link in email"
    return match.group(1)


def reset_token(user) -> str:
    return create_password_token(
        user.id, user.password_hash, PASSWORD_RESET, timedelta(minutes=30)
    )


def actions(db, user) -> list[str]:
    db.expire_all()
    return [
        row.action
        for row in db.query(AuditLog)
        .filter(AuditLog.entity_type == "USER", AuditLog.entity_id == user.id)
        .order_by(AuditLog.id)
    ]


def login(client, email, password):
    return client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )


def submit(client, kind, token, password=NEW_PASSWORD, confirm=None):
    return client.post(
        f"/api/auth/password/{kind}",
        json={
            "token": token,
            "new_password": password,
            "confirm_password": password if confirm is None else confirm,
        },
    )


def stored_hash(db, user) -> str:
    db.expire_all()
    return db.get(User, user.id).password_hash


# ============================================================
# ADMIN PROVISIONING AND INITIAL SETUP
# ============================================================

def test_provisioned_admin_gets_setup_link_and_no_password(db, people, outbox):
    user, created = pm.provision_admin(
        db, people.campus, "Asha Admin", "asha@test.com"
    )

    assert created
    assert user.role == UserRole.ADMIN
    assert not is_password_usable(user.password_hash)

    assert len(outbox) == 1
    message = outbox[0]
    assert message["to"] == "asha@test.com"
    assert "Set up your Kitchen Copilot password" == message["subject"]
    assert f"{FRONTEND}/set-password#token=" in message["text"]
    assert "Zaitoon Test Campus" in message["text"]
    assert user.password_hash not in message["text"] + message["html"]

    assert actions(db, user) == ["CREATE", "PASSWORD_EMAIL_SENT"]


def test_provisioning_saves_nothing_when_setup_email_fails(
    db, people, monkeypatch
):
    break_mailer(monkeypatch)

    with pytest.raises(pm.AccountProvisioningError, match="nothing was saved"):
        pm.provision_admin(db, people.campus, "Asha Admin", "asha@test.com")

    assert db.query(User).filter(User.email == "asha@test.com").first() is None
    assert db.query(AuditLog).count() == 0


def test_provisioning_saves_nothing_without_frontend_url(
    db, people, outbox, monkeypatch
):
    monkeypatch.setattr(settings, "FRONTEND_BASE_URL", None)

    with pytest.raises(pm.AccountProvisioningError):
        pm.provision_admin(db, people.campus, "Asha Admin", "asha@test.com")

    assert outbox == []
    assert db.query(User).filter(User.email == "asha@test.com").first() is None


def test_resending_setup_disables_earlier_links(db, people, outbox, client):
    pm.provision_admin(db, people.campus, "Asha Admin", "asha@test.com")
    _user, created = pm.provision_admin(
        db, people.campus, "Asha Admin", "asha@test.com"
    )

    assert not created
    first, second = token_from(outbox[0]), token_from(outbox[1])

    assert submit(client, "setup", first).status_code == 400
    assert submit(client, "setup", second).status_code == 200


def test_provisioning_refuses_accounts_that_already_exist(db, people, outbox):
    with pytest.raises(pm.AccountProvisioningError, match="already set"):
        pm.provision_admin(db, people.campus, "Admin", "admin@test.com")

    with pytest.raises(pm.AccountProvisioningError, match="another account"):
        pm.provision_admin(db, people.campus, "Manager", "manager@test.com")

    assert outbox == []


def test_pending_admin_cannot_sign_in(client, people):
    for password in (PASSWORD, "", people.pending.password_hash):
        response = login(client, "new.admin@test.com", password or "x" * 8)
        assert response.status_code == 401


def test_initial_setup_sets_hashed_password_and_confirms(
    client, db, people, outbox
):
    user, _ = pm.provision_admin(db, people.campus, "Asha", "asha@test.com")

    response = submit(client, "setup", token_from(outbox[0]))

    assert response.status_code == 200
    assert response.json()["confirmation_email_sent"] is True

    saved = stored_hash(db, user)
    assert saved.startswith("$argon2")
    assert NEW_PASSWORD not in saved
    assert verify_password(NEW_PASSWORD, saved)

    assert outbox[-1]["subject"] == "Your Kitchen Copilot password is set"
    assert login(client, "asha@test.com", NEW_PASSWORD).status_code == 200

    assert actions(db, user)[-3:] == [
        "PASSWORD_EMAIL_SENT",
        "PASSWORD_SETUP",
        "PASSWORD_EMAIL_SENT",
    ]
    setup_row = (
        db.query(AuditLog).filter(AuditLog.action == "PASSWORD_SETUP").one()
    )
    assert setup_row.user_id == user.id


def test_setup_link_cannot_be_reused(client, db, people, outbox):
    pm.provision_admin(db, people.campus, "Asha", "asha@test.com")
    token = token_from(outbox[0])

    assert submit(client, "setup", token).status_code == 200

    reused = submit(client, "setup", token, password="Another#Pass99")
    assert reused.status_code == 400
    assert reused.json()["detail"] == pm.INVALID_LINK_MESSAGE
    assert login(client, "asha@test.com", NEW_PASSWORD).status_code == 200


def test_setup_and_reset_links_are_not_interchangeable(client, db, people, outbox):
    pm.provision_admin(db, people.campus, "Asha", "asha@test.com")
    setup_token = token_from(outbox[0])

    assert submit(client, "reset", setup_token).status_code == 400
    assert submit(client, "setup", reset_token(people.admin)).status_code == 400


# ============================================================
# INVALID AND EXPIRED LINKS
# ============================================================

@pytest.mark.parametrize("make_token", [
    lambda admin: "not-a-real-token-" * 3,
    lambda admin: reset_token(admin)[:-4] + "AAAA",
    lambda admin: create_access_token(admin.id, admin.password_hash),
    lambda admin: jwt.encode(
        {"sub": str(admin.id), "purpose": PASSWORD_RESET, "pwd": "x",
         "iat": 0, "exp": 9999999999},
        "guessed-secret",
        algorithm="HS256",
    ),
], ids=["garbage", "tampered", "session-token", "foreign-signature"])
def test_invalid_links_are_rejected(client, db, people, make_token):
    before = stored_hash(db, people.admin)

    response = submit(client, "reset", make_token(people.admin))

    assert response.status_code == 400
    assert response.json()["detail"] == pm.INVALID_LINK_MESSAGE
    assert stored_hash(db, people.admin) == before


def test_expired_link_is_rejected(client, db, people):
    before = stored_hash(db, people.admin)
    expired = create_password_token(
        people.admin.id,
        people.admin.password_hash,
        PASSWORD_RESET,
        timedelta(seconds=-1),
    )

    assert submit(client, "reset", expired).status_code == 400
    assert stored_hash(db, people.admin) == before


def test_verify_endpoint_reports_link_state(client, people):
    good = client.post(
        "/api/auth/password/verify",
        json={"token": reset_token(people.admin), "purpose": "reset"},
    )
    bad = client.post(
        "/api/auth/password/verify",
        json={"token": reset_token(people.admin), "purpose": "setup"},
    )

    assert good.status_code == 200 and good.json() == {"valid": True}
    assert bad.status_code == 400


# ============================================================
# FORGOT PASSWORD AND RESET
# ============================================================

@pytest.mark.parametrize("email", [
    "admin@test.com",
    "nobody@test.com",
    "manager@test.com",
    "staff@test.com",
    "former.admin@test.com",
])
def test_forgot_password_response_never_reveals_the_account(
    client, people, outbox, email
):
    response = client.post("/api/auth/password/forgot", json={"email": email})

    assert response.status_code == 202
    assert response.json() == {"message": pm.FORGOT_PASSWORD_MESSAGE}

    # Only an active ADMIN is emailed.
    expected = 1 if email == "admin@test.com" else 0
    assert len(outbox) == expected


def test_kitchen_manager_and_staff_cannot_use_password_links(
    client, db, people
):
    for user in (people.manager, people.staff):
        before = stored_hash(db, user)

        for kind, purpose in (("reset", PASSWORD_RESET), ("setup", PASSWORD_SETUP)):
            token = create_password_token(
                user.id, user.password_hash, purpose, timedelta(minutes=5)
            )
            assert submit(client, kind, token).status_code == 400

        assert stored_hash(db, user) == before


def test_reset_signs_out_every_existing_session(client, db, people, outbox):
    assert login(client, "admin@test.com", PASSWORD).status_code == 200
    old_access = client.cookies.get(settings.ACCESS_COOKIE_NAME)
    old_refresh = client.cookies.get(settings.REFRESH_COOKIE_NAME)
    assert client.get("/api/auth/me").status_code == 200

    client.post("/api/auth/password/forgot", json={"email": "admin@test.com"})
    response = submit(client, "reset", token_from(outbox[0]))

    assert response.status_code == 200
    assert "signed out" in response.json()["message"]
    assert response.json()["confirmation_email_sent"] is True
    assert outbox[-1]["subject"] == "Your Kitchen Copilot password was changed"

    client.cookies.set(settings.ACCESS_COOKIE_NAME, old_access)
    assert client.get("/api/auth/me").status_code == 401

    client.cookies.set(settings.REFRESH_COOKIE_NAME, old_refresh)
    assert client.post("/api/auth/refresh").status_code == 401

    # Drop the replayed cookies (set by hand, so under a different cookie
    # domain than the server's) before signing in fresh.
    client.cookies.delete(settings.ACCESS_COOKIE_NAME)
    client.cookies.delete(settings.REFRESH_COOKIE_NAME)

    assert login(client, "admin@test.com", PASSWORD).status_code == 401
    assert login(client, "admin@test.com", NEW_PASSWORD).status_code == 200
    assert client.get("/api/auth/me").status_code == 200

    assert actions(db, people.admin) == [
        "PASSWORD_RESET_REQUESTED",
        "PASSWORD_EMAIL_SENT",
        "PASSWORD_RESET",
        "PASSWORD_EMAIL_SENT",
    ]


def test_using_one_reset_link_disables_the_others(client, people, outbox):
    for _ in range(2):
        client.post("/api/auth/password/forgot", json={"email": "admin@test.com"})

    first, second = token_from(outbox[0]), token_from(outbox[1])
    assert first != second

    assert submit(client, "reset", second).status_code == 200
    assert submit(client, "reset", first).status_code == 400


def test_sessions_issued_without_a_fingerprint_are_rejected(client, people):
    legacy = jwt.encode(
        {"sub": str(people.admin.id), "type": "access",
         "iat": 0, "exp": 9999999999},
        settings.SECRET_KEY,
        algorithm="HS256",
    )
    client.cookies.set(settings.ACCESS_COOKIE_NAME, legacy)

    assert client.get("/api/auth/me").status_code == 401


@pytest.mark.parametrize("password, confirm", [
    ("short7!", "short7!"),
    (NEW_PASSWORD, NEW_PASSWORD + "x"),
])
def test_password_policy_is_enforced(client, db, people, password, confirm):
    before = stored_hash(db, people.admin)

    response = submit(
        client, "reset", reset_token(people.admin), password, confirm
    )

    assert response.status_code == 422
    assert stored_hash(db, people.admin) == before


# ============================================================
# EMAIL FAILURES
# ============================================================

def test_reset_email_failure_is_audited_not_revealed(
    client, db, people, monkeypatch
):
    break_mailer(monkeypatch)

    response = client.post(
        "/api/auth/password/forgot", json={"email": "admin@test.com"}
    )

    assert response.status_code == 202
    assert response.json() == {"message": pm.FORGOT_PASSWORD_MESSAGE}

    failed = (
        db.query(AuditLog)
        .filter(AuditLog.action == "PASSWORD_EMAIL_FAILED")
        .one()
    )
    assert failed.details == {
        "email_type": "password_reset",
        "reason": "delivery_failed",
    }


def test_missing_frontend_url_blocks_reset_email(
    client, db, people, outbox, monkeypatch
):
    monkeypatch.setattr(settings, "FRONTEND_BASE_URL", None)

    client.post("/api/auth/password/forgot", json={"email": "admin@test.com"})

    assert outbox == []
    assert actions(db, people.admin) == [
        "PASSWORD_RESET_REQUESTED",
        "PASSWORD_EMAIL_FAILED",
    ]


def test_failed_confirmation_email_is_reported_honestly(
    client, db, people, monkeypatch
):
    token = reset_token(people.admin)
    break_mailer(monkeypatch)

    response = submit(client, "reset", token)

    assert response.status_code == 200
    assert response.json()["confirmation_email_sent"] is False
    assert verify_password(NEW_PASSWORD, stored_hash(db, people.admin))
    assert actions(db, people.admin)[-1] == "PASSWORD_EMAIL_FAILED"


# ============================================================
# RATE LIMITS
# ============================================================

def test_forgot_password_is_limited_per_client(client, people, outbox, monkeypatch):
    monkeypatch.setattr(settings, "PASSWORD_RESET_REQUESTS_PER_IP", 2)

    codes = [
        client.post(
            "/api/auth/password/forgot", json={"email": "nobody@test.com"}
        ).status_code
        for _ in range(3)
    ]

    assert codes == [202, 202, 429]


def test_per_account_limit_is_silent(client, people, outbox, monkeypatch):
    monkeypatch.setattr(settings, "PASSWORD_RESET_REQUESTS_PER_EMAIL", 2)

    responses = [
        client.post(
            "/api/auth/password/forgot", json={"email": "admin@test.com"}
        )
        for _ in range(4)
    ]

    assert {r.status_code for r in responses} == {202}
    assert len({json.dumps(r.json()) for r in responses}) == 1
    assert len(outbox) == 2


def test_link_attempts_are_limited_per_client(client, people, monkeypatch):
    monkeypatch.setattr(settings, "PASSWORD_TOKEN_ATTEMPTS_PER_IP", 3)

    codes = [submit(client, "reset", "x" * 40).status_code for _ in range(4)]

    assert codes == [400, 400, 400, 429]


# ============================================================
# SECRETS STAY OUT OF RECORDS AND LOGS
# ============================================================

def test_no_token_or_password_in_audit_or_logs(
    client, db, people, outbox, monkeypatch, caplog
):
    caplog.set_level(logging.DEBUG)

    client.post("/api/auth/password/forgot", json={"email": "admin@test.com"})
    token = token_from(outbox[0])

    break_mailer(monkeypatch)
    assert submit(client, "reset", token).status_code == 200

    secrets_ = [token, NEW_PASSWORD, PASSWORD, stored_hash(db, people.admin)]

    audit_text = json.dumps(
        [row.details for row in db.query(AuditLog).all()]
    )
    for secret in secrets_:
        assert secret not in audit_text
        assert secret not in caplog.text

    assert "PASSWORD_EMAIL_FAILED" in actions(db, people.admin)


def test_links_are_unpredictable_and_carry_no_secrets(people):
    first, second = reset_token(people.admin), reset_token(people.admin)

    assert first != second
    for token in (first, second):
        assert people.admin.password_hash not in token
        assert PASSWORD not in token


# ============================================================
# LINK BASE URL AND SMTP TRANSPORT
# ============================================================

@pytest.mark.parametrize("base, ok", [
    ("https://kitchen.example.com", True),
    ("https://kitchen.example.com/", True),
    ("http://localhost:3000", True),
    ("http://kitchen.example.com", False),
    ("kitchen.example.com", False),
    (None, False),
])
def test_links_require_https_outside_localhost(monkeypatch, base, ok):
    monkeypatch.setattr(settings, "FRONTEND_BASE_URL", base)

    if ok:
        link = pm.build_frontend_link("/reset-password", "abc")
        assert link == f"{base.rstrip('/')}/reset-password#token=abc"
    else:
        with pytest.raises(pm.PasswordLinkConfigError):
            pm.build_frontend_link("/reset-password", "abc")


class FakeSMTP:
    instances = []
    fail_with = None

    def __init__(self, host, port, timeout):
        self.calls = [("connect", host, port)]
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context):
        self.calls.append(("starttls",))

    def login(self, username, password):
        self.calls.append(("login", username, password))

    def send_message(self, message):
        if FakeSMTP.fail_with:
            raise FakeSMTP.fail_with
        self.calls.append(("send", message["To"], message["Subject"]))
        return {}


def test_smtp_transport_uses_starttls_and_hides_credentials(monkeypatch):
    from pydantic import SecretStr

    monkeypatch.setattr(settings, "SMTP_USERNAME", "mailer")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", SecretStr("s3cret-smtp"))
    monkeypatch.setattr(email_transport.smtplib, "SMTP", FakeSMTP)
    FakeSMTP.instances, FakeSMTP.fail_with = [], None

    email_transport.send_email("admin@test.com", "Subject", "Body")

    calls = FakeSMTP.instances[0].calls
    assert [call[0] for call in calls] == ["connect", "starttls", "login", "send"]
    assert ("login", "mailer", "s3cret-smtp") in calls

    FakeSMTP.fail_with = smtplib.SMTPAuthenticationError(
        535, b"5.7.8 credentials for mailer rejected"
    )
    with pytest.raises(email_transport.EmailDeliveryError) as raised:
        email_transport.send_email("admin@test.com", "Subject", "Body")

    assert "s3cret-smtp" not in str(raised.value)
    assert "rejected" not in str(raised.value)
    assert raised.value.__cause__ is None
    FakeSMTP.fail_with = None


def test_unconfigured_email_is_reported_as_failure(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", None)

    with pytest.raises(email_transport.EmailNotConfiguredError):
        email_transport.send_email("admin@test.com", "Subject", "Body")
