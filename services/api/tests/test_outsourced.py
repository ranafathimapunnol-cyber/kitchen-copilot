"""
Stage 8a: outsourced food (OUT01, OUT02, OUT03 criterion 1, AT04), per
docs/STAGE-8-IMPLEMENTATION-PLAN.md (P8-1 to P8-5, P8-7).

Interim rules tested here are not client decisions: orders by ADMIN and
KITCHEN_MANAGER, deliveries through outsourced_food.create/update, costs only
with purchase_bill.read (P8-3 option b, matrix gap); rejected quantities
recorded with no credit (Q6); exact meal-session matching (C5); closed meal
records never changed (reconciliation pending); explicit units only (Q7).

In-memory SQLite with the shared fixtures of test_operational_authority and
the kitchen fixture of test_kitchen_issues. tests/test_outsourced_postgres.py
covers the PostgreSQL constraints and races.
"""

import io
import zipfile
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.core.clock import campus_today
from app.models import AuditLog, Item, MealSession, Supplier, Unit
from app.models.meals import MealDish, MealRecord
from app.models.outsourced import OutsourcedDelivery, OutsourcedDeliveryLine, OutsourcedOrder, OutsourcedOrderLine
from app.models.purchases import (
    GoodsReceipt, GoodsReceiptItem, Purchase, PurchaseItem, PurchaseOrder, PurchaseOrderItem, StockMovement,
    SupplierPayment, SupplierReturn, SupplierReturnItem,
)
from app.models.stock import (
    KitchenIssue, KitchenIssueItem, KitchenReturn, KitchenReturnItem, StockAdjustment, StockCount, StockCountItem,
    StockOpening,
)
from app.services import stock_ledger

from tests.test_kitchen_issues import days_ago, kitchen, new_issue  # noqa: F401 (fixtures)
from tests.test_meals import add_dish, created, dish_named, distribute, ok, set_counts
from tests.test_operational_authority import act_as, client, db, grant, world  # noqa: F401 (fixtures)

ORDERS = "/api/outsourced-orders"
DELIVERIES = "/api/outsourced-deliveries"
LINES = "/api/outsourced-order-lines"
REPORT = "/api/outsourced-food/report"
MEALS = "/api/meal-records"

STOCK_MODELS = (
    StockMovement, StockOpening, KitchenIssue, KitchenIssueItem, KitchenReturn, KitchenReturnItem, StockCount,
    StockCountItem, StockAdjustment, Purchase, PurchaseItem, PurchaseOrder, PurchaseOrderItem, GoodsReceipt,
    GoodsReceiptItem, SupplierPayment, SupplierReturn, SupplierReturnItem,
)
COST_FIELDS = ("unit_rate", "line_total", "bill_line", "planned_total", "billed_total", "planned_cost",
               "billed_cost", "cost_totals")


def today(offset=0):
    return (campus_today() + timedelta(days=offset)).isoformat()


@pytest.fixture
def out(db, kitchen):
    """Adds to campus A: a plate unit; two OUTSOURCED items (Idli set,
    Veg Meals, in plates); a caterer and a second supplier; Breakfast and a
    same-named "  breakfast " session. Campus B: its own outsourced item."""
    a, b = kitchen.a, kitchen.b
    plate = Unit(campus_id=a.campus.id, name="Plate", symbol="plate", dimension="count")
    db.add(plate)
    db.flush()
    idli = Item(campus_id=a.campus.id, name="Idli set", category_id=a.category.id, standard_unit_id=plate.id,
                minimum_stock=0, item_kind="OUTSOURCED")
    meals_item = Item(campus_id=a.campus.id, name="Veg Meals", category_id=a.category.id, standard_unit_id=plate.id,
                      minimum_stock=0, item_kind="OUTSOURCED")
    caterer = Supplier(campus_id=a.campus.id, name="Annapurna Caterers")
    hotel = Supplier(campus_id=a.campus.id, name="Hotel Saravana")
    breakfast = MealSession(campus_id=a.campus.id, name="Breakfast")
    breakfast_dup = MealSession(campus_id=a.campus.id, name="  breakfast ")
    b_plate = Unit(campus_id=b.campus.id, name="Plate", symbol="plate", dimension="count")
    db.add_all([idli, meals_item, caterer, hotel, breakfast, breakfast_dup, b_plate])
    db.flush()
    b_item = Item(campus_id=b.campus.id, name="Hill Idli", category_id=b.category.id, standard_unit_id=b_plate.id,
                  minimum_stock=0, item_kind="OUTSOURCED")
    db.add(b_item)
    db.commit()
    a.plate, a.idli, a.meals, a.caterer, a.hotel = plate, idli, meals_item, caterer, hotel
    a.breakfast, a.breakfast_dup = breakfast, breakfast_dup
    b.plate, b.idli = b_plate, b_item
    return kitchen


def order_body(a, lines=None, day=None, session=None, supplier=None, notes=None):
    lines = lines if lines is not None else [(a.idli, "100", "35")]
    return {"meal_date": day or today(), "meal_session_id": (session or a.breakfast).id,
            "supplier_id": (supplier or a.caterer).id, "notes": notes,
            "lines": [{"item_id": i.id, "ordered_quantity": q, "unit_id": a.plate.id, "unit_rate": r}
                      for i, q, r in lines]}


def placed(client, a, **kwargs):
    order = ok(client.post(ORDERS, json=order_body(a, **kwargs)), 201)
    return ok(client.post(f"{ORDERS}/{order['id']}/place"))


def line_for(order, item):
    return next(l for l in order["lines"] if l["item_id"] == item.id)


def delivery_body(order, entries, day=None, remarks=None):
    """entries: [(item, received, rejected, reason)]"""
    return {"delivery_date": day or today(), "remarks": remarks, "lines": [
        {"order_line_id": line_for(order, item)["id"], "received_quantity": received,
         "rejected_quantity": rejected, "rejection_reason": reason}
        for item, received, rejected, reason in entries]}


def deliver(client, order, entries, confirm=True, **kwargs):
    after = ok(client.post(f"{ORDERS}/{order['id']}/deliveries", json=delivery_body(order, entries, **kwargs)), 201)
    delivery = after["deliveries"][0]
    if confirm:
        after = ok(client.post(f"{DELIVERIES}/{delivery['id']}/confirm"))
    return after, delivery


def stock_fingerprint(db):
    db.expire_all()
    return {m.__tablename__: sorted(repr(sorted((k, str(v)) for k, v in vars(r).items() if not k.startswith("_")))
                                    for r in db.query(m).all()) for m in STOCK_MODELS}


def make_bill(db, a, item, qty, rate, supplier=None, unit=None, invoice="INV-OUT-1"):
    total = (Decimal(qty) * Decimal(rate)).quantize(Decimal("0.01"))
    bill = Purchase(campus_id=a.campus.id, supplier_id=(supplier or a.caterer).id, invoice_number=invoice,
                    purchase_date=campus_today(), subtotal=total, discount=0, extra_charges=0, grand_total=total,
                    status="DRAFT", created_by=a.admin.id)
    db.add(bill)
    db.flush()
    line = PurchaseItem(campus_id=a.campus.id, purchase_id=bill.id, item_id=item.id, quantity=Decimal(qty),
                        unit_id=(unit or a.plate).id, unit_rate=Decimal(rate), line_total=total)
    db.add(line)
    db.commit()
    return bill, line


def audit_actions(db, entity, entity_id):
    return [r.action for r in db.query(AuditLog).filter_by(entity_type=entity, entity_id=entity_id).order_by(AuditLog.id)]


# ============================================================
# ORDERS: ADMIN AND KITCHEN_MANAGER (P8-3 option b)
# ============================================================

@pytest.mark.parametrize("role", ["admin", "manager"])
def test_admin_and_manager_create_edit_place_and_cancel_orders(client, db, out, role):
    a = out.a
    act_as(client, getattr(a, role))
    order = ok(client.post(ORDERS, json=order_body(a, notes="For Monday breakfast")), 201)
    assert order["order_number"] == "OO-00001" and order["status"] == "DRAFT"
    assert order["meal_session_name"] == "Breakfast" and order["supplier_name"] == "Annapurna Caterers"
    line = order["lines"][0]
    assert (line["ordered_quantity"], line["unit_symbol"], line["unit_rate"], line["line_total"]) == (
        "100.000", "plate", "35.0000", "3500.00")
    assert order["planned_total"] == "3500.00"

    edited = ok(client.put(f"{ORDERS}/{order['id']}", json=order_body(
        a, lines=[(a.idli, "120", "35"), (a.meals, "40", "80.50")])))
    assert [l["item_name"] for l in edited["lines"]] == ["Idli set", "Veg Meals"]
    assert edited["planned_total"] == "7420.00"

    placed_order = ok(client.post(f"{ORDERS}/{order['id']}/place"))
    assert placed_order["status"] == "ORDERED" and placed_order["receiving_status"] == "NOT_RECEIVED"
    assert client.put(f"{ORDERS}/{order['id']}", json=order_body(a)).status_code == 409
    assert client.post(f"{ORDERS}/{order['id']}/place").status_code == 409

    assert client.post(f"{ORDERS}/{order['id']}/cancel", json={"reason": ""}).status_code == 422
    cancelled = ok(client.post(f"{ORDERS}/{order['id']}/cancel", json={"reason": "Menu changed"}))
    assert cancelled["status"] == "CANCELLED" and cancelled["cancellation_reason"] == "Menu changed"
    assert audit_actions(db, "OUTSOURCED_ORDER", order["id"]) == ["CREATE", "UPDATE", "PLACE", "CANCEL"]


def test_staff_never_create_or_manage_orders_whatever_grants_exist(client, db, out):
    a = out.a
    act_as(client, a.admin)
    draft = ok(client.post(ORDERS, json=order_body(a)), 201)
    for code in ("outsourced_food.create", "outsourced_food.read", "outsourced_food.update", "purchase_bill.read"):
        grant(db, a.staff, a.admin, code)
    act_as(client, a.staff)
    assert client.post(ORDERS, json=order_body(a)).status_code == 403
    assert client.put(f"{ORDERS}/{draft['id']}", json=order_body(a)).status_code == 403
    assert client.post(f"{ORDERS}/{draft['id']}/place").status_code == 403
    assert client.post(f"{ORDERS}/{draft['id']}/cancel", json={"reason": "No"}).status_code == 403
    detail = ok(client.get(f"{ORDERS}/{draft['id']}"))
    assert not detail["permissions"]["can_edit"] and not detail["permissions"]["can_place"]
    assert db.query(OutsourcedOrder).count() == 1


def test_staff_without_grants_see_nothing(client, out):
    a = out.a
    act_as(client, a.admin)
    order = placed(client, a)
    act_as(client, a.staff)
    for path in (ORDERS, f"{ORDERS}/options", f"{ORDERS}/{order['id']}", f"{ORDERS}/{order['id']}/history",
                 f"{REPORT}?date_from={today()}&date_to={today()}"):
        assert client.get(path).status_code == 403, path
    body = delivery_body(order, [(a.idli, "10", "0", None)])
    assert client.post(f"{ORDERS}/{order['id']}/deliveries", json=body).status_code == 403


def test_orders_accept_only_active_outsourced_items_and_valid_dates(client, db, out):
    a = out.a
    act_as(client, a.admin)
    refused = client.post(ORDERS, json={**order_body(a), "lines": [
        {"item_id": a.item.id, "ordered_quantity": "5", "unit_id": a.kg.id, "unit_rate": "60"}]})
    assert refused.status_code == 422 and "not classified as outsourced food" in refused.json()["detail"]
    twice = client.post(ORDERS, json=order_body(a, lines=[(a.idli, "1", "1"), (a.idli, "2", "1")]))
    assert twice.status_code == 422 and "once per order" in twice.json()["detail"]
    assert client.post(ORDERS, json=order_body(a, day=today(31))).status_code == 422
    assert client.post(ORDERS, json={**order_body(a), "order_date": today(1), "meal_date": today(2)}).status_code == 422
    assert client.post(ORDERS, json={**order_body(a), "order_date": today(), "meal_date": today(-1)}).status_code == 422
    assert client.post(ORDERS, json=order_body(a, lines=[(a.idli, "0", "1")])).status_code == 422
    assert client.post(ORDERS, json=order_body(a, lines=[(a.idli, "5", "-1")])).status_code == 422
    assert client.post(ORDERS, json=order_body(a, session=out.b.lunch)).status_code == 422
    a.hotel.is_active = False
    db.commit()
    assert client.post(ORDERS, json=order_body(a, supplier=a.hotel)).status_code == 422
    # A past meal can be recorded after the fact.
    ok(client.post(ORDERS, json={**order_body(a, day=today(-3)), "order_date": today(-4)}), 201)
    assert db.query(OutsourcedOrder).count() == 1


def test_campus_isolation(client, db, out):
    a, b = out.a, out.b
    act_as(client, a.admin)
    order = placed(client, a)
    act_as(client, b.admin)
    assert client.get(f"{ORDERS}/{order['id']}").status_code == 404
    assert client.post(f"{ORDERS}/{order['id']}/cancel", json={"reason": "Not ours"}).status_code == 404
    assert client.post(f"{ORDERS}/{order['id']}/deliveries",
                       json=delivery_body(order, [(a.idli, "1", "0", None)])).status_code == 404
    assert ok(client.get(ORDERS))["total"] == 0
    assert [i["name"] for i in ok(client.get(f"{ORDERS}/options"))["items"]] == ["Hill Idli"]
    refused = client.post(ORDERS, json={"meal_date": today(), "meal_session_id": b.lunch.id,
                                        "supplier_id": b.supplier.id, "lines": [
        {"item_id": a.idli.id, "ordered_quantity": "1", "unit_id": b.plate.id, "unit_rate": "1"}]})
    assert refused.status_code == 422


# ============================================================
# DELIVERIES: RECEIVED, REJECTED, ACCEPTED (OUT01, OUT03 criterion 1)
# ============================================================

def test_partial_deliveries_and_quantity_validation(client, db, out):
    a = out.a
    act_as(client, a.admin)
    order = placed(client, a, lines=[(a.idli, "100", "35"), (a.meals, "40", "80")])
    deliveries = f"{ORDERS}/{order['id']}/deliveries"

    no_reason = client.post(deliveries, json=delivery_body(order, [(a.idli, "60", "5", None)]))
    assert no_reason.status_code == 422 and "reason" in no_reason.text
    too_many_rejected = client.post(deliveries, json=delivery_body(order, [(a.idli, "60", "61", "Spoilt")]))
    assert too_many_rejected.status_code == 422
    assert client.post(deliveries, json=delivery_body(order, [(a.idli, "0", "0", None)])).status_code == 422
    assert client.post(deliveries, json=delivery_body(order, [(a.idli, "5", "0", None)], day=today(1))).status_code == 422

    first, d1 = deliver(client, order, [(a.idli, "60", "5", "Five plates cold")])
    line = line_for(first, a.idli)
    assert (line["received_quantity"], line["rejected_quantity"], line["accepted_quantity"],
            line["remaining_quantity"]) == ("60.000", "5.000", "55.000", "45.000")
    assert first["receiving_status"] == "PARTLY_RECEIVED"
    assert first["rejection_note"].startswith("Credit not recorded because client question Q6")
    delivered = first["deliveries"][0]["lines"][0]
    assert delivered["rejection_reason"] == "Five plates cold" and delivered["accepted_quantity"] == "55.000"

    # A draft holds its quantity: a second draft cannot also take it.
    held, d2 = deliver(client, order, [(a.idli, "40", "0", None)], confirm=False)
    assert line_for(held, a.idli)["in_draft_quantity"] == "40.000"
    over = client.post(deliveries, json=delivery_body(order, [(a.idli, "10", "4", "Extra")]))
    assert over.status_code == 422 and "only 5.000 plate remain" in over.json()["detail"]
    # Excess received is allowed when it is rejected.
    ok(client.put(f"{DELIVERIES}/{d2['id']}", json=delivery_body(order, [(a.idli, "48", "3", "Over-delivered")])))
    final = ok(client.post(f"{DELIVERIES}/{d2['id']}/confirm"))
    assert line_for(final, a.idli)["accepted_quantity"] == "100.000"
    assert line_for(final, a.idli)["remaining_quantity"] == "0.000"
    assert final["receiving_status"] == "PARTLY_RECEIVED"  # Veg Meals not yet delivered
    assert client.post(f"{DELIVERIES}/{d2['id']}/confirm").status_code == 409
    assert client.put(f"{DELIVERIES}/{d2['id']}", json=delivery_body(order, [(a.idli, "1", "0", None)])).status_code == 409

    done, _d3 = deliver(client, order, [(a.meals, "40", "0", None)])
    assert done["receiving_status"] == "RECEIVED"
    assert not done["permissions"]["can_record_delivery"]
    assert [d["delivery_number"] for d in done["deliveries"]] == ["OD-00003", "OD-00002", "OD-00001"]
    assert audit_actions(db, "OUTSOURCED_DELIVERY", d2["id"]) == ["CREATE", "UPDATE", "CONFIRM"]


def test_deliveries_need_an_ordered_order(client, out):
    a = out.a
    act_as(client, a.admin)
    draft = ok(client.post(ORDERS, json=order_body(a)), 201)
    refused = client.post(f"{ORDERS}/{draft['id']}/deliveries", json=delivery_body(draft, [(a.idli, "1", "0", None)]))
    assert refused.status_code == 409


def test_staff_with_outsourced_grants_record_and_confirm_deliveries_without_costs(client, db, out):
    a = out.a
    act_as(client, a.admin)
    order = placed(client, a)
    for code in ("outsourced_food.create", "outsourced_food.read", "outsourced_food.update"):
        grant(db, a.staff, a.admin, code)
    act_as(client, a.staff)
    view = ok(client.get(f"{ORDERS}/{order['id']}"))
    assert not view["costs_visible"]
    for field in COST_FIELDS:
        assert field not in view and field not in view["lines"][0], field
    assert view["permissions"]["can_record_delivery"] and not view["permissions"]["can_link_bill"]
    after, delivery = deliver(client, view, [(a.idli, "100", "2", "Two broken boxes")])
    assert after["deliveries"][0]["status"] == "CONFIRMED"
    assert all(f not in after for f in COST_FIELDS)
    listing = ok(client.get(ORDERS))
    assert "planned_total" not in listing["items"][0] and not listing["costs_visible"]
    options = ok(client.get(f"{ORDERS}/options"))
    assert not options["can_manage_orders"] and not options["costs_visible"]
    # A confirmed delivery is cancelled only by an Admin or Kitchen Manager.
    assert client.post(f"{DELIVERIES}/{delivery['id']}/cancel", json={"reason": "Mistake"}).status_code == 403
    # History leaves out costs.
    history = ok(client.get(f"{ORDERS}/{order['id']}/history"))["items"]
    assert [h["action"] for h in history][:2] == ["CREATE", "PLACE"]
    assert "unit_rate" not in str(history) and "line_total" not in str(history)


def test_staff_with_only_create_cannot_confirm(client, db, out):
    a = out.a
    act_as(client, a.admin)
    order = placed(client, a)
    for code in ("outsourced_food.create", "outsourced_food.read"):
        grant(db, a.staff, a.admin, code)
    act_as(client, a.staff)
    after, delivery = deliver(client, order, [(a.idli, "10", "0", None)], confirm=False)
    assert client.post(f"{DELIVERIES}/{delivery['id']}/confirm").status_code == 403
    assert client.put(f"{DELIVERIES}/{delivery['id']}",
                      json=delivery_body(order, [(a.idli, "9", "0", None)])).status_code == 403


def test_staff_with_bill_read_sees_costs(client, db, out):
    a = out.a
    act_as(client, a.admin)
    order = placed(client, a)
    for code in ("outsourced_food.read", "purchase_bill.read"):
        grant(db, a.staff, a.admin, code)
    act_as(client, a.staff)
    view = ok(client.get(f"{ORDERS}/{order['id']}"))
    assert view["costs_visible"] and view["planned_total"] == "3500.00"
    assert view["lines"][0]["unit_rate"] == "35.0000"
    assert not view["permissions"]["can_link_bill"]  # needs purchase_bill.update


# ============================================================
# MEAL RECORDS (P8-4): EXACT SESSION, CLOSED RECORDS
# ============================================================

def test_confirmed_food_waits_for_the_meal_record_then_is_added(client, db, out):
    a = out.a
    act_as(client, a.admin)
    order = placed(client, a)
    after, delivery = deliver(client, order, [(a.idli, "100", "4", "Four plates spilt")])
    link = after["deliveries"][0]["lines"][0]["meal_link"]
    assert link["state"] == "PENDING_NO_RECORD" and after["meal_link_state"] == "PENDING_NO_RECORD"

    # The same-named other session is never linked.
    other = created(client, a, session=a.breakfast_dup)
    assert other["dishes"] == []
    record = created(client, a, session=a.breakfast)
    received = dish_named(record, "Idli set")
    assert received["kind"] == "RECEIVED" and received["received_quantity"] == "96.000"
    assert received["available_quantity"] == "96.000" and received["unit_symbol"] == "plate"
    assert received["received_from"]["delivery_number"] == delivery["delivery_number"]
    assert received["received_from"]["order_number"] == order["order_number"]
    view = ok(client.get(f"{ORDERS}/{order['id']}"))
    assert view["deliveries"][0]["lines"][0]["meal_link"]["state"] == "ADDED"
    assert view["meal_record"]["id"] == record["id"] and view["meal_link_state"] == "ADDED"
    assert any("same name" in w for w in view["session_warnings"])
    assert "RECEIVE_OUTSOURCED" in audit_actions(db, "MEAL_RECORD", record["id"])
    assert "ADDED_TO_MEAL_RECORD" in audit_actions(db, "OUTSOURCED_DELIVERY", delivery["id"])


def test_food_confirmed_while_the_record_is_open_is_added_at_once(client, db, out):
    a = out.a
    act_as(client, a.admin)
    record = created(client, a, session=a.breakfast)
    order = placed(client, a)
    after, _d = deliver(client, order, [(a.idli, "50", "0", None)])
    assert after["meal_link_state"] == "ADDED"
    record = ok(client.get(f"{MEALS}/{record['id']}"))
    assert dish_named(record, "Idli set")["received_quantity"] == "50.000"


def test_received_lines_reconcile_like_prepared_dishes_and_stay_fixed(client, db, out):
    a = out.a
    act_as(client, a.admin)
    record = created(client, a, session=a.breakfast)
    order = placed(client, a)
    deliver(client, order, [(a.idli, "100", "0", None)])
    record = ok(client.get(f"{MEALS}/{record['id']}"))
    dish = dish_named(record, "Idli set")
    edit = client.put(f"{MEALS}/{record['id']}/dishes/{dish['id']}", json={
        "dish_name": "Idli", "output_quantity": "1", "unit_id": a.plate.id})
    assert edit.status_code == 409 and "only its remarks" in edit.json()["detail"]
    removal = client.delete(f"{MEALS}/{record['id']}/dishes/{dish['id']}")
    assert removal.status_code == 409 and "cancelling that delivery" in removal.json()["detail"]
    ok(client.put(f"{MEALS}/{record['id']}/dishes/{dish['id']}/remarks", json={"remarks": "Arrived 7:10"}))
    assert client.put(f"{MEALS}/{record['id']}/dishes/{dish['id']}/distribution", json={
        "distributed_quantity": "90", "remaining_quantity": "5", "leftovers": []}).status_code == 422
    ok(set_counts(client, record))
    record = ok(distribute(client, record, dish, "92", "8", [("RETAINED", "3", "Kept for dinner"),
                                                             ("WASTED", "5", "Cold")]))
    closed = ok(client.post(f"{MEALS}/{record['id']}/close"))
    assert closed["status"] == "CLOSED"


def test_a_closed_record_is_never_changed_and_shows_reconciliation_pending(client, db, out):
    a = out.a
    act_as(client, a.admin)
    record = created(client, a, session=a.breakfast)
    record = ok(add_dish(client, record, "Upma", "20", a.kg), 201)
    ok(set_counts(client, record))
    ok(distribute(client, record, dish_named(record, "Upma"), "20", "0"))
    closed = ok(client.post(f"{MEALS}/{record['id']}/close"))
    before = db.query(MealDish).filter_by(meal_record_id=record["id"]).count()

    order = placed(client, a)
    after, _d = deliver(client, order, [(a.idli, "80", "0", None)])
    link = after["deliveries"][0]["lines"][0]["meal_link"]
    assert link["state"] == "PENDING_CLOSED" and "Reconciliation pending" in link["message"]
    assert after["meal_link_state"] == "PENDING_CLOSED"
    db.expire_all()
    assert db.query(MealDish).filter_by(meal_record_id=record["id"]).count() == before
    still = ok(client.get(f"{MEALS}/{record['id']}"))
    assert still["status"] == "CLOSED" and still["closed_at"] == closed["closed_at"]
    assert [p["item_name"] for p in still["outsourced_pending"]] == ["Idli set"]

    reopened = ok(client.post(f"{MEALS}/{record['id']}/reopen", json={"reason": "Outsourced idli arrived late"}))
    assert dish_named(reopened, "Idli set")["received_quantity"] == "80.000"
    assert reopened["outsourced_pending"] == []
    assert ok(client.get(f"{ORDERS}/{order['id']}"))["meal_link_state"] == "ADDED"


def test_cancelling_a_meal_record_releases_received_food_to_the_next_record(client, db, out):
    a = out.a
    act_as(client, a.admin)
    wrong = created(client, a, session=a.breakfast)
    order = placed(client, a)
    deliver(client, order, [(a.idli, "30", "0", None)])
    cancelled = ok(client.post(f"{MEALS}/{wrong['id']}/cancel", json={"reason": "Wrong counts"}))
    assert cancelled["dishes"] == []
    assert ok(client.get(f"{ORDERS}/{order['id']}"))["meal_link_state"] == "PENDING_NO_RECORD"
    right = created(client, a, session=a.breakfast)
    assert dish_named(right, "Idli set")["received_quantity"] == "30.000"
    assert "RECEIVED_RELEASED" in audit_actions(db, "MEAL_RECORD", wrong["id"])


# ============================================================
# CANCELLING DELIVERIES AND ORDERS
# ============================================================

def test_cancelling_a_confirmed_delivery_is_blocked_once_food_is_distributed(client, db, out):
    a = out.a
    act_as(client, a.admin)
    record = created(client, a, session=a.breakfast)
    order = placed(client, a)
    after, delivery = deliver(client, order, [(a.idli, "100", "0", None)])
    record = ok(client.get(f"{MEALS}/{record['id']}"))
    dish = dish_named(record, "Idli set")
    ok(distribute(client, record, dish, "100", "0"))

    refused = client.post(f"{DELIVERIES}/{delivery['id']}/cancel", json={"reason": "Supplier error"})
    assert refused.status_code == 409
    assert "already has its distribution recorded" in refused.json()["detail"]
    assert "cannot be un-delivered" in refused.json()["detail"]
    order_refused = client.post(f"{ORDERS}/{order['id']}/cancel", json={"reason": "Supplier error"})
    assert order_refused.status_code == 409 and "Cancel those deliveries first" in order_refused.json()["detail"]

    ok(client.delete(f"{MEALS}/{record['id']}/dishes/{dish['id']}/distribution"))
    done = ok(client.post(f"{DELIVERIES}/{delivery['id']}/cancel", json={"reason": "Supplier error"}))
    assert done["deliveries"][0]["status"] == "CANCELLED"
    assert all(d["dish_name"] != "Idli set" for d in ok(client.get(f"{MEALS}/{record['id']}"))["dishes"])
    assert line_for(done, a.idli)["accepted_quantity"] == "0.000"
    assert "REMOVE_RECEIVED" in audit_actions(db, "MEAL_RECORD", record["id"])
    ok(client.post(f"{ORDERS}/{order['id']}/cancel", json={"reason": "Supplier error"}))


def test_cancelling_a_delivery_on_a_closed_record_is_refused(client, db, out):
    a = out.a
    act_as(client, a.admin)
    record = created(client, a, session=a.breakfast)
    order = placed(client, a)
    _after, delivery = deliver(client, order, [(a.idli, "10", "0", None)])
    record = ok(client.get(f"{MEALS}/{record['id']}"))
    ok(set_counts(client, record))
    ok(distribute(client, record, dish_named(record, "Idli set"), "10", "0"))
    ok(client.post(f"{MEALS}/{record['id']}/close"))
    refused = client.post(f"{DELIVERIES}/{delivery['id']}/cancel", json={"reason": "Wrong"})
    assert refused.status_code == 409 and "closed meal record" in refused.json()["detail"]


def test_draft_deliveries_are_cancelled_by_update_holders(client, db, out):
    a = out.a
    act_as(client, a.admin)
    order = placed(client, a)
    _after, delivery = deliver(client, order, [(a.idli, "10", "0", None)], confirm=False)
    for code in ("outsourced_food.read", "outsourced_food.update"):
        grant(db, a.staff, a.admin, code)
    act_as(client, a.staff)
    done = ok(client.post(f"{DELIVERIES}/{delivery['id']}/cancel", json={"reason": "Entered twice"}))
    assert done["deliveries"][0]["status"] == "CANCELLED"
    assert client.post(f"{DELIVERIES}/{delivery['id']}/cancel", json={"reason": "Again"}).status_code == 409


# ============================================================
# NO RAW STOCK EFFECT (OUT01 criterion 7, P8-2)
# ============================================================

def test_the_whole_outsourced_workflow_writes_no_stock_or_purchasing_row(client, db, out):
    a = out.a
    act_as(client, a.admin)
    bill, bill_line = make_bill(db, a, a.idli, "100", "35")
    before = stock_fingerprint(db)
    record = created(client, a, session=a.breakfast)
    order = placed(client, a)
    ok(client.put(f"{LINES}/{line_for(order, a.idli)['id']}/bill-line", json={"purchase_item_id": bill_line.id}))
    _after, delivery = deliver(client, order, [(a.idli, "100", "6", "Cold")])
    record = ok(client.get(f"{MEALS}/{record['id']}"))
    ok(set_counts(client, record))
    ok(distribute(client, record, dish_named(record, "Idli set"), "90", "4", [("WASTED", "4", "Cold")]))
    ok(client.post(f"{MEALS}/{record['id']}/close"))
    ok(client.get(f"{REPORT}?date_from={today()}&date_to={today()}"))
    assert stock_fingerprint(db) == before
    assert db.query(StockMovement).filter_by(item_id=a.idli.id).count() == 0


def test_stock_screens_refuse_outsourced_items(client, db, out):
    a = out.a
    act_as(client, a.admin)
    issue = new_issue(client, a, [(a.idli, "5", None)])
    assert issue.status_code == 422 and "outsourced food" in issue.json()["detail"]
    assert a.idli.id not in [i["id"] for i in ok(client.get("/api/kitchen-issues/options"))["items"]]
    opening = client.post("/api/stock/openings", json={"effective_date": today(),
                                                       "lines": [{"item_id": a.idli.id, "quantity": "5"}]})
    assert opening.status_code == 422 and "outsourced food" in opening.json()["detail"]
    count = client.post("/api/stock-counts", json={"reason": "Monthly count", "lines": [
        {"item_id": a.idli.id, "quantity": "5"}]})
    assert count.status_code == 422 and "outsourced food" in count.text
    assert a.idli.id not in [i["id"] for i in ok(client.get("/api/stock-counts/options"))["items"]]
    assert db.query(StockMovement).filter_by(item_id=a.idli.id).count() == 0


def test_goods_receipts_refuse_outsourced_bill_lines(client, db, out):
    a = out.a
    act_as(client, a.admin)
    bill, bill_line = make_bill(db, a, a.idli, "100", "35")
    receivable = ok(client.get("/api/receipts/receivable-bills"))
    assert bill.id not in [b["purchase_id"] for b in receivable["items"]]
    receiving = ok(client.get(f"/api/purchases/{bill.id}/receiving"))
    assert receiving["lines"] == [] and receiving["outsourced_lines"][0]["item_name"] == "Idli set"
    refused = client.post(f"/api/purchases/{bill.id}/receipts", json={"items": [
        {"purchase_item_id": bill_line.id, "quantity_received": "100", "quantity_accepted": "100"}]})
    assert refused.status_code == 422 and "outsourced food" in refused.json()["detail"]
    assert db.query(GoodsReceipt).count() == 0


def test_a_draft_receipt_cannot_be_accepted_after_the_item_becomes_outsourced(client, db, out):
    a = out.a
    act_as(client, a.admin)
    bill, bill_line = make_bill(db, a, a.dal, "10", "90", supplier=a.supplier, unit=a.kg, invoice="INV-DAL")
    receipt = ok(client.post(f"/api/purchases/{bill.id}/receipts", json={"items": [
        {"purchase_item_id": bill_line.id, "quantity_received": "10", "quantity_accepted": "10"}]}), 201)
    # The kind change itself is refused while the draft exists (P8-5) ...
    refused = client.put(f"/api/items/{a.dal.id}/kind", json={"item_kind": "OUTSOURCED"})
    assert refused.status_code == 409 and "draft goods receipt" in refused.json()["detail"]
    # ... and acceptance re-checks the kind with the item row locked.
    a.dal.item_kind = "OUTSOURCED"
    db.commit()
    accepted = client.post(f"/api/receipts/{receipt['id']}/accept")
    assert accepted.status_code == 422 and "outsourced food" in accepted.json()["detail"]
    assert db.query(StockMovement).filter_by(item_id=a.dal.id).count() == 0


def test_the_stock_ledger_refuses_any_outsourced_posting(db, out):
    a = out.a
    posting = stock_ledger.Posting(item_id=a.idli.id, movement_type="OPENING", direction=1, quantity=Decimal("1"),
                                   unit_id=a.plate.id, effective_at=stock_ledger.start_of_campus_day(campus_today()),
                                   source_key="TEST:1", reference_type="TEST", reference_id=1)
    with pytest.raises(Exception) as error:
        stock_ledger.post(db, a.admin, [posting])
    assert "outsourced food" in str(getattr(error.value, "detail", error.value))
    db.rollback()


# ============================================================
# ITEM CLASSIFICATION (P8-5)
# ============================================================

def test_an_item_with_stock_movements_cannot_become_outsourced(client, db, out):
    a = out.a
    act_as(client, a.admin)
    refused = client.put(f"/api/items/{a.item.id}/kind", json={"item_kind": "OUTSOURCED"})
    assert refused.status_code == 409 and "stock movements" in refused.json()["detail"]
    assert db.get(Item, a.item.id).item_kind != "OUTSOURCED"
    # Toor Dal has no movement: it can be classified (and back, while unused).
    assert ok(client.put(f"/api/items/{a.dal.id}/kind", json={"item_kind": "OUTSOURCED"}))["item_kind"] == "OUTSOURCED"
    assert ok(client.put(f"/api/items/{a.dal.id}/kind", json={"item_kind": "RAW"}))["item_kind"] == "RAW"


def test_an_item_on_outsourced_orders_stays_outsourced(client, db, out):
    a = out.a
    act_as(client, a.admin)
    ok(client.post(ORDERS, json=order_body(a)), 201)
    refused = client.put(f"/api/items/{a.idli.id}/kind", json={"item_kind": "PREPARED"})
    assert refused.status_code == 409 and "outsourced orders" in refused.json()["detail"]


# ============================================================
# SUPPLIER BILL LINKS (OUT01 criterion 6)
# ============================================================

def test_bill_lines_link_once_with_matching_supplier_item_and_unit(client, db, out):
    a = out.a
    act_as(client, a.admin)
    order = placed(client, a, lines=[(a.idli, "100", "35"), (a.meals, "40", "80")])
    idli_line, meals_line = line_for(order, a.idli), line_for(order, a.meals)
    _b1, good = make_bill(db, a, a.idli, "100", "36")
    _b2, wrong_supplier = make_bill(db, a, a.idli, "100", "36", supplier=a.hotel, invoice="INV-H")
    _b3, wrong_unit = make_bill(db, a, a.meals, "4", "800", unit=a.kg, invoice="INV-KG")

    candidates = ok(client.get(f"{LINES}/{idli_line['id']}/bill-candidates"))["items"]
    assert [c["purchase_item_id"] for c in candidates] == [good.id]
    assert client.put(f"{LINES}/{idli_line['id']}/bill-line",
                      json={"purchase_item_id": wrong_supplier.id}).status_code == 422
    unit_refused = client.put(f"{LINES}/{meals_line['id']}/bill-line", json={"purchase_item_id": wrong_unit.id})
    assert unit_refused.status_code == 422 and "no conversion is assumed" in unit_refused.json()["detail"]
    assert client.put(f"{LINES}/{meals_line['id']}/bill-line", json={"purchase_item_id": good.id}).status_code == 422

    linked = ok(client.put(f"{LINES}/{idli_line['id']}/bill-line", json={"purchase_item_id": good.id}))
    assert line_for(linked, a.idli)["bill_line"]["invoice_number"] == "INV-OUT-1"
    assert linked["billed_total"] == "3600.00" and linked["planned_total"] == "6700.00"
    second = order_body(a)
    other = ok(client.post(ORDERS, json=second), 201)
    ok(client.post(f"{ORDERS}/{other['id']}/place"))
    taken = client.put(f"{LINES}/{line_for(other, a.idli)['id']}/bill-line", json={"purchase_item_id": good.id})
    assert taken.status_code in (409, 422)
    links = ok(client.get(f"/api/purchases/{_b1.id}/outsourced-links"))["items"]
    assert links[0]["order_number"] == order["order_number"]
    assert client.post(f"{ORDERS}/{order['id']}/cancel", json={"reason": "x" * 5}).status_code == 409
    unlinked = ok(client.delete(f"{LINES}/{idli_line['id']}/bill-line"))
    assert line_for(unlinked, a.idli)["bill_line"] is None
    assert audit_actions(db, "OUTSOURCED_ORDER", order["id"])[-2:] == ["LINK_BILL", "UNLINK_BILL"]


def test_bill_links_need_bill_update(client, db, out):
    a = out.a
    act_as(client, a.admin)
    order = placed(client, a)
    _bill, bill_line = make_bill(db, a, a.idli, "100", "35")
    for code in ("outsourced_food.read", "purchase_bill.read"):
        grant(db, a.staff, a.admin, code)
    act_as(client, a.staff)
    assert client.put(f"{LINES}/{order['lines'][0]['id']}/bill-line",
                      json={"purchase_item_id": bill_line.id}).status_code == 403
    grant(db, a.staff, a.admin, "purchase_bill.update")
    ok(client.put(f"{LINES}/{order['lines'][0]['id']}/bill-line", json={"purchase_item_id": bill_line.id}))


# ============================================================
# REPORT (OUT02, AT04)
# ============================================================

def at04_breakfast(client, db, a):
    """AT04: outsourced breakfast ordered, billed, delivered with a rejection,
    distributed with leftovers; reconciles."""
    record = created(client, a, session=a.breakfast)
    order = placed(client, a, lines=[(a.idli, "100", "35"), (a.meals, "40", "80")])
    _bill, bill_line = make_bill(db, a, a.idli, "100", "35.50")
    ok(client.put(f"{LINES}/{line_for(order, a.idli)['id']}/bill-line", json={"purchase_item_id": bill_line.id}))
    deliver(client, order, [(a.idli, "100", "6", "Six plates cold")])
    record = ok(client.get(f"{MEALS}/{record['id']}"))
    ok(set_counts(client, record))
    ok(distribute(client, record, dish_named(record, "Idli set"), "85", "9",
                  [("RETAINED", "4", "Kept for snacks"), ("RETURNED_TO_SUPPLIER", "2", "Sent back"),
                   ("WASTED", "3", "Plate waste")]))
    return order, record


def test_report_reconciles_quantities_and_shows_linked_cost(client, db, out):
    a = out.a
    act_as(client, a.admin)
    order, _record = at04_breakfast(client, db, a)
    report = ok(client.get(f"{REPORT}?date_from={today()}&date_to={today()}"))
    idli = next(r for r in report["lines"] if r["item_name"] == "Idli set")
    assert (idli["ordered_quantity"], idli["received_quantity"], idli["rejected_quantity"],
            idli["accepted_quantity"], idli["added_quantity"], idli["distributed_quantity"],
            idli["remaining_quantity"]) == ("100.000", "100.000", "6.000", "94.000", "94.000", "85.000", "9.000")
    assert (idli["retained_quantity"], idli["returned_to_supplier_quantity"], idli["wasted_quantity"],
            idli["disposed_quantity"]) == ("4.000", "2.000", "3.000", "0.000")
    assert idli["status"] == "RECONCILED" and idli["meal_session_name"] == "Breakfast"
    assert idli["billed_cost"] == "3550.00" and idli["planned_cost"] == "3500.00"
    meals = next(r for r in report["lines"] if r["item_name"] == "Veg Meals")
    assert meals["status"] == "NOT_DELIVERED" and meals["billed_cost"] is None
    # Expenditure comes from bill lines only; the planned cost is separate.
    assert report["cost_totals"] == {"planned_cost": "6700.00", "billed_cost": "3550.00", "lines_without_bill": 1}
    plate = report["totals_by_unit"][0]
    assert plate["unit_symbol"] == "plate" and plate["ordered_quantity"] == "140.000"
    assert report["rejected_note"].startswith("Credit not recorded")
    assert report["unreconciled_count"] == 1
    filtered = ok(client.get(f"{REPORT}?date_from={today()}&date_to={today()}&item_id={a.meals.id}"))
    assert [r["item_name"] for r in filtered["lines"]] == ["Veg Meals"]
    other_session = ok(client.get(f"{REPORT}?date_from={today()}&date_to={today()}"
                                  f"&meal_session_id={a.breakfast_dup.id}"))
    assert other_session["lines"] == []
    assert client.get(f"{REPORT}?date_from={today()}&date_to={today(-1)}").status_code == 422


def test_report_hides_costs_without_bill_read_and_exports(client, db, out):
    a = out.a
    act_as(client, a.admin)
    at04_breakfast(client, db, a)
    grant(db, a.staff, a.admin, "outsourced_food.read")
    act_as(client, a.staff)
    report = ok(client.get(f"{REPORT}?date_from={today()}&date_to={today()}"))
    assert not report["costs_visible"] and "cost_totals" not in report
    assert all(f not in report["lines"][0] for f in COST_FIELDS) and "planned_cost" not in report["by_item"][0]
    for fmt, magic in (("xlsx", b"PK"), ("pdf", b"%PDF")):
        response = client.post(f"{REPORT}/export", json={"format": fmt, "date_from": today(), "date_to": today()})
        assert response.status_code == 200, response.text
        assert response.content.startswith(magic)
        assert f"outsourced-food_{today()}_{today()}.{fmt}" in response.headers["content-disposition"]
    sheet = zipfile.ZipFile(io.BytesIO(client.post(f"{REPORT}/export", json={
        "format": "xlsx", "date_from": today(), "date_to": today()}).content))
    strings = sheet.read("xl/sharedStrings.xml").decode()
    assert "Idli set" in strings and "Billed cost" not in strings and "Planned cost" not in strings
    exports = db.query(AuditLog).filter_by(entity_type="OUTSOURCED_REPORT", action="EXPORT").all()
    assert len(exports) == 3 and all(e.details["costs_included"] is False for e in exports)
    act_as(client, a.admin)
    full = zipfile.ZipFile(io.BytesIO(client.post(f"{REPORT}/export", json={
        "format": "xlsx", "date_from": today(), "date_to": today()}).content))
    assert "Billed cost" in full.read("xl/sharedStrings.xml").decode()


def test_list_filters_and_status_counts(client, db, out):
    a = out.a
    act_as(client, a.admin)
    placed(client, a)
    ok(client.post(ORDERS, json=order_body(a, lines=[(a.meals, "10", "80")], supplier=a.hotel, day=today(2))), 201)
    listing = ok(client.get(ORDERS))
    assert listing["status_counts"] == {"DRAFT": 1, "ORDERED": 1, "CANCELLED": 0}
    assert [o["meal_date"] for o in listing["items"]] == [today(2), today()]
    assert ok(client.get(f"{ORDERS}?supplier_id={a.hotel.id}"))["total"] == 1
    assert ok(client.get(f"{ORDERS}?item_id={a.idli.id}"))["items"][0]["item_names"] == ["Idli set"]
    assert ok(client.get(f"{ORDERS}?status=DRAFT"))["items"][0]["supplier_name"] == "Hotel Saravana"
    assert ok(client.get(f"{ORDERS}?date_from={today(1)}"))["total"] == 1
    assert ok(client.get(f"{ORDERS}?search=oo-00002"))["total"] == 1


# ============================================================
# PLANNED VS ACTUAL (PLAN08, received side)
# ============================================================

def test_planned_vs_actual_shows_received_outsourced_food(client, db, out):
    """PLAN08 criterion 3: the meal record's planning panel compares the plan
    with prepared and received food; received outsourced food is listed as
    its own kind with the received quantity (outsourced items stay
    unplannable, P8-6 deferred)."""
    from tests.test_planning import approved, new_plan

    a = out.a
    act_as(client, a.manager)
    a.item.item_kind = "RAW"
    db.commit()
    approved(client, a.item, "150", a.g, a.biryani)
    plan = ok(new_plan(client, a, [a.item], headcount=100), 201)
    ok(client.post(f"/api/meal-plans/{plan['id']}/approve"))
    order = placed(client, a, session=a.lunch)
    deliver(client, order, [(a.idli, "100", "0", None)])
    record = created(client, a, session=a.lunch)
    dishes = record["planning"]["comparison"]["dishes"]
    received = next(d for d in dishes if d["dish_name"] == "Idli set")
    assert received["kind"] == "RECEIVED" and received["received_quantity"] == "100.000"
    assert received["prepared_quantity"] == "0.000" and received["unit_symbol"] == "plate"
    refused = client.post("/api/portion-standards", json={"menu_id": a.biryani.id, "item_id": a.idli.id,
                                                          "quantity_per_person": "1", "unit_id": a.plate.id,
                                                          "effective_from": today()})
    assert refused.status_code == 422 and "outsourced" in refused.text.lower()
