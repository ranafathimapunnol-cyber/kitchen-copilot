"""
Account creation by a campus ADMIN (POST /api/auth/users).

Approved rules:
- An ADMIN may create only KITCHEN_MANAGER and STAFF accounts.
- An ADMIN may never create ADMIN or SUPER_ADMIN accounts; those are
  provisioned by a separate process.
- The new account always belongs to the creating ADMIN's campus.
"""

from uuid import uuid4

import pytest

from app.models import Campus, User
from app.models.audit_log import AuditLog

from tests.test_authorization import authenticate_as, create_test_user


USERS_URL = "/api/auth/users"


def new_user_payload(role, **extra):
    payload = {
        "full_name": "New Campus User",
        "email": f"new-{uuid4().hex[:8]}@test.com",
        "password": "TestPassword123!",
        "role": role,
    }
    payload.update(extra)
    return payload


def user_count(db, email):
    return db.query(User).filter(User.email == email).count()


@pytest.mark.parametrize("role", ["KITCHEN_MANAGER", "STAFF"])
def test_admin_can_create_kitchen_manager_and_staff(
    client, db, setup_data, role
):
    payload = new_user_payload(role)

    response = client.post(USERS_URL, json=payload)

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["role"] == role
    assert data["campus_id"] == setup_data["campus"].id
    assert data["is_active"] is True

    audit = (
        db.query(AuditLog)
        .filter(
            AuditLog.entity_type == "USER",
            AuditLog.entity_id == data["id"],
            AuditLog.action == "CREATE",
        )
        .first()
    )
    assert audit is not None
    assert audit.campus_id == setup_data["campus"].id
    assert audit.user_id == setup_data["user"].id


def test_admin_cannot_create_admin(client, db):
    payload = new_user_payload("ADMIN")

    response = client.post(USERS_URL, json=payload)

    assert response.status_code == 403, response.text
    assert user_count(db, payload["email"]) == 0
    assert (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == "USER")
        .count()
        == 0
    )


@pytest.mark.parametrize("role", ["SUPER_ADMIN", "OWNER", "admin", ""])
def test_unknown_or_platform_roles_are_rejected(client, db, role):
    payload = new_user_payload(role)

    response = client.post(USERS_URL, json=payload)

    assert response.status_code == 422, response.text
    assert user_count(db, payload["email"]) == 0


def test_denied_role_is_rejected_before_email_lookup(
    client, db, setup_data
):
    # An existing email must not change the answer for a forbidden role,
    # so the denied path cannot be used to probe for registered emails.
    payload = new_user_payload("ADMIN", email=setup_data["user"].email)

    response = client.post(USERS_URL, json=payload)

    assert response.status_code == 403, response.text


def test_campus_comes_from_the_authenticated_admin(client, db, setup_data):
    other_campus = Campus(name="Other User Campus", code="OTHER-USERS")
    db.add(other_campus)
    db.commit()

    payload = new_user_payload("STAFF", campus_id=other_campus.id)

    response = client.post(USERS_URL, json=payload)

    assert response.status_code == 201, response.text
    assert response.json()["campus_id"] == setup_data["campus"].id

    created = db.query(User).filter(User.email == payload["email"]).one()
    assert created.campus_id == setup_data["campus"].id


@pytest.mark.parametrize("creator_role", ["KITCHEN_MANAGER", "STAFF"])
@pytest.mark.parametrize("target_role", ["KITCHEN_MANAGER", "STAFF", "ADMIN"])
def test_non_admins_cannot_create_any_account(
    client, db, setup_data, creator_role, target_role
):
    creator = create_test_user(db, setup_data["campus"].id, creator_role)
    authenticate_as(client, creator)
    payload = new_user_payload(target_role)

    response = client.post(USERS_URL, json=payload)

    assert response.status_code == 403, response.text
    assert user_count(db, payload["email"]) == 0
