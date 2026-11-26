"""
PUR04 / AT08: Excel and PDF exports of the purchases-versus-payments report.

Every file must carry exactly the figures, period and filters the screen
shows for the same request (both are built by build_purchases_vs_payments),
follow the report's read permission and campus, and be written to the
audit log.

Excel files are read back with the standard library (zipfile and XML);
PDFs with pypdf (approved for tests). Self-contained: in-memory SQLite and
no project conftest:

    pytest --noconftest tests/test_pur04_exports.py
"""

import io
import re
import zipfile
from decimal import Decimal
from xml.etree import ElementTree

import pytest
from pypdf import PdfReader

from app.core.config import settings
from app.models import AuditLog, StaffAccessAssignment
from app.services.report_exports import format_balance, format_inr

from tests.test_operational_authority import (  # noqa: F401 (fixtures)
    _campus,
    act_as,
    client,
    db,
    grant,
    world,
)
from tests.test_pur04_bills_and_report import (  # noqa: F401 (fixture)
    ledger,
    record_ledger_payments,
    report,
)

EXPORT = "/api/reports/purchases-vs-payments/export"
PERIOD = {"date_from": "2026-11-01", "date_to": "2026-11-15"}
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def export(client, fmt, **params):
    return client.post(EXPORT, json={"format": fmt, **PERIOD, **params})


def screen(client, **params):
    response = report(client, PERIOD["date_from"], PERIOD["date_to"], **params)
    assert response.status_code == 200, response.text
    return response.json()


# ------------------------------------------------------------
# Reading the files back
# ------------------------------------------------------------

def read_xlsx(content: bytes) -> dict[str, list[list]]:
    """Sheet name → rows of cell values (str or Decimal), by column."""
    book = zipfile.ZipFile(io.BytesIO(content))
    strings = [
        "".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t"))
        for si in ElementTree.fromstring(book.read("xl/sharedStrings.xml"))
    ] if "xl/sharedStrings.xml" in book.namelist() else []

    workbook = ElementTree.fromstring(book.read("xl/workbook.xml"))
    names = [s.get("name") for s in workbook.find("m:sheets", NS)]
    sheets = {}
    for index, name in enumerate(names, start=1):
        root = ElementTree.fromstring(book.read(f"xl/worksheets/sheet{index}.xml"))
        rows = []
        for row in root.iter(f"{{{NS['m']}}}row"):
            cells = {}
            for cell in row.findall("m:c", NS):
                column = re.match(r"[A-Z]+", cell.get("r")).group()
                value = cell.find("m:v", NS)
                if value is None:
                    continue
                cells[ord(column) - ord("A")] = (
                    strings[int(value.text)] if cell.get("t") == "s"
                    else Decimal(value.text)
                )
            width = max(cells) + 1 if cells else 0
            rows.append([cells.get(i) for i in range(width)])
        sheets[name] = rows
    return sheets


def xlsx_number_formats(content: bytes) -> list[str]:
    styles = ElementTree.fromstring(zipfile.ZipFile(io.BytesIO(content)).read("xl/styles.xml"))
    return [f.get("formatCode") for f in styles.iter(f"{{{NS['m']}}}numFmt")]


def pdf_text(content: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(content)).pages)


def pdf_fonts(content: bytes) -> set[str]:
    fonts = set()
    for page in PdfReader(io.BytesIO(content)).pages:
        for font in page["/Resources"]["/Font"].values():
            fonts.add(str(font.get_object()["/BaseFont"]))
    return fonts


def row_named(rows, name):
    return next(row for row in rows if row and row[0] == name)


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


# ============================================================
# CONTENTS MATCH THE SCREEN
# ============================================================

@pytest.mark.parametrize("role", ["admin", "manager"])
def test_excel_export_matches_the_screen(client, world, ledger, role):
    record_ledger_payments(client, world, ledger)
    act_as(client, getattr(world.a, role))
    expected = screen(client)

    response = export(client, "xlsx")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == XLSX_TYPE
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-disposition"] == (
        'attachment; filename="purchases-vs-payments_2026-11-01_2026-11-15.xlsx"'
    )

    sheets = read_xlsx(response.content)
    assert list(sheets) == ["Report", "Payment methods"]
    rows = sheets["Report"]
    assert rows[0][0] == "Purchases vs payments"
    assert row_named(rows, "Campus")[1] == "Campus A"
    assert row_named(rows, "Period")[1] == "01 Nov 2026 – 15 Nov 2026"
    assert row_named(rows, "Supplier")[1] == "All suppliers"
    assert row_named(rows, "Currency")[1] == "INR (₹)"
    assert row_named(rows, "Generated")[1].endswith(f"by {getattr(world.a, role).full_name}")

    for supplier in expected["suppliers"]:
        assert row_named(rows, supplier["supplier_name"])[1:8] == [
            money(supplier["opening_balance"]), supplier["bill_count"],
            money(supplier["billed"]), supplier["payment_count"],
            money(supplier["paid"]), money(supplier["paid_cash"]),
            money(supplier["closing_balance"]),
        ]
    totals = expected["totals"]
    assert row_named(rows, "Total")[1:8] == [
        money(totals["opening_balance"]), totals["bill_count"], money(totals["billed"]),
        totals["payment_count"], money(totals["paid"]), money(totals["paid_cash"]),
        money(totals["closing_balance"]),
    ]
    assert row_named(rows, "Purchase expenditure (bills dated in the period)")[1:3] == [
        totals["bill_count"], money(totals["billed"]),
    ]
    assert row_named(rows, "Owed at end")[2] == money(totals["closing_balance"])

    methods = sheets["Payment methods"]
    for entry in totals["paid_by_method"]:
        label = {"CASH": "Cash", "BANK_TRANSFER": "Bank transfer", "UPI": "UPI",
                 "CHEQUE": "Cheque", "OTHER": "Other"}[entry["payment_method"]]
        assert row_named(methods, label)[1:3] == [entry["payment_count"], money(entry["amount"])]
    assert row_named(methods, "Total paid")[1:3] == [totals["payment_count"], money(totals["paid"])]

    assert any("₹" in code for code in xlsx_number_formats(response.content))


@pytest.mark.parametrize("role", ["admin", "manager"])
def test_pdf_export_matches_the_screen(client, world, ledger, role):
    record_ledger_payments(client, world, ledger)
    act_as(client, getattr(world.a, role))
    expected = screen(client)

    response = export(client, "pdf")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].endswith(
        'filename="purchases-vs-payments_2026-11-01_2026-11-15.pdf"'
    )
    assert response.content.startswith(b"%PDF")
    text = pdf_text(response.content)

    for expected_text in ["Purchases vs payments", "Campus A",
                          "01 Nov 2026 – 15 Nov 2026", "All suppliers", "INR (₹)",
                          f"by {getattr(world.a, role).full_name}"]:
        assert expected_text in text, expected_text

    # Every page is numbered against the real page count.
    pages = len(PdfReader(io.BytesIO(response.content)).pages)
    for number in range(1, pages + 1):
        assert f"Page {number} of {pages}" in text

    lines = text.splitlines()
    for supplier in expected["suppliers"]:
        start = lines.index(supplier["supplier_name"])
        assert lines[start + 1: start + 8] == [
            format_balance(supplier["opening_balance"]), str(supplier["bill_count"]),
            format_inr(supplier["billed"]), str(supplier["payment_count"]),
            format_inr(supplier["paid"]), format_inr(supplier["paid_cash"]),
            format_balance(supplier["closing_balance"]),
        ]
    totals = expected["totals"]
    start = len(lines) - 1 - lines[::-1].index("Total")
    assert lines[start + 1: start + 8] == [
        format_balance(totals["opening_balance"]), str(totals["bill_count"]),
        format_inr(totals["billed"]), str(totals["payment_count"]),
        format_inr(totals["paid"]), format_inr(totals["paid_cash"]),
        format_balance(totals["closing_balance"]),
    ]
    assert format_inr("1500.00") == "₹1,500.00" and "₹1,500.00" in text
    assert any("NotoSans" in font for font in pdf_fonts(response.content))


def test_exports_apply_the_supplier_filter(client, world, ledger):
    record_ledger_payments(client, world, ledger)
    act_as(client, world.a.admin)
    other_id = ledger["other"].id
    expected = screen(client, supplier_id=other_id)

    xlsx = export(client, "xlsx", supplier_id=other_id)
    pdf = export(client, "pdf", supplier_id=other_id)

    assert xlsx.headers["content-disposition"].endswith(
        'filename="purchases-vs-payments_2026-11-01_2026-11-15_other-a.xlsx"'
    )
    rows = read_xlsx(xlsx.content)["Report"]
    assert row_named(rows, "Supplier")[1] == "Other A"
    assert [row[0] for row in rows if row and row[0] in ("Supplier A", "Other A")] == ["Other A"]
    assert row_named(rows, "Total")[3] == money(expected["totals"]["billed"])

    text = pdf_text(pdf.content)
    assert "Other A" in text and "Supplier A" not in text
    assert format_inr(expected["totals"]["billed"]) in text


def test_empty_period_exports_say_so(client, world):
    act_as(client, world.a.admin)

    for fmt in ("xlsx", "pdf"):
        response = client.post(EXPORT, json={
            "format": fmt, "date_from": "2025-01-01", "date_to": "2025-01-31",
        })
        assert response.status_code == 200, response.text
        body = (
            "\n".join(str(c) for r in read_xlsx(response.content)["Report"] for c in r)
            if fmt == "xlsx" else pdf_text(response.content)
        )
        assert "No bills or payments in this period." in body


# ============================================================
# AUDIT
# ============================================================

def test_every_export_is_audited(client, db, world, ledger):
    record_ledger_payments(client, world, ledger)
    act_as(client, world.a.manager)
    expected = screen(client, supplier_id=ledger["other"].id)

    export(client, "xlsx")
    export(client, "pdf", supplier_id=ledger["other"].id)

    rows = db.query(AuditLog).filter_by(action="EXPORT").order_by(AuditLog.id).all()
    assert [(r.entity_type, r.entity_id, r.user_id, r.campus_id) for r in rows] == [
        ("PURCHASE_REPORT", None, world.a.manager.id, world.a.campus.id),
    ] * 2
    details = rows[1].details
    assert {k: details[k] for k in (
        "report", "format", "file_name", "date_from", "date_to",
        "supplier_id", "supplier_name", "supplier_rows", "billed", "paid",
        "closing_balance")} == {
        "report": "purchases_vs_payments", "format": "pdf",
        "file_name": "purchases-vs-payments_2026-11-01_2026-11-15_other-a.pdf",
        "date_from": "2026-11-01", "date_to": "2026-11-15",
        "supplier_id": ledger["other"].id, "supplier_name": "Other A",
        "supplier_rows": 1,
        "billed": expected["totals"]["billed"], "paid": expected["totals"]["paid"],
        "closing_balance": expected["totals"]["closing_balance"],
    }
    assert details["bytes"] > 0


def test_export_entries_stay_out_of_other_users_activity_feed(client, db, world):
    act_as(client, world.a.admin)
    assert export(client, "pdf").status_code == 200
    feed = client.get("/api/dashboard/overview").json()["activity"]
    assert "PURCHASE_REPORT" in {e["entity_type"] for e in feed}

    for code in ("dashboard.read", "audit.read"):
        grant(db, world.a.staff, world.a.admin, code)
    act_as(client, world.a.staff)
    feed = client.get("/api/dashboard/overview").json()["activity"]
    assert "PURCHASE_REPORT" not in {e["entity_type"] for e in feed}


# ============================================================
# PERMISSIONS, VALIDATION, CSRF AND CAMPUS ISOLATION
# ============================================================

def assignment_rows(db, staff):
    db.expire_all()
    return sorted((r.permission_id, r.is_active, r.assigned_by)
                  for r in db.query(StaffAccessAssignment).filter_by(staff_user_id=staff.id))


def test_exports_follow_the_report_read_permission(client, db, world):
    act_as(client, world.a.staff)
    for fmt in ("xlsx", "pdf"):
        assert export(client, fmt).status_code == 403

    grant(db, world.a.staff, world.a.admin, "purchase_bill.read")
    before = assignment_rows(db, world.a.staff)
    for fmt in ("xlsx", "pdf"):
        assert export(client, fmt).status_code == 200
    assert assignment_rows(db, world.a.staff) == before

    db.query(StaffAccessAssignment).filter_by(
        staff_user_id=world.a.staff.id
    ).update({"is_active": False})
    db.commit()
    for fmt in ("xlsx", "pdf"):
        assert export(client, fmt).status_code == 403

    # Only the two permitted exports were audited.
    assert db.query(AuditLog).filter_by(action="EXPORT").count() == 2


def test_invalid_export_requests_are_refused_and_not_audited(client, db, world):
    act_as(client, world.a.admin)

    for body, status in [
        ({"format": "csv", **PERIOD}, 422),
        ({"format": "pdf", "date_from": "2026-11-15", "date_to": "2026-11-01"}, 422),
        ({"format": "pdf", "date_from": "2026-11-01"}, 422),
        ({"format": "xlsx", **PERIOD, "supplier_id": world.b.supplier.id}, 404),
        ({"format": "xlsx", **PERIOD, "supplier_id": 0}, 422),
    ]:
        assert client.post(EXPORT, json=body).status_code == status, body

    assert db.query(AuditLog).filter_by(action="EXPORT").count() == 0


def test_export_needs_the_csrf_token(client, db, world):
    act_as(client, world.a.admin)

    response = client.post(
        EXPORT, json={"format": "pdf", **PERIOD},
        headers={settings.CSRF_HEADER_NAME: "wrong-token"},
    )

    assert response.status_code == 403
    assert db.query(AuditLog).filter_by(action="EXPORT").count() == 0


def test_exports_are_campus_isolated(client, world, ledger):
    record_ledger_payments(client, world, ledger)
    act_as(client, world.b.admin)

    rows = read_xlsx(export(client, "xlsx").content)["Report"]
    names = {row[0] for row in rows if row}
    assert "Supplier B" in names
    assert not names & {"Supplier A", "Other A"}
    assert row_named(rows, "Campus")[1] == "Campus B"
    assert row_named(rows, "Total")[3] == Decimal("500.00")

    text = pdf_text(export(client, "pdf").content)
    assert "Supplier B" in text and "Supplier A" not in text and "Campus A" not in text
