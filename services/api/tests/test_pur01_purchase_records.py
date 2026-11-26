"""
PUR01 — Record Purchases and Bill Attachments. Tests grouped by the five
acceptance criteria in the approved proposal:

1. Authorised users record purchase date, supplier, invoice number, item,
   category, quantity, unit, unit rate, total and remarks.
2. A bill may contain multiple item lines.
3. Users can attach bill images or documents (ADR-008; rules approved
   18 November 2026: PDF/JPEG/PNG/WEBP by content, 10 MB, 10 per bill,
   permanent, upload with purchase_bill.create, read with .read).
4. Possible duplicate supplier invoice numbers are identified and flagged
   for review (exact duplicates stay refused; review by purchase_bill.update).
5. Purchase records preserve their original transaction details.

Self-contained: in-memory SQLite, temporary file storage, no project
conftest:

    pytest --noconftest tests/test_pur01_purchase_records.py
"""

import hashlib
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.api.routes import purchase_attachments
from app.core.config import settings
from app.main import app
from app.models import AuditLog, StaffAccessAssignment, Supplier
from app.models.purchases import Purchase, PurchaseAttachment, PurchaseItem
from app.services.attachment_storage import (
    LocalAttachmentStorage,
    get_attachment_storage,
)

from tests.test_operational_authority import (  # noqa: F401 (fixtures)
    act_as,
    client,
    db,
    grant,
    world,
)

BILLS = "/api/purchases/"

PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj << /Type /Catalog >> endobj\n" + b"0" * 200
PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(64)) * 4
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + bytes(range(100)) * 3
WEBP = b"RIFF" + (300).to_bytes(4, "little") + b"WEBPVP8 " + bytes(range(90)) * 3


@pytest.fixture
def storage(tmp_path):
    store = LocalAttachmentStorage(tmp_path / "bill-attachments")
    app.dependency_overrides[get_attachment_storage] = lambda: store
    yield store
    app.dependency_overrides.pop(get_attachment_storage, None)


def stored_files(store):
    return sorted(p for p in store.root.rglob("*") if p.is_file()) if store.root.exists() else []


def line(place, quantity="2.5", rate="45.50", **extra):
    return {"item_id": place.item.id, "quantity": quantity,
            "unit_id": place.kg.id, "unit_rate": rate, **extra}


def create_bill(client, place, invoice, supplier=None, **extra):
    response = client.post(BILLS, json={
        "supplier_id": (supplier or place.supplier).id, "invoice_number": invoice,
        "purchase_date": "2026-11-03", "items": [line(place)], **extra,
    })
    assert response.status_code == 201, response.text
    return response.json()


def upload(client, bill_id, data, name="bill.pdf", remarks=None, claimed="application/pdf"):
    return client.post(
        f"{BILLS}{bill_id}/attachments",
        files={"file": (name, data, claimed)},
        data={"remarks": remarks} if remarks is not None else None,
    )


# ============================================================
# 1. EVERY REQUIRED FIELD IS RECORDED
# ============================================================

def test_criterion_1_every_required_field_is_recorded(client, world):
    act_as(client, world.a.manager)

    bill = create_bill(client, world.a, "PUR01-C1", remarks="Monthly rice",
                       items=[line(world.a, "2.5", "45.50", remarks="Sona masoori")])
    detail = client.get(f"{BILLS}{bill['id']}").json()

    assert detail["purchase_date"] == "2026-11-03"
    assert (detail["supplier_id"], detail["supplier_name"]) == (world.a.supplier.id, "Supplier A")
    assert detail["invoice_number"] == "PUR01-C1"
    assert detail["remarks"] == "Monthly rice"
    assert detail["grand_total"] == "113.75"
    item = detail["items"][0]
    assert (item["item_id"], item["item_name"], item["category_name"]) == (
        world.a.item.id, "Rice", "Grains")
    assert Decimal(str(item["quantity"])) == Decimal("2.5")
    assert (item["unit_id"], item["unit_symbol"]) == (world.a.kg.id, "kg")
    assert Decimal(item["unit_rate"]) == Decimal("45.50")
    assert item["line_total"] == "113.75"
    assert item["remarks"] == "Sona masoori"


# ============================================================
# 2. A BILL MAY CONTAIN MULTIPLE ITEM LINES
# ============================================================

def test_criterion_2_a_bill_holds_multiple_lines(client, db, world):
    act_as(client, world.a.admin)

    bill = create_bill(client, world.a, "PUR01-C2", items=[
        line(world.a, "1", "10"), line(world.a, "2", "20"), line(world.a, "3", "30"),
    ])

    assert [l["line_total"] for l in bill["items"]] == ["10.00", "40.00", "90.00"]
    assert db.query(PurchaseItem).filter_by(purchase_id=bill["id"]).count() == 3
    assert bill["grand_total"] == "140.00"


# ============================================================
# 3. BILL ATTACHMENTS
# ============================================================

@pytest.mark.parametrize("role", ["admin", "manager"])
@pytest.mark.parametrize("data, expected_type, extension", [
    (PDF, "application/pdf", "pdf"),
    (JPEG, "image/jpeg", "jpg"),
    (PNG, "image/png", "png"),
    (WEBP, "image/webp", "webp"),
])
def test_allowed_files_attach_and_read_back_exactly(
    client, world, storage, role, data, expected_type, extension
):
    actor = getattr(world.a, role)
    act_as(client, actor)
    bill = create_bill(client, world.a, f"ATT-{extension}")

    # The browser's claimed type and the name do not matter; content does.
    response = upload(client, bill["id"], data, name=f"Scan 01.{extension}",
                      remarks="Original bill", claimed="application/octet-stream")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["content_type"] == expected_type
    assert body["size_bytes"] == len(data)
    assert body["checksum_sha256"] == hashlib.sha256(data).hexdigest()
    assert body["original_filename"] == f"Scan 01.{extension}"
    assert body["remarks"] == "Original bill"
    assert (body["uploaded_by"], body["uploaded_by_name"]) == (actor.id, actor.full_name)
    assert "object_key" not in body          # storage keys are never exposed

    files = stored_files(storage)
    assert len(files) == 1 and files[0].read_bytes() == data
    assert files[0].suffix == f".{extension}"
    assert len(files[0].stem) == 32           # 128-bit random, not guessable

    download = client.get(f"{BILLS}{bill['id']}/attachments/{body['id']}/file")
    assert download.status_code == 200
    assert download.content == data
    assert download.headers["content-type"].startswith(expected_type)
    assert download.headers["x-content-type-options"] == "nosniff"
    assert download.headers["content-security-policy"] == "sandbox"
    assert download.headers["cache-control"] == "private, no-store"
    assert download.headers["content-disposition"].startswith("attachment;")
    assert "filename*=UTF-8''Scan%2001." in download.headers["content-disposition"]

    inline = client.get(f"{BILLS}{bill['id']}/attachments/{body['id']}/file?disposition=inline")
    assert inline.headers["content-disposition"].startswith("inline;")


@pytest.mark.parametrize("data, name", [
    (b"<html><script>alert(1)</script></html>", "bill.pdf"),
    (b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>', "bill.png"),
    (b"MZ\x90\x00\x03\x00\x00\x00", "bill.jpg"),
    (b"GIF89a\x01\x00\x01\x00", "bill.gif"),
    (b"PK\x03\x04 a zip or docx", "bill.docx"),
])
def test_other_file_types_are_refused_by_content(client, db, world, storage, data, name):
    act_as(client, world.a.admin)
    bill = create_bill(client, world.a, "ATT-BAD")

    response = upload(client, bill["id"], data, name=name)

    assert response.status_code == 415, response.text
    assert db.query(PurchaseAttachment).count() == 0
    assert stored_files(storage) == []


def test_empty_and_oversized_files_are_refused(client, db, world, storage):
    act_as(client, world.a.admin)
    bill = create_bill(client, world.a, "ATT-SIZE")

    assert upload(client, bill["id"], b"").status_code == 422
    just_over = PDF + b"0" * (10 * 1024 * 1024 + 1 - len(PDF))
    assert upload(client, bill["id"], just_over).status_code == 413
    # Far over: refused from the declared length, before the body is read.
    far_over = PDF + b"0" * (12 * 1024 * 1024)
    assert upload(client, bill["id"], far_over).status_code == 413
    exactly = PDF + b"0" * (10 * 1024 * 1024 - len(PDF))
    assert upload(client, bill["id"], exactly).status_code == 201

    assert db.query(PurchaseAttachment).count() == 1
    assert len(stored_files(storage)) == 1


def test_at_most_ten_attachments_per_bill(client, db, world, storage):
    act_as(client, world.a.manager)
    bill = create_bill(client, world.a, "ATT-TEN")

    for n in range(10):
        assert upload(client, bill["id"], PDF + bytes([n])).status_code == 201
    eleventh = upload(client, bill["id"], PDF + b"eleven")

    assert eleventh.status_code == 409
    assert "at most 10" in eleventh.json()["detail"]
    assert len(stored_files(storage)) == 10


def test_the_same_file_attaches_to_a_bill_only_once(client, db, world, storage):
    act_as(client, world.a.manager)
    first = create_bill(client, world.a, "ATT-SAME-1")
    second = create_bill(client, world.a, "ATT-SAME-2")

    assert upload(client, first["id"], PNG).status_code == 201
    again = upload(client, first["id"], PNG, name="renamed.png")
    assert again.status_code == 409
    # The same scan on a different bill is allowed.
    assert upload(client, second["id"], PNG).status_code == 201
    assert len(stored_files(storage)) == 2


def test_attachments_are_listed_with_limits(client, world, storage):
    act_as(client, world.a.admin)
    bill = create_bill(client, world.a, "ATT-LIST")
    upload(client, bill["id"], PDF, name="invoice.pdf")
    upload(client, bill["id"], JPEG, name="photo.jpg", claimed="image/jpeg")

    body = client.get(f"{BILLS}{bill['id']}/attachments").json()

    assert [i["original_filename"] for i in body["items"]] == ["invoice.pdf", "photo.jpg"]
    # Upload times carry their UTC offset, so browsers show them in local time.
    assert all(datetime.fromisoformat(i["uploaded_at"]).utcoffset() == timedelta(0)
               for i in body["items"])
    assert body["limits"] == {
        "max_files": 10, "max_bytes": 10 * 1024 * 1024,
        "content_types": ["application/pdf", "image/jpeg", "image/png", "image/webp"],
    }


def test_attachments_are_permanent(client, world, storage):
    act_as(client, world.a.admin)
    bill = create_bill(client, world.a, "ATT-KEEP")
    attachment = upload(client, bill["id"], PDF).json()
    base = f"{BILLS}{bill['id']}/attachments/{attachment['id']}"

    # The API offers no way to delete or replace an attachment: no route
    # with a writing method mentions attachments, except the upload itself.
    for path, operations in app.openapi()["paths"].items():
        if "attachments" in path:
            assert set(operations) & {"put", "patch", "delete"} == set(), path
            if "{attachment_id}" in path:
                assert set(operations) == {"get"}, path

    for method, url in [("delete", base), ("put", base), ("patch", base),
                        ("delete", f"{base}/file"), ("put", f"{base}/file"),
                        ("patch", f"{base}/file")]:
        assert getattr(client, method)(url).status_code in (404, 405), (method, url)
    assert len(stored_files(storage)) == 1
    assert client.get(f"{base}/file").content == PDF


def test_upload_is_audited_with_its_details(client, db, world, storage):
    act_as(client, world.a.manager)
    bill = create_bill(client, world.a, "ATT-AUDIT")

    attachment = upload(client, bill["id"], PDF, name="bill.pdf", remarks="Front page").json()

    row = db.query(AuditLog).filter_by(
        entity_type="PURCHASE_ATTACHMENT", entity_id=attachment["id"]).one()
    assert (row.action, row.user_id, row.campus_id) == (
        "CREATE", world.a.manager.id, world.a.campus.id)
    assert row.details == {
        "purchase_id": bill["id"], "invoice_number": "ATT-AUDIT",
        "supplier_id": world.a.supplier.id, "original_filename": "bill.pdf",
        "content_type": "application/pdf", "size_bytes": len(PDF),
        "checksum_sha256": hashlib.sha256(PDF).hexdigest(), "remarks": "Front page",
    }


def test_a_failed_save_leaves_no_file_behind(client, db, world, storage, monkeypatch):
    act_as(client, world.a.admin)
    bill = create_bill(client, world.a, "ATT-ROLLBACK")

    def failing_audit(*args, **kwargs):
        raise RuntimeError("audit store unavailable")

    monkeypatch.setattr(purchase_attachments, "record_audit", failing_audit)
    with pytest.raises(RuntimeError):
        upload(client, bill["id"], PDF)

    db.expire_all()
    assert db.query(PurchaseAttachment).count() == 0
    assert stored_files(storage) == []


def test_a_committed_upload_keeps_its_file_if_reloading_fails(
    client, db, world, storage, monkeypatch
):
    act_as(client, world.a.admin)
    bill = create_bill(client, world.a, "ATT-AFTER-COMMIT")
    original_refresh = Session.refresh

    def refresh_fails_for_attachments(self, instance, *args, **kwargs):
        if isinstance(instance, PurchaseAttachment):
            raise RuntimeError("connection lost after commit")
        return original_refresh(self, instance, *args, **kwargs)

    monkeypatch.setattr(Session, "refresh", refresh_fails_for_attachments)
    with pytest.raises(RuntimeError):
        upload(client, bill["id"], PDF)
    monkeypatch.undo()

    db.expire_all()
    saved = db.query(PurchaseAttachment).one()
    assert storage.read(saved.object_key) == PDF


def test_uploads_must_declare_their_size(client, world, storage):
    """The form is parsed before the user is checked, so a body of
    undeclared length (chunked) is refused before it is read."""
    act_as(client, world.a.admin)
    bill = create_bill(client, world.a, "ATT-CHUNKED")
    boundary = "kitchencopilot"
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.pdf"\r\n'
        "Content-Type: application/pdf\r\n\r\n"
    ).encode() + PDF + f"\r\n--{boundary}--\r\n".encode()
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}

    def chunked():
        yield body

    refused = client.post(f"{BILLS}{bill['id']}/attachments", content=chunked(), headers=headers)
    assert refused.status_code == 411
    assert stored_files(storage) == []

    declared = client.post(f"{BILLS}{bill['id']}/attachments", content=body, headers=headers)
    assert declared.status_code == 201, declared.text


@pytest.mark.parametrize("name", [
    "a" * 300 + ".pdf", "a." + "b" * 300, "." + "c" * 300, "x" * 400, "ബിൽ " * 80 + ".jpg",
])
def test_long_file_names_fit_the_column(name):
    cleaned = purchase_attachments.clean_filename(name)
    assert 0 < len(cleaned) <= 255
    if name.endswith((".pdf", ".jpg")):
        assert cleaned.endswith(name[-4:])


def test_a_missing_stored_file_is_reported(client, world, storage):
    act_as(client, world.a.admin)
    bill = create_bill(client, world.a, "ATT-MISSING")
    attachment = upload(client, bill["id"], PDF).json()
    for path in stored_files(storage):
        path.unlink()

    response = client.get(f"{BILLS}{bill['id']}/attachments/{attachment['id']}/file")

    assert response.status_code == 404
    assert "missing" in response.json()["detail"]


def test_storage_refuses_unsafe_keys_and_overwrites(tmp_path):
    store = LocalAttachmentStorage(tmp_path)
    for key in ("../escape.pdf", "campus-1/bill-1/../../x.pdf", "/etc/passwd",
                "campus-1/bill-1/short.pdf", "campus-1/bill-1/" + "a" * 32 + ".exe"):
        with pytest.raises(ValueError):
            store.save(key, b"x")
    key = "campus-1/bill-2/" + "0" * 32 + ".pdf"
    store.save(key, b"first")
    with pytest.raises(FileExistsError):
        store.save(key, b"second")
    assert store.read(key) == b"first"
    assert list(tmp_path.rglob("*.tmp")) == []


def test_unconfigured_storage_answers_503(client, world, monkeypatch):
    act_as(client, world.a.admin)
    bill = create_bill(client, world.a, "ATT-503")
    monkeypatch.setattr(settings, "ATTACHMENT_STORAGE_BACKEND", "s3")

    response = upload(client, bill["id"], PDF)

    assert response.status_code == 503


def assignment_rows(db, staff):
    db.expire_all()
    return sorted((r.permission_id, r.is_active, r.assigned_by)
                  for r in db.query(StaffAccessAssignment).filter_by(staff_user_id=staff.id))


def test_attachment_access_follows_existing_codes(client, db, world, storage):
    act_as(client, world.a.admin)
    bill = create_bill(client, world.a, "ATT-ACCESS")
    attachment = upload(client, bill["id"], PDF).json()
    file_url = f"{BILLS}{bill['id']}/attachments/{attachment['id']}/file"

    act_as(client, world.a.staff)
    assert upload(client, bill["id"], PNG).status_code == 403
    assert client.get(f"{BILLS}{bill['id']}/attachments").status_code == 403
    assert client.get(file_url).status_code == 403

    grant(db, world.a.staff, world.a.admin, "purchase_bill.read")
    before = assignment_rows(db, world.a.staff)
    assert client.get(f"{BILLS}{bill['id']}/attachments").status_code == 200
    assert client.get(file_url).status_code == 200
    assert upload(client, bill["id"], PNG).status_code == 403     # read ≠ create
    assert assignment_rows(db, world.a.staff) == before

    db.query(StaffAccessAssignment).filter_by(
        staff_user_id=world.a.staff.id).update({"is_active": False})
    db.commit()
    assert client.get(file_url).status_code == 403
    assert len(stored_files(storage)) == 1


def test_attachments_are_campus_isolated(client, world, storage):
    act_as(client, world.a.admin)
    bill = create_bill(client, world.a, "ATT-CAMPUS")
    attachment = upload(client, bill["id"], PDF).json()

    act_as(client, world.b.admin)
    assert client.get(f"{BILLS}{bill['id']}/attachments").status_code == 404
    assert upload(client, bill["id"], PNG).status_code == 404
    assert client.get(
        f"{BILLS}{bill['id']}/attachments/{attachment['id']}/file").status_code == 404
    # Campus A's attachment through campus B's own bill: still not found.
    assert client.get(
        f"{BILLS}{world.b.bill.id}/attachments/{attachment['id']}/file").status_code == 404
    assert len(stored_files(storage)) == 1


def test_upload_needs_the_csrf_token(client, db, world, storage):
    act_as(client, world.a.admin)
    bill = create_bill(client, world.a, "ATT-CSRF")

    response = client.post(f"{BILLS}{bill['id']}/attachments",
                           files={"file": ("bill.pdf", PDF, "application/pdf")},
                           headers={settings.CSRF_HEADER_NAME: "wrong"})

    assert response.status_code == 403
    assert stored_files(storage) == []


def test_attachment_activity_is_hidden_from_non_bill_readers(client, db, world, storage):
    act_as(client, world.a.admin)
    bill = create_bill(client, world.a, "ATT-FEED")
    upload(client, bill["id"], PDF)
    for code in ("dashboard.read", "audit.read"):
        grant(db, world.a.staff, world.a.admin, code)

    admin_feed = client.get("/api/dashboard/overview").json()["activity"]
    assert "PURCHASE_ATTACHMENT" in {e["entity_type"] for e in admin_feed}
    act_as(client, world.a.staff)
    staff_feed = client.get("/api/dashboard/overview").json()["activity"]
    assert "PURCHASE_ATTACHMENT" not in {e["entity_type"] for e in staff_feed}


# ============================================================
# 4. POSSIBLE DUPLICATE INVOICE NUMBERS
# ============================================================

def test_exact_duplicates_are_still_refused(client, world):
    act_as(client, world.a.admin)
    create_bill(client, world.a, "DUP-EXACT")

    response = client.post(BILLS, json={
        "supplier_id": world.a.supplier.id, "invoice_number": "DUP-EXACT",
        "purchase_date": "2026-11-04", "items": [line(world.a)],
    })

    assert response.status_code == 409


def test_possible_duplicates_are_flagged_not_blocked(client, db, world):
    other = Supplier(campus_id=world.a.campus.id, name="Other A")
    db.add(other)
    db.commit()
    act_as(client, world.a.manager)

    first = create_bill(client, world.a, "INV-001")
    assert first["possible_duplicates"] == [] and first["flagged_as_possible_duplicate"] is False

    second = create_bill(client, world.a, "inv 001")
    third = create_bill(client, world.a, "INV/001")
    assert [d["invoice_number"] for d in second["possible_duplicates"]] == ["INV-001"]
    assert second["flagged_as_possible_duplicate"] is True
    assert {d["invoice_number"] for d in third["possible_duplicates"]} == {"INV-001", "inv 001"}

    # Not possible duplicates: another supplier, or a different number.
    assert create_bill(client, world.a, "INV-001", supplier=other)["possible_duplicates"] == []
    assert create_bill(client, world.a, "INV-0010")["possible_duplicates"] == []

    detail = client.get(f"{BILLS}{first['id']}").json()
    assert {d["invoice_number"] for d in detail["possible_duplicates"]} == {"inv 001", "INV/001"}
    assert detail["flagged_as_possible_duplicate"] is True


def test_invoice_matching_handles_indian_scripts_and_full_width_digits(client, world):
    act_as(client, world.a.admin)
    create_bill(client, world.a, "ബിൽ-12")

    assert create_bill(client, world.a, "ബിൽ 12")["flagged_as_possible_duplicate"] is True
    # A different vowel sign is a different invoice number.
    assert create_bill(client, world.a, "ബൽ-12")["flagged_as_possible_duplicate"] is False
    create_bill(client, world.a, "INV12")
    assert create_bill(client, world.a, "INV１２")["flagged_as_possible_duplicate"] is True


def test_duplicate_check_before_saving(client, db, world):
    act_as(client, world.a.manager)
    create_bill(client, world.a, "CHK-500")
    url = f"{BILLS}duplicate-check?supplier_id={world.a.supplier.id}"

    exact = client.get(f"{url}&invoice_number=CHK-500")
    assert exact.status_code == 200, exact.text
    assert exact.json() == {"exact_duplicate": True, "possible_duplicates": []}

    possible = client.get(f"{url}&invoice_number=chk%20500").json()
    assert possible["exact_duplicate"] is False
    assert [d["invoice_number"] for d in possible["possible_duplicates"]] == ["CHK-500"]

    assert client.get(f"{url}&invoice_number=NEW-1").json() == {
        "exact_duplicate": False, "possible_duplicates": []}
    assert client.get(
        f"{BILLS}duplicate-check?supplier_id={world.b.supplier.id}&invoice_number=X"
    ).status_code == 404

    grant(db, world.a.staff, world.a.admin, "purchase_bill.read")
    act_as(client, world.a.staff)
    assert client.get(f"{url}&invoice_number=X").status_code == 403   # needs create


def test_possible_duplicates_list_and_review(client, db, world):
    act_as(client, world.a.admin)
    first = create_bill(client, world.a, "REV-9")
    second = create_bill(client, world.a, "rev 9")
    create_bill(client, world.a, "UNIQUE-1")

    listed = client.get(f"{BILLS}possible-duplicates").json()
    assert listed["total"] == 2
    assert {i["purchase_id"] for i in listed["items"]} == {first["id"], second["id"]}
    assert all(i["supplier_name"] == "Supplier A" for i in listed["items"])

    act_as(client, world.a.manager)
    assert client.post(f"{BILLS}{second['id']}/duplicate-review",
                       json={"note": "   "}).status_code == 422
    reviewed = client.post(f"{BILLS}{second['id']}/duplicate-review",
                           json={"note": "Separate delivery, checked with supplier"})
    assert reviewed.status_code == 200, reviewed.text
    body = reviewed.json()
    assert body["flagged_as_possible_duplicate"] is False
    assert body["duplicate_review"]["reviewed_by_name"] == world.a.manager.full_name
    assert body["duplicate_review"]["note"] == "Separate delivery, checked with supplier"
    assert datetime.fromisoformat(body["duplicate_review"]["reviewed_at"]).utcoffset() == timedelta(0)

    audit = db.query(AuditLog).filter_by(
        entity_type="PURCHASE", entity_id=second["id"], action="UPDATE").one()
    assert audit.details["duplicate_review"] == "NOT_A_DUPLICATE"
    assert audit.details["similar_invoice_numbers"] == ["REV-9"]

    remaining = client.get(f"{BILLS}possible-duplicates").json()
    assert [i["purchase_id"] for i in remaining["items"]] == [first["id"]]
    everything = client.get(f"{BILLS}possible-duplicates?include_reviewed=true").json()
    assert everything["total"] == 2

    again = client.post(f"{BILLS}{second['id']}/duplicate-review", json={"note": "again"})
    assert again.status_code == 409
    unique = db.query(Purchase).filter_by(invoice_number="UNIQUE-1").one()
    assert client.post(f"{BILLS}{unique.id}/duplicate-review",
                       json={"note": "x"}).status_code == 409


def test_review_needs_update_permission_and_stays_in_campus(client, db, world):
    act_as(client, world.a.admin)
    create_bill(client, world.a, "PERM-1")
    flagged = create_bill(client, world.a, "perm 1")

    grant(db, world.a.staff, world.a.admin, "purchase_bill.read")
    act_as(client, world.a.staff)
    assert client.get(f"{BILLS}possible-duplicates").status_code == 200
    assert client.post(f"{BILLS}{flagged['id']}/duplicate-review",
                       json={"note": "x"}).status_code == 403

    act_as(client, world.b.admin)
    assert client.post(f"{BILLS}{flagged['id']}/duplicate-review",
                       json={"note": "x"}).status_code == 404
    assert client.get(f"{BILLS}possible-duplicates").json()["total"] == 0


# ============================================================
# 5. ORIGINAL TRANSACTION DETAILS ARE PRESERVED
# ============================================================

def snapshot(db, purchase_id):
    db.expire_all()
    bill = db.get(Purchase, purchase_id)
    lines = db.query(PurchaseItem).filter_by(purchase_id=purchase_id).order_by(PurchaseItem.id)
    return (
        bill.supplier_id, bill.invoice_number, bill.purchase_date,
        str(bill.subtotal), str(bill.discount), str(bill.extra_charges),
        str(bill.grand_total), bill.remarks, bill.status, bill.created_by,
        bill.created_at.isoformat(),
        [(l.item_id, str(l.quantity), l.unit_id, str(l.unit_rate),
          str(l.line_total), l.remarks) for l in lines],
    )


def test_criterion_5_original_details_are_preserved(client, db, world, storage):
    act_as(client, world.a.admin)
    create_bill(client, world.a, "KEEP-1")
    bill = create_bill(client, world.a, "keep 1", discount="1.00",
                       extra_charges="2.00", remarks="Original")
    before = snapshot(db, bill["id"])

    # Attaching files and reviewing the duplicate flag do not touch the
    # recorded transaction.
    upload(client, bill["id"], PDF)
    client.post(f"{BILLS}{bill['id']}/duplicate-review", json={"note": "Checked"})
    create_bill(client, world.a, "KEEP-2")

    assert snapshot(db, bill["id"]) == before
    for method in ("put", "patch", "delete"):
        response = getattr(client, method)(
            f"{BILLS}{bill['id']}", **({} if method == "delete" else {"json": {}}))
        assert response.status_code == 405, method
