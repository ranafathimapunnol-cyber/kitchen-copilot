"""
Stage 4 slice 4a: the stock ledger, opening stock, balances, low stock and
the replenishment list (STK01; STK04 criteria 1-3), with the decisions of
23 November 2026 (docs/STAGE-4-STOCK-PLAN.md):

- S1: balances, replenishment list and item ledger need inventory.read;
  opening stock and its reversal are ADMIN and KITCHEN_MANAGER only, never
  STAFF, whatever codes a STAFF user holds.
- S2: no posting may take a balance below zero at any point in the item's
  history; movements replay by effective time, then posting order, and a
  new posting goes after existing movements with the same effective time.
- S3: one active opening per item per campus (enforced by the database),
  dated today or earlier, corrected only by reversal and re-entry.
- S4 (as applied to openings): a reversal is effective at its posting time
  and never changes the original movement; history and audit rows stay.

Runs on in-memory SQLite with the shared fixtures of
test_operational_authority; tests/test_stock_ledger_postgres.py covers
locking, races and the database constraints on PostgreSQL.
"""

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.core.clock import campus_timezone, campus_today
from app.models import AuditLog, Category, Item, Unit, UnitConversion
from app.models.purchases import StockMovement
from app.models.stock import StockOpening
from app.services import stock_ledger
from app.services.stock_ledger import Posting, as_utc, start_of_campus_day

from tests.test_operational_authority import (  # noqa: F401 (fixtures)
    act_as,
    client,
    db,
    grant,
    world,
)
from tests.test_pur03_receipts import bill_lines, create_bill, draft

OPENINGS = "/api/stock/openings"
BALANCES = "/api/stock/balances"
REPLENISHMENT = "/api/stock/replenishment"


def ledger_url(item):
    return f"/api/stock/items/{item.id}/ledger"


def days_ago(n):
    return (campus_today() - timedelta(days=n)).isoformat()


@pytest.fixture
def stock(db, world):
    """Campus A: kg (standard), g and bag (25 kg) with conversions; Rice
    (minimum 50 kg), Dal (no minimum), Oil (minimum 5 kg); an inactive
    item; campus B keeps its own Rice."""
    a = world.a
    g = Unit(campus_id=a.campus.id, name="Gram", symbol="g", dimension="weight")
    bag = Unit(campus_id=a.campus.id, name="Bag", symbol="bag", dimension="weight")
    litre = Unit(campus_id=a.campus.id, name="Litre", symbol="L", dimension="volume")
    pulses = Category(campus_id=a.campus.id, name="Pulses")
    db.add_all([g, bag, litre, pulses])
    db.flush()
    db.add_all([
        UnitConversion(campus_id=a.campus.id, from_unit_id=g.id, to_unit_id=a.kg.id,
                       factor=Decimal("0.001")),
        UnitConversion(campus_id=a.campus.id, from_unit_id=bag.id, to_unit_id=a.kg.id,
                       factor=Decimal("25")),
    ])
    a.item.minimum_stock = Decimal("50")
    dal = Item(campus_id=a.campus.id, name="Toor Dal", category_id=pulses.id,
               standard_unit_id=a.kg.id, minimum_stock=0)
    oil = Item(campus_id=a.campus.id, name="Oil", category_id=a.category.id,
               standard_unit_id=a.kg.id, minimum_stock=Decimal("5"))
    old = Item(campus_id=a.campus.id, name="Old Millet", category_id=a.category.id,
               standard_unit_id=a.kg.id, minimum_stock=Decimal("3"), is_active=False)
    db.add_all([dal, oil, old])
    db.commit()
    a.g, a.bag, a.litre, a.pulses, a.dal, a.oil, a.old = g, bag, litre, pulses, dal, oil, old
    return world


def record_opening(client, lines, effective_date=None, **extra):
    return client.post(OPENINGS, json={
        "effective_date": effective_date or days_ago(10),
        "lines": lines,
        **extra,
    })


def line(item, qty, unit=None, **extra):
    body = {"item_id": item.id, "quantity": qty, **extra}
    if unit is not None:
        body["unit_id"] = unit.id
    return body


def receive(client, place, item, qty, invoice):
    """A bill, a draft receipt and its acceptance: stock in via PUR03."""
    bill = create_bill(client, place, invoice, [(item, qty)])
    line_id = bill_lines(client, bill["id"])[0]["purchase_item_id"]
    receipt = draft(client, bill["id"], [(line_id, qty, qty, "0")]).json()
    accepted = client.post(f"/api/receipts/{receipt['id']}/accept")
    assert accepted.status_code == 200, accepted.text
    return accepted.json()


def raw_movement(db, place, item, movement_type, direction, qty, effective_at, key):
    """A movement written directly: stands in for later slices (kitchen
    issues) so the history checks can be exercised now."""
    movement = StockMovement(
        campus_id=place.campus.id, item_id=item.id, movement_type=movement_type,
        direction=direction, quantity=Decimal(qty), unit_id=item.standard_unit_id,
        effective_at=effective_at, source_key=key, reference_type="TEST",
        reference_id=1, created_by=place.admin.id,
    )
    db.add(movement)
    db.commit()
    return movement


def balance_of(client, item):
    return client.get(ledger_url(item)).json()["item"]["balance"]


def snapshot(movement):
    return (movement.id, movement.movement_type, movement.direction, movement.quantity,
            as_utc(movement.effective_at), as_utc(movement.created_at), movement.source_key,
            movement.reversal_of_id, movement.remarks)


# ============================================================
# STK01: OPENING STOCK CREATES A SEPARATE OPENING MOVEMENT
# ============================================================

def test_admin_records_opening_stock_as_separate_opening_movements(client, db, stock):
    a = stock.a
    act_as(client, a.admin)
    date_text = days_ago(30)

    response = record_opening(client, [line(a.item, "40"), line(a.dal, "12.5")], date_text)

    assert response.status_code == 201, response.text
    created = response.json()["items"]
    assert [o["item_name"] for o in created] == ["Rice", "Toor Dal"]
    assert all(o["status"] == "ACTIVE" and o["effective_date"] == date_text for o in created)

    movements = db.query(StockMovement).filter_by(campus_id=a.campus.id).order_by(StockMovement.id).all()
    assert [(m.movement_type, m.direction, m.quantity, m.source_key, m.reference_type) for m in movements] == [
        ("OPENING", 1, Decimal("40.000"), f"OPENING:{created[0]['id']}", "STOCK_OPENING"),
        ("OPENING", 1, Decimal("12.500"), f"OPENING:{created[1]['id']}", "STOCK_OPENING"),
    ]
    # Effective at 00:00 campus time on the effective date; posted now.
    local = as_utc(movements[0].effective_at).astimezone(campus_timezone())
    assert (local.date().isoformat(), local.time()) == (date_text, time(0, 0))
    assert as_utc(movements[0].created_at) > as_utc(movements[0].effective_at)
    assert balance_of(client, a.item) == "40.000"

    audits = db.query(AuditLog).filter_by(entity_type="STOCK_OPENING", action="CREATE").all()
    assert sorted(x.entity_id for x in audits) == sorted(o["id"] for o in created)
    assert audits[0].details["movement_id"] in {m.id for m in movements}


def test_kitchen_manager_records_opening_stock(client, stock):
    act_as(client, stock.a.manager)
    assert record_opening(client, [line(stock.a.item, "5")]).status_code == 201


def test_opening_entered_in_another_unit_is_converted_and_keeps_its_factor(client, db, stock):
    a = stock.a
    act_as(client, a.admin)

    created = record_opening(client, [line(a.item, "2", a.bag), line(a.dal, "1500", a.g)]).json()["items"]

    assert [(o["quantity"], o["unit_symbol"], o["conversion_factor"], o["standard_quantity"],
             o["standard_unit_symbol"]) for o in created] == [
        ("2.000", "bag", "25", "50.000", "kg"),
        ("1500.000", "g", "0.001", "1.500", "kg"),
    ]
    assert balance_of(client, a.item) == "50.000"
    # A later change to the conversion cannot alter what was recorded.
    stored = db.query(StockOpening).filter_by(id=created[0]["id"]).one()
    assert stored.conversion_factor == Decimal("25") and stored.standard_quantity == Decimal("50.000")


@pytest.mark.parametrize("body, status, message", [
    ("future", 422, "future"),
    ("zero", 422, None),
    ("negative", 422, None),
    ("four_decimals", 422, None),
    ("duplicate_item", 422, "only once"),
    ("no_conversion", 422, "explicit unit conversion"),
    ("inactive_item", 422, "inactive"),
    ("other_campus_item", 404, None),
    ("no_lines", 422, None),
])
def test_invalid_opening_stock_is_refused_and_posts_nothing(client, db, stock, body, status, message):
    a, b = stock.a, stock.b
    act_as(client, a.admin)
    tomorrow = (campus_today() + timedelta(days=1)).isoformat()
    bodies = {
        "future": ([line(a.item, "1")], tomorrow),
        "zero": ([line(a.item, "0")], None),
        "negative": ([line(a.item, "-1")], None),
        "four_decimals": ([line(a.item, "1.0005")], None),
        "duplicate_item": ([line(a.item, "1"), line(a.item, "2")], None),
        "no_conversion": ([line(a.item, "1", a.litre)], None),
        "inactive_item": ([line(a.old, "1")], None),
        "other_campus_item": ([line(b.item, "1")], None),
        "no_lines": ([], None),
    }
    lines, when = bodies[body]

    response = record_opening(client, lines, when)

    assert response.status_code == status, response.text
    if message:
        assert message in response.json()["detail"]
    assert db.query(StockMovement).count() == 0
    assert db.query(StockOpening).count() == 0


def test_a_batch_is_all_or_nothing(client, db, stock):
    a = stock.a
    act_as(client, a.admin)

    response = record_opening(client, [line(a.item, "10"), line(a.dal, "1", a.litre)])

    assert response.status_code == 422
    assert db.query(StockOpening).count() == 0 and db.query(StockMovement).count() == 0


# ============================================================
# S3: ONE ACTIVE OPENING PER ITEM PER CAMPUS
# ============================================================

def test_a_second_opening_for_the_same_item_is_refused(client, db, stock):
    a = stock.a
    act_as(client, a.admin)
    first = record_opening(client, [line(a.item, "10")]).json()["items"][0]

    again = record_opening(client, [line(a.dal, "3"), line(a.item, "20")])

    assert again.status_code == 409
    assert f"entry #{first['id']}" in again.json()["detail"]
    assert db.query(StockOpening).count() == 1
    assert balance_of(client, a.item) == "10.000"


def test_the_database_allows_only_one_active_opening_per_item(db, stock):
    a = stock.a

    def opening(status="ACTIVE", **extra):
        return StockOpening(
            campus_id=a.campus.id, item_id=a.item.id, quantity=Decimal("1"), unit_id=a.kg.id,
            conversion_factor=Decimal("1"), standard_quantity=Decimal("1"),
            standard_unit_id=a.kg.id, effective_date=campus_today(), status=status,
            created_by=a.admin.id, **extra,
        )

    reversed_fields = dict(reversed_by=a.admin.id, reversed_at=datetime.now(timezone.utc),
                           reversal_reason="history")
    db.add_all([opening("REVERSED", **reversed_fields), opening("REVERSED", **reversed_fields), opening()])
    db.commit()

    db.add(opening())
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    # The opening's reversal fields must be complete together.
    db.add(opening("REVERSED"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_another_campus_keeps_its_own_opening(client, stock):
    act_as(client, stock.a.admin)
    assert record_opening(client, [line(stock.a.item, "10")]).status_code == 201
    act_as(client, stock.b.admin)
    assert record_opening(client, [line(stock.b.item, "4")]).status_code == 201
    assert balance_of(client, stock.b.item) == "4.000"


# ============================================================
# REVERSING AN OPENING: POSTING DATE, ORIGINAL UNCHANGED, HISTORY KEPT
# ============================================================

def test_reversing_an_opening_posts_a_linked_reversal_at_the_posting_time(client, db, stock):
    a = stock.a
    act_as(client, a.admin)
    opening = record_opening(client, [line(a.item, "40")], days_ago(20)).json()["items"][0]
    original = db.query(StockMovement).filter_by(source_key=f"OPENING:{opening['id']}").one()
    before = snapshot(original)

    started = datetime.now(timezone.utc)
    response = client.post(f"{OPENINGS}/{opening['id']}/reverse", json={"reason": "Counted the wrong store"})
    finished = datetime.now(timezone.utc)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["reversal_reason"], body["reversed_by_name"]) == (
        "REVERSED", "Counted the wrong store", a.admin.full_name)

    db.expire_all()
    reversal = db.query(StockMovement).filter_by(source_key=f"REVERSAL:{original.id}").one()
    assert (reversal.movement_type, reversal.direction, reversal.quantity, reversal.reversal_of_id,
            reversal.reference_type, reversal.reference_id) == (
        "REVERSAL", -1, Decimal("40.000"), original.id, "STOCK_OPENING", opening["id"])
    # Effective at the actual posting time, not the opening's date...
    assert started - timedelta(seconds=1) <= as_utc(reversal.effective_at) <= finished + timedelta(seconds=1)
    # ...and the original keeps its own transaction date, untouched.
    assert snapshot(db.query(StockMovement).filter_by(id=original.id).one()) == before
    assert body["movement_id"] == original.id and body["reversal_movement_id"] == reversal.id
    assert balance_of(client, a.item) == "0.000"

    audit = {(x.action, x.entity_id) for x in db.query(AuditLog).filter_by(entity_type="STOCK_OPENING")}
    assert audit == {("CREATE", opening["id"]), ("REVERSE", opening["id"])}


def test_after_a_reversal_a_new_opening_can_be_entered_and_history_stays(client, db, stock):
    a = stock.a
    act_as(client, a.admin)
    first = record_opening(client, [line(a.item, "40")]).json()["items"][0]
    client.post(f"{OPENINGS}/{first['id']}/reverse", json={"reason": "Wrong quantity"})

    second = record_opening(client, [line(a.item, "45")])

    assert second.status_code == 201, second.text
    assert balance_of(client, a.item) == "45.000"
    listed = client.get(OPENINGS).json()
    assert listed["status_counts"] == {"ACTIVE": 1, "REVERSED": 1}
    assert [o["status"] for o in listed["items"]] == ["ACTIVE", "REVERSED"]
    assert listed["items_with_active_opening"] == [a.item.id]
    assert db.query(StockMovement).filter_by(item_id=a.item.id).count() == 3


@pytest.mark.parametrize("reason", ["", "  ", "ab"])
def test_a_reversal_needs_a_reason(client, db, stock, reason):
    act_as(client, stock.a.admin)
    opening = record_opening(client, [line(stock.a.item, "4")]).json()["items"][0]

    response = client.post(f"{OPENINGS}/{opening['id']}/reverse", json={"reason": reason})

    assert response.status_code == 422
    assert db.query(StockMovement).filter_by(movement_type="REVERSAL").count() == 0


def test_an_opening_is_reversed_only_once(client, db, stock):
    act_as(client, stock.a.admin)
    opening = record_opening(client, [line(stock.a.item, "4")]).json()["items"][0]
    path = f"{OPENINGS}/{opening['id']}/reverse"

    assert client.post(path, json={"reason": "first"}).status_code == 200
    again = client.post(path, json={"reason": "second"})

    assert again.status_code == 409
    assert db.query(StockMovement).filter_by(movement_type="REVERSAL").count() == 1


def test_kitchen_manager_reverses_and_another_campus_cannot(client, db, stock):
    act_as(client, stock.a.admin)
    opening = record_opening(client, [line(stock.a.item, "4")]).json()["items"][0]
    path = f"{OPENINGS}/{opening['id']}/reverse"

    act_as(client, stock.b.admin)
    assert client.post(path, json={"reason": "not mine"}).status_code == 404
    act_as(client, stock.a.manager)
    assert client.post(path, json={"reason": "manager fix"}).status_code == 200


def test_a_reversal_that_would_leave_stock_below_zero_is_refused(client, db, stock):
    """Opening 10 kg; 8 kg later left the store (a kitchen issue, slice
    4b, written directly here). Reversing the opening would leave -8 kg."""
    a = stock.a
    act_as(client, a.admin)
    opening = record_opening(client, [line(a.item, "10")], days_ago(5)).json()["items"][0]
    raw_movement(db, a, a.item, "ISSUE", -1, "8", datetime.now(timezone.utc) - timedelta(days=1), "TEST-ISSUE:1")

    response = client.post(f"{OPENINGS}/{opening['id']}/reverse", json={"reason": "wrong"})

    assert response.status_code == 409
    assert "Not enough Rice" in response.json()["detail"] and "-8.000 kg" in response.json()["detail"]
    db.expire_all()
    assert db.query(StockOpening).filter_by(id=opening["id"]).one().status == "ACTIVE"
    assert db.query(StockMovement).filter_by(movement_type="REVERSAL").count() == 0
    assert db.query(AuditLog).filter_by(action="REVERSE").count() == 0


# ============================================================
# S2: THE HISTORICAL NO-NEGATIVE CHECK (service level, backdated postings)
# ============================================================

@pytest.fixture
def history(db, stock):
    """Rice: +10 at T1, -8 at T2, +20 at T3 (balances 10, 2, 22)."""
    a = stock.a
    t0 = datetime(2026, 11, 1, 6, 0, tzinfo=timezone.utc)
    raw_movement(db, a, a.item, "RECEIPT", 1, "10", t0 + timedelta(days=1), "T:1")
    raw_movement(db, a, a.item, "ISSUE", -1, "8", t0 + timedelta(days=2), "T:2")
    raw_movement(db, a, a.item, "RECEIPT", 1, "20", t0 + timedelta(days=3), "T:3")
    return t0


def outflow(place, item, qty, when, key, movement_type="ADJUSTMENT"):
    return Posting(item_id=item.id, movement_type=movement_type, direction=-1,
                   quantity=Decimal(qty), unit_id=item.standard_unit_id, effective_at=when,
                   source_key=key, reference_type="TEST", reference_id=1)


def inflow(place, item, qty, when, key):
    return Posting(item_id=item.id, movement_type="ADJUSTMENT", direction=1,
                   quantity=Decimal(qty), unit_id=item.standard_unit_id, effective_at=when,
                   source_key=key, reference_type="TEST", reference_id=1)


def test_backdated_outflow_refused_when_an_earlier_point_goes_negative(db, stock, history):
    """Today's balance would be 17, but between T1.5 and T3 it would be -3:
    the 8 kg issued at T2 could not have left a store holding 5 kg."""
    a = stock.a
    count = db.query(StockMovement).count()

    with pytest.raises(HTTPException) as refused:
        stock_ledger.post(db, a.admin, [outflow(a, a.item, "5", history + timedelta(days=1, hours=12), "N:1")])

    assert refused.value.status_code == 409
    assert "-3.000 kg" in refused.value.detail
    assert db.query(StockMovement).count() == count


def test_backdated_outflow_accepted_when_every_point_stays_at_or_above_zero(db, stock, history):
    a = stock.a

    (posted,) = stock_ledger.post(db, a.admin, [outflow(a, a.item, "2", history + timedelta(days=1, hours=12), "N:1")])
    db.commit()

    replayed = stock_ledger.running_balances(stock_ledger.ledger_movements(db, a.campus.id, a.item.id))
    assert [b for _m, b in replayed] == [Decimal("10"), Decimal("8"), Decimal("0"), Decimal("20")]
    assert replayed[1][0].id == posted.id


def test_an_outflow_now_is_judged_on_the_current_balance(db, stock, history):
    a = stock.a
    now = datetime.now(timezone.utc)
    with pytest.raises(HTTPException):
        stock_ledger.post(db, a.admin, [outflow(a, a.item, "22.001", now, "N:1")])
    stock_ledger.post(db, a.admin, [outflow(a, a.item, "22", now, "N:2")])
    db.commit()
    assert stock_ledger.item_balance(db, a.campus.id, a.item.id) == Decimal("0")


def test_same_effective_time_new_posting_goes_after_existing_movements(db, stock):
    """A receipt of 5 kg and an outflow of 5 kg at the same instant: the
    new posting is placed after the existing movement, so it is allowed;
    replaying it first would have shown -5."""
    a = stock.a
    moment = datetime(2026, 11, 10, 4, 30, tzinfo=timezone.utc)
    existing = raw_movement(db, a, a.item, "RECEIPT", 1, "5", moment, "T:same")

    (posted,) = stock_ledger.post(db, a.admin, [outflow(a, a.item, "5", moment, "N:same")])
    db.commit()

    ordered = stock_ledger.ledger_movements(db, a.campus.id, a.item.id)
    assert [m.id for m in ordered] == [existing.id, posted.id]
    assert [b for _m, b in stock_ledger.running_balances(ordered)] == [Decimal("5"), Decimal("0")]


def test_same_effective_time_existing_outflow_is_not_rescued_by_a_new_inflow(db, stock):
    """The mirror case: an existing outflow at T and a new outflow at T,
    with only one inflow at T placed before both. Deterministic order gives
    5, 0, -1: refused."""
    a = stock.a
    moment = datetime(2026, 11, 10, 4, 30, tzinfo=timezone.utc)
    raw_movement(db, a, a.item, "RECEIPT", 1, "5", moment, "T:in")
    raw_movement(db, a, a.item, "ISSUE", -1, "5", moment, "T:out")

    with pytest.raises(HTTPException) as refused:
        stock_ledger.post(db, a.admin, [outflow(a, a.item, "1", moment, "N:1")])
    assert "-1.000 kg" in refused.value.detail


def test_postings_in_one_call_are_replayed_in_the_order_given(db, stock):
    a = stock.a
    moment = datetime(2026, 11, 10, 4, 30, tzinfo=timezone.utc)

    with pytest.raises(HTTPException):
        stock_ledger.post(db, a.admin, [outflow(a, a.item, "3", moment, "N:1"), inflow(a, a.item, "3", moment, "N:2")])
    stock_ledger.post(db, a.admin, [inflow(a, a.item, "3", moment, "N:3"), outflow(a, a.item, "3", moment, "N:4")])
    db.commit()
    assert stock_ledger.item_balance(db, a.campus.id, a.item.id) == Decimal("0")


def test_a_backdated_inflow_is_never_refused(db, stock, history):
    a = stock.a
    stock_ledger.post(db, a.admin, [inflow(a, a.item, "1", history - timedelta(days=30), "N:1")])
    db.commit()
    assert stock_ledger.item_balance(db, a.campus.id, a.item.id) == Decimal("23")


def test_points_before_the_new_posting_are_not_judged_by_it(db, stock):
    """History written directly with a dip below zero (only possible
    outside the API): a later outflow that keeps every point from its own
    time onwards at or above zero is not blamed for the earlier dip."""
    a = stock.a
    t = datetime(2026, 11, 1, tzinfo=timezone.utc)
    raw_movement(db, a, a.item, "ISSUE", -1, "2", t, "T:dip")
    raw_movement(db, a, a.item, "RECEIPT", 1, "10", t + timedelta(days=1), "T:in")

    stock_ledger.post(db, a.admin, [outflow(a, a.item, "8", t + timedelta(days=2), "N:1")])
    db.commit()
    assert stock_ledger.item_balance(db, a.campus.id, a.item.id) == Decimal("0")


def test_each_item_is_checked_on_its_own_history(db, stock, history):
    a = stock.a
    with pytest.raises(HTTPException) as refused:
        stock_ledger.post(db, a.admin, [
            outflow(a, a.item, "1", datetime.now(timezone.utc), "N:1"),
            outflow(a, a.dal, "1", datetime.now(timezone.utc), "N:2"),
        ])
    assert "Toor Dal" in refused.value.detail


# ============================================================
# DATABASE RULES ON THE LEDGER
# ============================================================

@pytest.mark.parametrize("movement_type, direction, reversal_of", [
    ("OPENING", -1, None),
    ("RECEIPT", -1, None),
    ("ISSUE", 1, None),
    ("REVERSAL", -1, None),      # a reversal must point at its original
    ("ADJUSTMENT", 1, "self"),   # only a reversal may point at another row
    ("ADJUSTMENT", 2, None),
    ("TRANSFER", 1, None),       # not a ledger movement type
])
def test_the_database_refuses_inconsistent_movements(db, stock, movement_type, direction, reversal_of):
    a = stock.a
    anchor = raw_movement(db, a, a.item, "RECEIPT", 1, "1", datetime.now(timezone.utc), "T:anchor")
    db.add(StockMovement(
        campus_id=a.campus.id, item_id=a.item.id, movement_type=movement_type, direction=direction,
        quantity=Decimal("1"), unit_id=a.kg.id, effective_at=datetime.now(timezone.utc),
        source_key="T:bad", reference_type="TEST", reference_id=1, created_by=a.admin.id,
        reversal_of_id=anchor.id if reversal_of else None,
    ))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_the_database_refuses_a_second_posting_of_one_source_or_one_reversal(db, stock):
    a = stock.a
    now = datetime.now(timezone.utc)
    original = raw_movement(db, a, a.item, "RECEIPT", 1, "5", now, "T:source")
    with pytest.raises(IntegrityError):
        raw_movement(db, a, a.item, "RECEIPT", 1, "5", now, "T:source")
    db.rollback()

    raw = dict(campus_id=a.campus.id, item_id=a.item.id, movement_type="REVERSAL", direction=-1,
               quantity=Decimal("5"), unit_id=a.kg.id, effective_at=now, reference_type="TEST",
               reference_id=1, created_by=a.admin.id, reversal_of_id=original.id)
    db.add(StockMovement(source_key="T:rev1", **raw))
    db.commit()
    db.add(StockMovement(source_key="T:rev2", **raw))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


# ============================================================
# RECEIPTS (PUR03) NOW FILL THE LEDGER COLUMNS
# ============================================================

def test_accepted_receipts_post_inflows_effective_at_acceptance(client, db, stock):
    a = stock.a
    act_as(client, a.admin)

    receipt = receive(client, a, a.dal, "6", "STK-R1")

    movement = db.query(StockMovement).filter_by(reference_id=receipt["id"], reference_type="GOODS_RECEIPT").one()
    line_id = receipt["items"][0]["id"]
    assert (movement.movement_type, movement.direction, movement.source_key) == ("RECEIPT", 1, f"RECEIPT_ITEM:{line_id}")
    assert as_utc(movement.effective_at).isoformat() == receipt["accepted_at"]
    assert balance_of(client, a.dal) == "6.000"


# ============================================================
# ITEM LEDGER: EVERY BALANCE EXPLAINED
# ============================================================

def test_item_ledger_replays_by_effective_time_with_running_balances(client, db, stock):
    """A receipt accepted today, then opening stock backdated 30 days: the
    opening comes first in the ledger although it was posted later."""
    a = stock.a
    act_as(client, a.admin)
    receive(client, a, a.item, "10", "STK-L1")
    opening = record_opening(client, [line(a.item, "40")], days_ago(30)).json()["items"][0]
    client.post(f"{OPENINGS}/{opening['id']}/reverse", json={"reason": "Wrong store"})

    ledger = client.get(ledger_url(a.item)).json()

    assert ledger["item"]["balance"] == "10.000" and ledger["total"] == 3
    rows = list(reversed(ledger["movements"]))  # oldest first
    assert [(r["movement_type"], r["signed_quantity"], r["balance_after"]) for r in rows] == [
        ("OPENING", "40.000", "40.000"),
        ("RECEIPT", "10.000", "50.000"),
        ("REVERSAL", "-40.000", "10.000"),
    ]
    assert rows[0]["reversed_by_movement_id"] == rows[2]["id"]
    assert rows[2]["reversal_of_id"] == rows[0]["id"]
    assert rows[0]["opening_id"] == opening["id"] and rows[1]["receipt_id"] and rows[1]["invoice_number"] == "STK-L1"
    assert all(r["created_by_name"] == a.admin.full_name for r in rows)

    page = client.get(ledger_url(a.item), params={"page_size": 1, "page": 2}).json()
    assert page["total_pages"] == 3 and page["movements"][0]["movement_type"] == "RECEIPT"


def test_item_ledger_is_campus_scoped(client, stock):
    act_as(client, stock.b.admin)
    assert client.get(ledger_url(stock.a.item)).status_code == 404


# ============================================================
# STK04: BALANCES, BELOW MINIMUM, REPLENISHMENT LIST
# ============================================================

def test_balances_flag_items_below_their_minimum(client, db, stock):
    a = stock.a
    act_as(client, a.admin)
    record_opening(client, [line(a.item, "30"), line(a.oil, "5"), line(a.dal, "2")])
    raw_movement(db, a, a.old, "RECEIPT", 1, "1", datetime.now(timezone.utc), "T:old")

    body = client.get(BALANCES).json()
    rows = {r["item_name"]: r for r in body["items"]}

    # Inactive items appear only while they still hold stock.
    assert sorted(rows) == ["Oil", "Old Millet", "Rice", "Toor Dal"]
    assert (rows["Rice"]["balance"], rows["Rice"]["minimum_stock"], rows["Rice"]["below_minimum"],
            rows["Rice"]["shortfall"]) == ("30.000", "50.000", True, "20.000")
    assert (rows["Oil"]["below_minimum"], rows["Oil"]["shortfall"]) == (False, "0.000")  # at minimum
    assert (rows["Toor Dal"]["has_minimum"], rows["Toor Dal"]["below_minimum"]) == (False, False)
    assert rows["Old Millet"]["is_active"] is False and rows["Old Millet"]["below_minimum"] is True
    assert body["summary"] == {"items": 4, "below_minimum": 2, "zero_or_less": 0, "without_minimum": 1}

    below = client.get(BALANCES, params={"below_minimum": True}).json()
    assert sorted(r["item_name"] for r in below["items"]) == ["Old Millet", "Rice"]
    assert [r["item_name"] for r in client.get(BALANCES, params={"search": "dal"}).json()["items"]] == ["Toor Dal"]
    in_pulses = client.get(BALANCES, params={"category_id": a.pulses.id}).json()
    assert [r["item_name"] for r in in_pulses["items"]] == ["Toor Dal"]
    assert client.get(BALANCES, params={"search": "%"}).json()["total"] == 0


def test_items_with_no_movements_show_a_zero_balance(client, stock):
    act_as(client, stock.a.admin)
    rows = {r["item_name"]: r for r in client.get(BALANCES).json()["items"]}
    assert sorted(rows) == ["Oil", "Rice", "Toor Dal"]
    assert rows["Rice"]["balance"] == "0.000" and rows["Rice"]["below_minimum"] is True
    assert rows["Rice"]["last_movement_at"] is None


def test_replenishment_list_has_active_items_below_minimum_with_quantities_needed(client, db, stock):
    a = stock.a
    act_as(client, a.admin)
    record_opening(client, [line(a.item, "12.5"), line(a.oil, "6")])
    raw_movement(db, a, a.old, "RECEIPT", 1, "1", datetime.now(timezone.utc), "T:old")

    body = client.get(REPLENISHMENT).json()

    assert [(r["item_name"], r["balance"], r["minimum_stock"], r["shortfall"], r["unit_symbol"])
            for r in body["items"]] == [("Rice", "12.500", "50.000", "37.500", "kg")]
    assert body["total"] == 1 and body["campus_date"] == campus_today().isoformat()


def test_balances_are_campus_scoped(client, stock):
    act_as(client, stock.a.admin)
    record_opening(client, [line(stock.a.item, "7")])
    act_as(client, stock.b.admin)
    rows = client.get(BALANCES).json()["items"]
    assert [(r["item_name"], r["balance"]) for r in rows] == [("Rice", "0.000")]
    assert rows[0]["item_id"] == stock.b.item.id


# ============================================================
# S1: WHO MAY DO WHAT
# ============================================================

READS = [BALANCES, REPLENISHMENT, "LEDGER"]


@pytest.mark.parametrize("endpoint", READS)
def test_staff_reads_stock_only_with_inventory_read(client, db, stock, endpoint):
    a = stock.a
    url = ledger_url(a.item) if endpoint == "LEDGER" else endpoint
    act_as(client, a.staff)
    assert client.get(url).status_code == 403

    grant(db, a.staff, a.admin, "inventory.read")
    assert client.get(url).status_code == 200


def test_manager_reads_stock(client, stock):
    act_as(client, stock.a.manager)
    for url in (BALANCES, REPLENISHMENT, ledger_url(stock.a.item), OPENINGS):
        assert client.get(url).status_code == 200, url


def test_staff_never_records_lists_or_reverses_opening_stock_whatever_codes_they_hold(client, db, stock):
    a = stock.a
    act_as(client, a.admin)
    opening = record_opening(client, [line(a.item, "5")]).json()["items"][0]
    for code in ("inventory.create", "inventory.read", "inventory.update",
                 "consumption.create", "consumption.read", "consumption.update"):
        grant(db, a.staff, a.admin, code)

    act_as(client, a.staff)
    assert client.get(OPENINGS).status_code == 403
    assert record_opening(client, [line(a.dal, "1")]).status_code == 403
    assert client.post(f"{OPENINGS}/{opening['id']}/reverse", json={"reason": "staff try"}).status_code == 403
    assert client.get(BALANCES).status_code == 200  # inventory.read still works
    assert db.query(StockOpening).count() == 1
    assert db.query(StockMovement).filter_by(movement_type="REVERSAL").count() == 0


# ============================================================
# MOVEMENT LOG SHOWS DIRECTION, EFFECTIVE TIME AND REVERSAL LINKS
# ============================================================

def test_movement_log_shows_direction_effective_time_and_reversal_links(client, stock):
    a = stock.a
    act_as(client, a.admin)
    opening = record_opening(client, [line(a.item, "9")], days_ago(3)).json()["items"][0]
    client.post(f"{OPENINGS}/{opening['id']}/reverse", json={"reason": "Typed 9 for 6"})

    log = client.get("/api/stock-movements").json()["items"]

    reversal, original = log  # newest posting first
    assert (reversal["movement_type"], reversal["direction"], reversal["reversal_of_id"]) == ("REVERSAL", -1, original["id"])
    assert (original["movement_type"], original["direction"], original["reversed_by_movement_id"]) == (
        "OPENING", 1, reversal["id"])
    assert original["opening_id"] == opening["id"] and original["effective_at"] < original["created_at"]
    assert client.get("/api/stock-movements", params={"movement_type": "reversal"}).json()["total"] == 1
    legacy = client.get("/api/stock/movements").json()
    assert {m["direction"] for m in legacy} == {1, -1}
