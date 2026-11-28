"""
Stage 9: dashboard and reports (DASH01–DASH05, AT03, AT07; PROPOSAL.md §5.6,
§5.8). In-memory SQLite with the shared fixtures of test_operational_authority
and the kitchen fixture of test_kitchen_issues (campus A: kg and g with an
explicit g→kg conversion; Rice and Toor Dal; Lunch and Dinner; campus B).
Bills are dated June and July 2026 so the fixture's own November bills do
not mix in.
"""

import io
import zipfile
from datetime import date
from decimal import Decimal

import pytest

from app.core.clock import campus_today
from app.models import AuditLog, Item, Unit
from app.models.daily_headcount import DailyHeadcount
from app.models.purchases import Purchase, PurchaseItem
from app.services import purchase_analytics as pa

from tests.test_kitchen_issues import kitchen  # noqa: F401 (fixture)
from tests.test_meals import created, ok, set_counts
from tests.test_operational_authority import act_as, client, db, grant, world  # noqa: F401 (fixtures)

SPENDING = "/api/analytics/spending"
REPORTS = "/api/reports"


def bill(db, a, day, invoice, lines, supplier=None, discount="0", extra="0"):
    """lines: [(item, qty, unit, rate)]"""
    subtotal = sum((Decimal(q) * Decimal(r)).quantize(Decimal("0.01")) for _i, q, _u, r in lines)
    row = Purchase(campus_id=a.campus.id, supplier_id=(supplier or a.supplier).id, invoice_number=invoice,
                   purchase_date=day, subtotal=subtotal, discount=Decimal(discount), extra_charges=Decimal(extra),
                   grand_total=subtotal - Decimal(discount) + Decimal(extra), status="DRAFT", created_by=a.admin.id)
    db.add(row)
    db.flush()
    for item, qty, unit, rate in lines:
        db.add(PurchaseItem(campus_id=a.campus.id, purchase_id=row.id, item_id=item.id, quantity=Decimal(qty),
                            unit_id=unit.id, unit_rate=Decimal(rate),
                            line_total=(Decimal(qty) * Decimal(rate)).quantize(Decimal("0.01"))))
    db.commit()
    return row


@pytest.fixture
def spend(db, kitchen):
    """June: Rice 10 kg @ 50 and 5000 g @ 0.06 (15 kg, ₹800); July: Rice 20 kg
    @ 60 (₹1,200, discount ₹10 on the bill) and Toor Dal 4 kg @ 120 (new);
    a Rice line in bags (no conversion) in July."""
    a = kitchen.a
    bag = Unit(campus_id=a.campus.id, name="Bag", symbol="bag", dimension="count")
    db.add(bag)
    db.commit()
    bill(db, a, date(2026, 6, 5), "JUN-1", [(a.item, "10", a.kg, "50")])
    bill(db, a, date(2026, 6, 20), "JUN-2", [(a.item, "5000", a.g, "0.06")])
    bill(db, a, date(2026, 7, 4), "JUL-1", [(a.item, "20", a.kg, "60"), (a.dal, "4", a.kg, "120")], discount="10")
    bill(db, a, date(2026, 7, 9), "JUL-2", [(a.item, "2", bag, "500")])
    a.bag = bag
    return kitchen


# ============================================================
# CALCULATIONS (DASH02–DASH04, AT07)
# ============================================================

def test_comparison_periods_use_matching_elapsed_days_and_full_months():
    elapsed = pa.comparison_periods(date(2026, 11, 1), date(2026, 11, 24), "elapsed")
    assert elapsed["previous"] == {"date_from": "2026-10-01", "date_to": "2026-10-24", "days": 24}
    assert elapsed["current"]["days"] == elapsed["previous"]["days"] == 24
    march = pa.comparison_periods(date(2026, 3, 1), date(2026, 3, 31), "elapsed")
    assert march["previous"] == {"date_from": "2026-02-01", "date_to": "2026-02-28", "days": 28}
    full = pa.comparison_periods(date(2026, 11, 1), date(2026, 11, 24), "full")
    assert full["current"]["date_to"] == "2026-11-30" and full["previous"] == {
        "date_from": "2026-10-01", "date_to": "2026-10-31", "days": 31}
    previous = pa.comparison_periods(date(2026, 11, 11), date(2026, 11, 20), "previous")
    assert previous["previous"] == {"date_from": "2026-11-01", "date_to": "2026-11-10", "days": 10}
    two_months = pa.comparison_periods(date(2026, 10, 1), date(2026, 11, 26), "elapsed")
    assert two_months["previous"]["date_to"] < two_months["current"]["date_from"]


def test_percentages_are_not_comparable_without_a_previous_value():
    assert pa.percent_change(Decimal("150"), Decimal("100")) == "50.0"
    assert pa.percent_change(Decimal("5"), Decimal("0")) is None
    assert pa.percent_change(Decimal("5"), None) is None


def test_at07_weighted_prices_and_price_quantity_effects(client, db, spend):
    a = spend.a
    act_as(client, a.manager)
    data = ok(client.get(SPENDING, params={"date_from": "2026-07-01", "date_to": "2026-07-31", "compare": "full"}))
    assert data["periods"]["previous"] == {"date_from": "2026-06-01", "date_to": "2026-06-30", "days": 30}
    rice = next(r for r in data["items"] if r["item_name"] == "Rice")
    # Matching units: 5000 g counted as 5 kg; the bag line has no conversion.
    assert (rice["previous_quantity"], rice["current_quantity"]) == ("15.000", "20.000")
    assert (rice["previous_price"], rice["current_price"]) == ("53.3333", "60.0000")
    assert rice["price_change_percent"] == "12.5" and rice["status"] == "COMPARABLE"
    assert (rice["price_effect"], rice["quantity_effect"]) == ("133.33", "266.67")
    assert Decimal(rice["price_effect"]) + Decimal(rice["quantity_effect"]) == Decimal(rice["value_change"]) == Decimal("400.00")
    assert rice["excluded_lines"] == 1
    dal = next(r for r in data["items"] if r["item_name"] == "Toor Dal")
    assert dal["status"] == "NEW" and dal["price_effect"] is None and dal["quantity_effect"] == "480.00"
    assert dal["value_change_percent"] is None and dal["price_change_percent"] is None  # "Not comparable"
    assert [r["item_name"] for r in data["top_price_increases"]] == ["Rice"]
    totals = data["totals"]
    assert totals["basis"] == "bill grand totals"
    assert (totals["previous"], totals["current"]) == ("800.00", "2670.00")  # 1200 + 480 − 10 + 1000 (bags)
    assert totals["current_bills"]["discount"] == "10.00" and totals["change_percent"] == "233.8"
    assert totals["excluded_lines"] == 1
    july = next(m for m in data["monthly"] if m["month"] == "2026-07")
    assert july["expenditure"] == "2670.00" and len(data["monthly"]) == 12
    chosen = ok(client.get(SPENDING, params={"date_from": "2026-07-01", "date_to": "2026-07-31", "compare": "full",
                                             "item_id": a.item.id}))
    assert chosen["totals"]["basis"].startswith("line totals")
    rice_july = next(m for m in chosen["monthly"] if m["month"] == "2026-07")
    assert (rice_july["quantity"], rice_july["average_price"]) == ("20.000", "60.0000")


def test_spending_needs_bill_read_and_is_campus_isolated(client, db, spend):
    a, b = spend.a, spend.b
    params = {"date_from": "2026-07-01", "date_to": "2026-07-31"}
    act_as(client, a.staff)
    assert client.get(SPENDING, params=params).status_code == 403
    assert client.get("/api/analytics/transactions", params=params).status_code == 403
    grant(db, a.staff, a.admin, "purchase_bill.read")
    assert ok(client.get(SPENDING, params=params))["totals"]["current"] == "2670.00"
    act_as(client, b.admin)
    assert ok(client.get(SPENDING, params=params))["totals"]["current"] == "0.00"
    assert client.get(SPENDING, params={**params, "item_id": a.item.id}).status_code == 404
    assert client.get(SPENDING, params={"date_from": "2026-07-31", "date_to": "2026-07-01"}).status_code == 422


def test_dash05_drilldown_lists_the_source_bill_lines(client, db, spend):
    a = spend.a
    act_as(client, a.admin)
    lines = ok(client.get("/api/analytics/transactions", params={
        "date_from": "2026-07-01", "date_to": "2026-07-31", "item_id": a.item.id}))
    assert lines["total"] == 2 and lines["line_total"] == "2200.00"
    first = lines["items"][0]
    assert first["invoice_number"] == "JUL-1" and first["attachment_count"] == 0
    assert (first["quantity"], first["standard_quantity"], first["standard_unit_symbol"]) == ("20.000", "20.000", "kg")
    assert lines["items"][1]["standard_quantity"] is None  # bags: no conversion


# ============================================================
# REPORTS (§5.8, AT03)
# ============================================================

def test_at03_monthly_item_purchase_report(client, db, spend):
    a = spend.a
    chicken = Item(campus_id=a.campus.id, name="Chicken", category_id=a.category.id, standard_unit_id=a.kg.id,
                   minimum_stock=0)
    db.add(chicken)
    db.commit()
    bill(db, a, date(2026, 8, 3), "AUG-1", [(chicken, "5", a.kg, "200"), (chicken, "3000", a.g, "0.2")])
    bill(db, a, date(2026, 8, 3), "AUG-2", [(chicken, "4", a.kg, "210")])
    bill(db, a, date(2026, 8, 10), "AUG-3", [(chicken, "6", a.kg, "205"), (chicken, "1", a.bag, "300")])
    act_as(client, a.manager)
    report = ok(client.get(f"{REPORTS}/item_purchases", params={"date_from": "2026-08-01", "date_to": "2026-08-31",
                                                                 "item_id": chicken.id}))
    totals = {t["label"]: t["value"] for t in report["totals"]}
    # Interim Q4 rule: one bill = one transaction, however many chicken lines.
    assert totals["Transactions (bills)"] == "3"
    assert totals["Distinct purchase days"] == "2"
    assert totals["Total quantity (kg)"] == "18.000"
    assert totals["Total purchase expenditure (line totals)"] == "3970.00"  # 1000 + 600 + 840 + 1230 + 300 (bag)
    row = report["rows"][0]
    assert (row["transactions"], row["purchase_days"], row["lines"], row["excluded_lines"]) == (3, 2, 5, 1)
    assert row["average_price"] == "203.8889"  # 3670 ÷ 18 kg (bag line excluded)
    assert report["period"] == {"date_from": "2026-08-01", "date_to": "2026-08-31"}
    assert {"label": "Item", "value": "Chicken"} in report["filters"]
    assert any("Q4" in note for note in report["notes"])
    for fmt, magic in (("xlsx", b"PK"), ("pdf", b"%PDF")):
        response = client.post(f"{REPORTS}/item_purchases/export", json={
            "format": fmt, "date_from": "2026-08-01", "date_to": "2026-08-31", "item_id": chicken.id})
        assert response.status_code == 200 and response.content.startswith(magic), response.text
        assert "item-purchases_2026-08-01_2026-08-31_chicken" in response.headers["content-disposition"]
    sheet = zipfile.ZipFile(io.BytesIO(client.post(f"{REPORTS}/item_purchases/export", json={
        "format": "xlsx", "date_from": "2026-08-01", "date_to": "2026-08-31", "item_id": chicken.id}).content))
    assert "Chicken" in sheet.read("xl/sharedStrings.xml").decode()
    assert db.query(AuditLog).filter_by(entity_type="REPORT", action="EXPORT").count() == 3


def test_category_report_keeps_bill_charges_separate(client, db, spend):
    a = spend.a
    act_as(client, a.admin)
    report = ok(client.get(f"{REPORTS}/category_expenses", params={"date_from": "2026-07-01", "date_to": "2026-07-31"}))
    totals = {t["label"]: t["value"] for t in report["totals"]}
    assert totals["Line totals"] == "2680.00"
    assert totals["Bill discounts (not allocated)"] == "-10.00"
    assert totals["Purchase expenditure (bill grand totals)"] == "2670.00"
    assert report["rows"][0]["share"] == "100.0"


def test_every_report_runs_for_managers_and_respects_permissions(client, db, spend):
    a = spend.a
    act_as(client, a.manager)
    catalog = ok(client.get(f"{REPORTS}/catalog"))["items"]
    keys = {r["key"] for r in catalog if not r["href"]}
    assert {"purchase_transactions", "category_expenses", "item_purchases", "price_comparison", "supplier_balances",
            "stock_movements", "low_stock", "ingredient_usage", "stock_differences", "meal_distribution", "leftovers",
            "planned_vs_actual"} == keys
    for key in keys:
        response = client.get(f"{REPORTS}/{key}", params={"date_from": "2026-06-01", "date_to": "2026-07-31"})
        assert response.status_code == 200, (key, response.text)
        body = response.json()
        assert body["columns"] and "totals" in body and body["campus"]["id"] == a.campus.id
    movements = ok(client.get(f"{REPORTS}/stock_movements", params={"date_from": "2026-01-01", "date_to": campus_today().isoformat()}))
    assert movements["row_count"] == 1 and movements["rows"][0]["unit"] == "kg"  # the fixture's 20 kg opening
    assert client.get(f"{REPORTS}/purchase_transactions").status_code == 422
    assert client.get(f"{REPORTS}/purchase_transactions", params={"date_from": "2025-01-01", "date_to": "2026-07-31"}).status_code == 422
    assert client.get(f"{REPORTS}/no_such_report", params={"date_from": "2026-07-01", "date_to": "2026-07-31"}).status_code == 404

    grant(db, a.staff, a.admin, "meal.read")
    act_as(client, a.staff)
    assert client.get(f"{REPORTS}/catalog").status_code == 403         # Reports need report.read (27 Nov 2026)
    grant(db, a.staff, a.admin, "report.read")
    staff_keys = {r["key"] for r in ok(client.get(f"{REPORTS}/catalog"))["items"]}
    assert staff_keys == {"meal_distribution", "leftovers"}
    assert client.get(f"{REPORTS}/purchase_transactions", params={"date_from": "2026-07-01", "date_to": "2026-07-31"}).status_code == 403
    assert client.post(f"{REPORTS}/item_purchases/export", json={"format": "pdf", "date_from": "2026-07-01",
                                                                 "date_to": "2026-07-31"}).status_code == 403
    act_as(client, spend.b.admin)
    other = ok(client.get(f"{REPORTS}/purchase_transactions", params={"date_from": "2026-06-01", "date_to": "2026-07-31"}))
    assert other["row_count"] == 0
    assert client.get(f"{REPORTS}/item_purchases", params={"date_from": "2026-06-01", "date_to": "2026-07-31",
                                                            "item_id": a.item.id}).status_code == 404


# ============================================================
# HOME DASHBOARD
# ============================================================

def test_dashboard_headcount_comes_from_meal_records(client, db, spend):
    a = spend.a
    act_as(client, a.admin)
    db.add(DailyHeadcount(campus_id=a.campus.id, headcount_date=campus_today(), student_count=999))
    db.commit()
    empty = ok(client.get("/api/dashboard/overview"))["headcount"]
    assert empty["today"] is None and empty["source"] == "meal_records"
    lunch = created(client, a, session=a.lunch, counts=(120, 10, 5))
    ok(set_counts(client, lunch, expected=(120, 10, 5), actual=(110, 9, 4)))
    created(client, a, session=a.dinner, counts=(100, 5, 0))
    data = ok(client.get("/api/dashboard/overview"))
    head = data["headcount"]
    assert head["today"] == 123 and head["today_basis"] == "actual" and data["kpis"]["headcount_today"] == 123
    assert sorted((s["meal_session_name"], s["expected"], s["actual"]) for s in head["sessions"]) == [
        ("Dinner", 105, None), ("Lunch", 135, 123)]
    assert head["trend"][-1]["count"] == 123
    assert data["meals"]["open_count"] == 2
    act_as(client, spend.b.admin)
    assert ok(client.get("/api/dashboard/overview"))["headcount"]["today"] is None


def test_dashboard_sections_follow_permissions(client, db, spend):
    a = spend.a
    act_as(client, a.manager)
    data = ok(client.get("/api/dashboard/overview"))
    assert {"stock", "meals", "planning", "outsourced", "kitchen", "counts", "spending"} <= set(data)
    assert "planned_cost_this_month" in data["outsourced"]
    assert data["stock"]["items_tracked"] == 2 and data["stock"]["below_minimum"] == 0
    for code in ("dashboard.read", "outsourced_food.read"):
        grant(db, a.staff, a.admin, code)
    act_as(client, a.staff)
    staff = ok(client.get("/api/dashboard/overview"))
    assert "outsourced" in staff and "planned_cost_this_month" not in staff["outsourced"]
    assert not ({"spending", "stock", "planning", "meals", "headcount", "purchases"} & set(staff))
