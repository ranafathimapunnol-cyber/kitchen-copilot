from decimal import Decimal

from app.models import (
    Campus,
    Category,
    Unit,
    Item,
    Supplier,
    AuditLog,
)
from app.models.purchases import Purchase, PurchaseItem, StockMovement


def create_master_records(client):
    category_response = client.post(
        "/api/master/categories",
        json={"name": "Purchase Test Category"},
    )
    assert category_response.status_code == 201, category_response.text
    category_id = category_response.json()["id"]

    unit_response = client.post(
        "/api/master/units",
        json={
            "name": "Purchase Kilogram",
            "symbol": "pkg",
            "dimension": "weight",
        },
    )
    assert unit_response.status_code == 201, unit_response.text
    unit_id = unit_response.json()["id"]

    supplier_response = client.post(
        "/api/master/suppliers",
        json={
            "name": "Purchase Test Supplier",
            "phone": "9876543210",
        },
    )
    assert supplier_response.status_code == 201, supplier_response.text
    supplier_id = supplier_response.json()["id"]

    item_ids = []

    for name in ["Purchase Rice", "Purchase Wheat"]:
        response = client.post(
            "/api/master/items",
            json={
                "name": name,
                "category_id": category_id,
                "standard_unit_id": unit_id,
                "minimum_stock": "5",
            },
        )
        assert response.status_code == 201, response.text
        item_ids.append(response.json()["id"])

    return {
        "category_id": category_id,
        "unit_id": unit_id,
        "supplier_id": supplier_id,
        "item_ids": item_ids,
    }


def purchase_payload(records, invoice_number="INV-001"):
    return {
        "supplier_id": records["supplier_id"],
        "invoice_number": invoice_number,
        "purchase_date": "2026-11-07",
        "discount": "2.50",
        "extra_charges": "1.00",
        "remarks": "Test purchase",
        "items": [
            {
                "item_id": records["item_ids"][0],
                "quantity": "2",
                "unit_id": records["unit_id"],
                "unit_rate": "10.25",
            },
            {
                "item_id": records["item_ids"][1],
                "quantity": "3",
                "unit_id": records["unit_id"],
                "unit_rate": "4.00",
            },
        ],
    }


def test_create_purchase_with_multiple_items_and_calculated_totals(
    client, db, setup_data
):
    records = create_master_records(client)

    response = client.post(
        "/api/purchases/",
        json=purchase_payload(records),
    )

    assert response.status_code == 201, response.text
    data = response.json()

    assert data["invoice_number"] == "INV-001"
    assert data["status"] == "DRAFT"
    assert Decimal(str(data["subtotal"])) == Decimal("32.50")
    assert Decimal(str(data["discount"])) == Decimal("2.50")
    assert Decimal(str(data["extra_charges"])) == Decimal("1.00")
    assert Decimal(str(data["grand_total"])) == Decimal("31.00")

    assert len(data["items"]) == 2
    assert Decimal(str(data["items"][0]["line_total"])) == Decimal("20.50")
    assert Decimal(str(data["items"][1]["line_total"])) == Decimal("12.00")

    purchase = db.query(Purchase).filter(
        Purchase.id == data["id"]
    ).first()
    assert purchase is not None
    assert purchase.campus_id == setup_data["campus"].id

    assert db.query(PurchaseItem).filter(
        PurchaseItem.purchase_id == purchase.id
    ).count() == 2

    # Creating an invoice must never post stock.
    assert db.query(StockMovement).count() == 0

    audit = db.query(AuditLog).filter(
        AuditLog.entity_type == "PURCHASE",
        AuditLog.entity_id == purchase.id,
    ).first()

    assert audit is not None
    assert audit.action == "CREATE"
    assert audit.campus_id == setup_data["campus"].id


def test_reject_duplicate_supplier_invoice(client):
    records = create_master_records(client)
    payload = purchase_payload(records, "DUP-001")

    first = client.post("/api/purchases/", json=payload)
    assert first.status_code == 201, first.text

    second = client.post("/api/purchases/", json=payload)

    assert second.status_code == 409
    assert "already exists" in second.json()["detail"]


def test_reject_discount_greater_than_subtotal(client):
    records = create_master_records(client)
    payload = purchase_payload(records)
    payload["discount"] = "1000"

    response = client.post("/api/purchases/", json=payload)

    assert response.status_code == 422
    assert "Discount cannot exceed" in response.json()["detail"]


def test_reject_missing_unit_conversion(client):
    records = create_master_records(client)

    gram_response = client.post(
        "/api/master/units",
        json={
            "name": "Purchase Gram",
            "symbol": "p-g",
            "dimension": "weight",
        },
    )
    assert gram_response.status_code == 201
    gram_id = gram_response.json()["id"]

    payload = purchase_payload(records)
    payload["items"][0]["unit_id"] = gram_id

    response = client.post("/api/purchases/", json=payload)

    assert response.status_code == 422
    assert "conversion" in response.json()["detail"].lower()


def test_reject_supplier_from_another_campus(
    client, db, setup_data
):
    other_campus = Campus(
        name="Another Purchase Campus",
        code="PURCHASE-OTHER",
    )
    db.add(other_campus)
    db.flush()

    foreign_supplier = Supplier(
        campus_id=other_campus.id,
        name="Foreign Supplier",
        is_active=True,
    )
    db.add(foreign_supplier)
    db.commit()

    records = create_master_records(client)
    payload = purchase_payload(records)
    payload["supplier_id"] = foreign_supplier.id

    response = client.post("/api/purchases/", json=payload)

    assert response.status_code == 404


def test_reject_item_from_another_campus(client, db):
    records = create_master_records(client)

    other_campus = Campus(
        name="Foreign Item Campus",
        code="FOREIGN-ITEM",
    )
    db.add(other_campus)
    db.flush()

    foreign_category = Category(
        campus_id=other_campus.id,
        name="Foreign Category",
    )
    foreign_unit = Unit(
        campus_id=other_campus.id,
        name="Foreign Unit",
        symbol="fu",
        dimension="weight",
        is_active=True,
    )
    db.add_all([foreign_category, foreign_unit])
    db.flush()

    foreign_item = Item(
        campus_id=other_campus.id,
        name="Foreign Rice",
        category_id=foreign_category.id,
        standard_unit_id=foreign_unit.id,
        minimum_stock=0,
        is_active=True,
    )
    db.add(foreign_item)
    db.commit()

    payload = purchase_payload(records)
    payload["items"][0]["item_id"] = foreign_item.id

    response = client.post("/api/purchases/", json=payload)

    assert response.status_code == 404


def test_list_and_get_purchases(client):
    records = create_master_records(client)

    create_response = client.post(
        "/api/purchases/",
        json=purchase_payload(records),
    )
    assert create_response.status_code == 201

    purchase_id = create_response.json()["id"]

    list_response = client.get("/api/purchases/")
    assert list_response.status_code == 200
    assert any(
        purchase["id"] == purchase_id
        for purchase in list_response.json()
    )

    detail_response = client.get(f"/api/purchases/{purchase_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == purchase_id

    missing_response = client.get("/api/purchases/999999")
    assert missing_response.status_code == 404
