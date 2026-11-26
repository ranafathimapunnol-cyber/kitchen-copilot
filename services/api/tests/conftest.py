import pytest

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Campus, User, UserRole
from app.models.authorization import Module, Permission
from app.core.config import settings
from app.core.security import create_access_token, hash_password


# Never use the application database for automated tests.
TEST_DATABASE_NAME = "kitchen_copilot_test_db"

database_url = make_url(settings.DATABASE_URL)

# Connect to PostgreSQL's default maintenance database to create
# the separate test database if it does not already exist.
admin_engine = create_engine(
    database_url.set(database="postgres"),
    isolation_level="AUTOCOMMIT",
)

with admin_engine.connect() as connection:
    database_exists = connection.execute(
        text("SELECT 1 FROM pg_database WHERE datname = :name"),
        {"name": TEST_DATABASE_NAME},
    ).scalar()

    if not database_exists:
        connection.exec_driver_sql(
            f'CREATE DATABASE "{TEST_DATABASE_NAME}"'
        )

admin_engine.dispose()

# All automated tests use this PostgreSQL database.
TEST_DATABASE_URL = database_url.set(database=TEST_DATABASE_NAME)

TEST_ENGINE = create_engine(
    TEST_DATABASE_URL,
    pool_pre_ping=True,
)

TestingSessionLocal = sessionmaker(
    bind=TEST_ENGINE,
    autoflush=False,
    autocommit=False,
)


MODULES = [
    ("Dashboard", "dashboard"),
    ("Headcount", "headcount"),
    ("Inventory", "inventory"),
    ("Purchase Order", "purchase_order"),
    ("Supplier Bills", "purchase_bill"),
    ("Consumption", "consumption"),
    ("Outsourced Food", "outsourced_food"),
    ("Menu", "menu"),
    ("Audit", "audit"),
]

PERMISSIONS = {
    "dashboard": ["READ"],
    "headcount": ["CREATE", "READ", "UPDATE"],
    "inventory": ["CREATE", "READ", "UPDATE"],
    "purchase_order": ["CREATE", "READ", "UPDATE"],
    "purchase_bill": ["CREATE", "READ", "UPDATE"],
    "consumption": ["CREATE", "READ", "UPDATE"],
    "outsourced_food": ["CREATE", "READ", "UPDATE"],
    "menu": ["CREATE", "READ", "UPDATE"],
    "audit": ["READ"],
}


def seed_authorization_data(db):
    """Seed approved modules and permissions in the test database."""

    module_ids = {}

    for module_name, module_code in MODULES:
        module = Module(
            name=module_name,
            code=module_code,
        )
        db.add(module)
        db.flush()

        module_ids[module_code] = module.id

    for module_code, actions in PERMISSIONS.items():
        for action in actions:
            db.add(
                Permission(
                    module_id=module_ids[module_code],
                    action=action,
                    permission_code=f"{module_code}.{action.lower()}",
                )
            )

    db.commit()


@pytest.fixture
def db():
    Base.metadata.create_all(bind=TEST_ENGINE)

    session = TestingSessionLocal()

    try:
        seed_authorization_data(session)
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
        "token": create_access_token(user.id, user.password_hash),
    }


@pytest.fixture
def client(db, setup_data):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as test_client:
            csrf_response = test_client.get("/api/auth/csrf")
            assert csrf_response.status_code == 200

            csrf_token = csrf_response.json()["csrf_token"]

            test_client.headers.update({
                settings.CSRF_HEADER_NAME: csrf_token
            })

            test_client.cookies.set(
                settings.ACCESS_COOKIE_NAME,
                setup_data["token"],
            )

            yield test_client
    finally:
        app.dependency_overrides.clear()
