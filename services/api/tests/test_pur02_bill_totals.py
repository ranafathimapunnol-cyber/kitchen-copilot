"""
PUR02 — Calculate Bill Totals. One test per acceptance criterion in the
approved proposal:

1. Item total = quantity × unit rate.
2. Bill-level discounts and additional charges are recorded separately.
3. The bill total includes the recorded discounts and charges consistently.
4. Actual purchase rates remain available for historical comparisons.
5. Monetary calculations use exact decimal arithmetic.

Criterion 5 is also tested on PostgreSQL (test_pur04_postgres.py), because
SQLite stores NUMERIC values as floating point and so cannot show exact
storage. Self-contained here: in-memory SQLite, no project conftest:

    pytest --noconftest tests/test_pur02_bill_totals.py
"""

from decimal import ROUND_HALF_UP, Decimal

from app.models.purchases import Purchase, PurchaseItem

from tests.test_operational_authority import (  # noqa: F401 (fixtures)
    act_as,
    client,
    db,
    world,
)

BILLS = "/api/purchases/"


def line(place, quantity, rate):
    return {"item_id": place.item.id, "quantity": quantity,
            "unit_id": place.kg.id, "unit_rate": rate}


def create(client, place, invoice, lines, **extra):
    response = client.post(BILLS, json={
        "supplier_id": place.supplier.id, "invoice_number": invoice,
        "purchase_date": "2026-11-03", "items": lines, **extra,
    })
    assert response.status_code == 201, response.text
    return response.json()


def expected_line_total(quantity: str, rate: str) -> str:
    return format(
        (Decimal(quantity) * Decimal(rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        "f",
    )


def test_criterion_1_item_total_is_quantity_times_unit_rate(client, world):
    act_as(client, world.a.manager)
    cases = [("2.5", "45.50"), ("0.333", "10.005"), ("1", "0.005"),
             ("1", "0.0049"), ("12", "54"), ("7.125", "0.4444")]

    bill = create(client, world.a, "PUR02-C1", [line(world.a, q, r) for q, r in cases])

    assert [l["line_total"] for l in bill["items"]] == [
        expected_line_total(q, r) for q, r in cases
    ]
    # 2.5 × 45.50 = 113.75; 0.333 × 10.005 = 3.331665 → 3.33;
    # 1 × 0.005 = 0.005 → 0.01 (half up); 1 × 0.0049 → 0.00.
    assert [l["line_total"] for l in bill["items"]][:4] == ["113.75", "3.33", "0.01", "0.00"]


def test_criterion_2_discount_and_charges_are_recorded_separately(client, db, world):
    act_as(client, world.a.admin)

    bill = create(client, world.a, "PUR02-C2", [line(world.a, "10", "10")],
                  discount="12.50", extra_charges="7.25")

    assert (bill["subtotal"], bill["discount"], bill["extra_charges"]) == (
        "100.00", "12.50", "7.25",
    )
    db.expire_all()
    stored = db.get(Purchase, bill["id"])
    assert (Decimal(str(stored.discount)), Decimal(str(stored.extra_charges))) == (
        Decimal("12.50"), Decimal("7.25"),
    )
    # Neither is folded into the lines.
    assert [Decimal(str(i.line_total)) for i in
            db.query(PurchaseItem).filter_by(purchase_id=bill["id"])] == [Decimal("100.00")]


def test_criterion_3_bill_total_includes_discount_and_charges(client, db, world):
    act_as(client, world.a.manager)

    for invoice, lines, discount, charges in [
        ("PUR02-C3-A", [("2.5", "45.50"), ("0.333", "10.005")], "1.08", "2.00"),
        ("PUR02-C3-B", [("1", "99.99")], "0", "0"),
        ("PUR02-C3-C", [("3", "33.333")], "99.99", "0.01"),   # discount = subtotal
    ]:
        bill = create(client, world.a, invoice, [line(world.a, q, r) for q, r in lines],
                      discount=discount, extra_charges=charges)
        subtotal = sum(Decimal(l["line_total"]) for l in bill["items"])
        assert Decimal(bill["subtotal"]) == subtotal
        assert Decimal(bill["grand_total"]) == (
            subtotal - Decimal(discount) + Decimal(charges)
        ), invoice

    # A discount larger than the subtotal is refused, so a total can never
    # go below the charges.
    refused = client.post(BILLS, json={
        "supplier_id": world.a.supplier.id, "invoice_number": "PUR02-C3-D",
        "purchase_date": "2026-11-03", "items": [line(world.a, "1", "10")],
        "discount": "10.01",
    })
    assert refused.status_code == 422


def test_criterion_4_purchase_rates_stay_available_unchanged(client, db, world):
    act_as(client, world.a.admin)
    first = create(client, world.a, "PUR02-C4-A", [line(world.a, "5", "45.50")])
    # Later purchases of the same item at other rates do not touch it.
    create(client, world.a, "PUR02-C4-B", [line(world.a, "5", "52.25")])
    create(client, world.a, "PUR02-C4-C", [line(world.a, "5", "39.0075")])

    again = client.get(f"{BILLS}{first['id']}").json()

    assert Decimal(again["items"][0]["unit_rate"]) == Decimal("45.50")
    assert again["items"][0]["line_total"] == "227.50"
    assert again["items"][0]["item_name"] == "Rice"
    rates = sorted(
        Decimal(str(i.unit_rate)) for i in db.query(PurchaseItem).filter_by(item_id=world.a.item.id)
    )
    assert rates == [Decimal("39.0075"), Decimal("45.50"), Decimal("52.25")]

    # Recorded bills cannot be edited or deleted through the API.
    for method in ("put", "patch", "delete"):
        response = getattr(client, method)(f"{BILLS}{first['id']}", **(
            {"json": {"items": []}} if method != "delete" else {}
        ))
        assert response.status_code == 405, (method, response.status_code)


def test_criterion_5_totals_use_exact_decimal_arithmetic(client, world):
    act_as(client, world.a.manager)

    # Classic floating-point traps: 0.1 × 3 and sums of tenths.
    bill = create(client, world.a, "PUR02-C5", [
        line(world.a, "3", "0.1"),
        line(world.a, "0.1", "0.2"),
        line(world.a, "0.7", "0.1"),
    ], discount="0.01", extra_charges="0.03")

    assert [l["line_total"] for l in bill["items"]] == ["0.30", "0.02", "0.07"]
    assert bill["subtotal"] == "0.39"
    assert bill["grand_total"] == "0.41"
    assert 0.1 * 3 != 0.3      # what binary floating point would have done
