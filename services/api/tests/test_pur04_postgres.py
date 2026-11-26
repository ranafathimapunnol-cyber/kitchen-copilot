"""
PUR04 supplier payments on PostgreSQL.

Uses the shared tests/conftest.py fixtures, so it runs against
kitchen_copilot_test_db on the Docker database server. Run it only as
described in docs/DEVELOPMENT-SAFETY.md section 3.3; from the host shell
the conftest would reach the Homebrew server instead.

Covers what the in-memory SQLite suites cannot:
- concurrent payments on one bill (SELECT ... FOR UPDATE serialises them);
- exact NUMERIC(18,2) arithmetic at the column's limits;
- case-insensitive duplicate references through PostgreSQL lower();
- the balance, bill-list and dashboard queries on a real server.
"""

import threading
import time
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.api.routes import supplier_payments
from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models import AuditLog, StaffAccessAssignment, Supplier, User, UserRole
from app.models.purchases import Purchase, SupplierPayment

from tests.test_authorization import authenticate_as, create_test_user

BILL_DATE = date(2026, 11, 1)
PAY_DATE = "2026-11-05"


def make_bill(db, setup_data, invoice, total, supplier=None):
    if supplier is None:
        supplier = Supplier(campus_id=setup_data["campus"].id, name=f"S-{invoice}")
        db.add(supplier)
        db.flush()
    bill = Purchase(
        campus_id=setup_data["campus"].id, supplier_id=supplier.id,
        invoice_number=invoice, purchase_date=BILL_DATE,
        subtotal=Decimal(total), discount=0, extra_charges=0,
        grand_total=Decimal(total), status="DRAFT",
        created_by=setup_data["user"].id,
    )
    db.add(bill)
    db.commit()
    return bill


def pay(client, bill, amount, **extra):
    # Threads must pass the id: reading bill.id after a commit reloads it
    # through the shared test session, which is not thread-safe.
    bill_id = bill if isinstance(bill, int) else bill.id
    return client.post(
        f"/api/purchases/{bill_id}/payments",
        json={"payment_date": PAY_DATE, "amount": amount,
              "payment_method": "BANK_TRANSFER", **extra},
    )


# ============================================================
# CONCURRENCY: separate sessions, separate event loops
# ============================================================

@pytest.fixture
def concurrent_clients(db, setup_data):
    """Two independent clients, each request in its own database session,
    as in production. The shared-session conftest client cannot race."""

    # A private, unpooled engine. Its connections must not go back into the
    # shared test pool: they would carry prepared statements into later
    # tests, after the per-test drop_all/create_all has recreated the enum
    # types ("cached plan must not change result type").
    engine = create_engine(
        db.get_bind().url,
        poolclass=NullPool,
        connect_args={"prepare_threshold": None},
    )
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
        for _ in range(2):
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
        app.dependency_overrides.clear()
        engine.dispose()


def race(clients, bill, amounts, monkeypatch, **extra):
    """Send one payment per client at the same instant. paid_total is
    slowed down, so without the row lock both requests would read the
    same balance and both would be saved."""

    original = supplier_payments.paid_total

    def slow_paid_total(*args, **kwargs):
        value = original(*args, **kwargs)
        time.sleep(0.4)
        return value

    monkeypatch.setattr(supplier_payments, "paid_total", slow_paid_total)

    bill_id = bill.id  # resolved before the threads start
    barrier = threading.Barrier(len(clients))
    statuses = [None] * len(clients)

    def worker(index):
        barrier.wait()
        statuses[index] = pay(clients[index], bill_id, amounts[index], **extra).status_code

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(len(clients))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return sorted(statuses)


def saved(db, bill):
    db.expire_all()
    rows = db.query(SupplierPayment).filter_by(purchase_id=bill.id).all()
    return rows, sum((row.amount for row in rows), Decimal("0"))


def test_race_window_is_real_without_the_row_lock(db, setup_data, concurrent_clients, monkeypatch):
    """Control: with the lock switched off, the same race saves both
    payments. This proves the concurrency tests below can fail, so their
    passing is evidence that SELECT ... FOR UPDATE prevents it."""
    original = supplier_payments.get_campus_bill
    monkeypatch.setattr(
        supplier_payments, "get_campus_bill",
        lambda db_, user, purchase_id, lock=False: original(db_, user, purchase_id, lock=False),
    )
    bill = make_bill(db, setup_data, "RACE-NOLOCK", "1000.00")

    statuses = race(concurrent_clients, bill, ["1000.00", "1000.00"], monkeypatch)

    _rows, total = saved(db, bill)
    assert statuses == [201, 201]
    assert total == Decimal("2000.00")


def test_concurrent_full_payments_save_only_one(db, setup_data, concurrent_clients, monkeypatch):
    bill = make_bill(db, setup_data, "RACE-FULL", "1000.00")

    statuses = race(concurrent_clients, bill, ["1000.00", "1000.00"], monkeypatch)

    rows, total = saved(db, bill)
    assert statuses == [201, 409]
    assert len(rows) == 1 and total == Decimal("1000.00")
    assert db.query(AuditLog).filter_by(entity_type="SUPPLIER_PAYMENT").count() == 1


def test_concurrent_partial_payments_cannot_overpay(db, setup_data, concurrent_clients, monkeypatch):
    bill = make_bill(db, setup_data, "RACE-PART", "1000.00")

    statuses = race(concurrent_clients, bill, ["600.00", "600.00"], monkeypatch)

    rows, total = saved(db, bill)
    assert statuses == [201, 422]
    assert total == Decimal("600.00")


def test_concurrent_duplicate_reference_saves_once(db, setup_data, concurrent_clients, monkeypatch):
    bill = make_bill(db, setup_data, "RACE-REF", "1000.00")

    statuses = race(concurrent_clients, bill, ["100.00", "100.00"], monkeypatch,
                    reference_number="UTR-RACE")

    rows, _total = saved(db, bill)
    assert statuses == [201, 409]
    assert len(rows) == 1


def test_concurrent_payments_on_different_bills_both_succeed(db, setup_data, concurrent_clients, monkeypatch):
    # The lock is per bill, not per table.
    first = make_bill(db, setup_data, "RACE-A", "100.00")
    second = make_bill(db, setup_data, "RACE-B", "100.00")
    original = supplier_payments.paid_total
    windows = []
    windows_lock = threading.Lock()

    def slow_paid_total(*args, **kwargs):
        # Runs while the request holds its bill's row lock.
        entered = time.monotonic()
        time.sleep(1.0)
        result = original(*args, **kwargs)
        with windows_lock:
            windows.append((entered, time.monotonic()))
        return result

    monkeypatch.setattr(supplier_payments, "paid_total", slow_paid_total)

    barrier = threading.Barrier(2)
    statuses = {}
    targets = [("RACE-A", first.id), ("RACE-B", second.id)]  # resolved up front

    def worker(client, invoice, bill_id):
        barrier.wait()
        statuses[invoice] = pay(client, bill_id, "100.00").status_code

    threads = [threading.Thread(target=worker, args=(concurrent_clients[i], *targets[i]))
               for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert statuses == {"RACE-A": 201, "RACE-B": 201}
    # Each request sleeps 1 s while holding its own bill's lock. Had one
    # waited for the other's lock, its locked work could only start after
    # the other committed, so the two windows would not overlap. (Measured
    # as overlap, not elapsed time, so a busy machine cannot fail the test.)
    (_first_in, first_out), (second_in, _second_out) = sorted(windows)
    assert len(windows) == 2 and second_in < first_out, windows


# ============================================================
# OVERPAYMENT AND DECIMAL PRECISION ON NUMERIC(18,2)
# ============================================================

def test_overpayment_is_refused_to_the_paisa(client, db, setup_data):
    bill = make_bill(db, setup_data, "PAISA", "1000.00")

    assert pay(client, bill, "999.99").status_code == 201
    assert pay(client, bill, "0.02").status_code == 422
    last = pay(client, bill, "0.01")

    assert last.status_code == 201
    assert last.json()["bill"]["payment_status"] == "PAID"
    assert last.json()["bill"]["outstanding"] == "0.00"
    assert pay(client, bill, "0.01").status_code == 409


def test_many_small_payments_sum_exactly(client, db, setup_data):
    bill = make_bill(db, setup_data, "SMALL", "0.30")

    for _ in range(3):
        assert pay(client, bill, "0.10").status_code == 201

    body = client.get(f"/api/purchases/{bill.id}/payments").json()["bill"]
    assert body["paid_total"] == "0.30"
    assert body["payment_status"] == "PAID"


def test_amounts_at_the_column_limit_stay_exact(client, db, setup_data):
    bill = make_bill(db, setup_data, "HUGE", "9999999999999999.99")

    response = pay(client, bill, "1234567890123456.78")

    assert response.status_code == 201, response.text
    assert response.json()["bill"]["outstanding"] == "8765432109876543.21"
    balances = client.get("/api/supplier-balances").json()
    assert balances["totals"]["outstanding"] == "8765432109876543.21"
    assert balances["totals"]["total_paid"] == "1234567890123456.78"


def test_three_decimal_amount_is_rejected(client, db, setup_data):
    bill = make_bill(db, setup_data, "THREE", "10.00")
    assert pay(client, bill, "1.005").status_code == 422
    assert db.query(SupplierPayment).count() == 0


# ============================================================
# DUPLICATE REFERENCES THROUGH POSTGRESQL lower()
# ============================================================

def test_duplicate_reference_is_case_insensitive(client, db, setup_data):
    bill = make_bill(db, setup_data, "REF", "1000.00")
    other = make_bill(db, setup_data, "REF-2", "1000.00")

    assert pay(client, bill, "10.00", reference_number="UTR-AbC-9").status_code == 201
    assert pay(client, bill, "10.00", reference_number="utr-abc-9").status_code == 409
    assert pay(client, bill, "10.00", reference_number=" UTR-ABC-9 ").status_code == 409
    assert pay(client, other, "10.00", reference_number="UTR-ABC-9").status_code == 201


# ============================================================
# BALANCE QUERIES ON A REAL SERVER
# ============================================================

def test_balances_bill_list_and_overpaid_on_postgres(client, db, setup_data):
    supplier = Supplier(campus_id=setup_data["campus"].id, name="PG Supplier")
    db.add(supplier)
    db.flush()
    open_bill = make_bill(db, setup_data, "PG-OPEN", "500.50", supplier)
    over_bill = make_bill(db, setup_data, "PG-OVER", "100.00", supplier)
    make_bill(db, setup_data, "PG-ZERO", "0.00", supplier)
    db.add(SupplierPayment(campus_id=setup_data["campus"].id, purchase_id=over_bill.id,
                           payment_date=date(2026, 11, 2), amount=Decimal("100.25"),
                           payment_method="CASH", created_by=setup_data["user"].id))
    db.commit()
    assert pay(client, open_bill, "0.50").status_code == 201

    body = client.get(f"/api/supplier-balances?supplier_id={supplier.id}").json()
    assert body["items"] == [{
        "supplier_id": supplier.id, "supplier_name": "PG Supplier",
        "bill_count": 3, "open_bill_count": 1,
        "total_billed": "600.50", "total_paid": "100.75",
        "outstanding": "500.00", "overpaid": "0.25",
    }]

    bills = client.get(f"/api/supplier-balances/bills?supplier_id={supplier.id}").json()
    status = {row["invoice_number"]: row["payment_status"] for row in bills["items"]}
    assert status == {"PG-OPEN": "PARTIALLY_PAID", "PG-OVER": "OVERPAID", "PG-ZERO": "PAID"}

    open_only = client.get("/api/supplier-balances/bills?open_only=true").json()
    assert [row["invoice_number"] for row in open_only["items"]] == ["PG-OPEN"]


def test_payment_list_pages_and_totals_on_postgres(client, db, setup_data):
    bill = make_bill(db, setup_data, "PAGES", "1000.00")
    for day in range(1, 8):
        assert pay(client, bill, "1.10", payment_date=f"2026-11-0{day}").status_code == 201

    first = client.get("/api/supplier-payments?page=1&page_size=3").json()
    assert first["total"] == 7 and first["total_pages"] == 3
    assert first["total_paid"] == "7.70"
    assert [row["payment_date"] for row in first["items"]] == ["2026-11-07", "2026-11-06", "2026-11-05"]
    upi = client.get("/api/supplier-payments?payment_method=upi").json()
    assert upi["total"] == 0 and upi["total_paid"] == "0.00"


def test_dashboard_team_query_on_postgres(client, db, setup_data):
    campus_id = setup_data["campus"].id
    manager = create_test_user(db, campus_id, "KITCHEN_MANAGER")
    with_access = create_test_user(db, campus_id, "STAFF")
    create_test_user(db, campus_id, "STAFF")                  # no access
    retired = create_test_user(db, campus_id, "STAFF")
    retired.is_active = False
    from app.models.authorization import Permission
    permission = db.query(Permission).filter_by(permission_code="dashboard.read").one()
    db.add(StaffAccessAssignment(staff_user_id=with_access.id, permission_id=permission.id,
                                 assigned_by=setup_data["user"].id, is_active=True))
    db.commit()

    team = client.get("/api/dashboard/overview").json()["team"]
    assert team == {"active_admins": 1, "active_kitchen_managers": 1, "active_staff": 2,
                    "inactive_users": 1, "staff_without_access": 1}

    authenticate_as(client, manager)
    body = client.get("/api/dashboard/overview").json()
    assert "team" not in body and "payments" in body


def test_dashboard_payables_on_postgres(client, db, setup_data):
    bill = make_bill(db, setup_data, "DASH", "250.75")
    assert pay(client, bill, "100.25", payment_date=date.today().isoformat()).status_code == 201

    payments = client.get("/api/dashboard/overview").json()["payments"]
    assert payments["outstanding"] == "150.50"
    assert payments["paid_this_month"] == "100.25"
    assert payments["top_outstanding"][0]["outstanding"] == "150.50"


# ============================================================
# BILL ENTRY, BILL LIST AND THE PERIOD REPORT ON POSTGRESQL
# ============================================================

def dated(db, bill, day):
    bill.purchase_date = day
    db.commit()
    return bill


def test_bill_detail_names_lines_on_postgres(client):
    from tests.test_receipts import create_receipt_purchase

    records = create_receipt_purchase(client)

    bill = client.get(f"/api/purchases/{records['purchase_id']}").json()

    line = bill["items"][0]
    assert line["item_name"] == "Receipt Test Rice"
    assert line["unit_symbol"] == "rg"
    assert line["category_name"]
    assert line["line_total"] == "100.00"          # 2000 g × 0.05
    assert bill["grand_total"] == "100.00"


def test_bill_list_search_and_dates_on_postgres(client, db, setup_data):
    supplier = Supplier(campus_id=setup_data["campus"].id, name="Search Supplier")
    db.add(supplier)
    db.flush()
    dated(db, make_bill(db, setup_data, "OCT-100", "10.00", supplier), date(2026, 10, 15))
    dated(db, make_bill(db, setup_data, "NOV_50%", "20.00", supplier), date(2026, 11, 10))

    def invoices(query):
        response = client.get(f"/api/supplier-balances/bills?{query}")
        assert response.status_code == 200, response.text
        return [row["invoice_number"] for row in response.json()["items"]]

    # LIKE wildcards typed by the user match literally (ESCAPE on PostgreSQL).
    assert invoices("search=v_5") == ["NOV_50%"]
    assert invoices("search=50%25") == ["NOV_50%"]
    assert invoices("search=OCT") == ["OCT-100"]
    assert invoices("search=c_1") == []
    assert invoices("date_from=2026-11-01&date_to=2026-11-30") == ["NOV_50%"]


def test_purchases_vs_payments_report_on_postgres(client, db, setup_data):
    supplier = Supplier(campus_id=setup_data["campus"].id, name="Report Supplier")
    db.add(supplier)
    db.flush()
    october = dated(db, make_bill(db, setup_data, "R-OCT", "500.00", supplier), date(2026, 10, 20))
    november = dated(db, make_bill(db, setup_data, "R-NOV", "300.00", supplier), date(2026, 11, 10))
    first = make_bill(db, setup_data, "R-1", "1000.00", supplier)   # 1 Nov
    october_id, first_id = october.id, first.id

    for bill_id, amount, method, day in [
        (october_id, "200.00", "CASH", "2026-10-25"),
        (october_id, "100.00", "UPI", "2026-11-02"),
        (first_id, "400.00", "BANK_TRANSFER", "2026-11-05"),
        (first_id, "50.25", "CASH", "2026-11-06"),
    ]:
        assert pay(client, bill_id, amount, payment_method=method,
                   payment_date=day).status_code == 201

    response = client.get(
        "/api/reports/purchases-vs-payments"
        f"?date_from=2026-11-01&date_to=2026-11-15&supplier_id={supplier.id}"
    )

    assert response.status_code == 200, response.text
    body = response.json()
    row = body["suppliers"][0]
    assert {k: row[k] for k in ("bill_count", "billed", "payment_count", "paid",
                                "paid_cash", "opening_balance", "closing_balance")} == {
        "bill_count": 2, "billed": "1300.00", "payment_count": 3, "paid": "550.25",
        "paid_cash": "50.25", "opening_balance": "300.00", "closing_balance": "1049.75",
    }
    assert [(m["payment_method"], m["amount"]) for m in body["totals"]["paid_by_method"]] == [
        ("CASH", "50.25"), ("BANK_TRANSFER", "400.00"), ("UPI", "100.00"),
        ("CHEQUE", "0.00"), ("OTHER", "0.00"),
    ]
    assert body["filters"]["supplier_name"] == "Report Supplier"
    assert november.invoice_number == "R-NOV"


# ============================================================
# PUR02 CRITERION 5 AND REPORT EXPORTS ON POSTGRESQL
# ============================================================

def make_master_data(client):
    """A supplier and an item in kilograms, created through the API."""
    category = client.post("/api/master/categories", json={"name": "PG Grains"}).json()
    kg = client.post("/api/master/units", json={
        "name": "PG Kilogram", "symbol": "pgkg", "dimension": "weight"}).json()
    supplier = client.post("/api/master/suppliers", json={"name": "PG Bill Supplier"}).json()
    item = client.post("/api/master/items", json={
        "name": "PG Rice", "category_id": category["id"],
        "standard_unit_id": kg["id"], "minimum_stock": "0"}).json()
    return supplier["id"], item["id"], kg["id"]


def test_pur02_bill_totals_are_exact_at_scale_on_postgres(client, db):
    from decimal import ROUND_HALF_UP

    from app.models.purchases import PurchaseItem

    supplier_id, item_id, kg_id = make_master_data(client)
    lines = [("123456.789", "98765.4321"), ("999999999999.999", "9.9999"),
             ("0.333", "10.005"), ("3", "0.1")]

    response = client.post("/api/purchases/", json={
        "supplier_id": supplier_id, "invoice_number": "PG-PUR02-SCALE",
        "purchase_date": "2026-11-03", "discount": "0.07", "extra_charges": "1.05",
        "items": [{"item_id": item_id, "quantity": q, "unit_id": kg_id, "unit_rate": r}
                  for q, r in lines],
    })

    assert response.status_code == 201, response.text
    bill = response.json()
    expected = [(Decimal(q) * Decimal(r)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                for q, r in lines]
    assert [Decimal(l["line_total"]) for l in bill["items"]] == expected
    assert [l["line_total"] for l in bill["items"]] == [format(e, "f") for e in expected]
    subtotal = sum(expected, Decimal("0"))
    assert bill["subtotal"] == format(subtotal, "f")
    assert bill["grand_total"] == format(subtotal - Decimal("0.07") + Decimal("1.05"), "f")

    # Stored exactly in NUMERIC columns, rates included.
    db.expire_all()
    stored = db.query(PurchaseItem).filter_by(purchase_id=bill["id"]).order_by(PurchaseItem.id).all()
    assert [row.line_total for row in stored] == expected
    assert [row.unit_rate for row in stored] == [Decimal(r) for _q, r in lines]


def test_report_exports_on_postgres(client, db, setup_data):
    from tests.test_pur04_exports import pdf_text, read_xlsx, row_named

    from app.models import AuditLog
    from app.services.report_exports import format_inr

    supplier = Supplier(campus_id=setup_data["campus"].id, name="Export Supplier")
    db.add(supplier)
    db.flush()
    bill_id = make_bill(db, setup_data, "EXP-1", "1234567.89", supplier).id
    assert pay(client, bill_id, "234567.80", payment_method="CASH").status_code == 201
    period = {"date_from": "2026-11-01", "date_to": "2026-11-30"}

    screen = client.get("/api/reports/purchases-vs-payments", params=period).json()
    xlsx = client.post("/api/reports/purchases-vs-payments/export",
                       json={"format": "xlsx", **period})
    pdf = client.post("/api/reports/purchases-vs-payments/export",
                      json={"format": "pdf", **period})

    assert xlsx.status_code == 200 and pdf.status_code == 200
    total = row_named(read_xlsx(xlsx.content)["Report"], "Total")
    assert total[3] == Decimal(screen["totals"]["billed"]) == Decimal("1234567.89")
    assert total[5] == Decimal(screen["totals"]["paid"]) == Decimal("234567.80")
    assert total[7] == Decimal(screen["totals"]["closing_balance"]) == Decimal("1000000.09")
    text = pdf_text(pdf.content)
    assert format_inr("1234567.89") == "₹12,34,567.89" and "₹12,34,567.89" in text
    assert "₹10,00,000.09" in text
    assert db.query(AuditLog).filter_by(action="EXPORT").count() == 2
