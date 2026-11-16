
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import require_permission, require_roles
from app.api.routes.master_data import record_audit
from app.db.session import get_db
from app.models.master_data import Item, MealSession, Menu, Unit
from app.models.user import User, UserRole
from app.models.waste import WasteItem, WasteRecord


router = APIRouter(tags=["Waste Tracking"])


# ============================================================
# REQUEST SCHEMAS
# ============================================================

class WasteItemInput(BaseModel):
    waste_type: Literal["RAW_INGREDIENT", "PREPARED_FOOD"]

    item_id: int | None = None
    food_name: str | None = Field(default=None, max_length=150)

    menu_id: int | None = None
    unit_id: int

    quantity: Decimal = Field(
        gt=0,
        max_digits=18,
        decimal_places=3,
    )

    waste_stage: Literal[
        "STORAGE",
        "PREPARATION",
        "COOKING",
        "SERVING",
        "AFTER_MEAL",
    ]

    waste_reason: Literal[
        "SPOILED",
        "EXPIRED",
        "DAMAGED",
        "OVERPRODUCTION",
        "LEFTOVER",
        "PLATE_WASTE",
        "OTHER",
    ]

    estimated_cost: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        max_digits=18,
        decimal_places=2,
    )


class WasteRecordCreate(BaseModel):
    waste_date: date | None = None
    meal_session_id: int | None = None
    notes: str | None = Field(default=None, max_length=2000)
    items: list[WasteItemInput] = Field(min_length=1)


class WasteRecordUpdate(BaseModel):
    waste_date: date | None = None
    meal_session_id: int | None = None
    notes: str | None = Field(default=None, max_length=2000)
    items: list[WasteItemInput] | None = Field(default=None, min_length=1)


# ============================================================
# VALIDATION HELPERS
# ============================================================

def validate_meal_session(
    db: Session,
    meal_session_id: int | None,
    campus_id: int,
):
    if meal_session_id is None:
        return

    session = (
        db.query(MealSession)
        .filter(
            MealSession.id == meal_session_id,
            MealSession.campus_id == campus_id,
        )
        .first()
    )

    if not session:
        raise HTTPException(
            status_code=404,
            detail="Meal session not found in this campus",
        )


def prepare_waste_item(
    db: Session,
    payload: WasteItemInput,
    campus_id: int,
) -> dict:
    """
    Validate related records and prepare a WasteItem row.

    RAW_INGREDIENT:
        Uses the existing inventory Item.

    PREPARED_FOOD:
        Uses the supplied food_name.
    """

    unit = (
        db.query(Unit)
        .filter(
            Unit.id == payload.unit_id,
            Unit.campus_id == campus_id,
        )
        .first()
    )

    if not unit:
        raise HTTPException(
            status_code=404,
            detail="Unit not found in this campus",
        )

    item_name = None

    if payload.menu_id is not None:
        menu = (
            db.query(Menu)
            .filter(
                Menu.id == payload.menu_id,
                Menu.campus_id == campus_id,
            )
            .first()
        )

        if not menu:
            raise HTTPException(
                status_code=404,
                detail="Menu not found in this campus",
            )

    if payload.waste_type == "RAW_INGREDIENT":

        if payload.item_id is None:
            raise HTTPException(
                status_code=422,
                detail="item_id is required for raw ingredient waste",
            )

        item = (
            db.query(Item)
            .filter(
                Item.id == payload.item_id,
                Item.campus_id == campus_id,
            )
            .first()
        )

        if not item:
            raise HTTPException(
                status_code=404,
                detail="Inventory item not found in this campus",
            )

        item_name = item.name

    else:
        if payload.item_id is not None:
            raise HTTPException(
                status_code=422,
                detail="Prepared food must not reference an inventory item",
            )

        if not payload.food_name or not payload.food_name.strip():
            raise HTTPException(
                status_code=422,
                detail="food_name is required for prepared food waste",
            )

        item_name = payload.food_name.strip()

    return {
        "item_id": payload.item_id,
        "menu_id": payload.menu_id,
        "unit_id": payload.unit_id,
        "food_name": item_name,
        "waste_type": payload.waste_type,
        "quantity": payload.quantity,
        "waste_stage": payload.waste_stage,
        "waste_reason": payload.waste_reason,
        "estimated_cost": payload.estimated_cost,
    }


# ============================================================
# GET RECORD
# ============================================================

def get_waste_record(
    record_id: int,
    db: Session,
    user: User,
) -> WasteRecord:

    record = (
        db.query(WasteRecord)
        .filter(
            WasteRecord.id == record_id,
            WasteRecord.campus_id == user.campus_id,
        )
        .first()
    )

    if not record:
        raise HTTPException(
            status_code=404,
            detail="Waste record not found",
        )

    return record


# ============================================================
# SERIALIZE RECORD
# ============================================================

def serialize_waste_record(
    db: Session,
    record: WasteRecord,
) -> dict:

    lines = (
        db.query(WasteItem)
        .filter(
            WasteItem.waste_record_id == record.id,
            WasteItem.campus_id == record.campus_id,
        )
        .order_by(WasteItem.id)
        .all()
    )

    items = []

    for line in lines:

        unit = (
            db.query(Unit)
            .filter(
                Unit.id == line.unit_id,
                Unit.campus_id == record.campus_id,
            )
            .first()
        )

        menu = None

        if line.menu_id is not None:
            menu = (
                db.query(Menu)
                .filter(
                    Menu.id == line.menu_id,
                    Menu.campus_id == record.campus_id,
                )
                .first()
            )

        items.append({
            "id": line.id,
            "item_id": line.item_id,
            "food_name": line.food_name,
            "waste_type": line.waste_type,
            "menu_id": line.menu_id,
            "menu_name": menu.name if menu else None,
            "unit_id": line.unit_id,
            "unit_name": unit.name if unit else None,
            "unit_symbol": unit.symbol if unit else None,
            "quantity": line.quantity,
            "waste_stage": line.waste_stage,
            "waste_reason": line.waste_reason,
            "estimated_cost": line.estimated_cost,
        })

    return {
        "id": record.id,
        "waste_date": record.waste_date,
        "meal_session_id": record.meal_session_id,
        "recorded_by": record.recorded_by,
        "notes": record.notes,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "items": items,
    }


# ============================================================
# CREATE WASTE RECORD
# Permission: waste_tracking.create
# ============================================================

@router.post(
    "/api/waste/records",
    status_code=status.HTTP_201_CREATED,
)
def create_waste_record(
    payload: WasteRecordCreate,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_permission("waste_tracking.create")
    ),
):

    validate_meal_session(
        db,
        payload.meal_session_id,
        user.campus_id,
    )

    prepared_items = [
        prepare_waste_item(db, line, user.campus_id)
        for line in payload.items
    ]

    record = WasteRecord(
        campus_id=user.campus_id,
        waste_date=payload.waste_date or date.today(),
        meal_session_id=payload.meal_session_id,
        recorded_by=user.id,
        notes=payload.notes,
    )

    try:
        db.add(record)
        db.flush()

        for line in prepared_items:
            db.add(
                WasteItem(
                    campus_id=user.campus_id,
                    waste_record_id=record.id,
                    **line,
                )
            )

        record_audit(
            db,
            user,
            "CREATE",
            "WASTE_RECORD",
            record.id,
            {
                "item_count": len(prepared_items),
                "waste_date": str(record.waste_date),
            },
        )

        db.commit()
        db.refresh(record)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Waste record could not be saved",
        )

    return jsonable_encoder(
        serialize_waste_record(db, record)
    )


# ============================================================
# LIST WASTE RECORDS
# Permission: waste_tracking.read
# ============================================================

@router.get("/api/waste/records")
def list_waste_records(
    waste_date: date | None = Query(default=None),
    meal_session_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(
        require_permission("waste_tracking.read")
    ),
):

    query = db.query(WasteRecord).filter(
        WasteRecord.campus_id == user.campus_id,
    )

    if waste_date is not None:
        query = query.filter(
            WasteRecord.waste_date == waste_date,
        )

    if meal_session_id is not None:
        query = query.filter(
            WasteRecord.meal_session_id == meal_session_id,
        )

    records = (
        query
        .order_by(
            WasteRecord.waste_date.desc(),
            WasteRecord.id.desc(),
        )
        .all()
    )

    return jsonable_encoder([
        serialize_waste_record(db, record)
        for record in records
    ])


# ============================================================
# GET WASTE RECORD DETAILS
# Permission: waste_tracking.read
# ============================================================

@router.get("/api/waste/records/{record_id}")
def get_waste_record_detail(
    record_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_permission("waste_tracking.read")
    ),
):

    record = get_waste_record(
        record_id,
        db,
        user,
    )

    return jsonable_encoder(
        serialize_waste_record(db, record)
    )


# ============================================================
# UPDATE WASTE RECORD
# Permission: waste_tracking.update
# ============================================================

@router.patch("/api/waste/records/{record_id}")
def update_waste_record(
    record_id: int,
    payload: WasteRecordUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_permission("waste_tracking.update")
    ),
):

    record = get_waste_record(
        record_id,
        db,
        user,
    )

    changes = payload.model_dump(exclude_unset=True)

    if "meal_session_id" in changes:
        validate_meal_session(
            db,
            changes["meal_session_id"],
            user.campus_id,
        )

    prepared_items = None

    if "items" in changes:
        prepared_items = [
            prepare_waste_item(db, line, user.campus_id)
            for line in payload.items
        ]

    try:
        if "waste_date" in changes:
            record.waste_date = changes["waste_date"]

        if "meal_session_id" in changes:
            record.meal_session_id = changes["meal_session_id"]

        if "notes" in changes:
            record.notes = changes["notes"]

        if prepared_items is not None:

            db.query(WasteItem).filter(
                WasteItem.waste_record_id == record.id,
                WasteItem.campus_id == user.campus_id,
            ).delete(synchronize_session=False)

            for line in prepared_items:
                db.add(
                    WasteItem(
                        campus_id=user.campus_id,
                        waste_record_id=record.id,
                        **line,
                    )
                )

        record_audit(
            db,
            user,
            "UPDATE",
            "WASTE_RECORD",
            record.id,
            {
                "updated_fields": list(changes.keys()),
            },
        )

        db.commit()
        db.refresh(record)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Waste record could not be updated",
        )

    return jsonable_encoder(
        serialize_waste_record(db, record)
    )


# ============================================================
# DELETE WASTE RECORD
# Admin only
# ============================================================

@router.delete("/api/waste/records/{record_id}")
def delete_waste_record(
    record_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_roles(UserRole.ADMIN)
    ),
):

    record = get_waste_record(
        record_id,
        db,
        user,
    )

    try:
        item_count = (
            db.query(WasteItem)
            .filter(
                WasteItem.waste_record_id == record.id,
                WasteItem.campus_id == user.campus_id,
            )
            .count()
        )

        record_audit(
            db,
            user,
            "DELETE",
            "WASTE_RECORD",
            record.id,
            {
                "item_count": item_count,
                "waste_date": str(record.waste_date),
            },
        )

        db.query(WasteItem).filter(
            WasteItem.waste_record_id == record.id,
            WasteItem.campus_id == user.campus_id,
        ).delete(synchronize_session=False)

        db.delete(record)
        db.commit()

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Waste record could not be deleted",
        )

    return {
        "message": "Waste record deleted successfully",
        "record_id": record_id,
    }
