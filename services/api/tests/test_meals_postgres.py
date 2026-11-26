"""
Stage 5 meal records on PostgreSQL (kitchen_copilot_test_db, shared
tests/conftest.py fixtures). Covers what SQLite cannot:
- two records for one session saved at once: one is kept;
- closing twice at once, and a change racing the close: never a closed
  record that does not reconcile;
- one retained line carried into two records at once: carried once;
- a carry racing the reopening of its source;
- the database rules for a superuser: the carried source cannot change or
  disappear, one carry per retained line, one live record per session,
  exact reconciliation, leftovers in their dish's unit, closing fields.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.clock import campus_today
from app.core.config import settings
from app.core.security import create_access_token
from app.models import MealSession, Unit
from app.models.meals import MealDish, MealLeftover, MealRecord
from app.models.purchases import StockMovement

from tests.test_authorization import create_test_user
from tests.test_stock_counts_postgres import race_all
from tests.test_stock_ledger_postgres import engine_factory, parallel_clients  # noqa: F401 (fixtures)

MEALS = "/api/meal-records"


def act_as(client, user):
    client.cookies.set(settings.ACCESS_COOKIE_NAME, create_access_token(user.id, user.password_hash))


@pytest.fixture
def meals_pg(client, db, setup_data):
    campus_id = setup_data["campus"].id
    kg = Unit(campus_id=campus_id, name="Kilogram", symbol="kg", dimension="weight")
    g = Unit(campus_id=campus_id, name="Gram", symbol="g", dimension="weight")
    lunch = MealSession(campus_id=campus_id, name="Lunch")
    dinner = MealSession(campus_id=campus_id, name="Dinner")
    db.add_all([kg, g, lunch, dinner])
    db.commit()
    manager = create_test_user(db, campus_id, "KITCHEN_MANAGER")
    return {"campus_id": campus_id, "kg": kg.id, "g": g.id, "lunch": lunch.id, "dinner": dinner.id,
            "admin": setup_data["user"], "manager": manager}


def body(k, session="lunch", day=None):
    return {"meal_date": day or campus_today().isoformat(), "meal_session_id": k[session],
            "expected_students": 100, "expected_staff": 5, "expected_guests": 0}


def reconciled(client, k, session="lunch", day=None, retained="3"):
    """An OPEN record ready to close: 20 kg rice, 15 served, 3 retained, 2 wasted."""
    record = client.post(MEALS, json=body(k, session, day)).json()
    record = client.post(f"{MEALS}/{record['id']}/dishes", json={
        "dish_name": "Steamed rice", "output_quantity": "20", "unit_id": k["kg"]}).json()
    dish = record["dishes"][0]
    rest = str(Decimal("5") - Decimal(retained))
    response = client.put(f"{MEALS}/{record['id']}/dishes/{dish['id']}/distribution", json={
        "distributed_quantity": "15", "remaining_quantity": "5",
        "leftovers": [{"classification": "RETAINED", "quantity": retained, "remarks": "Kept cold"},
                      {"classification": "WASTED", "quantity": rest, "remarks": "Plate waste"}]})
    assert response.status_code == 200, response.text
    response = client.put(f"{MEALS}/{record['id']}", json={**{k2: v for k2, v in body(k).items() if k2.startswith("expected")},
                                                          "actual_students": 95, "actual_staff": 5, "actual_guests": 0})
    assert response.status_code == 200, response.text
    return response.json()


def closed_source(client, k):
    record = reconciled(client, k, day=(campus_today() - timedelta(days=1)).isoformat())
    closed = client.post(f"{MEALS}/{record['id']}/close")
    assert closed.status_code == 200, closed.text
    return closed.json()


def test_two_records_for_one_session_at_once_keep_one(db, meals_pg, parallel_clients):
    outcomes = race_all(parallel_clients, [lambda c: c.post(MEALS, json=body(meals_pg))] * 4)

    assert sorted(outcomes) == [201, 409, 409, 409], outcomes
    db.expire_all()
    assert db.query(MealRecord).filter(MealRecord.status != "CANCELLED").count() == 1


def test_closing_twice_at_once_closes_once(client, db, meals_pg, parallel_clients):
    record = reconciled(client, meals_pg)

    outcomes = race_all(parallel_clients, [lambda c: c.post(f"{MEALS}/{record['id']}/close")] * 4)

    assert sorted(outcomes) == [200, 409, 409, 409], outcomes
    closes = db.execute(text("SELECT count(*) FROM audit_logs WHERE entity_type = 'MEAL_RECORD' "
                             "AND entity_id = :id AND action = 'CLOSE'"), {"id": record["id"]}).scalar()
    assert closes == 1


def test_a_change_racing_the_close_never_leaves_an_unreconciled_closed_record(client, db, meals_pg, parallel_clients):
    for round_number in range(4):
        day = (campus_today() - timedelta(days=round_number + 2)).isoformat()
        record = reconciled(client, meals_pg, day=day)
        dish = record["dishes"][0]
        outcomes = race_all(parallel_clients, [
            lambda c: c.post(f"{MEALS}/{record['id']}/close"),
            lambda c: c.put(f"{MEALS}/{record['id']}/dishes/{dish['id']}/distribution", json={
                "distributed_quantity": "15", "remaining_quantity": "5"}),  # leftovers cleared
        ])
        assert sorted(outcomes) in ([200, 409], [200, 422]), (round_number, outcomes)
        db.expire_all()
        final = db.get(MealRecord, record["id"])
        leftovers = db.query(MealLeftover).filter(MealLeftover.meal_record_id == record["id"]).count()
        assert (final.status, leftovers) in {("CLOSED", 2), ("OPEN", 0)}, (round_number, final.status, leftovers)


def test_one_retained_line_carried_into_two_records_at_once_is_carried_once(client, db, meals_pg, parallel_clients):
    source = closed_source(client, meals_pg)
    leftover_id = next(l["id"] for l in source["dishes"][0]["leftovers"] if l["classification"] == "RETAINED")
    lunch = client.post(MEALS, json=body(meals_pg)).json()
    dinner = client.post(MEALS, json=body(meals_pg, "dinner")).json()

    outcomes = race_all(parallel_clients, [
        lambda c: c.post(f"{MEALS}/{lunch['id']}/carry", json={"leftover_id": leftover_id}),
        lambda c: c.post(f"{MEALS}/{dinner['id']}/carry", json={"leftover_id": leftover_id}),
        lambda c: c.post(f"{MEALS}/{lunch['id']}/carry", json={"leftover_id": leftover_id}),
        lambda c: c.post(f"{MEALS}/{dinner['id']}/carry", json={"leftover_id": leftover_id}),
    ])

    assert sorted(outcomes) == [201, 409, 409, 409], outcomes
    db.expire_all()
    assert db.query(MealDish).filter(MealDish.source_leftover_id == leftover_id).count() == 1


def test_a_carry_racing_the_reopening_of_its_source(client, db, meals_pg, parallel_clients):
    source = closed_source(client, meals_pg)
    leftover_id = next(l["id"] for l in source["dishes"][0]["leftovers"] if l["classification"] == "RETAINED")
    lunch = client.post(MEALS, json=body(meals_pg)).json()
    act_as(client, meals_pg["manager"])  # parallel clients are the Admin; the manager reopens

    outcomes = race_all(parallel_clients[:1] + [client], [
        lambda c: c.post(f"{MEALS}/{lunch['id']}/carry", json={"leftover_id": leftover_id}),
        lambda c: c.post(f"{MEALS}/{source['id']}/reopen", json={"reason": "Correct the waste"}),
    ])

    assert outcomes[1] == 200 and outcomes[0] in (201, 409), outcomes
    db.expire_all()
    carried = db.query(MealDish).filter(MealDish.source_leftover_id == leftover_id).count()
    assert carried == (1 if outcomes[0] == 201 else 0)


def test_postgresql_keeps_a_carried_source_fixed_even_for_a_superuser(client, db, meals_pg):
    source = closed_source(client, meals_pg)
    leftover_id = next(l["id"] for l in source["dishes"][0]["leftovers"] if l["classification"] == "RETAINED")
    lunch = client.post(MEALS, json=body(meals_pg)).json()
    assert client.post(f"{MEALS}/{lunch['id']}/carry", json={"leftover_id": leftover_id}).status_code == 201
    assert db.execute(text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")).scalar() is True

    for sql in ("UPDATE meal_leftovers SET quantity = 1 WHERE id = :id",
                "UPDATE meal_leftovers SET classification = 'DISPOSED' WHERE id = :id",
                "DELETE FROM meal_leftovers WHERE id = :id"):
        with pytest.raises(IntegrityError) as refused:
            db.execute(text(sql), {"id": leftover_id})
        assert "fk_meal_dish_carried_from" in str(refused.value), sql
        db.rollback()
    carried = db.query(MealDish).filter(MealDish.source_leftover_id == leftover_id).one()
    with pytest.raises(IntegrityError) as twice:
        db.execute(text(
            "INSERT INTO meal_dishes (campus_id, meal_record_id, dish_name, unit_id, output_quantity, carried_quantity, "
            "available_quantity, source_leftover_id, source_dish_id, source_meal_record_id, source_classification, "
            "created_by, created_at) SELECT campus_id, :dest, dish_name, unit_id, 0, carried_quantity, available_quantity, "
            "source_leftover_id, source_dish_id, source_meal_record_id, 'RETAINED', created_by, now() "
            "FROM meal_dishes WHERE id = :id"),
            {"dest": client.post(MEALS, json=body(meals_pg, "dinner")).json()["id"], "id": carried.id})
    assert "uq_meal_dish_source_leftover" in str(twice.value)
    db.rollback()


@pytest.mark.parametrize("sql, constraint", [
    ("UPDATE meal_dishes SET distributed_quantity = 10, remaining_quantity = 1", "ck_meal_dish_reconciles"),
    ("UPDATE meal_dishes SET available_quantity = 5", "ck_meal_dish_available"),
    ("UPDATE meal_leftovers SET unit_id = :g", "fk_meal_leftover_dish"),
    ("UPDATE meal_leftovers SET remarks = '  '", "ck_meal_leftover_remarks"),
    ("UPDATE meal_records SET status = 'CLOSED', closed_at = now(), closed_by = created_by, "
     "actual_students = NULL, actual_staff = NULL, actual_guests = NULL", "ck_meal_record_closed"),
    ("UPDATE meal_records SET actual_guests = NULL", "ck_meal_record_actual_complete"),
    ("UPDATE meal_records SET reopen_count = 1", "ck_meal_record_reopened"),
    ("INSERT INTO meal_records (campus_id, meal_date, meal_session_id, status, expected_students, expected_staff, "
     "expected_guests, created_by, created_at, reopen_count) SELECT campus_id, meal_date, meal_session_id, 'OPEN', 0, 0, 0, "
     "created_by, now(), 0 FROM meal_records", "uq_meal_record_session_date"),
])
def test_postgresql_meal_rules_hold_for_a_superuser(client, db, meals_pg, sql, constraint):
    reconciled(client, meals_pg)

    with pytest.raises(IntegrityError) as refused:
        db.execute(text(sql), {"g": meals_pg["g"]})

    assert constraint in str(refused.value)
    db.rollback()


def test_meals_write_no_stock_movement_and_the_ledger_triggers_stand(client, db, meals_pg):
    before = db.query(StockMovement).count()
    source = closed_source(client, meals_pg)
    leftover_id = next(l["id"] for l in source["dishes"][0]["leftovers"] if l["classification"] == "RETAINED")
    lunch = client.post(MEALS, json=body(meals_pg)).json()
    client.post(f"{MEALS}/{lunch['id']}/carry", json={"leftover_id": leftover_id})

    db.expire_all()
    assert db.query(StockMovement).count() == before
    triggers = sorted(r[0] for r in db.execute(text(
        "SELECT tgname FROM pg_trigger WHERE tgrelid = 'stock_movements'::regclass AND NOT tgisinternal")))
    assert triggers == ["stock_movements_no_truncate", "stock_movements_no_update_delete"]
