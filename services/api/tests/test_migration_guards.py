"""The guarded migrations refuse to run without their exact authorization.

The API container runs "alembic upgrade head" at start; these guards are what
stop a rebuilt image from applying M1, M2 or M3 to a database with real
records. The checks run before any schema operation, so they are tested here
without a database. The CI workflow authorizes them only for its fresh,
empty service database (scripts/ci_migrate.sh).
"""

import importlib.util
from pathlib import Path

import pytest

VERSIONS = Path(__file__).resolve().parents[1] / "migrations" / "versions"
GUARDED = {
    "d5e8f0b2a314": ("d5e8f0b2a314_platform_super_admin.py", "KC_AUTHORIZE_M1"),
    "e2b7c4d9a5f1": ("e2b7c4d9a5f1_campus_logo_and_photo.py", "KC_AUTHORIZE_MIGRATION"),
    "a7d3e9b1c4f2": ("a7d3e9b1c4f2_one_admin_tasks_permissions.py", "KC_AUTHORIZE_MIGRATION"),
}


def load(revision):
    filename, _var = GUARDED[revision]
    spec = importlib.util.spec_from_file_location(f"migration_{revision}", VERSIONS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("revision", GUARDED)
def test_guard_names_the_expected_variable(revision):
    module = load(revision)
    assert module.revision == revision
    assert module.AUTHORIZATION_ENV == GUARDED[revision][1]


@pytest.mark.parametrize("revision", GUARDED)
@pytest.mark.parametrize("value", [None, "", "yes", "true", "1", "d5e8f0b2a314x"])
def test_guard_refuses_missing_or_wrong_authorization(revision, value, monkeypatch):
    module = load(revision)
    monkeypatch.delenv("KC_AUTHORIZE_M1", raising=False)
    monkeypatch.delenv("KC_AUTHORIZE_MIGRATION", raising=False)
    if value is not None:
        monkeypatch.setenv(module.AUTHORIZATION_ENV, value)
    with pytest.raises(RuntimeError, match="is not authorized"):
        module.upgrade()


def test_m2_and_m3_do_not_accept_each_others_authorization(monkeypatch):
    m2, m3 = load("e2b7c4d9a5f1"), load("a7d3e9b1c4f2")
    monkeypatch.setenv("KC_AUTHORIZE_MIGRATION", "a7d3e9b1c4f2")
    with pytest.raises(RuntimeError, match="is not authorized"):
        m2.upgrade()
    monkeypatch.setenv("KC_AUTHORIZE_MIGRATION", "e2b7c4d9a5f1")
    with pytest.raises(RuntimeError, match="is not authorized"):
        m3.upgrade()


def test_m1_is_not_authorized_by_the_shared_variable(monkeypatch):
    m1 = load("d5e8f0b2a314")
    monkeypatch.delenv("KC_AUTHORIZE_M1", raising=False)
    monkeypatch.setenv("KC_AUTHORIZE_MIGRATION", "d5e8f0b2a314")
    with pytest.raises(RuntimeError, match="is not authorized"):
        m1.upgrade()
