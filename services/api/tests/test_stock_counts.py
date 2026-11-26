"""
Stage 4 slice 4c: physical stock counts and adjustments (STK05, AT02), with
the decisions of 23 November 2026 (docs/STAGE-4-STOCK-PLAN.md):

- S1: stock_count.create records counts and raises adjustment requests;
  stock_count.read views them; approving and rejecting are ADMIN and
  KITCHEN_MANAGER only.
- S6: blind entry (the form never receives a balance); the system balance
  at count time, the physical quantity and the difference are stored and
  never recalculated; adjustments are raised explicitly, one PENDING per
  item; approval only by an ADMIN or KITCHEN_MANAGER who did not count
  (API and database); the difference measured at count time is posted,
  effective at the count time, created at approval; rejection posts
  nothing.
- S2: a negative adjustment is refused if the balance would go below zero
  at any point from the count time onwards.
- Q10 (interim): no fallback approver.
- Movements between the count and the approval: later movements are kept
  and follow the adjustment; a movement dated on or before the count but
  posted after it blocks raising and approval (count again).

In-memory SQLite with the shared fixtures of test_operational_authority
and the kitchen fixture of test_kitchen_issues (Rice: 20 kg opening stock
dated 10 days ago). tests/test_stock_counts_postgres.py covers races and
the PostgreSQL constraints.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.clock import campus_today
from app.models import AuditLog, User
from app.models.ledger_guard import CountIsFinal
from app.models.purchases import StockMovement
from app.models.stock import StockAdjustment, StockCount, StockCountItem
from app.services.stock_ledger import as_utc

from tests.test_kitchen_issues import (  # noqa: F401 (fixtures)
    balance,
    days_ago,
    issued_and_confirmed,
    kitchen,
)
from tests.test_operational_authority import (  # noqa: F401 (fixtures)
    act_as,
    client,
    db,
    grant,
    world,
)

COUNTS = "/api/stock-counts"
ADJUSTMENTS = "/api/stock-adjustments"


def record_count(client, lines, reason="Monthly stock check", remarks=None):
    return client.post(COUNTS, json={
        "reason": reason,
        "remarks": remarks,
        "lines": [{"item_id": item.id, "quantity": qty, **({"unit_id": unit.id} if unit else {})}
                  for item, qty, unit in lines],
    })


def counted(client, lines, **kwargs):
    response = record_count(client, lines, **kwargs)
    assert response.status_code == 201, response.text
    return response.json()


def line_of(count, item):
    return next(line for line in count["lines"] if line["item_id"] == item.id)


def raise_for(client, count, item, reason="Physical count differs from the system"):
    return client.post(f"{COUNTS}/{count['id']}/lines/{line_of(count, item)['id']}/adjustment",
                       json={"reason": reason})


def raised(client, count, item, **kwargs):
    response = raise_for(client, count, item, **kwargs)
    assert response.status_code == 201, response.text
    return response.json()


def approve(client, adjustment_id, note=None):
    return client.post(f"{ADJUSTMENTS}/{adjustment_id}/approve", json={"note": note} if note else {})


def reject(client, adjustment_id, reason="Recount: the store room was not finished"):
    return client.post(f"{ADJUSTMENTS}/{adjustment_id}/reject", json={"reason": reason})


def adjustment_movements(db):
    return db.query(StockMovement).filter_by(movement_type="ADJUSTMENT").order_by(StockMovement.id).all()


def ledger(client, item):
    return client.get(f"/api/stock/items/{item.id}/ledger").json()


# ============================================================
# STK05 — ACCEPTANCE CRITERIA
# ============================================================

def test_criterion_1_count_keeps_system_balance_physical_quantity_and_difference(client, kitchen):
    a = kitchen.a
    act_as(client, a.manager)

    count = counted(client, [(a.item, "18500", a.g), (a.dal, "2", None)])

    rice, dal = line_of(count, a.item), line_of(count, a.dal)
    assert count["count_number"] == "SC-00001"
    assert (rice["system_balance"], rice["physical_quantity"], rice["difference"]) == ("20.000", "18.500", "-1.500")
    assert (rice["quantity"], rice["unit_symbol"], rice["conversion_factor"]) == ("18500.000", "g", "0.001")
    assert (dal["system_balance"], dal["physical_quantity"], dal["difference"]) == ("0.000", "2.000", "2.000")
    assert count["difference_count"] == 2


def test_criterion_1_nothing_found_is_a_zero_count(client, kitchen):
    a = kitchen.a
    act_as(client, a.manager)

    count = counted(client, [(a.item, "0", None)])

    assert line_of(count, a.item)["difference"] == "-20.000"
    assert record_count(client, [(a.item, "-1", None)]).status_code == 422


def test_criterion_2_count_records_date_verifier_and_reason(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    before = datetime.now(timezone.utc)

    count = counted(client, [(a.item, "19", None)], reason="Quarter-end verification", remarks="Shelf B")

    counted_at = datetime.fromisoformat(count["counted_at"])
    assert before <= counted_at <= datetime.now(timezone.utc)
    assert (count["counted_by_name"], count["reason"], count["remarks"]) == ("KITCHEN_MANAGER A", "Quarter-end verification", "Shelf B")
    audit = db.query(AuditLog).filter_by(entity_type="STOCK_COUNT", entity_id=count["id"]).one()
    assert audit.action == "CREATE" and audit.user_id == a.manager.id
    assert audit.details["lines"][0]["system_balance"] == "20.000"
    assert audit.details["lines"][0]["physical_quantity"] == "19.000"
    for reason in ("", "  ", "ok"):
        assert record_count(client, [(a.item, "19", None)], reason=reason).status_code == 422


def test_criterion_3_original_count_never_changes(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    count = counted(client, [(a.item, "18", None)])
    adjustment = raised(client, count, a.item)
    act_as(client, a.admin)
    assert approve(client, adjustment["id"]).status_code == 200
    issued_and_confirmed(client, a, [(a.item, "5", None)])

    again = client.get(f"{COUNTS}/{count['id']}").json()

    assert line_of(again, a.item)["system_balance"] == "20.000"
    assert line_of(again, a.item)["difference"] == "-2.000"
    assert again["counted_at"] == count["counted_at"] and again["reason"] == count["reason"]
    for method in ("put", "patch", "delete"):
        assert getattr(client, method)(f"{COUNTS}/{count['id']}").status_code == 405


def test_criterion_3_the_application_refuses_to_change_a_saved_count(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    count = counted(client, [(a.item, "18", None)])

    record = db.get(StockCount, count["id"])
    record.reason = "edited later"
    with pytest.raises(CountIsFinal):
        db.flush()
    db.rollback()

    line = db.get(StockCountItem, line_of(count, a.item)["id"])
    line.system_balance = Decimal("18")
    with pytest.raises(CountIsFinal):
        db.flush()
    db.rollback()

    db.delete(db.get(StockCountItem, line_of(count, a.item)["id"]))
    with pytest.raises(CountIsFinal):
        db.flush()
    db.rollback()

    with pytest.raises(CountIsFinal):
        db.query(StockCountItem).filter_by(count_id=count["id"]).update({"difference": 0})
    db.rollback()
    assert db.get(StockCountItem, line_of(count, a.item)["id"]).system_balance == Decimal("20")


def test_criterion_4_an_approved_adjustment_is_a_separate_movement(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    count = counted(client, [(a.item, "18.5", None)])
    adjustment = raised(client, count, a.item)
    opening = db.query(StockMovement).filter_by(movement_type="OPENING").one()
    opening_before = (opening.quantity, opening.effective_at, opening.created_at)

    act_as(client, a.admin)
    response = approve(client, adjustment["id"], note="Checked the shelf")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "APPROVED" and response.json()["decision_reason"] == "Checked the shelf"
    (movement,) = adjustment_movements(db)
    assert (movement.direction, movement.quantity, movement.unit_id) == (-1, Decimal("1.5"), a.kg.id)
    assert (movement.source_key, movement.reference_type, movement.reference_id) == (
        f"ADJUSTMENT:{adjustment['id']}", "STOCK_ADJUSTMENT", adjustment["id"])
    assert as_utc(movement.effective_at) == datetime.fromisoformat(count["counted_at"])
    assert as_utc(movement.created_at) > as_utc(movement.effective_at)
    assert movement.created_by == a.admin.id
    db.refresh(opening)
    assert (opening.quantity, opening.effective_at, opening.created_at) == opening_before
    assert balance(client, a.item) == "18.500"


def test_criterion_5_the_counter_cannot_approve_or_reject(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    count = counted(client, [(a.item, "18", None)])
    adjustment = raised(client, count, a.item)

    for refused in (approve(client, adjustment["id"]), reject(client, adjustment["id"])):
        assert refused.status_code == 403
        assert "another Admin or Kitchen Manager" in refused.json()["detail"]
    assert adjustment_movements(db) == []

    act_as(client, a.admin)
    assert approve(client, adjustment["id"]).status_code == 200


def test_criterion_5_an_admin_counter_needs_the_kitchen_manager(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.admin)
    count = counted(client, [(a.dal, "3", None)])
    adjustment = raised(client, count, a.dal)

    assert approve(client, adjustment["id"]).status_code == 403
    act_as(client, a.manager)
    assert approve(client, adjustment["id"]).status_code == 200
    assert balance(client, a.dal) == "3.000"


def test_criterion_5_staff_never_approve_even_with_every_count_code(client, db, kitchen):
    a = kitchen.a
    for code in ("stock_count.create", "stock_count.read", "inventory.read", "consumption.update"):
        grant(db, a.staff, a.admin, code)
    act_as(client, a.manager)
    count = counted(client, [(a.item, "18", None)])
    adjustment = raised(client, count, a.item)

    act_as(client, a.staff)
    assert approve(client, adjustment["id"]).status_code == 403
    assert reject(client, adjustment["id"]).status_code == 403
    assert db.get(StockAdjustment, adjustment["id"]).status == "PENDING"


def test_the_database_refuses_a_decision_by_the_counter(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    count = counted(client, [(a.item, "18", None)])
    adjustment = db.get(StockAdjustment, raised(client, count, a.item)["id"])

    adjustment.status, adjustment.decided_by = "REJECTED", a.manager.id
    adjustment.decided_at, adjustment.decision_reason = datetime.now(timezone.utc), "self"
    with pytest.raises(IntegrityError) as refused:
        db.commit()
    assert "ck_stock_adjustment_independent_approver" in str(refused.value)
    db.rollback()


def test_the_counter_copied_onto_an_adjustment_must_be_the_real_counter(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    count = counted(client, [(a.item, "18", None)])
    line = line_of(count, a.item)

    db.add(StockAdjustment(campus_id=a.campus.id, count_id=count["id"], count_item_id=line["id"],
                           item_id=a.item.id, counted_by=a.admin.id, reason="forged counter",
                           status="PENDING", raised_by=a.admin.id))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


# ============================================================
# AT02 — PHYSICAL STOCK VERIFICATION (walkthrough)
# ============================================================

def test_at02_walkthrough(client, db, kitchen):
    a = kitchen.a
    for code in ("stock_count.create", "stock_count.read"):
        grant(db, a.staff, a.admin, code)

    # A store keeper (STAFF) records a count that differs from the system.
    act_as(client, a.staff)
    count = counted(client, [(a.item, "17", None)], reason="Weekly store check")
    rice = line_of(count, a.item)

    # Original system balance preserved; physical count and reason recorded.
    assert (rice["system_balance"], rice["physical_quantity"], rice["difference"]) == ("20.000", "17.000", "-3.000")
    assert count["reason"] == "Weekly store check"

    # Stock unchanged by the count and by raising the adjustment.
    act_as(client, a.admin)
    assert balance(client, a.item) == "20.000"
    act_as(client, a.staff)
    adjustment = raised(client, count, a.item)
    assert adjustment["status"] == "PENDING" and adjustment["you_counted"] is True
    assert adjustment["can_decide"] is False
    act_as(client, a.admin)
    assert balance(client, a.item) == "20.000"
    assert adjustment_movements(db) == []

    # The approver must not be the counter: STAFF can never approve; the
    # Kitchen Manager (who did not count) can.
    act_as(client, a.staff)
    assert approve(client, adjustment["id"]).status_code == 403
    act_as(client, a.manager)
    approved = approve(client, adjustment["id"])
    assert approved.status_code == 200, approved.text
    assert balance(client, a.item) == "17.000"
    assert ledger(client, a.item)["item"]["balance"] == "17.000"
    assert line_of(client.get(f"{COUNTS}/{count['id']}").json(), a.item)["system_balance"] == "20.000"


# ============================================================
# S6 — BLIND COUNTS
# ============================================================

def test_count_form_options_never_carry_a_balance(client, kitchen):
    a = kitchen.a
    act_as(client, a.admin)  # holds inventory.read, still blind on the count form

    response = client.get(f"{COUNTS}/options")

    assert response.status_code == 200, response.text
    assert "balance" not in response.text.lower() and "stock_visible" not in response.text
    assert {item["name"] for item in response.json()["items"]} == {"Rice", "Toor Dal"}
    assert {"id", "name", "category_name", "standard_unit_id", "is_active"} == set(response.json()["items"][0])


def test_a_client_cannot_send_a_system_balance_or_difference(client, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    for extra in ({"system_balance": "18"}, {"difference": "0"}):
        response = client.post(COUNTS, json={"reason": "Monthly check", "lines": [
            {"item_id": a.item.id, "quantity": "18", **extra}]})
        assert response.status_code == 422, extra
    response = client.post(COUNTS, json={"reason": "Monthly check", "system_balance": "1",
                                         "lines": [{"item_id": a.item.id, "quantity": "18"}]})
    assert response.status_code == 422


def test_a_counter_without_stock_count_read_gets_no_balances_back(client, db, kitchen):
    a = kitchen.a
    grant(db, a.staff, a.admin, "stock_count.create")
    act_as(client, a.staff)

    assert client.get(f"{COUNTS}/options").status_code == 200
    response = record_count(client, [(a.item, "19", None)])

    assert response.status_code == 201, response.text
    assert "balance" not in response.text and "difference" not in response.text
    assert set(response.json()) == {"id", "count_number", "counted_at", "line_count"}
    assert client.get(f"{COUNTS}/{response.json()['id']}").status_code == 403
    assert client.get(COUNTS).status_code == 403


def test_a_count_never_raises_an_adjustment_by_itself(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.manager)

    count = counted(client, [(a.item, "12", None), (a.dal, "4", None)])

    assert db.query(StockAdjustment).count() == 0
    assert all(line["adjustment"] is None and line["can_raise"] for line in count["lines"])
    assert balance(client, a.item) == "20.000"


def test_a_line_without_a_difference_cannot_raise(client, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    count = counted(client, [(a.item, "20", None)])

    assert line_of(count, a.item)["can_raise"] is False
    assert raise_for(client, count, a.item).status_code == 422


def test_one_pending_adjustment_per_item(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    first = counted(client, [(a.item, "18", None)])
    second = counted(client, [(a.item, "18", None)])
    raised(client, first, a.item)

    refused = raise_for(client, second, a.item)

    assert refused.status_code == 409 and "SC-00001" in refused.json()["detail"]
    detail = client.get(f"{COUNTS}/{second['id']}").json()
    assert line_of(detail, a.item)["other_pending_adjustment"]["count_number"] == "SC-00001"
    assert line_of(detail, a.item)["can_raise"] is False
    # The partial unique index is the final guard.
    db.add(StockAdjustment(campus_id=a.campus.id, count_id=second["id"], count_item_id=line_of(second, a.item)["id"],
                           item_id=a.item.id, counted_by=a.manager.id, reason="second pending",
                           status="PENDING", raised_by=a.manager.id))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_a_line_raises_at_most_once(client, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    count = counted(client, [(a.item, "18", None)])
    raised(client, count, a.item)

    again = raise_for(client, count, a.item)

    assert again.status_code == 409 and "already waiting" in again.json()["detail"]


# ============================================================
# REJECTION
# ============================================================

def test_rejection_posts_nothing_keeps_the_reason_and_needs_a_new_count(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    count = counted(client, [(a.item, "15", None)])
    adjustment = raised(client, count, a.item)

    act_as(client, a.admin)
    response = reject(client, adjustment["id"], reason="Bags in the cold room were not counted")

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["decision_reason"], body["decided_by_name"]) == (
        "REJECTED", "Bags in the cold room were not counted", "ADMIN A")
    assert adjustment_movements(db) == [] and body["movement_id"] is None
    assert balance(client, a.item) == "20.000"
    assert approve(client, adjustment["id"]).status_code == 409

    act_as(client, a.manager)
    again = raise_for(client, count, a.item)
    assert again.status_code == 409 and "Count Rice again" in again.json()["detail"]
    recount = counted(client, [(a.item, "19", None)])
    second = raised(client, recount, a.item)
    act_as(client, a.admin)
    assert approve(client, second["id"]).status_code == 200
    assert balance(client, a.item) == "19.000"


def test_rejection_needs_a_reason(client, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    adjustment = raised(client, counted(client, [(a.item, "18", None)]), a.item)
    act_as(client, a.admin)

    for reason in ("", "no"):
        assert reject(client, adjustment["id"], reason=reason).status_code == 422


def test_a_decided_adjustment_cannot_be_decided_again(client, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    adjustment = raised(client, counted(client, [(a.item, "18", None)]), a.item)
    act_as(client, a.admin)
    assert approve(client, adjustment["id"]).status_code == 200

    assert approve(client, adjustment["id"]).status_code == 409
    assert reject(client, adjustment["id"]).status_code == 409


# ============================================================
# MOVEMENTS BETWEEN THE COUNT AND THE APPROVAL
# ============================================================

def test_movements_after_the_count_are_kept_and_follow_the_adjustment(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    count = counted(client, [(a.item, "18", None)])
    adjustment = raised(client, count, a.item)
    issued_and_confirmed(client, a, [(a.item, "5", None)])  # today: effective after the count

    act_as(client, a.admin)
    before = client.get(f"{ADJUSTMENTS}/{adjustment['id']}").json()
    assert (before["system_balance_at_count"], before["count_time_balance_now"], before["balance_now"],
            before["balance_after_approval"], before["ledger_changed"]) == ("20.000", "20.000", "15.000", "13.000", False)
    (since,) = before["movements_since_count"]
    assert (since["movement_type"], since["signed_quantity"], since["dated_before_count"]) == ("ISSUE", "-5.000", False)
    assert since["document_number"] == "KI-00001"

    assert approve(client, adjustment["id"]).status_code == 200

    assert balance(client, a.item) == "13.000"
    rows = {m["movement_type"]: m for m in ledger(client, a.item)["movements"]}
    # Replayed in ledger order: the count time holds the counted 18 kg, the
    # later issue follows it.
    assert rows["ADJUSTMENT"]["balance_after"] == "18.000"
    assert rows["ISSUE"]["balance_after"] == "13.000"
    issue = db.query(StockMovement).filter_by(movement_type="ISSUE").one()
    assert issue.quantity == Decimal("5") and issue.direction == -1  # untouched


def test_a_backdated_movement_posted_after_the_count_blocks_approval(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    count = counted(client, [(a.item, "18", None)])
    adjustment = raised(client, count, a.item)
    issued_and_confirmed(client, a, [(a.item, "3", None)], issue_date=days_ago(1))  # dated before the count

    act_as(client, a.admin)
    detail = client.get(f"{ADJUSTMENTS}/{adjustment['id']}").json()
    assert detail["ledger_changed"] is True
    assert (detail["system_balance_at_count"], detail["count_time_balance_now"]) == ("20.000", "17.000")
    assert detail["movements_since_count"][0]["dated_before_count"] is True

    refused = approve(client, adjustment["id"])

    assert refused.status_code == 409
    assert "has changed since the count was saved" in refused.json()["detail"]
    assert "Count Rice again" in refused.json()["detail"]
    assert adjustment_movements(db) == []
    assert balance(client, a.item) == "17.000"
    assert reject(client, adjustment["id"], reason="Late issue entered after the count").status_code == 200

    act_as(client, a.manager)
    recount = counted(client, [(a.item, "15", None)])
    assert line_of(recount, a.item)["system_balance"] == "17.000"
    act_as(client, a.admin)
    assert approve(client, raised(client, recount, a.item)["id"]).status_code == 200
    assert balance(client, a.item) == "15.000"


def test_raising_is_refused_once_the_ledger_at_the_count_time_changed(client, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    count = counted(client, [(a.item, "18", None)])
    issued_and_confirmed(client, a, [(a.item, "3", None)], issue_date=days_ago(1))

    detail = client.get(f"{COUNTS}/{count['id']}").json()
    assert line_of(detail, a.item)["ledger_changed"] is True and line_of(detail, a.item)["can_raise"] is False
    refused = raise_for(client, count, a.item)
    assert refused.status_code == 409 and "Count Rice again" in refused.json()["detail"]


def test_a_second_count_cannot_apply_the_same_difference_twice(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    first = counted(client, [(a.item, "18", None)])
    second = counted(client, [(a.item, "18", None)])
    act_as(client, a.admin)
    assert approve(client, raised(client, first, a.item)["id"]).status_code == 200
    assert balance(client, a.item) == "18.000"

    act_as(client, a.manager)
    detail = client.get(f"{COUNTS}/{second['id']}").json()
    assert line_of(detail, a.item)["ledger_changed"] is True
    assert raise_for(client, second, a.item).status_code == 409
    assert len(adjustment_movements(db)) == 1
    # The first count, already applied, is not reported as changed.
    assert line_of(client.get(f"{COUNTS}/{first['id']}").json(), a.item)["ledger_changed"] is False


def test_an_adjustment_approved_while_another_count_waits_blocks_the_stale_one(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    first = counted(client, [(a.item, "18", None)])
    first_adjustment = raised(client, first, a.item)
    second = counted(client, [(a.item, "18", None)])  # saved while the first is pending
    act_as(client, a.admin)
    assert approve(client, first_adjustment["id"]).status_code == 200

    act_as(client, a.manager)
    assert raise_for(client, second, a.item).status_code == 409
    assert balance(client, a.item) == "18.000"


# ============================================================
# S2 — NO NEGATIVE BALANCE AT ANY POINT
# ============================================================

def test_a_negative_adjustment_is_refused_if_later_history_would_go_below_zero(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    count = counted(client, [(a.item, "2", None)])  # 18 kg short
    adjustment = raised(client, count, a.item)
    issued_and_confirmed(client, a, [(a.item, "10", None)])  # after the count: 10 kg left

    act_as(client, a.admin)
    detail = client.get(f"{ADJUSTMENTS}/{adjustment['id']}").json()
    assert detail["would_go_negative"] is True and detail["shortfall"]["balance"] == "-8.000"
    refused = approve(client, adjustment["id"])

    assert refused.status_code == 409
    assert "Not enough Rice in stock" in refused.json()["detail"] and "-8.000 kg" in refused.json()["detail"]
    assert "Reject this adjustment" in refused.json()["detail"]
    assert adjustment_movements(db) == [] and balance(client, a.item) == "10.000"
    assert db.get(StockAdjustment, adjustment["id"]).status == "PENDING"


def test_a_positive_adjustment_adds_stock_from_the_count_time(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    count = counted(client, [(a.dal, "2.5", None)])
    adjustment = raised(client, count, a.dal)
    act_as(client, a.admin)

    assert approve(client, adjustment["id"]).status_code == 200

    (movement,) = adjustment_movements(db)
    assert (movement.direction, movement.quantity) == (1, Decimal("2.5"))
    assert balance(client, a.dal) == "2.500"


# ============================================================
# Q10 — NO FALLBACK APPROVER (interim)
# ============================================================

def test_without_an_eligible_approver_the_adjustment_waits_and_says_why(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.admin)
    adjustment = raised(client, counted(client, [(a.item, "18", None)]), a.item)
    db.get(User, a.manager.id).is_active = False
    db.commit()

    listed = client.get(ADJUSTMENTS, params={"status": "PENDING"}).json()["items"][0]

    assert (listed["you_counted"], listed["can_decide"], listed["eligible_approver_count"]) == (True, False, 0)
    assert approve(client, adjustment["id"]).status_code == 403
    db.get(User, a.manager.id).is_active = True
    db.commit()
    assert client.get(ADJUSTMENTS).json()["items"][0]["eligible_approver_count"] == 1
    act_as(client, a.manager)
    assert approve(client, adjustment["id"]).status_code == 200


# ============================================================
# S1 — PERMISSIONS AND CAMPUS ISOLATION
# ============================================================

def test_staff_without_count_codes_are_refused_everywhere(client, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    count = counted(client, [(a.item, "18", None)])
    adjustment = raised(client, count, a.item)

    act_as(client, a.staff)
    for response in (
        client.get(f"{COUNTS}/options"), client.get(COUNTS), client.get(f"{COUNTS}/{count['id']}"),
        record_count(client, [(a.item, "18", None)]), raise_for(client, count, a.item),
        client.get(ADJUSTMENTS), client.get(f"{ADJUSTMENTS}/{adjustment['id']}"),
        approve(client, adjustment["id"]), reject(client, adjustment["id"]),
    ):
        assert response.status_code == 403, response.request.url


def test_staff_with_read_only_view_counts_but_cannot_count_or_raise(client, db, kitchen):
    a = kitchen.a
    grant(db, a.staff, a.admin, "stock_count.read")
    act_as(client, a.manager)
    count = counted(client, [(a.item, "18", None)])
    adjustment = raised(client, count, a.item)
    issued_and_confirmed(client, a, [(a.item, "1", None)])

    act_as(client, a.staff)
    assert client.get(COUNTS).json()["total"] == 1
    assert line_of(client.get(f"{COUNTS}/{count['id']}").json(), a.item)["system_balance"] == "20.000"
    viewed = client.get(f"{ADJUSTMENTS}/{adjustment['id']}").json()
    # Current stock figures need inventory.read.
    assert viewed["stock_visible"] is False
    assert viewed["balance_now"] is None and viewed["movements_since_count"] is None
    assert client.get(f"{COUNTS}/options").status_code == 403
    assert record_count(client, [(a.item, "18", None)]).status_code == 403
    assert raise_for(client, count, a.item).status_code == 403


def test_staff_with_create_can_count_and_raise_but_never_decide(client, db, kitchen):
    a = kitchen.a
    for code in ("stock_count.create", "stock_count.read"):
        grant(db, a.staff, a.admin, code)
    act_as(client, a.manager)
    managers_count = counted(client, [(a.item, "18", None)])

    act_as(client, a.staff)
    own = counted(client, [(a.dal, "1", None)])
    assert raised(client, own, a.dal)["status"] == "PENDING"
    assert raised(client, managers_count, a.item)["status"] == "PENDING"  # any count's line
    for item in client.get(ADJUSTMENTS).json()["items"]:
        assert item["can_decide"] is False


def test_kitchen_manager_holds_the_count_codes_and_decides_others_counts(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    codes = set(client.get("/api/authorization/me").json()["permissions"])
    assert {"stock_count.create", "stock_count.read"} <= codes

    act_as(client, a.admin)
    adjustment = raised(client, counted(client, [(a.item, "18", None)]), a.item)
    act_as(client, a.manager)
    listed = client.get(ADJUSTMENTS).json()["items"][0]
    assert listed["can_decide"] is True and listed["stock_visible"] is True
    assert reject(client, adjustment["id"]).status_code == 200


def test_another_campus_sees_nothing_and_cannot_act(client, db, kitchen):
    a, b = kitchen.a, kitchen.b
    act_as(client, a.manager)
    count = counted(client, [(a.item, "18", None)])
    adjustment = raised(client, count, a.item)

    act_as(client, b.admin)
    assert client.get(COUNTS).json()["total"] == 0
    assert client.get(ADJUSTMENTS).json()["total"] == 0
    assert {i["name"] for i in client.get(f"{COUNTS}/options").json()["items"]} == {"Rice"}
    assert client.get(f"{COUNTS}/{count['id']}").status_code == 404
    assert client.get(f"{ADJUSTMENTS}/{adjustment['id']}").status_code == 404
    assert raise_for(client, count, a.item).status_code == 404
    assert approve(client, adjustment["id"]).status_code == 404
    assert reject(client, adjustment["id"]).status_code == 404
    assert record_count(client, [(a.item, "1", None)]).status_code == 404
    assert db.get(StockAdjustment, adjustment["id"]).status == "PENDING"


# ============================================================
# LEDGER, LISTS, AUDIT AND MASTER DATA
# ============================================================

def test_the_ledger_and_movement_log_name_the_count(client, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    count = counted(client, [(a.item, "19", None)])
    adjustment = raised(client, count, a.item)
    act_as(client, a.admin)
    approve(client, adjustment["id"])

    row = next(m for m in ledger(client, a.item)["movements"] if m["movement_type"] == "ADJUSTMENT")
    assert (row["document_number"], row["stock_count_id"], row["kitchen_issue_id"]) == ("SC-00001", count["id"], None)
    assert row["signed_quantity"] == "-1.000" and row["balance_after"] == "19.000"
    logged = next(m for m in client.get("/api/stock-movements").json()["items"] if m["movement_type"] == "ADJUSTMENT")
    assert (logged["document_number"], logged["stock_count_id"]) == ("SC-00001", count["id"])


def test_count_and_adjustment_lists(client, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    first = counted(client, [(a.item, "18", None), (a.dal, "0", None)])
    raised(client, first, a.item)
    counted(client, [(a.dal, "1", None)])

    listed = client.get(COUNTS).json()
    assert [c["count_number"] for c in listed["items"]] == ["SC-00002", "SC-00001"]
    older = listed["items"][1]
    assert (older["line_count"], older["difference_count"], older["pending_count"], older["not_raised_count"]) == (2, 1, 1, 0)
    assert client.get(COUNTS, params={"item_id": a.item.id}).json()["total"] == 1
    assert client.get(COUNTS, params={"search": "00002"}).json()["total"] == 1
    today = campus_today().isoformat()
    assert client.get(COUNTS, params={"date_from": today, "date_to": today}).json()["total"] == 2
    tomorrow = (campus_today() + timedelta(days=1)).isoformat()
    assert client.get(COUNTS, params={"date_from": tomorrow}).json()["total"] == 0
    adjustments = client.get(ADJUSTMENTS, params={"status": "PENDING"}).json()
    assert adjustments["status_counts"] == {"PENDING": 1, "APPROVED": 0, "REJECTED": 0}
    assert adjustments["items"][0]["count_number"] == "SC-00001"


def test_every_step_is_audited(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    count = counted(client, [(a.item, "18", None), (a.dal, "1", None)])
    first = raised(client, count, a.item)
    second = raised(client, count, a.dal)
    act_as(client, a.admin)
    approve(client, first["id"])
    reject(client, second["id"], reason="Dal sacks belong to the hostel store")

    actions = sorted((r.entity_type, r.action, r.user_id) for r in db.query(AuditLog).filter(
        AuditLog.entity_type.in_(("STOCK_COUNT", "STOCK_ADJUSTMENT"))))
    assert actions == sorted([
        ("STOCK_COUNT", "CREATE", a.manager.id),
        ("STOCK_ADJUSTMENT", "RAISE", a.manager.id), ("STOCK_ADJUSTMENT", "RAISE", a.manager.id),
        ("STOCK_ADJUSTMENT", "APPROVE", a.admin.id), ("STOCK_ADJUSTMENT", "REJECT", a.admin.id),
    ])
    approval = db.query(AuditLog).filter_by(entity_type="STOCK_ADJUSTMENT", action="APPROVE").one()
    movement = adjustment_movements(db)[0]
    assert approval.details["movement_id"] == movement.id
    assert (approval.details["balance_before"], approval.details["balance_after"]) == ("20.000", "18.000")


def test_a_counted_item_keeps_its_standard_unit(client, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    counted(client, [(a.dal, "1", None)])
    act_as(client, a.admin)

    response = client.put(f"/api/master/items/{a.dal.id}", json={
        "name": "Toor Dal", "category_id": a.category.id, "standard_unit_id": a.g.id, "minimum_stock": "0"})

    assert response.status_code == 409 and "stock count lines" in response.json()["detail"]


def test_inactive_or_unknown_items_and_units(client, db, kitchen):
    a = kitchen.a
    act_as(client, a.manager)
    a.dal.is_active = False
    db.commit()

    assert record_count(client, [(a.dal, "1", None)]).status_code == 422
    assert client.post(COUNTS, json={"reason": "Monthly check", "lines": [
        {"item_id": 99999, "quantity": "1"}]}).status_code == 404
    assert record_count(client, [(a.item, "1", None), (a.item, "2", None)]).status_code == 422
