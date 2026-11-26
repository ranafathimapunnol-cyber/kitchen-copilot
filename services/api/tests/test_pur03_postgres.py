"""
PUR03 on PostgreSQL: goods receipts under concurrency, exact quantities and
campus-local dates. Uses the shared tests/conftest.py fixtures
(kitchen_copilot_test_db). Covers what SQLite cannot:
- simultaneous drafts against one bill line never exceed the billed quantity;
- a receipt accepted from several sessions at once posts stock once;
- accept and cancel racing on one draft: exactly one wins;
- the stock movement log filters by campus-local day.
"""

import threading
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models import Category, Item, Supplier, Unit
from app.models.purchases import GoodsReceipt, StockMovement


@pytest.fixture
def stock_world(client, db, setup_data):
    campus_id = setup_data["campus"].id
    kg = Unit(campus_id=campus_id, name="Kilogram", symbol="kg", dimension="weight")
    category = Category(campus_id=campus_id, name="Grains")
    supplier = Supplier(campus_id=campus_id, name="PG Receipts Supplier")
    db.add_all([kg, category, supplier])
    db.flush()
    rice = Item(campus_id=campus_id, name="Rice", category_id=category.id,
                standard_unit_id=kg.id, minimum_stock=0)
    db.add(rice)
    db.commit()

    bill = client.post("/api/purchases/", json={
        "supplier_id": supplier.id, "invoice_number": "PG-REC-1",
        "purchase_date": "2026-11-03",
        "items": [{"item_id": rice.id, "quantity": "10", "unit_id": kg.id,
                   "unit_rate": "52.00"}],
    })
    assert bill.status_code == 201, bill.text
    bill_id = bill.json()["id"]
    line_id = client.get(f"/api/purchases/{bill_id}/receiving").json()["lines"][0]["purchase_item_id"]
    return {"bill_id": bill_id, "line_id": line_id, "rice": rice}


def draft_body(line_id, received, accepted=None):
    return {"receipt_date": "2026-11-05", "items": [{
        "purchase_item_id": line_id, "quantity_received": received,
        "quantity_accepted": accepted if accepted is not None else received}]}


@pytest.fixture
def parallel_clients(db, setup_data):
    engine = create_engine(db.get_bind().url, poolclass=NullPool,
                           connect_args={"prepare_threshold": None})
    factory = sessionmaker(bind=engine, autoflush=False)

    def per_request_session():
        session = factory()
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
        engine.dispose()


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


def test_simultaneous_drafts_never_exceed_the_billed_quantity(db, stock_world, parallel_clients):
    path = f"/api/purchases/{stock_world['bill_id']}/receipts"
    statuses = race(parallel_clients, [
        lambda c: c.post(path, json=draft_body(stock_world["line_id"], "4"))] * 4)

    assert statuses.count(201) == 2 and statuses.count(422) == 2, statuses
    db.expire_all()
    receiving = parallel_clients[0].get(f"/api/purchases/{stock_world['bill_id']}/receiving").json()
    assert receiving["lines"][0]["in_draft_quantity"] == "8.000"


def test_simultaneous_accepts_post_stock_once(client, db, stock_world, parallel_clients):
    receipt = client.post(f"/api/purchases/{stock_world['bill_id']}/receipts",
                          json=draft_body(stock_world["line_id"], "6.125")).json()

    statuses = race(parallel_clients, [
        lambda c: c.post(f"/api/receipts/{receipt['id']}/accept")] * 4)

    assert statuses.count(200) == 1 and statuses.count(409) == 3, statuses
    db.expire_all()
    posted = db.query(StockMovement).filter_by(reference_id=receipt["id"]).all()
    assert [m.quantity for m in posted] == [Decimal("6.125")]


def test_accept_and_cancel_racing_on_one_draft(client, db, stock_world, parallel_clients):
    receipt = client.post(f"/api/purchases/{stock_world['bill_id']}/receipts",
                          json=draft_body(stock_world["line_id"], "2")).json()
    accept = lambda c: c.post(f"/api/receipts/{receipt['id']}/accept")  # noqa: E731
    cancel = lambda c: c.post(f"/api/receipts/{receipt['id']}/cancel", json={"reason": "race"})  # noqa: E731

    statuses = race(parallel_clients, [accept, cancel, accept, cancel])

    assert statuses.count(200) == 1 and statuses.count(409) == 3, statuses
    db.expire_all()
    final = db.query(GoodsReceipt).filter_by(id=receipt["id"]).one().status
    stock = db.query(StockMovement).filter_by(reference_id=receipt["id"]).count()
    assert (final, stock) in {("ACCEPTED", 1), ("CANCELLED", 0)}


def test_stock_log_days_are_campus_local(client, db, setup_data, stock_world):
    # The ledger is append-only (decision 4b-5): instead of editing an
    # accepted receipt's posting time, the test posts its own movement with
    # the posting time it needs. 20:00 UTC on 17 November is 01:30 on
    # 18 November in India.
    posted = datetime(2026, 11, 17, 20, 0, tzinfo=timezone.utc)
    db.add(StockMovement(
        campus_id=setup_data["campus"].id, item_id=stock_world["rice"].id, movement_type="RECEIPT",
        direction=1, quantity=Decimal("1"), unit_id=stock_world["rice"].standard_unit_id,
        reference_type="TEST", reference_id=1, source_key="TEST:campus-local-day",
        effective_at=posted, created_at=posted, created_by=setup_data["user"].id,
    ))
    db.commit()

    def total(**params):
        return client.get("/api/stock-movements", params=params).json()["total"]

    assert total(date_from="2026-11-18", date_to="2026-11-18") == 1
    assert total(date_to="2026-11-17") == 0
    item = client.get("/api/stock-movements").json()["items"][0]
    assert item["created_at"].endswith("+00:00") and item["quantity"] == "1.000"
