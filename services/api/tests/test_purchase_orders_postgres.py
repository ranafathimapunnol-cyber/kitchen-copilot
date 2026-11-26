"""
Stage 3 purchase orders on PostgreSQL (kitchen_copilot_test_db through the
shared tests/conftest.py fixtures). Covers what SQLite cannot:
- orders created at the same moment get distinct, consecutive numbers
  (the campus row lock);
- a cancellation racing a bill entered against the same order leaves a
  consistent result (the order row lock): never a bill on a cancelled order;
- quantities stay exact through unit conversion (NUMERIC).
"""

import threading
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
from app.models import Category, Item, Supplier, Unit, UnitConversion
from app.models.purchases import Purchase, PurchaseOrder

ORDERS = "/api/purchase-orders"


@pytest.fixture
def stock_world(db, setup_data):
    campus_id = setup_data["campus"].id
    kg = Unit(campus_id=campus_id, name="Kilogram", symbol="kg", dimension="weight")
    gram = Unit(campus_id=campus_id, name="Gram", symbol="g", dimension="weight")
    category = Category(campus_id=campus_id, name="Grains")
    supplier = Supplier(campus_id=campus_id, name="PG Orders Supplier")
    db.add_all([kg, gram, category, supplier])
    db.flush()
    db.add(UnitConversion(campus_id=campus_id, from_unit_id=kg.id, to_unit_id=gram.id,
                          factor=Decimal("1000")))
    rice = Item(campus_id=campus_id, name="Rice", category_id=category.id,
                standard_unit_id=kg.id, minimum_stock=0)
    db.add(rice)
    db.commit()
    return {"kg": kg, "gram": gram, "supplier": supplier, "rice": rice}


def order_body(world, quantity="50", unit="kg"):
    return {"supplier_id": world["supplier"].id, "order_date": "2026-11-10",
            "items": [{"item_id": world["rice"].id, "quantity": quantity,
                       "unit_id": world[unit].id}]}


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
    results = [None] * len(calls)

    def worker(index):
        barrier.wait()
        results[index] = calls[index](clients[index])

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(len(calls))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return results


def test_simultaneous_orders_get_distinct_consecutive_numbers(db, stock_world, parallel_clients):
    results = race(parallel_clients, [lambda c: c.post(ORDERS, json=order_body(stock_world))] * 4)

    assert [r.status_code for r in results] == [201] * 4, [r.text for r in results]
    numbers = sorted(r.json()["order_number"] for r in results)
    assert numbers == ["PO-00001", "PO-00002", "PO-00003", "PO-00004"]
    db.expire_all()
    assert db.query(PurchaseOrder).count() == 4


@pytest.mark.parametrize("attempt", range(3))
def test_cancel_racing_a_bill_never_leaves_a_bill_on_a_cancelled_order(
    client, db, stock_world, parallel_clients, attempt
):
    order = client.post(ORDERS, json=order_body(stock_world)).json()
    assert client.post(f"{ORDERS}/{order['id']}/place").status_code == 200
    line_id = order["items"][0]["id"]
    bill = {"supplier_id": stock_world["supplier"].id, "invoice_number": f"RACE-{attempt}",
            "purchase_date": "2026-11-12", "purchase_order_id": order["id"],
            "items": [{"item_id": stock_world["rice"].id, "quantity": "10",
                       "unit_id": stock_world["kg"].id, "unit_rate": "50",
                       "purchase_order_item_id": line_id}]}

    cancel, enter = race(parallel_clients[:2], [
        lambda c: c.post(f"{ORDERS}/{order['id']}/cancel", json={"reason": "race"}),
        lambda c: c.post("/api/purchases/", json=bill),
    ])

    db.expire_all()
    final = db.query(PurchaseOrder).filter_by(id=order["id"]).one().status
    bills = db.query(Purchase).filter_by(purchase_order_id=order["id"]).count()
    outcome = (cancel.status_code, enter.status_code, final, bills)
    assert outcome in {(200, 422, "CANCELLED", 0), (409, 201, "PLACED", 1)}, outcome


def test_progress_is_exact_through_unit_conversion(client, stock_world):
    order = client.post(ORDERS, json=order_body(stock_world, quantity="12.345", unit="kg")).json()
    client.post(f"{ORDERS}/{order['id']}/place")
    line_id = order["items"][0]["id"]
    bill = client.post("/api/purchases/", json={
        "supplier_id": stock_world["supplier"].id, "invoice_number": "EXACT-1",
        "purchase_date": "2026-11-12", "purchase_order_id": order["id"],
        "items": [{"item_id": stock_world["rice"].id, "quantity": "4567.891",
                   "unit_id": stock_world["gram"].id, "unit_rate": "0.05",
                   "purchase_order_item_id": line_id}]})
    assert bill.status_code == 201, bill.text

    line = client.get(f"{ORDERS}/{order['id']}").json()["items"][0]
    assert (line["ordered_quantity"], line["billed_quantity"], line["left_to_bill"]) == (
        "12.345", "4.568", "7.777")
    receiving = client.get(f"/api/purchases/{bill.json()['id']}/receiving").json()
    assert receiving["lines"][0]["ordered_quantity"] == "12345.000"
