"""
Stage 5: meal records (MEAL01–MEAL05), per docs/STAGE-5-MEAL-PLAN.md
(decisions 5-1 to 5-10, approved 23 November 2026; closing needs
meal.update, reopening is ADMIN and KITCHEN_MANAGER with a reason).

Interim rules tested here are not client decisions: retained food carried
once, whole, as its own dish line (client question Q11); reopening as the
correction route (proposal §4.2 note); the 14-day window and per-group
actual counts (client question on headcount collection).

In-memory SQLite with the shared fixtures of test_operational_authority and
the kitchen fixture of test_kitchen_issues (campus A: Lunch with menu Veg
Biryani, Dinner with Dal Fry, an inactive session; kg and g; Rice with 20 kg
opening stock, Toor Dal). tests/test_meals_postgres.py covers races and the
PostgreSQL constraints.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.clock import campus_today
from app.models import AuditLog, Unit
from app.models.meals import MealDish, MealLeftover, MealRecord
from app.models.purchases import GoodsReceipt, Purchase, StockMovement, SupplierPayment, SupplierReturn

from tests.test_kitchen_issues import (  # noqa: F401 (fixtures)
    days_ago,
    issued_and_confirmed,
    kitchen,
    new_issue,
)
from tests.test_operational_authority import (  # noqa: F401 (fixtures)
    act_as,
    client,
    db,
    grant,
    world,
)

MEALS = "/api/meal-records"


def today():
    return campus_today().isoformat()


def create(client, place, day=None, session=None, counts=(120, 10, 5), remarks=None):
    return client.post(MEALS, json={
        "meal_date": day or today(), "meal_session_id": (session or place.lunch).id,
        "expected_students": counts[0], "expected_staff": counts[1], "expected_guests": counts[2], "remarks": remarks,
    })


def created(client, place, **kwargs):
    response = create(client, place, **kwargs)
    assert response.status_code == 201, response.text
    return response.json()


def set_counts(client, record, expected=(120, 10, 5), actual=(110, 9, 4)):
    body = dict(zip(("expected_students", "expected_staff", "expected_guests"), expected))
    if actual is not None:
        body.update(zip(("actual_students", "actual_staff", "actual_guests"), actual))
    return client.put(f"{MEALS}/{record['id']}", json=body)


def add_dish(client, record, name, qty, unit, menu=None):
    return client.post(f"{MEALS}/{record['id']}/dishes", json={
        "dish_name": name, "output_quantity": qty, "unit_id": unit.id, **({"menu_id": menu.id} if menu else {})})


def dish_named(record, name):
    return next(d for d in record["dishes"] if d["dish_name"] == name)


def distribute(client, record, dish, distributed, remaining, leftovers=()):
    return client.put(f"{MEALS}/{record['id']}/dishes/{dish['id']}/distribution", json={
        "distributed_quantity": distributed, "remaining_quantity": remaining,
        "leftovers": [{"classification": c, "quantity": q, "remarks": r} for c, q, r in leftovers],
    })


def ok(response, code=200):
    assert response.status_code == code, response.text
    return response.json()


def closed_record_with_rice_retained(client, place, day=None, retained="3"):
    """A closed Lunch record with 20 kg of rice: 15 served, 5 left (3 retained, 2 wasted)."""
    record = created(client, place, day=day)
    record = ok(add_dish(client, record, "Steamed rice", "20", place.kg), 201)
    rice = dish_named(record, "Steamed rice")
    rest = Decimal("5") - Decimal(retained)
    leftovers = [("RETAINED", retained, "Kept in the cold room")] + ([("WASTED", str(rest), "Spilt")] if rest else [])
    ok(distribute(client, record, rice, "15", "5", leftovers))
    ok(set_counts(client, record))
    return ok(client.post(f"{MEALS}/{record['id']}/close"))


def carry(client, record, leftover_id):
    return client.post(f"{MEALS}/{record['id']}/carry", json={"leftover_id": leftover_id})


def money_and_stock_rows(db):
    return tuple(db.query(model).count() for model in (StockMovement, Purchase, GoodsReceipt, SupplierReturn, SupplierPayment))


# ============================================================
# MEAL01 — DAILY MEAL SESSIONS AND HEADCOUNTS
# ============================================================

def test_meal01_record_has_a_date_session_and_separate_expected_counts(client, kitchen):
    a = kitchen.a
    act_as(client, a.manager)

    record = created(client, a, counts=(250, 12, 3), remarks="Exam week")

    assert (record["meal_date"], record["meal_session_name"], record["status"]) == (today(), "Lunch", "OPEN")
    assert (record["expected_students"], record["expected_staff"], record["expected_guests"]) == (250, 12, 3)
    assert record["expected_total"] == 265 and record["actual_total"] is None and record["remarks"] == "Exam week"


def test_meal01_actual_people_served_are_recorded_after_the_meal_and_kept_separate(client, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    record = created(client, a, counts=(250, 12, 3))

    updated = ok(set_counts(client, record, expected=(250, 12, 3), actual=(231, 11, 0)))

    assert (updated["expected_students"], updated["expected_staff"], updated["expected_guests"]) == (250, 12, 3)
    assert (updated["actual_students"], updated["actual_staff"], updated["actual_guests"]) == (231, 11, 0)
    assert (updated["expected_total"], updated["actual_total"]) == (265, 242)
    future = created(client, a, day=(campus_today() + timedelta(days=2)).isoformat(), session=a.dinner)
    refused = set_counts(client, future)
    assert refused.status_code == 422 and "on or after the meal date" in refused.json()["detail"]
    assert set_counts(client, record, actual=None).status_code == 200  # expected only is fine
    partial = client.put(f"{MEALS}/{record['id']}", json={
        "expected_students": 1, "expected_staff": 0, "expected_guests": 0, "actual_students": 5})
    assert partial.status_code == 422
    assert set_counts(client, record, expected=(-1, 0, 0), actual=None).status_code == 422


def test_meal01_one_record_per_campus_date_and_session(client, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    first = created(client, a)

    second = create(client, a)

    assert second.status_code == 409 and f"#{first['id']}" in second.json()["detail"]
    assert create(client, a, session=a.dinner).status_code == 201
    assert create(client, a, day=days_ago(1)).status_code == 201
    ok(client.post(f"{MEALS}/{first['id']}/cancel", json={"reason": "Wrong session chosen"}))
    assert create(client, a).status_code == 201  # a cancelled record frees the date and session


def test_meal01_expected_counts_up_to_14_days_ahead_interim(client, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    assert create(client, a, day=(campus_today() + timedelta(days=14)).isoformat()).status_code == 201
    refused = create(client, a, day=(campus_today() + timedelta(days=15)).isoformat())
    assert refused.status_code == 422 and "14 days ahead" in refused.json()["detail"]
    assert create(client, a, session=a.old_session).status_code == 422


# ============================================================
# MEAL02 — PREPARED DISHES
# ============================================================

def test_meal02_each_dish_has_an_output_quantity_and_unit_and_belongs_to_the_meal(client, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    record = created(client, a)

    record = ok(add_dish(client, record, "Veg biryani", "42.5", a.kg, menu=a.biryani), 201)
    record = ok(add_dish(client, record, "Raita", "8000", a.g), 201)

    biryani, raita = dish_named(record, "Veg biryani"), dish_named(record, "Raita")
    assert (biryani["output_quantity"], biryani["unit_symbol"], biryani["menu_name"]) == ("42.500", "kg", "Veg Biryani")
    assert (raita["available_quantity"], raita["unit_symbol"]) == ("8000.000", "g")
    assert record["meal_session_name"] == "Lunch"
    assert add_dish(client, record, "Dal", "0", a.kg).status_code == 422
    assert add_dish(client, record, "  ", "1", a.kg).status_code == 422
    wrong_menu = add_dish(client, record, "Dal fry", "5", a.kg, menu=a.dal_fry)
    assert wrong_menu.status_code == 422 and "another meal session" in wrong_menu.json()["detail"]


def test_meal02_ingredient_issues_of_the_same_date_and_session_are_linked_with_actual_net_usage(client, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    issue = issued_and_confirmed(client, a, [(a.item, "6", None)])  # Lunch, today
    ret = client.post(f"/api/kitchen-issues/{issue['id']}/returns", json={
        "return_date": today(), "lines": [{"issue_item_id": issue["lines"][0]["id"], "quantity": "1.5"}]}).json()
    ok(client.post(f"/api/kitchen-returns/{ret['returns'][0]['id']}/confirm"))
    draft = new_issue(client, a, [(a.dal, "1", None)]).json()          # draft: listed, no usage
    issued_and_confirmed(client, a, [(a.item, "2", None)], session=a.dinner, menu=a.dal_fry)  # other session

    record = created(client, a)

    assert [(i["issue_number"], i["status"]) for i in record["linked_issues"]] == [
        (issue["issue_number"], "CONFIRMED"), (draft["issue_number"], "DRAFT")]
    assert record["usage"] == [{"item_id": a.item.id, "item_name": "Rice", "unit_symbol": "kg",
                                "issued_quantity": "6.000", "returned_quantity": "1.500", "net_quantity": "4.500"}]
    linked = client.get(f"/api/kitchen-issues/{issue['id']}").json()["meal_record"]
    assert linked == {"id": record["id"], "status": "OPEN"}


# ============================================================
# MEAL03 — DISTRIBUTION
# ============================================================

def test_meal03_available_distributed_and_remaining_are_recorded_separately(client, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    record = ok(add_dish(client, created(client, a), "Veg biryani", "40", a.kg), 201)
    dish = dish_named(record, "Veg biryani")

    record = ok(distribute(client, record, dish, "36.5", "3.5"))

    dish = dish_named(record, "Veg biryani")
    assert (dish["available_quantity"], dish["distributed_quantity"], dish["remaining_quantity"]) == ("40.000", "36.500", "3.500")
    assert dish["unit_symbol"] == "kg"


def test_meal03_people_counts_and_food_quantities_are_never_interchangeable(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    record = ok(add_dish(client, created(client, a, counts=(100, 0, 0)), "Chapati", "300", a.g), 201)
    dish = dish_named(record, "Chapati")

    record = ok(set_counts(client, record, expected=(400, 0, 0), actual=(390, 0, 0)))

    assert dish_named(record, "Chapati")["available_quantity"] == "300.000"
    record = ok(distribute(client, record, dish, "250", "50", [("WASTED", "50", "Dropped tray")]))
    assert (record["expected_total"], record["actual_total"]) == (400, 390)
    columns = {c.name for c in MealDish.__table__.columns} | {c.name for c in MealLeftover.__table__.columns}
    assert not any("student" in c or "guest" in c or "staff" in c for c in columns)


# ============================================================
# MEAL04 — LEFTOVERS
# ============================================================

def test_meal04_leftovers_are_classified_with_quantity_and_remarks(client, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    record = ok(add_dish(client, created(client, a), "Veg biryani", "40", a.kg), 201)
    dish = dish_named(record, "Veg biryani")

    record = ok(distribute(client, record, dish, "30", "10", [
        ("RETAINED", "4", "Kept for dinner"), ("RETURNED_TO_SUPPLIER", "1", "Caterer took back a tray"),
        ("WASTED", "3", "Plate waste"), ("DISPOSED", "2", "Given to the farm")]))

    rows = dish_named(record, "Veg biryani")["leftovers"]
    assert [(r["classification"], r["quantity"], r["remarks"]) for r in rows] == [
        ("RETAINED", "4.000", "Kept for dinner"), ("RETURNED_TO_SUPPLIER", "1.000", "Caterer took back a tray"),
        ("WASTED", "3.000", "Plate waste"), ("DISPOSED", "2.000", "Given to the farm")]
    no_remarks = distribute(client, record, dish, "30", "10", [("WASTED", "10", " ")])
    assert no_remarks.status_code == 422
    assert distribute(client, record, dish, "30", "10", [("EATEN", "10", "unknown class")]).status_code == 422


def test_meal04_retained_food_is_carried_forward_traceably_and_never_a_purchase(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    rows_before = money_and_stock_rows(db)
    source = closed_record_with_rice_retained(client, a, day=days_ago(1))
    retained = dish_named(source, "Steamed rice")["leftovers"][0]
    dinner = created(client, a, session=a.dinner)

    available = client.get(f"{MEALS}/retained", params={"for_record": dinner["id"]}).json()["items"]
    assert [(r["leftover_id"], r["dish_name"], r["quantity"], r["unit_symbol"]) for r in available] == [
        (retained["id"], "Steamed rice", "3.000", "kg")]
    dinner = ok(carry(client, dinner, retained["id"]), 201)

    carried = dinner["dishes"][0]
    assert (carried["dish_name"], carried["available_quantity"], carried["unit_symbol"], carried["output_quantity"]) == (
        "Steamed rice", "3.000", "kg", "0.000")
    assert carried["carried_in"]["leftover_id"] == retained["id"]
    assert carried["carried_in"]["record"]["id"] == source["id"]
    source_now = client.get(f"{MEALS}/{source['id']}").json()
    assert dish_named(source_now, "Steamed rice")["leftovers"][0]["carried_to"]["record"]["id"] == dinner["id"]
    assert money_and_stock_rows(db) == rows_before
    assert client.get(f"{MEALS}/retained", params={"for_record": dinner["id"]}).json()["items"] == []


# ============================================================
# MEAL05 — RECONCILIATION
# ============================================================

def test_meal05_available_must_equal_distributed_plus_remaining(client, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    record = ok(add_dish(client, created(client, a), "Veg biryani", "40", a.kg), 201)
    dish = dish_named(record, "Veg biryani")

    refused = distribute(client, record, dish, "36", "3")

    assert refused.status_code == 422
    assert "available 40.000 kg must equal distributed + remaining (36.000 + 3.000 = 39.000 kg)" in refused.json()["detail"]


def test_meal05_leftovers_must_reconcile_with_the_remaining_quantity_and_never_count_twice(client, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    record = ok(add_dish(client, created(client, a), "Veg biryani", "40", a.kg), 201)
    dish = dish_named(record, "Veg biryani")

    short = distribute(client, record, dish, "36", "4", [("WASTED", "3", "Plate waste")])
    over = distribute(client, record, dish, "36", "4", [("WASTED", "3", "Plate waste"), ("DISPOSED", "2", "Farm")])
    twice = distribute(client, record, dish, "36", "4", [("WASTED", "2", "Plate"), ("WASTED", "2", "Plate again")])
    nothing_left = distribute(client, record, dish, "40", "0", [("WASTED", "1", "Plate")])

    assert short.status_code == 422 and "add up to 3.000 kg but 4.000 kg remains" in short.json()["detail"]
    assert over.status_code == 422 and twice.status_code == 422 and nothing_left.status_code == 422
    assert ok(distribute(client, record, dish, "36", "4"))["dishes"][0]["reconciled"] is False  # not classified yet


def test_meal05_closing_is_refused_until_everything_reconciles(client, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    record = ok(add_dish(client, created(client, a), "Veg biryani", "40", a.kg), 201)
    dish = dish_named(record, "Veg biryani")

    first = client.post(f"{MEALS}/{record['id']}/close")
    ok(distribute(client, record, dish, "36", "4"))
    ok(set_counts(client, record))
    second = client.post(f"{MEALS}/{record['id']}/close")

    assert first.status_code == 422
    assert "actual people served" in first.json()["detail"] and "distributed and remaining" in first.json()["detail"]
    assert second.status_code == 422 and "leftovers classified 0.000 kg, remaining 4.000 kg" in second.json()["detail"]
    ok(distribute(client, record, dish, "36", "4", [("WASTED", "4", "Plate waste")]))
    closed = ok(client.post(f"{MEALS}/{record['id']}/close"))
    assert closed["status"] == "CLOSED" and closed["closed_by_name"] == "KITCHEN_MANAGER A"


def test_meal05_the_database_refuses_inconsistent_quantities(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    record = ok(add_dish(client, created(client, a), "Veg biryani", "40", a.kg), 201)
    dish = db.get(MealDish, record["dishes"][0]["id"])

    dish.distributed_quantity, dish.remaining_quantity = Decimal("30"), Decimal("5")
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.add(MealLeftover(campus_id=a.campus.id, meal_record_id=record["id"], dish_id=dish.id, classification="WASTED",
                        quantity=Decimal("1"), unit_id=a.g.id, remarks="wrong unit", created_by=a.manager.id))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


# ============================================================
# RETAINED FOOD CARRIED FORWARD (interim, Q11)
# ============================================================

def test_retained_food_is_carried_only_once(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    source = closed_record_with_rice_retained(client, a, day=days_ago(1))
    retained_id = dish_named(source, "Steamed rice")["leftovers"][0]["id"]
    dinner = created(client, a, session=a.dinner)
    lunch = created(client, a)
    ok(carry(client, dinner, retained_id), 201)

    again = carry(client, lunch, retained_id)

    assert again.status_code == 409 and "can be carried only once" in again.json()["detail"]
    assert carry(client, dinner, retained_id).status_code == 409
    carried = db.query(MealDish).filter(MealDish.source_leftover_id == retained_id).one()
    duplicate = MealDish(campus_id=a.campus.id, meal_record_id=lunch["id"], dish_name="Steamed rice",
                         unit_id=carried.unit_id, output_quantity=0, carried_quantity=carried.carried_quantity,
                         available_quantity=carried.carried_quantity, source_leftover_id=retained_id,
                         source_dish_id=carried.source_dish_id, source_meal_record_id=carried.source_meal_record_id,
                         source_classification="RETAINED", created_by=a.manager.id)
    db.add(duplicate)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_carry_forward_rules(client, kitchen):
    a, b = kitchen.a, kitchen.b
    act_as(client, a.manager)
    yesterday = closed_record_with_rice_retained(client, a, day=days_ago(1))
    retained_id = dish_named(yesterday, "Steamed rice")["leftovers"][0]["id"]
    open_source = created(client, a, day=days_ago(2))
    open_source = ok(add_dish(client, open_source, "Dal", "10", a.kg), 201)
    open_source = ok(distribute(client, open_source, open_source["dishes"][0], "8", "2", [("RETAINED", "2", "Kept")]))
    earlier = created(client, a, day=days_ago(3))
    today_lunch = created(client, a)

    from_open = carry(client, today_lunch, open_source["dishes"][0]["leftovers"][0]["id"])
    into_earlier = carry(client, earlier, retained_id)
    into_itself = carry(client, yesterday, retained_id)
    wasted_id = next(l["id"] for l in dish_named(yesterday, "Steamed rice")["leftovers"] if l["classification"] == "WASTED")
    not_retained = carry(client, today_lunch, wasted_id)

    assert from_open.status_code == 409 and "not closed" in from_open.json()["detail"]
    assert into_earlier.status_code == 422 and "same or a later date" in into_earlier.json()["detail"]
    assert into_itself.status_code in (409, 422)
    assert not_retained.status_code == 422
    act_as(client, b.admin)
    assert carry(client, today_lunch, retained_id).status_code == 404


def test_a_carried_source_is_locked_even_when_its_record_is_reopened(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    source = closed_record_with_rice_retained(client, a, day=days_ago(1))
    rice = dish_named(source, "Steamed rice")
    retained_id = rice["leftovers"][0]["id"]
    dinner = ok(carry(client, created(client, a, session=a.dinner), retained_id), 201)
    act_as(client, a.admin)
    ok(client.post(f"{MEALS}/{source['id']}/reopen", json={"reason": "Correct the waste remarks"}))

    changed = distribute(client, source, rice, "15", "5", [("RETAINED", "2", "Kept"), ("WASTED", "3", "Spilt")])
    cleared = client.delete(f"{MEALS}/{source['id']}/dishes/{rice['id']}/distribution")
    removed = client.delete(f"{MEALS}/{source['id']}/dishes/{rice['id']}")
    cancelled = client.post(f"{MEALS}/{source['id']}/cancel", json={"reason": "try to cancel"})
    remarks_only = distribute(client, source, rice, "15", "5", [("RETAINED", "3", "Kept cold, labelled"), ("WASTED", "2", "Spilt")])

    for refused in (changed, cleared, removed, cancelled):
        assert refused.status_code == 409, refused.text
    assert "carried into" in changed.json()["detail"]
    assert remarks_only.status_code == 200
    # The database-level lock (composite foreign key fk_meal_dish_carried_from)
    # is tested on PostgreSQL (test_meals_postgres.py): SQLAlchemy does not
    # always create that added-later key on the SQLite test schema.
    assert dish_named(client.get(f"{MEALS}/{dinner['id']}").json(), "Steamed rice")["available_quantity"] == "3.000"


def test_removing_the_carried_line_frees_the_source(client, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    source = closed_record_with_rice_retained(client, a, day=days_ago(1))
    retained_id = dish_named(source, "Steamed rice")["leftovers"][0]["id"]
    dinner = ok(carry(client, created(client, a, session=a.dinner), retained_id), 201)
    carried = dinner["dishes"][0]

    edit = client.put(f"{MEALS}/{dinner['id']}/dishes/{carried['id']}", json={
        "dish_name": "Fried rice", "output_quantity": "5", "unit_id": a.kg.id})
    remarks = client.put(f"{MEALS}/{dinner['id']}/dishes/{carried['id']}/remarks", json={"remarks": "Reheated"})
    removed = client.delete(f"{MEALS}/{dinner['id']}/dishes/{carried['id']}")

    assert edit.status_code == 409 and remarks.status_code == 200
    assert removed.status_code == 200 and removed.json()["dishes"] == []
    lunch = created(client, a)
    assert carry(client, lunch, retained_id).status_code == 201


# ============================================================
# STATUS, CLOSE, CANCEL, REOPEN, HISTORY (5-1, 5-9)
# ============================================================

def test_a_closed_record_refuses_every_change(client, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    record = closed_record_with_rice_retained(client, a)
    dish = record["dishes"][0]

    attempts = [
        set_counts(client, record),
        add_dish(client, record, "Dal", "5", a.kg),
        client.put(f"{MEALS}/{record['id']}/dishes/{dish['id']}", json={"dish_name": "x", "output_quantity": "1", "unit_id": a.kg.id}),
        client.delete(f"{MEALS}/{record['id']}/dishes/{dish['id']}"),
        distribute(client, record, dish, "20", "0"),
        client.delete(f"{MEALS}/{record['id']}/dishes/{dish['id']}/distribution"),
        client.post(f"{MEALS}/{record['id']}/close"),
        client.post(f"{MEALS}/{record['id']}/cancel", json={"reason": "late cancel"}),
    ]

    for response in attempts:
        assert response.status_code == 409, response.text
    assert "closed and cannot be changed" in attempts[0].json()["detail"]


def test_reopening_is_admin_and_kitchen_manager_only_with_a_reason(client, db, kitchen):
    a = kitchen.a
    for code in ("meal.create", "meal.read", "meal.update", "audit.read"):
        grant(db, a.staff, a.admin, code)
    act_as(client, a.manager)
    record = closed_record_with_rice_retained(client, a)

    act_as(client, a.staff)
    assert client.post(f"{MEALS}/{record['id']}/reopen", json={"reason": "staff try"}).status_code == 403
    act_as(client, a.manager)
    assert client.post(f"{MEALS}/{record['id']}/reopen", json={"reason": ""}).status_code == 422
    reopened = ok(client.post(f"{MEALS}/{record['id']}/reopen", json={"reason": "Waste was weighed wrongly"}))
    assert (reopened["status"], reopened["reopened_by_name"], reopened["reopen_reason"], reopened["reopen_count"]) == (
        "OPEN", "KITCHEN_MANAGER A", "Waste was weighed wrongly", 1)
    assert client.post(f"{MEALS}/{record['id']}/reopen", json={"reason": "again"}).status_code == 409
    act_as(client, a.admin)
    ok(client.post(f"{MEALS}/{record['id']}/close"))
    assert ok(client.post(f"{MEALS}/{record['id']}/reopen", json={"reason": "Second correction"}))["reopen_count"] == 2


def test_the_history_keeps_every_change_closing_and_reopening(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    record = closed_record_with_rice_retained(client, a)
    rice = record["dishes"][0]
    act_as(client, a.admin)
    ok(client.post(f"{MEALS}/{record['id']}/reopen", json={"reason": "Correct the remarks"}))
    ok(distribute(client, record, rice, "15", "5", [("RETAINED", "3", "Kept cold"), ("WASTED", "2", "Plate waste")]))
    ok(client.post(f"{MEALS}/{record['id']}/close"))

    history = ok(client.get(f"{MEALS}/{record['id']}/history"))["items"]

    assert [h["action"] for h in history] == [
        "CREATE", "ADD_DISH", "SET_DISTRIBUTION", "UPDATE_COUNTS", "CLOSE", "REOPEN", "SET_DISTRIBUTION", "CLOSE"]
    reopen = history[5]
    assert (reopen["user_name"], reopen["details"]["reason"]) == ("ADMIN A", "Correct the remarks")
    assert reopen["details"]["previous_closing"]["closed_by"] == a.manager.id
    assert history[6]["details"]["before"]["leftovers"][1]["remarks"] == "Spilt"
    assert history[6]["details"]["after"]["leftovers"][1]["remarks"] == "Plate waste"
    assert history[4]["details"]["dishes"][0]["distributed_quantity"] == "15.000"  # first closing snapshot kept
    assert history[7]["user_name"] == "ADMIN A"
    assert db.query(AuditLog).filter_by(entity_type="MEAL_RECORD", entity_id=record["id"]).count() == 8


def test_cancelling_an_open_record(client, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    record = created(client, a)

    assert client.post(f"{MEALS}/{record['id']}/cancel", json={"reason": "x"}).status_code == 422
    cancelled = ok(client.post(f"{MEALS}/{record['id']}/cancel", json={"reason": "Recorded for the wrong session"}))

    assert (cancelled["status"], cancelled["cancellation_reason"]) == ("CANCELLED", "Recorded for the wrong session")
    assert set_counts(client, record).status_code == 409
    act_as(client, a.admin)
    assert client.post(f"{MEALS}/{record['id']}/reopen", json={"reason": "undo"}).status_code == 409


def test_issues_changed_after_closing_are_shown_and_stage4_is_not_blocked(client, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    issued_and_confirmed(client, a, [(a.item, "4", None)])
    record = closed_record_with_rice_retained(client, a)
    assert record["usage_changes_since_closing"] == []

    late = issued_and_confirmed(client, a, [(a.item, "1", None)])  # Stage 4 works after the meal closed
    now = client.get(f"{MEALS}/{record['id']}").json()

    assert late["status"] == "CONFIRMED"
    assert now["usage_changes_since_closing"] == [{"item_id": a.item.id, "item_name": "Rice", "unit_symbol": "kg",
                                                    "net_at_closing": "4.000", "net_now": "5.000"}]
    act_as(client, a.admin)
    ok(client.post(f"{MEALS}/{record['id']}/reopen", json={"reason": "Late issue entered"}))
    assert ok(client.post(f"{MEALS}/{record['id']}/close"))["usage_changes_since_closing"] == []


def test_meal_actions_never_touch_stock_purchases_or_supplier_money(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    rows_before = money_and_stock_rows(db)
    source = closed_record_with_rice_retained(client, a, day=days_ago(1))
    dinner = ok(carry(client, created(client, a, session=a.dinner), source["dishes"][0]["leftovers"][0]["id"]), 201)
    ok(distribute(client, dinner, dinner["dishes"][0], "2", "1", [("RETURNED_TO_SUPPLIER", "1", "Back to caterer")]))
    ok(set_counts(client, dinner))
    ok(client.post(f"{MEALS}/{dinner['id']}/close"))

    assert money_and_stock_rows(db) == rows_before


# ============================================================
# PERMISSIONS (5-1) AND CAMPUS ISOLATION
# ============================================================

def test_staff_permissions_follow_the_meal_codes(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    record = ok(add_dish(client, created(client, a), "Veg biryani", "40", a.kg), 201)
    dish = record["dishes"][0]

    act_as(client, a.staff)  # no meal codes
    for response in (client.get(MEALS), client.get(f"{MEALS}/{record['id']}"), client.get(f"{MEALS}/options"),
                     create(client, a, session=a.dinner), set_counts(client, record),
                     client.post(f"{MEALS}/{record['id']}/close")):
        assert response.status_code == 403, response.request.url

    grant(db, a.staff, a.admin, "meal.read")
    assert client.get(MEALS).json()["total"] == 1 and client.get(f"{MEALS}/{record['id']}").status_code == 200
    assert create(client, a, session=a.dinner).status_code == 403 and set_counts(client, record).status_code == 403
    assert client.get(f"{MEALS}/{record['id']}/history").status_code == 403

    grant(db, a.staff, a.admin, "meal.create")
    staff_record = created(client, a, session=a.dinner)
    assert add_dish(client, staff_record, "Dal", "5", a.kg).status_code == 403

    grant(db, a.staff, a.admin, "meal.update")
    ok(distribute(client, record, dish, "40", "0"))
    ok(set_counts(client, record))
    assert ok(client.post(f"{MEALS}/{record['id']}/close"))["closed_by_name"] == "STAFF A"
    assert client.post(f"{MEALS}/{record['id']}/reopen", json={"reason": "staff try"}).status_code == 403
    assert client.get(f"{MEALS}/{record['id']}/history").status_code == 403


def test_admin_and_kitchen_manager_hold_the_meal_codes(client, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    assert {"meal.create", "meal.read", "meal.update"} <= set(client.get("/api/authorization/me").json()["permissions"])
    act_as(client, a.admin)
    assert {"meal.create", "meal.read", "meal.update"} <= set(client.get("/api/authorization/me").json()["permissions"])


def test_another_campus_sees_nothing_and_cannot_act(client, kitchen):
    a, b = kitchen.a, kitchen.b
    act_as(client, a.manager)
    record = closed_record_with_rice_retained(client, a)

    act_as(client, b.admin)
    assert client.get(MEALS).json()["total"] == 0
    assert {s["name"] for s in client.get(f"{MEALS}/options").json()["meal_sessions"]} == {"Lunch"}
    for response in (client.get(f"{MEALS}/{record['id']}"), set_counts(client, record),
                     client.post(f"{MEALS}/{record['id']}/reopen", json={"reason": "other campus"}),
                     client.get(f"{MEALS}/{record['id']}/history")):
        assert response.status_code == 404, response.request.url
    assert create(client, a).status_code == 422  # campus A's session


def test_list_filters_and_counts(client, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    closed_record_with_rice_retained(client, a, day=days_ago(1))
    created(client, a)
    created(client, a, session=a.dinner)

    listed = client.get(MEALS).json()

    assert listed["status_counts"] == {"OPEN": 2, "CLOSED": 1, "CANCELLED": 0}
    assert client.get(MEALS, params={"status": "CLOSED"}).json()["items"][0]["meal_date"] == days_ago(1)
    assert client.get(MEALS, params={"meal_session_id": a.dinner.id}).json()["total"] == 1
    assert client.get(MEALS, params={"date_from": today(), "date_to": today()}).json()["total"] == 2


# ============================================================
# MASTER DATA STAYS CONSISTENT
# ============================================================

def test_units_and_menus_used_by_meal_dishes_are_protected(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    ok(add_dish(client, created(client, a), "Veg biryani", "40", a.kg, menu=a.biryani), 201)
    act_as(client, a.admin)

    dimension = client.put(f"/api/master/units/{a.kg.id}", json={"name": "Kilogram", "symbol": "kg", "dimension": "volume"})
    menu = client.delete(f"/api/master/menus/{a.biryani.id}")

    assert dimension.status_code == 409 and "meal dishes" in dimension.json()["detail"]
    assert menu.status_code == 409
