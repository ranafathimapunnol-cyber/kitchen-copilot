from app.core.config import settings


def test_login_sets_http_only_auth_cookies(client, setup_data):
    client.cookies.delete(settings.ACCESS_COOKIE_NAME)

    response = client.post(
        "/api/auth/login",
        json={
            "email": "admin@test.com",
            "password": setup_data["password"],
        },
    )

    assert response.status_code == 200
    assert response.json()["email"] == "admin@test.com"

    access_cookie = client.cookies.get(settings.ACCESS_COOKIE_NAME)
    refresh_cookie = client.cookies.get(settings.REFRESH_COOKIE_NAME)

    assert access_cookie
    assert refresh_cookie

    set_cookie_headers = response.headers.get_list("set-cookie")

    access_header = next(
        header for header in set_cookie_headers
        if header.startswith(f"{settings.ACCESS_COOKIE_NAME}=")
    )
    refresh_header = next(
        header for header in set_cookie_headers
        if header.startswith(f"{settings.REFRESH_COOKIE_NAME}=")
    )

    assert "httponly" in access_header.lower()
    assert "httponly" in refresh_header.lower()


def test_login_rejects_invalid_password(client):
    client.cookies.delete(settings.ACCESS_COOKIE_NAME)

    response = client.post(
        "/api/auth/login",
        json={
            "email": "admin@test.com",
            "password": "WrongPassword123!",
        },
    )

    assert response.status_code == 401


def test_me_uses_access_cookie(client, setup_data):
    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json()["id"] == setup_data["user"].id
    assert response.json()["role"] == "ADMIN"


def test_refresh_rotates_auth_cookies(client, setup_data):
    client.cookies.delete(settings.ACCESS_COOKIE_NAME)

    login_response = client.post(
        "/api/auth/login",
        json={
            "email": "admin@test.com",
            "password": setup_data["password"],
        },
    )
    assert login_response.status_code == 200

    old_access = client.cookies.get(settings.ACCESS_COOKIE_NAME)
    old_refresh = client.cookies.get(settings.REFRESH_COOKIE_NAME)

    response = client.post("/api/auth/refresh")

    assert response.status_code == 200
    assert response.json()["email"] == "admin@test.com"

    new_access = client.cookies.get(settings.ACCESS_COOKIE_NAME)
    new_refresh = client.cookies.get(settings.REFRESH_COOKIE_NAME)

    assert new_access
    assert new_refresh
    assert new_access != old_access
    assert new_refresh != old_refresh


def test_refresh_rejects_missing_refresh_cookie(client):
    client.cookies.delete(settings.REFRESH_COOKIE_NAME)

    response = client.post("/api/auth/refresh")

    assert response.status_code == 401


def test_logout_clears_auth_cookies(client):
    response = client.post("/api/auth/logout")

    assert response.status_code == 200
    assert response.json()["message"] == "Logged out successfully"

    set_cookie_headers = response.headers.get_list("set-cookie")

    for cookie_name in (
        settings.ACCESS_COOKIE_NAME,
        settings.REFRESH_COOKIE_NAME,
        settings.CSRF_COOKIE_NAME,
    ):
        matching_headers = [
            header for header in set_cookie_headers
            if header.startswith(f"{cookie_name}=")
        ]
        assert matching_headers
        assert any(
            "max-age=0" in header.lower()
            or "expires=" in header.lower()
            for header in matching_headers
        )


def test_csrf_rejects_missing_or_mismatched_header(client):
    client.headers[settings.CSRF_HEADER_NAME] = "incorrect-token"

    response = client.post("/api/auth/logout")

    assert response.status_code == 403
    assert response.json()["detail"] == "CSRF token missing or invalid."
