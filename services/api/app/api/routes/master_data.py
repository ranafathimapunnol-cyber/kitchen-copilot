from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.dependencies import get_current_user, require_roles
from app.models.user import User, UserRole
from app.models.audit_log import AuditLog
from app.models.master_data import (
    Category,
    Unit,
    UnitConversion,
    Item,
    Supplier,
    MealSession,
    Menu,
    MenuMainItem,
)

router = APIRouter(prefix="/api/master", tags=["Master Data"])


# ---------------------------------------------------------------------
# REQUEST SCHEMAS
# ---------------------------------------------------------------------

class MasterInput(BaseModel):
    name: str = Field(min_length=1, max_length=150)


class CategoryInput(MasterInput):
    description: str | None = Field(default=None, max_length=500)


class UnitInput(MasterInput):
    symbol: str = Field(min_length=1, max_length=20)
    dimension: Literal["weight", "volume", "count", "other"]


class ItemInput(MasterInput):
    category_id: int
    standard_unit_id: int
    minimum_stock: Decimal = Field(default=Decimal("0"), ge=0)
    description: str | None = Field(default=None, max_length=500)


class SupplierInput(MasterInput):
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=500)


class MenuInput(MasterInput):
    meal_session_id: int


class MealSessionInput(MasterInput):
    pass


class UnitConversionInput(BaseModel):
    from_unit_id: int
    to_unit_id: int
    factor: Decimal = Field(gt=0, max_digits=18, decimal_places=6)


class MenuMainItemInput(BaseModel):
    menu_id: int
    item_id: int
    quantity_per_person: Decimal = Field(
        gt=0, max_digits=18, decimal_places=3
    )
    unit_id: int


# ---------------------------------------------------------------------
# SHARED HELPERS
# ---------------------------------------------------------------------

def record_audit(
    db: Session,
    user: User,
    action: str,
    entity_type: str,
    entity_id: int,
    details=None,
):
    db.add(
        AuditLog(
            campus_id=user.campus_id,
            user_id=user.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=jsonable_encoder(details or {}),
        )
    )


def list_records(model, db: Session, user: User):
    return (
        db.query(model)
        .filter(model.campus_id == user.campus_id)
        .order_by(model.id.desc())
        .all()
    )


def create_record(
    model,
    values: dict,
    db: Session,
    user: User,
    entity_type: str,
):
    try:
        record = model(campus_id=user.campus_id, **values)
        db.add(record)
        db.flush()

        record_audit(
            db,
            user,
            "CREATE",
            entity_type,
            record.id,
            values,
        )

        db.commit()
        db.refresh(record)
        return record

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"{entity_type.replace('_', ' ').title()} already exists or violates a database constraint.",
        )


def ensure_campus_record(model, record_id: int, db: Session, user: User):
    record = (
        db.query(model)
        .filter(
            model.id == record_id,
            model.campus_id == user.campus_id,
        )
        .first()
    )

    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    return record


def get_unit_conversion_factor(
    db: Session,
    user: User,
    from_unit_id: int,
    to_unit_id: int,
) -> Decimal:
    """
    Return the multiplier for converting from_unit to to_unit.

    Stored rule:
        quantity_in_to_unit = quantity_in_from_unit * factor

    Reverse conversions use the reciprocal factor.
    """
    if from_unit_id == to_unit_id:
        return Decimal("1")

    conversion = (
        db.query(UnitConversion)
        .filter(
            UnitConversion.campus_id == user.campus_id,
            UnitConversion.from_unit_id == from_unit_id,
            UnitConversion.to_unit_id == to_unit_id,
        )
        .first()
    )

    if conversion:
        return Decimal(str(conversion.factor))

    reverse_conversion = (
        db.query(UnitConversion)
        .filter(
            UnitConversion.campus_id == user.campus_id,
            UnitConversion.from_unit_id == to_unit_id,
            UnitConversion.to_unit_id == from_unit_id,
        )
        .first()
    )

    if reverse_conversion:
        return Decimal("1") / Decimal(str(reverse_conversion.factor))

    raise HTTPException(
        status_code=422,
        detail=(
            "An explicit unit conversion is required between "
            "the item's standard unit and the selected unit."
        ),
    )


# ---------------------------------------------------------------------
# CATEGORIES
# ---------------------------------------------------------------------

@router.get("/categories")
def get_categories(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.KITCHEN_MANAGER)),
):
    return list_records(Category, db, user)


@router.post("/categories", status_code=201)
def add_category(
    data: CategoryInput,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.KITCHEN_MANAGER)),
):
    return create_record(
        Category, data.model_dump(), db, user, "CATEGORY"
    )


# ---------------------------------------------------------------------
# UNITS
# ---------------------------------------------------------------------

@router.get("/units")
def get_units(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.KITCHEN_MANAGER)),
):
    return list_records(Unit, db, user)


@router.post("/units", status_code=201)
def add_unit(
    data: UnitInput,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.KITCHEN_MANAGER)),
):
    return create_record(
        Unit, data.model_dump(), db, user, "UNIT"
    )


# ---------------------------------------------------------------------
# UNIT CONVERSIONS
# ---------------------------------------------------------------------

@router.get("/unit-conversions")
def get_unit_conversions(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.KITCHEN_MANAGER)),
):
    return list_records(UnitConversion, db, user)


@router.post("/unit-conversions", status_code=201)
def add_unit_conversion(
    data: UnitConversionInput,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.KITCHEN_MANAGER)),
):
    if data.from_unit_id == data.to_unit_id:
        raise HTTPException(
            status_code=422,
            detail="Source and destination units must be different.",
        )

    from_unit = ensure_campus_record(
        Unit, data.from_unit_id, db, user
    )
    to_unit = ensure_campus_record(
        Unit, data.to_unit_id, db, user
    )

    if from_unit.dimension != to_unit.dimension:
        raise HTTPException(
            status_code=422,
            detail="Conversions between different dimensions are not allowed.",
        )

    return create_record(
        UnitConversion,
        data.model_dump(),
        db,
        user,
        "UNIT_CONVERSION",
    )


# ---------------------------------------------------------------------
# ITEMS
# ---------------------------------------------------------------------

@router.get("/items")
def get_items(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.KITCHEN_MANAGER)),
):
    return list_records(Item, db, user)


@router.post("/items", status_code=201)
def add_item(
    data: ItemInput,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.KITCHEN_MANAGER)),
):
    category = ensure_campus_record(
        Category, data.category_id, db, user
    )
    unit = ensure_campus_record(
        Unit, data.standard_unit_id, db, user
    )

    if not category.is_active:
        raise HTTPException(
            status_code=422,
            detail="Cannot assign an inactive category to an item.",
        )

    if not unit.is_active:
        raise HTTPException(
            status_code=422,
            detail="Cannot assign an inactive unit to an item.",
        )

    return create_record(
        Item, data.model_dump(), db, user, "ITEM"
    )


# ---------------------------------------------------------------------
# SUPPLIERS
# ---------------------------------------------------------------------

@router.get("/suppliers")
def get_suppliers(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.ACCOUNTS)),
):
    return list_records(Supplier, db, user)


@router.post("/suppliers", status_code=201)
def add_supplier(
    data: SupplierInput,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.ACCOUNTS)),
):
    return create_record(
        Supplier, data.model_dump(), db, user, "SUPPLIER"
    )


# ---------------------------------------------------------------------
# MEAL SESSIONS
# ---------------------------------------------------------------------

@router.get("/meal-sessions")
def get_meal_sessions(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.KITCHEN_MANAGER)),
):
    return list_records(MealSession, db, user)


@router.post("/meal-sessions", status_code=201)
def add_meal_session(
    data: MealSessionInput,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.KITCHEN_MANAGER)),
):
    return create_record(
        MealSession, data.model_dump(), db, user, "MEAL_SESSION"
    )


# ---------------------------------------------------------------------
# MENUS
# ---------------------------------------------------------------------

@router.get("/menus")
def get_menus(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.KITCHEN_MANAGER)),
):
    return list_records(Menu, db, user)


@router.post("/menus", status_code=201)
def add_menu(
    data: MenuInput,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.KITCHEN_MANAGER)),
):
    meal_session = ensure_campus_record(
        MealSession, data.meal_session_id, db, user
    )

    if not meal_session.is_active:
        raise HTTPException(
            status_code=422,
            detail="Cannot assign an inactive meal session to a menu.",
        )

    return create_record(
        Menu, data.model_dump(), db, user, "MENU"
    )


# ---------------------------------------------------------------------
# MENU MAIN ITEMS
# ---------------------------------------------------------------------

@router.get("/menu-main-items")
def get_menu_main_items(
    menu_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.KITCHEN_MANAGER)),
):
    query = db.query(MenuMainItem).filter(
        MenuMainItem.campus_id == user.campus_id
    )

    if menu_id is not None:
        ensure_campus_record(Menu, menu_id, db, user)
        query = query.filter(MenuMainItem.menu_id == menu_id)

    return query.order_by(MenuMainItem.id.desc()).all()


@router.post("/menu-main-items", status_code=201)
def add_menu_main_item(
    data: MenuMainItemInput,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.KITCHEN_MANAGER)),
):
    menu = ensure_campus_record(
        Menu, data.menu_id, db, user
    )
    item = ensure_campus_record(
        Item, data.item_id, db, user
    )
    selected_unit = ensure_campus_record(
        Unit, data.unit_id, db, user
    )
    standard_unit = ensure_campus_record(
        Unit, item.standard_unit_id, db, user
    )

    if not menu.is_active:
        raise HTTPException(
            status_code=422,
            detail="Cannot add items to an inactive menu.",
        )

    if not item.is_active:
        raise HTTPException(
            status_code=422,
            detail="Cannot add an inactive item to a menu.",
        )

    if not selected_unit.is_active or not standard_unit.is_active:
        raise HTTPException(
            status_code=422,
            detail="Inactive units cannot be used in menu quantities.",
        )

    if selected_unit.dimension != standard_unit.dimension:
        raise HTTPException(
            status_code=422,
            detail="The menu quantity unit must have the same dimension as the item's standard unit.",
        )

    # Validate that the selected quantity can be converted
    # into the item's standard unit.
    get_unit_conversion_factor(
        db,
        user,
        selected_unit.id,
        standard_unit.id,
    )

    return create_record(
        MenuMainItem,
        data.model_dump(),
        db,
        user,
        "MENU_MAIN_ITEM",
    )
