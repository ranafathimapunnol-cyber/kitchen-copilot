"""
PUR04: supplier bill entry (the API behind the bill screen) and the
purchases-versus-payments period report.

Self-contained: in-memory SQLite and no project conftest, so it runs
without PostgreSQL:

    pytest --noconftest tests/test_pur04_bills_and_report.py

The PostgreSQL versions of the report queries are in
test_pur04_postgres.py.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.models import AuditLog, StaffAccessAssignment, Supplier
from app.models.purchases import Purchase, PurchaseItem, SupplierPayment

from tests.test_operational_authority import (  # noqa: F401 (fixtures)
    _campus,
    act_as,
    client,
    db,
    grant,
    make_bill,
    pay,
    world,
)

BILLS = "/api/purchases/"
BILL_LIST = "/api/supplier-balances/bills"
REPORT = "/api/reports/purchases-vs-payments"


def rice(place, quantity, rate, **extra):
    return {"item_id": place.item.id, "quantity": quantity,
            "unit_id": place.kg.id, "unit_rate": rate, **extra}


def bill_payload(place, invoice, lines, **extra):
    return {"supplier_id": place.supplier.id, "invoice_number": invoice,
            "purchase_date": "2026-11-03", "items": lines, **extra}


def dated_bill(db, place, invoice, total, day, supplier=None):
    bill = make_bill(db, place, invoice, total, supplier)
    bill.purchase_date = day
    db.commit()
    return bill


def report(client, date_from, date_to, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return client.get(
        f"{REPORT}?date_from={date_from}&date_to={date_to}"
        + (f"&{query}" if query else "")
    )


# ============================================================
# BILL ENTRY
# ============================================================

@pytest.mark.parametrize("role", ["admin", "manager"])
def test_admin_and_manager_enter_multi_line_bills_exactly(
    client, db, world, role
):
    actor = getattr(world.a, role)
    act_as(client, actor)

    response = client.post(BILLS, json=bill_payload(world.a, "ENTRY-1", [
        rice(world.a, "2.5", "45.50", remarks="Sona masoori"),
        # 0.333 × 10.005 = 3.331665 → 3.33 (half up, to the paisa)
        rice(world.a, "0.333", "10.005"),
    ], discount="1.08", extra_charges="2.00", remarks="Weekly grains"))

    assert response.status_code == 201, response.text
    bill = response.json()
    assert bill["subtotal"] == "117.08"
    assert bill["discount"] == "1.08"
    assert bill["extra_charges"] == "2.00"
    assert bill["grand_total"] == "118.00"
    assert bill["status"] == "DRAFT"
    assert [line["line_total"] for line in bill["items"]] == ["113.75", "3.33"]
    first = bill["items"][0]
    assert (first["item_name"], first["category_name"], first["unit_symbol"]) == (
        "Rice", "Grains", "kg",
    )
    assert Decimal(first["unit_rate"]) == Decimal("45.50")
    assert first["remarks"] == "Sona masoori"

    audit = db.query(AuditLog).filter_by(
        entity_type="PURCHASE", entity_id=bill["id"]
    ).one()
    assert audit.user_id == actor.id

    listed = client.get(f"{BILL_LIST}?search=entry-1").json()["items"]
    assert [(row["invoice_number"], row["grand_total"], row["payment_status"])
            for row in listed] == [("ENTRY-1", "118.00", "UNPAID")]


def test_bill_entry_rejections_save_nothing(client, db, world):
    act_as(client, world.a.manager)
    before = db.query(Purchase).count()

    cases = [
        (bill_payload(world.a, "A-INV-1", [rice(world.a, "1", "1")]), 409),
        (bill_payload(world.a, "BAD-DISC", [rice(world.a, "1", "10")],
                      discount="10.01"), 422),
        (bill_payload(world.a, "BAD-QTY", [rice(world.a, "1.0005", "1")]), 422),
        (bill_payload(world.a, "BAD-RATE", [rice(world.a, "1", "1.00005")]), 422),
        (bill_payload(world.a, "ZERO-QTY", [rice(world.a, "0", "1")]), 422),
        (bill_payload(world.a, "NO-LINES", []), 422),
        (bill_payload(world.a, "   ", [rice(world.a, "1", "1")]), 422),
        (bill_payload(world.a, "OTHER-ITEM",
                      [{**rice(world.a, "1", "1"), "item_id": world.b.item.id}]), 404),
        (bill_payload(world.a, "OTHER-UNIT",
                      [{**rice(world.a, "1", "1"), "unit_id": world.b.kg.id}]), 404),
        ({**bill_payload(world.a, "OTHER-SUP", [rice(world.a, "1", "1")]),
          "supplier_id": world.b.supplier.id}, 404),
    ]

    for payload, expected in cases:
        response = client.post(BILLS, json=payload)
        assert response.status_code == expected, (payload["invoice_number"], response.text)

    assert db.query(Purchase).count() == before
    assert db.query(PurchaseItem).count() == 0


def test_staff_cannot_enter_bills_without_an_existing_create_grant(
    client, db, world
):
    act_as(client, world.a.staff)
    payload = bill_payload(world.a, "STAFF-1", [rice(world.a, "1", "1")])
    assert client.post(BILLS, json=payload).status_code == 403

    # Read does not imply create.
    grant(db, world.a.staff, world.a.admin, "purchase_bill.read")
    assert client.post(BILLS, json=payload).status_code == 403
    assert client.get(BILL_LIST).status_code == 200


def test_bill_list_filters_by_date_and_invoice(client, db, world):
    dated_bill(db, world.a, "OCT-100", "10.00", date(2026, 10, 15))
    dated_bill(db, world.a, "NOV_50%", "20.00", date(2026, 11, 10))
    act_as(client, world.a.admin)

    def invoices(query):
        response = client.get(f"{BILL_LIST}?{query}")
        assert response.status_code == 200, response.text
        return [row["invoice_number"] for row in response.json()["items"]]

    assert invoices("date_from=2026-11-01&date_to=2026-11-30") == ["NOV_50%", "A-INV-1"]
    assert invoices("date_to=2026-10-31") == ["OCT-100"]
    assert invoices("search=oct") == ["OCT-100"]
    # "_" and "%" are matched literally, not as wildcards.
    assert invoices("search=v_5") == ["NOV_50%"]
    assert invoices("search=50%25") == ["NOV_50%"]
    assert invoices("search=a_inv") == []
    assert client.get(
        f"{BILL_LIST}?date_from=2026-11-02&date_to=2026-11-01"
    ).status_code == 422


# ============================================================
# PURCHASES VERSUS PAYMENTS REPORT
# ============================================================

@pytest.fixture
def ledger(db, world):
    """Campus A: an October bill partly paid in October, November bills and
    payments, and a second supplier. Campus B has its own activity."""
    a = world.a
    other = Supplier(campus_id=a.campus.id, name="Other A")
    db.add(other)
    db.commit()

    october = dated_bill(db, a, "A-OCT", "500.00", date(2026, 10, 20))
    november = dated_bill(db, a, "A-NOV", "300.00", date(2026, 11, 10))
    other_bill = dated_bill(db, a, "O-1", "200.00", date(2026, 11, 15), other)

    return {"other": other, "october": october, "november": november,
            "other_bill": other_bill}


def record_ledger_payments(client, world, ledger):
    act_as(client, world.a.admin)
    for bill, amount, method, day in [
        (ledger["october"], "200.00", "CASH", "2026-10-25"),         # before
        (ledger["october"], "100.00", "UPI", "2026-11-02"),          # in
        (world.a.bill, "400.00", "BANK_TRANSFER", "2026-11-05"),     # in
        (world.a.bill, "50.00", "CASH", "2026-11-06"),               # in
        (ledger["other_bill"], "200.00", "CASH", "2026-11-16"),      # after
    ]:
        response = pay(client, bill, amount, payment_method=method,
                       payment_date=day)
        assert response.status_code == 201, response.text
    act_as(client, world.b.admin)
    assert pay(client, world.b.bill, "100.00", payment_method="CASH",
               payment_date="2026-11-03").status_code == 201


@pytest.mark.parametrize("role", ["admin", "manager"])
def test_report_separates_purchases_from_payments(
    client, world, ledger, role
):
    record_ledger_payments(client, world, ledger)
    act_as(client, getattr(world.a, role))

    response = report(client, "2026-11-01", "2026-11-15")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["period"] == {"date_from": "2026-11-01", "date_to": "2026-11-15"}
    assert body["filters"] == {"supplier_id": None, "supplier_name": None}
    assert body["currency"] == "INR"

    rows = {row["supplier_name"]: row for row in body["suppliers"]}
    assert set(rows) == {"Supplier A", "Other A"}       # campus B excluded
    assert {k: rows["Supplier A"][k] for k in (
        "bill_count", "billed", "payment_count", "paid", "paid_cash",
        "opening_balance", "closing_balance")} == {
        "bill_count": 2, "billed": "1300.00",
        "payment_count": 3, "paid": "550.00", "paid_cash": "50.00",
        "opening_balance": "300.00", "closing_balance": "1050.00",
    }
    assert {k: rows["Other A"][k] for k in (
        "billed", "paid", "opening_balance", "closing_balance")} == {
        "billed": "200.00", "paid": "0.00",
        "opening_balance": "0.00", "closing_balance": "200.00",
    }

    totals = body["totals"]
    assert {k: totals[k] for k in (
        "supplier_count", "bill_count", "billed", "payment_count", "paid",
        "paid_cash", "opening_balance", "closing_balance")} == {
        "supplier_count": 2, "bill_count": 3, "billed": "1500.00",
        "payment_count": 3, "paid": "550.00", "paid_cash": "50.00",
        "opening_balance": "300.00", "closing_balance": "1250.00",
    }
    assert totals["paid_by_method"] == [
        {"payment_method": "CASH", "payment_count": 1, "amount": "50.00"},
        {"payment_method": "BANK_TRANSFER", "payment_count": 1, "amount": "400.00"},
        {"payment_method": "UPI", "payment_count": 1, "amount": "100.00"},
        {"payment_method": "CHEQUE", "payment_count": 0, "amount": "0.00"},
        {"payment_method": "OTHER", "payment_count": 0, "amount": "0.00"},
    ]


def test_report_reconciles_row_by_row_and_with_balances(client, world, ledger):
    record_ledger_payments(client, world, ledger)
    act_as(client, world.a.manager)

    body = report(client, "2026-01-01", date.today().isoformat()).json()

    for row in body["suppliers"] + [body["totals"]]:
        assert Decimal(row["closing_balance"]) == (
            Decimal(row["opening_balance"]) + Decimal(row["billed"])
            - Decimal(row["paid"])
        )
    assert sum(Decimal(m["amount"]) for m in body["totals"]["paid_by_method"]) \
        == Decimal(body["totals"]["paid"])

    # A period ending today closes at what the balances page shows as owed.
    balances = {
        row["supplier_id"]: Decimal(row["outstanding"]) - Decimal(row["overpaid"])
        for row in client.get("/api/supplier-balances").json()["items"]
    }
    assert {row["supplier_id"]: Decimal(row["closing_balance"])
            for row in body["suppliers"]} == balances


def test_report_period_boundaries_are_inclusive(client, world, ledger):
    record_ledger_payments(client, world, ledger)
    act_as(client, world.a.admin)

    on_the_day = report(client, "2026-11-15", "2026-11-15").json()["totals"]
    assert (on_the_day["bill_count"], on_the_day["billed"]) == (1, "200.00")

    next_day = report(client, "2026-11-16", "2026-11-16").json()["totals"]
    assert (next_day["bill_count"], next_day["payment_count"],
            next_day["paid"], next_day["paid_cash"]) == (0, 1, "200.00", "200.00")


def test_report_supplier_filter(client, world, ledger):
    record_ledger_payments(client, world, ledger)
    act_as(client, world.a.admin)

    body = report(client, "2026-11-01", "2026-11-30",
                  supplier_id=ledger["other"].id).json()

    assert body["filters"] == {"supplier_id": ledger["other"].id,
                               "supplier_name": "Other A"}
    assert [row["supplier_name"] for row in body["suppliers"]] == ["Other A"]
    assert body["totals"]["paid"] == "200.00"
    assert [m["amount"] for m in body["totals"]["paid_by_method"]][0] == "200.00"

    assert report(client, "2026-11-01", "2026-11-30",
                  supplier_id=world.b.supplier.id).status_code == 404


def test_report_shows_overpayment_as_a_credit(client, db, world):
    db.add(SupplierPayment(
        campus_id=world.a.campus.id, purchase_id=world.a.bill.id,
        payment_date=date(2026, 11, 3), amount=Decimal("1100.00"),
        payment_method="CHEQUE", created_by=world.a.admin.id,
    ))
    db.commit()
    act_as(client, world.a.admin)

    row = report(client, "2026-11-01", "2026-11-30").json()["suppliers"][0]

    assert row["closing_balance"] == "-100.00"


def test_report_validation(client, world):
    act_as(client, world.a.admin)

    assert client.get(REPORT).status_code == 422
    assert client.get(f"{REPORT}?date_from=2026-11-01").status_code == 422
    assert report(client, "2026-11-02", "2026-11-01").status_code == 422
    assert report(client, "2026-11-01", "not-a-date").status_code == 422


def test_empty_period_reports_zeros(client, world):
    act_as(client, world.a.admin)

    body = report(client, "2025-01-01", "2025-01-31").json()

    assert body["suppliers"] == []
    assert body["totals"]["billed"] == "0.00"
    assert body["totals"]["paid"] == "0.00"
    assert all(m["amount"] == "0.00" for m in body["totals"]["paid_by_method"])


def test_report_access_follows_existing_assignments(client, db, world):
    act_as(client, world.a.staff)
    assert report(client, "2026-11-01", "2026-11-30").status_code == 403

    grant(db, world.a.staff, world.a.admin, "purchase_bill.read")
    rows_before = sorted(
        (r.permission_id, r.is_active)
        for r in db.query(StaffAccessAssignment).filter_by(staff_user_id=world.a.staff.id)
    )
    assert report(client, "2026-11-01", "2026-11-30").status_code == 200

    db.query(StaffAccessAssignment).filter_by(
        staff_user_id=world.a.staff.id
    ).update({"is_active": False})
    db.commit()
    assert report(client, "2026-11-01", "2026-11-30").status_code == 403

    db.expire_all()
    rows_after = sorted(
        (r.permission_id, True)
        for r in db.query(StaffAccessAssignment).filter_by(staff_user_id=world.a.staff.id)
    )
    assert [p for p, _ in rows_after] == [p for p, _ in rows_before]


def test_report_is_campus_isolated(client, world, ledger):
    record_ledger_payments(client, world, ledger)
    act_as(client, world.b.admin)

    body = report(client, "2026-11-01", "2026-11-30").json()

    assert [row["supplier_name"] for row in body["suppliers"]] == ["Supplier B"]
    assert body["totals"]["billed"] == "500.00"
    assert body["totals"]["paid"] == "100.00"
