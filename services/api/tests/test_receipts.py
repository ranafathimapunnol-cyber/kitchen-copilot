from datetime import date
from decimal import Decimal

from app.models import (
    Campus,
    Category,
    Unit,
    UnitConversion,
    Item,
    Supplier,
    AuditLog,
)
from app.models.purchases import (
    Purchase,
    PurchaseItem,
    GoodsReceipt,
    GoodsReceiptItem,
    StockMovement,
)


def create_receipt_purchase(client):
    category = client.post(
        "/api/master/categories",
        json={"name": "Receipt Test Category"},
    )
    assert category.status_code == 201, category.text

    kg = client.post(
        "/api/master/units",
        json={
            "name": "Receipt Kilogram",
            "symbol": "rkg",
            "dimension": "weight",
        },
    )
    assert kg.status_code == 201, kg.text

    gram = client.post(
        "/api/master/units",
        json={
            "name": "Receipt Gram",
            "symbol": "rg",
            "dimension": "weight",
        },
    )
    assert gram.status_code == 201, gram.text

    conversion = client.post(
        "/api/master/unit-conversions",
        json={
            "from_unit_id": kg.json()["id"],
            "to_unit_id": gram.json()["id"],
            "factor": "1000",
        },
    )
    assert conversion.status_code == 201, conversion.text

    supplier = client.post(
        "/api/master/suppliers",
        json={"name": "Receipt Test Supplier"},
    )
    assert supplier.status_code == 201, supplier.text

    item = client.post(
        "/api/master/items",
        json={
            "name": "Receipt Test Rice",
            "category_id": category.json()["id"],
            "standard_unit_id": kg.json()["id"],
            "minimum_stock": "5",
        },
    )
    assert item.status_code == 201, item.text

    purchase = client.post(
        "/api/purchases/",
        json={
            "supplier_id": supplier.json()["id"],
            "invoice_number": "RECEIPT-INV-001",
            "purchase_date": "2026-11-07",
            "items": [
                {
                    "item_id": item.json()["id"],
                    "quantity": "2000",
                    "unit_id": gram.json()["id"],
                    "unit_rate": "0.05",
                }
            ],
        },
    )
    assert purchase.status_code == 201, purchase.text

    return {
        "purchase_id": purchase.json()["id"],
        "purchase_item_id": purchase.json()["items"][0]["id"],
        "item_id": item.json()["id"],
        "kg_id": kg.json()["id"],
        "gram_id": gram.json()["id"],
    }


def receipt_payload(records, received="1500", accepted="1400", rejected="100"):
    return {
        "receipt_date": "2026-11-07",
        "remarks": "Test goods receipt",
        "items": [
            {
                "purchase_item_id": records["purchase_item_id"],
                "quantity_received": received,
                "quantity_accepted": accepted,
                "quantity_rejected": rejected,
            }
        ],
    }


def create_receipt(client, records, **quantities):
    response = client.post(
        f"/api/purchases/{records['purchase_id']}/receipts",
        json=receipt_payload(records, **quantities),
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_and_accept_receipt_posts_converted_stock_once(
    client, db, setup_data
):
    records = create_receipt_purchase(client)

    receipt = create_receipt(client, records)

    assert receipt["status"] == "DRAFT"
    assert len(receipt["items"]) == 1
    assert Decimal(str(receipt["items"][0]["quantity_received"])) == Decimal("1500")

    # Draft receipts must not affect stock.
    assert db.query(StockMovement).count() == 0

    response = client.post(f"/api/receipts/{receipt['id']}/accept")

    assert response.status_code == 200, response.text
    accepted = response.json()

    assert accepted["status"] == "ACCEPTED"
    assert accepted["accepted_by"] == setup_data["user"].id
    assert accepted["accepted_at"] is not None

    movements = db.query(StockMovement).filter(
        StockMovement.reference_id == receipt["id"],
        StockMovement.reference_type == "GOODS_RECEIPT",
    ).all()

    assert len(movements) == 1

    movement = movements[0]
    assert movement.item_id == records["item_id"]
    assert movement.unit_id == records["kg_id"]
    assert movement.movement_type == "RECEIPT"

    # 1400 grams accepted = 1.400 kilograms.
    assert Decimal(str(movement.quantity)) == Decimal("1.400")

    audit = db.query(AuditLog).filter(
        AuditLog.entity_type == "GOODS_RECEIPT",
        AuditLog.entity_id == receipt["id"],
        AuditLog.action == "ACCEPT",
    ).first()

    assert audit is not None
    assert audit.campus_id == setup_data["campus"].id

    # A second acceptance must not post stock again.
    second_response = client.post(
        f"/api/receipts/{receipt['id']}/accept"
    )

    assert second_response.status_code == 409
    assert db.query(StockMovement).count() == 1


def test_reject_acceptance_when_quantity_split_is_incomplete(client, db):
    records = create_receipt_purchase(client)

    receipt = create_receipt(
        client,
        records,
        received="1000",
        accepted="600",
        rejected="200",
    )

    response = client.post(
        f"/api/receipts/{receipt['id']}/accept"
    )

    assert response.status_code == 422
    assert "must equal received quantity" in response.json()["detail"]
    assert db.query(StockMovement).count() == 0

    saved_receipt = db.query(GoodsReceipt).filter(
        GoodsReceipt.id == receipt["id"]
    ).first()
    assert saved_receipt.status == "DRAFT"


def test_reject_receipt_quantity_above_purchased_quantity(client):
    records = create_receipt_purchase(client)

    first = create_receipt(
        client,
        records,
        received="1500",
        accepted="1500",
        rejected="0",
    )
    assert first["status"] == "DRAFT"

    second_response = client.post(
        f"/api/purchases/{records['purchase_id']}/receipts",
        json=receipt_payload(
            records,
            received="600",
            accepted="600",
            rejected="0",
        ),
    )

    assert second_response.status_code == 422
    assert "exceeds the remaining purchased quantity" in second_response.json()["detail"]


def test_receipt_with_zero_accepted_quantity_posts_no_stock(client, db):
    records = create_receipt_purchase(client)

    receipt = create_receipt(
        client,
        records,
        received="500",
        accepted="0",
        rejected="500",
    )

    response = client.post(
        f"/api/receipts/{receipt['id']}/accept"
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ACCEPTED"
    assert db.query(StockMovement).count() == 0


def test_list_and_get_receipts(client):
    records = create_receipt_purchase(client)
    receipt = create_receipt(client, records)

    list_response = client.get(
        f"/api/purchases/{records['purchase_id']}/receipts"
    )
    assert list_response.status_code == 200
    assert any(row["id"] == receipt["id"] for row in list_response.json())

    detail_response = client.get(
        f"/api/receipts/{receipt['id']}"
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == receipt["id"]

    missing_response = client.get("/api/receipts/999999")
    assert missing_response.status_code == 404


def test_receipt_rejects_duplicate_purchase_item_lines(client):
    records = create_receipt_purchase(client)

    payload = receipt_payload(records)
    payload["items"].append(payload["items"][0])

    response = client.post(
        f"/api/purchases/{records['purchase_id']}/receipts",
        json=payload,
    )

    assert response.status_code == 422
    assert "only once" in response.json()["detail"]


def test_receipt_cannot_access_purchase_from_another_campus(
    client, db, setup_data
):
    records = create_receipt_purchase(client)

    other_campus = Campus(
        name="Receipt Other Campus",
        code="RECEIPT-OTHER",
    )
    db.add(other_campus)
    db.flush()

    foreign_receipt = GoodsReceipt(
        campus_id=other_campus.id,
        purchase_id=records["purchase_id"],
        receipt_date=date(2026, 11, 7),
        status="DRAFT",
        created_by=setup_data["user"].id,
    )
    db.add(foreign_receipt)
    db.commit()

    response = client.get(
        f"/api/receipts/{foreign_receipt.id}"
    )

    assert response.status_code == 404


def test_stock_movements_are_campus_scoped(client, db, setup_data):
    records = create_receipt_purchase(client)
    receipt = create_receipt(client, records)

    accepted = client.post(
        f"/api/receipts/{receipt['id']}/accept"
    )
    assert accepted.status_code == 200, accepted.text

    response = client.get("/api/stock/movements")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["reference_id"] == receipt["id"]
    assert all(
        movement.campus_id == setup_data["campus"].id
        for movement in db.query(StockMovement).all()
    )
