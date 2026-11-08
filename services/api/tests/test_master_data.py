from decimal import Decimal

from app.models import (
    Campus,
    Category,
    Unit,
    UnitConversion,
    Item,
    Menu,
    MealSession,
    AuditLog,
)


def create_unit(client, name, symbol, dimension):
    response = client.post(
        "/api/master/units",
        json={
            "name": name,
            "symbol": symbol,
            "dimension": dimension,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_and_list_units(client):
    unit = create_unit(client, "Kilogram", "kg", "weight")

    assert unit["name"] == "Kilogram"
    assert unit["symbol"] == "kg"
    assert unit["dimension"] == "weight"

    response = client.get("/api/master/units")

    assert response.status_code == 200
    assert any(row["id"] == unit["id"] for row in response.json())


def test_create_unit_conversion(client):
    kg = create_unit(client, "Kilogram", "kg", "weight")
    gram = create_unit(client, "Gram", "g", "weight")

    response = client.post(
        "/api/master/unit-conversions",
        json={
            "from_unit_id": kg["id"],
            "to_unit_id": gram["id"],
            "factor": "1000",
        },
    )

    assert response.status_code == 201, response.text
    assert Decimal(str(response.json()["factor"])) == Decimal("1000")


def test_reject_conversion_between_different_dimensions(client):
    kg = create_unit(client, "Kilogram", "kg", "weight")
    litre = create_unit(client, "Litre", "L", "volume")

    response = client.post(
        "/api/master/unit-conversions",
        json={
            "from_unit_id": kg["id"],
            "to_unit_id": litre["id"],
            "factor": "1",
        },
    )

    assert response.status_code == 422


def test_create_menu_main_item_with_explicit_conversion(client):
    category_response = client.post(
        "/api/master/categories",
        json={"name": "Groceries"},
    )
    assert category_response.status_code == 201

    kg = create_unit(client, "Kilogram", "kg", "weight")
    gram = create_unit(client, "Gram", "g", "weight")

    conversion_response = client.post(
        "/api/master/unit-conversions",
        json={
            "from_unit_id": kg["id"],
            "to_unit_id": gram["id"],
            "factor": "1000",
        },
    )
    assert conversion_response.status_code == 201

    item_response = client.post(
        "/api/master/items",
        json={
            "name": "Rice",
            "category_id": category_response.json()["id"],
            "standard_unit_id": kg["id"],
            "minimum_stock": "10",
        },
    )
    assert item_response.status_code == 201, item_response.text

    meal_response = client.post(
        "/api/master/meal-sessions",
        json={"name": "Lunch"},
    )
    assert meal_response.status_code == 201

    menu_response = client.post(
        "/api/master/menus",
        json={
            "name": "Rice Lunch",
            "meal_session_id": meal_response.json()["id"],
        },
    )
    assert menu_response.status_code == 201, menu_response.text

    response = client.post(
        "/api/master/menu-main-items",
        json={
            "menu_id": menu_response.json()["id"],
            "item_id": item_response.json()["id"],
            "quantity_per_person": "150",
            "unit_id": gram["id"],
        },
    )

    assert response.status_code == 201, response.text
    assert Decimal(str(response.json()["quantity_per_person"])) == Decimal("150")


def test_reject_menu_item_without_explicit_conversion(client):
    category = client.post(
        "/api/master/categories",
        json={"name": "Vegetables"},
    )
    kg = create_unit(client, "Kilogram", "kg", "weight")
    gram = create_unit(client, "Gram", "g", "weight")

    item = client.post(
        "/api/master/items",
        json={
            "name": "Potato",
            "category_id": category.json()["id"],
            "standard_unit_id": kg["id"],
            "minimum_stock": "5",
        },
    )

    meal = client.post(
        "/api/master/meal-sessions",
        json={"name": "Dinner"},
    )
    menu = client.post(
        "/api/master/menus",
        json={
            "name": "Dinner Menu",
            "meal_session_id": meal.json()["id"],
        },
    )

    response = client.post(
        "/api/master/menu-main-items",
        json={
            "menu_id": menu.json()["id"],
            "item_id": item.json()["id"],
            "quantity_per_person": "200",
            "unit_id": gram["id"],
        },
    )

    assert response.status_code == 422


def test_campus_isolation_and_audit_logging(client, db, setup_data):
    other_campus = Campus(
        name="Other Campus",
        code="OTHER-CAMPUS",
    )
    db.add(other_campus)
    db.flush()

    db.add(
        Category(
            campus_id=other_campus.id,
            name="Private Category",
        )
    )
    db.commit()

    response = client.get("/api/master/categories")

    assert response.status_code == 200
    assert all(
        row["name"] != "Private Category"
        for row in response.json()
    )

    create_response = client.post(
        "/api/master/categories",
        json={
            "name": "Audit Test Category",
            "description": "Testing audit logging",
        },
    )
    assert create_response.status_code == 201

    audit = db.query(AuditLog).filter(
        AuditLog.entity_type == "CATEGORY",
        AuditLog.entity_id == create_response.json()["id"],
    ).first()

    assert audit is not None
    assert audit.campus_id == setup_data["campus"].id
    assert audit.user_id == setup_data["user"].id
    assert audit.action == "CREATE"
    assert audit.details["name"] == "Audit Test Category"


def test_direct_and_reverse_conversion_factors(client, db, setup_data):
    from app.api.routes.master_data import get_unit_conversion_factor

    kg = create_unit(client, "Kilogram Conversion", "kg", "weight")
    gram = create_unit(client, "Gram Conversion", "g", "weight")

    response = client.post(
        "/api/master/unit-conversions",
        json={
            "from_unit_id": kg["id"],
            "to_unit_id": gram["id"],
            "factor": "1000",
        },
    )
    assert response.status_code == 201, response.text

    user = setup_data["user"]

    direct_factor = get_unit_conversion_factor(
        db, user, kg["id"], gram["id"]
    )
    reverse_factor = get_unit_conversion_factor(
        db, user, gram["id"], kg["id"]
    )

    assert direct_factor == Decimal("1000")
    assert reverse_factor == Decimal("0.001")

    # 150 grams must equal 0.15 kilograms.
    assert Decimal("150") * reverse_factor == Decimal("0.150")


def test_same_unit_conversion_factor_is_one(client, db, setup_data):
    from app.api.routes.master_data import get_unit_conversion_factor

    kg = create_unit(client, "Same Unit Kilogram", "kg", "weight")

    factor = get_unit_conversion_factor(
        db,
        setup_data["user"],
        kg["id"],
        kg["id"],
    )

    assert factor == Decimal("1")


def test_missing_conversion_factor_is_rejected(client, db, setup_data):
    from fastapi import HTTPException
    from app.api.routes.master_data import get_unit_conversion_factor

    kg = create_unit(client, "Missing Conversion KG", "kg", "weight")
    gram = create_unit(client, "Missing Conversion G", "g", "weight")

    try:
        get_unit_conversion_factor(
            db,
            setup_data["user"],
            gram["id"],
            kg["id"],
        )
        assert False, "Expected missing conversion to be rejected"
    except HTTPException as exc:
        assert exc.status_code == 422
