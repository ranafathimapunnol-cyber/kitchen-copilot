"""Owner request 27 Nov 2026: one active Admin per campus (with safe
replacement), Admin adds Staff and Kitchen Managers, assigns individual
Staff permissions (incl. goods receipts, reports, tasks, Copilot, supplier
bills), Staff tasks, and the role limits of the Kitchen Manager."""

import pytest
from sqlalchemy.exc import IntegrityError

from app.core import email as email_transport
from app.core.config import settings
from app.models import AuditLog, User
from app.models.authorization import Permission
from app.models.platform import PlatformAuditLog
from app.models.tasks import StaffTask
from app.models.user import UserRole

from tests.test_kitchen_issues import kitchen  # noqa: F401 (fixture)
from tests.test_operational_authority import PASSWORD_HASH, act_as, client, db, grant, world  # noqa: F401
from tests.test_platform import P, platform_as, root  # noqa: F401


def ok(response, code=200):
    assert response.status_code == code, response.text
    return response.json()


@pytest.fixture
def mail(monkeypatch):
    sent = []
    monkeypatch.setattr(settings, "FRONTEND_BASE_URL", "http://localhost:8080")
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.mail.invalid")
    monkeypatch.setattr(settings, "EMAIL_FROM", "no-reply@example.com")
    monkeypatch.setattr(email_transport, "send_email", lambda to, *a, **k: sent.append(to))
    return sent


# ---------------- one active Admin per campus ----------------

def test_database_refuses_a_second_active_admin(db, world):
    db.add(User(campus_id=world.a.campus.id, full_name="Second", email="second@example.com", password_hash=PASSWORD_HASH,
                role=UserRole.ADMIN, is_active=True))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
    # An inactive second Admin row, and Admins of other campuses, are fine.
    db.add(User(campus_id=world.a.campus.id, full_name="Old", email="old@example.com", password_hash=PASSWORD_HASH,
                role=UserRole.ADMIN, is_active=False))
    db.commit()


def test_platform_invite_refuses_a_second_admin(client, world, root, mail):
    platform_as(client, root)
    response = client.post(f"{P}/campuses/{world.a.campus.id}/admins", json={"full_name": "Two", "email": "two@example.com"})
    assert response.status_code == 409 and "Replace Admin" in response.json()["detail"]
    assert mail == []


def test_replace_admin_hands_over_and_keeps_the_old_account(client, db, world, root, mail):
    old = world.a.admin
    platform_as(client, root)
    result = ok(client.post(f"{P}/campuses/{world.a.campus.id}/admins/replace",
                            json={"full_name": "New Head", "email": "new.head@example.com"}), 201)
    assert result["previous"]["email"] == old.email and mail == ["new.head@example.com"]
    db.expire_all()
    assert db.get(User, old.id).is_active is False                         # kept, deactivated
    admins = db.query(User).filter(User.campus_id == world.a.campus.id, User.role == UserRole.ADMIN,
                                   User.is_active.is_(True)).all()
    assert [a.email for a in admins] == ["new.head@example.com"]
    act_as(client, old)
    assert client.get("/api/auth/me").status_code == 401                   # old sessions refused
    assert db.query(PlatformAuditLog).filter_by(action="REPLACE_ADMIN", outcome="SUCCESS").count() == 1
    assert db.query(AuditLog).filter_by(action="DEACTIVATE", entity_type="USER", entity_id=old.id).count() == 1


def test_replace_admin_changes_nothing_when_the_email_fails(client, db, world, root, monkeypatch, mail):
    def fail(*_a, **_k):
        raise email_transport.EmailDeliveryError("down")
    monkeypatch.setattr(email_transport, "send_email", fail)
    platform_as(client, root)
    response = client.post(f"{P}/campuses/{world.a.campus.id}/admins/replace",
                           json={"full_name": "New Head", "email": "new.head@example.com"})
    assert response.status_code == 503
    db.expire_all()
    assert db.get(User, world.a.admin.id).is_active is True
    assert db.query(User).filter_by(email="new.head@example.com").count() == 0
    assert db.query(PlatformAuditLog).filter_by(action="REPLACE_ADMIN", outcome="FAILURE").count() == 1


def test_an_admin_cannot_reactivate_a_second_admin(client, db, world):
    spare = User(campus_id=world.a.campus.id, full_name="Spare", email="spare@example.com", password_hash=PASSWORD_HASH,
                 role=UserRole.ADMIN, is_active=False)
    db.add(spare)
    db.commit()
    act_as(client, world.a.admin)
    response = client.post(f"/api/admin/users/{spare.id}/reactivate", json={"reason": "bring back"})
    assert response.status_code == 409 and "already has its active Admin" in response.json()["detail"]


# ---------------- Admin adds Staff and Kitchen Managers ----------------

@pytest.mark.parametrize("role", ["STAFF", "KITCHEN_MANAGER"])
def test_admin_adds_staff_and_managers_to_own_campus(client, db, world, role):
    act_as(client, world.a.admin)
    made = ok(client.post("/api/auth/users", json={"full_name": "New Person", "email": f"{role.lower()}.new@example.com",
                                                   "password": "Start-Pass-123", "role": role}), 201)
    assert made["role"] == role and made["campus_id"] == world.a.campus.id
    assert db.query(AuditLog).filter_by(action="CREATE", entity_type="USER", entity_id=made["id"]).count() == 1


@pytest.mark.parametrize("role", ["ADMIN", "SUPER_ADMIN"])
def test_admin_cannot_create_admins(client, world, role):
    act_as(client, world.a.admin)
    response = client.post("/api/auth/users", json={"full_name": "X Y", "email": "x.y@example.com",
                                                     "password": "Start-Pass-123", "role": role})
    assert response.status_code in (403, 422)


def test_kitchen_manager_cannot_manage_users_or_permissions(client, db, world):
    act_as(client, world.a.manager)
    assert client.post("/api/auth/users", json={"full_name": "X Y", "email": "x.y@example.com",
                                                "password": "Start-Pass-123", "role": "STAFF"}).status_code == 403
    assert client.get("/api/admin/users").status_code == 403
    assert client.get("/api/authorization/staff").status_code == 403
    perm = db.query(Permission).filter_by(permission_code="task.read").one()
    assert client.put(f"/api/authorization/staff/{world.a.staff.id}/permissions",
                      json={"permission_ids": [perm.id]}).status_code == 403
    assert client.post("/api/tasks", json={"title": "Count rice", "category": "STOCK_COUNT",
                                           "assigned_to": world.a.staff.id}).status_code == 403


def test_kitchen_manager_cannot_delete_items_and_stocked_items_are_protected(client, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    assert client.delete(f"/api/master/items/{a.item.id}").status_code == 403
    act_as(client, a.admin)
    assert client.delete(f"/api/master/items/{a.item.id}").status_code == 409      # has opening stock


# ---------------- Staff permissions ----------------

NEW_ASSIGNABLE = ["goods_receipt.read", "goods_receipt.create", "goods_receipt.update", "report.read", "task.read",
                  "task.update", "copilot.read", "purchase_bill.read", "purchase_bill.create", "purchase_bill.update"]


def test_admin_assigns_and_revokes_the_new_staff_permissions(client, db, world):
    ids = {p.permission_code: p.id for p in db.query(Permission).filter(Permission.permission_code.in_(NEW_ASSIGNABLE))}
    act_as(client, world.a.admin)
    ok(client.put(f"/api/authorization/staff/{world.a.staff.id}/permissions",
                  json={"permission_ids": list(ids.values())}))
    act_as(client, world.a.staff)
    held = set(client.get("/api/authorization/me").json()["permissions"])
    assert set(NEW_ASSIGNABLE) <= held
    act_as(client, world.a.admin)
    ok(client.delete(f"/api/authorization/staff/{world.a.staff.id}/permissions/{ids['copilot.read']}"))
    act_as(client, world.a.staff)
    assert "copilot.read" not in client.get("/api/authorization/me").json()["permissions"]
    assert db.query(AuditLog).filter_by(entity_type="STAFF_ACCESS").count() == 2   # grant and revoke


def test_staff_permission_gates(client, db, world):
    staff, admin = world.a.staff, world.a.admin
    act_as(client, staff)
    assert client.get("/api/receipts").status_code == 403
    assert client.get("/api/reports/catalog").status_code == 403
    assert client.get("/api/agent/status").status_code == 403
    assert client.get("/api/tasks").status_code == 403
    for code in ("goods_receipt.read", "report.read", "copilot.read", "task.read"):
        grant(db, staff, admin, code)
    assert client.get("/api/receipts").status_code == 200
    assert client.get("/api/reports/catalog").status_code == 200
    assert client.get("/api/agent/status").status_code == 200
    assert client.get("/api/tasks").status_code == 200
    # goods_receipt.read does not open items or suppliers for writing.
    assert client.post("/api/master/suppliers", json={"name": "Nope"}).status_code == 403


def test_managers_keep_receipts_reports_and_copilot(client, world):
    act_as(client, world.a.manager)
    for path in ("/api/receipts", "/api/reports/catalog", "/api/agent/status", "/api/tasks"):
        assert client.get(path).status_code == 200, path


# ---------------- Staff tasks ----------------

def new_task(client, staff_id, **extra):
    body = {"title": "Count the rice store", "category": "STOCK_COUNT", "priority": "HIGH", "assigned_to": staff_id,
            "due_date": "2026-11-30", **extra}
    return ok(client.post("/api/tasks", json=body), 201)


def test_task_lifecycle_and_audit(client, db, world):
    a = world.a
    grant(db, a.staff, a.admin, "task.read")
    grant(db, a.staff, a.admin, "task.update")
    act_as(client, a.admin)
    task = new_task(client, a.staff.id)
    assert task["status"] == "OPEN" and task["assigned_to_name"] == a.staff.full_name
    edited = ok(client.put(f"/api/tasks/{task['id']}", params={"version": 1},
                           json={"title": "Count the rice and dal store", "category": "STOCK_COUNT", "priority": "NORMAL",
                                 "assigned_to": a.staff.id}))
    assert edited["version"] == 2
    assert client.put(f"/api/tasks/{task['id']}", params={"version": 1},
                      json={"title": "Stale", "category": "GENERAL", "assigned_to": a.staff.id}).status_code == 409

    act_as(client, a.staff)
    mine = ok(client.get("/api/tasks"))
    assert [t["id"] for t in mine["items"]] == [task["id"]] and mine["can_manage"] is False and mine["can_update_own"]
    started = ok(client.post(f"/api/tasks/{task['id']}/status", json={"status": "IN_PROGRESS", "version": 2}))
    done = ok(client.post(f"/api/tasks/{task['id']}/status", json={"status": "DONE", "version": started["version"],
                                                                      "note": "Rice 18 kg, dal 6 kg"}))
    assert done["completed_at"] and done["staff_note"] == "Rice 18 kg, dal 6 kg"
    assert client.post(f"/api/tasks/{task['id']}/status",
                       json={"status": "CANCELLED", "version": done["version"]}).status_code == 403
    act_as(client, a.admin)
    reopened = ok(client.post(f"/api/tasks/{task['id']}/status", json={"status": "OPEN", "version": done["version"]}))
    assert reopened["completed_at"] is None
    actions = [r.action for r in db.query(AuditLog).filter_by(entity_type="STAFF_TASK").order_by(AuditLog.id)]
    assert actions == ["CREATE", "UPDATE", "STATUS", "STATUS", "STATUS"]


def test_task_visibility_and_isolation(client, db, world):
    a, b = world.a, world.b
    other = User(campus_id=a.campus.id, full_name="Other Staff", email="other.staff@example.com", password_hash=PASSWORD_HASH,
                 role=UserRole.STAFF, is_active=True)
    db.add(other)
    db.commit()
    for person in (a.staff, other):
        grant(db, person, a.admin, "task.read")
    act_as(client, a.admin)
    mine = new_task(client, a.staff.id)
    theirs = new_task(client, other.id, title="Clean the store room", category="CLEANING")
    # Only STAFF of this campus can be assignees.
    assert client.post("/api/tasks", json={"title": "Wrong", "category": "GENERAL", "assigned_to": a.manager.id}).status_code == 422
    assert client.post("/api/tasks", json={"title": "Wrong", "category": "GENERAL", "assigned_to": b.staff.id}).status_code == 422

    act_as(client, a.staff)
    assert [t["id"] for t in ok(client.get("/api/tasks"))["items"]] == [mine["id"]]
    assert client.post(f"/api/tasks/{theirs['id']}/status", json={"status": "DONE", "version": 1}).status_code == 404
    assert client.post(f"/api/tasks/{mine['id']}/status", json={"status": "IN_PROGRESS", "version": 1}).status_code == 403  # no task.update

    act_as(client, a.manager)
    assert {t["id"] for t in ok(client.get("/api/tasks"))["items"]} == {mine["id"], theirs["id"]}
    assert client.post(f"/api/tasks/{mine['id']}/status", json={"status": "DONE", "version": 1}).status_code == 403

    act_as(client, b.admin)
    assert ok(client.get("/api/tasks"))["items"] == []
    assert client.put(f"/api/tasks/{mine['id']}", params={"version": 1},
                      json={"title": "Steal", "category": "GENERAL", "assigned_to": b.staff.id}).status_code == 404
    assert db.query(StaffTask).count() == 2
