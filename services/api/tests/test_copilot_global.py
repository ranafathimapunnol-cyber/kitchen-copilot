"""Global Kitchen Copilot (floating panel): page context and the read-only
"what needs attention" job.

The page a person is viewing only focuses the answer; what they may see is
decided by their own role and permissions, through the same per-section
checks as the dashboard overview.
"""

from decimal import Decimal

import pytest

from app.agent import intent as agent_intent
from app.core.config import settings
from app.models import AuditLog
from app.models.agent import AgentProposal, AgentStep

from tests.test_kitchen_issues import kitchen  # noqa: F401 (fixture)
from tests.test_operational_authority import act_as, client, db, grant, world  # noqa: F401

AGENT = "/api/agent"


@pytest.fixture
def agent_on(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_ENABLED", True)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)


def ask(client, text, page=None, conversation_id=None):
    response = client.post(f"{AGENT}/messages", json={"text": text, "page": page, "conversation_id": conversation_id})
    assert response.status_code == 200, response.text
    return response.json()


def low_rice(db, kitchen):
    """Campus A's Rice (20 kg in stock) gets a 50 kg minimum; campus B's
    item is renamed so its name cannot be confused with A's."""
    kitchen.a.item.minimum_stock = Decimal("50")
    kitchen.b.item.name = "Hill Rice"
    db.commit()


def lists(reply) -> str:
    return " ".join(" ".join(b.get("items", [])) for b in reply["answer"]["payload"]["blocks"])


@pytest.mark.parametrize("text", [
    "What needs my attention today?",
    "Give me a summary of this page",
    "Anything urgent?",
    "What needs attention on this screen?",
])
def test_rule_reader_recognises_attention_requests(text, db, world):
    names = agent_intent.campus_names(db, world.a.admin)
    assert agent_intent.rule_read(text, agent_intent.date(2026, 11, 26), names).workflow == "attention"


def test_the_three_original_jobs_still_route_as_before(db, world):
    names = agent_intent.campus_names(db, world.a.admin)
    today = agent_intent.date(2026, 11, 26)
    assert agent_intent.rule_read("Plan tomorrow's lunch for 450 people", today, names).workflow == "plan_procure"
    assert agent_intent.rule_read("Why did spending go up this month?", today, names).workflow == "explain_spending"
    assert agent_intent.rule_read("Rice count is 2 kg below the system", today, names).workflow == "stock_difference"


def test_attention_on_the_stock_screen_uses_live_figures_and_writes_nothing(client, db, kitchen, agent_on):
    low_rice(db, kitchen)
    act_as(client, kitchen.a.manager)
    proposals_before = db.query(AgentProposal).count()

    reply = ask(client, "What needs attention on this screen?", page="/dashboard/stock")
    payload = reply["answer"]["payload"]
    assert payload["status"] == "answered" and payload["workflow"] == "attention"
    assert payload["page"] == "/dashboard/stock"
    text = lists(reply)
    assert "Rice (20 of 50 kg)" in text and "Hill Rice" not in text   # A's own record, B's never
    assert "/dashboard/stock" in [link["href"] for link in payload["links"]]
    assert reply["proposals"] == [] and db.query(AgentProposal).count() == proposals_before
    assert {"name": "operations_overview", "ok": True} in [
        {k: t[k] for k in ("name", "ok")} for t in payload["tools"]]

    steps = db.query(AgentStep).filter(AgentStep.conversation_id == reply["conversation_id"]).all()
    assert any(s.kind == "tool" and s.name == "operations_overview" and s.ok for s in steps)
    audit = (db.query(AuditLog).filter(AuditLog.entity_type == "AGENT_CONVERSATION",
                                       AuditLog.entity_id == reply["conversation_id"]).one())
    assert audit.details["page"] == "/dashboard/stock" and audit.details["workflow"] == "attention"


def test_page_focuses_the_answer(client, db, kitchen, agent_on):
    low_rice(db, kitchen)
    act_as(client, kitchen.a.manager)
    on_meals = lists(ask(client, "What needs attention here?", page="/dashboard/meals"))
    assert "below minimum" not in on_meals and "headcount" in on_meals.lower()
    everywhere = lists(ask(client, "What needs attention today?", page="/dashboard"))
    assert "below minimum" in everywhere and "headcount" in everywhere.lower()


def test_staff_sees_only_what_they_are_granted(client, db, kitchen, agent_on):
    low_rice(db, kitchen)
    a = kitchen.a
    act_as(client, a.staff)
    # Without dashboard.read the tool is refused.
    assert ask(client, "What needs attention today?")["answer"]["payload"]["status"] == "not_allowed"
    # With dashboard.read only: no stock, money or meal figures leak through.
    grant(db, a.staff, a.admin, "dashboard.read")
    reply = ask(client, "What needs attention today?", page="/dashboard/supplier-bills")
    assert reply["answer"]["payload"]["status"] == "answered"
    body = reply["answer"]["content"] + lists(reply)
    assert "₹" not in body and "Rice" not in body and "headcount" not in body.lower()
    # Granting inventory.read adds exactly the stock finding.
    grant(db, a.staff, a.admin, "inventory.read")
    assert "Rice (20 of 50 kg)" in lists(ask(client, "What needs attention today?"))


def test_other_campus_sees_only_its_own_records(client, db, kitchen, agent_on):
    low_rice(db, kitchen)
    act_as(client, kitchen.b.manager)
    text = lists(ask(client, "What needs attention today?", page="/dashboard/stock"))
    assert "Rice (20 of 50 kg)" not in text and "Hill Rice" not in text  # B's item has no minimum
    assert "out of stock" in text


@pytest.mark.parametrize("page", ["/admin", "https://example.com/dashboard", "/dashboard/../x", "/dashboard/Stock",
                                  "/dashboard/" + "a" * 130])
def test_page_must_be_a_dashboard_path(client, world, agent_on, page):
    act_as(client, world.a.manager)
    response = client.post(f"{AGENT}/messages", json={"text": "What needs attention?", "page": page})
    assert response.status_code == 422


def test_unrecognised_request_offers_the_page_summary_first(client, world, agent_on):
    act_as(client, world.a.manager)
    reply = ask(client, "hello there", page="/dashboard/receipts")
    payload = reply["answer"]["payload"]
    assert payload["status"] == "needs_info"
    assert payload["choices"][0] == {"label": "What needs attention here", "text": "What needs attention on this screen?"}


def test_status_reports_the_attention_job_per_user(client, db, world, agent_on):
    act_as(client, world.a.manager)
    assert client.get(f"{AGENT}/status").json()["workflows"]["attention"] is True
    act_as(client, world.a.staff)
    assert client.get(f"{AGENT}/status").json()["workflows"]["attention"] is False


def test_a_weekday_inside_a_menu_name_is_not_read_as_a_date():
    """Choosing the menu "Monday Lunch" after asking about tomorrow kept
    moving the plan to next Monday (found in the browser check)."""
    names = {"sessions": [(1, "Lunch")], "menus": [(7, "Monday Lunch", 1)], "items": [], "categories": []}
    today = agent_intent.date(2026, 11, 27)   # a Friday
    plain = agent_intent.rule_read("Monday Lunch", today, names)
    assert plain.menu_id == 7 and plain.plan_date is None
    asked = agent_intent.rule_read("Plan tomorrow's Monday Lunch for 450 people", today, names)
    assert asked.plan_date == "2026-11-28" and asked.menu_id == 7 and asked.headcount == 450
    named_day = agent_intent.rule_read("Plan Monday Lunch on Wednesday for 300 people", today, names)
    assert named_day.plan_date == "2026-12-02"
    # A real weekday on its own still counts.
    assert agent_intent.rule_read("Plan lunch on Monday for 300 people", today, names).plan_date == "2026-11-30"
