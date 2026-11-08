from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.dependencies import get_current_user, require_roles
from app.api.routes.master_data import (
    get_unit_conversion_factor,
    record_audit,
)
from app.models.user import User, UserRole
from app.models.master_data import Item, Supplier, Unit
from app.models.purchases import Purchase, PurchaseItem


router = APIRouter(prefix="/api/purchases", tags=["Purchases"])

MONEY = Decimal("0.01")


class PurchaseLineInput(BaseModel):
    item_id: int
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    unit_id: int
    unit_rate: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    remarks: str | None = Field(default=None, max_length=500)


class PurchaseCreate(BaseModel):
    supplier_id: int
    invoice_number: str = Field(min_length=1, max_length=100)
    purchase_date: date
    discount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=2)
    extra_charges: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=2)
    remarks: str | None = None
    items: list[PurchaseLineInput] = Field(min_length=1)

    @field_validator("invoice_number")
    @classmethod
    def clean_invoice_number(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Invoice number cannot be empty")
        return value


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def serialize_purchase(db: Session, purchase: Purchase) -> dict:
    lines = (
        db.query(PurchaseItem)
        .filter(
            PurchaseItem.purchase_id == purchase.id,
            PurchaseItem.campus_id == purchase.campus_id,
        )
        .order_by(PurchaseItem.id)
        .all()
    )

    supplier = db.query(Supplier).filter(
        Supplier.id == purchase.supplier_id,
        Supplier.campus_id == purchase.campus_id,
    ).first()

    return {
        "id": purchase.id,
        "supplier_id": purchase.supplier_id,
        "supplier_name": supplier.name if supplier else None,
        "invoice_number": purchase.invoice_number,
        "purchase_date": purchase.purchase_date,
        "subtotal": purchase.subtotal,
        "discount": purchase.discount,
        "extra_charges": purchase.extra_charges,
        "grand_total": purchase.grand_total,
        "remarks": purchase.remarks,
        "status": purchase.status,
        "created_at": purchase.created_at,
        "items": [
            {
                "id": line.id,
                "item_id": line.item_id,
                "quantity": line.quantity,
                "unit_id": line.unit_id,
                "unit_rate": line.unit_rate,
                "line_total": line.line_total,
                "remarks": line.remarks,
            }
            for line in lines
        ],
    }


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_purchase(
    payload: PurchaseCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.ACCOUNTS)),
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

        # Validate that a conversion to the item's standard unit exists.
        # The entered quantity and unit are preserved on the purchase line.
        get_unit_conversion_factor(
            db,
            user,
            selected_unit.id,
            standard_unit.id,
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
        })

    subtotal = money(subtotal)
    discount = money(payload.discount)
    extra_charges = money(payload.extra_charges)

    if discount > subtotal:
        raise HTTPException(
            status_code=422,
            detail="Discount cannot exceed the purchase subtotal",
        )

    grand_total = money(subtotal - discount + extra_charges)

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
            },
        )

        db.commit()
        db.refresh(purchase)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Purchase could not be saved because of a duplicate or invalid record",
        )

    return jsonable_encoder(serialize_purchase(db, purchase))


@router.get("/")
def list_purchases(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.ACCOUNTS)),
):
    purchases = (
        db.query(Purchase)
        .filter(Purchase.campus_id == user.campus_id)
        .order_by(Purchase.purchase_date.desc(), Purchase.id.desc())
        .all()
    )

    return jsonable_encoder([
        serialize_purchase(db, purchase)
        for purchase in purchases
    ])


@router.get("/{purchase_id}")
def get_purchase(
    purchase_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.ACCOUNTS)),
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
        raise HTTPException(status_code=404, detail="Purchase not found")

    return jsonable_encoder(serialize_purchase(db, purchase))
