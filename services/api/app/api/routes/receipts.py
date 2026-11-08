from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.dependencies import get_current_user, require_roles
from app.api.routes.master_data import (
    get_unit_conversion_factor,
    record_audit,
)
from app.models.user import User, UserRole
from app.models.master_data import Item, Unit
from app.models.purchases import (
    Purchase,
    PurchaseItem,
    GoodsReceipt,
    GoodsReceiptItem,
    StockMovement,
)

router = APIRouter(tags=["Goods Receipts"])

QUANTITY_STEP = Decimal("0.001")


def quantity(value: Decimal) -> Decimal:
    return value.quantize(QUANTITY_STEP, rounding=ROUND_HALF_UP)


class ReceiptLineInput(BaseModel):
    purchase_item_id: int
    quantity_received: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    quantity_accepted: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=3)
    quantity_rejected: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=3)
    remarks: str | None = Field(default=None, max_length=500)


class ReceiptCreate(BaseModel):
    receipt_date: date | None = None
    remarks: str | None = None
    items: list[ReceiptLineInput] = Field(min_length=1)


def get_receipt(receipt_id: int, db: Session, user: User) -> GoodsReceipt:
    receipt = (
        db.query(GoodsReceipt)
        .filter(
            GoodsReceipt.id == receipt_id,
            GoodsReceipt.campus_id == user.campus_id,
        )
        .first()
    )
    if not receipt:
        raise HTTPException(status_code=404, detail="Goods receipt not found")
    return receipt


def serialize_receipt(db: Session, receipt: GoodsReceipt) -> dict:
    lines = (
        db.query(GoodsReceiptItem)
        .filter(
            GoodsReceiptItem.receipt_id == receipt.id,
            GoodsReceiptItem.campus_id == receipt.campus_id,
        )
        .order_by(GoodsReceiptItem.id)
        .all()
    )

    result = []
    for line in lines:
        purchase_line = db.query(PurchaseItem).filter(
            PurchaseItem.id == line.purchase_item_id,
            PurchaseItem.campus_id == receipt.campus_id,
        ).first()

        item = None
        if purchase_line:
            item = db.query(Item).filter(
                Item.id == purchase_line.item_id,
                Item.campus_id == receipt.campus_id,
            ).first()

        result.append({
            "id": line.id,
            "purchase_item_id": line.purchase_item_id,
            "item_id": purchase_line.item_id if purchase_line else None,
            "item_name": item.name if item else None,
            "quantity_received": line.quantity_received,
            "quantity_accepted": line.quantity_accepted,
            "quantity_rejected": line.quantity_rejected,
            "remarks": line.remarks,
        })

    return {
        "id": receipt.id,
        "purchase_id": receipt.purchase_id,
        "receipt_date": receipt.receipt_date,
        "status": receipt.status,
        "remarks": receipt.remarks,
        "accepted_by": receipt.accepted_by,
        "accepted_at": receipt.accepted_at,
        "created_by": receipt.created_by,
        "created_at": receipt.created_at,
        "items": result,
    }


@router.post(
    "/api/purchases/{purchase_id}/receipts",
    status_code=status.HTTP_201_CREATED,
)
def create_receipt(
    purchase_id: int,
    payload: ReceiptCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.KITCHEN_MANAGER, UserRole.STORE_KEEPER)),
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

    line_ids = [line.purchase_item_id for line in payload.items]
    if len(line_ids) != len(set(line_ids)):
        raise HTTPException(
            status_code=422,
            detail="A purchase item can appear only once in a receipt",
        )

    prepared = []

    for line in payload.items:
        purchase_line = (
            db.query(PurchaseItem)
            .filter(
                PurchaseItem.id == line.purchase_item_id,
                PurchaseItem.purchase_id == purchase.id,
                PurchaseItem.campus_id == user.campus_id,
            )
            .first()
        )
        if not purchase_line:
            raise HTTPException(
                status_code=404,
                detail=f"Purchase item {line.purchase_item_id} not found in this purchase",
            )

        received = quantity(line.quantity_received)
        accepted = quantity(line.quantity_accepted)
        rejected = quantity(line.quantity_rejected)

        if accepted + rejected > received:
            raise HTTPException(
                status_code=422,
                detail="Accepted and rejected quantities cannot exceed received quantity",
            )

        # Include draft receipts too, so quantities already recorded are reserved.
        previously_received = (
            db.query(GoodsReceiptItem)
            .join(
                GoodsReceipt,
                GoodsReceipt.id == GoodsReceiptItem.receipt_id,
            )
            .filter(
                GoodsReceiptItem.purchase_item_id == purchase_line.id,
                GoodsReceiptItem.campus_id == user.campus_id,
                GoodsReceipt.campus_id == user.campus_id,
            )
        ).with_entities(
            GoodsReceiptItem.quantity_received
        ).all()

        already_recorded = sum(
            (Decimal(str(row[0])) for row in previously_received),
            Decimal("0"),
        )

        if already_recorded + received > Decimal(str(purchase_line.quantity)):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Receipt quantity exceeds the remaining purchased quantity "
                    f"for purchase item {purchase_line.id}"
                ),
            )

        prepared.append({
            "purchase_item_id": purchase_line.id,
            "quantity_received": received,
            "quantity_accepted": accepted,
            "quantity_rejected": rejected,
            "remarks": line.remarks,
        })

    receipt = GoodsReceipt(
        campus_id=user.campus_id,
        purchase_id=purchase.id,
        receipt_date=payload.receipt_date or datetime.now(timezone.utc).date(),
        status="DRAFT",
        remarks=payload.remarks,
        created_by=user.id,
    )

    try:
        db.add(receipt)
        db.flush()

        for line in prepared:
            db.add(
                GoodsReceiptItem(
                    campus_id=user.campus_id,
                    receipt_id=receipt.id,
                    **line,
                )
            )

        record_audit(
            db,
            user,
            "CREATE",
            "GOODS_RECEIPT",
            receipt.id,
            {
                "purchase_id": purchase.id,
                "item_count": len(prepared),
            },
        )

        db.commit()
        db.refresh(receipt)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Goods receipt could not be saved",
        )

    return jsonable_encoder(serialize_receipt(db, receipt))


@router.get("/api/purchases/{purchase_id}/receipts")
def list_purchase_receipts(
    purchase_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.KITCHEN_MANAGER, UserRole.STORE_KEEPER)),
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

    receipts = (
        db.query(GoodsReceipt)
        .filter(
            GoodsReceipt.purchase_id == purchase.id,
            GoodsReceipt.campus_id == user.campus_id,
        )
        .order_by(GoodsReceipt.id.desc())
        .all()
    )

    return jsonable_encoder([
        serialize_receipt(db, receipt)
        for receipt in receipts
    ])


@router.get("/api/receipts/{receipt_id}")
def get_receipt_detail(
    receipt_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.KITCHEN_MANAGER, UserRole.STORE_KEEPER)),
):
    receipt = get_receipt(receipt_id, db, user)
    return jsonable_encoder(serialize_receipt(db, receipt))


@router.post("/api/receipts/{receipt_id}/accept")
def accept_receipt(
    receipt_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.KITCHEN_MANAGER, UserRole.STORE_KEEPER)),
):
    receipt = (
        db.query(GoodsReceipt)
        .filter(
            GoodsReceipt.id == receipt_id,
            GoodsReceipt.campus_id == user.campus_id,
        )
        .with_for_update()
        .first()
    )
    if not receipt:
        raise HTTPException(status_code=404, detail="Goods receipt not found")

    if receipt.status != "DRAFT":
        raise HTTPException(
            status_code=409,
            detail="Only draft receipts can be accepted",
        )

    lines = (
        db.query(GoodsReceiptItem)
        .filter(
            GoodsReceiptItem.receipt_id == receipt.id,
            GoodsReceiptItem.campus_id == user.campus_id,
        )
        .order_by(GoodsReceiptItem.id)
        .all()
    )

    if not lines:
        raise HTTPException(status_code=422, detail="Receipt has no items")

    # Validate every line and conversion before adding any stock movements.
    movements = []

    for line in lines:
        received = Decimal(str(line.quantity_received))
        accepted = Decimal(str(line.quantity_accepted))
        rejected = Decimal(str(line.quantity_rejected))

        if accepted + rejected != received:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Accepted and rejected quantities must equal received quantity "
                    f"for receipt item {line.id}"
                ),
            )

        purchase_line = (
            db.query(PurchaseItem)
            .filter(
                PurchaseItem.id == line.purchase_item_id,
                PurchaseItem.campus_id == user.campus_id,
                PurchaseItem.purchase_id == receipt.purchase_id,
            )
            .first()
        )
        if not purchase_line:
            raise HTTPException(
                status_code=404,
                detail="Related purchase item not found",
            )

        item = (
            db.query(Item)
            .filter(
                Item.id == purchase_line.item_id,
                Item.campus_id == user.campus_id,
            )
            .first()
        )
        if not item:
            raise HTTPException(status_code=404, detail="Related item not found")

        standard_unit = (
            db.query(Unit)
            .filter(
                Unit.id == item.standard_unit_id,
                Unit.campus_id == user.campus_id,
            )
            .first()
        )
        purchase_unit = (
            db.query(Unit)
            .filter(
                Unit.id == purchase_line.unit_id,
                Unit.campus_id == user.campus_id,
            )
            .first()
        )
        if not standard_unit or not purchase_unit:
            raise HTTPException(
                status_code=422,
                detail=f"Valid units are required for item {item.name}",
            )

        if accepted > 0:
            factor = get_unit_conversion_factor(
                db,
                user,
                purchase_unit.id,
                standard_unit.id,
            )
            standard_quantity = quantity(accepted * factor)

            if standard_quantity <= 0:
                raise HTTPException(
                    status_code=422,
                    detail=f"Converted quantity is invalid for item {item.name}",
                )

            existing_movement = (
                db.query(StockMovement)
                .filter(
                    StockMovement.campus_id == user.campus_id,
                    StockMovement.receipt_item_id == line.id,
                )
                .first()
            )
            if existing_movement:
                raise HTTPException(
                    status_code=409,
                    detail=f"Stock was already posted for receipt item {line.id}",
                )

            movements.append({
                "item_id": item.id,
                "movement_type": "RECEIPT",
                "quantity": standard_quantity,
                "unit_id": standard_unit.id,
                "receipt_item_id": line.id,
                "reference_type": "GOODS_RECEIPT",
                "reference_id": receipt.id,
                "remarks": line.remarks or receipt.remarks,
                "created_by": user.id,
            })

    try:
        for movement in movements:
            db.add(
                StockMovement(
                    campus_id=user.campus_id,
                    **movement,
                )
            )

        receipt.status = "ACCEPTED"
        receipt.accepted_by = user.id
        receipt.accepted_at = datetime.now(timezone.utc)

        record_audit(
            db,
            user,
            "ACCEPT",
            "GOODS_RECEIPT",
            receipt.id,
            {
                "stock_movement_count": len(movements),
                "accepted_item_count": len(movements),
            },
        )

        db.commit()
        db.refresh(receipt)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Receipt stock was already posted or the receipt could not be accepted",
        )

    return jsonable_encoder(serialize_receipt(db, receipt))


@router.get("/api/stock/movements")
def list_stock_movements(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.KITCHEN_MANAGER, UserRole.STORE_KEEPER)),
):
    movements = (
        db.query(StockMovement)
        .filter(StockMovement.campus_id == user.campus_id)
        .order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
        .all()
    )

    return jsonable_encoder([
        {
            "id": movement.id,
            "item_id": movement.item_id,
            "movement_type": movement.movement_type,
            "quantity": movement.quantity,
            "unit_id": movement.unit_id,
            "receipt_item_id": movement.receipt_item_id,
            "reference_type": movement.reference_type,
            "reference_id": movement.reference_id,
            "remarks": movement.remarks,
            "created_by": movement.created_by,
            "created_at": movement.created_at,
        }
        for movement in movements
    ])
