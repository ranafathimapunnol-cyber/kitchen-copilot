"""
Stage 4 slice 4a on PostgreSQL (kitchen_copilot_test_db, shared
tests/conftest.py fixtures). Covers what SQLite cannot:
- simultaneous opening entries for one item: exactly one is recorded;
- simultaneous reversals of one opening: exactly one reversal is posted;
- two outflows racing for the same stock: the item-row lock makes the
  second see the first, so the balance never goes below zero;
- the partial unique index (one ACTIVE opening per item per campus) and the
  ledger check constraints on the real server;
- opening stock effective at 00:00 campus time, stored as UTC.
"""

import threading
import time as clock
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.core.clock import campus_timezone, campus_today
from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models import Category, Item, Unit
from app.models.purchases import StockMovement
from app.models.stock import StockOpening
from app.services import stock_ledger
from app.services.stock_ledger import Posting, as_utc

OPENINGS = "/api/stock/openings"


@pytest.fixture
def stock_world(client, db, setup_data):
    campus_id = setup_data["campus"].id
    kg = Unit(campus_id=campus_id, name="Kilogram", symbol="kg", dimension="weight")
    category = Category(campus_id=campus_id, name="Grains")
    db.add_all([kg, category])
    db.flush()
    rice = Item(campus_id=campus_id, name="Rice", category_id=category.id,
                standard_unit_id=kg.id, minimum_stock=Decimal("20"))
    db.add(rice)
    db.commit()
    return SimpleNamespace(campus_id=campus_id, kg=kg, rice=rice, admin=setup_data["user"])


@pytest.fixture
def engine_factory(db):
    engine = create_engine(db.get_bind().url, poolclass=NullPool,
                           connect_args={"prepare_threshold": None})
    yield sessionmaker(bind=engine, autoflush=False)
    engine.dispose()


@pytest.fixture
def parallel_clients(engine_factory, setup_data):
    def per_request_session():
        session = engine_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = per_request_session
    token = create_access_token(setup_data["user"].id, setup_data["user"].password_hash)
    clients = []
    try:
        for _ in range(4):
            client = TestClient(app)
            client.__enter__()
            csrf = client.get("/api/auth/csrf").json()["csrf_token"]
            client.headers.update({settings.CSRF_HEADER_NAME: csrf})
            client.cookies.set(settings.ACCESS_COOKIE_NAME, token)
            clients.append(client)
        yield clients
    finally:
        for client in clients:
            client.__exit__(None, None, None)
        app.dependency_overrides.pop(get_db, None)


def race(clients, calls):
    barrier = threading.Barrier(len(calls))
    statuses = [None] * len(calls)

    def worker(index):
        barrier.wait()
        statuses[index] = calls[index](clients[index]).status_code

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(len(calls))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return sorted(statuses)


def opening_body(item, qty="10"):
    return {"effective_date": (campus_today() - timedelta(days=2)).isoformat(),
            "lines": [{"item_id": item.id, "quantity": qty}]}


def test_simultaneous_openings_for_one_item_record_exactly_one(db, stock_world, parallel_clients):
    body = opening_body(stock_world.rice)  # read before the threads start
    statuses = race(parallel_clients, [lambda c: c.post(OPENINGS, json=body)] * 4)

    assert statuses.count(201) == 1 and statuses.count(409) == 3, statuses
    db.expire_all()
    assert db.query(StockOpening).filter_by(status="ACTIVE").count() == 1
    assert db.query(StockMovement).filter_by(movement_type="OPENING").count() == 1


def test_simultaneous_reversals_post_exactly_one(client, db, stock_world, parallel_clients):
    opening = client.post(OPENINGS, json=opening_body(stock_world.rice)).json()["items"][0]
    path = f"{OPENINGS}/{opening['id']}/reverse"

    statuses = race(parallel_clients, [lambda c: c.post(path, json={"reason": "race"})] * 4)

    assert statuses.count(200) == 1 and statuses.count(409) == 3, statuses
    db.expire_all()
    assert db.query(StockMovement).filter_by(movement_type="REVERSAL").count() == 1
    assert stock_ledger.item_balance(db, stock_world.campus_id, stock_world.rice.id) == Decimal("0")


def test_racing_outflows_cannot_both_pass_the_balance_check(client, db, stock_world, engine_factory):
    """Balance 10; two outflows of 6 at once. Each holds the item lock while
    it posts and waits before committing, so without the lock both would
    see 10 and pass. With it, the second sees 4 and is refused."""
    client.post(OPENINGS, json=opening_body(stock_world.rice, "10"))
    user = SimpleNamespace(id=stock_world.admin.id, campus_id=stock_world.campus_id)
    rice_id, kg_id = stock_world.rice.id, stock_world.kg.id  # not read inside threads
    barrier = threading.Barrier(2)
    results = []

    def worker(key):
        session = engine_factory()
        try:
            barrier.wait()
            stock_ledger.post(session, user, [Posting(
                item_id=rice_id, movement_type="ADJUSTMENT", direction=-1,
                quantity=Decimal("6"), unit_id=kg_id,
                effective_at=datetime.now(timezone.utc), source_key=key,
                reference_type="TEST", reference_id=1)])
            clock.sleep(0.4)
            session.commit()
            results.append("posted")
        except HTTPException as refused:
            session.rollback()
            results.append(refused.status_code)
        finally:
            session.close()

    threads = [threading.Thread(target=worker, args=(f"RACE:{i}",)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert sorted(results, key=str) == [409, "posted"], results
    db.expire_all()
    assert stock_ledger.item_balance(db, stock_world.campus_id, stock_world.rice.id) == Decimal("4")


def test_backdated_outflow_is_checked_against_history_on_postgresql(db, stock_world):
    rice, user = stock_world.rice, SimpleNamespace(id=stock_world.admin.id, campus_id=stock_world.campus_id)
    t = datetime(2026, 11, 1, 6, 0, tzinfo=timezone.utc)

    def posting(direction, qty, when, key, movement_type="ADJUSTMENT"):
        return Posting(item_id=rice.id, movement_type=movement_type, direction=direction,
                       quantity=Decimal(qty), unit_id=stock_world.kg.id, effective_at=when,
                       source_key=key, reference_type="TEST", reference_id=1)

    stock_ledger.post(db, user, [posting(1, "10", t + timedelta(days=1), "H:1"),
                                 posting(-1, "8", t + timedelta(days=2), "H:2"),
                                 posting(1, "20", t + timedelta(days=3), "H:3")])
    db.commit()
    with pytest.raises(HTTPException) as refused:
        stock_ledger.post(db, user, [posting(-1, "5", t + timedelta(days=1, hours=12), "H:4")])
    assert refused.value.status_code == 409 and "-3.000 kg" in refused.value.detail
    db.rollback()
    assert stock_ledger.item_balance(db, stock_world.campus_id, rice.id) == Decimal("22")


def test_one_active_opening_per_item_is_enforced_by_postgresql(db, stock_world):
    w = stock_world

    def opening(status="ACTIVE", **extra):
        return StockOpening(campus_id=w.campus_id, item_id=w.rice.id, quantity=Decimal("1"),
                            unit_id=w.kg.id, conversion_factor=Decimal("1"),
                            standard_quantity=Decimal("1"), standard_unit_id=w.kg.id,
                            effective_date=campus_today(), status=status,
                            created_by=w.admin.id, **extra)

    history = dict(reversed_by=w.admin.id, reversed_at=datetime.now(timezone.utc), reversal_reason="old")
    db.add_all([opening("REVERSED", **history), opening("REVERSED", **history), opening()])
    db.commit()
    db.add(opening())
    with pytest.raises(IntegrityError) as error:
        db.commit()
    db.rollback()
    assert "uq_stock_opening_active_item" in str(error.value)

    definition = db.execute(text(
        "SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_stock_opening_active_item'"
    )).scalar_one()
    assert "UNIQUE" in definition and "WHERE" in definition and "ACTIVE" in definition


def test_ledger_check_constraints_hold_on_postgresql(db, stock_world):
    w = stock_world
    now = datetime.now(timezone.utc)
    base = dict(campus_id=w.campus_id, item_id=w.rice.id, quantity=Decimal("1"), unit_id=w.kg.id,
                effective_at=now, reference_type="TEST", reference_id=1, created_by=w.admin.id)
    for index, bad in enumerate([
        dict(movement_type="OPENING", direction=-1),
        dict(movement_type="ISSUE", direction=1),
        dict(movement_type="REVERSAL", direction=-1),
        dict(movement_type="TRANSFER", direction=1),
        dict(movement_type="ADJUSTMENT", direction=0),
    ]):
        db.add(StockMovement(source_key=f"BAD:{index}", **base, **bad))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_opening_is_effective_at_campus_midnight_stored_as_utc(client, db, stock_world):
    day = campus_today() - timedelta(days=3)
    body = {"effective_date": day.isoformat(), "lines": [{"item_id": stock_world.rice.id, "quantity": "2"}]}
    assert client.post(OPENINGS, json=body).status_code == 201

    stored = db.execute(text(
        "SELECT effective_at FROM stock_movements WHERE movement_type = 'OPENING'"
    )).scalar_one()
    assert stored.tzinfo is not None
    local = as_utc(stored).astimezone(campus_timezone())
    assert (local.date(), local.time()) == (day, time(0, 0))
    expected = datetime.combine(day, time.min, tzinfo=campus_timezone()).astimezone(timezone.utc)
    assert as_utc(stored) == expected
