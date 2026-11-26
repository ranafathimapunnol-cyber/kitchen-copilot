"""
Stage 4 slice 4b: kitchen issues and unused returns (STK02, STK03, STK04
criterion 4, AT01), with the decisions of 23 November 2026
(docs/STAGE-4-STOCK-PLAN.md sections 4 and 9):

- S1 / 4b-3: consumption.create records a draft; consumption.update edits,
  cancels and confirms one, including the user's own; consumption.read
  views; reversals are ADMIN and KITCHEN_MANAGER only.
- S2: no balance below zero at any point (confirming an issue, reversing a
  return).
- S4: whole-document reversal with a reason; an issue's confirmed returns
  are reversed first; originals never change.
- S5: date, meal session and menu on every issue.
- 4b-1 / 4b-2: effective at confirmation when dated today, at the end of
  the date when backdated; a return never before its issue.
- 4b-4: KI-00001 and KR-00001 per campus.

In-memory SQLite with the shared fixtures of test_operational_authority;
tests/test_kitchen_issues_postgres.py covers races and PostgreSQL.
"""

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

import pytest

from app.core.clock import campus_timezone, campus_today
from app.models import AuditLog, Category, Item, MealSession, Menu, Unit, UnitConversion
from app.models.purchases import StockMovement
from app.models.stock import KitchenIssue
from app.services.stock_ledger import as_utc

from tests.test_operational_authority import (  # noqa: F401 (fixtures)
    act_as,
    client,
    db,
    grant,
    world,
)
from tests.test_pur03_receipts import bill_lines, create_bill, draft

ISSUES = "/api/kitchen-issues"


def days_ago(n):
    return (campus_today() - timedelta(days=n)).isoformat()


def end_of(day_text):
    day = datetime.fromisoformat(day_text).date()
    return datetime.combine(day, time.max, tzinfo=campus_timezone()).astimezone(timezone.utc)


@pytest.fixture
def kitchen(db, world, client):
    """Campus A: kg and g; Rice and Toor Dal; Lunch (Veg Biryani) and
    Dinner (Dal Fry); an inactive session and menu. Rice has 20 kg opening
    stock dated 10 days ago; Toor Dal has none. Campus B has its own."""
    a, b = world.a, world.b
    g = Unit(campus_id=a.campus.id, name="Gram", symbol="g", dimension="weight")
    db.add(g)
    db.flush()
    db.add(UnitConversion(campus_id=a.campus.id, from_unit_id=g.id, to_unit_id=a.kg.id, factor=Decimal("0.001")))
    dal = Item(campus_id=a.campus.id, name="Toor Dal", category_id=a.category.id, standard_unit_id=a.kg.id, minimum_stock=0)
    lunch = MealSession(campus_id=a.campus.id, name="Lunch")
    dinner = MealSession(campus_id=a.campus.id, name="Dinner")
    old = MealSession(campus_id=a.campus.id, name="Old Session", is_active=False)
    b_lunch = MealSession(campus_id=b.campus.id, name="Lunch")
    db.add_all([dal, lunch, dinner, old, b_lunch])
    db.flush()
    biryani = Menu(campus_id=a.campus.id, name="Veg Biryani", meal_session_id=lunch.id)
    dal_fry = Menu(campus_id=a.campus.id, name="Dal Fry", meal_session_id=dinner.id)
    retired = Menu(campus_id=a.campus.id, name="Retired Menu", meal_session_id=lunch.id, is_active=False)
    b_menu = Menu(campus_id=b.campus.id, name="Hill Lunch", meal_session_id=b_lunch.id)
    db.add_all([biryani, dal_fry, retired, b_menu])
    db.commit()
    a.g, a.dal, a.lunch, a.dinner, a.old_session = g, dal, lunch, dinner, old
    a.biryani, a.dal_fry, a.retired_menu = biryani, dal_fry, retired
    b.lunch, b.menu = b_lunch, b_menu

    act_as(client, a.admin)
    opening = client.post("/api/stock/openings", json={
        "effective_date": days_ago(10), "lines": [{"item_id": a.item.id, "quantity": "20"}]})
    assert opening.status_code == 201, opening.text
    return world


def new_issue(client, place, lines, issue_date=None, session=None, menu=None, remarks=None):
    return client.post(ISSUES, json={
        "issue_date": issue_date or campus_today().isoformat(),
        "meal_session_id": (session or place.lunch).id,
        "menu_id": (menu or place.biryani).id,
        "remarks": remarks,
        "lines": [{"item_id": item.id, "quantity": qty, **({"unit_id": unit.id} if unit else {})}
                  for item, qty, unit in lines],
    })


def confirm(client, issue_id):
    return client.post(f"{ISSUES}/{issue_id}/confirm")


def new_return(client, issue, lines, return_date=None):
    by_item = {line["item_id"]: line["id"] for line in issue["lines"]}
    return client.post(f"{ISSUES}/{issue['id']}/returns", json={
        "return_date": return_date or campus_today().isoformat(),
        "lines": [{"issue_item_id": by_item[item.id], "quantity": qty, **({"unit_id": unit.id} if unit else {})}
                  for item, qty, unit in lines],
    })


def balance(client, item):
    return client.get(f"/api/stock/items/{item.id}/ledger").json()["item"]["balance"]


def issued_and_confirmed(client, place, lines, **kwargs):
    created = new_issue(client, place, lines, **kwargs)
    assert created.status_code == 201, created.text
    confirmed = confirm(client, created.json()["id"])
    assert confirmed.status_code == 200, confirmed.text
    return confirmed.json()


def movements_of(db, reference_type, reference_id):
    return db.query(StockMovement).filter_by(reference_type=reference_type, reference_id=reference_id).order_by(StockMovement.id).all()


# ============================================================
# STK02 — RECORD KITCHEN ISSUES
# ============================================================

def test_criterion_1_issue_records_date_session_menu_items_units_user_and_remarks(client, kitchen):
    a = kitchen.a
    act_as(client, a.manager)

    response = new_issue(client, a, [(a.item, "4", None), (a.dal, "1500", a.g)], remarks="Lunch batch")

    assert response.status_code == 201, response.text
    issue = response.json()
    assert (issue["issue_number"], issue["status"], issue["issue_date"]) == ("KI-00001", "DRAFT", campus_today().isoformat())
    assert (issue["meal_session_name"], issue["menu_name"], issue["remarks"]) == ("Lunch", "Veg Biryani", "Lunch batch")
    assert issue["created_by_name"] == a.manager.full_name  # the responsible user (S5)
    assert [(l["item_name"], l["quantity"], l["unit_symbol"], l["standard_quantity"], l["standard_unit_symbol"], l["conversion_factor"])
            for l in issue["lines"]] == [("Rice", "4.000", "kg", "4.000", "kg", "1"),
                                         ("Toor Dal", "1500.000", "g", "1.500", "kg", "0.001")]


def test_criterion_2_confirmation_reduces_stock(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.admin)
    issue = issued_and_confirmed(client, a, [(a.item, "4", None)])

    assert issue["status"] == "CONFIRMED" and balance(client, a.item) == "16.000"
    (movement,) = movements_of(db, "KITCHEN_ISSUE", issue["id"])
    line = issue["lines"][0]
    assert (movement.movement_type, movement.direction, movement.quantity, movement.source_key) == (
        "ISSUE", -1, Decimal("4.000"), f"ISSUE_ITEM:{line['id']}")
    assert line["movement_id"] == movement.id and line["net_quantity"] == "4.000"


def test_criterion_3_drafts_never_change_stock(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.admin)
    # Even a draft for more than is in stock may be saved (Q9 interim).
    issue = new_issue(client, a, [(a.item, "100", None)]).json()
    edited = client.put(f"{ISSUES}/{issue['id']}", json={
        "issue_date": campus_today().isoformat(), "meal_session_id": a.dinner.id, "menu_id": a.dal_fry.id,
        "lines": [{"item_id": a.item.id, "quantity": "3"}, {"item_id": a.dal.id, "quantity": "1"}]})
    assert edited.status_code == 200, edited.text
    assert edited.json()["menu_name"] == "Dal Fry" and len(edited.json()["lines"]) == 2
    assert client.post(f"{ISSUES}/{issue['id']}/cancel", json={"reason": ""}).status_code == 422
    cancelled = client.post(f"{ISSUES}/{issue['id']}/cancel", json={"reason": "Menu changed"}).json()

    assert (cancelled["status"], cancelled["cancellation_reason"]) == ("CANCELLED", "Menu changed")
    assert confirm(client, issue["id"]).status_code == 409
    assert db.query(StockMovement).filter_by(movement_type="ISSUE").count() == 0
    assert balance(client, a.item) == "20.000"


@pytest.mark.parametrize("case, status, message", [
    ("menu_of_other_session", 422, "belongs to another meal session"),
    ("inactive_session", 422, "active meal session"),
    ("inactive_menu", 422, "active menu"),
    ("other_campus_menu", 422, "active menu"),
    ("future_date", 422, "future"),
    ("duplicate_item", 422, "only once"),
    ("inactive_item_unit", 422, "explicit unit conversion"),
])
def test_criterion_4_issue_is_linked_to_an_active_session_and_its_menu(client, db, kitchen, case, status, message):
    a, b = kitchen.a, kitchen.b
    act_as(client, a.admin)
    litre = Unit(campus_id=a.campus.id, name="Litre", symbol="L", dimension="volume")
    db.add(litre)
    db.commit()
    args = {
        "menu_of_other_session": dict(lines=[(a.item, "1", None)], session=a.lunch, menu=a.dal_fry),
        "inactive_session": dict(lines=[(a.item, "1", None)], session=a.old_session, menu=a.biryani),
        "inactive_menu": dict(lines=[(a.item, "1", None)], menu=a.retired_menu),
        "other_campus_menu": dict(lines=[(a.item, "1", None)], menu=b.menu),
        "future_date": dict(lines=[(a.item, "1", None)], issue_date=(campus_today() + timedelta(days=1)).isoformat()),
        "duplicate_item": dict(lines=[(a.item, "1", None), (a.item, "2", None)]),
        "inactive_item_unit": dict(lines=[(a.item, "1", litre)]),
    }[case]

    response = new_issue(client, a, **args)

    assert response.status_code == status, response.text
    assert message in response.json()["detail"]
    assert db.query(KitchenIssue).count() == 0


def test_criterion_5_issues_exceeding_available_stock_are_prevented(client, db, kitchen):
    """STK04 criterion 4: confirming more than the balance is refused, with
    the shortfall named; the draft stays a draft and posts nothing."""
    a = kitchen.a
    act_as(client, a.admin)
    issue = new_issue(client, a, [(a.item, "25", None)]).json()

    refused = confirm(client, issue["id"])

    assert refused.status_code == 409
    assert "Not enough Rice" in refused.json()["detail"] and "-5.000 kg" in refused.json()["detail"]
    assert client.get(f"{ISSUES}/{issue['id']}").json()["status"] == "DRAFT"
    assert db.query(StockMovement).filter_by(movement_type="ISSUE").count() == 0
    assert balance(client, a.item) == "20.000"


# ============================================================
# 4b-1 — WHEN AN ISSUE TAKES EFFECT
# ============================================================

def test_an_issue_dated_today_takes_effect_at_confirmation(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.admin)
    created = new_issue(client, a, [(a.item, "1", None)]).json()
    before = datetime.now(timezone.utc)
    issue = confirm(client, created["id"]).json()
    after = datetime.now(timezone.utc)

    effective = datetime.fromisoformat(issue["effective_at"])
    assert before - timedelta(seconds=1) <= effective <= after + timedelta(seconds=1)
    assert issue["effective_at"] == issue["confirmed_at"]
    assert as_utc(movements_of(db, "KITCHEN_ISSUE", issue["id"])[0].effective_at) == effective


def test_a_backdated_issue_takes_effect_at_the_end_of_its_date(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.admin)
    issue = issued_and_confirmed(client, a, [(a.item, "2", None)], issue_date=days_ago(3))

    assert datetime.fromisoformat(issue["effective_at"]) == end_of(days_ago(3))
    local = end_of(days_ago(3)).astimezone(campus_timezone())
    assert (local.hour, local.minute, local.second, local.microsecond) == (23, 59, 59, 999999)
    assert as_utc(movements_of(db, "KITCHEN_ISSUE", issue["id"])[0].effective_at) == end_of(days_ago(3))


def test_a_backdated_issue_is_judged_against_the_stock_of_its_own_day(client, kitchen):
    """Toor Dal arrives today (receipt). An issue dated two days ago cannot
    have used it, so confirming it is refused; the same issue dated today is
    fine."""
    a = kitchen.a
    act_as(client, a.admin)
    bill = create_bill(client, a, "KI-DAL-1", [(a.dal, "5")])
    line_id = bill_lines(client, bill["id"])[0]["purchase_item_id"]
    receipt = draft(client, bill["id"], [(line_id, "5", "5", "0")], receipt_date=campus_today().isoformat()).json()
    assert client.post(f"/api/receipts/{receipt['id']}/accept").status_code == 200

    backdated = new_issue(client, a, [(a.dal, "1", None)], issue_date=days_ago(2)).json()
    refused = confirm(client, backdated["id"])
    assert refused.status_code == 409 and "Not enough Toor Dal" in refused.json()["detail"]

    today = new_issue(client, a, [(a.dal, "1", None)]).json()
    assert confirm(client, today["id"]).status_code == 200
    assert balance(client, a.dal) == "4.000"


# ============================================================
# STK03 — UNUSED RETURNS
# ============================================================

def test_returns_increase_stock_reference_their_issue_and_keep_figures_separate(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.admin)
    issue = issued_and_confirmed(client, a, [(a.item, "4", None)])

    drafted = new_return(client, issue, [(a.item, "1500", a.g)])
    assert drafted.status_code == 201, drafted.text
    record = drafted.json()["returns"][0]
    assert (record["return_number"], record["status"]) == ("KR-00001", "DRAFT")
    assert balance(client, a.item) == "16.000"  # a draft return posts nothing

    confirmed = client.post(f"/api/kitchen-returns/{record['id']}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    detail = confirmed.json()
    line = detail["lines"][0]
    # Issued and returned stay separately visible; net usage = issued − returned.
    assert (line["standard_quantity"], line["returned_quantity"], line["net_quantity"], line["returnable_quantity"]) == (
        "4.000", "1.500", "2.500", "2.500")
    (movement,) = movements_of(db, "KITCHEN_RETURN", record["id"])
    return_line = detail["returns"][0]["lines"][0]
    assert (movement.movement_type, movement.direction, movement.quantity, movement.source_key) == (
        "UNUSED_RETURN", 1, Decimal("1.500"), f"RETURN_ITEM:{return_line['id']}")
    assert return_line["issue_item_id"] == line["id"]  # each return references its source issue line
    assert balance(client, a.item) == "17.500"


def test_returns_never_exceed_what_was_issued(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.admin)
    issue = issued_and_confirmed(client, a, [(a.item, "4", None)])

    assert new_return(client, issue, [(a.item, "4.001", None)]).status_code == 422
    first = new_return(client, issue, [(a.item, "3", None)])
    assert first.status_code == 201
    # A second draft cannot take more than the first one leaves.
    too_much = new_return(client, issue, [(a.item, "1.5", None)])
    assert too_much.status_code == 422 and "Only 1.000 kg of Rice" in too_much.json()["detail"]
    assert new_return(client, issue, [(a.item, "1", None)]).status_code == 201
    assert db.query(StockMovement).filter_by(movement_type="UNUSED_RETURN").count() == 0


def test_a_return_takes_effect_by_the_same_rule_and_never_before_its_issue(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.admin)
    issue = issued_and_confirmed(client, a, [(a.item, "4", None)], issue_date=days_ago(3))

    assert new_return(client, issue, [(a.item, "1", None)], return_date=days_ago(4)).status_code == 422
    same_day = new_return(client, issue, [(a.item, "1", None)], return_date=days_ago(3)).json()["returns"][0]
    later = new_return(client, issue, [(a.item, "1", None)]).json()["returns"][1]
    client.post(f"/api/kitchen-returns/{same_day['id']}/confirm")
    detail = client.post(f"/api/kitchen-returns/{later['id']}/confirm").json()

    same_day_effective = datetime.fromisoformat(detail["returns"][0]["effective_at"])
    issue_effective = datetime.fromisoformat(issue["effective_at"])
    assert same_day_effective == issue_effective == end_of(days_ago(3))
    assert datetime.fromisoformat(detail["returns"][1]["effective_at"]) > issue_effective
    # Same effective time as its issue, but posted later: replayed after it.
    issue_move = movements_of(db, "KITCHEN_ISSUE", issue["id"])[0]
    return_move = movements_of(db, "KITCHEN_RETURN", same_day["id"])[0]
    assert as_utc(return_move.effective_at) == as_utc(issue_move.effective_at) and return_move.id > issue_move.id


def test_returns_only_against_confirmed_issues(client, kitchen):
    a = kitchen.a
    act_as(client, a.admin)
    drafted = new_issue(client, a, [(a.item, "1", None)]).json()
    assert new_return(client, drafted, [(a.item, "1", None)]).status_code == 409


# ============================================================
# S4 — REVERSALS (ADMIN AND KITCHEN_MANAGER)
# ============================================================

def test_reversing_an_issue_restores_stock_and_keeps_the_original(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.admin)
    issue = issued_and_confirmed(client, a, [(a.item, "4", None)], issue_date=days_ago(1))
    (original,) = movements_of(db, "KITCHEN_ISSUE", issue["id"])
    before = (original.id, original.direction, original.quantity, as_utc(original.effective_at), original.source_key)

    assert client.post(f"{ISSUES}/{issue['id']}/reverse", json={"reason": "  "}).status_code == 422
    act_as(client, a.manager)
    started = datetime.now(timezone.utc)
    reversed_ = client.post(f"{ISSUES}/{issue['id']}/reverse", json={"reason": "Recorded against the wrong menu"})

    assert reversed_.status_code == 200, reversed_.text
    detail = reversed_.json()
    assert (detail["status"], detail["reversal_reason"], detail["reversed_by_name"]) == (
        "REVERSED", "Recorded against the wrong menu", a.manager.full_name)
    assert detail["lines"][0]["net_quantity"] == "0.000"
    db.expire_all()
    moves = movements_of(db, "KITCHEN_ISSUE", issue["id"])
    reversal = moves[1]
    assert (reversal.movement_type, reversal.direction, reversal.reversal_of_id) == ("REVERSAL", 1, original.id)
    assert as_utc(reversal.effective_at) >= started - timedelta(seconds=1)  # posting time, not the issue date
    first = moves[0]
    assert (first.id, first.direction, first.quantity, as_utc(first.effective_at), first.source_key) == before
    assert balance(client, a.item) == "20.000"
    assert client.post(f"{ISSUES}/{issue['id']}/reverse", json={"reason": "again"}).status_code == 409


def test_an_issue_with_a_confirmed_return_is_reversed_only_after_the_return(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.admin)
    issue = issued_and_confirmed(client, a, [(a.item, "4", None)])
    record = new_return(client, issue, [(a.item, "1", None)]).json()["returns"][0]
    client.post(f"/api/kitchen-returns/{record['id']}/confirm")

    refused = client.post(f"{ISSUES}/{issue['id']}/reverse", json={"reason": "wrong"})
    assert refused.status_code == 409 and "KR-00001" in refused.json()["detail"]

    reversed_return = client.post(f"/api/kitchen-returns/{record['id']}/reverse", json={"reason": "Counted twice"})
    assert reversed_return.status_code == 200 and reversed_return.json()["returns"][0]["status"] == "REVERSED"
    assert balance(client, a.item) == "16.000"
    assert client.post(f"{ISSUES}/{issue['id']}/reverse", json={"reason": "wrong"}).status_code == 200
    assert balance(client, a.item) == "20.000"
    kinds = [(m.movement_type, m.direction) for m in db.query(StockMovement).filter(
        StockMovement.reference_type.in_(("KITCHEN_ISSUE", "KITCHEN_RETURN"))).order_by(StockMovement.id)]
    assert kinds == [("ISSUE", -1), ("UNUSED_RETURN", 1), ("REVERSAL", -1), ("REVERSAL", 1)]


def test_reversing_a_return_cannot_take_stock_below_zero(client, kitchen):
    a = kitchen.a
    act_as(client, a.admin)
    issue = issued_and_confirmed(client, a, [(a.item, "4", None)])
    record = new_return(client, issue, [(a.item, "2", None)]).json()["returns"][0]
    client.post(f"/api/kitchen-returns/{record['id']}/confirm")
    issued_and_confirmed(client, a, [(a.item, "18", None)])  # everything left goes to the kitchen

    refused = client.post(f"/api/kitchen-returns/{record['id']}/reverse", json={"reason": "wrong"})

    assert refused.status_code == 409 and "-2.000 kg" in refused.json()["detail"]
    assert balance(client, a.item) == "0.000"


def test_a_draft_return_cannot_be_confirmed_after_its_issue_is_reversed(client, kitchen):
    a = kitchen.a
    act_as(client, a.admin)
    issue = issued_and_confirmed(client, a, [(a.item, "4", None)])
    record = new_return(client, issue, [(a.item, "1", None)]).json()["returns"][0]
    assert client.post(f"{ISSUES}/{issue['id']}/reverse", json={"reason": "wrong"}).status_code == 200

    refused = client.post(f"/api/kitchen-returns/{record['id']}/confirm")
    assert refused.status_code == 409 and "no longer confirmed" in refused.json()["detail"]
    assert client.post(f"/api/kitchen-returns/{record['id']}/cancel", json={"reason": "Issue reversed"}).status_code == 200


# ============================================================
# 4b-4 — NUMBERING
# ============================================================

def test_numbers_are_sequential_per_campus_and_kept_by_cancelled_drafts(client, kitchen):
    a, b = kitchen.a, kitchen.b
    act_as(client, a.admin)
    first = new_issue(client, a, [(a.item, "1", None)]).json()
    client.post(f"{ISSUES}/{first['id']}/cancel", json={"reason": "Typo"})
    second = new_issue(client, a, [(a.item, "1", None)]).json()
    assert (first["issue_number"], second["issue_number"]) == ("KI-00001", "KI-00002")

    act_as(client, b.admin)
    hill_item = b.item
    other = client.post(ISSUES, json={"issue_date": campus_today().isoformat(), "meal_session_id": b.lunch.id,
                                      "menu_id": b.menu.id, "lines": [{"item_id": hill_item.id, "quantity": "1"}]})
    assert other.json()["issue_number"] == "KI-00001"


# ============================================================
# S1 / 4b-3 — WHO MAY DO WHAT
# ============================================================

def test_staff_permissions_follow_the_consumption_codes(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.staff)
    assert client.get(ISSUES).status_code == 403
    assert new_issue(client, a, [(a.item, "1", None)]).status_code == 403

    grant(db, a.staff, a.admin, "consumption.read")
    assert client.get(ISSUES).status_code == 200
    assert new_issue(client, a, [(a.item, "1", None)]).status_code == 403

    grant(db, a.staff, a.admin, "consumption.create")
    issue = new_issue(client, a, [(a.item, "2", None)]).json()
    assert issue["created_by_name"] == a.staff.full_name
    assert confirm(client, issue["id"]).status_code == 403  # confirming needs consumption.update

    grant(db, a.staff, a.admin, "consumption.update")
    assert confirm(client, issue["id"]).status_code == 200  # 4b-3: own draft
    record = new_return(client, client.get(f"{ISSUES}/{issue['id']}").json(), [(a.item, "1", None)]).json()["returns"][0]
    assert client.post(f"/api/kitchen-returns/{record['id']}/confirm").status_code == 200
    # Reversals stay with ADMIN and KITCHEN_MANAGER, whatever STAFF hold.
    grant(db, a.staff, a.admin, "inventory.update")
    assert client.post(f"/api/kitchen-returns/{record['id']}/reverse", json={"reason": "staff"}).status_code == 403
    assert client.post(f"{ISSUES}/{issue['id']}/reverse", json={"reason": "staff"}).status_code == 403


def test_form_options_serve_staff_without_menu_or_inventory_codes(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.staff)
    assert client.get(f"{ISSUES}/options").status_code == 403
    grant(db, a.staff, a.admin, "consumption.read")
    assert client.get(f"{ISSUES}/options").status_code == 403  # viewing is not recording

    grant(db, a.staff, a.admin, "consumption.create")
    options = client.get(f"{ISSUES}/options").json()

    assert [s["name"] for s in options["meal_sessions"]] == ["Lunch", "Dinner"]
    assert sorted(m["name"] for m in options["menus"]) == ["Dal Fry", "Veg Biryani"]
    assert [i["name"] for i in options["items"]] == ["Rice", "Toor Dal"]
    assert {u["symbol"] for u in options["units"]} >= {"kg", "g"} and options["conversions"]
    assert options["stock_visible"] is False and options["balances"] is None
    # The master-data lists still refuse this user: the form does not need them.
    assert client.get("/api/master/menus").status_code == 403
    assert client.get("/api/master/items").status_code == 403

    grant(db, a.staff, a.admin, "inventory.read")
    options = client.get(f"{ISSUES}/options").json()
    assert options["stock_visible"] is True and options["balances"][str(a.item.id)] == "20.000"


def test_kitchen_manager_runs_the_whole_workflow(client, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    assert client.get(f"{ISSUES}/options").status_code == 200
    issue = issued_and_confirmed(client, a, [(a.item, "5", None)])
    record = new_return(client, issue, [(a.item, "1", None)]).json()["returns"][0]
    assert client.post(f"/api/kitchen-returns/{record['id']}/confirm").status_code == 200
    assert client.post(f"/api/kitchen-returns/{record['id']}/reverse", json={"reason": "Kitchen manager correction"}).status_code == 200
    assert client.post(f"{ISSUES}/{issue['id']}/reverse", json={"reason": "Kitchen manager correction"}).status_code == 200


def test_another_campus_cannot_see_or_act_on_issues(client, kitchen):
    a, b = kitchen.a, kitchen.b
    act_as(client, a.admin)
    issue = issued_and_confirmed(client, a, [(a.item, "1", None)])
    act_as(client, b.admin)
    assert client.get(f"{ISSUES}/{issue['id']}").status_code == 404
    assert confirm(client, issue["id"]).status_code == 404
    assert client.post(f"{ISSUES}/{issue['id']}/reverse", json={"reason": "other"}).status_code == 404
    assert client.get(ISSUES).json()["total"] == 0
    # Campus A's item, session or menu cannot be used from campus B.
    response = client.post(ISSUES, json={"issue_date": campus_today().isoformat(), "meal_session_id": b.lunch.id,
                                         "menu_id": b.menu.id, "lines": [{"item_id": a.item.id, "quantity": "1"}]})
    assert response.status_code == 404


def test_list_filters_and_counts(client, kitchen):
    a = kitchen.a
    act_as(client, a.admin)
    issued_and_confirmed(client, a, [(a.item, "1", None)], issue_date=days_ago(2))
    new_issue(client, a, [(a.dal, "1", None)], session=a.dinner, menu=a.dal_fry)

    listed = client.get(ISSUES).json()
    assert listed["status_counts"] == {"DRAFT": 1, "CONFIRMED": 1, "CANCELLED": 0, "REVERSED": 0}
    assert [i["issue_number"] for i in listed["items"]] == ["KI-00002", "KI-00001"]  # newest date first
    assert client.get(ISSUES, params={"status": "DRAFT"}).json()["items"][0]["menu_name"] == "Dal Fry"
    assert client.get(ISSUES, params={"item_id": a.dal.id}).json()["total"] == 1
    assert client.get(ISSUES, params={"date_to": days_ago(1)}).json()["total"] == 1
    assert client.get(ISSUES, params={"search": "ki-00002"}).json()["total"] == 1


def test_every_step_is_audited(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.admin)
    issue = new_issue(client, a, [(a.item, "4", None)]).json()
    client.put(f"{ISSUES}/{issue['id']}", json={"issue_date": campus_today().isoformat(), "meal_session_id": a.lunch.id,
                                                "menu_id": a.biryani.id, "lines": [{"item_id": a.item.id, "quantity": "3"}]})
    issue = confirm(client, issue["id"]).json()
    record = new_return(client, issue, [(a.item, "1", None)]).json()["returns"][0]
    client.post(f"/api/kitchen-returns/{record['id']}/confirm")
    client.post(f"/api/kitchen-returns/{record['id']}/reverse", json={"reason": "audit"})
    client.post(f"{ISSUES}/{issue['id']}/reverse", json={"reason": "audit"})

    trail = [(x.entity_type, x.action) for x in db.query(AuditLog).filter(
        AuditLog.entity_type.in_(("KITCHEN_ISSUE", "KITCHEN_RETURN"))).order_by(AuditLog.id)]
    assert trail == [("KITCHEN_ISSUE", "CREATE"), ("KITCHEN_ISSUE", "UPDATE"), ("KITCHEN_ISSUE", "CONFIRM"),
                     ("KITCHEN_RETURN", "CREATE"), ("KITCHEN_RETURN", "CONFIRM"), ("KITCHEN_RETURN", "REVERSE"),
                     ("KITCHEN_ISSUE", "REVERSE")]


# ============================================================
# AT01 — STOCK MOVEMENTS AND BALANCE RECONCILIATION
# ============================================================

def test_at01_receipt_issue_and_return_reconcile_with_the_ledger(client, db, kitchen):
    """Accept a receipt, issue to the kitchen, return unused: the receipt
    posts once, the issue lowers and the return restores stock, and at every
    step the ledger's running balance equals the displayed balance."""
    a = kitchen.a
    act_as(client, a.admin)

    def check(expected):
        ledger = client.get(f"/api/stock/items/{a.dal.id}/ledger").json()
        shown = next(r for r in client.get("/api/stock/balances", params={"search": "Toor"}).json()["items"])
        assert ledger["item"]["balance"] == shown["balance"] == expected
        assert ledger["movements"][0]["balance_after"] == expected

    bill = create_bill(client, a, "AT01-1", [(a.dal, "10")])
    line_id = bill_lines(client, bill["id"])[0]["purchase_item_id"]
    receipt = draft(client, bill["id"], [(line_id, "10", "10", "0")], receipt_date=campus_today().isoformat()).json()
    assert client.post(f"/api/receipts/{receipt['id']}/accept").status_code == 200
    assert client.post(f"/api/receipts/{receipt['id']}/accept").status_code == 409  # posts once
    check("10.000")

    issue = issued_and_confirmed(client, a, [(a.dal, "6", None)], session=a.dinner, menu=a.dal_fry)
    check("4.000")
    record = new_return(client, issue, [(a.dal, "1500", a.g)]).json()["returns"][0]
    client.post(f"/api/kitchen-returns/{record['id']}/confirm")
    check("5.500")

    rows = list(reversed(client.get(f"/api/stock/items/{a.dal.id}/ledger").json()["movements"]))
    assert [(r["movement_type"], r["signed_quantity"], r["balance_after"], r["document_number"]) for r in rows] == [
        ("RECEIPT", "10.000", "10.000", None),
        ("ISSUE", "-6.000", "4.000", issue["issue_number"]),
        ("UNUSED_RETURN", "1.500", "5.500", "KR-00001"),
    ]
    assert rows[1]["kitchen_issue_id"] == rows[2]["kitchen_issue_id"] == issue["id"]
    log = client.get("/api/stock-movements", params={"item_id": a.dal.id}).json()["items"]
    assert {r["document_number"] for r in log} == {None, issue["issue_number"], "KR-00001"}
