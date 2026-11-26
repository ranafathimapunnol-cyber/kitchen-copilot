"""
P0 characterization tests for GET /api/dashboard/overview.

They record the current rule that every dashboard section is returned
only when the caller holds that section's read permission, and that
all figures are limited to the caller's campus.
"""

from datetime import date

from app.models import Campus, Category, Item, Unit
from app.models.authorization import Module, Permission
from app.models.daily_headcount import DailyHeadcount

from tests.test_authorization import (
    assign_staff_permission,
    authenticate_as,
    create_test_user,
)


OVERVIEW_URL = "/api/dashboard/overview"

DATA_SECTIONS = {
    "headcount",
    "inventory",
    "purchases",
    "payments",
    "receipts",
    "menus",
    "waste",
    "activity",
}


def ensure_waste_permission_exists(db):
    """The shared test fixture seeds the original eight modules only.
    The waste_tracking module is added by migration d4e8a91b2c70, so
    create it here when a test needs it."""

    module = db.query(Module).filter(Module.code == "waste_tracking").first()

    if module is None:
        module = Module(name="Waste Tracking", code="waste_tracking")
        db.add(module)
        db.flush()

        for action in ("CREATE", "READ", "UPDATE"):
            db.add(
                Permission(
                    module_id=module.id,
                    action=action,
                    permission_code=f"waste_tracking.{action.lower()}",
                )
            )

        db.commit()


def present_sections(payload):
    return DATA_SECTIONS & set(payload.keys())


def test_admin_sees_every_section(client, db):
    ensure_waste_permission_exists(db)

    response = client.get(OVERVIEW_URL)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["role"] == "ADMIN"
    assert present_sections(payload) == DATA_SECTIONS
    # Users and permissions are ADMIN-only, so only ADMIN sees the team
    # overview.
    assert "team" in payload


def test_kitchen_manager_sees_operational_sections(client, db, setup_data):
    manager = create_test_user(
        db, setup_data["campus"].id, "KITCHEN_MANAGER"
    )
    authenticate_as(client, manager)

    response = client.get(OVERVIEW_URL)

    assert response.status_code == 200, response.text
    # Kitchen Managers have the same operational access as ADMIN,
    # including supplier bills, payments and balances (confirmed role
    # rules, 17 November 2026). The team overview stays ADMIN-only.
    assert present_sections(response.json()) == DATA_SECTIONS
    assert "team" not in response.json()


def test_staff_without_dashboard_permission_is_denied(client, db, setup_data):
    staff = create_test_user(db, setup_data["campus"].id, "STAFF")
    authenticate_as(client, staff)

    assert client.get(OVERVIEW_URL).status_code == 403


def test_staff_with_dashboard_only_gets_no_data_sections(
    client, db, setup_data
):
    staff = create_test_user(db, setup_data["campus"].id, "STAFF")
    assign_staff_permission(
        db, staff, setup_data["user"],
        "dashboard", "Dashboard", "dashboard.read",
    )
    authenticate_as(client, staff)

    response = client.get(OVERVIEW_URL)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert present_sections(payload) == set()
    assert payload["permissions"] == ["dashboard.read"]
    assert payload["kpis"] == {}


def test_staff_sections_follow_assigned_permissions(client, db, setup_data):
    staff = create_test_user(db, setup_data["campus"].id, "STAFF")

    for code, module, name in (
        ("dashboard.read", "dashboard", "Dashboard"),
        ("inventory.read", "inventory", "Inventory"),
    ):
        assign_staff_permission(
            db, staff, setup_data["user"], module, name, code
        )

    authenticate_as(client, staff)

    response = client.get(OVERVIEW_URL)

    assert response.status_code == 200, response.text
    # inventory.read unlocks inventory and goods receipts only.
    assert present_sections(response.json()) == {"inventory", "receipts"}


def test_dashboard_figures_are_campus_isolated(client, db, setup_data):
    other_campus = Campus(name="Other Dashboard Campus", code="OTHER-DASH")
    db.add(other_campus)
    db.flush()

    db.add(
        DailyHeadcount(
            campus_id=other_campus.id,
            headcount_date=date.today(),
            student_count=999,
        )
    )

    other_unit = Unit(
        campus_id=other_campus.id,
        name="Piece",
        symbol="pc",
        dimension="count",
    )
    other_category = Category(campus_id=other_campus.id, name="Other")
    db.add_all([other_unit, other_category])
    db.flush()

    db.add(
        Item(
            campus_id=other_campus.id,
            name="Other campus item",
            category_id=other_category.id,
            standard_unit_id=other_unit.id,
            minimum_stock=0,
        )
    )
    db.commit()

    response = client.get(OVERVIEW_URL)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["campus_id"] == setup_data["campus"].id
    assert payload["headcount"]["today"] is None
    assert payload["headcount"]["trend"] == []
    assert payload["inventory"]["active_items"] == 0
