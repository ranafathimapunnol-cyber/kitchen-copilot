"""
STAFF permission assignment (PUT /api/authorization/staff/{id}/permissions).

Approved rules:
- An ADMIN may assign STAFF only permissions on the approved whitelist
  (STAFF_ASSIGNABLE_PERMISSIONS); anything else is rejected with 422.
- STAFF never receive audit access, menu.create or menu.update; menus
  stay read-only.
- Older assignments outside the whitelist are kept unchanged (and keep
  working) when an ADMIN saves, until a separately approved cleanup.
"""

import pytest

from app.api.dependencies import STAFF_ASSIGNABLE_PERMISSIONS
from app.models import Campus
from app.models.audit_log import AuditLog
from app.models.authorization import Permission, StaffAccessAssignment

from tests.test_authorization import (
    assign_staff_permission,
    authenticate_as,
    create_test_user,
)
from tests.test_dashboard import ensure_waste_permission_exists


EXPECTED_ASSIGNABLE = {
    "dashboard.read",
    "headcount.create", "headcount.read", "headcount.update",
    "inventory.read",
    "consumption.create", "consumption.read", "consumption.update",
    "outsourced_food.create", "outsourced_food.read",
    "outsourced_food.update",
    "menu.read",
    "waste_tracking.create", "waste_tracking.read", "waste_tracking.update",
}

NOT_ASSIGNABLE = [
    "audit.read",
    "menu.create",
    "menu.update",
    "inventory.create",
    "inventory.update",
    "purchase_order.create",
    "purchase_order.read",
    "purchase_order.update",
]


def permission_id(db, code):
    return (
        db.query(Permission.id)
        .filter(Permission.permission_code == code)
        .scalar()
    )


def permissions_url(staff):
    return f"/api/authorization/staff/{staff.id}/permissions"


def active_codes(db, staff):
    db.expire_all()
    rows = (
        db.query(Permission.permission_code)
        .join(
            StaffAccessAssignment,
            StaffAccessAssignment.permission_id == Permission.id,
        )
        .filter(
            StaffAccessAssignment.staff_user_id == staff.id,
            StaffAccessAssignment.is_active.is_(True),
        )
        .all()
    )
    return {row[0] for row in rows}


def staff_access_audits(db):
    return (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == "STAFF_ACCESS")
        .all()
    )


@pytest.fixture
def staff(db, setup_data):
    return create_test_user(db, setup_data["campus"].id, "STAFF")


def give_legacy(db, setup_data, staff, code):
    """Create an assignment directly, as older data may contain."""
    module_code = code.split(".")[0]
    assign_staff_permission(
        db, staff, setup_data["user"], module_code,
        module_code.title(), code,
    )


# ------------------------------------------------------------
# The whitelist
# ------------------------------------------------------------

def test_whitelist_matches_the_approved_mapping():
    assert set(STAFF_ASSIGNABLE_PERMISSIONS) == EXPECTED_ASSIGNABLE

    for code in NOT_ASSIGNABLE:
        assert code not in STAFF_ASSIGNABLE_PERMISSIONS


def test_modules_list_flags_assignable_permissions(client, db):
    ensure_waste_permission_exists(db)

    response = client.get("/api/authorization/modules")

    assert response.status_code == 200, response.text
    flags = {
        permission["permission_code"]: permission["assignable"]
        for module in response.json()
        for permission in module["permissions"]
    }

    assert flags  # every seeded permission is listed with a flag
    for code, assignable in flags.items():
        assert assignable == (code in EXPECTED_ASSIGNABLE), code

    assert flags["menu.read"] is True
    assert flags["audit.read"] is False
    assert flags["menu.create"] is False
    assert flags["menu.update"] is False


# ------------------------------------------------------------
# Valid assignments
# ------------------------------------------------------------

def test_admin_can_assign_whitelisted_permissions(client, db, staff):
    ensure_waste_permission_exists(db)
    codes = {
        "dashboard.read",
        "inventory.read",
        "menu.read",
        "headcount.create",
        "waste_tracking.update",
    }

    response = client.put(
        permissions_url(staff),
        json={"permission_ids": [permission_id(db, c) for c in codes]},
    )

    assert response.status_code == 200, response.text
    assert active_codes(db, staff) == codes
    assert all(p["assignable"] for p in response.json()["permissions"])
    assert len(staff_access_audits(db)) == 1


def test_saving_replaces_previous_whitelisted_assignments(
    client, db, setup_data, staff
):
    give_legacy(db, setup_data, staff, "inventory.read")

    response = client.put(
        permissions_url(staff),
        json={"permission_ids": [permission_id(db, "dashboard.read")]},
    )

    assert response.status_code == 200, response.text
    assert active_codes(db, staff) == {"dashboard.read"}


# ------------------------------------------------------------
# Rejected requests change nothing
# ------------------------------------------------------------

@pytest.mark.parametrize("forbidden", NOT_ASSIGNABLE)
def test_non_assignable_permissions_are_rejected(
    client, db, staff, forbidden
):
    response = client.put(
        permissions_url(staff),
        json={
            "permission_ids": [
                permission_id(db, "dashboard.read"),
                permission_id(db, forbidden),
            ]
        },
    )

    assert response.status_code == 422, response.text
    assert forbidden in response.json()["detail"]
    assert active_codes(db, staff) == set()
    assert staff_access_audits(db) == []


def test_duplicate_permission_ids_are_rejected(client, db, staff):
    dashboard = permission_id(db, "dashboard.read")

    response = client.put(
        permissions_url(staff),
        json={"permission_ids": [dashboard, dashboard]},
    )

    assert response.status_code == 422, response.text
    assert "Duplicate" in response.json()["detail"]
    assert active_codes(db, staff) == set()


def test_unknown_permission_ids_are_rejected(client, db, staff):
    response = client.put(
        permissions_url(staff),
        json={
            "permission_ids": [permission_id(db, "dashboard.read"), 999999]
        },
    )

    assert response.status_code == 422, response.text
    assert "invalid" in response.json()["detail"]
    assert active_codes(db, staff) == set()


def test_only_admin_can_assign(client, db, setup_data, staff):
    manager = create_test_user(
        db, setup_data["campus"].id, "KITCHEN_MANAGER"
    )
    authenticate_as(client, manager)

    response = client.put(
        permissions_url(staff),
        json={"permission_ids": [permission_id(db, "dashboard.read")]},
    )

    assert response.status_code == 403, response.text
    assert active_codes(db, staff) == set()


def test_staff_of_another_campus_cannot_be_assigned(client, db):
    other_campus = Campus(name="Other Staff Campus", code="OTHER-STAFF")
    db.add(other_campus)
    db.commit()
    outsider = create_test_user(db, other_campus.id, "STAFF")

    response = client.put(
        permissions_url(outsider),
        json={"permission_ids": [permission_id(db, "dashboard.read")]},
    )

    assert response.status_code == 404, response.text
    assert active_codes(db, outsider) == set()


# ------------------------------------------------------------
# Older non-assignable assignments are preserved
# ------------------------------------------------------------

def test_saving_keeps_older_non_assignable_assignments(
    client, db, setup_data, staff
):
    for code in ("audit.read", "menu.create", "inventory.read"):
        give_legacy(db, setup_data, staff, code)

    response = client.put(
        permissions_url(staff),
        json={"permission_ids": [permission_id(db, "dashboard.read")]},
    )

    assert response.status_code == 200, response.text
    # inventory.read is whitelisted and was not selected, so it is removed;
    # the older non-assignable permissions are kept.
    assert active_codes(db, staff) == {
        "dashboard.read", "audit.read", "menu.create"
    }

    details = staff_access_audits(db)[-1].details
    assert sorted(details["kept_not_assignable"]) == sorted([
        permission_id(db, "audit.read"),
        permission_id(db, "menu.create"),
    ])


def test_clearing_all_keeps_older_non_assignable_assignments(
    client, db, setup_data, staff
):
    give_legacy(db, setup_data, staff, "menu.update")
    give_legacy(db, setup_data, staff, "menu.read")

    response = client.put(permissions_url(staff), json={"permission_ids": []})

    assert response.status_code == 200, response.text
    assert active_codes(db, staff) == {"menu.update"}


def test_older_assignments_still_grant_access_until_cleanup(
    client, db, setup_data, staff
):
    give_legacy(db, setup_data, staff, "audit.read")

    authenticate_as(client, staff)
    response = client.get("/api/authorization/me")

    assert response.status_code == 200, response.text
    assert "audit.read" in response.json()["permissions"]


def test_staff_detail_flags_older_assignments(
    client, db, setup_data, staff
):
    give_legacy(db, setup_data, staff, "audit.read")
    give_legacy(db, setup_data, staff, "inventory.read")

    response = client.get(f"/api/authorization/staff/{staff.id}")

    assert response.status_code == 200, response.text
    flags = {
        p["permission_code"]: p["assignable"]
        for p in response.json()["permissions"]
    }
    assert flags == {"audit.read": False, "inventory.read": True}
