"""
Stage 3 — genuine purchase orders, and the split of supplier-bill access
into purchase_bill.* (decisions of 18 November 2026).

In-memory SQLite with the shared fixtures of test_operational_authority.
Concurrency and the migration are covered on PostgreSQL elsewhere.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.api.routes import purchase_orders as orders_module
from app.models import AuditLog, Item, StaffAccessAssignment, Supplier, Unit, UnitConversion
from app.models.purchases import Purchase, PurchaseOrder

from tests.test_operational_authority import (  # noqa: F401 (fixtures)
    act_as,
    client,
    db,
    grant,
    world,
)

ORDERS = "/api/purchase-orders"
BILLS = "/api/purchases/"


@pytest.fixture
def stock(db, world):
    """Grams (with an explicit kg→g conversion) and a second item, Dal,
    whose standard unit is kg."""
    a = world.a
    gram = Unit(campus_id=a.campus.id, name="Gram", symbol="g", dimension="weight")
    litre = Unit(campus_id=a.campus.id, name="Litre", symbol="L", dimension="volume")
    db.add_all([gram, litre])
    db.flush()
    db.add(UnitConversion(campus_id=a.campus.id, from_unit_id=a.kg.id,
                          to_unit_id=gram.id, factor=Decimal("1000")))
    dal = Item(campus_id=a.campus.id, name="Toor Dal", category_id=a.category.id,
               standard_unit_id=a.kg.id, minimum_stock=0)
    db.add(dal)
    db.commit()
    return {"gram": gram, "litre": litre, "dal": dal}


def order_body(place, lines, supplier=None, order_date="2026-11-10", **extra):
    return {
        "supplier_id": (supplier or place.supplier).id,
        "order_date": order_date,
        "items": [{"item_id": item.id, "quantity": qty, "unit_id": unit.id}
                  for item, qty, unit in lines],
        **extra,
    }


def make_order(client, place, lines, **extra):
    response = client.post(ORDERS, json=order_body(place, lines, **extra))
    assert response.status_code == 201, response.text
    return response.json()


def placed_order(client, world, stock):
    order = make_order(client, world.a, [(world.a.item, "50", world.a.kg),
                                         (stock["dal"], "5000", stock["gram"])])
    placed = client.post(f"{ORDERS}/{order['id']}/place")
    assert placed.status_code == 200, placed.text
    return placed.json()


def bill_against(client, place, order, lines, invoice="INV-PO-1", **extra):
    """lines: (item, quantity, unit, order_line_id or None)."""
    return client.post(BILLS, json={
        "supplier_id": place.supplier.id, "invoice_number": invoice,
        "purchase_date": "2026-11-12", "purchase_order_id": order["id"] if order else None,
        "items": [{"item_id": item.id, "quantity": qty, "unit_id": unit.id,
                   "unit_rate": "10.00", "purchase_order_item_id": link}
                  for item, qty, unit, link in lines],
        **extra,
    })


def line_of(order, name):
    return next(line for line in order["items"] if line["item_name"] == name)


# ============================================================
# CREATING, NUMBERING AND EDITING
# ============================================================

def test_orders_are_numbered_per_campus_and_start_as_drafts(client, world, stock):
    act_as(client, world.a.admin)
    first = make_order(client, world.a, [(world.a.item, "50", world.a.kg)])
    second = make_order(client, world.a, [(stock["dal"], "2", world.a.kg)])
    act_as(client, world.b.admin)
    other = make_order(client, world.b, [(world.b.item, "1", world.b.kg)])

    assert (first["order_number"], second["order_number"], other["order_number"]) == (
        "PO-00001", "PO-00002", "PO-00001")
    assert first["status"] == "DRAFT" and first["actions"]["edit"] and not first["actions"]["bill"]
    assert first["items"][0]["ordered_quantity"] == "50.000"
    assert first["items"][0]["unit_symbol"] == "kg"


@pytest.mark.parametrize("change, expected", [
    ({"order_date": "2099-01-01"}, "future"),
    ({"expected_date": "2026-11-01"}, "before the order date"),
])
def test_order_dates_are_checked(client, world, monkeypatch, change, expected):
    monkeypatch.setattr(orders_module, "campus_today", lambda: date(2026, 11, 18))
    act_as(client, world.a.admin)
    response = client.post(ORDERS, json={**order_body(world.a, [(world.a.item, "1", world.a.kg)]), **change})
    assert response.status_code == 422 and expected in response.json()["detail"]


def test_order_lines_follow_the_item_and_unit_rules(client, db, world, stock):
    act_as(client, world.a.admin)
    rice, kg = world.a.item, world.a.kg

    twice = client.post(ORDERS, json=order_body(world.a, [(rice, "1", kg), (rice, "2", kg)]))
    assert twice.status_code == 422 and "only once" in twice.json()["detail"]
    wrong_dimension = client.post(ORDERS, json=order_body(world.a, [(rice, "1", stock["litre"])]))
    assert wrong_dimension.status_code == 422 and "dimension" in wrong_dimension.json()["detail"]
    zero = client.post(ORDERS, json=order_body(world.a, [(rice, "0", kg)]))
    assert zero.status_code == 422
    other_campus_item = client.post(ORDERS, json=order_body(world.a, [(world.b.item, "1", kg)]))
    assert other_campus_item.status_code == 404
    other_supplier = client.post(ORDERS, json=order_body(world.a, [(rice, "1", kg)], supplier=world.b.supplier))
    assert other_supplier.status_code == 404

    db.query(Supplier).filter_by(id=world.a.supplier.id).update({"is_active": False})
    db.commit()
    inactive = client.post(ORDERS, json=order_body(world.a, [(rice, "1", kg)]))
    assert inactive.status_code == 404


def test_only_drafts_are_edited_and_edits_are_audited(client, db, world, stock):
    act_as(client, world.a.admin)
    order = make_order(client, world.a, [(world.a.item, "50", world.a.kg)])

    edited = client.put(f"{ORDERS}/{order['id']}", json=order_body(
        world.a, [(stock["dal"], "5000", stock["gram"])], expected_date="2026-11-15", remarks="Revised"))
    assert edited.status_code == 200, edited.text
    body = edited.json()
    assert [(l["item_name"], l["ordered_quantity"], l["unit_symbol"]) for l in body["items"]] == [
        ("Toor Dal", "5000.000", "g")]
    assert (body["expected_date"], body["remarks"]) == ("2026-11-15", "Revised")

    audit = db.query(AuditLog).filter_by(entity_type="PURCHASE_ORDER", action="UPDATE").one()
    assert audit.details["before"]["lines"][0]["quantity"] == "50.000"
    assert audit.details["after"]["lines"][0]["quantity"] == "5000.000"

    assert client.post(f"{ORDERS}/{order['id']}/place").status_code == 200
    again = client.put(f"{ORDERS}/{order['id']}", json=order_body(world.a, [(world.a.item, "1", world.a.kg)]))
    assert again.status_code == 409


# ============================================================
# STATUSES
# ============================================================

def test_status_changes_and_history(client, db, world, stock):
    act_as(client, world.a.manager)
    order = placed_order(client, world, stock)
    assert order["status"] == "PLACED" and order["placed_by_name"] == world.a.manager.full_name
    assert order["actions"] == {"edit": False, "place": False, "close": True, "cancel": True, "bill": True}
    assert client.post(f"{ORDERS}/{order['id']}/place").status_code == 409

    assert client.post(f"{ORDERS}/{order['id']}/close", json={"reason": "  "}).status_code == 422
    closed = client.post(f"{ORDERS}/{order['id']}/close", json={"reason": "Supplier cannot deliver the rest"})
    assert closed.status_code == 200
    body = closed.json()
    assert (body["status"], body["close_reason"]) == ("CLOSED", "Supplier cannot deliver the rest")
    assert [h["action"] for h in body["history"]] == ["CREATE", "PLACE", "CLOSE"]
    assert body["history"][-1]["reason"] == "Supplier cannot deliver the rest"
    assert client.post(f"{ORDERS}/{order['id']}/cancel", json={"reason": "x"}).status_code == 409

    draft = make_order(client, world.a, [(world.a.item, "1", world.a.kg)])
    cancelled = client.post(f"{ORDERS}/{draft['id']}/cancel", json={"reason": "Ordered by mistake"})
    assert cancelled.json()["status"] == "CANCELLED"
    assert cancelled.json()["cancelled_by_name"] == world.a.manager.full_name


def test_placing_checks_the_lines_again(client, db, world, stock):
    act_as(client, world.a.admin)
    order = make_order(client, world.a, [(stock["dal"], "2", world.a.kg)])
    db.query(Item).filter_by(id=stock["dal"].id).update({"is_active": False})
    db.commit()

    refused = client.post(f"{ORDERS}/{order['id']}/place")

    assert refused.status_code == 404 and "Active item" in refused.json()["detail"]
    assert db.query(PurchaseOrder).filter_by(id=order["id"]).one().status == "DRAFT"


# ============================================================
# BILLS AGAINST ORDERS, AND RECEIVING PROGRESS
# ============================================================

def test_bills_link_to_order_lines_and_progress_is_in_the_order_unit(client, world, stock):
    act_as(client, world.a.admin)
    order = placed_order(client, world, stock)
    rice_line, dal_line = line_of(order, "Rice")["id"], line_of(order, "Toor Dal")["id"]

    bill = bill_against(client, world.a, order, [
        (world.a.item, "30", world.a.kg, rice_line),
        (stock["dal"], "2", world.a.kg, dal_line),       # billed in kg, ordered in g
    ])
    assert bill.status_code == 201, bill.text
    bill = bill.json()
    assert bill["purchase_order_number"] == "PO-00001"
    assert {l["purchase_order_item_id"] for l in bill["items"]} == {rice_line, dal_line}

    detail = client.get(f"{ORDERS}/{order['id']}").json()
    assert (line_of(detail, "Rice")["billed_quantity"], line_of(detail, "Rice")["left_to_bill"]) == ("30.000", "20.000")
    assert line_of(detail, "Toor Dal")["billed_quantity"] == "2000.000"
    assert detail["bills"] == [{"purchase_id": bill["id"], "invoice_number": "INV-PO-1",
                                "purchase_date": "2026-11-12"}]
    assert detail["receiving_state"] == "NOT_RECEIVED"

    receiving = client.get(f"{BILLS}{bill['id']}/receiving").json()
    assert receiving["purchase_order_number"] == "PO-00001"
    by_item = {l["item_name"]: l for l in receiving["lines"]}
    assert (by_item["Rice"]["ordered_quantity"], by_item["Rice"]["billed_quantity"]) == ("50.000", "30.000")
    assert by_item["Toor Dal"]["ordered_quantity"] == "5.000"          # 5000 g in the bill's kg

    lines = {l["item_name"]: l["purchase_item_id"] for l in receiving["lines"]}
    receipt = client.post(f"{BILLS}{bill['id']}/receipts", json={"receipt_date": "2026-11-12", "items": [
        {"purchase_item_id": lines["Rice"], "quantity_received": "30", "quantity_accepted": "28",
         "quantity_rejected": "2"},
        {"purchase_item_id": lines["Toor Dal"], "quantity_received": "1.5", "quantity_accepted": "1.5"},
    ]}).json()
    detail = client.get(f"{ORDERS}/{order['id']}").json()
    assert line_of(detail, "Toor Dal")["in_draft_quantity"] == "1500.000"

    assert client.post(f"/api/receipts/{receipt['id']}/accept").status_code == 200
    detail = client.get(f"{ORDERS}/{order['id']}").json()
    rice = line_of(detail, "Rice")
    assert (rice["received_quantity"], rice["accepted_quantity"], rice["rejected_quantity"],
            rice["left_to_receive"]) == ("30.000", "28.000", "2.000", "20.000")
    assert line_of(detail, "Toor Dal")["received_quantity"] == "1500.000"
    assert detail["receiving_state"] == "PARTLY_RECEIVED"
    assert detail["actions"]["cancel"] is False                      # billed: close, not cancel


def test_billing_more_than_ordered_is_recorded_and_flagged(client, world, stock):
    act_as(client, world.a.admin)
    order = placed_order(client, world, stock)
    rice_line = line_of(order, "Rice")["id"]

    bill = bill_against(client, world.a, order, [(world.a.item, "52", world.a.kg, rice_line)])

    assert bill.status_code == 201, bill.text
    detail = client.get(f"{ORDERS}/{order['id']}").json()
    rice = line_of(detail, "Rice")
    assert (rice["billed_quantity"], rice["left_to_bill"], rice["over_billed"]) == ("52.000", "0.000", "2.000")
    assert detail["over_billed"] is True


@pytest.mark.parametrize("case", [
    "draft_order", "cancelled_order", "other_supplier", "item_mismatch",
    "line_of_another_order", "same_line_twice", "link_without_order",
])
def test_bill_links_are_validated(client, db, world, stock, case):
    act_as(client, world.a.admin)
    order = placed_order(client, world, stock)
    rice_line = line_of(order, "Rice")["id"]
    rice, kg = world.a.item, world.a.kg
    bills_before = db.query(Purchase).count()

    if case == "draft_order":
        draft = make_order(client, world.a, [(rice, "1", kg)])
        response = bill_against(client, world.a, draft, [(rice, "1", kg, draft["items"][0]["id"])])
    elif case == "cancelled_order":
        other = placed_order(client, world, stock)
        client.post(f"{ORDERS}/{other['id']}/cancel", json={"reason": "x"})
        response = bill_against(client, world.a, other, [(rice, "1", kg, line_of(other, "Rice")["id"])])
    elif case == "other_supplier":
        supplier = Supplier(campus_id=world.a.campus.id, name="Second Supplier")
        db.add(supplier)
        db.commit()
        response = client.post(BILLS, json={
            "supplier_id": supplier.id, "invoice_number": "X-1", "purchase_date": "2026-11-12",
            "purchase_order_id": order["id"],
            "items": [{"item_id": rice.id, "quantity": "1", "unit_id": kg.id, "unit_rate": "1"}]})
    elif case == "item_mismatch":
        response = bill_against(client, world.a, order, [(stock["dal"], "1", kg, rice_line)])
    elif case == "line_of_another_order":
        other = placed_order(client, world, stock)
        response = bill_against(client, world.a, order, [(rice, "1", kg, line_of(other, "Rice")["id"])])
    elif case == "same_line_twice":
        response = bill_against(client, world.a, order, [(rice, "1", kg, rice_line), (rice, "2", kg, rice_line)])
    else:
        response = bill_against(client, world.a, None, [(rice, "1", kg, rice_line)])

    assert response.status_code == 422, (case, response.text)
    assert db.query(Purchase).count() == bills_before


def test_an_order_with_bills_is_closed_not_cancelled(client, world, stock):
    act_as(client, world.a.admin)
    order = placed_order(client, world, stock)
    bill_against(client, world.a, order, [(world.a.item, "10", world.a.kg, line_of(order, "Rice")["id"])])

    refused = client.post(f"{ORDERS}/{order['id']}/cancel", json={"reason": "No longer needed"})

    assert refused.status_code == 409 and "close it instead" in refused.json()["detail"]
    assert client.post(f"{ORDERS}/{order['id']}/close", json={"reason": "Rest not needed"}).status_code == 200


def test_bill_entry_lists_placed_orders_of_the_supplier(client, world, stock):
    act_as(client, world.a.admin)
    make_order(client, world.a, [(world.a.item, "1", world.a.kg)])                 # draft: not listed
    order = placed_order(client, world, stock)
    bill_against(client, world.a, order, [(world.a.item, "20", world.a.kg, line_of(order, "Rice")["id"])])

    listed = client.get(f"{ORDERS}/billable", params={"supplier_id": world.a.supplier.id}).json()["items"]

    assert [o["order_number"] for o in listed] == [order["order_number"]]
    rice = next(l for l in listed[0]["items"] if l["item_name"] == "Rice")
    assert (rice["ordered_quantity"], rice["billed_quantity"], rice["left_to_bill"]) == ("50.000", "20.000", "30.000")
    assert "price" not in str(listed) and "rate" not in str(listed)


def test_bills_without_an_order_are_unchanged(client, world):
    act_as(client, world.a.admin)
    bill = bill_against(client, world.a, None, [(world.a.item, "3", world.a.kg, None)], invoice="PLAIN-1")

    assert bill.status_code == 201
    assert bill.json()["purchase_order_id"] is None
    assert bill.json()["items"][0]["purchase_order_item_id"] is None


# ============================================================
# LIST
# ============================================================

def test_order_list_filters_counts_and_pages(client, world, stock):
    act_as(client, world.a.admin)
    for n in range(1, 4):
        make_order(client, world.a, [(world.a.item, str(n), world.a.kg)], order_date=f"2026-11-0{n}")
    placed = placed_order(client, world, stock)

    page = client.get(ORDERS, params={"page_size": 2}).json()
    assert (page["total"], page["total_pages"], len(page["items"])) == (4, 2, 2)
    assert page["items"][0]["order_number"] == placed["order_number"]      # newest first
    assert page["status_counts"] == {"DRAFT": 3, "PLACED": 1, "CLOSED": 0, "CANCELLED": 0}
    assert client.get(ORDERS, params={"status": "PLACED"}).json()["total"] == 1
    assert client.get(ORDERS, params={"search": "po-00002"}).json()["total"] == 1
    assert client.get(ORDERS, params={"search": "supplier a"}).json()["total"] == 4
    assert client.get(ORDERS, params={"search": "%"}).json()["total"] == 0
    assert client.get(ORDERS, params={"date_to": "2026-11-02"}).json()["total"] == 2
    assert client.get(ORDERS, params={"status": "APPROVED"}).status_code == 422


# ============================================================
# PERMISSIONS: purchase_order.* for orders, purchase_bill.* for bills
# ============================================================

ORDER_CODES = ("purchase_order.create", "purchase_order.read", "purchase_order.update")
BILL_CODES = ("purchase_bill.create", "purchase_bill.read", "purchase_bill.update")


def order_operations(client, place, order_id, draft_id):
    """Every purchase-order operation, as (name, response)."""
    rice, kg = place.item, place.kg
    return [
        ("list", client.get(ORDERS)),
        ("detail", client.get(f"{ORDERS}/{order_id}")),
        ("billable", client.get(f"{ORDERS}/billable", params={"supplier_id": place.supplier.id})),
        ("create", client.post(ORDERS, json=order_body(place, [(rice, "1", kg)]))),
        ("edit", client.put(f"{ORDERS}/{draft_id}", json=order_body(place, [(rice, "2", kg)]))),
        ("place", client.post(f"{ORDERS}/{draft_id}/place")),
        ("close", client.post(f"{ORDERS}/{order_id}/close", json={"reason": "check"})),
        ("cancel", client.post(f"{ORDERS}/{draft_id}/cancel", json={"reason": "check"})),
    ]


def staff_grants(db, staff):
    db.expire_all()
    return sorted(
        (row.permission_id, row.is_active, row.assigned_by)
        for row in db.query(StaffAccessAssignment).filter_by(staff_user_id=staff.id)
    )


def test_staff_never_reach_purchase_orders_even_with_older_grants(client, db, world, stock):
    """STAFF user #3 in the development database holds all three
    purchase_order.* grants (kept by migration a3c9e1f47b20) plus their
    purchase_bill.* copies. Purchase orders stay ADMIN and KITCHEN_MANAGER
    work: every order operation is refused, the grant rows are left
    untouched, and bill access is unaffected."""
    act_as(client, world.a.admin)
    order = placed_order(client, world, stock)
    draft = make_order(client, world.a, [(world.a.item, "1", world.a.kg)])
    for code in ORDER_CODES + BILL_CODES:
        grant(db, world.a.staff, world.a.admin, code)
    before = staff_grants(db, world.a.staff)

    act_as(client, world.a.staff)
    refused = {name: response.status_code
               for name, response in order_operations(client, world.a, order["id"], draft["id"])}

    assert refused == {name: 403 for name in refused}, refused
    assert staff_grants(db, world.a.staff) == before                  # history kept
    assert db.query(PurchaseOrder).count() == 2                       # nothing created
    me = client.get("/api/authorization/me").json()["permissions"]
    assert not set(ORDER_CODES) & set(me) and set(BILL_CODES) <= set(me)

    # Bills still work, but not against an order.
    plain = bill_against(client, world.a, None, [(world.a.item, "2", world.a.kg, None)], invoice="STAFF-1")
    assert plain.status_code == 201, plain.text
    linked = bill_against(client, world.a, order, [(world.a.item, "2", world.a.kg, line_of(order, "Rice")["id"])],
                          invoice="STAFF-2")
    assert linked.status_code == 403


def test_staff_detail_marks_kept_order_grants_as_not_effective(client, db, world):
    for code in ("purchase_order.read", "purchase_bill.read"):
        grant(db, world.a.staff, world.a.admin, code)
    act_as(client, world.a.admin)

    detail = client.get(f"/api/authorization/staff/{world.a.staff.id}").json()

    effective = {p["permission_code"]: p["effective"] for p in detail["permissions"]}
    assert effective == {"purchase_order.read": False, "purchase_bill.read": True}


@pytest.mark.parametrize("role", ["admin", "manager"])
def test_admin_and_kitchen_manager_perform_every_order_operation(client, world, stock, role):
    act_as(client, getattr(world.a, role))
    order = placed_order(client, world, stock)
    draft = make_order(client, world.a, [(world.a.item, "1", world.a.kg)])

    results = {name: response.status_code
               for name, response in order_operations(client, world.a, order["id"], draft["id"])}

    # The draft is placed before it is cancelled, so cancel still applies.
    assert results == {"list": 200, "detail": 200, "billable": 200, "create": 201, "edit": 200,
                       "place": 200, "close": 200, "cancel": 200}, results


def test_order_information_is_hidden_from_staff(client, db, world, stock):
    """Bill, receiving and activity views show no purchase-order
    information (order id or number, order-line links, ordered quantities)
    to STAFF, even with bill, inventory and audit access and kept older
    order grants (decision 20 November 2026). ADMIN and KITCHEN_MANAGER
    still see it."""
    act_as(client, world.a.admin)
    order = placed_order(client, world, stock)
    bill = bill_against(client, world.a, order, [(world.a.item, "10", world.a.kg, line_of(order, "Rice")["id"])],
                        invoice="HIDE-1").json()
    for code in ORDER_CODES + ("purchase_bill.read", "inventory.read", "audit.read", "dashboard.read"):
        grant(db, world.a.staff, world.a.admin, code)
    before = staff_grants(db, world.a.staff)

    act_as(client, world.a.staff)
    detail = client.get(f"{BILLS}{bill['id']}").json()
    assert (detail["purchase_order_id"], detail["purchase_order_number"]) == (None, None)
    assert all(line["purchase_order_item_id"] is None for line in detail["items"])
    assert all(row["purchase_order_id"] is None for row in client.get(BILLS).json())
    receiving = client.get(f"{BILLS}{bill['id']}/receiving").json()
    assert (receiving["purchase_order_id"], receiving["purchase_order_number"]) == (None, None)
    assert all(line["ordered_quantity"] is None and line["purchase_order_item_id"] is None
               for line in receiving["lines"])
    feed = client.get("/api/dashboard/overview").json()["activity"]
    assert any(entry["entity_type"] == "PURCHASE" for entry in feed)
    assert "PO-" not in str(feed) and "purchase_order" not in str(feed)
    assert staff_grants(db, world.a.staff) == before

    for role in ("admin", "manager"):
        act_as(client, getattr(world.a, role))
        assert client.get(f"{BILLS}{bill['id']}").json()["purchase_order_number"] == "PO-00001"
        rice = next(l for l in client.get(f"{BILLS}{bill['id']}/receiving").json()["lines"])
        assert rice["ordered_quantity"] == "50.000"


def test_bill_access_alone_does_not_open_orders(client, db, world):
    grant(db, world.a.staff, world.a.admin, "purchase_bill.read")
    act_as(client, world.a.staff)

    assert client.get(BILLS).status_code == 200
    assert client.get(ORDERS).status_code == 403


def test_kitchen_manager_holds_both_namespaces(client, world, stock):
    act_as(client, world.a.manager)
    order = placed_order(client, world, stock)
    bill = bill_against(client, world.a, order, [(world.a.item, "5", world.a.kg, line_of(order, "Rice")["id"])])
    assert bill.status_code == 201
    assert client.get(f"{ORDERS}/billable", params={"supplier_id": world.a.supplier.id}).status_code == 200


# ============================================================
# CAMPUS ISOLATION AND AUDIT
# ============================================================

def test_another_campus_cannot_see_or_use_orders(client, world, stock):
    act_as(client, world.a.admin)
    order = placed_order(client, world, stock)

    act_as(client, world.b.admin)
    assert client.get(f"{ORDERS}/{order['id']}").status_code == 404
    assert client.put(f"{ORDERS}/{order['id']}", json=order_body(world.b, [(world.b.item, "1", world.b.kg)])).status_code == 404
    for action, body in (("place", None), ("close", {"reason": "x"}), ("cancel", {"reason": "x"})):
        assert client.post(f"{ORDERS}/{order['id']}/{action}", json=body).status_code == 404, action
    assert client.get(ORDERS).json()["total"] == 0
    assert client.get(f"{ORDERS}/billable", params={"supplier_id": world.a.supplier.id}).json()["items"] == []
    stolen = client.post(BILLS, json={
        "supplier_id": world.b.supplier.id, "invoice_number": "B-STEAL", "purchase_date": "2026-11-12",
        "purchase_order_id": order["id"],
        "items": [{"item_id": world.b.item.id, "quantity": "1", "unit_id": world.b.kg.id, "unit_rate": "1"}]})
    assert stolen.status_code == 404


def test_order_activity_reaches_only_order_readers(client, db, world, stock):
    act_as(client, world.a.admin)
    placed_order(client, world, stock)
    actions = sorted(a for (a,) in db.query(AuditLog.action).filter_by(entity_type="PURCHASE_ORDER"))
    assert actions == ["CREATE", "PLACE"]

    act_as(client, world.a.manager)
    feed = client.get("/api/dashboard/overview").json()["activity"]
    assert any(entry["entity_type"] == "PURCHASE_ORDER" for entry in feed)

    grant(db, world.a.staff, world.a.admin, "audit.read")
    grant(db, world.a.staff, world.a.admin, "dashboard.read")
    act_as(client, world.a.staff)
    feed = client.get("/api/dashboard/overview").json().get("activity", [])
    assert not any(entry["entity_type"] == "PURCHASE_ORDER" for entry in feed)
