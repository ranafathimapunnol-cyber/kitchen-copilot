"""Supplier bill attachments (PUR01, ADR-008).

Rules approved 18 November 2026:
- PDF, JPEG, PNG and WEBP only, recognised from the file's content, not
  its name or the browser's claimed type.
- At most 10 MB per file and 10 files per bill.
- The same file (SHA-256) can be attached to a bill only once.
- Upload needs purchase_bill.create (as entering a bill); listing and
  downloading need purchase_bill.read. Campus-scoped: another campus's
  bill is "not found".
- Attachments are permanent: there is no delete or replace endpoint. A wrong
  file is superseded by uploading the right one with a remark.
- Every upload writes an audit row in the same transaction as its metadata.
  If that transaction fails, the stored file is removed again.
"""

import hashlib
import re
import unicodedata
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import require_permission
from app.api.routes.master_data import record_audit
from app.core.clock import utc_iso
from app.db.session import get_db
from app.models.purchases import Purchase, PurchaseAttachment
from app.models.user import User
from app.services.attachment_storage import (
    AttachmentStorage,
    get_attachment_storage,
    new_object_key,
)

router = APIRouter(tags=["Purchase Attachments"])

MAX_BYTES = 10 * 1024 * 1024
MAX_PER_BILL = 10

# content type → stored extension
ALLOWED_TYPES = {
    "application/pdf": "pdf",
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


def detect_type(data: bytes) -> str | None:
    """The file's real type from its first bytes (its "magic number")."""
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def clean_filename(name: str | None) -> str:
    """The original name, kept for display: no folders, no control
    characters, at most 255 characters."""
    name = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(ch for ch in name if unicodedata.category(ch)[0] != "C")
    name = re.sub(r"\s+", " ", name).strip()
    if len(name) > 255:
        stem, dot, extension = name.rpartition(".")
        if dot and stem and len(extension) <= 10:
            name = stem[: 254 - len(extension)] + "." + extension
        else:
            name = name[:255]
    return name or "attachment"


def serialize_attachment(row: PurchaseAttachment, uploaded_by_name: str | None) -> dict:
    return {
        "id": row.id,
        "purchase_id": row.purchase_id,
        "original_filename": row.original_filename,
        "content_type": row.content_type,
        "size_bytes": row.size_bytes,
        "checksum_sha256": row.checksum_sha256,
        "remarks": row.remarks,
        "uploaded_by": row.uploaded_by,
        "uploaded_by_name": uploaded_by_name,
        "uploaded_at": utc_iso(row.uploaded_at),
    }


def campus_bill(db: Session, user: User, purchase_id: int, lock: bool = False) -> Purchase:
    query = db.query(Purchase).filter(
        Purchase.id == purchase_id, Purchase.campus_id == user.campus_id
    )
    if lock:
        # Serialises uploads to one bill, so the 10-file limit holds.
        query = query.with_for_update()
    purchase = query.first()
    if purchase is None:
        raise HTTPException(status_code=404, detail="Purchase not found")
    return purchase


# ============================================================
# UPLOAD
# Permission: purchase_bill.create
# ============================================================

@router.post(
    "/api/purchases/{purchase_id}/attachments",
    status_code=status.HTTP_201_CREATED,
)
def upload_attachment(
    purchase_id: int,
    file: UploadFile = File(...),
    remarks: str | None = Form(default=None, max_length=500),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("purchase_bill.create")),
    storage: AttachmentStorage = Depends(get_attachment_storage),
):
    purchase = campus_bill(db, user, purchase_id, lock=True)

    existing = db.query(PurchaseAttachment).filter(
        PurchaseAttachment.campus_id == user.campus_id,
        PurchaseAttachment.purchase_id == purchase.id,
    ).count()
    if existing >= MAX_PER_BILL:
        raise HTTPException(
            status_code=409,
            detail=f"A bill can have at most {MAX_PER_BILL} attachments.",
        )

    data = file.file.read(MAX_BYTES + 1)
    if not data:
        raise HTTPException(status_code=422, detail="The file is empty.")
    if len(data) > MAX_BYTES:
        raise HTTPException(
            status_code=413, detail="A file can be at most 10 MB."
        )

    content_type = detect_type(data)
    if content_type is None:
        raise HTTPException(
            status_code=415,
            detail="Only PDF, JPEG, PNG and WEBP files can be attached.",
        )

    checksum = hashlib.sha256(data).hexdigest()
    already = db.query(PurchaseAttachment.id).filter(
        PurchaseAttachment.campus_id == user.campus_id,
        PurchaseAttachment.purchase_id == purchase.id,
        PurchaseAttachment.checksum_sha256 == checksum,
    ).first()
    if already:
        raise HTTPException(
            status_code=409, detail="This file is already attached to this bill."
        )

    note = remarks.strip() if remarks else None
    key = new_object_key(user.campus_id, purchase.id, ALLOWED_TYPES[content_type])
    storage.save(key, data)

    try:
        attachment = PurchaseAttachment(
            campus_id=user.campus_id,
            purchase_id=purchase.id,
            object_key=key,
            original_filename=clean_filename(file.filename),
            content_type=content_type,
            size_bytes=len(data),
            checksum_sha256=checksum,
            remarks=note or None,
            uploaded_by=user.id,
        )
        db.add(attachment)
        db.flush()

        record_audit(
            db,
            user,
            "CREATE",
            "PURCHASE_ATTACHMENT",
            attachment.id,
            {
                "purchase_id": purchase.id,
                "invoice_number": purchase.invoice_number,
                "supplier_id": purchase.supplier_id,
                "original_filename": attachment.original_filename,
                "content_type": content_type,
                "size_bytes": len(data),
                "checksum_sha256": checksum,
                "remarks": attachment.remarks,
            },
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        storage.delete(key)
        raise HTTPException(
            status_code=409, detail="This file is already attached to this bill."
        )
    except Exception:
        db.rollback()
        storage.delete(key)
        raise

    # Committed: from here on the stored file belongs to a saved row and is
    # never removed, even if reloading the row fails.
    db.refresh(attachment)
    return serialize_attachment(attachment, user.full_name)


# ============================================================
# LIST
# Permission: purchase_bill.read
# ============================================================

@router.get("/api/purchases/{purchase_id}/attachments")
def list_attachments(
    purchase_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("purchase_bill.read")),
):
    purchase = campus_bill(db, user, purchase_id)
    rows = (
        db.query(PurchaseAttachment, User.full_name)
        .outerjoin(User, User.id == PurchaseAttachment.uploaded_by)
        .filter(
            PurchaseAttachment.campus_id == user.campus_id,
            PurchaseAttachment.purchase_id == purchase.id,
        )
        .order_by(PurchaseAttachment.uploaded_at, PurchaseAttachment.id)
        .all()
    )
    return {
        "items": [serialize_attachment(row, name) for row, name in rows],
        "limits": {
            "max_files": MAX_PER_BILL,
            "max_bytes": MAX_BYTES,
            "content_types": sorted(ALLOWED_TYPES),
        },
    }


# ============================================================
# DOWNLOAD
# Permission: purchase_bill.read
# ============================================================

@router.get("/api/purchases/{purchase_id}/attachments/{attachment_id}/file")
def download_attachment(
    purchase_id: int,
    attachment_id: int,
    disposition: str = Query(default="attachment", pattern="^(attachment|inline)$"),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("purchase_bill.read")),
    storage: AttachmentStorage = Depends(get_attachment_storage),
):
    campus_bill(db, user, purchase_id)
    attachment = db.query(PurchaseAttachment).filter(
        PurchaseAttachment.id == attachment_id,
        PurchaseAttachment.purchase_id == purchase_id,
        PurchaseAttachment.campus_id == user.campus_id,
    ).first()
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found")

    try:
        data = storage.read(attachment.object_key)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail="The stored file for this attachment is missing."
        )

    ascii_name = (
        attachment.original_filename.encode("ascii", "ignore").decode()
        .replace('"', "").replace("\\", "") or "attachment"
    )
    return Response(
        content=data,
        media_type=attachment.content_type,
        headers={
            "Content-Disposition": (
                f'{disposition}; filename="{ascii_name}"; '
                f"filename*=UTF-8''{quote(attachment.original_filename)}"
            ),
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            # Opened directly, the file runs with no scripts and no origin.
            "Content-Security-Policy": "sandbox",
        },
    )
