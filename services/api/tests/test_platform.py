"""Stage 11 / Phase 2: organisation-level platform (SUPER_ADMIN).

Separate sign-in and session, no campus access for platform accounts, no
platform access for campus accounts, organisation scoping, campus lifecycle
without data loss, append-only platform audit, health without secrets, and
the ERP adapter's not-configured / contract-pending behaviour.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, text
from sqlalchemy.exc import DBAPIError

from app.api import platform_auth
from app.core.config import settings
from app.core.security import create_access_token, create_platform_token
from app.models import AuditLog, Campus, Organization, User
from app.models.platform import CampusIntegration, ErpHeadcountImport, ErpSyncRun, PlatformAuditIsAppendOnly, PlatformAuditLog
from app.models.purchases import Purchase
from app.models.user import UserRole
from app.services import erp_headcount

from tests.test_operational_authority import PASSWORD_HASH, act_as, client, db, world  # noqa: F401

P = "/api/platform"
PASSWORD = "Password123!"


def ok(response, code=200):
    assert response.status_code == code, response.text
    return response.json()


@pytest.fixture
def root(db, world):
    user = User(campus_id=None, full_name="Platform Owner", email="root@test.com", password_hash=PASSWORD_HASH,
                role=UserRole.SUPER_ADMIN, is_active=True)
    db.add(user)
    db.commit()
    return user


def platform_as(client, user):
    client.cookies.clear()
    client.cookies.set(settings.PLATFORM_ACCESS_COOKIE_NAME, create_platform_token(user.id, user.password_hash))
    csrf = client.get("/api/auth/csrf").json()["csrf_token"]
    client.headers.update({settings.CSRF_HEADER_NAME: csrf})


def audits(db, action=None):
    query = db.query(PlatformAuditLog)
    if action:
        query = query.filter(PlatformAuditLog.action == action)
    return query.order_by(PlatformAuditLog.id).all()


# ---------------- sign-in and sessions ----------------

def test_platform_sign_in_sets_a_separate_session_and_is_audited(client, db, root):
    me = ok(client.post(f"{P}/auth/login", json={"email": "ROOT@test.com", "password": PASSWORD}))
    assert me["role"] == "SUPER_ADMIN" and me["session_minutes"] == settings.PLATFORM_SESSION_MINUTES
    assert settings.PLATFORM_ACCESS_COOKIE_NAME in client.cookies
    assert settings.ACCESS_COOKIE_NAME not in client.cookies          # no campus session
    assert ok(client.get(f"{P}/auth/me"))["email"] == "root@test.com"
    [login] = audits(db, "LOGIN")
    assert (login.actor_user_id, login.outcome) == (root.id, "SUCCESS")

    ok(client.post(f"{P}/auth/logout"))
    assert client.get(f"{P}/auth/me").status_code == 401
    assert audits(db, "LOGOUT")[0].outcome == "SUCCESS"


def test_logout_revokes_the_token_itself(client, db, root):
    token = create_platform_token(root.id, root.password_hash)
    platform_as(client, root)
    ok(client.post(f"{P}/auth/logout"))
    client.cookies.set(settings.PLATFORM_ACCESS_COOKIE_NAME, token)   # replaying the old token
    assert client.get(f"{P}/auth/me").status_code == 401


@pytest.mark.parametrize("who", ["admin", "manager", "staff"])
def test_campus_accounts_cannot_use_the_platform_sign_in(client, db, world, root, who):
    user = getattr(world.a, who)
    response = client.post(f"{P}/auth/login", json={"email": user.email, "password": PASSWORD})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password for a platform account."
    [failure] = audits(db, "LOGIN")
    assert failure.outcome == "FAILURE" and failure.details["reason"] == "not_platform_account"


def test_failed_platform_sign_ins_are_audited_and_throttled(client, db, root):
    for _ in range(5):
        assert client.post(f"{P}/auth/login", json={"email": "root@test.com", "password": "wrong"}).status_code == 401
    assert client.post(f"{P}/auth/login", json={"email": "root@test.com", "password": PASSWORD}).status_code == 429
    outcomes = [a.outcome for a in audits(db, "LOGIN")]
    assert outcomes == ["FAILURE"] * 5 + ["DENIED"]
    assert all(a.actor_email == "root@test.com" for a in audits(db, "LOGIN"))


def test_super_admin_cannot_sign_in_or_act_on_the_campus_side(client, db, world, root):
    # Campus sign-in refuses the platform account (even with the right password).
    response = client.post("/api/auth/login", json={"email": "root@test.com", "password": PASSWORD})
    assert response.status_code == 403 and "platform sign-in" in response.json()["detail"]
    # A campus-style token for a SUPER_ADMIN is refused everywhere on the campus side.
    act_as(client, root)
    for path in ("/api/auth/me", "/api/dashboard/overview", "/api/master/items", "/api/purchases", "/api/agent/status",
                 "/api/audit", "/api/admin/users"):
        assert client.get(path).status_code == 401, path
    # A platform session gives no campus access either.
    platform_as(client, root)
    for path in ("/api/auth/me", "/api/dashboard/overview", "/api/master/items", "/api/purchase-orders"):
        assert client.get(path).status_code == 401, path


@pytest.mark.parametrize("who", ["admin", "manager", "staff"])
def test_campus_users_cannot_reach_platform_routes(client, world, root, who):
    act_as(client, getattr(world.a, who))
    for path in ("/auth/me", "/overview", "/campuses", "/users", "/audit", "/integrations", "/health", "/analytics"):
        assert client.get(f"{P}{path}").status_code == 401, path
    assert client.post(f"{P}/campuses", json={"name": "Sneaky", "code": "SNK"}).status_code == 401
    assert client.post(f"{P}/campuses/{world.b.campus.id}/deactivate", json={"reason": "nope"}).status_code == 401


def test_a_campus_token_is_not_a_platform_token(client, world, root):
    client.cookies.set(settings.PLATFORM_ACCESS_COOKIE_NAME, create_access_token(root.id, root.password_hash))
    assert client.get(f"{P}/auth/me").status_code == 401


# ---------------- campuses ----------------

def test_register_view_edit_campus_with_duplicate_protection(client, db, world, root):
    platform_as(client, root)
    created = ok(client.post(f"{P}/campuses", json={
        "name": "  Hill   Campus ", "code": "hill-1", "address": "1 Ridge Road", "contact_name": "Asha",
        "contact_email": "Office@Hill-School.example.com", "contact_phone": "+91 98765 43210"}), 201)
    assert (created["name"], created["code"], created["contact_email"]) == ("Hill Campus", "HILL-1", "office@hill-school.example.com")
    assert client.post(f"{P}/campuses", json={"name": "hill campus", "code": "OTHER"}).status_code == 409
    assert client.post(f"{P}/campuses", json={"name": "Another", "code": "Hill-1"}).status_code == 409
    assert client.post(f"{P}/campuses", json={"name": "Bad", "code": "has space"}).status_code == 422
    assert client.post(f"{P}/campuses", json={"name": "Bad", "code": "BAD", "contact_phone": "call me"}).status_code == 422

    detail = ok(client.get(f"{P}/campuses/{created['id']}"))
    assert detail["users"]["total"] == 0 and detail["erp"]["state"] == "NOT_CONFIGURED"
    assert {"critical"} == {a["level"] for a in detail["alerts"]}        # no Admin yet

    edited = ok(client.patch(f"{P}/campuses/{created['id']}", json={"name": "Hill Campus North", "contact_phone": ""}))
    assert edited["name"] == "Hill Campus North" and edited["contact_phone"] is None and edited["code"] == "HILL-1"
    assert client.patch(f"{P}/campuses/{created['id']}", json={"name": world.a.campus.name}).status_code == 409
    [create], [update] = audits(db, "CREATE"), audits(db, "UPDATE")
    assert create.campus_id == created["id"] and update.details["changes"]["name"]["to"] == "Hill Campus North"


def test_deactivating_a_campus_keeps_everything_and_blocks_its_users(client, db, world, root):
    a = world.a
    counts = lambda: {  # noqa: E731
        "users": db.query(func.count(User.id)).filter(User.campus_id == a.campus.id).scalar(),
        "bills": db.query(func.count(Purchase.id)).filter(Purchase.campus_id == a.campus.id).scalar(),
        "audit": db.query(func.count(AuditLog.id)).filter(AuditLog.campus_id == a.campus.id).scalar(),
    }
    before = counts()
    platform_as(client, root)
    ok(client.post(f"{P}/campuses/{a.campus.id}/deactivate", json={"reason": "Term closed"}))
    assert client.post(f"{P}/campuses/{a.campus.id}/deactivate", json={"reason": "again"}).status_code == 409
    db.expire_all()
    assert counts() == before
    assert all(u.is_active for u in db.query(User).filter(User.campus_id == a.campus.id))  # accounts untouched

    # Existing sessions and new sign-ins of that campus are refused; campus B is unaffected.
    act_as(client, a.manager)
    assert client.get("/api/auth/me").status_code == 403
    client.cookies.clear()
    client.headers.update({settings.CSRF_HEADER_NAME: client.get("/api/auth/csrf").json()["csrf_token"]})
    login = client.post("/api/auth/login", json={"email": a.manager.email, "password": PASSWORD})
    assert login.status_code == 403 and "deactivated" in login.json()["detail"]
    act_as(client, world.b.manager)
    assert client.get("/api/auth/me").status_code == 200

    platform_as(client, root)
    ok(client.post(f"{P}/campuses/{a.campus.id}/activate"))
    act_as(client, a.manager)
    assert client.get("/api/auth/me").status_code == 200
    assert [x.action for x in audits(db) if x.target_type == "CAMPUS"] == ["DEACTIVATE", "ACTIVATE"]
    assert audits(db, "DEACTIVATE")[0].details["reason"] == "Term closed"


def test_overview_figures_come_from_the_database(client, db, world, root):
    platform_as(client, root)
    data = ok(client.get(f"{P}/overview", params={"date_from": "2026-11-01", "date_to": "2026-11-30"}))
    totals = data["totals"]
    assert (totals["campuses"], totals["active_campuses"], totals["inactive_campuses"]) == (2, 2, 0)
    assert totals["users"] == db.query(func.count(User.id)).filter(User.campus_id.isnot(None)).scalar() == 6
    expected = db.query(func.sum(Purchase.grand_total)).filter(
        Purchase.purchase_date.between(date(2026, 11, 1), date(2026, 11, 30))).scalar()
    assert Decimal(totals["purchases_total"]) == expected == Decimal("1500.00")
    by_code = {c["code"]: c for c in data["campuses"]}
    assert Decimal(by_code[world.a.campus.code]["purchases"]["total"]) == Decimal("1000.00")
    # Filters.
    one = ok(client.get(f"{P}/overview", params={"campus_id": world.b.campus.id}))
    assert [c["id"] for c in one["campuses"]] == [world.b.campus.id]
    october = ok(client.get(f"{P}/overview", params={"date_from": "2026-10-01", "date_to": "2026-10-31"}))
    assert october["totals"]["purchases_total"] == "0.00"
    assert client.get(f"{P}/overview", params={"date_from": "2026-11-30", "date_to": "2026-11-01"}).status_code == 422


def test_organisation_scoped_super_admin_sees_only_its_campuses(client, db, world, root):
    org = Organization(name="Hill Schools", code="HILL")
    db.add(org)
    db.flush()
    db.execute(text("UPDATE campuses SET organization_id = :o WHERE id = :c"), {"o": org.id, "c": world.a.campus.id})
    scoped = User(campus_id=None, organization_id=org.id, full_name="Hill Owner", email="hill@test.com",
                  password_hash=PASSWORD_HASH, role=UserRole.SUPER_ADMIN, is_active=True)
    db.add(scoped)
    db.commit()
    platform_as(client, scoped)
    assert [c["id"] for c in ok(client.get(f"{P}/campuses"))["items"]] == [world.a.campus.id]
    assert client.get(f"{P}/campuses/{world.b.campus.id}").status_code == 404
    assert client.post(f"{P}/campuses/{world.b.campus.id}/deactivate", json={"reason": "not mine"}).status_code == 404
    assert {u["campus_id"] for u in ok(client.get(f"{P}/users"))["items"]} == {world.a.campus.id}
    assert client.post(f"{P}/organizations", json={"name": "Other", "code": "OTH"}).status_code == 403
    created = ok(client.post(f"{P}/campuses", json={"name": "Hill Two", "code": "HILL2"}), 201)
    assert created["organization_id"] == org.id


def test_users_are_read_only_and_campus_scoped(client, db, world, root):
    platform_as(client, root)
    rows = ok(client.get(f"{P}/campuses/{world.a.campus.id}/users"))["items"]
    assert {r["role"] for r in rows} == {"ADMIN", "KITCHEN_MANAGER", "STAFF"}
    assert all(r["campus_id"] == world.a.campus.id for r in rows)
    assert all("password" not in "".join(r.keys()) for r in rows)
    staff = ok(client.get(f"{P}/users", params={"role": "STAFF"}))["items"]
    assert {r["campus_id"] for r in staff} == {world.a.campus.id, world.b.campus.id}
    assert [r["email"] for r in ok(client.get(f"{P}/users", params={"scope": "platform"}))["items"]] == ["root@test.com"]


def test_provisioning_a_campus_admin_needs_email_and_is_audited(client, db, world, root, monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", None)
    platform_as(client, root)
    response = client.post(f"{P}/campuses/{world.b.campus.id}/admins", json={"full_name": "New Admin", "email": "new.admin@example.com"})
    assert response.status_code == 503
    assert db.query(User).filter(User.email == "new.admin@example.com").count() == 0
    [row] = audits(db, "PROVISION_ADMIN")
    assert row.outcome == "FAILURE" and row.campus_id == world.b.campus.id


# ---------------- audit ----------------

def test_platform_audit_is_append_only(client, db, root):
    client.post(f"{P}/auth/login", json={"email": "root@test.com", "password": PASSWORD})
    row = audits(db)[0]
    row.outcome = "FAILURE"
    with pytest.raises(PlatformAuditIsAppendOnly):
        db.flush()
    db.rollback()
    with pytest.raises(DBAPIError):
        db.execute(text("UPDATE platform_audit_logs SET outcome = 'X'"))
    db.rollback()
    with pytest.raises(DBAPIError):
        db.execute(text("DELETE FROM platform_audit_logs"))
    db.rollback()
    assert len(audits(db)) == 1


def test_audit_viewer_filters(client, db, world, root):
    platform_as(client, root)
    ok(client.post(f"{P}/campuses/{world.a.campus.id}/deactivate", json={"reason": "check"}))
    client.post(f"{P}/auth/login", json={"email": "nobody@test.com", "password": "x"})
    page = ok(client.get(f"{P}/audit"))
    assert page["total"] == 2
    assert [r["action"] for r in ok(client.get(f"{P}/audit", params={"outcome": "FAILURE"}))["items"]] == ["LOGIN"]
    assert [r["action"] for r in ok(client.get(f"{P}/audit", params={"campus_id": world.a.campus.id}))["items"]] == ["DEACTIVATE"]


# ---------------- health and integrations ----------------

def test_health_reports_status_without_secrets(client, db, root, monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "secret-gemini-key-123")
    monkeypatch.setattr(settings, "AGENT_ENABLED", True)
    monkeypatch.setattr(settings, "ERP_HEADCOUNT_API_TOKEN", "secret-erp-token-456")
    platform_as(client, root)
    response = client.get(f"{P}/health")
    body = response.text
    for secret in ("secret-gemini-key-123", "secret-erp-token-456", settings.SECRET_KEY, settings.DATABASE_URL):
        assert secret not in body
    checks = {c["key"]: c for c in response.json()["checks"]}
    assert checks["database"]["state"] == "ok" and checks["erp"]["state"] == "not_configured"
    assert set(checks) >= {"api", "database", "jobs", "ai", "storage", "email", "erp", "campuses"}


def test_erp_not_configured_then_contract_pending_and_never_fabricated(client, db, world, root, monkeypatch):
    platform_as(client, root)
    campus = world.a.campus.id
    items = ok(client.get(f"{P}/integrations"))["items"]
    assert {i["state"] for i in items} == {"NOT_CONFIGURED"} and all(i["label"] == "ERP connection not configured" for i in items)
    run = ok(client.post(f"{P}/campuses/{campus}/integrations/erp-headcount/sync"))
    assert run["status"] == "NOT_CONFIGURED" and run["records_received"] == 0

    assert client.put(f"{P}/campuses/{campus}/integrations/erp-headcount",
                      json={"is_enabled": True, "base_url": "http://plain-http.example"}).status_code == 422
    ok(client.put(f"{P}/campuses/{campus}/integrations/erp-headcount",
                  json={"is_enabled": True, "base_url": "https://erp.campus.example/api"}))
    still = ok(client.get(f"{P}/integrations"))
    assert still["credential"] == "not set"
    assert next(i for i in still["items"] if i["campus_id"] == campus)["state"] == "NOT_CONFIGURED"

    monkeypatch.setattr(settings, "ERP_HEADCOUNT_API_TOKEN", "tok-789")
    status = next(i for i in ok(client.get(f"{P}/integrations"))["items"] if i["campus_id"] == campus)
    assert status["state"] == "AWAITING_CONTRACT" and "tok-789" not in str(status)
    run = ok(client.post(f"{P}/campuses/{campus}/integrations/erp-headcount/sync"))
    assert run["status"] == "CONTRACT_PENDING" and run["records_applied"] == 0
    assert db.query(ErpHeadcountImport).count() == 0
    assert [a.action for a in audits(db) if a.target_type == "CAMPUS_INTEGRATION"] == [
        "ERP_SYNC", "CONFIGURE_INTEGRATION", "ERP_SYNC"]


def test_erp_import_plan_is_idempotent(db, world):
    a = world.a.campus.id
    rec = lambda key, count: erp_headcount.HeadcountRecord(key, date(2026, 11, 27), 1, count)  # noqa: E731
    db.add(ErpHeadcountImport(campus_id=a, external_key="K1", payload_hash=rec("K1", 100).content_hash()))
    db.add(ErpHeadcountImport(campus_id=a, external_key="K2", payload_hash=rec("K2", 50).content_hash()))
    db.commit()
    plan = erp_headcount.plan_imports(db, a, [rec("K1", 100), rec("K2", 55), rec("K3", 10), rec("K3", 11)])
    assert [r.external_key for r in plan["unchanged"]] == ["K1"]
    assert [r.external_key for r in plan["changed"]] == ["K2"]
    assert [(r.external_key, r.count) for r in plan["new"]] == [("K3", 10)]
    assert [(r.external_key, r.count) for r in plan["duplicate"]] == [("K3", 11)]
    # Another campus's imports never count.
    assert [r.external_key for r in erp_headcount.plan_imports(db, world.b.campus.id, [rec("K1", 100)])["new"]] == ["K1"]


def test_erp_transport_retries_times_out_and_redacts(monkeypatch):
    import httpx

    monkeypatch.setattr(settings, "ERP_HEADCOUNT_API_TOKEN", "supersecret")
    calls = []

    def handler(request):
        calls.append(request.url)
        if len(calls) < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    factory = lambda **kw: httpx.Client(transport=httpx.MockTransport(handler), **kw)  # noqa: E731
    t = erp_headcount.Transport("https://erp.example", 5, 2, sleep=lambda s: None, client_factory=factory)
    assert t.get_json("/x") == {"ok": True} and len(calls) == 3

    def slow(request):
        raise httpx.ConnectTimeout("token=supersecret timed out")

    t = erp_headcount.Transport("https://erp.example", 5, 1, sleep=lambda s: None,
                                client_factory=lambda **kw: httpx.Client(transport=httpx.MockTransport(slow), **kw))
    with pytest.raises(erp_headcount.TransportError) as err:
        t.get_json("/x")
    assert "supersecret" not in str(err.value) and "2 attempts" in str(err.value)
    assert "supersecret" not in erp_headcount.redact("Authorization: Bearer supersecret token=supersecret")


# ---------------- not migrated ----------------

def test_platform_answers_503_before_migration(client, root, monkeypatch):
    monkeypatch.setattr(platform_auth, "_schema_ready", False)
    monkeypatch.setattr(platform_auth, "platform_schema_ready", lambda db: False)
    response = client.post(f"{P}/auth/login", json={"email": "root@test.com", "password": PASSWORD})
    assert response.status_code == 503 and "d5e8f0b2a314" in response.json()["detail"]


def test_a_new_platform_account_sets_its_password_by_link_and_it_is_platform_audited(client, db, world, monkeypatch):
    from datetime import timedelta

    from app.core.security import PASSWORD_SETUP, create_password_token, make_unusable_password

    user = User(campus_id=None, full_name="New Owner", email="owner@example.com", password_hash=make_unusable_password(),
                role=UserRole.SUPER_ADMIN, is_active=True)
    db.add(user)
    db.commit()
    token = create_password_token(user.id, user.password_hash, PASSWORD_SETUP, timedelta(hours=1))
    response = client.post("/api/auth/password/setup", json={"token": token, "new_password": "A-strong-pass-123",
                                                             "confirm_password": "A-strong-pass-123"})
    assert response.status_code == 200, response.text
    assert settings.ACCESS_COOKIE_NAME not in response.cookies          # no campus session is started
    assert db.query(AuditLog).filter(AuditLog.entity_id == user.id).count() == 0
    assert {a.target_id for a in audits(db) if a.target_type == "USER"} == {user.id}
    ok(client.post(f"{P}/auth/login", json={"email": "owner@example.com", "password": "A-strong-pass-123"}))
