"""
Stage 4 slice 4b on PostgreSQL (kitchen_copilot_test_db, shared
tests/conftest.py fixtures). Covers what SQLite cannot:
- two confirmations racing for the last stock: one wins, the balance never
  goes below zero;
- one issue confirmed from several sessions at once: posted once;
- returns drafted at once against one issue line: never more than issued;
- a return's confirmation racing the issue's reversal: exactly one wins;
- issues saved at once: distinct sequential numbers;
- the append-only triggers (UPDATE, DELETE, TRUNCATE) on the real server,
  where the test role is a superuser, and the application guard;
- a backdated issue stored as the end of its campus day.
"""

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.clock import campus_timezone, campus_today
from app.models import Category, Item, MealSession, Menu, Unit
from app.models.ledger_guard import LedgerIsAppendOnly
from app.models.purchases import StockMovement
from app.models.stock import KitchenIssue, KitchenReturn
from app.services import stock_ledger

from tests.test_stock_ledger_postgres import engine_factory, parallel_clients, race  # noqa: F401 (fixtures)

ISSUES = "/api/kitchen-issues"


@pytest.fixture
def kitchen_pg(client, db, setup_data):
    campus_id = setup_data["campus"].id
    kg = Unit(campus_id=campus_id, name="Kilogram", symbol="kg", dimension="weight")
    category = Category(campus_id=campus_id, name="Grains")
    lunch = MealSession(campus_id=campus_id, name="Lunch")
    db.add_all([kg, category, lunch])
    db.flush()
    rice = Item(campus_id=campus_id, name="Rice", category_id=category.id, standard_unit_id=kg.id, minimum_stock=0)
    menu = Menu(campus_id=campus_id, name="Veg Biryani", meal_session_id=lunch.id)
    db.add_all([rice, menu])
    db.commit()
    opening = client.post("/api/stock/openings", json={
        "effective_date": (campus_today() - timedelta(days=5)).isoformat(),
        "lines": [{"item_id": rice.id, "quantity": "10"}]})
    assert opening.status_code == 201, opening.text
    return {"campus_id": campus_id, "rice_id": rice.id, "lunch_id": lunch.id, "menu_id": menu.id}


def issue_body(k, qty, issue_date=None):
    return {"issue_date": issue_date or campus_today().isoformat(), "meal_session_id": k["lunch_id"],
            "menu_id": k["menu_id"], "lines": [{"item_id": k["rice_id"], "quantity": qty}]}


def rice_balance(db, k):
    db.expire_all()
    return stock_ledger.item_balance(db, k["campus_id"], k["rice_id"])


def test_two_confirmations_racing_for_the_last_stock(client, db, kitchen_pg, parallel_clients):
    first = client.post(ISSUES, json=issue_body(kitchen_pg, "6")).json()["id"]
    second = client.post(ISSUES, json=issue_body(kitchen_pg, "6")).json()["id"]

    statuses = race(parallel_clients, [lambda c: c.post(f"{ISSUES}/{first}/confirm"),
                                       lambda c: c.post(f"{ISSUES}/{second}/confirm")])

    assert statuses == [200, 409], statuses
    assert rice_balance(db, kitchen_pg) == Decimal("4")


def test_one_issue_confirmed_from_several_sessions_posts_once(client, db, kitchen_pg, parallel_clients):
    issue_id = client.post(ISSUES, json=issue_body(kitchen_pg, "3")).json()["id"]

    statuses = race(parallel_clients, [lambda c: c.post(f"{ISSUES}/{issue_id}/confirm")] * 4)

    assert statuses.count(200) == 1 and statuses.count(409) == 3, statuses
    db.expire_all()
    assert db.query(StockMovement).filter_by(reference_type="KITCHEN_ISSUE", reference_id=issue_id).count() == 1
    assert rice_balance(db, kitchen_pg) == Decimal("7")


def test_returns_drafted_at_once_never_exceed_the_issue(client, db, kitchen_pg, parallel_clients):
    issue = client.post(ISSUES, json=issue_body(kitchen_pg, "4")).json()
    issue = client.post(f"{ISSUES}/{issue['id']}/confirm").json()
    body = {"return_date": campus_today().isoformat(),
            "lines": [{"issue_item_id": issue["lines"][0]["id"], "quantity": "3"}]}

    statuses = race(parallel_clients, [lambda c: c.post(f"{ISSUES}/{issue['id']}/returns", json=body)] * 4)

    assert statuses.count(201) == 1 and statuses.count(422) == 3, statuses


def test_return_confirmation_racing_the_issue_reversal(client, db, kitchen_pg, parallel_clients):
    issue = client.post(ISSUES, json=issue_body(kitchen_pg, "4")).json()
    issue = client.post(f"{ISSUES}/{issue['id']}/confirm").json()
    detail = client.post(f"{ISSUES}/{issue['id']}/returns", json={
        "return_date": campus_today().isoformat(),
        "lines": [{"issue_item_id": issue["lines"][0]["id"], "quantity": "1"}]}).json()
    return_id = detail["returns"][0]["id"]

    statuses = race(parallel_clients, [
        lambda c: c.post(f"/api/kitchen-returns/{return_id}/confirm"),
        lambda c: c.post(f"{ISSUES}/{issue['id']}/reverse", json={"reason": "race with a return"}),
    ])

    assert statuses == [200, 409], statuses
    db.expire_all()
    issue_status = db.get(KitchenIssue, issue["id"]).status
    return_status = db.get(KitchenReturn, return_id).status
    assert (issue_status, return_status, rice_balance(db, kitchen_pg)) in {
        ("CONFIRMED", "CONFIRMED", Decimal("7")),  # the return won; the reversal waits for it
        ("REVERSED", "DRAFT", Decimal("10")),      # the reversal won; the return can no longer post
    }


def test_issues_saved_at_once_take_distinct_sequential_numbers(db, kitchen_pg, parallel_clients):
    body = issue_body(kitchen_pg, "1")
    statuses = race(parallel_clients, [lambda c: c.post(ISSUES, json=body)] * 4)

    assert statuses == [201] * 4
    db.expire_all()
    numbers = sorted(n for (n,) in db.query(KitchenIssue.issue_number))
    assert numbers == ["KI-00001", "KI-00002", "KI-00003", "KI-00004"]


@pytest.mark.parametrize("sql", [
    "UPDATE stock_movements SET remarks = 'edited'",
    "DELETE FROM stock_movements",
    "TRUNCATE stock_movements",
    "TRUNCATE stock_movements CASCADE",
])
def test_postgresql_refuses_changes_to_the_ledger_even_for_a_superuser(db, kitchen_pg, sql):
    assert db.execute(text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")).scalar() is True
    before = db.query(StockMovement).count()
    with pytest.raises(DBAPIError) as refused:
        db.execute(text(sql))
    assert "append-only" in str(refused.value)
    db.rollback()
    assert db.query(StockMovement).count() == before == 1


def test_the_triggers_exist_and_the_application_guard_holds_on_postgresql(db, kitchen_pg):
    triggers = {name for (name,) in db.execute(text(
        "SELECT tgname FROM pg_trigger WHERE tgrelid = 'stock_movements'::regclass AND NOT tgisinternal"))}
    assert triggers == {"stock_movements_no_update_delete", "stock_movements_no_truncate"}

    movement = db.query(StockMovement).one()
    movement.remarks = "edited through the ORM"
    with pytest.raises(LedgerIsAppendOnly):
        db.commit()
    db.rollback()
    db.expire_all()
    assert db.query(StockMovement).one().remarks is None


def test_a_backdated_issue_is_stored_at_the_end_of_its_campus_day(client, db, kitchen_pg):
    day = campus_today() - timedelta(days=2)
    issue = client.post(ISSUES, json=issue_body(kitchen_pg, "2", day.isoformat())).json()
    assert client.post(f"{ISSUES}/{issue['id']}/confirm").status_code == 200

    stored = db.execute(text(
        "SELECT effective_at FROM stock_movements WHERE movement_type = 'ISSUE'")).scalar_one()
    expected = datetime.combine(day, time.max, tzinfo=campus_timezone()).astimezone(timezone.utc)
    assert stored.tzinfo is not None and stored == expected
