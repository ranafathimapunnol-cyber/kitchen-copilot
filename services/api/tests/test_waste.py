"""
P0 characterization tests for the waste tracking API.

These tests record the CURRENT behaviour of /api/waste/records so that
later phases cannot change it by accident.

Two kinds of assertions are used:

* Permanent rules (must stay true in every phase):
  - Prepared-food waste never creates a stock movement.
  - Waste records are isolated per campus.
  - Permission checks are enforced by the backend.

* Current-behaviour characterization (expected to change on purpose):
  - Raw-ingredient waste does not post to the stock ledger yet.
    P4 will introduce a confirmation step that posts exactly one
    WASTE movement; this test must be updated in that phase.
"""

from datetime import date

from app.models import Campus, Unit
from app.models.purchases import StockMovement
from app.models.waste import WasteItem, WasteRecord
from app.models.audit_log import AuditLog

from tests.test_authorization import (
    assign_staff_permission,
    authenticate_as,
    create_test_user,
)


WASTE_URL = "/api/waste/records"


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def create_master_data(client):
    """Create a unit, category and raw item in the admin's campus."""

    unit = client.post(
        "/api/master/units",
        json={"name": "Kilogram", "symbol": "kg", "dimension": "weight"},
    )
    assert unit.status_code == 201, unit.text

    category = client.post(
        "/api/master/categories",
        json={"name": "Grains"},
    )
    assert category.status_code == 201, category.text

    item = client.post(
        "/api/master/items",
        json={
            "name": "Rice",
            "category_id": category.json()["id"],
            "standard_unit_id": unit.json()["id"],
            "minimum_stock": "0",
        },
    )
    assert item.status_code == 201, item.text

    return {
        "unit_id": unit.json()["id"],
        "item_id": item.json()["id"],
    }


def raw_line(master, quantity="2.500"):
    return {
        "waste_type": "RAW_INGREDIENT",
        "item_id": master["item_id"],
        "unit_id": master["unit_id"],
        "quantity": quantity,
        "waste_stage": "STORAGE",
        "waste_reason": "SPOILED",
        "estimated_cost": "120.00",
    }


def prepared_line(master, quantity="4.000"):
    return {
        "waste_type": "PREPARED_FOOD",
        "food_name": "Vegetable curry",
        "unit_id": master["unit_id"],
        "quantity": quantity,
        "waste_stage": "AFTER_MEAL",
        "waste_reason": "LEFTOVER",
        "estimated_cost": "80.00",
    }


def create_record(client, items):
    response = client.post(
        WASTE_URL,
        json={"notes": "P0 characterization", "items": items},
    )
    assert response.status_code == 201, response.text
    return response.json()


# ------------------------------------------------------------
# Create and read
# ------------------------------------------------------------

def test_admin_can_create_and_read_waste_record(client, db, setup_data):
    master = create_master_data(client)

    record = create_record(
        client, [raw_line(master), prepared_line(master)]
    )

    assert len(record["items"]) == 2
    types = sorted(line["waste_type"] for line in record["items"])
    assert types == ["PREPARED_FOOD", "RAW_INGREDIENT"]

    raw = next(
        line for line in record["items"]
        if line["waste_type"] == "RAW_INGREDIENT"
    )
    assert raw["food_name"] == "Rice"
    assert raw["unit_symbol"] == "kg"

    detail = client.get(f"{WASTE_URL}/{record['id']}")
    assert detail.status_code == 200
    assert detail.json()["id"] == record["id"]

    listing = client.get(WASTE_URL)
    assert listing.status_code == 200
    assert any(row["id"] == record["id"] for row in listing.json())

    audit = db.query(AuditLog).filter(
        AuditLog.entity_type == "WASTE_RECORD",
        AuditLog.entity_id == record["id"],
        AuditLog.action == "CREATE",
    ).first()
    assert audit is not None
    assert audit.campus_id == setup_data["campus"].id


# ------------------------------------------------------------
# Stock ledger behaviour
# ------------------------------------------------------------

def test_prepared_food_waste_never_creates_stock_movement(client, db):
    """Permanent rule (Decision 5): prepared-food waste must not
    reduce raw inventory."""

    master = create_master_data(client)
    before = db.query(StockMovement).count()

    create_record(client, [prepared_line(master)])

    assert db.query(StockMovement).count() == before


def test_raw_waste_does_not_post_stock_yet(client, db):
    """Current behaviour, to be changed deliberately in P4.

    Today raw-ingredient waste is recorded without touching the stock
    ledger. P4 adds a confirmation step that posts exactly one WASTE
    movement per raw line; update this test in that phase.
    """

    master = create_master_data(client)
    before = db.query(StockMovement).count()

    create_record(client, [raw_line(master)])

    assert db.query(StockMovement).count() == before


# ------------------------------------------------------------
# Validation
# ------------------------------------------------------------

def test_raw_waste_requires_item(client):
    master = create_master_data(client)
    line = raw_line(master)
    line.pop("item_id")

    response = client.post(WASTE_URL, json={"items": [line]})

    assert response.status_code == 422


def test_prepared_food_waste_rejects_inventory_item(client):
    master = create_master_data(client)
    line = prepared_line(master)
    line["item_id"] = master["item_id"]

    response = client.post(WASTE_URL, json={"items": [line]})

    assert response.status_code == 422


def test_prepared_food_waste_requires_food_name(client):
    master = create_master_data(client)
    line = prepared_line(master)
    line["food_name"] = "   "

    response = client.post(WASTE_URL, json={"items": [line]})

    assert response.status_code == 422


def test_waste_requires_at_least_one_line(client):
    response = client.post(WASTE_URL, json={"items": []})

    assert response.status_code == 422


def test_quantity_must_be_positive(client):
    master = create_master_data(client)

    response = client.post(
        WASTE_URL,
        json={"items": [raw_line(master, quantity="0")]},
    )

    assert response.status_code == 422


# ------------------------------------------------------------
# Campus isolation
# ------------------------------------------------------------

def test_waste_records_are_campus_isolated(client, db, setup_data):
    other_campus = Campus(name="Other Waste Campus", code="OTHER-WASTE")
    db.add(other_campus)
    db.flush()

    other_admin = create_test_user(db, other_campus.id, "ADMIN")

    other_unit = Unit(
        campus_id=other_campus.id,
        name="Litre",
        symbol="l",
        dimension="volume",
    )
    db.add(other_unit)
    db.flush()

    other_record = WasteRecord(
        campus_id=other_campus.id,
        waste_date=date.today(),
        recorded_by=other_admin.id,
        notes="Other campus waste",
    )
    db.add(other_record)
    db.flush()

    db.add(
        WasteItem(
            campus_id=other_campus.id,
            waste_record_id=other_record.id,
            unit_id=other_unit.id,
            food_name="Other campus soup",
            waste_type="PREPARED_FOOD",
            quantity=1,
            waste_stage="SERVING",
            waste_reason="OTHER",
            estimated_cost=0,
        )
    )
    db.commit()

    listing = client.get(WASTE_URL)
    assert listing.status_code == 200
    assert all(row["id"] != other_record.id for row in listing.json())

    assert client.get(f"{WASTE_URL}/{other_record.id}").status_code == 404

    master = create_master_data(client)
    patch = client.patch(
        f"{WASTE_URL}/{other_record.id}",
        json={"notes": "should not be allowed"},
    )
    assert patch.status_code == 404

    # A unit from another campus cannot be used either.
    line = prepared_line(master)
    line["unit_id"] = other_unit.id
    assert client.post(WASTE_URL, json={"items": [line]}).status_code == 404


# ------------------------------------------------------------
# Permissions
# ------------------------------------------------------------

def test_staff_without_waste_permission_is_denied(client, db, setup_data):
    master = create_master_data(client)

    staff = create_test_user(db, setup_data["campus"].id, "STAFF")
    authenticate_as(client, staff)

    assert client.get(WASTE_URL).status_code == 403

    # A valid body, so the 403 can only come from the permission check.
    response = client.post(
        WASTE_URL, json={"items": [prepared_line(master)]}
    )
    assert response.status_code == 403


def test_staff_with_read_only_cannot_create(client, db, setup_data):
    staff = create_test_user(db, setup_data["campus"].id, "STAFF")
    assign_staff_permission(
        db,
        staff,
        setup_data["user"],
        "waste_tracking",
        "Waste Tracking",
        "waste_tracking.read",
    )

    master = create_master_data(client)
    authenticate_as(client, staff)

    assert client.get(WASTE_URL).status_code == 200
    response = client.post(
        WASTE_URL, json={"items": [prepared_line(master)]}
    )
    assert response.status_code == 403


def test_kitchen_manager_can_create_but_not_delete(client, db, setup_data):
    master = create_master_data(client)
    record = create_record(client, [prepared_line(master)])

    manager = create_test_user(
        db, setup_data["campus"].id, "KITCHEN_MANAGER"
    )
    authenticate_as(client, manager)

    created = client.post(
        WASTE_URL, json={"items": [prepared_line(master)]}
    )
    assert created.status_code == 201, created.text

    assert client.delete(f"{WASTE_URL}/{record['id']}").status_code == 403


def test_admin_update_replaces_lines_and_admin_can_delete(client, db):
    master = create_master_data(client)
    record = create_record(
        client, [raw_line(master), prepared_line(master)]
    )

    updated = client.patch(
        f"{WASTE_URL}/{record['id']}",
        json={"notes": "updated", "items": [prepared_line(master, "1.000")]},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["notes"] == "updated"
    assert len(updated.json()["items"]) == 1

    deleted = client.delete(f"{WASTE_URL}/{record['id']}")
    assert deleted.status_code == 200
    assert client.get(f"{WASTE_URL}/{record['id']}").status_code == 404
