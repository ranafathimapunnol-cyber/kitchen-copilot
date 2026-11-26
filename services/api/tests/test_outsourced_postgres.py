"""
Stage 8a outsourced food on PostgreSQL (kitchen_copilot_test_db, shared
tests/conftest.py fixtures). Covers what SQLite cannot:
- the check constraints and composite foreign keys of the outsourced tables
  and the widened meal-dish kind (a received line must match its delivery
  line exactly; prepared and carried lines are unchanged);
- races: confirming one delivery four times at once; one bill line linked to
  two order lines at once; a delivery racing the order's cancellation; four
  deliveries at once against one order line (accepted never exceeds ordered);
  a meal record created while a delivery is confirmed (the food is added
  exactly once, never left waiting); classifying an item OUTSOURCED while
  its opening stock is posted (never both);
- no stock or purchasing row is written by the outsourced workflow,
  compared by table content.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.core.clock import campus_today
from app.core.config import settings
from app.core.security import create_access_token
from app.models import Category, Item, MealSession, Supplier, Unit
from app.models.meals import MealDish
from app.models.outsourced import OutsourcedDelivery, OutsourcedDeliveryLine, OutsourcedOrderLine
from app.models.purchases import Purchase, PurchaseItem, StockMovement

from tests.test_stock_counts_postgres import race_all
from tests.test_stock_ledger_postgres import engine_factory, parallel_clients  # noqa: F401 (fixtures)

ORDERS = "/api/outsourced-orders"
DELIVERIES = "/api/outsourced-deliveries"
LINES = "/api/outsourced-order-lines"
MEALS = "/api/meal-records"
WRITE_TABLES = (
    "stock_movements", "stock_openings", "kitchen_issues", "kitchen_issue_items", "kitchen_returns",
    "kitchen_return_items", "stock_counts", "stock_count_items", "stock_adjustments", "purchases", "purchase_items",
    "purchase_orders", "purchase_order_items", "goods_receipts", "goods_receipt_items", "supplier_payments",
    "supplier_returns", "supplier_return_items", "waste_records", "waste_items",
)


def today(offset=0):
    return (campus_today() + timedelta(days=offset)).isoformat()


def ok(response, code=200):
    assert response.status_code == code, response.text
    return response.json()


def refused(db, sql, **params):
    """(refused?, first line of the error); always rolled back."""
    try:
        db.execute(text(sql), params)
        db.flush()
        return False, ""
    except Exception as error:  # noqa: BLE001
        return True, str(error).splitlines()[0]
    finally:
        db.rollback()


def table_fingerprints(db):
    return {t: db.execute(text(f'SELECT count(*), md5(coalesce(string_agg(x::text, \',\' ORDER BY x::text), \'\')) '
                               f'FROM "{t}" x')).one() for t in WRITE_TABLES}


@pytest.fixture
def out_pg(client, db, setup_data):
    campus_id = setup_data["campus"].id
    plate = Unit(campus_id=campus_id, name="Plate", symbol="plate", dimension="count")
    kg = Unit(campus_id=campus_id, name="Kilogram", symbol="kg", dimension="weight")
    category = Category(campus_id=campus_id, name="Food")
    breakfast = MealSession(campus_id=campus_id, name="Breakfast")
    caterer = Supplier(campus_id=campus_id, name="Annapurna Caterers")
    db.add_all([plate, kg, category, breakfast, caterer])
    db.flush()
    idli = Item(campus_id=campus_id, name="Idli set", category_id=category.id, standard_unit_id=plate.id,
                minimum_stock=0, item_kind="OUTSOURCED")
    dal = Item(campus_id=campus_id, name="Toor Dal", category_id=category.id, standard_unit_id=kg.id,
               minimum_stock=0)
    db.add_all([idli, dal])
    db.commit()
    return {"campus_id": campus_id, "plate": plate.id, "kg": kg.id, "idli": idli.id, "dal": dal.id,
            "breakfast": breakfast.id, "caterer": caterer.id, "admin": setup_data["user"]}


def order_body(k, qty="100"):
    return {"meal_date": today(), "meal_session_id": k["breakfast"], "supplier_id": k["caterer"],
            "lines": [{"item_id": k["idli"], "ordered_quantity": qty, "unit_id": k["plate"], "unit_rate": "35"}]}


def placed(client, k, qty="100"):
    order = ok(client.post(ORDERS, json=order_body(k, qty)), 201)
    return ok(client.post(f"{ORDERS}/{order['id']}/place"))


def delivery_body(order, received="100", rejected="0", reason=None):
    return {"delivery_date": today(), "lines": [{
        "order_line_id": order["lines"][0]["id"], "received_quantity": received, "rejected_quantity": rejected,
        "rejection_reason": reason}]}


def draft_delivery(client, order, **kwargs):
    after = ok(client.post(f"{ORDERS}/{order['id']}/deliveries", json=delivery_body(order, **kwargs)), 201)
    return after["deliveries"][0]


def make_bill(db, k, invoice="INV-1"):
    bill = Purchase(campus_id=k["campus_id"], supplier_id=k["caterer"], invoice_number=invoice,
                    purchase_date=campus_today(), subtotal=Decimal("3500"), discount=0, extra_charges=0,
                    grand_total=Decimal("3500"), status="DRAFT", created_by=k["admin"].id)
    db.add(bill)
    db.flush()
    line = PurchaseItem(campus_id=k["campus_id"], purchase_id=bill.id, item_id=k["idli"], quantity=Decimal("100"),
                        unit_id=k["plate"], unit_rate=Decimal("35"), line_total=Decimal("3500"))
    db.add(line)
    db.commit()
    return line.id


# ============================================================
# CONSTRAINTS
# ============================================================

def test_the_database_keeps_delivery_and_received_lines_consistent(client, db, out_pg):
    k = out_pg
    order = placed(client, k)
    delivery = draft_delivery(client, order, received="10", rejected="2", reason="Cold")
    ok(client.post(f"{DELIVERIES}/{delivery['id']}/confirm"))
    record = ok(client.post(MEALS, json={"meal_date": today(), "meal_session_id": k["breakfast"],
                                         "expected_students": 10, "expected_staff": 0, "expected_guests": 0}), 201)
    dish = next(d for d in record["dishes"] if d["kind"] == "RECEIVED")
    line_id = db.get(MealDish, dish["id"]).source_delivery_line_id
    assert dish["received_quantity"] == "8.000"

    for sql, message in (
        ("UPDATE outsourced_delivery_lines SET accepted_quantity = 9 WHERE id = :id", "ck_outsourced_delivery_line"),
        ("UPDATE outsourced_delivery_lines SET rejection_reason = NULL WHERE id = :id", "ck_outsourced_delivery_line_reason"),
        ("UPDATE outsourced_delivery_lines SET rejected_quantity = 11, accepted_quantity = -1 WHERE id = :id",
         "ck_outsourced_delivery_line"),
        ("UPDATE outsourced_delivery_lines SET unit_id = :kg WHERE id = :id", "fk_"),
        ("DELETE FROM outsourced_delivery_lines WHERE id = :id", "fk_meal_dish_received_from"),
    ):
        was_refused, error = refused(db, sql, id=line_id, kg=k["kg"])
        assert was_refused and message in error, (sql, error)
    for sql, message in (
        ("UPDATE meal_dishes SET received_quantity = 9, available_quantity = 9 WHERE id = :d",
         "fk_meal_dish_received_from"),
        ("UPDATE meal_dishes SET output_quantity = 1, available_quantity = 9 WHERE id = :d", "ck_meal_dish_kind"),
        ("UPDATE meal_dishes SET available_quantity = 7 WHERE id = :d", "ck_meal_dish_available"),
        ("UPDATE meal_dishes SET source_delivery_line_id = NULL WHERE id = :d", "ck_meal_dish_kind"),
    ):
        was_refused, error = refused(db, sql, d=dish["id"])
        assert was_refused and message in error, (sql, error)
    # A prepared dish cannot carry a received quantity.
    prepared = ok(client.post(f"{MEALS}/{record['id']}/dishes", json={
        "dish_name": "Upma", "output_quantity": "5", "unit_id": k["kg"]}), 201)
    upma = next(d for d in prepared["dishes"] if d["dish_name"] == "Upma")
    was_refused, error = refused(db, "UPDATE meal_dishes SET received_quantity = 1, available_quantity = 6 WHERE id = :d",
                                 d=upma["id"])
    assert was_refused and "ck_meal_dish_kind" in error
    # Order and line checks.
    for sql, message in (
        ("UPDATE outsourced_order_lines SET ordered_quantity = 0 WHERE order_id = :o", "ck_outsourced_order_line_quantity"),
        ("UPDATE outsourced_order_lines SET purchase_item_id = NULL, linked_at = now() WHERE order_id = :o",
         "ck_outsourced_order_line_bill_link"),
        ("UPDATE outsourced_orders SET status = 'CANCELLED' WHERE id = :o", "ck_outsourced_order_cancelled"),
        ("UPDATE outsourced_orders SET status = 'SHIPPED' WHERE id = :o", "ck_outsourced_order_status"),
    ):
        was_refused, error = refused(db, sql, o=order["id"])
        assert was_refused and message in error, (sql, error)


# ============================================================
# RACES
# ============================================================

def test_confirming_one_delivery_four_times_at_once_confirms_it_once(client, db, out_pg, parallel_clients):
    k = out_pg
    ok(client.post(MEALS, json={"meal_date": today(), "meal_session_id": k["breakfast"], "expected_students": 1,
                                "expected_staff": 0, "expected_guests": 0}), 201)
    delivery = draft_delivery(client, placed(client, k))

    outcomes = race_all(parallel_clients, [lambda c: c.post(f"{DELIVERIES}/{delivery['id']}/confirm")] * 4)

    assert sorted(outcomes) == [200, 409, 409, 409], outcomes
    db.expire_all()
    assert db.query(MealDish).filter(MealDish.source_delivery_line_id.isnot(None)).count() == 1
    confirms = db.execute(text("SELECT count(*) FROM audit_logs WHERE entity_type = 'OUTSOURCED_DELIVERY' "
                               "AND entity_id = :id AND action = 'CONFIRM'"), {"id": delivery["id"]}).scalar()
    assert confirms == 1


def test_one_bill_line_linked_to_two_order_lines_at_once_links_once(client, db, out_pg, parallel_clients):
    k = out_pg
    bill_line = make_bill(db, k)
    first, second = placed(client, k), placed(client, k)

    outcomes = race_all(parallel_clients, [
        (lambda o: lambda c: c.put(f"{LINES}/{o['lines'][0]['id']}/bill-line",
                                   json={"purchase_item_id": bill_line}))(o) for o in (first, second)])

    assert sorted(outcomes) == [200, 409], outcomes
    db.expire_all()
    assert db.query(OutsourcedOrderLine).filter_by(purchase_item_id=bill_line).count() == 1


def test_a_delivery_racing_the_order_cancellation_never_both_succeed(client, db, out_pg, parallel_clients):
    k = out_pg
    for _ in range(3):
        order = placed(client, k)
        outcomes = race_all(parallel_clients, [
            lambda c: c.post(f"{ORDERS}/{order['id']}/deliveries", json=delivery_body(order, received="5")),
            lambda c: c.post(f"{ORDERS}/{order['id']}/cancel", json={"reason": "Supplier closed"}),
        ])
        assert sorted(outcomes) in ([200, 409], [201, 409]), outcomes
        db.expire_all()
        live = db.query(OutsourcedDelivery).filter(OutsourcedDelivery.order_id == order["id"],
                                                   OutsourcedDelivery.status != "CANCELLED").count()
        status = db.execute(text("SELECT status FROM outsourced_orders WHERE id = :id"), {"id": order["id"]}).scalar()
        assert (status, live) in (("CANCELLED", 0), ("ORDERED", 1))


def test_four_deliveries_at_once_never_accept_more_than_ordered(client, db, out_pg, parallel_clients):
    k = out_pg
    order = placed(client, k, qty="100")

    outcomes = race_all(parallel_clients, [
        lambda c: c.post(f"{ORDERS}/{order['id']}/deliveries", json=delivery_body(order, received="40"))] * 4)

    assert sorted(outcomes) == [201, 201, 422, 422], outcomes
    db.expire_all()
    accepted = sum(Decimal(str(l.accepted_quantity)) for l in db.query(OutsourcedDeliveryLine).all())
    assert accepted == Decimal("80")


def test_a_meal_record_created_while_a_delivery_is_confirmed_gets_the_food_once(client, db, out_pg, parallel_clients):
    k = out_pg
    for day in range(3):
        meal_date = today(-day)
        order_payload = {**order_body(k), "meal_date": meal_date, "order_date": meal_date}
        order = ok(client.post(ORDERS, json=order_payload), 201)
        order = ok(client.post(f"{ORDERS}/{order['id']}/place"))
        delivery = ok(client.post(f"{ORDERS}/{order['id']}/deliveries", json={
            **delivery_body(order, received="20"), "delivery_date": meal_date}), 201)["deliveries"][0]

        outcomes = race_all(parallel_clients, [
            lambda c: c.post(f"{DELIVERIES}/{delivery['id']}/confirm"),
            lambda c: c.post(MEALS, json={"meal_date": meal_date, "meal_session_id": k["breakfast"],
                                          "expected_students": 20, "expected_staff": 0, "expected_guests": 0}),
        ])

        assert sorted(outcomes) == [200, 201], outcomes
        db.expire_all()
        record = db.execute(text("SELECT id FROM meal_records WHERE meal_date = :d AND status = 'OPEN'"),
                            {"d": meal_date}).scalar()
        dishes = db.query(MealDish).filter(MealDish.meal_record_id == record,
                                           MealDish.source_delivery_line_id.isnot(None)).count()
        assert dishes == 1, f"day -{day}: food left waiting although the record exists"


def test_classifying_an_item_outsourced_while_its_opening_stock_is_posted_never_both(client, db, out_pg,
                                                                                     parallel_clients):
    k = out_pg
    outcomes = race_all(parallel_clients, [
        lambda c: c.put(f"/api/items/{k['dal']}/kind", json={"item_kind": "OUTSOURCED"}),
        lambda c: c.post("/api/stock/openings", json={"effective_date": today(),
                                                      "lines": [{"item_id": k["dal"], "quantity": "5"}]}),
    ])
    db.expire_all()
    kind = db.get(Item, k["dal"]).item_kind
    movements = db.query(StockMovement).filter_by(item_id=k["dal"]).count()
    assert (kind == "OUTSOURCED") != (movements == 1), (outcomes, kind, movements)
    assert sorted(outcomes) in ([200, 422], [201, 409]), outcomes


# ============================================================
# NO STOCK OR PURCHASING WRITES (OUT01 criterion 7)
# ============================================================

def test_the_outsourced_workflow_writes_no_stock_or_purchasing_row(client, db, out_pg):
    k = out_pg
    bill_line = make_bill(db, k)
    before = table_fingerprints(db)
    order = placed(client, k)
    ok(client.put(f"{LINES}/{order['lines'][0]['id']}/bill-line", json={"purchase_item_id": bill_line}))
    delivery = draft_delivery(client, order, received="100", rejected="3", reason="Spilt")
    ok(client.post(f"{DELIVERIES}/{delivery['id']}/confirm"))
    record = ok(client.post(MEALS, json={"meal_date": today(), "meal_session_id": k["breakfast"],
                                         "expected_students": 90, "expected_staff": 0, "expected_guests": 0}), 201)
    dish = next(d for d in record["dishes"] if d["kind"] == "RECEIVED")
    ok(client.put(f"{MEALS}/{record['id']}/dishes/{dish['id']}/distribution", json={
        "distributed_quantity": "90", "remaining_quantity": "7",
        "leftovers": [{"classification": "WASTED", "quantity": "7", "remarks": "Plate waste"}]}))
    ok(client.get(f"/api/outsourced-food/report?date_from={today()}&date_to={today()}"))
    export = client.post("/api/outsourced-food/report/export", json={"format": "pdf", "date_from": today(),
                                                                       "date_to": today()})
    assert export.status_code == 200 and export.content.startswith(b"%PDF")
    db.expire_all()
    assert table_fingerprints(db) == before
