"""
Stage 6 meal planning on PostgreSQL (kitchen_copilot_test_db, shared
tests/conftest.py fixtures). Covers what SQLite cannot:
- the PostgreSQL triggers (S6-2) for a superuser: approved and cancelled
  standards, suggestion basis rows, approved and cancelled plans and the
  lines of a plan that is not a draft refuse UPDATE and DELETE; an approved
  plan may only become CANCELLED; approval needs every line's snapshot;
- the check constraints and the one-live-plan index;
- races: two plans for one slot, approving one standard twice, approving
  several versions at once (distinct version numbers), approve against
  cancel, copying a menu twice at once;
- no stock, purchasing or supplier row is written by any planning action
  (S6-5), compared by table content.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.core.clock import campus_today
from app.core.config import settings
from app.core.security import create_access_token
from app.models import Category, Item, MealSession, Menu, MenuMainItem, Permission, StaffAccessAssignment, Unit, UnitConversion
from app.models.planning import MealPlan, MealPlanLine, PortionStandard

from tests.test_authorization import create_test_user
from tests.test_stock_counts_postgres import race_all
from tests.test_stock_ledger_postgres import engine_factory, parallel_clients  # noqa: F401 (fixtures)

STANDARDS = "/api/portion-standards"
PLANS = "/api/meal-plans"
WRITE_TABLES = (
    "stock_movements", "stock_openings", "kitchen_issues", "kitchen_issue_items", "kitchen_returns",
    "kitchen_return_items", "stock_counts", "stock_count_items", "stock_adjustments", "purchases", "purchase_items",
    "purchase_orders", "purchase_order_items", "goods_receipts", "goods_receipt_items", "supplier_payments",
    "supplier_returns", "supplier_return_items", "waste_records", "waste_items",
)


def act_as(client, user):
    client.cookies.set(settings.ACCESS_COOKIE_NAME, create_access_token(user.id, user.password_hash))


def today(offset=0):
    return (campus_today() + timedelta(days=offset)).isoformat()


@pytest.fixture
def planning_pg(client, db, setup_data):
    campus_id = setup_data["campus"].id
    kg = Unit(campus_id=campus_id, name="Kilogram", symbol="kg", dimension="weight")
    g = Unit(campus_id=campus_id, name="Gram", symbol="g", dimension="weight")
    category = Category(campus_id=campus_id, name="Grains")
    lunch = MealSession(campus_id=campus_id, name="Lunch")
    db.add_all([kg, g, category, lunch])
    db.flush()
    db.add(UnitConversion(campus_id=campus_id, from_unit_id=g.id, to_unit_id=kg.id, factor=Decimal("0.001")))
    rice = Item(campus_id=campus_id, name="Rice", category_id=category.id, standard_unit_id=kg.id, minimum_stock=0,
                item_kind="RAW")
    chicken = Item(campus_id=campus_id, name="Chicken", category_id=category.id, standard_unit_id=kg.id,
                   minimum_stock=0, item_kind="RAW")
    biryani = Menu(campus_id=campus_id, name="Veg Biryani", meal_session_id=lunch.id)
    db.add_all([rice, chicken, biryani])
    db.commit()
    manager = create_test_user(db, campus_id, "KITCHEN_MANAGER")
    return {"campus_id": campus_id, "kg": kg.id, "g": g.id, "rice": rice.id, "chicken": chicken.id,
            "lunch": lunch.id, "biryani": biryani.id, "admin": setup_data["user"], "manager": manager}


def standard_body(k, item="rice", qty="150", effective=None):
    return {"menu_id": k["biryani"], "item_id": k[item], "quantity_per_person": qty, "unit_id": k["g"],
            "effective_from": effective or today()}


def ok(response, code=200):
    assert response.status_code == code, response.text
    return response.json()


def approved_standard(client, k, item="rice", qty="150"):
    draft = ok(client.post(STANDARDS, json=standard_body(k, item, qty)), 201)
    return ok(client.post(f"{STANDARDS}/{draft['id']}/approve"))


def plan_body(k, items=("rice",), headcount=450, day=None):
    return {"plan_date": day or today(), "meal_session_id": k["lunch"], "menu_id": k["biryani"],
            "expected_headcount": headcount, "lines": [{"item_id": k[i]} for i in items]}


def refused(db, sql, **params):
    """(refused?, first line of the error); always rolled back."""
    try:
        db.execute(text(sql), params)
        return False, ""
    except Exception as error:  # noqa: BLE001
        return True, str(error).splitlines()[0]
    finally:
        db.rollback()


def table_fingerprints(db):
    return {t: db.execute(text(f'SELECT count(*), md5(coalesce(string_agg(x::text, \',\' ORDER BY x::text), \'\')) '
                               f'FROM "{t}" x')).one() for t in WRITE_TABLES}


# ============================================================
# TRIGGERS (S6-2)
# ============================================================

def test_the_database_refuses_changes_to_final_standards_and_basis_rows(client, db, planning_pg):
    k = planning_pg
    final = approved_standard(client, k)
    draft = ok(client.post(STANDARDS, json=standard_body(k, "chicken", "200")), 201)
    cancelled = ok(client.post(STANDARDS, json=standard_body(k, "chicken", "210")), 201)
    ok(client.post(f"{STANDARDS}/{cancelled['id']}/cancel", json={"reason": "Duplicate"}))

    for sql, standard_id, message in (
        ("UPDATE portion_standards SET quantity_per_person = 1 WHERE id = :id", final["id"], "cannot be changed"),
        ("UPDATE portion_standards SET status = 'DRAFT', approved_at = NULL, approved_by = NULL, version_no = NULL, "
         "item_kind = NULL WHERE id = :id", final["id"], "cannot be changed"),
        ("DELETE FROM portion_standards WHERE id = :id", final["id"], "never deleted"),
        ("UPDATE portion_standards SET notes = 'x' WHERE id = :id", cancelled["id"], "cannot be changed"),
        ("DELETE FROM portion_standards WHERE id = :id", draft["id"], "never deleted"),
    ):
        was_refused, error = refused(db, sql, id=standard_id)
        assert was_refused and message in error, (sql, error)
    basis = ("INSERT INTO portion_standard_basis (campus_id, standard_id, meal_record_id, quantity_used, unit_id, "
             "people_served) VALUES (:c, :id, 1, 1, :u, 1)")
    was_refused, error = refused(db, basis, c=k["campus_id"], id=final["id"], u=k["kg"])
    assert was_refused and "only to a draft standard" in error
    assert not refused(db, "UPDATE portion_standards SET notes = 'ok' WHERE id = :id", id=draft["id"])[0]
    trigger_names = {r[0] for r in db.execute(text(
        "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal AND tgenabled = 'O' AND tgrelid IN "
        "('portion_standards'::regclass, 'portion_standard_basis'::regclass, 'meal_plans'::regclass, "
        "'meal_plan_lines'::regclass)"))}
    assert trigger_names == {"portion_standards_final", "portion_standard_basis_final", "meal_plans_final",
                             "meal_plan_lines_final"}


def test_the_database_keeps_approved_plans_and_their_lines_frozen(client, db, planning_pg):
    k = planning_pg
    approved_standard(client, k)
    approved_standard(client, k, "chicken", "200")
    plan = ok(client.post(f"{PLANS}/{ok(client.post(PLANS, json=plan_body(k)), 201)['id']}/approve"))
    draft = ok(client.post(PLANS, json=plan_body(k, day=today(1))), 201)
    line = plan["lines"][0]["id"]
    for sql, params, message in (
        ("UPDATE meal_plans SET expected_headcount = 1 WHERE id = :id", {"id": plan["id"]}, "approved plan"),
        ("UPDATE meal_plans SET status = 'CANCELLED', cancelled_at = now(), cancelled_by = :u, cancellation_reason = 'x', "
         "expected_headcount = 2 WHERE id = :id", {"id": plan["id"], "u": k["admin"].id}, "approved plan"),
        ("UPDATE meal_plans SET status = 'DRAFT', approved_at = NULL, approved_by = NULL WHERE id = :id",
         {"id": plan["id"]}, "approved plan"),
        ("DELETE FROM meal_plans WHERE id = :id", {"id": plan["id"]}, "never deleted"),
        ("UPDATE meal_plan_lines SET required_base_quantity = 1 WHERE id = :id", {"id": line}, "draft"),
        ("DELETE FROM meal_plan_lines WHERE id = :id", {"id": line}, "draft"),
        ("INSERT INTO meal_plan_lines (campus_id, plan_id, item_id) VALUES (:c, :id, :item)",
         {"c": k["campus_id"], "id": plan["id"], "item": k["chicken"]}, "draft"),
        ("UPDATE meal_plans SET status = 'APPROVED', approved_at = now(), approved_by = :u WHERE id = :id",
         {"id": draft["id"], "u": k["admin"].id}, "snapshot"),
    ):
        was_refused, error = refused(db, sql, **params)
        assert was_refused and message in error, (sql, error)
    # Cancelling (cancellation fields only) is the one change allowed.
    db.execute(text("UPDATE meal_plans SET status = 'CANCELLED', cancelled_at = now(), cancelled_by = :u, "
                    "cancellation_reason = 'Direct' WHERE id = :id"), {"id": plan["id"], "u": k["admin"].id})
    db.commit()
    was_refused, error = refused(db, "UPDATE meal_plans SET notes = 'x' WHERE id = :id", id=plan["id"])
    assert was_refused and "cancelled plan" in error


def test_check_constraints_and_the_one_live_plan_index(client, db, planning_pg):
    k = planning_pg
    approved_standard(client, k)
    plan = ok(client.post(PLANS, json=plan_body(k)), 201)
    cases = (
        ("UPDATE items SET item_kind = 'SNACK' WHERE id = :rice", "ck_item_kind"),
        ("INSERT INTO portion_standards (campus_id, menu_id, item_id, quantity_per_person, unit_id, effective_from, "
         "status, source, created_by, created_at) VALUES (:c, :menu, :rice, 1, :kg, current_date, 'APPROVED', 'MANUAL', "
         ":u, now())", "ck_portion_standard_approved"),
        ("INSERT INTO portion_standards (campus_id, menu_id, item_id, quantity_per_person, unit_id, effective_from, "
         "status, source, created_by, created_at) VALUES (:c, :menu, :rice, 1, :kg, current_date, 'DRAFT', 'COPIED', "
         ":u, now())", "ck_portion_standard_copied"),
        ("INSERT INTO portion_standards (campus_id, menu_id, item_id, quantity_per_person, unit_id, effective_from, "
         "status, source, created_by, created_at) VALUES (:c, :menu, :rice, 0, :kg, current_date, 'DRAFT', 'MANUAL', "
         ":u, now())", "ck_portion_standard_quantity"),
        ("INSERT INTO meal_plan_lines (campus_id, plan_id, item_id, override_quantity_per_person, override_unit_id) "
         "VALUES (:c, :plan, :chicken, 1, :kg)", "ck_meal_plan_line_override"),
        ("INSERT INTO meal_plan_lines (campus_id, plan_id, item_id, required_base_quantity) "
         "VALUES (:c, :plan, :chicken, 1)", "ck_meal_plan_line_snapshot"),
        ("INSERT INTO meal_plans (campus_id, plan_seq, plan_number, plan_date, meal_session_id, menu_id, "
         "expected_headcount, status, created_by, created_at) VALUES (:c, 99, 'MP-00099', current_date, :lunch, :menu, "
         "10, 'DRAFT', :u, now())", "uq_meal_plan_session_date"),
        ("UPDATE meal_plans SET expected_headcount = 0 WHERE id = :plan", "ck_meal_plan_headcount"),
    )
    params = dict(c=k["campus_id"], menu=k["biryani"], rice=k["rice"], chicken=k["chicken"], kg=k["kg"],
                  u=k["admin"].id, plan=plan["id"], lunch=k["lunch"])
    for sql, constraint in cases:
        was_refused, error = refused(db, sql, **params)
        assert was_refused and constraint in error, (constraint, error)


# ============================================================
# RACES
# ============================================================

def test_two_plans_for_one_slot_at_once_keep_one(client, db, planning_pg, parallel_clients):
    approved_standard(client, planning_pg)
    outcomes = race_all(parallel_clients, [lambda c: c.post(PLANS, json=plan_body(planning_pg))] * 4)

    assert sorted(outcomes) == [201, 409, 409, 409], outcomes
    db.expire_all()
    assert db.query(MealPlan).filter(MealPlan.status != "CANCELLED").count() == 1


def test_approving_one_standard_four_times_at_once_approves_it_once(client, db, planning_pg, parallel_clients):
    draft = ok(client.post(STANDARDS, json=standard_body(planning_pg)), 201)

    outcomes = race_all(parallel_clients, [lambda c: c.post(f"{STANDARDS}/{draft['id']}/approve")] * 4)

    assert sorted(outcomes) == [200, 409, 409, 409], outcomes
    approvals = db.execute(text("SELECT count(*) FROM audit_logs WHERE entity_type = 'PORTION_STANDARD' "
                                "AND entity_id = :id AND action = 'APPROVE'"), {"id": draft["id"]}).scalar()
    assert approvals == 1


def test_approving_four_versions_at_once_gives_distinct_version_numbers(client, db, planning_pg, parallel_clients):
    drafts = [ok(client.post(STANDARDS, json=standard_body(planning_pg, qty=str(150 + i))), 201) for i in range(4)]

    outcomes = race_all(parallel_clients, [
        (lambda d: lambda c: c.post(f"{STANDARDS}/{d['id']}/approve"))(d) for d in drafts])

    assert outcomes == [200] * 4, outcomes
    db.expire_all()
    versions = sorted(s.version_no for s in db.query(PortionStandard).filter_by(status="APPROVED"))
    assert versions == [1, 2, 3, 4]


def test_approve_racing_cancel_leaves_one_consistent_plan(client, db, planning_pg, parallel_clients):
    approved_standard(client, planning_pg)
    for round_number in range(4):
        plan = ok(client.post(PLANS, json=plan_body(planning_pg, day=today(round_number + 1))), 201)
        outcomes = race_all(parallel_clients, [
            lambda c: c.post(f"{PLANS}/{plan['id']}/approve"),
            lambda c: c.post(f"{PLANS}/{plan['id']}/cancel", json={"reason": "Changed menu"}),
        ])
        db.expire_all()
        final = db.get(MealPlan, plan["id"])
        snapshots = db.query(MealPlanLine).filter(MealPlanLine.plan_id == plan["id"],
                                                  MealPlanLine.required_base_quantity.isnot(None)).count()
        assert outcomes[1] == 200, (round_number, outcomes)  # a draft or an approved plan can be cancelled
        assert final.status == "CANCELLED", round_number
        assert (outcomes[0], snapshots) in {(200, 1), (409, 0)}, (round_number, outcomes, snapshots)


def test_copying_a_menu_twice_at_once_creates_each_draft_once(client, db, planning_pg, parallel_clients):
    k = planning_pg
    db.add_all([MenuMainItem(campus_id=k["campus_id"], menu_id=k["biryani"], item_id=k["rice"],
                             quantity_per_person=Decimal("0.150"), unit_id=k["kg"]),
                MenuMainItem(campus_id=k["campus_id"], menu_id=k["biryani"], item_id=k["chicken"],
                             quantity_per_person=Decimal("200"), unit_id=k["g"])])
    db.commit()

    outcomes = race_all(parallel_clients, [lambda c: c.post(f"{STANDARDS}/copy-from-menu", json={
        "menu_id": k["biryani"], "effective_from": today()})] * 4)

    assert outcomes == [200] * 4, outcomes
    db.expire_all()
    assert db.query(PortionStandard).filter_by(source="COPIED", status="DRAFT").count() == 2
    assert db.query(PortionStandard).filter_by(status="APPROVED").count() == 0


# ============================================================
# S6-5 AND 6-8 ON POSTGRESQL
# ============================================================

def test_no_stock_purchasing_or_supplier_row_is_written_by_planning(client, db, planning_pg):
    k = planning_pg
    before = table_fingerprints(db)
    approved_standard(client, k)
    approved_standard(client, k, "chicken", "200")
    plan = ok(client.post(PLANS, json=plan_body(k, items=("rice", "chicken"))), 201)
    ok(client.put(f"{PLANS}/{plan['id']}", json={"expected_headcount": 500, "lines": [{"item_id": k["rice"]}]}))
    ok(client.post(f"{PLANS}/{plan['id']}/approve"))
    ok(client.get(f"{PLANS}/{plan['id']}/comparison"))
    ok(client.post(f"{PLANS}/{plan['id']}/cancel", json={"reason": "Replaced"}))
    ok(client.post(PLANS, json=plan_body(k)), 201)
    db.expire_all()
    assert table_fingerprints(db) == before


def test_staff_inventory_update_grant_never_classifies_an_item(client, db, planning_pg):
    k = planning_pg
    staff = create_test_user(db, k["campus_id"], "STAFF")
    for code in ("inventory.read", "inventory.update"):
        permission = db.query(Permission).filter_by(permission_code=code).one()
        db.add(StaffAccessAssignment(staff_user_id=staff.id, permission_id=permission.id,
                                     assigned_by=k["admin"].id, is_active=True))
    db.commit()
    act_as(client, staff)
    assert client.put(f"/api/items/{k['rice']}/kind", json={"item_kind": "PREPARED"}).status_code == 403
    act_as(client, k["manager"])
    assert ok(client.put(f"/api/items/{k['rice']}/kind", json={"item_kind": "PREPARED"}))["item_kind"] == "PREPARED"
    db.expire_all()
    assert db.get(Item, k["rice"]).item_kind == "PREPARED"
