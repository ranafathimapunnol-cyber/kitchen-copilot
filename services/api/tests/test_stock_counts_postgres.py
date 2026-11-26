"""
Stage 4 slice 4c on PostgreSQL (kitchen_copilot_test_db, shared
tests/conftest.py fixtures). Covers what SQLite cannot:
- several approvers deciding one adjustment at once: posted exactly once;
- an approval racing a rejection: exactly one wins;
- a negative adjustment racing a kitchen issue for the same stock: the
  balance never goes below zero at any point;
- a count saved while an issue is being confirmed: whichever order, an
  approval either reconciles the ledger to the counted quantity at the
  count time or is refused; it never produces a wrong balance;
- raises at once for one item: one PENDING (partial unique index);
- counts saved at once: distinct sequential numbers;
- the database rules on the real server, where the test role is a
  superuser: the counter cannot decide, the copied counter must be the real
  one, one PENDING per item, the difference check;
- the append-only ledger triggers still refuse changes, and an approval
  only inserts;
- no deadlock between numbering a document (count, issue) and a posting for
  the same item: the numbering lock does not block foreign-key checks.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import threading

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError

from app.core.clock import campus_today
from app.core.config import settings
from app.core.security import create_access_token
from app.models import Category, Item, MealSession, Menu, Unit
from app.models.purchases import StockMovement
from app.api.routes.kitchen import next_number
from app.models.stock import StockAdjustment, StockCount
from app.services import stock_ledger
from app.services.stock_ledger import as_utc

from tests.test_authorization import create_test_user
from tests.test_stock_ledger_postgres import engine_factory, parallel_clients, race  # noqa: F401 (fixtures)

COUNTS = "/api/stock-counts"
ADJUSTMENTS = "/api/stock-adjustments"
ISSUES = "/api/kitchen-issues"


def act_as(client, user):
    client.cookies.set(settings.ACCESS_COOKIE_NAME, create_access_token(user.id, user.password_hash))


@pytest.fixture
def counting(client, db, setup_data):
    """Rice with 10 kg opening stock dated 5 days ago; a Kitchen Manager who
    counts (the parallel clients act as the Admin, who approves)."""
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
    manager = create_test_user(db, campus_id, "KITCHEN_MANAGER")
    return {"campus_id": campus_id, "rice_id": rice.id, "lunch_id": lunch.id, "menu_id": menu.id,
            "admin": setup_data["user"], "manager": manager}


def count_body(k, qty):
    return {"reason": "Monthly stock check", "lines": [{"item_id": k["rice_id"], "quantity": qty}]}


def counted_and_raised(client, k, qty, counter=None):
    act_as(client, counter or k["manager"])
    count = client.post(COUNTS, json=count_body(k, qty))
    assert count.status_code == 201, count.text
    count = count.json()
    adjustment = client.post(f"{COUNTS}/{count['id']}/lines/{count['lines'][0]['id']}/adjustment",
                             json={"reason": "Count differs"})
    assert adjustment.status_code == 201, adjustment.text
    act_as(client, k["admin"])
    return count, adjustment.json()


def issue_draft(client, k, qty):
    response = client.post(ISSUES, json={
        "issue_date": campus_today().isoformat(), "meal_session_id": k["lunch_id"], "menu_id": k["menu_id"],
        "lines": [{"item_id": k["rice_id"], "quantity": qty}]})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def rice_movements(db, k):
    db.expire_all()
    return stock_ledger.ledger_movements(db, k["campus_id"], k["rice_id"])


def assert_never_negative(movements):
    for _movement, after in stock_ledger.running_balances(movements):
        assert after >= 0, movements


def test_several_approvers_at_once_post_exactly_once(client, db, counting, parallel_clients):
    _count, adjustment = counted_and_raised(client, counting, "8")

    statuses = race(parallel_clients, [lambda c: c.post(f"{ADJUSTMENTS}/{adjustment['id']}/approve", json={})] * 4)

    assert statuses.count(200) == 1 and statuses.count(409) == 3, statuses
    movements = rice_movements(db, counting)
    assert [m.movement_type for m in movements].count("ADJUSTMENT") == 1
    assert stock_ledger.item_balance(db, counting["campus_id"], counting["rice_id"]) == Decimal("8")


def test_approval_racing_a_rejection_exactly_one_wins(client, db, counting, parallel_clients):
    _count, adjustment = counted_and_raised(client, counting, "8")

    statuses = race(parallel_clients, [
        lambda c: c.post(f"{ADJUSTMENTS}/{adjustment['id']}/approve", json={}),
        lambda c: c.post(f"{ADJUSTMENTS}/{adjustment['id']}/reject", json={"reason": "Recount needed"}),
    ])

    assert statuses == [200, 409], statuses
    db.expire_all()
    final = db.get(StockAdjustment, adjustment["id"]).status
    posted = [m for m in rice_movements(db, counting) if m.movement_type == "ADJUSTMENT"]
    assert (final, len(posted)) in {("APPROVED", 1), ("REJECTED", 0)}


def test_negative_adjustment_racing_an_issue_never_goes_below_zero(client, db, counting, parallel_clients):
    _count, adjustment = counted_and_raised(client, counting, "4")  # 6 kg short at the count time
    issue_id = issue_draft(client, counting, "6")

    statuses = race(parallel_clients, [
        lambda c: c.post(f"{ADJUSTMENTS}/{adjustment['id']}/approve", json={}),
        lambda c: c.post(f"{ISSUES}/{issue_id}/confirm"),
    ])

    # Either order, the second posting would take the balance to -2 kg.
    assert statuses == [200, 409], statuses
    movements = rice_movements(db, counting)
    assert_never_negative(movements)
    assert stock_ledger.item_balance(db, counting["campus_id"], counting["rice_id"]) == Decimal("4")


def test_a_count_saved_while_an_issue_confirms_never_gives_a_wrong_balance(client, db, counting, parallel_clients):
    issue_id = issue_draft(client, counting, "3")

    statuses = race(parallel_clients, [
        lambda c: c.post(COUNTS, json=count_body(counting, "9")),
        lambda c: c.post(f"{ISSUES}/{issue_id}/confirm"),
    ])
    assert statuses == [200, 201], statuses

    db.expire_all()
    count = db.query(StockCount).one()
    line_id = db.execute(text("SELECT id FROM stock_count_items WHERE count_id = :c"), {"c": count.id}).scalar()
    act_as(client, counting["manager"])  # the Admin counted (parallel clients); the manager decides
    raised = client.post(f"{COUNTS}/{count.id}/lines/{line_id}/adjustment", json={"reason": "Count differs"})
    if raised.status_code == 201:
        decided = client.post(f"{ADJUSTMENTS}/{raised.json()['id']}/approve", json={})
    else:
        decided = raised
    movements = rice_movements(db, counting)
    if decided.status_code == 200:
        # The ledger at the count time now holds exactly the counted 9 kg,
        # and today's balance is that count plus everything after it.
        assert stock_ledger.balance_at(movements, count.counted_at) == Decimal("9")
        after = sum((stock_ledger.signed_quantity(m.direction, m.quantity) for m in movements
                     if as_utc(m.effective_at) > as_utc(count.counted_at)), Decimal("0"))
        assert stock_ledger.item_balance(db, counting["campus_id"], counting["rice_id"]) == Decimal("9") + after
    else:
        assert decided.status_code == 409 and "has changed since the count was saved" in decided.json()["detail"]
        assert not [m for m in movements if m.movement_type == "ADJUSTMENT"]
        assert stock_ledger.item_balance(db, counting["campus_id"], counting["rice_id"]) == Decimal("7")
    assert_never_negative(movements)


def test_raises_at_once_leave_one_pending_adjustment_per_item(client, db, counting, parallel_clients):
    act_as(client, counting["manager"])
    lines = []
    for _ in range(4):
        count = client.post(COUNTS, json=count_body(counting, "8")).json()
        lines.append((count["id"], count["lines"][0]["id"]))
    act_as(client, counting["admin"])

    statuses = race(parallel_clients, [
        (lambda c, ids=ids: c.post(f"{COUNTS}/{ids[0]}/lines/{ids[1]}/adjustment", json={"reason": "Count differs"}))
        for ids in lines
    ])

    assert statuses.count(201) == 1 and statuses.count(409) == 3, statuses
    db.expire_all()
    assert db.query(StockAdjustment).filter_by(status="PENDING").count() == 1


def test_counts_saved_at_once_take_distinct_sequential_numbers(db, counting, parallel_clients):
    statuses = race(parallel_clients, [lambda c: c.post(COUNTS, json=count_body(counting, "10"))] * 4)

    assert statuses == [201] * 4
    db.expire_all()
    assert sorted(n for (n,) in db.query(StockCount.count_number)) == ["SC-00001", "SC-00002", "SC-00003", "SC-00004"]


def test_postgresql_refuses_a_decision_by_the_counter_even_for_a_superuser(client, db, counting):
    _count, adjustment = counted_and_raised(client, counting, "8")
    assert db.execute(text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")).scalar() is True

    with pytest.raises(IntegrityError) as refused:
        db.execute(text(
            "UPDATE stock_adjustments SET status = 'APPROVED', decided_by = counted_by, decided_at = now() "
            "WHERE id = :id"), {"id": adjustment["id"]})
    assert "ck_stock_adjustment_independent_approver" in str(refused.value)
    db.rollback()

    with pytest.raises(IntegrityError) as forged:
        db.execute(text("UPDATE stock_adjustments SET counted_by = :admin WHERE id = :id"),
                   {"admin": counting["admin"].id, "id": adjustment["id"]})
    assert "fk_stock_adjustment_counter" in str(forged.value)
    db.rollback()


def test_postgresql_allows_one_pending_adjustment_per_item(client, db, counting):
    count, _adjustment = counted_and_raised(client, counting, "8")
    act_as(client, counting["manager"])
    second = client.post(COUNTS, json=count_body(counting, "8")).json()

    with pytest.raises(IntegrityError) as refused:
        db.execute(text(
            "INSERT INTO stock_adjustments (campus_id, count_id, count_item_id, item_id, counted_by, reason, status, "
            "raised_by, raised_at) VALUES (:campus, :count, :line, :item, :counter, 'second', 'PENDING', :counter, now())"),
            {"campus": counting["campus_id"], "count": second["id"], "line": second["lines"][0]["id"],
             "item": counting["rice_id"], "counter": counting["manager"].id})
    assert "uq_stock_adjustment_pending_item" in str(refused.value)
    db.rollback()


def test_postgresql_keeps_the_stored_difference_consistent(client, db, counting):
    act_as(client, counting["manager"])
    count = client.post(COUNTS, json=count_body(counting, "8")).json()

    with pytest.raises(IntegrityError) as refused:
        db.execute(text("INSERT INTO stock_count_items (campus_id, count_id, item_id, quantity, unit_id, "
                        "conversion_factor, standard_quantity, standard_unit_id, system_balance, difference) "
                        "SELECT campus_id, count_id, item_id, 1, unit_id, 1, 1, standard_unit_id, 5, 0 "
                        "FROM stock_count_items WHERE count_id = :c"), {"c": count["id"]})
    assert "ck_stock_count_item_difference" in str(refused.value) or "uq_stock_count_item" in str(refused.value)
    db.rollback()


def test_the_ledger_stays_append_only_and_an_approval_only_inserts(client, db, counting):
    triggers = sorted(name for (name,) in db.execute(text(
        "SELECT tgname FROM pg_trigger WHERE tgrelid = 'stock_movements'::regclass AND NOT tgisinternal")))
    assert triggers == ["stock_movements_no_truncate", "stock_movements_no_update_delete"]
    count, adjustment = counted_and_raised(client, counting, "8")
    before = {m.id: (m.quantity, m.effective_at, m.created_at) for m in rice_movements(db, counting)}

    assert client.post(f"{ADJUSTMENTS}/{adjustment['id']}/approve", json={}).status_code == 200

    after = rice_movements(db, counting)
    assert {m.id: (m.quantity, m.effective_at, m.created_at) for m in after if m.id in before} == before
    (posted,) = [m for m in after if m.id not in before]
    assert posted.movement_type == "ADJUSTMENT"
    assert as_utc(posted.effective_at) == datetime.fromisoformat(count["counted_at"]).astimezone(timezone.utc)
    with pytest.raises(DBAPIError) as refused:
        db.execute(text("UPDATE stock_movements SET quantity = 1 WHERE id = :id"), {"id": posted.id})
    assert "append-only" in str(refused.value)
    db.rollback()


def test_a_backdated_issue_after_the_count_blocks_approval_on_postgresql(client, db, counting):
    _count, adjustment = counted_and_raised(client, counting, "8")
    late = client.post(ISSUES, json={
        "issue_date": (campus_today() - timedelta(days=1)).isoformat(), "meal_session_id": counting["lunch_id"],
        "menu_id": counting["menu_id"], "lines": [{"item_id": counting["rice_id"], "quantity": "1"}]}).json()
    assert client.post(f"{ISSUES}/{late['id']}/confirm").status_code == 200

    refused = client.post(f"{ADJUSTMENTS}/{adjustment['id']}/approve", json={})

    assert refused.status_code == 409 and "has changed since the count was saved" in refused.json()["detail"]
    assert not [m for m in rice_movements(db, counting) if m.movement_type == "ADJUSTMENT"]
    assert stock_ledger.item_balance(db, counting["campus_id"], counting["rice_id"]) == Decimal("9")


def race_all(clients, calls):
    """Like race(), but a request that raises (a deadlock, for one) is
    reported by its exception name instead of breaking the comparison."""
    barrier = threading.Barrier(len(calls))
    outcomes = [None] * len(calls)

    def worker(index):
        barrier.wait()
        try:
            outcomes[index] = calls[index](clients[index]).status_code
        except Exception as error:  # noqa: BLE001 - reported to the assertion
            outcomes[index] = type(error).__name__

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(len(calls))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return outcomes


def test_the_numbering_lock_does_not_block_foreign_key_checks(db, counting, engine_factory):
    """While a document number is being taken, an insert referencing the
    campus (its foreign key takes FOR KEY SHARE) does not wait; a second
    numbering lock does, so numbers stay unique."""
    holder, other = engine_factory(), engine_factory()
    try:
        next_number(holder, counting["campus_id"], StockCount, StockCount.count_seq, "SC")
        other.execute(text("SET LOCAL lock_timeout = '2s'"))
        other.execute(text("SELECT id FROM campuses WHERE id = :c FOR KEY SHARE"), {"c": counting["campus_id"]})
        other.rollback()
        with pytest.raises(OperationalError) as waited:
            other.execute(text("SELECT id FROM campuses WHERE id = :c FOR NO KEY UPDATE NOWAIT"),
                          {"c": counting["campus_id"]})
        assert "could not obtain lock" in str(waited.value)
    finally:
        holder.rollback()
        other.rollback()
        holder.close()
        other.close()


def test_numbering_and_posting_for_one_item_at_once_never_deadlock(client, db, counting, parallel_clients):
    """Each round races a count of Rice, the confirmation of a Rice issue and
    a new Rice draft. Before the numbering lock became FOR NO KEY UPDATE this
    deadlocked intermittently (found by the slice 4c race tests)."""
    draft = {"issue_date": campus_today().isoformat(), "meal_session_id": counting["lunch_id"],
             "menu_id": counting["menu_id"], "lines": [{"item_id": counting["rice_id"], "quantity": "0.5"}]}
    for round_number in range(8):
        issue_id = issue_draft(client, counting, "0.5")
        outcomes = race_all(parallel_clients, [
            lambda c: c.post(COUNTS, json=count_body(counting, "5")),
            lambda c: c.post(f"{ISSUES}/{issue_id}/confirm"),
            lambda c: c.post(ISSUES, json=draft),
        ])
        assert outcomes == [201, 200, 201], (round_number, outcomes)
    assert_never_negative(rice_movements(db, counting))
    assert stock_ledger.item_balance(db, counting["campus_id"], counting["rice_id"]) == Decimal("6")
