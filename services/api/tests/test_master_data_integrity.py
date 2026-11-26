"""
Historical integrity of master data.

Approved rules (all rejected changes return 409; historical records are
never modified):
- A unit's dimension cannot change while the unit is referenced by items,
  unit conversions, purchase lines, menu standards, stock movements or
  waste lines.
- An item's standard unit cannot change while the item is referenced by
  purchase lines, goods receipt lines, stock movements, menu standards or
  waste lines.
- A unit conversion can be edited or deleted only until it is used, that
  is until a purchase line or menu standard converts between its two
  units. A used unit pair also cannot gain a second conversion in either
  direction.
- Update validation matches create validation.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models import (
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
    GoodsReceipt,
    GoodsReceiptItem,
    Purchase,
    PurchaseItem,
    StockMovement,
)
from app.models.waste import WasteItem, WasteRecord


UNITS_URL = "/api/master/units"
ITEMS_URL = "/api/master/items"
CONVERSIONS_URL = "/api/master/unit-conversions"


# ------------------------------------------------------------
# Fixtures and helpers
# ------------------------------------------------------------

@pytest.fixture
def base(db, setup_data):
    """Master records in the admin's campus, created directly."""

    campus_id = setup_data["campus"].id
    admin_id = setup_data["user"].id

    kg = Unit(campus_id=campus_id, name="Kilogram", symbol="kg",
              dimension="weight")
    g = Unit(campus_id=campus_id, name="Gram", symbol="g",
             dimension="weight")
    category = Category(campus_id=campus_id, name="Grains")
    supplier = Supplier(campus_id=campus_id, name="Integrity Supplier")
    session = MealSession(campus_id=campus_id, name="Lunch")
    db.add_all([kg, g, category, supplier, session])
    db.flush()

    item = Item(campus_id=campus_id, name="Rice", category_id=category.id,
                standard_unit_id=kg.id, minimum_stock=0)
    menu = Menu(campus_id=campus_id, name="Lunch Menu",
                meal_session_id=session.id)
    purchase = Purchase(campus_id=campus_id, supplier_id=supplier.id,
                        invoice_number="INTEGRITY-001",
                        purchase_date=date(2026, 11, 7),
                        created_by=admin_id)
    waste_record = WasteRecord(campus_id=campus_id,
                               waste_date=date(2026, 11, 7),
                               recorded_by=admin_id)
    db.add_all([item, menu, purchase, waste_record])
    db.commit()

    return SimpleNamespace(
        campus_id=campus_id,
        admin_id=admin_id,
        kg_id=kg.id,
        g_id=g.id,
        category_id=category.id,
        supplier_id=supplier.id,
        item_id=item.id,
        menu_id=menu.id,
        purchase_id=purchase.id,
        waste_record_id=waste_record.id,
    )


def add_unit(db, base, name="Sack", symbol="sk", dimension="weight"):
    unit = Unit(campus_id=base.campus_id, name=name, symbol=symbol,
                dimension=dimension)
    db.add(unit)
    db.commit()
    return unit.id


def add_purchase_line(db, base, item_id, unit_id):
    line = PurchaseItem(campus_id=base.campus_id,
                        purchase_id=base.purchase_id, item_id=item_id,
                        quantity=Decimal("1"), unit_id=unit_id,
                        unit_rate=Decimal("1"), line_total=Decimal("1"))
    db.add(line)
    db.flush()
    return line


def add_menu_standard(db, base, item_id, unit_id):
    db.add(MenuMainItem(campus_id=base.campus_id, menu_id=base.menu_id,
                        item_id=item_id, unit_id=unit_id,
                        quantity_per_person=Decimal("0.100")))


def add_stock_movement(db, base, item_id, unit_id):
    # Stage 4 ledger columns: direction, effective time and a unique source.
    db.add(StockMovement(campus_id=base.campus_id, item_id=item_id,
                         movement_type="RECEIPT", direction=1,
                         quantity=Decimal("1"), unit_id=unit_id,
                         reference_type="TEST", reference_id=1,
                         source_key=f"TEST:{item_id}:{unit_id}",
                         effective_at=datetime.now(timezone.utc),
                         created_by=base.admin_id))


def add_waste_line(db, base, item_id, unit_id):
    if item_id is None:
        extra = {"waste_type": "PREPARED_FOOD", "food_name": "Curry"}
    else:
        extra = {"waste_type": "RAW_INGREDIENT", "food_name": "Rice"}

    db.add(WasteItem(campus_id=base.campus_id,
                     waste_record_id=base.waste_record_id, item_id=item_id,
                     unit_id=unit_id, quantity=Decimal("1"),
                     waste_stage="STORAGE", waste_reason="SPOILED",
                     estimated_cost=Decimal("0"), **extra))


def add_receipt_line(db, base, item_id, unit_id):
    line = add_purchase_line(db, base, item_id, unit_id)
    receipt = GoodsReceipt(campus_id=base.campus_id,
                           purchase_id=base.purchase_id,
                           receipt_date=date(2026, 11, 7),
                           created_by=base.admin_id)
    db.add(receipt)
    db.flush()
    db.add(GoodsReceiptItem(campus_id=base.campus_id, receipt_id=receipt.id,
                            purchase_item_id=line.id,
                            quantity_received=Decimal("1"),
                            quantity_accepted=Decimal("1"),
                            quantity_rejected=Decimal("0")))


def unit_payload(dimension, name="Sack", symbol="sk"):
    return {"name": name, "symbol": symbol, "dimension": dimension}


def item_payload(base, standard_unit_id, name="Rice"):
    return {
        "name": name,
        "category_id": base.category_id,
        "standard_unit_id": standard_unit_id,
        "minimum_stock": "0",
    }


def conversion_payload(from_unit_id, to_unit_id, factor):
    return {
        "from_unit_id": from_unit_id,
        "to_unit_id": to_unit_id,
        "factor": factor,
    }


def create_conversion(client, from_unit_id, to_unit_id, factor="1000"):
    response = client.post(
        CONVERSIONS_URL,
        json=conversion_payload(from_unit_id, to_unit_id, factor),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def create_bill_line_via_api(client, base, unit_id):
    response = client.post(
        "/api/purchases/",
        json={
            "supplier_id": base.supplier_id,
            "invoice_number": f"API-{unit_id}",
            "purchase_date": "2026-11-07",
            "items": [
                {
                    "item_id": base.item_id,
                    "quantity": "500",
                    "unit_id": unit_id,
                    "unit_rate": "0.05",
                }
            ],
        },
    )
    assert response.status_code == 201, response.text


def create_menu_standard_via_api(client, base, unit_id):
    response = client.post(
        "/api/master/menu-main-items",
        json={
            "menu_id": base.menu_id,
            "item_id": base.item_id,
            "quantity_per_person": "150",
            "unit_id": unit_id,
        },
    )
    assert response.status_code == 201, response.text


def conversion_factor(db, conversion_id):
    db.expire_all()
    conversion = db.get(UnitConversion, conversion_id)
    return None if conversion is None else Decimal(str(conversion.factor))


# ------------------------------------------------------------
# Unit dimension
# ------------------------------------------------------------

UNIT_REFERENCES = [
    (
        "items",
        lambda db, base, unit_id: db.add(
            Item(campus_id=base.campus_id, name="Flour",
                 category_id=base.category_id, standard_unit_id=unit_id,
                 minimum_stock=0)
        ),
    ),
    (
        "unit conversions",
        lambda db, base, unit_id: db.add(
            UnitConversion(campus_id=base.campus_id, from_unit_id=unit_id,
                           to_unit_id=base.kg_id, factor=Decimal("50"))
        ),
    ),
    (
        "purchase lines",
        lambda db, base, unit_id: add_purchase_line(
            db, base, base.item_id, unit_id
        ),
    ),
    (
        "menu standards",
        lambda db, base, unit_id: add_menu_standard(
            db, base, base.item_id, unit_id
        ),
    ),
    (
        "stock movements",
        lambda db, base, unit_id: add_stock_movement(
            db, base, base.item_id, unit_id
        ),
    ),
    (
        "waste lines",
        lambda db, base, unit_id: add_waste_line(db, base, None, unit_id),
    ),
]


@pytest.mark.parametrize(
    "label, add_reference",
    UNIT_REFERENCES,
    ids=[label for label, _ in UNIT_REFERENCES],
)
def test_unit_dimension_change_is_blocked_by_each_reference(
    client, db, base, label, add_reference
):
    unit_id = add_unit(db, base)
    add_reference(db, base, unit_id)
    db.commit()

    response = client.put(
        f"{UNITS_URL}/{unit_id}", json=unit_payload("volume")
    )

    assert response.status_code == 409, response.text
    assert label in response.json()["detail"]

    db.expire_all()
    assert db.get(Unit, unit_id).dimension == "weight"


def test_unreferenced_unit_dimension_can_change(client, db, base):
    unit_id = add_unit(db, base)

    response = client.put(
        f"{UNITS_URL}/{unit_id}", json=unit_payload("volume")
    )

    assert response.status_code == 200, response.text
    db.expire_all()
    assert db.get(Unit, unit_id).dimension == "volume"


def test_referenced_unit_can_be_renamed_without_dimension_change(
    client, db, base
):
    # kg is the standard unit of the base item.
    response = client.put(
        f"{UNITS_URL}/{base.kg_id}",
        json=unit_payload("weight", name="Kilogramme", symbol="kgm"),
    )

    assert response.status_code == 200, response.text
    db.expire_all()
    unit = db.get(Unit, base.kg_id)
    assert (unit.name, unit.dimension) == ("Kilogramme", "weight")


# ------------------------------------------------------------
# Item standard unit
# ------------------------------------------------------------

ITEM_REFERENCES = [
    (
        "purchase lines",
        lambda db, base: add_purchase_line(
            db, base, base.item_id, base.kg_id
        ),
    ),
    (
        "goods receipt lines",
        lambda db, base: add_receipt_line(
            db, base, base.item_id, base.kg_id
        ),
    ),
    (
        "stock movements",
        lambda db, base: add_stock_movement(
            db, base, base.item_id, base.kg_id
        ),
    ),
    (
        "menu standards",
        lambda db, base: add_menu_standard(
            db, base, base.item_id, base.kg_id
        ),
    ),
    (
        "waste lines",
        lambda db, base: add_waste_line(
            db, base, base.item_id, base.kg_id
        ),
    ),
]


@pytest.mark.parametrize(
    "label, add_reference",
    ITEM_REFERENCES,
    ids=[label for label, _ in ITEM_REFERENCES],
)
def test_item_standard_unit_change_is_blocked_by_each_reference(
    client, db, base, label, add_reference
):
    add_reference(db, base)
    db.commit()

    response = client.put(
        f"{ITEMS_URL}/{base.item_id}", json=item_payload(base, base.g_id)
    )

    assert response.status_code == 409, response.text
    assert label in response.json()["detail"]

    db.expire_all()
    assert db.get(Item, base.item_id).standard_unit_id == base.kg_id


def test_unreferenced_item_standard_unit_can_change(client, db, base):
    response = client.put(
        f"{ITEMS_URL}/{base.item_id}", json=item_payload(base, base.g_id)
    )

    assert response.status_code == 200, response.text
    db.expire_all()
    assert db.get(Item, base.item_id).standard_unit_id == base.g_id


def test_referenced_item_keeps_other_edits(client, db, base):
    add_stock_movement(db, base, base.item_id, base.kg_id)
    db.commit()

    response = client.put(
        f"{ITEMS_URL}/{base.item_id}",
        json=item_payload(base, base.kg_id, name="Basmati Rice"),
    )

    assert response.status_code == 200, response.text
    db.expire_all()
    assert db.get(Item, base.item_id).name == "Basmati Rice"


# ------------------------------------------------------------
# Unit conversions
# ------------------------------------------------------------

def test_unused_conversion_can_be_edited_and_deleted(client, db, base):
    conversion_id = create_conversion(client, base.kg_id, base.g_id)

    edit = client.put(
        f"{CONVERSIONS_URL}/{conversion_id}",
        json=conversion_payload(base.kg_id, base.g_id, "1001"),
    )
    assert edit.status_code == 200, edit.text
    assert conversion_factor(db, conversion_id) == Decimal("1001")

    delete = client.delete(f"{CONVERSIONS_URL}/{conversion_id}")
    assert delete.status_code == 200, delete.text
    assert conversion_factor(db, conversion_id) is None


@pytest.mark.parametrize(
    "use_pair",
    [create_bill_line_via_api, create_menu_standard_via_api],
    ids=["purchase line", "menu standard"],
)
def test_used_conversion_cannot_be_edited_or_deleted(
    client, db, base, use_pair
):
    conversion_id = create_conversion(client, base.kg_id, base.g_id)
    # The base item's standard unit is kg; this line is entered in grams.
    use_pair(client, base, base.g_id)

    edit = client.put(
        f"{CONVERSIONS_URL}/{conversion_id}",
        json=conversion_payload(base.kg_id, base.g_id, "100"),
    )
    assert edit.status_code == 409, edit.text

    delete = client.delete(f"{CONVERSIONS_URL}/{conversion_id}")
    assert delete.status_code == 409, delete.text

    assert conversion_factor(db, conversion_id) == Decimal("1000")


def test_line_in_the_standard_unit_does_not_use_the_conversion(
    client, db, base
):
    conversion_id = create_conversion(client, base.kg_id, base.g_id)
    # Entered in kg, the item's standard unit: no conversion is involved.
    create_bill_line_via_api(client, base, base.kg_id)

    edit = client.put(
        f"{CONVERSIONS_URL}/{conversion_id}",
        json=conversion_payload(base.kg_id, base.g_id, "999"),
    )

    assert edit.status_code == 200, edit.text


def test_used_pair_cannot_gain_a_reverse_conversion(client, db, base):
    create_conversion(client, base.kg_id, base.g_id)
    create_bill_line_via_api(client, base, base.g_id)

    response = client.post(
        CONVERSIONS_URL,
        json=conversion_payload(base.g_id, base.kg_id, "0.002"),
    )

    assert response.status_code == 409, response.text
    assert db.query(UnitConversion).count() == 1


def test_unused_pair_still_accepts_a_reverse_conversion(client, db, base):
    # Unchanged behaviour until the pair is used.
    create_conversion(client, base.kg_id, base.g_id)
    create_conversion(client, base.g_id, base.kg_id, "0.001")

    assert db.query(UnitConversion).count() == 2


def test_unused_conversion_cannot_be_moved_onto_a_used_pair(
    client, db, base
):
    create_conversion(client, base.kg_id, base.g_id)
    create_bill_line_via_api(client, base, base.g_id)

    mg_id = add_unit(db, base, name="Milligram", symbol="mg")
    spare_id = create_conversion(client, base.kg_id, mg_id, "1000000")

    response = client.put(
        f"{CONVERSIONS_URL}/{spare_id}",
        json=conversion_payload(base.g_id, base.kg_id, "0.002"),
    )

    assert response.status_code == 409, response.text
    db.expire_all()
    spare = db.get(UnitConversion, spare_id)
    assert (spare.from_unit_id, spare.to_unit_id) == (base.kg_id, mg_id)


# ------------------------------------------------------------
# Update validation matches create validation
# ------------------------------------------------------------

def test_conversion_update_validation_matches_create(client, db, base):
    litre_id = add_unit(db, base, name="Litre", symbol="l",
                        dimension="volume")
    conversion_id = create_conversion(client, base.kg_id, base.g_id)

    for payload in (
        conversion_payload(base.kg_id, litre_id, "1"),   # dimensions differ
        conversion_payload(base.kg_id, base.kg_id, "1"),  # same unit
        conversion_payload(base.kg_id, base.g_id, "0"),   # factor not > 0
    ):
        created = client.post(CONVERSIONS_URL, json=payload)
        updated = client.put(
            f"{CONVERSIONS_URL}/{conversion_id}", json=payload
        )

        assert created.status_code == 422, (payload, created.text)
        assert updated.status_code == 422, (payload, updated.text)


def test_item_update_validation_matches_create(client, db, base):
    inactive_id = add_unit(db, base, name="Old Unit", symbol="old")
    db.get(Unit, inactive_id).is_active = False
    db.commit()

    created = client.post(
        ITEMS_URL, json=item_payload(base, inactive_id, name="New Item")
    )
    updated = client.put(
        f"{ITEMS_URL}/{base.item_id}", json=item_payload(base, inactive_id)
    )

    assert created.status_code == 422, created.text
    assert updated.status_code == 422, updated.text
