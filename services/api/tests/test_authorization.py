import pytest

from app.core.config import settings
from app.core.security import create_access_token
from app.models import User, UserRole


@pytest.mark.parametrize(
    "role,endpoint,expected",
    [
        ("ADMIN", "/api/master/categories", 200),
        ("KITCHEN_MANAGER", "/api/master/categories", 200),
        ("STORE_KEEPER", "/api/master/categories", 403),
        ("ACCOUNTS", "/api/master/categories", 403),

        ("ADMIN", "/api/master/suppliers", 200),
        ("ACCOUNTS", "/api/master/suppliers", 200),
        ("KITCHEN_MANAGER", "/api/master/suppliers", 403),
        ("STORE_KEEPER", "/api/master/suppliers", 403),

        ("ADMIN", "/api/purchases/", 200),
        ("ACCOUNTS", "/api/purchases/", 200),
        ("KITCHEN_MANAGER", "/api/purchases/", 403),
        ("STORE_KEEPER", "/api/purchases/", 403),

        ("ADMIN", "/api/stock/movements", 200),
        ("KITCHEN_MANAGER", "/api/stock/movements", 200),
        ("STORE_KEEPER", "/api/stock/movements", 200),
        ("ACCOUNTS", "/api/stock/movements", 403),

        ("ADMIN", "/api/master/menus", 200),
        ("KITCHEN_MANAGER", "/api/master/menus", 200),
        ("STORE_KEEPER", "/api/master/menus", 403),
        ("ACCOUNTS", "/api/master/menus", 403),
    ],
)
def test_role_access_matrix(
    client, db, setup_data, role, endpoint, expected
):
    if role == "ADMIN":
        user = setup_data["user"]
    else:
        user = User(
            campus_id=setup_data["campus"].id,
            full_name=f"Test {role}",
            email=f"{role.lower()}@test.com",
            password_hash="not-used-for-cookie-auth",
            role=UserRole(role),
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    client.cookies.set(
        settings.ACCESS_COOKIE_NAME,
        create_access_token(user.id),
    )

    response = client.get(endpoint)

    assert response.status_code == expected, (
        f"{role} accessing {endpoint}: "
        f"expected {expected}, got {response.status_code}: {response.text}"
    )


@pytest.mark.parametrize(
    "role",
    ["KITCHEN_MANAGER", "STORE_KEEPER", "ACCOUNTS"],
)
def test_only_admin_can_create_users(
    client, db, setup_data, role
):
    user = User(
        campus_id=setup_data["campus"].id,
        full_name=f"Test {role}",
        email=f"create-{role.lower()}@test.com",
        password_hash="not-used-for-cookie-auth",
        role=UserRole(role),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    client.cookies.set(
        settings.ACCESS_COOKIE_NAME,
        create_access_token(user.id),
    )

    response = client.post(
        "/api/auth/users",
        json={
            "full_name": "New Test User",
            "email": "new-user@test.com",
            "password": "TestPassword123!",
            "role": "STORE_KEEPER",
        },
    )

    assert response.status_code == 403
