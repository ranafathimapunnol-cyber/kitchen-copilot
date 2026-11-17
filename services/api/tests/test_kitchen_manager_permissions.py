"""
Kitchen Manager restrictions from the approved permission matrix.

- Suppliers are read-only: create, update, deactivate and delete are
  rejected with 403.
- Supplier bills (/api/purchases) are not accessible at all, for reading
  or writing, and the dashboard shows no bill data.
- Approved operational work (master data, menus, goods receipts) still
  works.
"""

import json

import pytest

from app.models import Supplier
from app.models.purchases import Purchase

from tests.test_authorization import (
    assign_staff_permission,
    authenticate_as,
    create_test_user,
)
from tests.test_receipts import create_receipt_purchase, receipt_payload


SUPPLIERS_URL = "/api/master/suppliers"


def create_supplier_as_admin(client, setup_data, name="Matrix Supplier"):
    authenticate_as(client, setup_data["user"])
    response = client.post(SUPPLIERS_URL, json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def kitchen_manager(db, setup_data):
    return create_test_user(db, setup_data["campus"].id, "KITCHEN_MANAGER")


# ------------------------------------------------------------
# Suppliers: read-only
# ------------------------------------------------------------

def test_kitchen_manager_can_read_suppliers(
    client, setup_data, kitchen_manager
):
    supplier = create_supplier_as_admin(client, setup_data)
    authenticate_as(client, kitchen_manager)

    response = client.get(SUPPLIERS_URL)

    assert response.status_code == 200, response.text
    assert supplier["id"] in [row["id"] for row in response.json()["items"]]


def test_kitchen_manager_cannot_create_supplier(
    client, db, kitchen_manager
):
    authenticate_as(client, kitchen_manager)

    response = client.post(SUPPLIERS_URL, json={"name": "Blocked Supplier"})

    assert response.status_code == 403, response.text
    assert db.query(Supplier).count() == 0


def test_kitchen_manager_cannot_update_supplier(
    client, db, setup_data, kitchen_manager
):
    supplier = create_supplier_as_admin(client, setup_data)
    authenticate_as(client, kitchen_manager)

    response = client.put(
        f"{SUPPLIERS_URL}/{supplier['id']}",
        json={"name": "Renamed By Manager"},
    )

    assert response.status_code == 403, response.text
    db.expire_all()
    assert db.get(Supplier, supplier["id"]).name == "Matrix Supplier"


def test_kitchen_manager_cannot_deactivate_supplier(
    client, db, setup_data, kitchen_manager
):
    supplier = create_supplier_as_admin(client, setup_data)
    authenticate_as(client, kitchen_manager)

    response = client.post(f"{SUPPLIERS_URL}/{supplier['id']}/deactivate")

    assert response.status_code == 403, response.text
    db.expire_all()
    assert db.get(Supplier, supplier["id"]).is_active is True


def test_kitchen_manager_cannot_delete_supplier(
    client, db, setup_data, kitchen_manager
):
    supplier = create_supplier_as_admin(client, setup_data)
    authenticate_as(client, kitchen_manager)

    response = client.delete(f"{SUPPLIERS_URL}/{supplier['id']}")

    assert response.status_code == 403, response.text
    assert db.get(Supplier, supplier["id"]) is not None


def test_admin_supplier_writes_are_unchanged(client, setup_data):
    supplier = create_supplier_as_admin(client, setup_data)

    update = client.put(
        f"{SUPPLIERS_URL}/{supplier['id']}",
        json={"name": "Renamed By Admin"},
    )
    assert update.status_code == 200, update.text

    deactivate = client.post(f"{SUPPLIERS_URL}/{supplier['id']}/deactivate")
    assert deactivate.status_code == 200, deactivate.text


def test_staff_supplier_access_still_follows_assignments(
    client, db, setup_data
):
    # The Kitchen Manager rule must not change STAFF behaviour.
    staff = create_test_user(db, setup_data["campus"].id, "STAFF")

    for code in ("inventory.create", "inventory.update"):
        assign_staff_permission(
            db, staff, setup_data["user"], "inventory", "Inventory", code
        )

    authenticate_as(client, staff)

    created = client.post(SUPPLIERS_URL, json={"name": "Staff Supplier"})
    assert created.status_code == 201, created.text

    updated = client.put(
        f"{SUPPLIERS_URL}/{created.json()['id']}",
        json={"name": "Staff Supplier Renamed"},
    )
    assert updated.status_code == 200, updated.text


# ------------------------------------------------------------
# Supplier bills: no access
# ------------------------------------------------------------

def test_kitchen_manager_cannot_list_or_read_bills(
    client, setup_data, kitchen_manager
):
    authenticate_as(client, setup_data["user"])
    records = create_receipt_purchase(client)

    authenticate_as(client, kitchen_manager)

    assert client.get("/api/purchases/").status_code == 403
    assert (
        client.get(f"/api/purchases/{records['purchase_id']}").status_code
        == 403
    )


def test_kitchen_manager_cannot_create_bill(
    client, db, setup_data, kitchen_manager
):
    authenticate_as(client, setup_data["user"])
    records = create_receipt_purchase(client)
    bills_before = db.query(Purchase).count()

    authenticate_as(client, kitchen_manager)

    response = client.post(
        "/api/purchases/",
        json={
            "supplier_id": db.query(Supplier).first().id,
            "invoice_number": "KM-BLOCKED-001",
            "purchase_date": "2026-11-07",
            "items": [
                {
                    "item_id": records["item_id"],
                    "quantity": "1",
                    "unit_id": records["kg_id"],
                    "unit_rate": "10",
                }
            ],
        },
    )

    assert response.status_code == 403, response.text
    assert db.query(Purchase).count() == bills_before


def test_kitchen_manager_effective_permissions_exclude_bills(
    client, kitchen_manager
):
    authenticate_as(client, kitchen_manager)

    response = client.get("/api/authorization/me")

    assert response.status_code == 200, response.text
    permissions = response.json()["permissions"]
    assert not [code for code in permissions if code.startswith("purchase_order.")]
    # Approved operational permissions are preserved.
    for code in (
        "dashboard.read",
        "inventory.create",
        "inventory.read",
        "inventory.update",
        "menu.create",
        "menu.read",
        "menu.update",
        "audit.read",
        "waste_tracking.create",
    ):
        assert code in permissions, code


def test_kitchen_manager_dashboard_contains_no_bill_data(
    client, setup_data, kitchen_manager
):
    authenticate_as(client, setup_data["user"])
    create_receipt_purchase(client)  # writes a PURCHASE audit entry

    admin_payload = client.get("/api/dashboard/overview").json()
    assert "purchases" in admin_payload
    assert any(
        entry["entity_type"] == "PURCHASE"
        for entry in admin_payload["activity"]
    )

    authenticate_as(client, kitchen_manager)
    response = client.get("/api/dashboard/overview")

    assert response.status_code == 200, response.text
    payload = response.json()

    assert "purchases" not in payload
    assert "purchases_this_month" not in payload["kpis"]
    assert "purchase_spending_this_month" not in payload["kpis"]

    # The activity feed is kept, but without bill entries.
    assert payload["activity"]
    assert all(
        entry["entity_type"] != "PURCHASE" for entry in payload["activity"]
    )
    assert "RECEIPT-INV-001" not in json.dumps(payload)


# ------------------------------------------------------------
# Approved operational work still works
# ------------------------------------------------------------

def test_kitchen_manager_keeps_master_data_writes(
    client, kitchen_manager
):
    authenticate_as(client, kitchen_manager)

    category = client.post(
        "/api/master/categories", json={"name": "Manager Category"}
    )
    assert category.status_code == 201, category.text

    updated = client.put(
        f"/api/master/categories/{category.json()['id']}",
        json={"name": "Manager Category Renamed"},
    )
    assert updated.status_code == 200, updated.text

    session = client.post(
        "/api/master/meal-sessions", json={"name": "Manager Lunch"}
    )
    assert session.status_code == 201, session.text


def test_kitchen_manager_keeps_goods_receipt_create_and_accept(
    client, setup_data, kitchen_manager
):
    authenticate_as(client, setup_data["user"])
    records = create_receipt_purchase(client)

    authenticate_as(client, kitchen_manager)

    receipt = client.post(
        f"/api/purchases/{records['purchase_id']}/receipts",
        json=receipt_payload(records),
    )
    assert receipt.status_code == 201, receipt.text

    accepted = client.post(f"/api/receipts/{receipt.json()['id']}/accept")
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "ACCEPTED"
