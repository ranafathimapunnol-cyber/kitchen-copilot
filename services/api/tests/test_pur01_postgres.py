"""
PUR01 on PostgreSQL: bill attachments and duplicate review.

Uses the shared tests/conftest.py fixtures, so it runs against
kitchen_copilot_test_db on the Docker database server (see
docs/DEVELOPMENT-SAFETY.md section 3.3). Covers what SQLite cannot:
- concurrent uploads to one bill never pass the 10-file limit (row lock);
- the same file cannot be attached twice, even in a race (unique key);
- the review-completeness check constraint;
- the attachment and duplicate endpoints on a real server.
"""

import hashlib
import threading
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models import AuditLog, Supplier
from app.models.purchases import Purchase, PurchaseAttachment
from app.services.attachment_storage import LocalAttachmentStorage, get_attachment_storage

PDF = b"%PDF-1.7\n" + b"0" * 300


@pytest.fixture
def storage(tmp_path):
    store = LocalAttachmentStorage(tmp_path / "bill-attachments")
    app.dependency_overrides[get_attachment_storage] = lambda: store
    yield store
    app.dependency_overrides.pop(get_attachment_storage, None)


def make_bill(db, setup_data, invoice, total="100.00"):
    supplier = db.query(Supplier).filter_by(campus_id=setup_data["campus"].id).first()
    if supplier is None:
        supplier = Supplier(campus_id=setup_data["campus"].id, name="PG PUR01 Supplier")
        db.add(supplier)
        db.flush()
    bill = Purchase(
        campus_id=setup_data["campus"].id, supplier_id=supplier.id,
        invoice_number=invoice, purchase_date=date(2026, 11, 3),
        subtotal=Decimal(total), discount=0, extra_charges=0,
        grand_total=Decimal(total), status="DRAFT", created_by=setup_data["user"].id,
    )
    db.add(bill)
    db.commit()
    return bill


def upload(client, bill_id, data, name="bill.pdf"):
    return client.post(f"/api/purchases/{bill_id}/attachments",
                       files={"file": (name, data, "application/pdf")})


def test_attachments_round_trip_on_postgres(client, db, setup_data, storage):
    bill = make_bill(db, setup_data, "PG-ATT-1")

    created = upload(client, bill.id, PDF, name="Scan ₹ 1.pdf")
    assert created.status_code == 201, created.text
    listed = client.get(f"/api/purchases/{bill.id}/attachments").json()["items"]
    download = client.get(f"/api/purchases/{bill.id}/attachments/{listed[0]['id']}/file")

    assert listed[0]["checksum_sha256"] == hashlib.sha256(PDF).hexdigest()
    assert listed[0]["original_filename"] == "Scan ₹ 1.pdf"
    assert download.content == PDF
    assert db.query(AuditLog).filter_by(entity_type="PURCHASE_ATTACHMENT").count() == 1
    assert upload(client, bill.id, PDF).status_code == 409


def test_long_file_names_are_stored_on_postgres(client, db, setup_data, storage):
    """VARCHAR(255) is enforced by PostgreSQL (SQLite ignores it)."""
    bill = make_bill(db, setup_data, "PG-ATT-LONG")
    for name in ("a" * 300 + ".pdf", "a." + "b" * 300):
        data = PDF + name.encode()[:8]
        response = upload(client, bill.id, data, name=name)
        assert response.status_code == 201, response.text
        assert len(response.json()["original_filename"]) <= 255


def test_same_file_cannot_be_stored_twice_by_the_database(db, setup_data):
    bill = make_bill(db, setup_data, "PG-ATT-UNIQUE")
    common = dict(campus_id=setup_data["campus"].id, purchase_id=bill.id,
                  original_filename="a.pdf", content_type="application/pdf",
                  size_bytes=10, checksum_sha256="f" * 64, uploaded_by=setup_data["user"].id)
    db.add(PurchaseAttachment(object_key="campus-1/bill-1/" + "a" * 32 + ".pdf", **common))
    db.commit()
    db.add(PurchaseAttachment(object_key="campus-1/bill-1/" + "b" * 32 + ".pdf", **common))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_review_fields_must_be_complete(db, setup_data):
    bill = make_bill(db, setup_data, "PG-REV-CHECK")
    bill.duplicate_reviewed_by = setup_data["user"].id      # without a time
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


@pytest.fixture
def parallel_clients(db, setup_data, storage):
    engine = create_engine(db.get_bind().url, poolclass=NullPool,
                           connect_args={"prepare_threshold": None})
    factory = sessionmaker(bind=engine, autoflush=False)

    def per_request_session():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = per_request_session
    token = create_access_token(setup_data["user"].id, setup_data["user"].password_hash)
    clients = []
    try:
        for _ in range(4):
            client = TestClient(app)
            client.__enter__()
            csrf = client.get("/api/auth/csrf").json()["csrf_token"]
            client.headers.update({settings.CSRF_HEADER_NAME: csrf})
            client.cookies.set(settings.ACCESS_COOKIE_NAME, token)
            clients.append(client)
        yield clients
    finally:
        for client in clients:
            client.__exit__(None, None, None)
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def race(clients, bill_id, payloads):
    barrier = threading.Barrier(len(clients))
    statuses = [None] * len(clients)

    def worker(index):
        barrier.wait()
        statuses[index] = upload(clients[index], bill_id, payloads[index]).status_code

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(len(clients))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return sorted(statuses)


def test_concurrent_uploads_never_pass_ten_files(db, setup_data, parallel_clients, storage):
    bill = make_bill(db, setup_data, "PG-ATT-RACE-10")
    bill_id = bill.id
    for n in range(8):
        db.add(PurchaseAttachment(
            campus_id=setup_data["campus"].id, purchase_id=bill_id,
            object_key=f"campus-1/bill-{bill_id}/" + f"{n:032x}" + ".pdf",
            original_filename=f"{n}.pdf", content_type="application/pdf",
            size_bytes=1, checksum_sha256=f"{n:064x}", uploaded_by=setup_data["user"].id,
        ))
    db.commit()

    statuses = race(parallel_clients, bill_id, [PDF + bytes([n]) for n in range(4)])

    db.expire_all()
    assert statuses.count(201) == 2 and statuses.count(409) == 2, statuses
    assert db.query(PurchaseAttachment).filter_by(purchase_id=bill_id).count() == 10
    # Only the two saved uploads left a file behind.
    assert len([p for p in storage.root.rglob("*") if p.is_file()]) == 2


def test_concurrent_uploads_of_the_same_file_store_it_once(db, setup_data, parallel_clients, storage):
    bill_id = make_bill(db, setup_data, "PG-ATT-RACE-SAME").id

    statuses = race(parallel_clients, bill_id, [PDF] * 4)

    db.expire_all()
    assert statuses.count(201) == 1 and statuses.count(409) == 3, statuses
    assert db.query(PurchaseAttachment).filter_by(purchase_id=bill_id).count() == 1
    assert len([p for p in storage.root.rglob("*") if p.is_file()]) == 1


def test_duplicate_flag_and_review_on_postgres(client, db, setup_data):
    make_bill(db, setup_data, "PG-DUP-77")
    flagged = make_bill(db, setup_data, "pg dup 77")

    listed = client.get("/api/purchases/possible-duplicates").json()
    assert listed["total"] == 2
    reviewed = client.post(f"/api/purchases/{flagged.id}/duplicate-review",
                           json={"note": "Checked on PostgreSQL"})
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["flagged_as_possible_duplicate"] is False
    stored = db.execute(text(
        "SELECT duplicate_reviewed_at IS NOT NULL, duplicate_review_note "
        "FROM purchases WHERE id = :id"), {"id": flagged.id}).one()
    assert tuple(stored) == (True, "Checked on PostgreSQL")
