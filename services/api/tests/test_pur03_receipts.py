"""
PUR03 — Record Accepted Receipts.

Acceptance criteria (PROPOSAL.md §5.1):
1. Each receipt must be linked to its source purchase.
2. Ordered, billed and accepted quantities must remain distinguishable.
   (Billed, received, accepted and rejected are tested here. "Ordered"
   needs purchase orders, which do not exist yet — stage 3.)
3. Only confirmed accepted quantities increase stock.
4. Duplicate receipt posting must be prevented.
5. Draft receipts must not affect stock.

Also: partial receipts (several receipts per bill, an assumption awaiting
client confirmation), correcting and cancelling drafts, permissions,
campus isolation, the receipt list and the stock movement log.
In-memory SQLite, shared fixtures from test_operational_authority.
"""

from datetime import date, timedelta

import pytest

from app.api.routes import receipts as receipts_module
from app.models import AuditLog, Item
from app.models.purchases import GoodsReceipt, StockMovement

from tests.test_operational_authority import (  # noqa: F401 (fixtures)
    act_as,
    client,
    db,
    grant,
    world,
)

BILLS = "/api/purchases/"


@pytest.fixture
def dal(db, world):
    item = Item(campus_id=world.a.campus.id, name="Toor Dal",
                category_id=world.a.category.id,
                standard_unit_id=world.a.kg.id, minimum_stock=0)
    db.add(item)
    db.commit()
    return item


def create_bill(client, place, invoice, lines):
    response = client.post(BILLS, json={
        "supplier_id": place.supplier.id, "invoice_number": invoice,
        "purchase_date": "2026-11-03",
        "items": [{"item_id": item.id, "quantity": qty, "unit_id": place.kg.id,
                   "unit_rate": "40.00"} for item, qty in lines],
    })
    assert response.status_code == 201, response.text
    return response.json()


def bill_lines(client, bill_id):
    return client.get(f"{BILLS}{bill_id}/receiving").json()["lines"]


def draft(client, bill_id, lines, receipt_date="2026-11-05", remarks=None):
    return client.post(f"{BILLS}{bill_id}/receipts", json={
        "receipt_date": receipt_date, "remarks": remarks,
        "items": [{"purchase_item_id": pid, "quantity_received": r,
                   "quantity_accepted": a, "quantity_rejected": j}
                  for pid, r, a, j in lines],
    })


def movements(db, campus_id):
    return db.query(StockMovement).filter_by(campus_id=campus_id).all()


@pytest.fixture
def bill(client, world, dal):
    act_as(client, world.a.admin)
    created = create_bill(client, world.a, "PUR03-1", [(world.a.item, "10"), (dal, "4")])
    lines = bill_lines(client, created["id"])
    return {"id": created["id"], "rice": lines[0]["purchase_item_id"],
            "dal": lines[1]["purchase_item_id"]}


# ============================================================
# 1. LINKED TO ITS SOURCE PURCHASE
# ============================================================

def test_criterion_1_receipts_are_linked_to_their_bill(client, world, bill):
    receipt = draft(client, bill["id"], [(bill["rice"], "6", "6", "0")]).json()

    assert receipt["purchase_id"] == bill["id"]
    assert receipt["invoice_number"] == "PUR03-1"
    assert receipt["supplier_name"] == world.a.supplier.name

    listed = client.get("/api/receipts", params={"purchase_id": bill["id"]}).json()
    assert [r["id"] for r in listed["items"]] == [receipt["id"]]
    assert listed["items"][0]["invoice_number"] == "PUR03-1"
    assert client.get(f"{BILLS}{bill['id']}/receipts").json()[0]["id"] == receipt["id"]


# ============================================================
# 2. BILLED, RECEIVED, ACCEPTED AND REJECTED STAY DISTINGUISHABLE
# ============================================================

def test_criterion_2_billed_received_accepted_and_rejected_are_separate(client, bill):
    receipt = draft(client, bill["id"], [(bill["rice"], "6", "5", "1")]).json()

    line = bill_lines(client, bill["id"])[0]
    assert (line["billed_quantity"], line["in_draft_quantity"], line["received_quantity"],
            line["remaining_quantity"]) == ("10.000", "6.000", "0.000", "4.000")
    detail = receipt["items"][0]
    assert (detail["billed_quantity"], detail["quantity_received"], detail["quantity_accepted"],
            detail["quantity_rejected"]) == ("10.000", "6.000", "5.000", "1.000")

    assert client.post(f"/api/receipts/{receipt['id']}/accept").status_code == 200
    line = bill_lines(client, bill["id"])[0]
    assert (line["billed_quantity"], line["received_quantity"], line["accepted_quantity"],
            line["rejected_quantity"], line["in_draft_quantity"], line["remaining_quantity"]) == (
        "10.000", "6.000", "5.000", "1.000", "0.000", "4.000")


def test_receiving_and_receipts_show_no_prices(client, bill):
    draft(client, bill["id"], [(bill["rice"], "1", "1", "0")])
    money_words = ("rate", "total", "amount", "price", "paid")

    def keys(value):
        if isinstance(value, dict):
            return set(value) | {k for v in value.values() for k in keys(v)}
        if isinstance(value, list):
            return {k for v in value for k in keys(v)}
        return set()

    for path in (f"{BILLS}{bill['id']}/receiving", "/api/receipts", "/api/receipts/receivable-bills"):
        found = {k for k in keys(client.get(path).json()) if any(w in k for w in money_words)}
        assert found <= {"total", "total_pages"}, (path, found)


# ============================================================
# 3. ONLY ACCEPTED QUANTITIES INCREASE STOCK
# ============================================================

def test_criterion_3_only_accepted_quantity_reaches_stock(client, db, world, bill):
    receipt = draft(client, bill["id"], [(bill["rice"], "6", "5", "1"),
                                         (bill["dal"], "4", "0", "4")]).json()

    accepted = client.post(f"/api/receipts/{receipt['id']}/accept").json()

    posted = movements(db, world.a.campus.id)
    assert [(m.item_id, str(m.quantity)) for m in posted] == [(world.a.item.id, "5.000")]
    assert accepted["stock_movements"][0]["quantity"] == "5.000"
    log = client.get("/api/stock-movements", params={"receipt_id": receipt["id"]}).json()
    assert [(m["item_name"], m["quantity"], m["unit_symbol"], m["invoice_number"])
            for m in log["items"]] == [("Rice", "5.000", "kg", "PUR03-1")]


def test_a_receipt_is_accepted_only_when_every_line_is_classified(client, db, world, bill):
    receipt = draft(client, bill["id"], [(bill["rice"], "6", "4", "1")]).json()

    refused = client.post(f"/api/receipts/{receipt['id']}/accept")

    assert refused.status_code == 422
    assert "must equal received quantity" in refused.json()["detail"]
    assert movements(db, world.a.campus.id) == []


# ============================================================
# 4. DUPLICATE POSTING IS PREVENTED
# ============================================================

def test_criterion_4_a_receipt_posts_stock_once(client, db, world, bill):
    receipt = draft(client, bill["id"], [(bill["rice"], "6", "6", "0")]).json()

    assert client.post(f"/api/receipts/{receipt['id']}/accept").status_code == 200
    again = client.post(f"/api/receipts/{receipt['id']}/accept")

    assert again.status_code == 409
    assert len(movements(db, world.a.campus.id)) == 1
    assert client.post(f"/api/receipts/{receipt['id']}/cancel",
                       json={"reason": "late"}).status_code == 409
    assert client.put(f"/api/receipts/{receipt['id']}", json={
        "items": [{"purchase_item_id": bill["rice"], "quantity_received": "1",
                   "quantity_accepted": "1"}]}).status_code == 409


# ============================================================
# 5. DRAFTS DO NOT AFFECT STOCK
# ============================================================

def test_criterion_5_drafts_never_touch_stock(client, db, world, bill):
    receipt = draft(client, bill["id"], [(bill["rice"], "6", "6", "0")]).json()
    client.put(f"/api/receipts/{receipt['id']}", json={
        "receipt_date": "2026-11-05",
        "items": [{"purchase_item_id": bill["rice"], "quantity_received": "7",
                   "quantity_accepted": "7"}]})
    client.post(f"/api/receipts/{receipt['id']}/cancel", json={"reason": "Wrong bill"})

    assert movements(db, world.a.campus.id) == []
    assert client.get("/api/stock-movements").json()["total"] == 0


# ============================================================
# PARTIAL RECEIPTS (assumption awaiting client confirmation)
# ============================================================

def test_several_partial_receipts_up_to_the_billed_quantity(client, bill):
    first = draft(client, bill["id"], [(bill["rice"], "6", "6", "0")]).json()
    second = draft(client, bill["id"], [(bill["rice"], "4", "3", "1")]).json()

    over = draft(client, bill["id"], [(bill["rice"], "0.001", "0.001", "0")])
    assert over.status_code == 422
    assert "exceeds the remaining purchased quantity" in over.json()["detail"]

    for receipt in (first, second):
        assert client.post(f"/api/receipts/{receipt['id']}/accept").status_code == 200
    receiving = client.get(f"{BILLS}{bill['id']}/receiving").json()
    rice = receiving["lines"][0]
    assert (rice["received_quantity"], rice["accepted_quantity"], rice["rejected_quantity"],
            rice["remaining_quantity"]) == ("10.000", "9.000", "1.000", "0.000")
    assert receiving["fully_received"] is False          # dal is still open
    assert receiving["receipt_counts"] == {"DRAFT": 0, "ACCEPTED": 2, "CANCELLED": 0}


# ============================================================
# CORRECTING AND CANCELLING DRAFTS
# ============================================================

def test_a_draft_can_be_corrected_before_acceptance(client, db, bill):
    receipt = draft(client, bill["id"], [(bill["rice"], "6", "0", "0"),
                                         (bill["dal"], "4", "0", "0")]).json()

    bad = client.put(f"/api/receipts/{receipt['id']}", json={"items": [
        {"purchase_item_id": bill["rice"], "quantity_received": "6",
         "quantity_accepted": "6", "quantity_rejected": "1"}]})
    assert bad.status_code == 422

    # Its own quantity is not counted against it: 10 of 10 is allowed.
    fixed = client.put(f"/api/receipts/{receipt['id']}", json={
        "receipt_date": "2026-11-06", "remarks": "Inspected",
        "items": [{"purchase_item_id": bill["rice"], "quantity_received": "10",
                   "quantity_accepted": "9.5", "quantity_rejected": "0.5"}]})
    assert fixed.status_code == 200, fixed.text
    body = fixed.json()
    assert body["receipt_date"] == "2026-11-06" and body["remarks"] == "Inspected"
    assert [(i["purchase_item_id"], i["quantity_accepted"]) for i in body["items"]] == [
        (bill["rice"], "9.500")]                          # the dal line was removed

    audit = db.query(AuditLog).filter_by(entity_type="GOODS_RECEIPT", action="UPDATE").one()
    assert [line["quantity_received"] for line in audit.details["before"]] == ["6.000", "4.000"]
    assert audit.details["after"][0]["quantity_accepted"] == "9.500"
    assert client.post(f"/api/receipts/{receipt['id']}/accept").status_code == 200


def test_cancelling_a_draft_frees_its_quantity_and_keeps_the_record(client, db, world, bill):
    receipt = draft(client, bill["id"], [(bill["rice"], "10", "10", "0")]).json()
    assert draft(client, bill["id"], [(bill["rice"], "1", "1", "0")]).status_code == 422

    assert client.post(f"/api/receipts/{receipt['id']}/cancel",
                       json={"reason": "   "}).status_code == 422
    cancelled = client.post(f"/api/receipts/{receipt['id']}/cancel",
                            json={"reason": "Entered against the wrong bill"})

    assert cancelled.status_code == 200
    body = cancelled.json()
    assert body["status"] == "CANCELLED"
    assert body["cancellation"]["reason"] == "Entered against the wrong bill"
    assert body["cancellation"]["cancelled_by_name"] == world.a.admin.full_name
    assert draft(client, bill["id"], [(bill["rice"], "10", "10", "0")]).status_code == 201
    assert client.post(f"/api/receipts/{receipt['id']}/accept").status_code == 409
    assert db.query(GoodsReceipt).filter_by(id=receipt["id"]).one().status == "CANCELLED"
    assert client.get("/api/receipts").json()["status_counts"] == {
        "DRAFT": 1, "ACCEPTED": 0, "CANCELLED": 1}


def test_receipt_dates_follow_the_campus_calendar(client, bill, monkeypatch):
    monkeypatch.setattr(receipts_module, "campus_today", lambda: date(2026, 11, 18))

    future = draft(client, bill["id"], [(bill["rice"], "1", "1", "0")], receipt_date="2026-11-19")
    assert future.status_code == 422
    assert "future" in future.json()["detail"]

    undated = client.post(f"{BILLS}{bill['id']}/receipts", json={"items": [
        {"purchase_item_id": bill["rice"], "quantity_received": "1", "quantity_accepted": "1"}]})
    assert undated.json()["receipt_date"] == "2026-11-18"


def test_every_receipt_step_is_audited(client, db, bill):
    first = draft(client, bill["id"], [(bill["rice"], "2", "2", "0")]).json()
    second = draft(client, bill["id"], [(bill["rice"], "2", "2", "0")]).json()
    client.put(f"/api/receipts/{first['id']}", json={"items": [
        {"purchase_item_id": bill["rice"], "quantity_received": "3", "quantity_accepted": "3"}]})
    client.post(f"/api/receipts/{first['id']}/accept")
    client.post(f"/api/receipts/{second['id']}/cancel", json={"reason": "Duplicate entry"})

    actions = sorted(a for (a,) in db.query(AuditLog.action).filter_by(entity_type="GOODS_RECEIPT"))
    assert actions == ["ACCEPT", "CANCEL", "CREATE", "CREATE", "UPDATE"]


# ============================================================
# LISTS
# ============================================================

def test_receipt_list_filters_and_pages(client, world, bill):
    ids = [draft(client, bill["id"], [(bill["rice"], "1", "1", "0")],
                 receipt_date=f"2026-11-0{n}").json()["id"] for n in range(1, 6)]
    client.post(f"/api/receipts/{ids[0]}/accept")

    page = client.get("/api/receipts", params={"page_size": 2}).json()
    assert (page["total"], page["total_pages"], len(page["items"])) == (5, 3, 2)
    assert page["items"][0]["receipt_date"] == "2026-11-05"          # newest first
    assert client.get("/api/receipts", params={"status": "ACCEPTED"}).json()["total"] == 1
    assert client.get("/api/receipts", params={"date_from": "2026-11-04"}).json()["total"] == 2
    assert client.get("/api/receipts", params={"search": "pur03"}).json()["total"] == 5
    assert client.get("/api/receipts", params={"search": "%"}).json()["total"] == 0
    assert client.get("/api/receipts", params={"status": "LOST"}).status_code == 422
    assert client.get("/api/receipts", params={
        "date_from": "2026-11-05", "date_to": "2026-11-01"}).status_code == 422


def test_receivable_bills_list_only_bills_with_quantity_left(client, world, bill):
    assert [b["invoice_number"] for b in client.get("/api/receipts/receivable-bills").json()["items"]] == ["PUR03-1"]
    draft(client, bill["id"], [(bill["rice"], "10", "10", "0"), (bill["dal"], "3", "3", "0")])
    open_bill = client.get("/api/receipts/receivable-bills").json()["items"][0]
    assert (open_bill["line_count"], open_bill["open_line_count"]) == (2, 1)

    draft(client, bill["id"], [(bill["dal"], "1", "1", "0")])
    assert client.get("/api/receipts/receivable-bills").json()["total"] == 0
    assert client.get("/api/receipts/receivable-bills",
                      params={"search": "supplier a"}).json()["total"] == 0


def test_stock_movement_log_filters_and_names(client, world, bill, dal):
    receipt = draft(client, bill["id"], [(bill["rice"], "6", "6", "0"),
                                         (bill["dal"], "4", "4", "0")]).json()
    client.post(f"/api/receipts/{receipt['id']}/accept")

    log = client.get("/api/stock-movements").json()
    assert log["total"] == 2
    assert {m["item_name"] for m in log["items"]} == {"Rice", "Toor Dal"}
    assert all(m["movement_type"] == "RECEIPT" and m["created_by_name"] == world.a.admin.full_name
               and m["supplier_name"] == world.a.supplier.name for m in log["items"])
    assert client.get("/api/stock-movements", params={"item_id": dal.id}).json()["total"] == 1
    assert client.get("/api/stock-movements", params={"movement_type": "issue"}).json()["total"] == 0
    assert client.get("/api/stock-movements", params={"page_size": 1}).json()["total_pages"] == 2
    # The original endpoint still returns its plain list.
    assert len(client.get("/api/stock/movements").json()) == 2


# ============================================================
# PERMISSIONS AND CAMPUS ISOLATION
# ============================================================

def test_kitchen_manager_runs_the_whole_receiving_workflow(client, db, world, bill):
    act_as(client, world.a.manager)
    receipt = draft(client, bill["id"], [(bill["rice"], "6", "0", "0")])
    assert receipt.status_code == 201
    receipt_id = receipt.json()["id"]
    assert client.put(f"/api/receipts/{receipt_id}", json={"items": [
        {"purchase_item_id": bill["rice"], "quantity_received": "6",
         "quantity_accepted": "6"}]}).status_code == 200
    assert client.post(f"/api/receipts/{receipt_id}/accept").status_code == 200
    other = draft(client, bill["id"], [(bill["rice"], "1", "1", "0")]).json()
    assert client.post(f"/api/receipts/{other['id']}/cancel",
                       json={"reason": "Not delivered"}).status_code == 200
    assert client.get("/api/receipts/receivable-bills").status_code == 200


def test_staff_needs_explicit_inventory_read_and_cannot_write(client, db, world, bill):
    receipt = draft(client, bill["id"], [(bill["rice"], "6", "6", "0")]).json()
    reads = ["/api/receipts", f"/api/receipts/{receipt['id']}",
             f"{BILLS}{bill['id']}/receiving", "/api/stock-movements"]

    act_as(client, world.a.staff)
    assert {client.get(path).status_code for path in reads} == {403}

    grant(db, world.a.staff, world.a.admin, "inventory.read")
    assert {client.get(path).status_code for path in reads} == {200}
    writes = [
        client.get("/api/receipts/receivable-bills"),
        draft(client, bill["id"], [(bill["rice"], "1", "1", "0")]),
        client.put(f"/api/receipts/{receipt['id']}", json={"items": [
            {"purchase_item_id": bill["rice"], "quantity_received": "1"}]}),
        client.post(f"/api/receipts/{receipt['id']}/accept"),
        client.post(f"/api/receipts/{receipt['id']}/cancel", json={"reason": "x"}),
    ]
    assert {response.status_code for response in writes} == {403}


def test_another_campus_cannot_see_or_change_receipts(client, db, world, bill):
    receipt = draft(client, bill["id"], [(bill["rice"], "6", "6", "0")]).json()

    act_as(client, world.b.admin)
    assert client.get(f"/api/receipts/{receipt['id']}").status_code == 404
    assert client.get(f"{BILLS}{bill['id']}/receiving").status_code == 404
    assert client.put(f"/api/receipts/{receipt['id']}", json={"items": [
        {"purchase_item_id": bill["rice"], "quantity_received": "1"}]}).status_code == 404
    assert client.post(f"/api/receipts/{receipt['id']}/cancel",
                       json={"reason": "x"}).status_code == 404
    assert client.post(f"/api/receipts/{receipt['id']}/accept").status_code == 404
    assert client.get("/api/receipts").json()["total"] == 0
    assert client.get("/api/receipts/receivable-bills").json()["total"] == 0
    # Campus B cannot receive against campus A's bill lines either.
    b_bill = world.b.bill.id
    assert draft(client, b_bill, [(bill["rice"], "1", "1", "0")]).status_code == 404

    act_as(client, world.a.admin)
    client.post(f"/api/receipts/{receipt['id']}/accept")
    act_as(client, world.b.admin)
    assert client.get("/api/stock-movements").json()["total"] == 0
