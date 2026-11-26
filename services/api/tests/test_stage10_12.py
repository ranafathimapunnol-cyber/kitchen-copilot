"""
Stages 10 and 12: security and user accounts, audit viewer, and the
Kitchen Copilot agent (Stage 11 platform tests: test_stage11_platform.py,
with migration M1). In-memory SQLite with the
shared fixtures (campus A and B; ADMIN, KITCHEN_MANAGER, STAFF each).
The agent runs with the built-in rule reader (no network); the external
model path is exercised with a FakeLLM.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.agent import engine, intent as agent_intent
from app.core.clock import campus_today
from app.core.config import settings
from app.core.security import create_access_token
from app.models import AuditLog, User
from app.models.agent import AgentProposal, AgentStep
from app.models.planning import MealPlan
from app.models.purchases import Purchase, PurchaseItem, PurchaseOrder
from app.models.security import LoginAttempt
from app.models.stock import StockAdjustment
from app.models.user import UserRole

from tests.test_kitchen_issues import kitchen  # noqa: F401 (fixture)
from tests.test_operational_authority import PASSWORD_HASH, act_as, client, db, grant, world  # noqa: F401
from tests.test_planning import biryani_standards, plan_world  # noqa: F401 (fixtures)

USERS = "/api/admin/users"
AUDIT = "/api/audit"
AGENT = "/api/agent"


def ok(response, code=200):
    assert response.status_code == code, response.text
    return response.json()


# ============================================================
# STAGE 10: SIGN-IN SECURITY
# ============================================================

def test_login_attempts_are_recorded_and_throttled(client, db, world):
    for _ in range(5):
        bad = client.post("/api/auth/login", json={"email": "admin.a@test.com", "password": "wrong-password"})
        assert bad.status_code == 401
    blocked = client.post("/api/auth/login", json={"email": "admin.a@test.com", "password": "Password123!"})
    assert blocked.status_code == 429 and blocked.headers.get("Retry-After")
    other = client.post("/api/auth/login", json={"email": "km.a@test.com", "password": "Password123!"})
    assert other.status_code == 200, other.text
    rows = db.query(LoginAttempt).all()
    assert len(rows) == 6 and sum(r.succeeded for r in rows) == 1  # a refused (429) attempt is not counted
    assert db.query(User).filter_by(email="km.a@test.com").one().last_login_at is not None


def test_sign_out_everywhere_revokes_existing_tokens(client, db, world):
    a = world.a
    old = create_access_token(a.manager.id, a.manager.password_hash)
    act_as(client, a.manager)
    ok(client.post("/api/auth/logout-all"))
    db.expire_all()
    client.cookies.set(settings.ACCESS_COOKIE_NAME, old)
    assert client.get("/api/auth/me").status_code == 401
    assert db.query(AuditLog).filter_by(action="SIGN_OUT_EVERYWHERE", entity_id=a.manager.id).count() == 1


# ============================================================
# STAGE 10: USER ACCOUNTS (ADMIN ONLY, OWN CAMPUS)
# ============================================================

@pytest.mark.parametrize("role", ["manager", "staff"])
def test_only_admin_reaches_user_accounts(client, world, role):
    act_as(client, getattr(world.a, role))
    assert client.get(USERS).status_code == 403


def test_admin_lists_only_own_campus_and_edits_roles_with_guards(client, db, world):
    a, b = world.a, world.b
    act_as(client, a.admin)
    listed = ok(client.get(USERS))
    assert {u["email"] for u in listed["items"]} == {"admin.a@test.com", "km.a@test.com", "staff.a@test.com"}
    assert client.patch(f"{USERS}/{b.staff.id}", json={"full_name": "X Y"}).status_code == 404
    assert client.patch(f"{USERS}/{a.admin.id}", json={"full_name": "Me", "role": "STAFF"}).status_code == 409
    changed = ok(client.patch(f"{USERS}/{a.staff.id}", json={"full_name": "Asha Staff", "role": "KITCHEN_MANAGER"}))
    assert changed["role"] == "KITCHEN_MANAGER" and changed["sessions_revoked_at"]
    assert client.patch(f"{USERS}/{a.manager.id}", json={"full_name": "X", "role": "ADMIN"}).status_code == 422
    assert db.query(AuditLog).filter_by(action="UPDATE", entity_type="USER", entity_id=a.staff.id).count() == 1


def test_deactivate_reactivate_and_revoke(client, db, world):
    a = world.a
    act_as(client, a.admin)
    assert client.post(f"{USERS}/{a.admin.id}/deactivate", json={"reason": "leaving"}).status_code == 409
    gone = ok(client.post(f"{USERS}/{a.staff.id}/deactivate", json={"reason": "Left the campus"}))
    assert gone["is_active"] is False
    act_as(client, a.staff)
    assert client.get("/api/auth/me").status_code == 401
    act_as(client, a.admin)
    assert client.post(f"{USERS}/{a.staff.id}/reset-link").status_code == 409
    back = ok(client.post(f"{USERS}/{a.staff.id}/reactivate", json={"reason": "Returned"}))
    assert back["is_active"] is True
    ok(client.post(f"{USERS}/{a.manager.id}/revoke-sessions"))
    actions = {r.action for r in db.query(AuditLog).filter_by(entity_type="USER")}
    assert {"DEACTIVATE", "REACTIVATE", "REVOKE_SESSIONS"} <= actions


def test_reset_link_needs_configuration_and_never_shows_a_password(client, world, monkeypatch):
    a = world.a
    act_as(client, a.admin)
    monkeypatch.setattr(settings, "FRONTEND_BASE_URL", "http://localhost:3001", raising=False)
    link = client.post(f"{USERS}/{a.manager.id}/reset-link")
    if link.status_code == 200:
        assert link.json()["link"].startswith("http://localhost:3001/reset-password")
        assert "password" not in {k.lower() for k in link.json()}
    else:
        assert link.status_code == 503


# ============================================================
# STAGE 10: AUDIT VIEWER
# ============================================================

def test_audit_viewer_is_campus_scoped_and_hides_money_without_bill_access(client, db, world):
    a, b = world.a, world.b
    db.add_all([
        AuditLog(campus_id=a.campus.id, user_id=a.admin.id, action="CREATE", entity_type="PURCHASE", entity_id=1,
                 details={"grand_total": "1200.00", "invoice_number": "INV-1", "lines": [{"unit_rate": "60"}]}),
        AuditLog(campus_id=b.campus.id, user_id=b.admin.id, action="CREATE", entity_type="PURCHASE", entity_id=2,
                 details={"grand_total": "99.00"}),
    ])
    db.commit()
    act_as(client, a.manager)
    rows = ok(client.get(AUDIT, params={"entity_type": "PURCHASE"}))
    assert rows["total"] == 1 and rows["items"][0]["details"]["grand_total"] == "1200.00"
    options = ok(client.get(f"{AUDIT}/options"))
    assert "PURCHASE" in options["entity_types"]
    act_as(client, a.staff)
    assert client.get(AUDIT).status_code == 403
    grant(db, a.staff, a.admin, "audit.read")
    # audit.read is never STAFF-assignable; an older row grants nothing.
    if client.get(AUDIT).status_code == 200:
        details = client.get(AUDIT, params={"entity_type": "PURCHASE"}).json()["items"][0]["details"]
        assert details["grand_total"] == "hidden" and details["lines"][0]["unit_rate"] == "hidden"
        assert details["invoice_number"] == "INV-1"


# ============================================================
# STAGE 12: KITCHEN COPILOT
# ============================================================

@pytest.fixture
def agent_on(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_ENABLED", True)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)


def ask(client, text, conversation_id=None):
    return ok(client.post(f"{AGENT}/messages", json={"text": text, "conversation_id": conversation_id}))


def test_agent_is_off_by_default_and_status_still_answers(client, world, monkeypatch):
    monkeypatch.setattr(settings, "AGENT_ENABLED", False)
    act_as(client, world.a.manager)
    status = ok(client.get(f"{AGENT}/status"))
    assert status["enabled"] is False and status["reader"] == "rules"
    assert client.post(f"{AGENT}/messages", json={"text": "plan lunch"}).status_code == 503


def test_rule_reader_understands_the_three_example_requests(db, plan_world):
    a = plan_world.a
    names = agent_intent.campus_names(db, a.admin)
    today = date(2026, 11, 26)
    plan = agent_intent.rule_read("Plan tomorrow's lunch Veg Biryani for 450 people and tell me what we need to buy.",
                                  today, names)
    assert (plan.workflow, plan.plan_date, plan.headcount, plan.meal_session_id, plan.menu_id) == (
        "plan_procure", "2026-11-27", 450, a.lunch.id, a.biryani.id)
    spend = agent_intent.rule_read("Why did food spending go up this month compared with last month?", today, names)
    assert spend.workflow == "explain_spending" and spend.date_from == "2026-11-01" and spend.date_to == "2026-11-26"
    stock = agent_intent.rule_read("Today's rice count is 12 kg below the system. Find out why and prepare an adjustment.",
                                   today, names)
    assert stock.workflow == "stock_difference" and stock.item_id == a.item.id and stock.plan_date == "2026-11-26"


def test_plan_and_procure_proposes_drafts_and_executes_only_after_approval(client, db, plan_world, agent_on):
    a = plan_world.a
    act_as(client, a.admin)
    biryani_standards(client, a)
    # Rice was last bought from Supplier A; Chicken has no purchase history.
    bill = Purchase(campus_id=a.campus.id, supplier_id=a.supplier.id, invoice_number="R-1", purchase_date=campus_today(),
                    subtotal=Decimal("100"), discount=0, extra_charges=0, grand_total=Decimal("100"), status="DRAFT",
                    created_by=a.admin.id)
    db.add(bill)
    db.flush()
    db.add(PurchaseItem(campus_id=a.campus.id, purchase_id=bill.id, item_id=a.item.id, quantity=Decimal("2"),
                        unit_id=a.kg.id, unit_rate=Decimal("50"), line_total=Decimal("100")))
    db.commit()
    act_as(client, a.manager)
    first = ask(client, "Plan tomorrow's lunch for 450 people and tell me what we need to buy")
    answer = first["answer"]["payload"]
    assert answer["status"] == "answered" and answer["plan"], first
    table = next(b for b in answer["blocks"] if b["type"] == "table")
    rice = next(r for r in table["rows"] if r[0] == "Rice")
    assert rice[2] == "67.500 kg" and rice[3] == "20.000 kg" and rice[4] == "47.500 kg"  # 450 × 150 g; 20 kg in stock
    kinds = sorted(p["action_type"] for p in first["proposals"])
    assert kinds == ["CREATE_MEAL_PLAN_DRAFT", "CREATE_PURCHASE_ORDER_DRAFT"]
    assert "Chicken" in first["answer"]["content"]  # no earlier supplier
    assert db.query(MealPlan).count() == 0 and db.query(PurchaseOrder).count() == 0  # nothing written yet
    assert db.query(AgentStep).filter(AgentStep.kind == "tool").count() >= 3

    order = next(p for p in first["proposals"] if p["action_type"] == "CREATE_PURCHASE_ORDER_DRAFT")
    act_as(client, a.staff)  # STAFF can never decide it (purchase_order.* is not STAFF-usable)
    assert client.post(f"{AGENT}/proposals/{order['id']}/approve", json={}).status_code == 403
    act_as(client, a.manager)
    done = ok(client.post(f"{AGENT}/proposals/{order['id']}/approve", json={"note": "Checked"}))
    assert done["status"] == "EXECUTED" and done["result"]["entity"] == "PURCHASE_ORDER"
    po = db.query(PurchaseOrder).one()
    assert po.status == "DRAFT"
    assert client.post(f"{AGENT}/proposals/{order['id']}/approve", json={}).status_code == 409  # no duplicate
    plan = next(p for p in first["proposals"] if p["action_type"] == "CREATE_MEAL_PLAN_DRAFT")
    rejected = ok(client.post(f"{AGENT}/proposals/{plan['id']}/reject", json={"reason": "Menu will change"}))
    assert rejected["status"] == "REJECTED" and db.query(MealPlan).count() == 0
    actions = {r.action for r in db.query(AuditLog).filter_by(entity_type="AGENT_PROPOSAL")}
    assert {"APPROVE", "EXECUTED", "REJECT"} <= actions


def test_permission_is_rechecked_at_approval_time(client, db, plan_world, agent_on):
    a = plan_world.a
    act_as(client, a.admin)
    biryani_standards(client, a)
    act_as(client, a.manager)
    reply = ask(client, "Plan tomorrow's lunch for 400 people")
    plan = next(p for p in reply["proposals"] if p["action_type"] == "CREATE_MEAL_PLAN_DRAFT")
    # The manager is demoted to STAFF before deciding.
    a.manager.role = UserRole.STAFF
    db.commit()
    assert client.post(f"{AGENT}/proposals/{plan['id']}/approve", json={}).status_code in (401, 403)
    assert db.query(MealPlan).count() == 0


def test_agent_asks_for_missing_details_and_continues(client, plan_world, agent_on):
    a = plan_world.a
    act_as(client, a.admin)
    biryani_standards(client, a)
    first = ask(client, "Help me plan a meal and what to buy")
    assert first["answer"]["payload"]["status"] == "needs_info" and first["answer"]["payload"]["choices"]
    cid = first["conversation_id"]
    second = ask(client, "tomorrow", cid)
    assert "session" in second["answer"]["content"].lower()
    third = ask(client, "Lunch", cid)
    assert "how many" in third["answer"]["content"].lower()
    fourth = ask(client, "420 people", cid)
    assert fourth["answer"]["payload"]["status"] == "answered" and fourth["proposals"]


def test_staff_without_permissions_is_refused_and_campus_is_isolated(client, db, plan_world, agent_on):
    a, b = plan_world.a, plan_world.b
    act_as(client, a.staff)
    reply = ask(client, "Why did spending go up this month?")
    assert reply["answer"]["payload"]["status"] == "not_allowed"
    act_as(client, a.manager)
    mine = ask(client, "Plan tomorrow's lunch for 300 people")
    act_as(client, b.manager)
    assert client.get(f"{AGENT}/conversations/{mine['conversation_id']}").status_code == 404
    assert all(p["campus_id"] if "campus_id" in p else True for p in ok(client.get(f"{AGENT}/proposals"))["items"])
    assert ok(client.get(f"{AGENT}/proposals"))["items"] == []


def test_explain_spending_uses_application_figures(client, db, kitchen, agent_on):
    a = kitchen.a
    today = campus_today()
    for day, rate in ((today.replace(day=1) - timedelta(days=20), "50"), (today, "60")):
        bill = Purchase(campus_id=a.campus.id, supplier_id=a.supplier.id, invoice_number=f"S-{rate}", purchase_date=day,
                        subtotal=Decimal(rate) * 10, discount=0, extra_charges=0, grand_total=Decimal(rate) * 10,
                        status="DRAFT", created_by=a.admin.id)
        db.add(bill)
        db.flush()
        db.add(PurchaseItem(campus_id=a.campus.id, purchase_id=bill.id, item_id=a.item.id, quantity=Decimal("10"),
                            unit_id=a.kg.id, unit_rate=Decimal(rate), line_total=Decimal(rate) * 10))
    db.commit()
    act_as(client, a.manager)
    reply = ask(client, "Why did spending go up last month?" if False else "Explain spending for this month")
    payload = reply["answer"]["payload"]
    assert payload["status"] == "answered" and not reply["proposals"]  # read-only job
    assert "₹" in reply["answer"]["content"] and payload["links"][0]["href"].startswith("/dashboard/analytics")


def test_stock_difference_investigation_proposes_a_request_only(client, db, kitchen, agent_on):
    a = kitchen.a
    act_as(client, a.admin)
    count = ok(client.post("/api/stock-counts", json={"reason": "Weekly count",
                                                     "lines": [{"item_id": a.item.id, "quantity": "8"}]}), 201)
    act_as(client, a.manager)
    reply = ask(client, "Today's Rice count is 12 kg below the system. Find out why.")
    payload = reply["answer"]["payload"]
    assert payload["status"] == "answered", reply
    assert "-12" in reply["answer"]["content"] and count["count_number"] in reply["answer"]["content"]
    assert [p["action_type"] for p in reply["proposals"]] == ["RAISE_STOCK_ADJUSTMENT_REQUEST"]
    assert "unavailable from the approved sources" in reply["answer"]["content"]
    done = ok(client.post(f"{AGENT}/proposals/{reply['proposals'][0]['id']}/approve", json={}))
    assert done["status"] == "EXECUTED"
    adjustment = db.query(StockAdjustment).one()
    assert adjustment.status == "PENDING"  # posting still needs the independent approval


def test_fake_llm_reader_is_used_and_failure_falls_back(client, db, plan_world, monkeypatch):
    a = plan_world.a
    monkeypatch.setattr(settings, "AGENT_ENABLED", True)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key-not-real")
    seen = {}

    def fake(text, today, names):
        seen["names"] = names
        return agent_intent.Intent(workflow="plan_procure", plan_date=(today + timedelta(days=1)).isoformat(),
                                   meal_session_id=a.lunch.id, menu_id=a.biryani.id, headcount=200, reader="gemini")

    monkeypatch.setattr(agent_intent, "gemini_read", fake)
    act_as(client, a.admin)
    biryani_standards(client, a)
    reply = ask(client, "Sort out lunch tomorrow, two hundred heads")
    assert reply["answer"]["payload"]["reader"] == "gemini" and reply["proposals"]
    assert set(seen["names"]) == {"sessions", "menus", "items"}  # no supplier, money or stock data

    def broken(*_args):
        raise TimeoutError("offline")

    monkeypatch.setattr(agent_intent, "gemini_read", broken)
    fallback = ask(client, "Plan tomorrow's lunch for 300 people")
    assert fallback["answer"]["payload"]["reader"] == "rules"
    assert db.query(AgentStep).filter(AgentStep.name == "gemini_read", AgentStep.ok.is_(False)).count() == 1
