
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_current_user,
    require_permission,
)
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.authorization import Permission, StaffAccessAssignment
from app.models.master_data import (
    Category,
    Item,
    MealSession,
    Menu,
    MenuMainItem,
    Supplier,
    Unit,
    UnitConversion,
)
from app.models.purchases import (
    GoodsReceiptItem,
    PurchaseItem,
    StockMovement,
)
from app.models.user import User, UserRole
from app.models.waste import WasteItem

router = APIRouter(prefix="/api/master", tags=["Master Data"])


# ============================================================
# REQUEST SCHEMAS
# ============================================================

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


# ============================================================
# AUDIT HELPER
# ============================================================

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


# ============================================================
# PERMISSION HELPER
# ============================================================

def has_module_permission(
    user: User,
    db: Session,
    module_code: str,
    action: str,
) -> bool:

    permission_code = f"{module_code}.{action}"

    if user.role == UserRole.ADMIN:
        return True

    if user.role == UserRole.KITCHEN_MANAGER:
        from app.api.dependencies import KITCHEN_MANAGER_PERMISSIONS

        return permission_code in KITCHEN_MANAGER_PERMISSIONS

    if user.role == UserRole.STAFF:
        assignment = (
            db.query(StaffAccessAssignment)
            .join(
                Permission,
                StaffAccessAssignment.permission_id == Permission.id,
            )
            .filter(
                StaffAccessAssignment.staff_user_id == user.id,
                StaffAccessAssignment.is_active.is_(True),
                Permission.permission_code == permission_code,
            )
            .first()
        )

        return assignment is not None

    return False


# ============================================================
# SHARED DATABASE HELPERS
# ============================================================

def list_records(
    model,
    db: Session,
    user: User,
    page: int = 1,
    page_size: int = 10,
    query=None,
):
    records_query = query if query is not None else db.query(model)

    records_query = records_query.filter(
        model.campus_id == user.campus_id
    )

    total = records_query.count()

    items = (
        records_query
        .order_by(model.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size,
    }


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
            detail=(
                f"{entity_type.replace('_', ' ').title()} "
                "already exists or violates a database constraint."
            ),
        )


def ensure_campus_record(
    model,
    record_id: int,
    db: Session,
    user: User,
):
    record = (
        db.query(model)
        .filter(
            model.id == record_id,
            model.campus_id == user.campus_id,
        )
        .first()
    )

    if not record:
        raise HTTPException(
            status_code=404,
            detail="Record not found",
        )

    return record


def get_unit_conversion_factor(
    db: Session,
    user: User,
    from_unit_id: int,
    to_unit_id: int,
) -> Decimal:

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


def ensure_supplier_write_allowed(user: User) -> None:
    """Kitchen Managers have read-only access to suppliers.

    Suppliers share the inventory.* permission codes with other master
    data, so this rule cannot be expressed by the permission set alone.
    """

    if user.role == UserRole.KITCHEN_MANAGER:
        raise HTTPException(
            status_code=403,
            detail="Kitchen Managers have read-only access to suppliers.",
        )


# ============================================================
# CATEGORIES
# ============================================================

@router.get("/categories")
def get_categories(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("inventory.read")),
):
    return list_records(Category, db, user, page, page_size)


@router.post("/categories", status_code=201)
def add_category(
    data: CategoryInput,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("inventory.create")),
):
    return create_record(
        Category, data.model_dump(), db, user, "CATEGORY"
    )


# ============================================================
# UNITS
# ============================================================

@router.get("/units")
def get_units(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("inventory.read")),
):
    return list_records(Unit, db, user, page, page_size)


@router.post("/units", status_code=201)
def add_unit(
    data: UnitInput,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("inventory.create")),
):
    return create_record(
        Unit, data.model_dump(), db, user, "UNIT"
    )


# ============================================================
# UNIT CONVERSIONS
# ============================================================

@router.get("/unit-conversions")
def get_unit_conversions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("inventory.read")),
):
    return list_records(UnitConversion, db, user, page, page_size)


@router.post("/unit-conversions", status_code=201)
def add_unit_conversion(
    data: UnitConversionInput,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("inventory.create")),
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

    ensure_conversion_pair_available(
        db, user, data.from_unit_id, data.to_unit_id
    )

    return create_record(
        UnitConversion,
        data.model_dump(),
        db,
        user,
        "UNIT_CONVERSION",
    )


# ============================================================
# ITEMS
# ============================================================

@router.get("/items")
def get_items(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("inventory.read")),
):
    return list_records(Item, db, user, page, page_size)


@router.post("/items", status_code=201)
def add_item(
    data: ItemInput,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("inventory.create")),
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


# ============================================================
# SUPPLIERS
# ============================================================

@router.get("/suppliers")
def get_suppliers(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("inventory.read")),
):
    return list_records(Supplier, db, user, page, page_size)


@router.post("/suppliers", status_code=201)
def add_supplier(
    data: SupplierInput,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("inventory.create")),
):
    ensure_supplier_write_allowed(user)

    return create_record(
        Supplier, data.model_dump(), db, user, "SUPPLIER"
    )


# ============================================================
# MEAL SESSIONS
# ============================================================

@router.get("/meal-sessions")
def get_meal_sessions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("menu.read")),
):
    return list_records(MealSession, db, user, page, page_size)


@router.post("/meal-sessions", status_code=201)
def add_meal_session(
    data: MealSessionInput,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("menu.create")),
):
    return create_record(
        MealSession, data.model_dump(), db, user, "MEAL_SESSION"
    )


# ============================================================
# MENUS
# ============================================================

@router.get("/menus")
def get_menus(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("menu.read")),
):
    return list_records(Menu, db, user, page, page_size)


@router.post("/menus", status_code=201)
def add_menu(
    data: MenuInput,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("menu.create")),
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


# ============================================================
# MENU MAIN ITEMS
# ============================================================

@router.get("/menu-main-items")
def get_menu_main_items(
    menu_id: int | None = Query(default=None, gt=0),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("menu.read")),
):
    query = db.query(MenuMainItem).filter(
        MenuMainItem.campus_id == user.campus_id
    )

    if menu_id is not None:
        ensure_campus_record(Menu, menu_id, db, user)
        query = query.filter(MenuMainItem.menu_id == menu_id)

    return list_records(
        MenuMainItem, db, user, page, page_size, query
    )


@router.post("/menu-main-items", status_code=201)
def add_menu_main_item(
    data: MenuMainItemInput,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("menu.create")),
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
            detail=(
                "The menu quantity unit must have the same dimension "
                "as the item's standard unit."
            ),
        )

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


# ============================================================
# MASTER RESOURCE CONFIGURATION
# ============================================================

MASTER_RESOURCES = {
    "categories": (
        Category, CategoryInput, "CATEGORY", "inventory"
    ),
    "units": (
        Unit, UnitInput, "UNIT", "inventory"
    ),
    "unit-conversions": (
        UnitConversion, UnitConversionInput,
        "UNIT_CONVERSION", "inventory"
    ),
    "items": (
        Item, ItemInput, "ITEM", "inventory"
    ),
    "suppliers": (
        Supplier, SupplierInput, "SUPPLIER", "inventory"
    ),
    "meal-sessions": (
        MealSession, MealSessionInput, "MEAL_SESSION", "menu"
    ),
    "menus": (
        Menu, MenuInput, "MENU", "menu"
    ),
    "menu-main-items": (
        MenuMainItem, MenuMainItemInput,
        "MENU_MAIN_ITEM", "menu"
    ),
}


# ============================================================
# MASTER DATA VALIDATION
# ============================================================

def validate_master_values(
    resource: str,
    values: dict,
    db: Session,
    user: User,
):
    if resource == "unit-conversions":

        if values["from_unit_id"] == values["to_unit_id"]:
            raise HTTPException(
                422,
                "Source and destination units must differ.",
            )

        source = ensure_campus_record(
            Unit, values["from_unit_id"], db, user
        )

        target = ensure_campus_record(
            Unit, values["to_unit_id"], db, user
        )

        if source.dimension != target.dimension:
            raise HTTPException(
                422,
                "Unit dimensions must match.",
            )

    elif resource == "items":

        category = ensure_campus_record(
            Category, values["category_id"], db, user
        )

        unit = ensure_campus_record(
            Unit, values["standard_unit_id"], db, user
        )

        if not category.is_active or not unit.is_active:
            raise HTTPException(
                422,
                "Inactive categories or units cannot be assigned.",
            )

    elif resource == "menus":

        session = ensure_campus_record(
            MealSession, values["meal_session_id"], db, user
        )

        if not session.is_active:
            raise HTTPException(
                422,
                "An inactive meal session cannot be assigned.",
            )

    elif resource == "menu-main-items":

        menu = ensure_campus_record(
            Menu, values["menu_id"], db, user
        )

        item = ensure_campus_record(
            Item, values["item_id"], db, user
        )

        selected_unit = ensure_campus_record(
            Unit, values["unit_id"], db, user
        )

        standard_unit = ensure_campus_record(
            Unit, item.standard_unit_id, db, user
        )

        if not menu.is_active or not item.is_active:
            raise HTTPException(
                422,
                "Inactive menus or items cannot be used.",
            )

        if not selected_unit.is_active or not standard_unit.is_active:
            raise HTTPException(
                422,
                "Inactive units cannot be used.",
            )

        if selected_unit.dimension != standard_unit.dimension:
            raise HTTPException(
                422,
                "Unit dimensions must match.",
            )

        get_unit_conversion_factor(
            db,
            user,
            selected_unit.id,
            standard_unit.id,
        )


# ============================================================
# HISTORICAL INTEGRITY
# A unit's dimension, an item's standard unit and a used conversion
# give meaning to quantities already recorded. Once referenced, they
# cannot be changed; historical records are never rewritten.
# ============================================================

def has_rows(query) -> bool:
    return query.first() is not None


def find_unit_references(db: Session, unit_id: int) -> list[str]:
    checks = [
        (
            "items",
            db.query(Item.id).filter(Item.standard_unit_id == unit_id),
        ),
        (
            "unit conversions",
            db.query(UnitConversion.id).filter(
                or_(
                    UnitConversion.from_unit_id == unit_id,
                    UnitConversion.to_unit_id == unit_id,
                )
            ),
        ),
        (
            "purchase lines",
            db.query(PurchaseItem.id).filter(PurchaseItem.unit_id == unit_id),
        ),
        (
            "menu standards",
            db.query(MenuMainItem.id).filter(MenuMainItem.unit_id == unit_id),
        ),
        (
            "stock movements",
            db.query(StockMovement.id).filter(
                StockMovement.unit_id == unit_id
            ),
        ),
        (
            "waste lines",
            db.query(WasteItem.id).filter(WasteItem.unit_id == unit_id),
        ),
    ]

    return [label for label, query in checks if has_rows(query)]


def find_item_references(db: Session, item_id: int) -> list[str]:
    checks = [
        (
            "purchase lines",
            db.query(PurchaseItem.id).filter(PurchaseItem.item_id == item_id),
        ),
        (
            "goods receipt lines",
            db.query(GoodsReceiptItem.id)
            .join(
                PurchaseItem,
                PurchaseItem.id == GoodsReceiptItem.purchase_item_id,
            )
            .filter(PurchaseItem.item_id == item_id),
        ),
        (
            "stock movements",
            db.query(StockMovement.id).filter(
                StockMovement.item_id == item_id
            ),
        ),
        (
            "menu standards",
            db.query(MenuMainItem.id).filter(MenuMainItem.item_id == item_id),
        ),
        (
            "waste lines",
            db.query(WasteItem.id).filter(WasteItem.item_id == item_id),
        ),
    ]

    return [label for label, query in checks if has_rows(query)]


def unit_pair_is_used(
    db: Session,
    campus_id: int,
    unit_a: int,
    unit_b: int,
) -> bool:
    """True when a purchase line or menu standard converts between the
    two units, in either direction (line unit versus the item's standard
    unit). This matches how get_unit_conversion_factor finds a factor."""

    def used_by(model) -> bool:
        return has_rows(
            db.query(model.id)
            .join(Item, Item.id == model.item_id)
            .filter(
                model.campus_id == campus_id,
                or_(
                    and_(
                        model.unit_id == unit_a,
                        Item.standard_unit_id == unit_b,
                    ),
                    and_(
                        model.unit_id == unit_b,
                        Item.standard_unit_id == unit_a,
                    ),
                ),
            )
        )

    return used_by(PurchaseItem) or used_by(MenuMainItem)


def ensure_conversion_unused(
    db: Session,
    conversion: UnitConversion,
) -> None:
    if unit_pair_is_used(
        db,
        conversion.campus_id,
        conversion.from_unit_id,
        conversion.to_unit_id,
    ):
        raise HTTPException(
            409,
            (
                "This unit conversion is used by purchase lines or menu "
                "standards, so it can no longer be edited or deleted."
            ),
        )


def ensure_conversion_pair_available(
    db: Session,
    user: User,
    from_unit_id: int,
    to_unit_id: int,
    exclude_id: int | None = None,
) -> None:
    """Applies to both creating and editing a conversion.

    When the unit pair is already used, its existing conversion stays the
    only one. A second conversion for the same units (in either direction)
    would change the factor applied to recorded quantities.
    """

    if not unit_pair_is_used(db, user.campus_id, from_unit_id, to_unit_id):
        return

    existing = db.query(UnitConversion.id).filter(
        UnitConversion.campus_id == user.campus_id,
        or_(
            and_(
                UnitConversion.from_unit_id == from_unit_id,
                UnitConversion.to_unit_id == to_unit_id,
            ),
            and_(
                UnitConversion.from_unit_id == to_unit_id,
                UnitConversion.to_unit_id == from_unit_id,
            ),
        ),
    )

    if exclude_id is not None:
        existing = existing.filter(UnitConversion.id != exclude_id)

    if has_rows(existing):
        raise HTTPException(
            409,
            (
                "These units already have a conversion that is used by "
                "purchase lines or menu standards. Another conversion "
                "between them would change recorded quantities."
            ),
        )


def ensure_update_preserves_history(
    resource: str,
    record,
    values: dict,
    db: Session,
    user: User,
) -> None:
    if resource == "units":
        if values["dimension"] == record.dimension:
            return

        references = find_unit_references(db, record.id)

        if references:
            raise HTTPException(
                409,
                (
                    "The unit's dimension cannot be changed because the "
                    f"unit is used by: {', '.join(references)}. "
                    "Create a new unit instead."
                ),
            )

    elif resource == "items":
        if values["standard_unit_id"] == record.standard_unit_id:
            return

        references = find_item_references(db, record.id)

        if references:
            raise HTTPException(
                409,
                (
                    "The item's standard unit cannot be changed because "
                    f"the item is used by: {', '.join(references)}. "
                    "Recorded quantities depend on the current unit."
                ),
            )

    elif resource == "unit-conversions":
        ensure_conversion_unused(db, record)
        ensure_conversion_pair_available(
            db,
            user,
            values["from_unit_id"],
            values["to_unit_id"],
            exclude_id=record.id,
        )


# ============================================================
# UPDATE MASTER RECORD
# ============================================================

@router.put("/{resource}/{record_id}")
def update_master_record(
    resource: str,
    record_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    config = MASTER_RESOURCES.get(resource)

    if not config:
        raise HTTPException(
            404,
            "Master data resource not found.",
        )

    model, schema, entity_type, module_code = config

    if not has_module_permission(
        user, db, module_code, "update"
    ):
        raise HTTPException(
            403,
            "You do not have permission to update this record.",
        )

    if resource == "suppliers":
        ensure_supplier_write_allowed(user)

    try:
        values = schema.model_validate(payload).model_dump()

    except ValidationError as exc:
        # Encoded like FastAPI's own 422 responses on create, so values
        # such as Decimal limits in the error context can be serialized.
        raise HTTPException(
            422,
            detail=jsonable_encoder(exc.errors(include_url=False)),
        )

    record = ensure_campus_record(
        model, record_id, db, user
    )

    if hasattr(record, "is_active") and not record.is_active:
        raise HTTPException(
            409,
            "Inactive records cannot be edited.",
        )

    validate_master_values(
        resource, values, db, user
    )

    ensure_update_preserves_history(
        resource, record, values, db, user
    )

    old_values = {
        key: getattr(record, key)
        for key in values
    }

    try:
        for key, value in values.items():
            setattr(record, key, value)

        db.flush()

        record_audit(
            db,
            user,
            "UPDATE",
            entity_type,
            record.id,
            {
                "before": old_values,
                "after": values,
            },
        )

        db.commit()
        db.refresh(record)

        return record

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            409,
            "Update conflicts with an existing record or database constraint.",
        )


# ============================================================
# DEACTIVATE MASTER RECORD
# ============================================================

@router.post("/{resource}/{record_id}/deactivate")
def deactivate_master_record(
    resource: str,
    record_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    config = MASTER_RESOURCES.get(resource)

    if not config:
        raise HTTPException(
            404,
            "Master data resource not found.",
        )

    model, _schema, entity_type, module_code = config

    if not has_module_permission(
        user, db, module_code, "update"
    ):
        raise HTTPException(
            403,
            "You do not have permission to deactivate this record.",
        )

    if resource == "suppliers":
        ensure_supplier_write_allowed(user)

    record = ensure_campus_record(
        model, record_id, db, user
    )

    if not hasattr(record, "is_active"):
        raise HTTPException(
            409,
            "This record does not support deactivation.",
        )

    if not record.is_active:
        raise HTTPException(
            409,
            "Record is already inactive.",
        )

    try:
        record.is_active = False

        db.flush()

        record_audit(
            db,
            user,
            "DEACTIVATE",
            entity_type,
            record_id,
            {"is_active": False},
        )

        db.commit()

        return {
            "message": "Record deactivated successfully.",
            "id": record_id,
            "action": "DEACTIVATE",
        }

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            409,
            "Unable to deactivate this record because of a database constraint.",
        )


# ============================================================
# DELETE MASTER RECORD - ADMIN ONLY
# ============================================================

@router.delete("/{resource}/{record_id}")
def delete_master_record(
    resource: str,
    record_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            403,
            "Only Admin can delete records.",
        )

    config = MASTER_RESOURCES.get(resource)

    if not config:
        raise HTTPException(
            404,
            "Master data resource not found.",
        )

    model, _schema, entity_type, _module_code = config

    record = ensure_campus_record(
        model, record_id, db, user
    )

    # Conversions have no foreign-key references, so the database alone
    # would allow deleting one that recorded quantities depend on.
    if resource == "unit-conversions":
        ensure_conversion_unused(db, record)

    try:
        db.delete(record)
        db.flush()

        record_audit(
            db,
            user,
            "DELETE",
            entity_type,
            record_id,
            {"deleted": True},
        )

        db.commit()

        return {
            "message": "Record deleted successfully.",
            "id": record_id,
            "action": "DELETE",
        }

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            409,
            (
                "This record is referenced by other data and cannot be deleted. "
                "Deactivate it instead, if supported."
            ),
        )
