from uuid import uuid4

import pytest

from app.core.config import settings
from app.core.security import create_access_token
from app.models import User, UserRole
from app.models.authorization import (
    Module,
    Permission,
    StaffAccessAssignment,
)


def create_test_user(db, campus_id, role):
    role = UserRole(role)

    user = User(
        campus_id=campus_id,
        full_name=f"Test {role.value}",
        email=f"{role.value.lower()}-{uuid4().hex[:8]}@test.com",
        password_hash="not-used-for-cookie-auth",
        role=role,
        is_active=True,
    )

    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_as(client, user):
    token = create_access_token(user.id)
    client.cookies.set(settings.ACCESS_COOKIE_NAME, token)


def assign_staff_permission(
    db, staff, admin, module_code, module_name, permission_code
):
    module = (
        db.query(Module)
        .filter(Module.code == module_code)
        .first()
    )

    if module is None:
        module = Module(name=module_name, code=module_code)
        db.add(module)
        db.flush()

    permission = (
        db.query(Permission)
        .filter(Permission.permission_code == permission_code)
        .first()
    )

    if permission is None:
        action = permission_code.split(".")[-1].upper()
        permission = Permission(
            module_id=module.id,
            action=action,
            permission_code=permission_code,
        )
        db.add(permission)
        db.flush()

    assignment = (
        db.query(StaffAccessAssignment)
        .filter(
            StaffAccessAssignment.staff_user_id == staff.id,
            StaffAccessAssignment.permission_id == permission.id,
        )
        .first()
    )

    if assignment is None:
        assignment = StaffAccessAssignment(
            staff_user_id=staff.id,
            permission_id=permission.id,
            assigned_by=admin.id,
            is_active=True,
        )
        db.add(assignment)
    else:
        assignment.is_active = True
        assignment.assigned_by = admin.id

    db.commit()


READ_ENDPOINTS = [
    "/api/master/categories",
    "/api/master/units",
    "/api/master/unit-conversions",
    "/api/master/items",
    "/api/master/suppliers",
    "/api/master/meal-sessions",
    "/api/master/menus",
    "/api/master/menu-main-items",
    "/api/purchases/",
]

# Approved matrix: Kitchen Managers have no access to supplier bills.
KITCHEN_MANAGER_DENIED_READ_ENDPOINTS = {
    "/api/purchases/",
}


@pytest.mark.parametrize("endpoint", READ_ENDPOINTS)
def test_admin_has_read_access_to_all_modules(
    client, setup_data, endpoint
):
    authenticate_as(client, setup_data["user"])

    response = client.get(endpoint)

    assert response.status_code == 200, response.text


@pytest.mark.parametrize("endpoint", READ_ENDPOINTS)
def test_kitchen_manager_has_approved_read_access(
    client, setup_data, db, endpoint
):
    kitchen_manager = create_test_user(
        db, setup_data["campus"].id, "KITCHEN_MANAGER"
    )
    authenticate_as(client, kitchen_manager)

    response = client.get(endpoint)

    expected = (
        403 if endpoint in KITCHEN_MANAGER_DENIED_READ_ENDPOINTS else 200
    )

    assert response.status_code == expected, (
        f"KITCHEN_MANAGER accessing {endpoint}: "
        f"{response.status_code}: {response.text}"
    )


@pytest.mark.parametrize("endpoint", READ_ENDPOINTS)
def test_staff_without_assignments_is_denied(
    client, setup_data, db, endpoint
):
    staff = create_test_user(
        db, setup_data["campus"].id, "STAFF"
    )
    authenticate_as(client, staff)

    response = client.get(endpoint)

    assert response.status_code == 403, (
        f"STAFF accessing {endpoint}: "
        f"{response.status_code}: {response.text}"
    )


def test_staff_can_access_assigned_inventory_module(
    client, setup_data, db
):
    staff = create_test_user(
        db, setup_data["campus"].id, "STAFF"
    )

    assign_staff_permission(
        db,
        staff,
        setup_data["user"],
        "inventory",
        "Inventory",
        "inventory.read",
    )

    authenticate_as(client, staff)

    response = client.get("/api/master/categories")
    assert response.status_code == 200, response.text


def test_staff_cannot_access_unassigned_menu_module(
    client, setup_data, db
):
    staff = create_test_user(
        db, setup_data["campus"].id, "STAFF"
    )

    assign_staff_permission(
        db,
        staff,
        setup_data["user"],
        "inventory",
        "Inventory",
        "inventory.read",
    )

    authenticate_as(client, staff)

    response = client.get("/api/master/menus")
    assert response.status_code == 403


def test_inactive_staff_assignment_does_not_grant_access(
    client, setup_data, db
):
    staff = create_test_user(
        db, setup_data["campus"].id, "STAFF"
    )

    assign_staff_permission(
        db,
        staff,
        setup_data["user"],
        "inventory",
        "Inventory",
        "inventory.read",
    )

    assignment = (
        db.query(StaffAccessAssignment)
        .filter(
            StaffAccessAssignment.staff_user_id == staff.id
        )
        .first()
    )

    assert assignment is not None

    assignment.is_active = False
    db.commit()

    authenticate_as(client, staff)

    response = client.get("/api/master/categories")
    assert response.status_code == 403


@pytest.mark.parametrize("role", ["KITCHEN_MANAGER", "STAFF"])
def test_only_admin_can_create_users(
    client, setup_data, db, role
):
    user = create_test_user(
        db, setup_data["campus"].id, role
    )
    authenticate_as(client, user)

    response = client.post(
        "/api/auth/users",
        json={
            "full_name": "Another Staff Member",
            "email": f"new-{uuid4().hex[:8]}@test.com",
            "password": "TestPassword123!",
            "role": "STAFF",
        },
    )

    assert response.status_code == 403


@pytest.mark.parametrize("role", ["KITCHEN_MANAGER", "STAFF"])
def test_only_admin_can_view_authorization_modules(
    client, setup_data, db, role
):
    user = create_test_user(
        db, setup_data["campus"].id, role
    )
    authenticate_as(client, user)

    response = client.get("/api/authorization/modules")
    assert response.status_code == 403


def test_staff_can_view_own_effective_permissions(
    client, setup_data, db
):
    staff = create_test_user(
        db, setup_data["campus"].id, "STAFF"
    )

    assign_staff_permission(
        db,
        staff,
        setup_data["user"],
        "inventory",
        "Inventory",
        "inventory.read",
    )

    authenticate_as(client, staff)

    response = client.get("/api/authorization/me")
    assert response.status_code == 200

    data = response.json()
    assert data["role"] == "STAFF"
    assert "inventory.read" in data["permissions"]


def test_staff_permissions_are_empty_by_default(
    client, setup_data, db
):
    staff = create_test_user(
        db, setup_data["campus"].id, "STAFF"
    )
    authenticate_as(client, staff)

    response = client.get("/api/authorization/me")
    assert response.status_code == 200

    data = response.json()
    assert data["role"] == "STAFF"
    assert data["permissions"] == []


def test_admin_can_view_authorization_modules(
    client, setup_data
):
    authenticate_as(client, setup_data["user"])

    response = client.get("/api/authorization/modules")
    assert response.status_code == 200


def test_admin_has_all_effective_permissions(
    client, setup_data
):
    authenticate_as(client, setup_data["user"])

    response = client.get("/api/authorization/me")
    assert response.status_code == 200

    data = response.json()
    assert data["role"] == "ADMIN"
    assert "inventory.read" in data["permissions"]
    assert "menu.read" in data["permissions"]
