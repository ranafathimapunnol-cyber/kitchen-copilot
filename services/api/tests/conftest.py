import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Campus, User, UserRole
from app.core.config import settings
from app.core.security import create_access_token, hash_password


# Importing app.models registers all project models with SQLAlchemy.
TEST_ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(
    bind=TEST_ENGINE,
    autoflush=False,
    autocommit=False,
)


@pytest.fixture
def db():
    Base.metadata.create_all(bind=TEST_ENGINE)

    session = TestingSessionLocal()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=TEST_ENGINE)


@pytest.fixture
def setup_data(db):
    campus = Campus(
        name="Test Campus",
        code="TEST-CAMPUS",
    )
    db.add(campus)
    db.flush()

    password = "TestPassword123!"

    user = User(
        campus_id=campus.id,
        full_name="Test Administrator",
        email="admin@test.com",
        password_hash=hash_password(password),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "campus": campus,
        "user": user,
        "password": password,
        "token": create_access_token(user.id),
    }


@pytest.fixture
def client(db, setup_data):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        # Obtain a CSRF token and its cookie.
        csrf_response = test_client.get("/api/auth/csrf")
        assert csrf_response.status_code == 200

        csrf_token = csrf_response.json()["csrf_token"]

        # Send the matching CSRF header on unsafe requests.
        test_client.headers.update({
            settings.CSRF_HEADER_NAME: csrf_token,
        })

        # Authenticate the default test administrator using a cookie.
        test_client.cookies.set(
            settings.ACCESS_COOKIE_NAME,
            setup_data["token"],
        )

        yield test_client

    app.dependency_overrides.clear()
