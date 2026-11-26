
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import require_permission, user_has_permission
from app.api.routes.master_data import (
    get_unit_conversion_factor,
    record_audit,
)
from app.core.clock import utc_iso
from app.db.session import get_db
from app.models.master_data import Category, Item, Supplier, Unit
from app.models.purchases import Purchase, PurchaseItem, PurchaseOrder, PurchaseOrderItem
from app.models.user import User

router = APIRouter(prefix="/api/purchases", tags=["Purchases"])

MONEY = Decimal("0.01")


# ============================================================
# REQUEST SCHEMAS
# ============================================================

class PurchaseLineInput(BaseModel):
    item_id: int
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    unit_id: int
    unit_rate: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    remarks: str | None = Field(default=None, max_length=500)
    # The purchase-order line this bill line bills for (optional, Stage 3).
    purchase_order_item_id: int | None = Field(default=None, gt=0)


class PurchaseCreate(BaseModel):
    supplier_id: int
    invoice_number: str = Field(min_length=1, max_length=100)
    purchase_date: date
    discount: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        max_digits=18,
        decimal_places=2,
    )
    extra_charges: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        max_digits=18,
        decimal_places=2,
    )
    remarks: str | None = None
    items: list[PurchaseLineInput] = Field(min_length=1)
    # The placed purchase order this bill is entered against (optional).
    purchase_order_id: int | None = Field(default=None, gt=0)

    @field_validator("invoice_number")
    @classmethod
    def clean_invoice_number(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Invoice number cannot be empty")

        return value


# ============================================================
# MONEY HELPER
# ============================================================

def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def money_text(value) -> str | None:
    """Money as a two-place decimal string ("1250.50"), the same format
    the supplier payment and balance endpoints use. Never a float."""
    if value is None:
        return None
    return format(money(Decimal(str(value))), "f")


def decimal_text(value) -> str | None:
    """A stored decimal (e.g. a 4-place unit rate) as an exact string."""
    if value is None:
        return None
    return format(Decimal(str(value)), "f")


# ============================================================
# PURCHASE SERIALIZATION
# ============================================================

def serialize_purchase(db: Session, purchase: Purchase, show_orders: bool = True) -> dict:
    """show_orders: include the purchase order the bill was entered against.
    False for users without order access (STAFF): purchase-order
    information is not shown through bill permissions."""
    if not show_orders:
        result = serialize_purchase(db, purchase)
        result["purchase_order_id"] = None
        result["purchase_order_number"] = None
        for line in result["items"]:
            line["purchase_order_item_id"] = None
        return result

    # Names are added for display only; the stored ids and values are
    # returned unchanged.
    lines = (
        db.query(PurchaseItem, Item.name, Category.name, Unit.symbol)
        .outerjoin(
            Item,
            (Item.id == PurchaseItem.item_id)
            & (Item.campus_id == purchase.campus_id),
        )
        .outerjoin(
            Category,
            (Category.id == Item.category_id)
            & (Category.campus_id == purchase.campus_id),
        )
        .outerjoin(
            Unit,
            (Unit.id == PurchaseItem.unit_id)
            & (Unit.campus_id == purchase.campus_id),
        )
        .filter(
            PurchaseItem.purchase_id == purchase.id,
            PurchaseItem.campus_id == purchase.campus_id,
        )
        .order_by(PurchaseItem.id)
        .all()
    )

    supplier = (
        db.query(Supplier)
        .filter(
            Supplier.id == purchase.supplier_id,
            Supplier.campus_id == purchase.campus_id,
        )
        .first()
    )

    return {
        "id": purchase.id,
        "supplier_id": purchase.supplier_id,
        "supplier_name": supplier.name if supplier else None,
        "invoice_number": purchase.invoice_number,
        "purchase_date": purchase.purchase_date,
        "subtotal": money_text(purchase.subtotal),
        "discount": money_text(purchase.discount),
        "extra_charges": money_text(purchase.extra_charges),
        "grand_total": money_text(purchase.grand_total),
        "remarks": purchase.remarks,
        "status": purchase.status,
        "created_at": purchase.created_at,
        "purchase_order_id": purchase.purchase_order_id,
        "purchase_order_number": (
            db.query(PurchaseOrder.order_number).filter(
                PurchaseOrder.id == purchase.purchase_order_id,
                PurchaseOrder.campus_id == purchase.campus_id,
            ).scalar()
            if purchase.purchase_order_id else None
        ),
        "items": [
            {
                "id": line.id,
                "item_id": line.item_id,
                "item_name": item_name,
                "category_name": category_name,
                "quantity": line.quantity,
                "unit_id": line.unit_id,
                "unit_symbol": unit_symbol,
                "unit_rate": decimal_text(line.unit_rate),
                "line_total": money_text(line.line_total),
                "remarks": line.remarks,
                "purchase_order_item_id": line.purchase_order_item_id,
            }
            for line, item_name, category_name, unit_symbol in lines
        ],
    }


def link_order(db: Session, user: User, supplier: Supplier, payload: PurchaseCreate):
    """The purchase order a new bill is entered against, if any (Stage 3).

    The order must be PLACED, of this campus and from the bill's supplier.
    Its row is locked, so it cannot be cancelled while the bill is saved.
    Bill lines may link to its lines; a bill may still bill more than was
    ordered (it is recorded as the supplier issued it) and the order shows
    the excess. Bills without an order are unaffected.
    """
    linked = [line.purchase_order_item_id for line in payload.items
              if line.purchase_order_item_id is not None]
    if payload.purchase_order_id is None:
        if linked:
            raise HTTPException(
                status_code=422,
                detail="Bill lines can be linked to order lines only when the bill "
                       "is entered against that purchase order",
            )
        return None, {}

    # Entering a bill against an order reads the order: ADMIN and
    # KITCHEN_MANAGER only (STAFF never hold purchase-order access).
    if not user_has_permission(db, user, "purchase_order.read"):
        raise HTTPException(
            status_code=403,
            detail="Only Admins and Kitchen Managers can enter a bill against a purchase order",
        )

    order = (
        db.query(PurchaseOrder)
        .filter(
            PurchaseOrder.id == payload.purchase_order_id,
            PurchaseOrder.campus_id == user.campus_id,
        )
        .with_for_update()
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    if order.status != "PLACED":
        raise HTTPException(
            status_code=422,
            detail=f"Bills can be entered only against a placed order "
                   f"({order.order_number} is {order.status.lower()})",
        )
    if order.supplier_id != supplier.id:
        raise HTTPException(
            status_code=422,
            detail=f"Purchase order {order.order_number} is from another supplier",
        )
    if len(linked) != len(set(linked)):
        raise HTTPException(
            status_code=422,
            detail="An order line can be billed by only one line of a bill",
        )
    lines = {
        line.id: line
        for line in db.query(PurchaseOrderItem).filter(
            PurchaseOrderItem.purchase_order_id == order.id,
            PurchaseOrderItem.campus_id == user.campus_id,
        )
    }
    return order, lines


# ============================================================
# CREATE PURCHASE
# Permission: purchase_bill.create
# ============================================================

@router.post("/", status_code=status.HTTP_201_CREATED)
def create_purchase(
    payload: PurchaseCreate,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_permission("purchase_bill.create")
    ),
):
    supplier = (
        db.query(Supplier)
        .filter(
            Supplier.id == payload.supplier_id,
            Supplier.campus_id == user.campus_id,
            Supplier.is_active.is_(True),
        )
        .first()
    )

    if not supplier:
        raise HTTPException(
            status_code=404,
            detail="Active supplier not found in your campus",
        )

    duplicate = (
        db.query(Purchase)
        .filter(
            Purchase.campus_id == user.campus_id,
            Purchase.supplier_id == supplier.id,
            Purchase.invoice_number == payload.invoice_number,
        )
        .first()
    )

    if duplicate:
        raise HTTPException(
            status_code=409,
            detail="This invoice number already exists for this supplier",
        )

    order, order_lines_by_id = link_order(db, user, supplier, payload)

    subtotal = Decimal("0")
    prepared_lines = []

    for line in payload.items:

        item = (
            db.query(Item)
            .filter(
                Item.id == line.item_id,
                Item.campus_id == user.campus_id,
                Item.is_active.is_(True),
            )
            .first()
        )

        if not item:
            raise HTTPException(
                status_code=404,
                detail=f"Active item {line.item_id} not found in your campus",
            )

        selected_unit = (
            db.query(Unit)
            .filter(
                Unit.id == line.unit_id,
                Unit.campus_id == user.campus_id,
                Unit.is_active.is_(True),
            )
            .first()
        )

        if not selected_unit:
            raise HTTPException(
                status_code=404,
                detail=f"Active unit {line.unit_id} not found in your campus",
            )

        standard_unit = (
            db.query(Unit)
            .filter(
                Unit.id == item.standard_unit_id,
                Unit.campus_id == user.campus_id,
                Unit.is_active.is_(True),
            )
            .first()
        )

        if not standard_unit:
            raise HTTPException(
                status_code=422,
                detail=f"Item {item.name} has no valid active standard unit",
            )

        if selected_unit.dimension != standard_unit.dimension:
            raise HTTPException(
                status_code=422,
                detail=f"Unit dimension mismatch for item {item.name}",
            )

        # Validate conversion to the item's standard unit.
        # The entered quantity and unit remain unchanged on the purchase line.
        get_unit_conversion_factor(
            db,
            user,
            selected_unit.id,
            standard_unit.id,
        )

        if line.purchase_order_item_id is not None:
            order_line = order_lines_by_id.get(line.purchase_order_item_id)
            if order_line is None:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Order line {line.purchase_order_item_id} is not on "
                        f"purchase order {order.order_number}"
                    ),
                )
            if order_line.item_id != item.id:
                raise HTTPException(
                    status_code=422,
                    detail=f"A bill line for {item.name} cannot bill a different ordered item",
                )

        line_total = money(line.quantity * line.unit_rate)
        subtotal += line_total

        prepared_lines.append({
            "item_id": item.id,
            "quantity": line.quantity,
            "unit_id": selected_unit.id,
            "unit_rate": line.unit_rate,
            "line_total": line_total,
            "remarks": line.remarks,
            "purchase_order_item_id": line.purchase_order_item_id,
        })

    subtotal = money(subtotal)
    discount = money(payload.discount)
    extra_charges = money(payload.extra_charges)

    if discount > subtotal:
        raise HTTPException(
            status_code=422,
            detail="Discount cannot exceed the purchase subtotal",
        )

    grand_total = money(
        subtotal - discount + extra_charges
    )

    purchase = Purchase(
        campus_id=user.campus_id,
        supplier_id=supplier.id,
        invoice_number=payload.invoice_number,
        purchase_date=payload.purchase_date,
        subtotal=subtotal,
        discount=discount,
        extra_charges=extra_charges,
        grand_total=grand_total,
        remarks=payload.remarks,
        status="DRAFT",
        created_by=user.id,
        purchase_order_id=order.id if order else None,
    )

    try:
        db.add(purchase)
        db.flush()

        for line in prepared_lines:
            db.add(
                PurchaseItem(
                    campus_id=user.campus_id,
                    purchase_id=purchase.id,
                    **line,
                )
            )

        record_audit(
            db,
            user,
            "CREATE",
            "PURCHASE",
            purchase.id,
            {
                "invoice_number": purchase.invoice_number,
                "supplier_id": supplier.id,
                "grand_total": str(grand_total),
                "item_count": len(prepared_lines),
                **({"purchase_order_id": order.id,
                    "purchase_order_number": order.order_number} if order else {}),
            },
        )

        db.commit()
        db.refresh(purchase)

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail=(
                "Purchase could not be saved because of "
                "a duplicate or invalid record"
            ),
        )

    # Saved, but possibly a duplicate of another bill from the same
    # supplier: flagged for review (PUR01), never blocked.
    return jsonable_encoder({
        **serialize_purchase(
            db, purchase, show_orders=user_has_permission(db, user, "purchase_order.read")
        ),
        **duplicate_status(db, purchase),
    })


# ============================================================
# LIST PURCHASES
# Permission: purchase_bill.read
# ============================================================

@router.get("/")
def list_purchases(
    db: Session = Depends(get_db),
    user: User = Depends(
        require_permission("purchase_bill.read")
    ),
):
    purchases = (
        db.query(Purchase)
        .filter(
            Purchase.campus_id == user.campus_id
        )
        .order_by(
            Purchase.purchase_date.desc(),
            Purchase.id.desc(),
        )
        .all()
    )

    show_orders = user_has_permission(db, user, "purchase_order.read")
    return jsonable_encoder([
        serialize_purchase(db, purchase, show_orders=show_orders)
        for purchase in purchases
    ])


# ============================================================
# POSSIBLE DUPLICATE INVOICES (PUR01)
#
# Exact duplicates (same campus, supplier and invoice number) are rejected
# by the database. A possible duplicate is another bill from the same
# supplier whose invoice number is equal once case, spaces and punctuation
# are ignored ("INV-001" and "inv 001"). It is flagged for review, never
# blocked. A user with purchase_bill.update may mark a flagged bill "not a
# duplicate" with a note; that review is audited. Approved 18 November 2026.
# ============================================================

class DuplicateReview(BaseModel):
    note: str = Field(min_length=1, max_length=500)

    @field_validator("note")
    @classmethod
    def clean_note(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Enter a note explaining the review")
        return value


def normalized_invoice(value: str) -> str:
    """'INV-001' and 'inv 001' → 'inv001'. Letters, digits and combining
    marks (the vowel signs of Malayalam and other Indian scripts) are kept,
    case-folded; spaces and punctuation are ignored. NFKC first, so
    full-width digits match ordinary ones."""
    text = unicodedata.normalize("NFKC", value).casefold()
    return "".join(ch for ch in text if unicodedata.category(ch)[0] in "LNM")


def similar_bills(
    db: Session,
    campus_id: int,
    supplier_id: int,
    invoice_number: str,
    exclude_id: int | None = None,
) -> list[Purchase]:
    key = normalized_invoice(invoice_number)
    if not key:
        return []
    rows = (
        db.query(Purchase)
        .filter(Purchase.campus_id == campus_id, Purchase.supplier_id == supplier_id)
        .order_by(Purchase.purchase_date, Purchase.id)
        .all()
    )
    return [
        row for row in rows
        if row.id != exclude_id and normalized_invoice(row.invoice_number) == key
    ]


def similar_summary(rows: list[Purchase]) -> list[dict]:
    return [
        {
            "purchase_id": row.id,
            "invoice_number": row.invoice_number,
            "purchase_date": row.purchase_date.isoformat(),
            "grand_total": money_text(row.grand_total),
        }
        for row in rows
    ]


def review_summary(db: Session, purchase: Purchase) -> dict | None:
    if purchase.duplicate_reviewed_at is None:
        return None
    reviewer = db.query(User.full_name).filter(
        User.id == purchase.duplicate_reviewed_by
    ).scalar()
    return {
        "reviewed_at": utc_iso(purchase.duplicate_reviewed_at),
        "reviewed_by": purchase.duplicate_reviewed_by,
        "reviewed_by_name": reviewer,
        "note": purchase.duplicate_review_note,
    }


def duplicate_status(db: Session, purchase: Purchase) -> dict:
    similar = similar_bills(
        db, purchase.campus_id, purchase.supplier_id,
        purchase.invoice_number, exclude_id=purchase.id,
    )
    review = review_summary(db, purchase)
    return {
        "possible_duplicates": similar_summary(similar),
        "duplicate_review": review,
        "flagged_as_possible_duplicate": bool(similar) and review is None,
    }


@router.get("/duplicate-check")
def check_invoice_number(
    supplier_id: int = Query(..., gt=0),
    invoice_number: str = Query(..., min_length=1, max_length=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("purchase_bill.create")),
):
    """Before saving: would this invoice number be refused (exact
    duplicate) or flagged (possible duplicate)?"""
    supplier = db.query(Supplier.id).filter(
        Supplier.id == supplier_id, Supplier.campus_id == user.campus_id
    ).first()
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found")

    invoice = invoice_number.strip()
    similar = similar_bills(db, user.campus_id, supplier_id, invoice)
    return {
        "exact_duplicate": any(row.invoice_number == invoice for row in similar),
        "possible_duplicates": similar_summary(
            [row for row in similar if row.invoice_number != invoice]
        ),
    }


@router.get("/possible-duplicates")
def list_possible_duplicates(
    include_reviewed: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("purchase_bill.read")),
):
    """Every bill flagged as a possible duplicate, with the similar bills.
    Reviewed bills are left out unless include_reviewed is set."""
    rows = (
        db.query(Purchase, Supplier.name)
        .outerjoin(
            Supplier,
            (Supplier.id == Purchase.supplier_id)
            & (Supplier.campus_id == user.campus_id),
        )
        .filter(Purchase.campus_id == user.campus_id)
        .all()
    )

    groups: dict[tuple[int, str], list] = defaultdict(list)
    for purchase, supplier_name in rows:
        key = normalized_invoice(purchase.invoice_number)
        if key:
            groups[(purchase.supplier_id, key)].append((purchase, supplier_name))

    items = []
    for group in groups.values():
        if len(group) < 2:
            continue
        for purchase, supplier_name in group:
            review = review_summary(db, purchase)
            if review is not None and not include_reviewed:
                continue
            others = sorted(
                (other for other, _name in group if other.id != purchase.id),
                key=lambda row: (row.purchase_date, row.id),
            )
            items.append({
                "purchase_id": purchase.id,
                "supplier_id": purchase.supplier_id,
                "supplier_name": supplier_name,
                "invoice_number": purchase.invoice_number,
                "purchase_date": purchase.purchase_date.isoformat(),
                "grand_total": money_text(purchase.grand_total),
                "possible_duplicates": similar_summary(others),
                "duplicate_review": review,
            })

    items.sort(key=lambda item: (
        (item["supplier_name"] or "").casefold(),
        normalized_invoice(item["invoice_number"]),
        item["purchase_date"],
        item["purchase_id"],
    ))
    return {"items": items, "total": len(items)}


@router.post("/{purchase_id}/duplicate-review")
def review_possible_duplicate(
    purchase_id: int,
    payload: DuplicateReview,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("purchase_bill.update")),
):
    """Confirm that a flagged bill is not a duplicate. Only the review
    fields change; the bill's transaction details are untouched."""
    purchase = (
        db.query(Purchase)
        .filter(Purchase.id == purchase_id, Purchase.campus_id == user.campus_id)
        .with_for_update()
        .first()
    )
    if purchase is None:
        raise HTTPException(status_code=404, detail="Purchase not found")

    similar = similar_bills(
        db, user.campus_id, purchase.supplier_id,
        purchase.invoice_number, exclude_id=purchase.id,
    )
    if not similar:
        raise HTTPException(
            status_code=409,
            detail="This bill is not flagged as a possible duplicate.",
        )
    if purchase.duplicate_reviewed_at is not None:
        raise HTTPException(
            status_code=409, detail="This bill has already been reviewed."
        )

    purchase.duplicate_reviewed_at = datetime.now(timezone.utc)
    purchase.duplicate_reviewed_by = user.id
    purchase.duplicate_review_note = payload.note

    record_audit(
        db,
        user,
        "UPDATE",
        "PURCHASE",
        purchase.id,
        {
            "duplicate_review": "NOT_A_DUPLICATE",
            "note": payload.note,
            "invoice_number": purchase.invoice_number,
            "supplier_id": purchase.supplier_id,
            "similar_purchase_ids": [row.id for row in similar],
            "similar_invoice_numbers": [row.invoice_number for row in similar],
        },
    )
    db.commit()
    db.refresh(purchase)

    return duplicate_status(db, purchase)


# ============================================================
# GET PURCHASE DETAILS
# Permission: purchase_bill.read
# ============================================================

@router.get("/{purchase_id}")
def get_purchase(
    purchase_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_permission("purchase_bill.read")
    ),
):
    purchase = (
        db.query(Purchase)
        .filter(
            Purchase.id == purchase_id,
            Purchase.campus_id == user.campus_id,
        )
        .first()
    )

    if not purchase:
        raise HTTPException(
            status_code=404,
            detail="Purchase not found",
        )

    return jsonable_encoder({
        **serialize_purchase(
            db, purchase, show_orders=user_has_permission(db, user, "purchase_order.read")
        ),
        **duplicate_status(db, purchase),
    })
