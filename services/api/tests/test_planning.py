"""
Stage 6: meal planning (PLAN01–PLAN08, AT05, AT06), per
docs/STAGE-6-PLANNING-PLAN.md (decisions 6-1 to 6-9, safeguards S6-1 to
S6-6 and the section 12 choices, approved 24 November 2026).

Interim rules tested here are not client decisions: Admins and Kitchen
Managers create and approve, self-approval allowed (Q3, matrix gap);
effective-dated versions plus one-day overrides (client questions §5.3);
explicit conversions only (Q7/Q8); item kind set by Admins and Kitchen
Managers only (Q2); same-named meal sessions reported, never linked (C5);
cancel-and-replace for approved plans (proposal §4.2).

In-memory SQLite with the shared fixtures of test_operational_authority and
the kitchen fixture of test_kitchen_issues (campus A: kg and g with an
explicit g→kg conversion; Rice with 20 kg opening stock, Toor Dal; Lunch with
Veg Biryani, Dinner with Dal Fry). tests/test_planning_postgres.py covers the
PostgreSQL triggers and races.
"""

import importlib.util
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from app.core.clock import campus_today
from app.models import AuditLog, Item, MealSession, Menu, MenuMainItem, Permission, Unit, UnitConversion
from app.models.planning import MealPlan, MealPlanLine, PortionStandard, PortionStandardBasis
from app.models.purchases import (
    GoodsReceipt, GoodsReceiptItem, Purchase, PurchaseItem, PurchaseOrder, PurchaseOrderItem, StockMovement,
    SupplierPayment, SupplierReturn, SupplierReturnItem,
)
from app.models.stock import (
    KitchenIssue, KitchenIssueItem, KitchenReturn, KitchenReturnItem, StockAdjustment, StockCount, StockCountItem,
    StockOpening,
)
from app.models.waste import WasteItem, WasteRecord

from tests.test_kitchen_issues import (  # noqa: F401 (fixtures)
    days_ago,
    issued_and_confirmed,
    kitchen,
)
from tests.test_meals import add_dish, create as create_meal, dish_named, distribute, ok, set_counts
from tests.test_operational_authority import (  # noqa: F401 (fixtures)
    act_as,
    client,
    db,
    grant,
    world,
)

STANDARDS = "/api/portion-standards"
PLANS = "/api/meal-plans"
MEALS = "/api/meal-records"
API_DIR = Path(__file__).resolve().parents[1]

WRITE_MODELS = (
    StockMovement, StockOpening, KitchenIssue, KitchenIssueItem, KitchenReturn, KitchenReturnItem, StockCount,
    StockCountItem, StockAdjustment, Purchase, PurchaseItem, PurchaseOrder, PurchaseOrderItem, GoodsReceipt,
    GoodsReceiptItem, SupplierPayment, SupplierReturn, SupplierReturnItem, WasteRecord, WasteItem,
)


def today(offset=0):
    return (campus_today() + timedelta(days=offset)).isoformat()


@pytest.fixture
def plan_world(db, kitchen):
    """Adds to campus A: pc (count) and lb (weight, no conversion); Chicken
    (kg), Egg (pc) and Paneer (kg); two meal sessions named "Breakfast" and
    "  breakfast " with a menu each. Rice, Chicken and Egg are RAW; Toor Dal
    and Paneer are not classified."""
    a = kitchen.a
    pc = Unit(campus_id=a.campus.id, name="Piece", symbol="pc", dimension="count")
    lb = Unit(campus_id=a.campus.id, name="Pound", symbol="lb", dimension="weight")
    db.add_all([pc, lb])
    db.flush()
    chicken = Item(campus_id=a.campus.id, name="Chicken", category_id=a.category.id, standard_unit_id=a.kg.id,
                   minimum_stock=0, item_kind="RAW")
    egg = Item(campus_id=a.campus.id, name="Egg", category_id=a.category.id, standard_unit_id=pc.id,
               minimum_stock=0, item_kind="RAW")
    paneer = Item(campus_id=a.campus.id, name="Paneer", category_id=a.category.id, standard_unit_id=a.kg.id,
                  minimum_stock=0)
    breakfast = MealSession(campus_id=a.campus.id, name="Breakfast")
    breakfast_dup = MealSession(campus_id=a.campus.id, name="  breakfast ")
    db.add_all([chicken, egg, paneer, breakfast, breakfast_dup])
    db.flush()
    idli = Menu(campus_id=a.campus.id, name="Idli", meal_session_id=breakfast.id)
    upma = Menu(campus_id=a.campus.id, name="Upma", meal_session_id=breakfast_dup.id)
    db.add_all([idli, upma])
    a.item.item_kind = "RAW"
    db.commit()
    a.pc, a.lb, a.chicken, a.egg, a.paneer = pc, lb, chicken, egg, paneer
    a.breakfast, a.breakfast_dup, a.idli, a.upma = breakfast, breakfast_dup, idli, upma
    return kitchen


def new_standard(client, item, qty, unit, menu, effective=None, notes=None):
    return client.post(STANDARDS, json={"menu_id": menu.id, "item_id": item.id, "quantity_per_person": qty,
                                        "unit_id": unit.id, "effective_from": effective or today(), "notes": notes})


def approved(client, item, qty, unit, menu, effective=None):
    draft = ok(new_standard(client, item, qty, unit, menu, effective), 201)
    return ok(client.post(f"{STANDARDS}/{draft['id']}/approve"))


def new_plan(client, a, lines, headcount=450, day=None, session=None, menu=None, notes=None):
    return client.post(PLANS, json={
        "plan_date": day or today(), "meal_session_id": (session or a.lunch).id, "menu_id": (menu or a.biryani).id,
        "expected_headcount": headcount, "notes": notes,
        "lines": [line if isinstance(line, dict) else {"item_id": line.id} for line in lines],
    })


def line_of(plan, item):
    return next(l for l in plan["lines"] if l["item_id"] == item.id)


def biryani_standards(client, a):
    """AT05: rice 150 g and chicken 200 g per person for Veg Biryani."""
    approved(client, a.item, "150", a.g, a.biryani)
    approved(client, a.chicken, "200", a.g, a.biryani)


def fingerprint(db):
    db.expire_all()
    return {m.__tablename__: sorted(repr(sorted((k, str(v)) for k, v in vars(r).items() if not k.startswith("_")))
                                    for r in db.query(m).all()) for m in WRITE_MODELS}


# ============================================================
# ITEM KIND (6-8): ADMIN AND KITCHEN_MANAGER ONLY
# ============================================================

def test_item_kind_is_set_only_by_admin_and_manager_and_audited(client, db, plan_world):
    a = plan_world.a
    act_as(client, a.manager)
    result = ok(client.put(f"/api/items/{a.dal.id}/kind", json={"item_kind": "RAW"}))
    assert result["item_kind"] == "RAW"
    act_as(client, a.admin)
    assert ok(client.put(f"/api/items/{a.paneer.id}/kind", json={"item_kind": "PREPARED"}))["item_kind"] == "PREPARED"
    assert ok(client.put(f"/api/items/{a.paneer.id}/kind", json={"item_kind": "OUTSOURCED"}))["item_kind"] == "OUTSOURCED"
    audits = db.query(AuditLog).filter_by(entity_type="ITEM", action="SET_KIND").order_by(AuditLog.id).all()
    assert [(r.details["before"]["item_kind"], r.details["after"]["item_kind"]) for r in audits] == [
        (None, "RAW"), (None, "PREPARED"), ("PREPARED", "OUTSOURCED")]
    # Can change, cannot be cleared; other campus 404.
    assert client.put(f"/api/items/{a.paneer.id}/kind", json={"item_kind": None}).status_code == 422
    assert client.put(f"/api/items/{a.paneer.id}/kind", json={"item_kind": "SNACK"}).status_code == 422
    assert client.put(f"/api/items/{plan_world.b.item.id}/kind", json={"item_kind": "RAW"}).status_code == 404
    listed = {i["name"]: i["item_kind"] for i in client.get("/api/master/items?page_size=100").json()["items"]}
    assert listed["Toor Dal"] == "RAW" and listed["Paneer"] == "OUTSOURCED"


def test_item_kind_cannot_be_set_through_staff_inventory_grants_or_the_item_forms(client, db, plan_world):
    a = plan_world.a
    for code in ("inventory.read", "inventory.create", "inventory.update", "menu.create", "menu.update"):
        grant(db, a.staff, a.admin, code)  # like the older grants STAFF #3 holds
    act_as(client, a.staff)
    refused = client.put(f"/api/items/{a.dal.id}/kind", json={"item_kind": "RAW"})
    assert refused.status_code == 403
    item_body = {"name": "Toor Dal", "category_id": a.category.id, "standard_unit_id": a.kg.id, "minimum_stock": "0"}
    via_form = client.put(f"/api/master/items/{a.dal.id}", json={**item_body, "item_kind": "RAW"})
    assert via_form.status_code == 422 and "classification action" in via_form.text
    created = client.post("/api/master/items", json={**item_body, "name": "Moong Dal", "item_kind": "PREPARED"})
    assert created.status_code == 422
    # Existing item edits through older grants still work, without the kind.
    edited = client.put(f"/api/master/items/{a.dal.id}", json={**item_body, "minimum_stock": "5"})
    assert edited.status_code == 200, edited.text
    db.expire_all()
    assert db.get(Item, a.dal.id).item_kind is None
    act_as(client, a.admin)
    assert client.put(f"/api/master/items/{a.dal.id}", json={**item_body, "item_kind": "RAW"}).status_code == 422
    assert db.query(AuditLog).filter_by(action="SET_KIND").count() == 0


# ============================================================
# PORTION STANDARDS (PLAN02, PLAN06, S6-2, S6-3, S6-4)
# ============================================================

def test_plan02_standards_per_menu_and_item_by_weight_or_count_and_kind(client, plan_world):
    a = plan_world.a
    act_as(client, a.manager)
    rice_biryani = approved(client, a.item, "150", a.g, a.biryani)
    rice_dal_fry = approved(client, a.item, "0.12", a.kg, a.dal_fry)
    egg = approved(client, a.egg, "1", a.pc, a.biryani)

    assert (rice_biryani["quantity_per_person"], rice_biryani["unit_symbol"], rice_biryani["item_kind"]) == ("150.000", "g", "RAW")
    assert (rice_dal_fry["quantity_per_person"], rice_dal_fry["unit_symbol"]) == ("0.120", "kg")
    assert (egg["unit_symbol"], egg["version_no"], egg["state"], egg["status"]) == ("pc", 1, "IN_EFFECT", "APPROVED")
    assert rice_biryani["approved_by_name"] == "KITCHEN_MANAGER A"  # own draft (interim, Q3)
    listed = client.get(f"{STANDARDS}?menu_id={a.biryani.id}").json()
    assert {(r["item_name"], r["state"]) for r in listed["items"]} == {("Rice", "IN_EFFECT"), ("Egg", "IN_EFFECT")}


def test_s6_3_standard_units_need_an_explicit_conversion(client, plan_world):
    a = plan_world.a
    act_as(client, a.manager)
    no_record = new_standard(client, a.item, "0.3", a.lb, a.biryani)
    assert no_record.status_code == 422 and "no approved conversion between lb and kg" in no_record.json()["detail"]
    pieces = new_standard(client, a.item, "2", a.pc, a.biryani)
    assert pieces.status_code == 422 and "never assumed" in pieces.json()["detail"]
    grams_of_egg = new_standard(client, a.egg, "50", a.g, a.biryani)
    assert grams_of_egg.status_code == 422 and "never assumed" in grams_of_egg.json()["detail"]
    options = client.get(f"{STANDARDS}/options").json()
    rice = next(i for i in options["items"] if i["name"] == "Rice")
    assert {u["symbol"] for u in rice["unit_choices"]} == {"kg", "g"}


def test_approval_needs_a_classified_plannable_item_and_the_role(client, db, plan_world):
    a = plan_world.a
    act_as(client, a.manager)
    draft = ok(new_standard(client, a.dal, "80", a.g, a.dal_fry), 201)
    assert any("Classify Toor Dal" in p for p in draft["approval_problems"])
    refused = client.post(f"{STANDARDS}/{draft['id']}/approve")
    assert refused.status_code == 422 and "Classify Toor Dal as raw or prepared" in refused.json()["detail"]
    ok(client.put(f"/api/items/{a.dal.id}/kind", json={"item_kind": "RAW"}))
    act_as(client, a.admin)
    done = ok(client.post(f"{STANDARDS}/{draft['id']}/approve"))
    assert (done["status"], done["item_kind"], done["approved_by_name"]) == ("APPROVED", "RAW", "ADMIN A")
    # Outsourced items are not planned (6-8).
    ok(client.put(f"/api/items/{a.paneer.id}/kind", json={"item_kind": "OUTSOURCED"}))
    outsourced = new_standard(client, a.paneer, "50", a.g, a.biryani)
    assert outsourced.status_code == 422 and "not planned until the outsourced-food stage" in outsourced.json()["detail"]


def test_s6_2_an_approved_standard_never_changes_and_a_newer_version_replaces_it(client, db, plan_world):
    a = plan_world.a
    act_as(client, a.manager)
    first = approved(client, a.item, "150", a.g, a.biryani)
    body = {"quantity_per_person": "160", "unit_id": a.g.id, "effective_from": today()}
    assert client.put(f"{STANDARDS}/{first['id']}", json=body).status_code == 409
    assert client.post(f"{STANDARDS}/{first['id']}/cancel", json={"reason": "Typo"}).status_code == 409
    assert client.post(f"{STANDARDS}/{first['id']}/approve").status_code == 409
    # Same effective date: the later approved (higher) version wins (choice 1).
    second = approved(client, a.item, "160", a.g, a.biryani)
    later = approved(client, a.item, "170", a.g, a.biryani, effective=today(3))
    detail = client.get(f"{STANDARDS}/{first['id']}").json()
    states = {v["version_no"]: v["state"] for v in detail["versions"]}
    assert states == {1: "SUPERSEDED", 2: "IN_EFFECT", 3: "SCHEDULED"}
    assert (second["version_no"], later["version_no"]) == (2, 3)
    db.expire_all()
    assert db.get(PortionStandard, first["id"]).quantity_per_person == Decimal("150.000")


def test_s6_2_the_database_refuses_changes_to_final_standards(client, db, plan_world):
    a = plan_world.a
    act_as(client, a.manager)
    final = approved(client, a.item, "150", a.g, a.biryani)
    draft = ok(new_standard(client, a.chicken, "200", a.g, a.biryani), 201)
    for statement in ("UPDATE portion_standards SET quantity_per_person = 1 WHERE id = :id",
                      "UPDATE portion_standards SET status = 'DRAFT' WHERE id = :id",
                      "DELETE FROM portion_standards WHERE id = :id"):
        with pytest.raises(Exception, match="portion_standards"):
            db.execute(text(statement), {"id": final["id"]})
        db.rollback()
    with pytest.raises(Exception, match="never deleted"):
        db.execute(text("DELETE FROM portion_standards WHERE id = :id"), {"id": draft["id"]})
    db.rollback()
    db.execute(text("UPDATE portion_standards SET notes = 'ok' WHERE id = :id"), {"id": draft["id"]})  # a draft may change
    db.rollback()


def test_effective_dates_are_today_or_later_and_drafts_can_be_edited_and_cancelled(client, db, plan_world):
    a = plan_world.a
    act_as(client, a.manager)
    back = new_standard(client, a.item, "150", a.g, a.biryani, effective=today(-1))
    assert back.status_code == 422 and "not back-dated" in back.json()["detail"]
    draft = ok(new_standard(client, a.item, "150", a.g, a.biryani, effective=today(2)), 201)
    edited = ok(client.put(f"{STANDARDS}/{draft['id']}", json={
        "quantity_per_person": "0.155", "unit_id": a.kg.id, "effective_from": today(1), "notes": "Rounded"}))
    assert (edited["quantity_per_person"], edited["unit_symbol"], edited["effective_from"]) == ("0.155", "kg", today(1))
    cancelled = ok(client.post(f"{STANDARDS}/{draft['id']}/cancel", json={"reason": "Not needed"}))
    assert (cancelled["status"], cancelled["cancellation_reason"]) == ("CANCELLED", "Not needed")
    assert client.put(f"{STANDARDS}/{draft['id']}", json={
        "quantity_per_person": "1", "unit_id": a.kg.id, "effective_from": today()}).status_code == 409
    # A draft whose date has passed cannot be approved (no back-dating).
    stale = ok(new_standard(client, a.chicken, "200", a.g, a.biryani), 201)
    db.query(PortionStandard).filter_by(id=stale["id"]).update({"effective_from": campus_today() - timedelta(days=1)})
    db.commit()
    refused = client.post(f"{STANDARDS}/{stale['id']}/approve")
    assert refused.status_code == 422 and "not back-dated" in refused.json()["detail"]
    actions = [r.action for r in db.query(AuditLog).filter_by(entity_type="PORTION_STANDARD", entity_id=draft["id"])
               .order_by(AuditLog.id)]
    assert actions == ["CREATE", "UPDATE", "CANCEL"]


def test_s6_4_copying_menu_main_items_creates_drafts_only(client, db, plan_world):
    a = plan_world.a
    db.add_all([
        MenuMainItem(campus_id=a.campus.id, menu_id=a.biryani.id, item_id=a.item.id, quantity_per_person=Decimal("0.150"), unit_id=a.kg.id),
        MenuMainItem(campus_id=a.campus.id, menu_id=a.biryani.id, item_id=a.chicken.id, quantity_per_person=Decimal("200"), unit_id=a.g.id),
        MenuMainItem(campus_id=a.campus.id, menu_id=a.biryani.id, item_id=a.paneer.id, quantity_per_person=Decimal("50"), unit_id=a.g.id),
    ])
    a.paneer.item_kind = "OUTSOURCED"
    db.commit()
    before = sorted((m.id, m.item_id, str(m.quantity_per_person), m.unit_id) for m in db.query(MenuMainItem))
    act_as(client, a.manager)

    copied = ok(client.post(f"{STANDARDS}/copy-from-menu", json={"menu_id": a.biryani.id, "effective_from": today()}))

    assert [c["item_name"] for c in copied["created"]] == ["Rice", "Chicken"]
    assert [s["item_name"] for s in copied["skipped"]] == ["Paneer"] and "outsourced" in copied["skipped"][0]["reason"]
    rows = db.query(PortionStandard).all()
    assert {(r.status, r.source, r.version_no, r.approved_by) for r in rows} == {("DRAFT", "COPIED", None, None)}
    again = ok(client.post(f"{STANDARDS}/copy-from-menu", json={"menu_id": a.biryani.id, "effective_from": today()}))
    assert again["created"] == [] and all("draft copy already exists" in s["reason"] for s in again["skipped"][:2])
    assert sorted((m.id, m.item_id, str(m.quantity_per_person), m.unit_id) for m in db.query(MenuMainItem)) == before
    # A plan cannot use a draft standard.
    prefill = client.get(f"{PLANS}/prefill", params={"plan_date": today(), "meal_session_id": a.lunch.id,
                                                       "menu_id": a.biryani.id}).json()
    assert prefill["items"] == [] and {u["reason"] for u in prefill["unavailable_items"]} == {
        "Only a draft standard exists (needs approval)."}
    refused = new_plan(client, a, [a.item])
    assert refused.status_code == 422 and "no approved standard" in refused.json()["detail"]
    # Each copy is approved on its own.
    ok(client.post(f"{STANDARDS}/{rows[0].id}/approve"))
    assert db.query(PortionStandard).filter_by(status="APPROVED").count() == 1


# ============================================================
# PLANS: AT05, PLAN01, PLAN04, PLAN05, PLAN06, PLAN07
# ============================================================

def test_at05_biryani_for_450_people_and_recalculation_without_stock_movement(client, db, plan_world):
    a = plan_world.a
    act_as(client, a.manager)
    biryani_standards(client, a)
    before = fingerprint(db)

    plan = ok(new_plan(client, a, [a.item, a.chicken], headcount=450), 201)

    rice, chicken = line_of(plan, a.item), line_of(plan, a.chicken)
    assert (rice["required_quantity"], rice["unit_symbol"], rice["required_display"][0]["quantity"],
            rice["required_display"][0]["unit_symbol"]) == ("67500.000", "g", "67.500", "kg")
    assert (rice["required_base_quantity"], chicken["required_base_quantity"]) == ("67.500", "90.000")
    assert plan["calculation"] == "LIVE" and plan["status"] == "DRAFT" and plan["plan_number"] == "MP-00001"
    changed = ok(client.put(f"{PLANS}/{plan['id']}", json={
        "expected_headcount": 500, "lines": [{"item_id": a.item.id}, {"item_id": a.chicken.id}]}))
    assert (line_of(changed, a.item)["required_base_quantity"], line_of(changed, a.chicken)["required_base_quantity"]) == (
        "75.000", "100.000")
    ok(client.post(f"{PLANS}/{plan['id']}/approve"))
    assert fingerprint(db) == before  # no stock, purchasing or supplier row (PLAN07, S6-5)


def test_plan01_only_selected_main_items_and_plan05_gap_is_current_availability(client, plan_world):
    a = plan_world.a
    act_as(client, a.manager)
    biryani_standards(client, a)
    plan = ok(new_plan(client, a, [a.item], headcount=450), 201)
    assert [l["item_name"] for l in plan["lines"]] == ["Rice"]  # chicken not compulsory
    rice = line_of(plan, a.item)
    assert (rice["available_stock"], rice["procurement_gap"]) == ("20.000", "47.500")
    assert plan["availability_note"].startswith("Current availability")
    ok(client.put(f"{PLANS}/{plan['id']}", json={"expected_headcount": 100, "lines": [{"item_id": a.item.id}]}))
    rice = line_of(client.get(f"{PLANS}/{plan['id']}").json(), a.item)
    assert (rice["required_base_quantity"], rice["procurement_gap"]) == ("15.000", "0.000")  # max(0, 15 − 20)
    for body in ({"lines": []}, {"lines": [{"item_id": a.item.id}, {"item_id": a.item.id}]}):
        assert client.put(f"{PLANS}/{plan['id']}", json={"expected_headcount": 10, **body}).status_code == 422
    assert client.put(f"{PLANS}/{plan['id']}", json={"expected_headcount": 0, "lines": [{"item_id": a.item.id}]}).status_code == 422


def test_plan04_count_items_round_up_and_plan06_one_day_override_with_reason(client, db, plan_world):
    a = plan_world.a
    act_as(client, a.manager)
    approved(client, a.egg, "0.5", a.pc, a.biryani)
    approved(client, a.item, "150", a.g, a.biryani)
    plan = ok(new_plan(client, a, [a.egg, {"item_id": a.item.id, "override_quantity_per_person": "0.2",
                                           "override_unit_id": a.kg.id, "override_reason": "Exam week, larger portions"}],
                       headcount=451), 201)
    egg, rice = line_of(plan, a.egg), line_of(plan, a.item)
    assert (egg["required_quantity"], egg["rounded_up"], egg["unit_symbol"]) == ("226.000", True, "pc")
    assert (rice["quantity_per_person"], rice["unit_symbol"], rice["required_base_quantity"]) == ("0.200", "kg", "90.200")
    assert rice["standard"]["quantity_per_person"] == "150.000" and rice["override"]["reason"] == "Exam week, larger portions"
    # The override applies to this plan only; the standard is unchanged.
    other = ok(new_plan(client, a, [a.item], headcount=451, day=today(1)), 201)
    assert line_of(other, a.item)["required_base_quantity"] == "67.650"
    for bad in ({"override_quantity_per_person": "0.2", "override_unit_id": a.kg.id},
                {"override_quantity_per_person": "0.2", "override_unit_id": a.kg.id, "override_reason": "  "},
                {"override_quantity_per_person": "0.3", "override_unit_id": a.lb.id, "override_reason": "Pounds"},
                {"override_quantity_per_person": "2", "override_unit_id": a.pc.id, "override_reason": "Pieces"}):
        response = client.put(f"{PLANS}/{plan['id']}", json={"expected_headcount": 451,
                                                            "lines": [{"item_id": a.item.id, **bad}]})
        assert response.status_code == 422, bad
    approved_plan = ok(client.post(f"{PLANS}/{plan['id']}/approve"))
    snap = db.query(MealPlanLine).filter_by(plan_id=plan["id"], item_id=a.item.id).one()
    assert (snap.override_reason, str(snap.quantity_per_person), str(snap.standard_quantity_per_person)) == (
        "Exam week, larger portions", "0.200", "150.000")
    assert approved_plan["calculation"] == "SNAPSHOT"


def test_plan_dates_sessions_and_one_live_plan_per_slot(client, db, plan_world):
    a = plan_world.a
    act_as(client, a.manager)
    approved(client, a.item, "150", a.g, a.biryani)
    past = new_plan(client, a, [a.item], day=today(-1))
    assert past.status_code == 422 and "today or a later date" in past.json()["detail"]
    wrong_menu = new_plan(client, a, [a.item], session=a.dinner)
    assert wrong_menu.status_code == 422 and "another meal session" in wrong_menu.json()["detail"]
    assert new_plan(client, a, [a.item], session=a.old_session).status_code == 422
    first = ok(new_plan(client, a, [a.item]), 201)
    again = new_plan(client, a, [a.item])
    assert again.status_code == 409 and first["plan_number"] in again.json()["detail"]
    future = ok(new_plan(client, a, [a.item], day=today(30)), 201)
    assert future["plan_number"] == "MP-00002"
    # A draft dated in the past can only be cancelled (choice 6).
    db.query(MealPlan).filter_by(id=future["id"]).update({"plan_date": campus_today() - timedelta(days=2)})
    db.commit()
    stale = client.get(f"{PLANS}/{future['id']}").json()
    assert not stale["editable"] and any("past-dated draft" in p for p in stale["approval_problems"])
    assert client.put(f"{PLANS}/{future['id']}", json={"expected_headcount": 5, "lines": [{"item_id": a.item.id}]}).status_code == 409
    assert client.post(f"{PLANS}/{future['id']}/approve").status_code == 409
    assert ok(client.post(f"{PLANS}/{future['id']}/cancel", json={"reason": "Too late"}))["status"] == "CANCELLED"


# ============================================================
# AT06, S6-2: APPROVED PLANS ARE FROZEN
# ============================================================

def test_at06_new_plans_use_the_new_standard_and_approved_plans_keep_theirs(client, db, plan_world):
    a = plan_world.a
    act_as(client, a.manager)
    approved(client, a.item, "150", a.g, a.biryani)
    old = ok(client.post(f"{PLANS}/{ok(new_plan(client, a, [a.item]), 201)['id']}/approve"))
    draft_tomorrow = ok(new_plan(client, a, [a.item], day=today(1)), 201)
    assert line_of(draft_tomorrow, a.item)["required_base_quantity"] == "67.500"

    newer = approved(client, a.item, "180", a.g, a.biryani)  # same date, higher version

    kept = client.get(f"{PLANS}/{old['id']}").json()
    assert (line_of(kept, a.item)["quantity_per_person"], line_of(kept, a.item)["required_base_quantity"],
            line_of(kept, a.item)["standard"]["version_no"]) == ("150.000", "67.500", 1)
    follows = client.get(f"{PLANS}/{draft_tomorrow['id']}").json()  # a draft recalculates (6-6)
    assert (line_of(follows, a.item)["required_base_quantity"], line_of(follows, a.item)["standard"]["version_no"]) == (
        "81.000", newer["version_no"])
    fresh = ok(new_plan(client, a, [a.item], day=today(2)), 201)
    assert line_of(fresh, a.item)["quantity_per_person"] == "180.000"
    trail = [(r.entity_type, r.action) for r in db.query(AuditLog).filter(
        AuditLog.entity_type.in_(["PORTION_STANDARD", "MEAL_PLAN"])).order_by(AuditLog.id)]
    assert trail[:4] == [("PORTION_STANDARD", "CREATE"), ("PORTION_STANDARD", "APPROVE"),
                         ("MEAL_PLAN", "CREATE"), ("MEAL_PLAN", "APPROVE")]
    assert ("PORTION_STANDARD", "APPROVE") in trail[4:]
    approval = db.query(AuditLog).filter_by(entity_type="MEAL_PLAN", entity_id=old["id"], action="APPROVE").one()
    assert approval.details["lines"][0]["required_base_quantity"] == "67.500"


def test_s6_2_an_approved_plan_is_frozen_and_corrected_by_cancel_and_replace(client, db, plan_world):
    a = plan_world.a
    act_as(client, a.manager)
    biryani_standards(client, a)
    plan = ok(client.post(f"{PLANS}/{ok(new_plan(client, a, [a.item]), 201)['id']}/approve"))
    body = {"expected_headcount": 10, "lines": [{"item_id": a.item.id}]}
    assert client.put(f"{PLANS}/{plan['id']}", json=body).status_code == 409
    assert client.post(f"{PLANS}/{plan['id']}/approve").status_code == 409
    assert new_plan(client, a, [a.item]).status_code == 409
    assert client.post(f"{PLANS}/{plan['id']}/cancel", json={"reason": " "}).status_code == 422
    cancelled = ok(client.post(f"{PLANS}/{plan['id']}/cancel", json={"reason": "Headcount changed after approval"}))
    assert (cancelled["status"], cancelled["approved_by_name"], cancelled["calculation"]) == (
        "CANCELLED", "KITCHEN_MANAGER A", "SNAPSHOT")
    assert line_of(cancelled, a.item)["required_base_quantity"] == "67.500"  # kept as history
    assert client.post(f"{PLANS}/{plan['id']}/cancel", json={"reason": "Again"}).status_code == 409
    replacement = ok(new_plan(client, a, [a.item, a.chicken], headcount=480), 201)
    assert replacement["plan_number"] == "MP-00002"


def test_s6_2_the_database_refuses_changes_to_approved_plans_and_their_lines(client, db, plan_world):
    a = plan_world.a
    act_as(client, a.manager)
    approved(client, a.item, "150", a.g, a.biryani)
    plan = ok(client.post(f"{PLANS}/{ok(new_plan(client, a, [a.item]), 201)['id']}/approve"))
    draft = ok(new_plan(client, a, [a.item], day=today(1)), 201)
    line_id = plan["lines"][0]["id"]
    for statement, params, match in (
        ("UPDATE meal_plans SET expected_headcount = 1 WHERE id = :id", {"id": plan["id"]}, "approved plan"),
        ("UPDATE meal_plans SET status = 'DRAFT', approved_at = NULL, approved_by = NULL WHERE id = :id", {"id": plan["id"]}, "approved plan"),
        ("DELETE FROM meal_plans WHERE id = :id", {"id": plan["id"]}, "never deleted"),
        ("UPDATE meal_plan_lines SET required_quantity = 1 WHERE id = :id", {"id": line_id}, "draft"),
        ("DELETE FROM meal_plan_lines WHERE id = :id", {"id": line_id}, "draft"),
        ("INSERT INTO meal_plan_lines (campus_id, plan_id, item_id) VALUES (:c, :id, :item)",
         {"c": a.campus.id, "id": plan["id"], "item": a.chicken.id}, "draft"),
        ("UPDATE meal_plans SET status = 'APPROVED', approved_at = CURRENT_TIMESTAMP, approved_by = 1 WHERE id = :id",
         {"id": draft["id"]}, "snapshot"),  # no line snapshot yet
    ):
        with pytest.raises(Exception, match=match):
            db.execute(text(statement), params)
        db.rollback()
    db.execute(text("UPDATE meal_plans SET status = 'CANCELLED', cancelled_at = CURRENT_TIMESTAMP, cancelled_by = :u, "
                    "cancellation_reason = 'direct' WHERE id = :id"), {"id": plan["id"], "u": a.manager.id})
    db.rollback()  # cancelling is the only change allowed


# ============================================================
# S6-1: AMBIGUOUS MEAL-SESSION MATCHING IS REPORTED, NEVER LINKED
# ============================================================

def test_s6_1_same_named_sessions_are_reported_and_never_linked(client, db, plan_world):
    a = plan_world.a
    act_as(client, a.manager)
    approved(client, a.item, "50", a.g, a.idli)
    other = ok(create_meal(client, a, session=a.breakfast_dup), 201)  # "  breakfast "

    prefill = client.get(f"{PLANS}/prefill", params={"plan_date": today(), "meal_session_id": a.breakfast.id,
                                                       "menu_id": a.idli.id}).json()
    assert prefill["meal_record"] is None  # never pre-filled from the other session
    assert any(f"#{other['id']}" in w and "not linked" in w for w in prefill["session_warnings"])
    plan = ok(new_plan(client, a, [a.item], headcount=200, session=a.breakfast, menu=a.idli), 201)
    assert plan["meal_record"] is None and any(f"#{other['id']}" in w for w in plan["session_warnings"])
    record_side = client.get(f"{MEALS}/{other['id']}").json()["planning"]
    assert record_side["plan"] is None and any(plan["plan_number"] in w for w in record_side["session_warnings"])
    assert new_plan(client, a, [a.item], session=a.breakfast, menu=a.upma).status_code == 422  # menu of the other

    exact = ok(create_meal(client, a, session=a.breakfast, counts=(180, 10, 2)), 201)
    linked = client.get(f"{PLANS}/{plan['id']}").json()
    assert linked["meal_record"]["id"] == exact["id"] and linked["meal_record"]["expected_total"] == 192
    assert any(f"#{other['id']}" in w for w in linked["session_warnings"])
    assert client.get(f"{MEALS}/{exact['id']}").json()["planning"]["plan"]["id"] == plan["id"]
    listed = client.get(PLANS).json()["items"][0]
    assert listed["meal_record_id"] == exact["id"]


# ============================================================
# PLAN03: SUGGESTIONS FROM CLOSED MEAL RECORDS
# ============================================================

def closed_meal(client, a, day, session=None, rice_issue=None):
    if rice_issue:
        issued_and_confirmed(client, a, [(a.item, rice_issue, None)], issue_date=day,
                             session=session or a.lunch, menu=a.biryani if (session or a.lunch) == a.lunch else a.dal_fry)
    record = ok(create_meal(client, a, day=day, session=session), 201)
    record = ok(add_dish(client, record, "Steamed rice", "20", a.kg), 201)
    ok(distribute(client, record, dish_named(record, "Steamed rice"), "18", "2", [("WASTED", "2", "Plate waste")]))
    ok(set_counts(client, record))  # actual 110 + 9 + 4 = 123
    return ok(client.post(f"{MEALS}/{record['id']}/close"))


def test_plan03_suggestion_from_selected_closed_records_saved_as_a_draft(client, db, plan_world):
    a = plan_world.a
    act_as(client, a.manager)
    first = closed_meal(client, a, days_ago(3), rice_issue="6")
    second = closed_meal(client, a, days_ago(2), rice_issue="4")
    no_rice = closed_meal(client, a, days_ago(2), session=a.dinner)
    still_open = ok(create_meal(client, a), 201)
    ids = [first["id"], second["id"], no_rice["id"], still_open["id"]]

    candidates = client.get(f"{STANDARDS}/suggestion/records", params={"item_id": a.item.id}).json()["items"]
    assert [c["id"] for c in candidates] == [second["id"], first["id"]]
    preview = ok(client.post(f"{STANDARDS}/suggestion/preview", json={
        "menu_id": a.biryani.id, "item_id": a.item.id, "meal_record_ids": ids, "unit_id": a.g.id}))

    assert (preview["total_quantity_used"], preview["total_people_served"], preview["included_count"]) == ("10.000", 246, 2)
    assert (preview["per_person_in_base_unit"], preview["suggested_quantity_per_person"]) == ("0.04065", "40.650")
    reasons = {r["meal_record_id"]: r["excluded_reason"] for r in preview["records"]}
    assert reasons[no_rice["id"]].startswith("No net usage") and reasons[still_open["id"]] == "Not closed"
    saved = ok(client.post(f"{STANDARDS}/suggestion", json={
        "menu_id": a.biryani.id, "item_id": a.item.id, "meal_record_ids": ids, "unit_id": a.g.id,
        "effective_from": today(), "notes": "From two lunches"}), 201)
    assert (saved["status"], saved["source"], saved["quantity_per_person"], saved["unit_symbol"]) == (
        "DRAFT", "SUGGESTED", "40.650", "g")
    assert [b["meal_record_id"] for b in saved["basis"]] == [first["id"], second["id"]]
    assert saved["basis_totals"] == {"quantity_used": "10.000", "people_served": 246, "per_person": "0.04065",
                                     "unit_symbol": "kg"}
    assert db.query(PortionStandard).filter_by(status="APPROVED").count() == 0  # applied only after approval
    approved_suggestion = ok(client.post(f"{STANDARDS}/{saved['id']}/approve"))
    assert approved_suggestion["state"] == "IN_EFFECT"
    with pytest.raises(Exception, match="portion_standard_basis"):
        db.execute(text("UPDATE portion_standard_basis SET people_served = 1 WHERE standard_id = :id"), {"id": saved["id"]})
    db.rollback()
    none_usable = client.post(f"{STANDARDS}/suggestion", json={
        "menu_id": a.biryani.id, "item_id": a.item.id, "meal_record_ids": [still_open["id"]], "unit_id": a.g.id,
        "effective_from": today()})
    assert none_usable.status_code == 422


# ============================================================
# PLAN08 / MEAL02 CRITERION 4: PLANNED VS ACTUAL
# ============================================================

def test_plan08_plan_vs_actual_on_the_plan_and_the_meal_record(client, db, plan_world):
    a = plan_world.a
    act_as(client, a.manager)
    biryani_standards(client, a)
    plan = ok(client.post(f"{PLANS}/{ok(new_plan(client, a, [a.item, a.chicken], headcount=135), 201)['id']}/approve"))
    issued_and_confirmed(client, a, [(a.item, "6", None)])  # Lunch, today
    assert client.get(f"{PLANS}/{plan['id']}/comparison").json()["record_note"].startswith("No meal record")
    record = ok(create_meal(client, a), 201)
    record = ok(add_dish(client, record, "Veg biryani", "40", a.kg, menu=a.biryani), 201)

    open_view = client.get(f"{PLANS}/{plan['id']}/comparison").json()
    assert open_view["record_note"] == "The meal record is not closed; figures may change."
    ok(distribute(client, record, dish_named(record, "Veg biryani"), "37", "3",
                  [("RETAINED", "2", "Kept cold"), ("WASTED", "1", "Plate waste")]))
    ok(set_counts(client, record))  # expected 135, actual 123
    ok(client.post(f"{MEALS}/{record['id']}/close"))

    view = client.get(f"{PLANS}/{plan['id']}/comparison").json()
    assert view["usage_source"] == "CLOSING" and view["record_note"] is None
    assert view["headcounts"] == {"plan_expected": 135, "record_expected": 135, "record_actual": 123}
    rice = next(r for r in view["items"] if r["item_name"] == "Rice")
    chicken = next(r for r in view["items"] if r["item_name"] == "Chicken")
    assert (rice["planned_quantity"], rice["actual_net_quantity"], rice["difference"]) == ("20.250", "6.000", "-14.250")
    assert (rice["planned_per_person"], rice["actual_per_person"]) == ("0.150", "0.04878")
    assert (chicken["planned_quantity"], chicken["actual_net_quantity"], chicken["difference"]) == ("27.000", None, "-27.000")
    dish = view["dishes"][0]
    assert (dish["prepared_quantity"], dish["distributed_quantity"], dish["leftovers"]["RETAINED"],
            dish["leftovers"]["WASTED"]) == ("40.000", "37.000", "2.000", "1.000")
    panel = client.get(f"{MEALS}/{record['id']}").json()["planning"]
    assert panel["plan"]["plan_number"] == plan["plan_number"] and panel["comparison"]["items"] == view["items"]
    # STAFF who may read meal records do not see planning.
    grant(db, a.staff, a.admin, "meal.read")
    act_as(client, a.staff)
    assert client.get(f"{MEALS}/{record['id']}").json()["planning"] is None


# ============================================================
# PERMISSIONS, CAMPUS ISOLATION, S6-5, HISTORY
# ============================================================

def test_planning_is_admin_and_manager_work_whatever_staff_grants_exist(client, db, plan_world):
    a = plan_world.a
    act_as(client, a.manager)
    standard = ok(new_standard(client, a.item, "150", a.g, a.biryani), 201)
    for code in ("menu.read", "menu.create", "menu.update", "inventory.read", "inventory.create", "inventory.update",
                 "meal.read", "meal.create", "meal.update", "portion_standard.read", "portion_standard.create",
                 "portion_standard.update", "meal_plan.read", "meal_plan.create", "meal_plan.update"):
        grant(db, a.staff, a.admin, code)  # even codes written directly into the database
    act_as(client, a.staff)
    calls = [
        client.get(STANDARDS), client.get(f"{STANDARDS}/options"), client.get(f"{STANDARDS}/{standard['id']}"),
        new_standard(client, a.chicken, "200", a.g, a.biryani),
        client.post(f"{STANDARDS}/{standard['id']}/approve"),
        client.post(f"{STANDARDS}/copy-from-menu", json={"menu_id": a.biryani.id, "effective_from": today()}),
        client.get(PLANS), client.get(f"{PLANS}/options"), new_plan(client, a, [a.item]),
        client.put(f"/api/items/{a.dal.id}/kind", json={"item_kind": "RAW"}),
    ]
    assert [c.status_code for c in calls] == [403] * len(calls)
    act_as(client, a.admin)
    staff_codes = client.put(f"/api/authorization/staff/{a.staff.id}/permissions", json={"permission_ids": [
        db.query(Permission).filter_by(permission_code="meal_plan.read").one().id]})
    assert staff_codes.status_code == 422  # not STAFF-assignable (6-3)
    act_as(client, a.manager)
    codes = set(client.get("/api/authorization/me").json()["permissions"])
    assert {"portion_standard.create", "portion_standard.read", "portion_standard.update",
            "meal_plan.create", "meal_plan.read", "meal_plan.update"} <= codes


def test_campus_isolation(client, db, plan_world):
    a, b = plan_world.a, plan_world.b
    act_as(client, a.manager)
    approved(client, a.item, "150", a.g, a.biryani)
    standard_id = db.query(PortionStandard.id).scalar()
    plan = ok(new_plan(client, a, [a.item]), 201)
    act_as(client, b.manager)
    assert client.get(f"{STANDARDS}/{standard_id}").status_code == 404
    assert client.post(f"{STANDARDS}/{standard_id}/approve").status_code == 404
    assert client.get(f"{PLANS}/{plan['id']}").status_code == 404
    assert client.post(f"{PLANS}/{plan['id']}/approve").status_code == 404
    assert client.post(f"{PLANS}/{plan['id']}/cancel", json={"reason": "Not ours"}).status_code == 404
    assert client.get(f"{PLANS}/{plan['id']}/comparison").status_code == 404
    assert client.get(PLANS).json()["items"] == [] and client.get(STANDARDS).json()["items"] == []
    assert new_standard(client, b.item, "1", a.kg, b.menu).status_code == 422  # campus A's unit
    assert new_standard(client, a.item, "1", b.kg, b.menu).status_code == 404  # campus A's item


def test_s6_5_planning_code_never_touches_stock_or_purchasing_models():
    import app.api.routes.planning as planning

    imported = [name for name, value in vars(planning).items() if value in WRITE_MODELS]
    assert imported == []


def test_s6_3_units_and_conversions_used_by_planning_become_frozen(client, db, plan_world):
    a = plan_world.a
    act_as(client, a.manager)
    approved(client, a.item, "150", a.g, a.biryani)
    ok(new_standard(client, a.paneer, "40", a.g, a.biryani), 201)
    conversion = db.query(UnitConversion).filter_by(campus_id=a.campus.id).one()
    act_as(client, a.admin)
    edit = client.put(f"/api/master/unit-conversions/{conversion.id}", json={
        "from_unit_id": a.g.id, "to_unit_id": a.kg.id, "factor": "0.002"})
    assert edit.status_code == 409
    assert client.delete(f"/api/master/unit-conversions/{conversion.id}").status_code == 409
    unit_change = client.put(f"/api/master/items/{a.paneer.id}", json={
        "name": "Paneer", "category_id": a.category.id, "standard_unit_id": a.g.id, "minimum_stock": "0"})
    assert unit_change.status_code == 409 and "portion standards" in unit_change.json()["detail"]


def test_migration_trigger_sql_is_a_frozen_copy_of_the_model_sql():
    import app.models.planning as models

    spec = importlib.util.spec_from_file_location(
        "m4", API_DIR / "migrations" / "versions" / "f3a8c2d61b47_add_meal_planning.py")
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert [s.strip() for s in migration.GUARDS] == [s.strip() for s in models.PG_STATEMENTS]
    assert migration.SNAPSHOT_COLUMNS == models.SNAPSHOT_COLUMNS
