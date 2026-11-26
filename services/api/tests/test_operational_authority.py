"""
Role authority (confirmed 17 November 2026) and supplier payments (PUR04).

- ADMIN and KITCHEN_MANAGER have the same operational authority,
  including supplier bills, recording and viewing supplier payments, and
  supplier balances. There is no payment approval step.
- Creating users and managing permissions stay ADMIN-only.
- Permanent deletion stays ADMIN-only for every master record, including
  stock items, and for waste records. Kitchen Managers may deactivate.
- STAFF has only what was explicitly assigned. Existing assignments are
  honoured as stored and never changed by these features.
- Every operation is limited to the user's campus.

Self-contained: an in-memory SQLite database and no project conftest, so
it runs without PostgreSQL:

    pytest --noconftest tests/test_operational_authority.py
"""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    AuditLog,
    Campus,
    Category,
    Item,
    Module,
    Permission,
    StaffAccessAssignment,
    Supplier,
    Unit,
    User,
    UserRole,
)
from app.api.routes import supplier_payments
from app.models.purchases import Purchase, SupplierPayment

PASSWORD_HASH = hash_password("Password123!")

MODULES = {
    "dashboard": ("Dashboard", ["READ"]),
    "headcount": ("Headcount", ["CREATE", "READ", "UPDATE"]),
    "inventory": ("Inventory", ["CREATE", "READ", "UPDATE"]),
    "purchase_order": ("Purchase Order", ["CREATE", "READ", "UPDATE"]),
    "purchase_bill": ("Supplier Bills", ["CREATE", "READ", "UPDATE"]),
    "consumption": ("Consumption", ["CREATE", "READ", "UPDATE"]),
    "outsourced_food": ("Outsourced Food", ["CREATE", "READ", "UPDATE"]),
    "menu": ("Menu", ["CREATE", "READ", "UPDATE"]),
    "audit": ("Audit", ["READ"]),
    "waste_tracking": ("Waste Tracking", ["CREATE", "READ", "UPDATE"]),
    # Added by migration 0e7d99065bd3 (Stage 4 slice 4c, decision S1).
    "stock_count": ("Stock Counts", ["CREATE", "READ"]),
    # Added by migration ea00e5387c2f (Stage 5, decision 5-1).
    "meal": ("Meals", ["CREATE", "READ", "UPDATE"]),
    # Added by migration f3a8c2d61b47 (Stage 6, decision 6-3).
    "portion_standard": ("Portion Standards", ["CREATE", "READ", "UPDATE"]),
    "meal_plan": ("Meal Plans", ["CREATE", "READ", "UPDATE"]),
}

OPERATIONAL_READS = [
    "/api/dashboard/overview",
    "/api/master/items",
    "/api/master/categories",
    "/api/master/units",
    "/api/master/unit-conversions",
    "/api/master/suppliers",
    "/api/master/meal-sessions",
    "/api/master/menus",
    "/api/master/menu-main-items",
    "/api/purchases/",
    "/api/stock/movements",
    "/api/waste/records",
    "/api/supplier-payments",
    "/api/supplier-balances",
]


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _foreign_keys_on(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()

    for code, (name, actions) in MODULES.items():
        module = Module(name=name, code=code)
        session.add(module)
        session.flush()
        for action in actions:
            session.add(Permission(
                module_id=module.id,
                action=action,
                permission_code=f"{code}.{action.lower()}",
            ))
    session.commit()

    yield session

    session.close()
    # Meal dishes and leftovers reference each other (a carried-in line and
    # its source); drop the tables without checking foreign keys.
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    Base.metadata.drop_all(engine)
    engine.dispose()


def _campus(db, code):
    campus = Campus(name=f"Campus {code}", code=code)
    db.add(campus)
    db.flush()

    kg = Unit(campus_id=campus.id, name="Kilogram", symbol="kg",
              dimension="weight")
    category = Category(campus_id=campus.id, name="Grains")
    supplier = Supplier(campus_id=campus.id, name=f"Supplier {code}")
    db.add_all([kg, category, supplier])
    db.flush()

    item = Item(campus_id=campus.id, name="Rice", category_id=category.id,
                standard_unit_id=kg.id, minimum_stock=0)
    db.add(item)
    db.flush()

    def user(role, email):
        account = User(campus_id=campus.id, full_name=f"{role.value} {code}",
                       email=email, password_hash=PASSWORD_HASH, role=role,
                       is_active=True)
        db.add(account)
        db.flush()
        return account

    admin = user(UserRole.ADMIN, f"admin.{code}@test.com".lower())
    manager = user(UserRole.KITCHEN_MANAGER, f"km.{code}@test.com".lower())
    staff = user(UserRole.STAFF, f"staff.{code}@test.com".lower())

    return SimpleNamespace(campus=campus, kg=kg, category=category,
                           supplier=supplier, item=item, admin=admin,
                           manager=manager, staff=staff)


def make_bill(db, place, invoice, total, supplier=None):
    total = Decimal(total)
    bill = Purchase(
        campus_id=place.campus.id,
        supplier_id=(supplier or place.supplier).id,
        invoice_number=invoice,
        purchase_date=date(2026, 11, 1),
        subtotal=total, discount=0, extra_charges=0, grand_total=total,
        status="DRAFT",
        created_by=place.admin.id,
    )
    db.add(bill)
    db.commit()
    return bill


@pytest.fixture
def world(db):
    a = _campus(db, "A")
    b = _campus(db, "B")
    db.commit()

    a.bill = make_bill(db, a, "A-INV-1", "1000.00")
    b.bill = make_bill(db, b, "B-INV-1", "500.00")
    return SimpleNamespace(a=a, b=b)


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            csrf = test_client.get("/api/auth/csrf").json()["csrf_token"]
            test_client.headers.update({settings.CSRF_HEADER_NAME: csrf})
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


# ============================================================
# HELPERS
# ============================================================

def act_as(client, user):
    client.cookies.set(
        settings.ACCESS_COOKIE_NAME,
        create_access_token(user.id, user.password_hash),
    )


def grant(db, staff, admin, code):
    """An explicit STAFF assignment, written directly (as an older grant
    would exist), so non-assignable codes can be exercised too."""
    permission = db.query(Permission).filter_by(permission_code=code).one()
    db.add(StaffAccessAssignment(
        staff_user_id=staff.id, permission_id=permission.id,
        assigned_by=admin.id, is_active=True,
    ))
    db.commit()


def pay(client, bill, amount, **extra):
    return client.post(
        f"/api/purchases/{bill.id}/payments",
        json={"payment_date": "2026-11-05", "amount": amount,
              "payment_method": "BANK_TRANSFER", **extra},
    )


# ============================================================
# 1–2. ADMIN AND KITCHEN_MANAGER: EQUAL OPERATIONAL ACCESS
# ============================================================

@pytest.mark.parametrize("role", ["admin", "manager"])
@pytest.mark.parametrize("endpoint", OPERATIONAL_READS)
def test_admin_and_manager_have_operational_read_access(
    client, world, role, endpoint
):
    act_as(client, getattr(world.a, role))

    response = client.get(endpoint)

    assert response.status_code == 200, f"{role} {endpoint}: {response.text}"


def test_manager_holds_every_operational_permission(client, world):
    act_as(client, world.a.admin)
    admin_codes = set(client.get("/api/authorization/me").json()["permissions"])

    act_as(client, world.a.manager)
    manager_codes = set(
        client.get("/api/authorization/me").json()["permissions"]
    )

    assert manager_codes == admin_codes
    assert {"purchase_bill.create", "purchase_bill.read", "purchase_bill.update",
            "purchase_order.create", "purchase_order.read",
            "purchase_order.update", "audit.read"} <= manager_codes


def test_manager_can_manage_suppliers_and_bills(client, db, world):
    act_as(client, world.a.manager)

    supplier = client.post("/api/master/suppliers", json={"name": "KM Supplier"})
    assert supplier.status_code == 201, supplier.text

    renamed = client.put(f"/api/master/suppliers/{supplier.json()['id']}",
                         json={"name": "KM Supplier Renamed"})
    assert renamed.status_code == 200, renamed.text

    bill = client.post("/api/purchases/", json={
        "supplier_id": world.a.supplier.id,
        "invoice_number": "KM-INV-1",
        "purchase_date": "2026-11-02",
        "items": [{"item_id": world.a.item.id, "quantity": "2",
                   "unit_id": world.a.kg.id, "unit_rate": "45.50"}],
    })
    assert bill.status_code == 201, bill.text
    assert bill.json()["grand_total"] == "91.00"


# ============================================================
# 3–5. STOCK ITEMS: KM ADDS AND EDITS, ONLY ADMIN DELETES
# ============================================================

def test_manager_can_create_edit_and_deactivate_items(client, db, world):
    act_as(client, world.a.manager)

    created = client.post("/api/master/items", json={
        "name": "Wheat", "category_id": world.a.category.id,
        "standard_unit_id": world.a.kg.id, "minimum_stock": "5",
    })
    assert created.status_code == 201, created.text
    item_id = created.json()["id"]

    edited = client.put(f"/api/master/items/{item_id}", json={
        "name": "Whole Wheat", "category_id": world.a.category.id,
        "standard_unit_id": world.a.kg.id, "minimum_stock": "8",
    })
    assert edited.status_code == 200, edited.text

    deactivated = client.post(f"/api/master/items/{item_id}/deactivate")
    assert deactivated.status_code == 200, deactivated.text


def test_manager_cannot_delete_stock_items(client, db, world):
    act_as(client, world.a.manager)

    response = client.delete(f"/api/master/items/{world.a.item.id}")

    assert response.status_code == 403, response.text
    db.expire_all()
    assert db.get(Item, world.a.item.id) is not None


def test_admin_can_delete_stock_items(client, db, world):
    act_as(client, world.a.admin)

    response = client.delete(f"/api/master/items/{world.a.item.id}")

    assert response.status_code == 200, response.text
    db.expire_all()
    assert db.get(Item, world.a.item.id) is None


@pytest.mark.parametrize("resource, attr", [
    ("categories", "category"),
    ("suppliers", "supplier"),
    ("units", "kg"),
])
def test_permanent_delete_of_any_master_record_stays_admin_only(
    client, db, world, resource, attr
):
    act_as(client, world.a.manager)

    record = getattr(world.a, attr)
    response = client.delete(f"/api/master/{resource}/{record.id}")

    assert response.status_code == 403, response.text


def test_manager_cannot_delete_waste_records(client, world):
    act_as(client, world.a.admin)
    created = client.post("/api/waste/records", json={
        "items": [{
            "waste_type": "RAW_INGREDIENT", "item_id": world.a.item.id,
            "unit_id": world.a.kg.id, "quantity": "1.5",
            "waste_stage": "STORAGE", "waste_reason": "SPOILED",
            "estimated_cost": "60",
        }],
    })
    assert created.status_code == 201, created.text

    act_as(client, world.a.manager)
    response = client.delete(f"/api/waste/records/{created.json()['id']}")

    assert response.status_code == 403, response.text


# ============================================================
# 6–8. USER MANAGEMENT STAYS ADMIN-ONLY
# ============================================================

@pytest.mark.parametrize("new_role", ["STAFF", "KITCHEN_MANAGER"])
@pytest.mark.parametrize("actor, expected", [
    ("admin", 201), ("manager", 403), ("staff", 403),
])
def test_only_admin_creates_staff_and_manager_accounts(
    client, db, world, new_role, actor, expected
):
    act_as(client, getattr(world.a, actor))

    response = client.post("/api/auth/users", json={
        "full_name": "New Person",
        "email": f"new.{actor}.{new_role.lower()}@test.com",
        "password": "LongEnough123",
        "role": new_role,
    })

    assert response.status_code == expected, response.text
    created = db.query(User).filter(
        User.email == f"new.{actor}.{new_role.lower()}@test.com"
    ).first()
    assert (created is not None) == (expected == 201)


def test_only_admin_manages_user_permissions(client, db, world):
    dashboard = db.query(Permission).filter_by(
        permission_code="dashboard.read"
    ).one()
    staff_id = world.a.staff.id

    act_as(client, world.a.manager)
    assert client.get("/api/authorization/staff").status_code == 403
    assert client.get("/api/authorization/modules").status_code == 403
    assert client.get(f"/api/authorization/staff/{staff_id}").status_code == 403
    assert client.put(
        f"/api/authorization/staff/{staff_id}/permissions",
        json={"permission_ids": [dashboard.id]},
    ).status_code == 403
    assert client.delete(
        f"/api/authorization/staff/{staff_id}/permissions/{dashboard.id}"
    ).status_code == 403
    assert db.query(StaffAccessAssignment).count() == 0

    act_as(client, world.a.admin)
    assert client.put(
        f"/api/authorization/staff/{staff_id}/permissions",
        json={"permission_ids": [dashboard.id]},
    ).status_code == 200
    assert db.query(StaffAccessAssignment).count() == 1


# ============================================================
# 9–10. SUPPLIER PAYMENTS: BOTH ROLES RECORD AND VIEW
# ============================================================

@pytest.mark.parametrize("role", ["admin", "manager"])
def test_admin_and_manager_record_payments(client, db, world, role):
    actor = getattr(world.a, role)
    act_as(client, actor)

    response = pay(client, world.a.bill, "250.00", reference_number="TXN-1")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["payment"]["amount"] == "250.00"
    assert body["payment"]["created_by"] == actor.id
    assert body["payment"]["created_by_name"] == actor.full_name
    assert body["bill"] == {
        "purchase_id": world.a.bill.id,
        "supplier_id": world.a.supplier.id,
        "supplier_name": "Supplier A",
        "invoice_number": "A-INV-1",
        "purchase_date": "2026-11-01",
        "grand_total": "1000.00",
        "paid_total": "250.00",
        "outstanding": "750.00",
        "overpaid": "0.00",
        "payment_status": "PARTIALLY_PAID",
    }


@pytest.mark.parametrize("role", ["admin", "manager"])
def test_admin_and_manager_view_payments(client, world, role):
    act_as(client, world.a.admin)
    pay(client, world.a.bill, "400.00")

    act_as(client, getattr(world.a, role))

    bill_view = client.get(f"/api/purchases/{world.a.bill.id}/payments")
    assert bill_view.status_code == 200, bill_view.text
    assert [p["amount"] for p in bill_view.json()["payments"]] == ["400.00"]
    assert bill_view.json()["bill"]["outstanding"] == "600.00"

    listing = client.get("/api/supplier-payments")
    assert listing.status_code == 200
    assert listing.json()["total_paid"] == "400.00"

    balances = client.get("/api/supplier-balances")
    assert balances.status_code == 200
    assert balances.json()["totals"]["outstanding"] == "600.00"


# ============================================================
# 11. STAFF: ONLY WHAT WAS EXPLICITLY ASSIGNED
# ============================================================

def test_staff_without_assignments_is_denied_everything(client, world):
    act_as(client, world.a.staff)

    for method, url in [
        ("get", "/api/dashboard/overview"),
        ("get", "/api/master/items"),
        ("get", "/api/purchases/"),
        ("get", f"/api/purchases/{world.a.bill.id}/payments"),
        ("get", "/api/supplier-payments"),
        ("get", "/api/supplier-balances"),
    ]:
        assert getattr(client, method)(url).status_code == 403, url

    assert pay(client, world.a.bill, "10.00").status_code == 403
    assert client.post("/api/master/items", json={
        "name": "X", "category_id": world.a.category.id,
        "standard_unit_id": world.a.kg.id,
    }).status_code == 403


def test_staff_gets_exactly_the_assigned_permission(client, db, world):
    grant(db, world.a.staff, world.a.admin, "inventory.read")
    act_as(client, world.a.staff)

    assert client.get("/api/master/items").status_code == 200
    assert client.post("/api/master/items", json={
        "name": "X", "category_id": world.a.category.id,
        "standard_unit_id": world.a.kg.id,
    }).status_code == 403
    assert client.delete(
        f"/api/master/items/{world.a.item.id}"
    ).status_code == 403
    assert client.get("/api/supplier-payments").status_code == 403


def test_staff_older_bill_read_grant_allows_viewing_not_paying(
    client, db, world
):
    # Bill codes (purchase_bill.*, which held purchase_order.* until the
    # Stage 3 split) cannot be newly assigned to STAFF, but an older
    # explicit grant still applies, read-only.
    grant(db, world.a.staff, world.a.admin, "purchase_bill.read")
    act_as(client, world.a.staff)

    for url in (
        f"/api/purchases/{world.a.bill.id}/payments",
        "/api/supplier-payments",
        "/api/supplier-balances",
        "/api/supplier-balances/bills",
    ):
        assert client.get(url).status_code == 200, url
    assert pay(client, world.a.bill, "10.00").status_code == 403


def _assignment_rows(db, staff):
    db.expire_all()
    return sorted(
        (row.permission_id, row.is_active, row.assigned_by)
        for row in db.query(StaffAccessAssignment).filter_by(
            staff_user_id=staff.id
        )
    )


def test_staff_existing_bill_create_grant_is_honoured_unchanged(
    client, db, world
):
    # An existing, active, explicit assignment is valid authorisation:
    # it is neither ignored nor rewritten by the payment features.
    grant(db, world.a.staff, world.a.admin, "purchase_bill.create")
    before = _assignment_rows(db, world.a.staff)
    act_as(client, world.a.staff)

    response = pay(client, world.a.bill, "10.00")

    assert response.status_code == 201, response.text
    # create does not imply read.
    assert client.get("/api/supplier-payments").status_code == 403
    assert _assignment_rows(db, world.a.staff) == before


def test_staff_inactive_bill_grant_gives_no_payment_access(
    client, db, world
):
    for code in ("purchase_bill.read", "purchase_bill.create"):
        grant(db, world.a.staff, world.a.admin, code)
    db.query(StaffAccessAssignment).filter_by(
        staff_user_id=world.a.staff.id
    ).update({"is_active": False})
    db.commit()
    before = _assignment_rows(db, world.a.staff)
    act_as(client, world.a.staff)

    assert pay(client, world.a.bill, "10.00").status_code == 403
    for url in (
        f"/api/purchases/{world.a.bill.id}/payments",
        "/api/supplier-payments",
        "/api/supplier-balances",
        "/api/supplier-balances/bills",
    ):
        assert client.get(url).status_code == 403, url
    assert _assignment_rows(db, world.a.staff) == before
    assert db.query(SupplierPayment).count() == 0


@pytest.mark.parametrize("code", ["purchase_bill.read", "purchase_order.read"])
def test_bill_and_order_permissions_still_cannot_be_newly_assigned_to_staff(
    client, db, world, code
):
    # Neither namespace is on the STAFF list (decision 18 November 2026).
    permission = db.query(Permission).filter_by(permission_code=code).one()
    act_as(client, world.a.admin)

    response = client.put(
        f"/api/authorization/staff/{world.a.staff.id}/permissions",
        json={"permission_ids": [permission.id]},
    )

    assert response.status_code == 422, response.text


# ============================================================
# 12. CAMPUS ISOLATION
# ============================================================

def test_other_campus_records_are_unreachable(client, db, world):
    act_as(client, world.b.admin)
    pay(client, world.b.bill, "100.00")

    act_as(client, world.a.manager)

    assert client.get(f"/api/purchases/{world.b.bill.id}").status_code == 404
    assert client.get(
        f"/api/purchases/{world.b.bill.id}/payments"
    ).status_code == 404
    assert pay(client, world.b.bill, "10.00").status_code == 404
    assert client.put(f"/api/master/items/{world.b.item.id}", json={
        "name": "Hijacked", "category_id": world.a.category.id,
        "standard_unit_id": world.a.kg.id,
    }).status_code == 404

    listing = client.get("/api/supplier-payments").json()
    assert listing["items"] == [] and listing["total_paid"] == "0.00"
    assert listing["total"] == 0

    balances = client.get("/api/supplier-balances").json()
    assert {row["supplier_id"] for row in balances["items"]} == {
        world.a.supplier.id
    }

    bills = client.get("/api/supplier-balances/bills").json()
    assert {row["purchase_id"] for row in bills["items"]} == {
        world.a.bill.id
    }

    act_as(client, world.a.admin)
    assert client.delete(
        f"/api/master/items/{world.b.item.id}"
    ).status_code == 404

    db.expire_all()
    assert db.query(SupplierPayment).filter_by(
        purchase_id=world.b.bill.id
    ).count() == 1


# ============================================================
# PUR04 RULES
# ============================================================

def test_full_payment_closes_the_bill(client, world):
    act_as(client, world.a.manager)

    response = pay(client, world.a.bill, "1000.00")

    assert response.status_code == 201, response.text
    assert response.json()["bill"]["payment_status"] == "PAID"
    assert response.json()["bill"]["outstanding"] == "0.00"

    again = pay(client, world.a.bill, "1.00")
    assert again.status_code == 409


def test_partial_payments_accumulate_exactly(client, world):
    act_as(client, world.a.manager)

    pay(client, world.a.bill, "300.00")
    second = pay(client, world.a.bill, "200.50")

    assert second.json()["bill"]["paid_total"] == "500.50"
    assert second.json()["bill"]["outstanding"] == "499.50"
    assert second.json()["bill"]["payment_status"] == "PARTIALLY_PAID"

    last = pay(client, world.a.bill, "499.50")
    assert last.json()["bill"]["payment_status"] == "PAID"


def test_overpayment_is_rejected_and_nothing_saved(client, db, world):
    act_as(client, world.a.manager)
    pay(client, world.a.bill, "900.00")

    response = pay(client, world.a.bill, "100.01")

    assert response.status_code == 422
    assert "100.00" in response.json()["detail"]
    assert db.query(SupplierPayment).count() == 1


@pytest.mark.parametrize("amount", ["0", "-5.00", "10.005"])
def test_invalid_amounts_are_rejected(client, db, world, amount):
    act_as(client, world.a.manager)

    assert pay(client, world.a.bill, amount).status_code == 422
    assert db.query(SupplierPayment).count() == 0


def test_payment_method_must_be_on_the_list(client, db, world):
    act_as(client, world.a.manager)

    bad = pay(client, world.a.bill, "10.00", payment_method="BITCOIN")
    assert bad.status_code == 422

    good = pay(client, world.a.bill, "10.00", payment_method=" upi ")
    assert good.status_code == 201
    assert good.json()["payment"]["payment_method"] == "UPI"


def test_reference_number_is_unique_per_bill(client, db, world):
    act_as(client, world.a.manager)
    other_bill = make_bill(db, world.a, "A-INV-2", "300.00")

    assert pay(client, world.a.bill, "10.00",
               reference_number="UTR-77").status_code == 201
    assert pay(client, world.a.bill, "10.00",
               reference_number="utr-77").status_code == 409
    assert pay(client, other_bill, "10.00",
               reference_number="UTR-77").status_code == 201


@pytest.mark.parametrize("role", ["admin", "manager"])
def test_payment_is_audited_with_its_actor(client, db, world, role):
    actor = getattr(world.a, role)
    act_as(client, actor)
    pay(client, world.a.bill, "100.00")
    payment = pay(
        client, world.a.bill, "250.00", reference_number="UTR-9"
    ).json()["payment"]

    row = db.query(AuditLog).filter_by(
        entity_type="SUPPLIER_PAYMENT", entity_id=payment["id"]
    ).one()

    assert row.action == "CREATE"
    assert row.user_id == actor.id
    assert row.campus_id == world.a.campus.id
    assert row.details == {
        "purchase_id": world.a.bill.id,
        "invoice_number": "A-INV-1",
        "supplier_id": world.a.supplier.id,
        "payment_date": "2026-11-05",
        "amount": "250.00",
        "payment_method": "BANK_TRANSFER",
        "reference_number": "UTR-9",
        "bill_total": "1000.00",
        "paid_before": "100.00",
        "paid_after": "350.00",
        "outstanding_after": "650.00",
        "payment_status_after": "PARTIALLY_PAID",
    }


def test_every_saved_payment_has_exactly_one_audit_row(client, db, world):
    act_as(client, world.a.manager)
    pay(client, world.a.bill, "100.00")
    pay(client, world.a.bill, "5000.00")            # rejected: overpayment
    pay(client, world.a.bill, "1.00", payment_date="2099-01-01")  # rejected
    act_as(client, world.a.admin)
    pay(client, world.a.bill, "200.00")

    payment_ids = {p.id for p in db.query(SupplierPayment)}
    audited = [
        row.entity_id
        for row in db.query(AuditLog).filter_by(entity_type="SUPPLIER_PAYMENT")
    ]
    assert len(payment_ids) == 2
    assert sorted(audited) == sorted(payment_ids)


def test_supplier_balances_combine_bills_and_payments(client, db, world):
    make_bill(db, world.a, "A-INV-2", "250.00")
    act_as(client, world.a.manager)
    pay(client, world.a.bill, "400.00")

    body = client.get(
        f"/api/supplier-balances?supplier_id={world.a.supplier.id}"
    ).json()

    assert body["items"] == [{
        "supplier_id": world.a.supplier.id,
        "supplier_name": "Supplier A",
        "bill_count": 2,
        "open_bill_count": 2,
        "total_billed": "1250.00",
        "total_paid": "400.00",
        "outstanding": "850.00",
        "overpaid": "0.00",
    }]
    assert body["totals"] == {
        "total_billed": "1250.00",
        "total_paid": "400.00",
        "outstanding": "850.00",
        "overpaid": "0.00",
        "open_bill_count": 2,
        "supplier_count": 1,
    }


def test_bill_activity_shows_only_to_bill_readers(client, db, world):
    act_as(client, world.a.manager)
    pay(client, world.a.bill, "50.00")
    category = client.post("/api/master/categories", json={"name": "Spices"})
    assert category.status_code == 201, category.text

    feed = client.get("/api/dashboard/overview").json()["activity"]
    assert {"SUPPLIER_PAYMENT", "CATEGORY"} <= {e["entity_type"] for e in feed}

    for code in ("dashboard.read", "audit.read"):
        grant(db, world.a.staff, world.a.admin, code)
    act_as(client, world.a.staff)

    feed = client.get("/api/dashboard/overview").json()["activity"]
    types = {e["entity_type"] for e in feed}
    assert "CATEGORY" in types
    assert not types & {"PURCHASE", "SUPPLIER_PAYMENT"}


# ============================================================
# PUR04: BALANCES ARE SHOWN HONESTLY
# ============================================================

def test_unpaid_bill_is_reported_unpaid(client, world):
    act_as(client, world.a.manager)

    bill = client.get(
        f"/api/purchases/{world.a.bill.id}/payments"
    ).json()["bill"]

    assert bill["payment_status"] == "UNPAID"
    assert bill["outstanding"] == "1000.00"
    assert bill["overpaid"] == "0.00"


def test_overpaid_bill_is_shown_not_hidden(client, db, world):
    # Only data written outside the API can overpay a bill. The excess
    # must be visible, never floored to a zero balance.
    other = make_bill(db, world.a, "A-INV-2", "300.00")
    db.add(SupplierPayment(
        campus_id=world.a.campus.id, purchase_id=world.a.bill.id,
        payment_date=date(2026, 11, 3), amount=Decimal("1100.00"),
        payment_method="CASH", created_by=world.a.admin.id,
    ))
    db.commit()
    act_as(client, world.a.manager)

    bill = client.get(
        f"/api/purchases/{world.a.bill.id}/payments"
    ).json()["bill"]
    assert bill["payment_status"] == "OVERPAID"
    assert bill["outstanding"] == "0.00"
    assert bill["overpaid"] == "100.00"

    # The overpaid bill does not cancel out the other bill's balance.
    balances = client.get("/api/supplier-balances").json()
    assert balances["items"][0]["outstanding"] == "300.00"
    assert balances["items"][0]["overpaid"] == "100.00"
    assert balances["items"][0]["open_bill_count"] == 1
    assert balances["totals"]["overpaid"] == "100.00"

    assert pay(client, world.a.bill, "1.00").status_code == 409
    assert pay(client, other, "300.00").status_code == 201


def test_zero_total_bill_is_settled_and_takes_no_payment(client, db, world):
    zero = make_bill(db, world.a, "A-ZERO", "0.00")
    act_as(client, world.a.manager)

    bill = client.get(f"/api/purchases/{zero.id}/payments").json()["bill"]
    assert bill["payment_status"] == "PAID"
    assert bill["outstanding"] == "0.00"

    response = pay(client, zero, "1.00")
    assert response.status_code == 409
    assert "zero total" in response.json()["detail"]
    assert db.query(SupplierPayment).count() == 0

    open_bills = client.get(
        "/api/supplier-balances/bills?open_only=true"
    ).json()
    assert zero.id not in {row["purchase_id"] for row in open_bills["items"]}


# ============================================================
# PUR04: PAYMENT DATE
# ============================================================

def test_payment_date_cannot_be_in_the_future(
    client, db, world, monkeypatch
):
    monkeypatch.setattr(supplier_payments, "today", lambda: date(2026, 11, 10))
    act_as(client, world.a.manager)

    response = pay(client, world.a.bill, "10.00", payment_date="2026-11-11")
    assert response.status_code == 422
    assert "future" in response.json()["detail"]
    assert db.query(SupplierPayment).count() == 0

    assert pay(
        client, world.a.bill, "10.00", payment_date="2026-11-10"
    ).status_code == 201


def test_payment_date_cannot_precede_the_bill(client, db, world):
    act_as(client, world.a.manager)

    response = pay(client, world.a.bill, "10.00", payment_date="2026-10-31")
    assert response.status_code == 422
    assert "2026-11-01" in response.json()["detail"]
    assert db.query(SupplierPayment).count() == 0

    assert pay(
        client, world.a.bill, "10.00", payment_date="2026-11-01"
    ).status_code == 201


# ============================================================
# PUR04: LISTS, FILTERS AND PAGINATION
# ============================================================

def test_payment_list_is_paginated_with_a_total_for_all_pages(client, world):
    act_as(client, world.a.manager)
    for day in range(1, 6):
        assert pay(
            client, world.a.bill, "10.00", payment_date=f"2026-11-0{day}"
        ).status_code == 201

    first = client.get("/api/supplier-payments?page=1&page_size=2").json()
    assert [p["payment_date"] for p in first["items"]] == [
        "2026-11-05", "2026-11-04",
    ]
    assert first["total"] == 5
    assert first["total_pages"] == 3
    assert first["total_paid"] == "50.00"
    assert first["items"][0]["created_by_name"] == world.a.manager.full_name

    last = client.get("/api/supplier-payments?page=3&page_size=2").json()
    assert len(last["items"]) == 1

    assert client.get("/api/supplier-payments?page_size=101").status_code == 422
    assert client.get("/api/supplier-payments?page=0").status_code == 422


def test_payment_list_filters(client, db, world):
    other_supplier = Supplier(campus_id=world.a.campus.id, name="Other A")
    db.add(other_supplier)
    db.commit()
    other_bill = make_bill(
        db, world.a, "A-INV-OTHER", "500.00", supplier=other_supplier
    )
    act_as(client, world.a.admin)
    pay(client, world.a.bill, "10.00", payment_date="2026-11-02",
        payment_method="CASH")
    pay(client, world.a.bill, "20.00", payment_date="2026-11-06")
    pay(client, other_bill, "40.00", payment_date="2026-11-04",
        payment_method="UPI")

    def listing(query):
        response = client.get(f"/api/supplier-payments?{query}")
        assert response.status_code == 200, response.text
        return response.json()

    by_supplier = listing(f"supplier_id={other_supplier.id}")
    assert by_supplier["total_paid"] == "40.00"
    assert by_supplier["items"][0]["supplier_name"] == "Other A"
    assert by_supplier["items"][0]["invoice_number"] == "A-INV-OTHER"

    in_range = listing("date_from=2026-11-03&date_to=2026-11-05")
    assert [p["amount"] for p in in_range["items"]] == ["40.00"]

    assert listing("payment_method=cash")["total_paid"] == "10.00"

    assert client.get(
        "/api/supplier-payments?date_from=2026-11-06&date_to=2026-11-01"
    ).status_code == 422
    assert client.get(
        "/api/supplier-payments?payment_method=BITCOIN"
    ).status_code == 422


def test_bill_balances_list_open_bills_per_supplier(client, db, world):
    paid_off = make_bill(db, world.a, "A-INV-PAID", "100.00")
    act_as(client, world.a.manager)
    pay(client, paid_off, "100.00")
    pay(client, world.a.bill, "250.00")

    every = client.get(
        f"/api/supplier-balances/bills?supplier_id={world.a.supplier.id}"
    ).json()
    assert every["total"] == 2
    assert {
        row["invoice_number"]: row["payment_status"] for row in every["items"]
    } == {"A-INV-1": "PARTIALLY_PAID", "A-INV-PAID": "PAID"}

    open_bills = client.get(
        "/api/supplier-balances/bills?open_only=true"
    ).json()
    assert [
        (row["invoice_number"], row["outstanding"], row["supplier_name"])
        for row in open_bills["items"]
    ] == [("A-INV-1", "750.00", "Supplier A")]


def test_campus_without_bills_has_zero_balances(client, db, world):
    empty = _campus(db, "C")
    db.commit()
    act_as(client, empty.admin)

    body = client.get("/api/supplier-balances").json()

    assert body["items"] == []
    assert body["total"] == 0
    assert body["totals"] == {
        "total_billed": "0.00",
        "total_paid": "0.00",
        "outstanding": "0.00",
        "overpaid": "0.00",
        "open_bill_count": 0,
        "supplier_count": 0,
    }


# ============================================================
# DASHBOARD
# ============================================================

@pytest.mark.parametrize("role", ["admin", "manager"])
def test_dashboard_reports_payables_for_admin_and_manager(
    client, db, world, role
):
    today = date.today().isoformat()
    make_bill(db, world.a, "A-INV-2", "250.00")
    act_as(client, world.a.admin)
    assert pay(
        client, world.a.bill, "400.00", payment_date=today
    ).status_code == 201

    act_as(client, getattr(world.a, role))
    body = client.get("/api/dashboard/overview").json()

    assert body["campus_name"] == "Campus A"

    # Campus B's 500.00 bill is not included.
    payments = body["payments"]
    assert payments["total_billed"] == "1250.00"
    assert payments["total_paid"] == "400.00"
    assert payments["outstanding"] == "850.00"
    assert payments["overpaid"] == "0.00"
    assert payments["paid_this_month"] == "400.00"
    assert payments["count_this_month"] == 1
    assert payments["open_bill_count"] == 2
    assert payments["suppliers_owed"] == 1
    assert payments["top_outstanding"][0]["outstanding"] == "850.00"
    assert payments["recent"][0]["amount"] == "400.00"
    assert payments["recent"][0]["supplier_name"] == "Supplier A"
    assert body["kpis"]["outstanding_payables"] == "850.00"

    recent = {row["invoice_number"]: row for row in body["purchases"]["recent"]}
    assert recent["A-INV-1"]["grand_total"] == "1000.00"
    assert recent["A-INV-1"]["paid_total"] == "400.00"
    assert recent["A-INV-1"]["outstanding"] == "600.00"
    assert recent["A-INV-1"]["payment_status"] == "PARTIALLY_PAID"

    # Waste quantities are in mixed units and are no longer summed.
    assert "quantity_today" not in body["waste"]
    assert body["waste"]["items_today"] == 0
    assert body["waste"]["estimated_cost_today"] == "0.00"


def test_only_admin_dashboard_has_the_team_overview(client, db, world):
    grant(db, world.a.staff, world.a.admin, "dashboard.read")
    db.add(User(
        campus_id=world.a.campus.id, full_name="New Staff",
        email="new.staff.a@test.com", password_hash=PASSWORD_HASH,
        role=UserRole.STAFF, is_active=True,
    ))
    db.add(User(
        campus_id=world.a.campus.id, full_name="Former Staff",
        email="former.staff.a@test.com", password_hash=PASSWORD_HASH,
        role=UserRole.STAFF, is_active=False,
    ))
    db.commit()

    act_as(client, world.a.admin)
    body = client.get("/api/dashboard/overview").json()
    assert body["team"] == {
        "active_admins": 1,
        "active_kitchen_managers": 1,
        "active_staff": 2,
        "inactive_users": 1,
        "staff_without_access": 1,
    }
    assert body["kpis"]["active_users"] == 4

    act_as(client, world.a.manager)
    assert "team" not in client.get("/api/dashboard/overview").json()

    act_as(client, world.a.staff)
    staff_view = client.get("/api/dashboard/overview").json()
    assert not {"team", "payments", "purchases"} & set(staff_view)


# ============================================================
# CAMPUS-LOCAL DATE (the server clock is UTC in Docker)
# ============================================================

def test_campus_date_follows_india_time_not_utc():
    from datetime import datetime, timezone

    from app.core.clock import campus_today

    # 20:00 UTC on 16 Nov is 01:30 IST on 17 Nov.
    assert campus_today(
        datetime(2026, 11, 16, 20, 0, tzinfo=timezone.utc)
    ) == date(2026, 11, 17)
    # 18:29 UTC is 23:59 IST, still the 16th.
    assert campus_today(
        datetime(2026, 11, 16, 18, 29, tzinfo=timezone.utc)
    ) == date(2026, 11, 16)


def test_campus_timezone_works_without_a_timezone_database(monkeypatch):
    from datetime import datetime, timezone

    from app.core import clock

    def missing(name):
        raise clock.ZoneInfoNotFoundError(name)

    monkeypatch.setattr(clock, "ZoneInfo", missing)

    zone = clock.campus_timezone("Asia/Kolkata")
    assert datetime(
        2026, 11, 16, 20, 0, tzinfo=timezone.utc
    ).astimezone(zone).date() == date(2026, 11, 17)

    with pytest.raises(clock.ZoneInfoNotFoundError):
        clock.campus_timezone("Europe/Nowhere")


def test_payment_dated_today_in_india_is_accepted_after_midnight(
    client, db, world, monkeypatch
):
    from datetime import datetime, timezone

    from app.core import clock

    # 01:30 IST on 17 Nov; the UTC date is still 16 Nov.
    monkeypatch.setattr(
        supplier_payments,
        "campus_today",
        lambda: clock.campus_today(
            datetime(2026, 11, 16, 20, 0, tzinfo=timezone.utc)
        ),
    )
    act_as(client, world.a.manager)

    assert pay(
        client, world.a.bill, "10.00", payment_date="2026-11-17"
    ).status_code == 201
    assert pay(
        client, world.a.bill, "10.00", payment_date="2026-11-18"
    ).status_code == 422
