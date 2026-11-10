
import argparse
import hashlib
import os
import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from getpass import getpass

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import (
    Campus,
    Category,
    DailyHeadcount,
    Item,
    MealSession,
    Menu,
    MenuMainItem,
    Supplier,
    Unit,
    UnitConversion,
    User,
    UserRole,
)
from app.models.purchases import (
    GoodsReceipt,
    GoodsReceiptItem,
    Purchase,
    PurchaseItem,
    StockMovement,
    SupplierPayment,
)

# ---------------------------------------------------------
# GENERAL HELPERS
# ---------------------------------------------------------

def get_or_create(db, model, filters, defaults):
    record = db.query(model).filter_by(**filters).first()

    if record:
        return record, False

    record = model(**filters, **defaults)
    db.add(record)
    db.flush()

    return record, True


def money(value):
    return Decimal(str(value)).quantize(Decimal("0.01"))


def quantity(value):
    return Decimal(str(value)).quantize(Decimal("0.001"))


# ---------------------------------------------------------
# EXISTING ADMINISTRATOR SETUP
# ---------------------------------------------------------

def setup_administrator():
    db = SessionLocal()

    try:
        campus, _ = get_or_create(
            db,
            Campus,
            {"code": "ZAITOON-PAYYANUR"},
            {
                "name": "Zaitoon International Girls Campus, Payyanur",
                "is_active": True,
            },
        )

        email = input("Administrator email: ").strip().lower()
        full_name = input("Administrator full name: ").strip()
        password = getpass(
            "Administrator password (minimum 8 characters): "
        )

        if not email or not full_name:
            raise ValueError("Email and full name are required.")

        if len(password) < 8:
            raise ValueError("Password must contain at least 8 characters.")

        existing = db.query(User).filter(User.email == email).first()

        if existing:
            print("This administrator email already exists.")
            db.rollback()
            return

        admin = User(
            campus_id=campus.id,
            full_name=full_name,
            email=email,
            password_hash=hash_password(password),
            role=UserRole.ADMIN,
            is_active=True,
        )

        db.add(admin)
        db.commit()

        print("Campus and administrator created successfully.")

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


# ---------------------------------------------------------
# DEMO DATA
# ---------------------------------------------------------

CATEGORIES = [
    "Grains",
    "Pulses",
    "Vegetables",
    "Fruits",
    "Dairy Products",
    "Spices",
    "Oils",
    "Cleaning Supplies",
]

UNITS = [
    ("Gram", "g", "weight"),
    ("Kilogram", "kg", "weight"),
    ("Millilitre", "ml", "volume"),
    ("Litre", "L", "volume"),
    ("Piece", "pc", "count"),
]

CONVERSIONS = [
    ("g", "g", "1"),
    ("kg", "kg", "1"),
    ("kg", "g", "1000"),
    ("g", "kg", "0.001"),
    ("ml", "ml", "1"),
    ("L", "L", "1"),
    ("L", "ml", "1000"),
    ("ml", "L", "0.001"),
    ("pc", "pc", "1"),
]

ITEM_GROUPS = {
    "Grains": [
        "Rice",
        "Basmati Rice",
        "Wheat",
        "Broken Wheat",
        "Rava",
        "Maida",
        "Atta",
        "Corn Flour",
    ],
    "Pulses": [
        "Toor Dal",
        "Moong Dal",
        "Urad Dal",
        "Chana Dal",
        "Masoor Dal",
        "Green Gram",
        "Black Gram",
        "Chickpeas",
    ],
    "Vegetables": [
        "Onion",
        "Tomato",
        "Potato",
        "Carrot",
        "Cabbage",
        "Beans",
        "Green Chilli",
        "Cucumber",
    ],
    "Fruits": [
        "Banana",
        "Apple",
        "Orange",
        "Papaya",
        "Watermelon",
        "Pineapple",
        "Mango",
        "Grapes",
    ],
    "Dairy Products": [
        "Milk",
        "Curd",
        "Butter",
        "Cheese",
        "Paneer",
        "Ghee",
        "Cream",
    ],
    "Spices": [
        "Turmeric Powder",
        "Chilli Powder",
        "Black Pepper",
        "Cumin",
        "Coriander Powder",
        "Cardamom",
        "Cinnamon",
    ],
    "Oils": [
        "Coconut Oil",
        "Sunflower Oil",
        "Vegetable Oil",
        "Olive Oil",
        "Mustard Oil",
        "Groundnut Oil",
        "Sesame Oil",
    ],
    "Cleaning Supplies": [
        "Dishwashing Liquid",
        "Floor Cleaner",
        "Hand Wash",
        "Laundry Detergent",
        "Cleaning Powder",
        "Garbage Bags",
        "Scrub Pads",
    ],
}

SUPPLIERS = [
    "Demo Fresh Foods",
    "Demo Grain Traders",
    "Demo Vegetable Market",
    "Demo Dairy Supplies",
    "Demo Spice Centre",
    "Demo Oil Distributors",
    "Demo Fruit Traders",
    "Demo General Stores",
]

SESSIONS = [
    "Breakfast",
    "Lunch",
    "Evening Snack",
    "Dinner",
]

MENUS = [
    ("Monday Breakfast", "Breakfast"),
    ("Tuesday Breakfast", "Breakfast"),
    ("Monday Lunch", "Lunch"),
    ("Tuesday Lunch", "Lunch"),
    ("Monday Evening Snack", "Evening Snack"),
    ("Tuesday Evening Snack", "Evening Snack"),
    ("Monday Dinner", "Dinner"),
    ("Tuesday Dinner", "Dinner"),
]

DEMO_CAMPUSES = [
    {
        "name": "Kitchen Copilot Demo Campus North",
        "code": "KC-DEMO-NORTH",
    },
    {
        "name": "Kitchen Copilot Demo Campus South",
        "code": "KC-DEMO-SOUTH",
    },
]

ROLE_NAMES = {
    UserRole.ADMIN: "Demo Administrator",
    UserRole.KITCHEN_MANAGER: "Demo Kitchen Manager",
    UserRole.STORE_KEEPER: "Demo Store Keeper",
    UserRole.ACCOUNTS: "Demo Accounts User",
}


# ---------------------------------------------------------
# DEMO USERS
# ---------------------------------------------------------

def get_demo_users(db, campus):
    users = {}

    for role in ROLE_NAMES:
        email = (
            f"{campus.code.lower()}."
            f"{role.value.lower()}@kitchencopilot.test"
        )

        user = db.query(User).filter(User.email == email).first()

        if user:
            if user.campus_id != campus.id or user.role != role:
                raise ValueError(
                    f"Demo email conflict: {email}. "
                    "Existing user was not modified."
                )

            users[role] = user

    missing = [
        role for role in ROLE_NAMES
        if role not in users
    ]

    if missing:
        password = getpass(
            "Enter a password for new demo accounts "
            "(minimum 8 characters): "
        )
        confirm = getpass("Confirm demo password: ")

        if len(password) < 8:
            raise ValueError(
                "Demo password must contain at least 8 characters."
            )

        if password != confirm:
            raise ValueError("Passwords do not match.")

        password_hash = hash_password(password)

        for role in missing:
            email = (
                f"{campus.code.lower()}."
                f"{role.value.lower()}@kitchencopilot.test"
            )

            user = User(
                campus_id=campus.id,
                full_name=ROLE_NAMES[role],
                email=email,
                password_hash=password_hash,
                role=role,
                is_active=True,
            )

            db.add(user)
            db.flush()
            users[role] = user

    return users


# ---------------------------------------------------------
# MASTER DATA SEEDING
# ---------------------------------------------------------

def seed_master_data(db, campus):
    categories = {}

    for name in CATEGORIES:
        categories[name], _ = get_or_create(
            db,
            Category,
            {
                "campus_id": campus.id,
                "name": name,
            },
            {
                "description": f"Demo category: {name}",
                "is_active": True,
            },
        )

    units = {}

    for name, symbol, dimension in UNITS:
        units[symbol], _ = get_or_create(
            db,
            Unit,
            {
                "campus_id": campus.id,
                "symbol": symbol,
            },
            {
                "name": name,
                "dimension": dimension,
                "is_active": True,
            },
        )

        if units[symbol].dimension != dimension:
            raise ValueError(
                f"Existing demo unit {symbol} has an incompatible dimension."
            )

    for from_symbol, to_symbol, factor in CONVERSIONS:
        get_or_create(
            db,
            UnitConversion,
            {
                "campus_id": campus.id,
                "from_unit_id": units[from_symbol].id,
                "to_unit_id": units[to_symbol].id,
            },
            {
                "factor": Decimal(factor),
            },
        )

    items = {}

    for category_name, names in ITEM_GROUPS.items():
        for name in names:
            if category_name == "Dairy Products":
                standard_symbol = (
                    "L" if name in ("Milk", "Cream") else "kg"
                )
            elif category_name == "Oils":
                standard_symbol = "L"
            elif category_name == "Cleaning Supplies":
                standard_symbol = (
                    "pc" if name in ("Garbage Bags", "Scrub Pads")
                    else "L"
                )
            else:
                standard_symbol = "kg"

            item, _ = get_or_create(
                db,
                Item,
                {
                    "campus_id": campus.id,
                    "name": name,
                },
                {
                    "category_id": categories[category_name].id,
                    "standard_unit_id": units[standard_symbol].id,
                    "minimum_stock": Decimal(5),
                    "description": f"Synthetic demo item: {name}",
                    "is_active": True,
                },
            )

            items[name] = item

    suppliers = {}

    for index, name in enumerate(SUPPLIERS, start=1):
        suppliers[name], _ = get_or_create(
            db,
            Supplier,
            {
                "campus_id": campus.id,
                "name": name,
            },
            {
                "phone": f"900000{index:04d}",
                "email": f"supplier{index}@demo.kitchencopilot.test",
                "address": "Synthetic demo address",
                "is_active": True,
            },
        )

    sessions = {}

    for name in SESSIONS:
        sessions[name], _ = get_or_create(
            db,
            MealSession,
            {
                "campus_id": campus.id,
                "name": name,
            },
            {"is_active": True},
        )

    menus = {}

    for name, session_name in MENUS:
        menus[name], _ = get_or_create(
            db,
            Menu,
            {
                "campus_id": campus.id,
                "name": name,
            },
            {
                "meal_session_id": sessions[session_name].id,
                "is_active": True,
            },
        )

        for item_name, amount in [
            ("Rice", "0.150"),
            ("Onion", "0.020"),
            ("Tomato", "0.030"),
        ]:
            item = items[item_name]

            get_or_create(
                db,
                MenuMainItem,
                {
                    "campus_id": campus.id,
                    "menu_id": menus[name].id,
                    "item_id": item.id,
                },
                {
                    "quantity_per_person": Decimal(amount),
                    "unit_id": item.standard_unit_id,
                },
            )

    return items, units, suppliers


# ---------------------------------------------------------
# DAILY HEADCOUNT SEEDING
# ---------------------------------------------------------

def seed_daily_headcounts(db, campus, days=90):
    """
    Create deterministic daily student headcounts for a demo campus.

    The headcount is the total number of students needing food
    for the day, not a separate count for each meal.

    Existing records are preserved.
    """

    today = date.today()
    start_date = today - timedelta(days=days - 1)

    existing_dates = {
        row[0]
        for row in (
            db.query(DailyHeadcount.headcount_date)
            .filter(DailyHeadcount.campus_id == campus.id)
            .all()
        )
    }

    created_count = 0

    for day_offset in range(days):
        headcount_date = start_date + timedelta(days=day_offset)

        if headcount_date in existing_dates:
            continue

        seed_value = (
            f"{campus.code}:{headcount_date.isoformat()}"
        )

        digest = hashlib.sha256(
            seed_value.encode("utf-8")
        ).hexdigest()

        student_count = 420 + (
            int(digest[:8], 16) % 51
        )

        db.add(
            DailyHeadcount(
                campus_id=campus.id,
                headcount_date=headcount_date,
                student_count=student_count,
            )
        )

        created_count += 1

    return created_count


# ---------------------------------------------------------
# PURCHASE, RECEIPT AND PAYMENT SEEDING
# ---------------------------------------------------------

def seed_purchase_and_receipt(
    db,
    campus,
    users,
    items,
    suppliers,
):
    admin = users[UserRole.ADMIN]
    store_keeper = users[UserRole.STORE_KEEPER]

    supplier = suppliers["Demo Grain Traders"]

    invoice_number = f"KC-DEMO-{campus.code}-001"

    purchase = (
        db.query(Purchase)
        .filter(
            Purchase.campus_id == campus.id,
            Purchase.supplier_id == supplier.id,
            Purchase.invoice_number == invoice_number,
        )
        .first()
    )

    purchase_lines = []

    if not purchase:
        purchase_date = date.today() - timedelta(days=30)

        line_data = [
            ("Rice", "25.000", "55.0000"),
            ("Toor Dal", "10.000", "110.0000"),
            ("Onion", "20.000", "35.0000"),
        ]

        subtotal = Decimal("0.00")
        prepared = []

        for item_name, qty, rate in line_data:
            item = items[item_name]
            item_quantity = quantity(qty)
            unit_rate = Decimal(rate)
            line_total = money(item_quantity * unit_rate)

            subtotal += line_total

            prepared.append(
                {
                    "item_id": item.id,
                    "quantity": item_quantity,
                    "unit_id": item.standard_unit_id,
                    "unit_rate": unit_rate,
                    "line_total": line_total,
                    "remarks": "Synthetic demonstration purchase",
                }
            )

        subtotal = money(subtotal)
        discount = Decimal("10.00")
        grand_total = money(subtotal - discount)

        purchase = Purchase(
            campus_id=campus.id,
            supplier_id=supplier.id,
            invoice_number=invoice_number,
            purchase_date=purchase_date,
            subtotal=subtotal,
            discount=discount,
            extra_charges=Decimal("0.00"),
            grand_total=grand_total,
            remarks="Synthetic demonstration purchase",
            status="DRAFT",
            created_by=admin.id,
        )

        db.add(purchase)
        db.flush()

        for line in prepared:
            purchase_line = PurchaseItem(
                campus_id=campus.id,
                purchase_id=purchase.id,
                **line,
            )
            db.add(purchase_line)
            db.flush()
            purchase_lines.append(purchase_line)

    else:
        purchase_lines = (
            db.query(PurchaseItem)
            .filter(
                PurchaseItem.campus_id == campus.id,
                PurchaseItem.purchase_id == purchase.id,
            )
            .order_by(PurchaseItem.id)
            .all()
        )

    if len(purchase_lines) != 3:
        raise ValueError(
            f"Demo purchase {invoice_number} must contain exactly "
            "three lines. Existing data was preserved."
        )

    receipt = (
        db.query(GoodsReceipt)
        .filter(
            GoodsReceipt.campus_id == campus.id,
            GoodsReceipt.purchase_id == purchase.id,
        )
        .first()
    )

    if not receipt:
        receipt_date = purchase.purchase_date + timedelta(days=1)

        receipt = GoodsReceipt(
            campus_id=campus.id,
            purchase_id=purchase.id,
            receipt_date=receipt_date,
            status="ACCEPTED",
            remarks="Synthetic demonstration goods receipt",
            accepted_by=admin.id,
            accepted_at=datetime.now(UTC),
            created_by=store_keeper.id,
        )

        db.add(receipt)
        db.flush()

        for index, purchase_line in enumerate(purchase_lines):
            received = quantity(purchase_line.quantity)

            rejected = (
                quantity("1.000") if index == 0
                else quantity("0.000")
            )

            accepted = quantity(received - rejected)

            receipt_item = GoodsReceiptItem(
                campus_id=campus.id,
                receipt_id=receipt.id,
                purchase_item_id=purchase_line.id,
                quantity_received=received,
                quantity_accepted=accepted,
                quantity_rejected=rejected,
                remarks="Synthetic demonstration receipt",
            )

            db.add(receipt_item)
            db.flush()

            if accepted > 0:
                movement = StockMovement(
                    campus_id=campus.id,
                    item_id=purchase_line.item_id,
                    movement_type="RECEIPT",
                    quantity=accepted,
                    unit_id=purchase_line.unit_id,
                    receipt_item_id=receipt_item.id,
                    reference_type="GOODS_RECEIPT",
                    reference_id=receipt.id,
                    remarks="Accepted demo receipt quantity",
                    created_by=admin.id,
                )

                db.add(movement)

    existing_payment = (
        db.query(SupplierPayment)
        .filter(
            SupplierPayment.campus_id == campus.id,
            SupplierPayment.purchase_id == purchase.id,
        )
        .first()
    )

    if not existing_payment:
        payment_amount = money(
            Decimal(str(purchase.grand_total)) / Decimal(2)
        )

        if payment_amount > 0:
            payment = SupplierPayment(
                campus_id=campus.id,
                purchase_id=purchase.id,
                payment_date=purchase.purchase_date + timedelta(days=2),
                amount=payment_amount,
                payment_method="BANK_TRANSFER",
                reference_number=f"KC-DEMO-PAY-{campus.code}",
                remarks="Synthetic partial payment",
                created_by=users[UserRole.ACCOUNTS].id,
            )

            db.add(payment)


# ---------------------------------------------------------
# HISTORICAL PURCHASE SEEDING
# ---------------------------------------------------------

def seed_historical_purchases(
    db,
    campus,
    users,
    items,
    suppliers,
):
    """Create three repeatable historical demo purchase bills."""

    admin = users[UserRole.ADMIN]
    supplier = suppliers["Demo Grain Traders"]

    historical_bills = [
        (90, "HIST-001", ("52.0000", "115.0000", "32.0000")),
        (60, "HIST-002", ("58.0000", "105.0000", "40.0000")),
        (15, "HIST-003", ("55.0000", "112.0000", "35.0000")),
    ]

    quantities = {
        "Rice": "25.000",
        "Toor Dal": "10.000",
        "Onion": "20.000",
    }

    created_count = 0

    for days_ago, suffix, rates in historical_bills:
        invoice_number = f"KC-DEMO-{campus.code}-{suffix}"

        existing = (
            db.query(Purchase)
            .filter(
                Purchase.campus_id == campus.id,
                Purchase.supplier_id == supplier.id,
                Purchase.invoice_number == invoice_number,
            )
            .first()
        )

        if existing:
            continue

        purchase_date = date.today() - timedelta(days=days_ago)

        line_data = [
            ("Rice", rates[0]),
            ("Toor Dal", rates[1]),
            ("Onion", rates[2]),
        ]

        prepared_lines = []
        subtotal = Decimal("0.00")

        for item_name, rate_text in line_data:
            item = items[item_name]
            item_quantity = quantity(quantities[item_name])
            unit_rate = Decimal(rate_text)
            line_total = money(item_quantity * unit_rate)

            subtotal += line_total

            prepared_lines.append(
                PurchaseItem(
                    campus_id=campus.id,
                    item_id=item.id,
                    quantity=item_quantity,
                    unit_id=item.standard_unit_id,
                    unit_rate=unit_rate,
                    line_total=line_total,
                    remarks="Synthetic historical demo purchase",
                )
            )

        subtotal = money(subtotal)

        purchase = Purchase(
            campus_id=campus.id,
            supplier_id=supplier.id,
            invoice_number=invoice_number,
            purchase_date=purchase_date,
            subtotal=subtotal,
            discount=Decimal("0.00"),
            extra_charges=Decimal("0.00"),
            grand_total=subtotal,
            remarks="Synthetic historical demonstration purchase",
            status="DRAFT",
            created_by=admin.id,
        )

        db.add(purchase)
        db.flush()

        for line in prepared_lines:
            line.purchase_id = purchase.id
            db.add(line)

        created_count += 1

    return created_count


# ---------------------------------------------------------
# MAIN DEMO SEED
# ---------------------------------------------------------

def seed_demo():
    db = SessionLocal()

    try:
        print("\nStarting synthetic demo-data seeding...\n")

        for campus_data in DEMO_CAMPUSES:
            campus, created = get_or_create(
                db,
                Campus,
                {"code": campus_data["code"]},
                {
                    "name": campus_data["name"],
                    "is_active": True,
                },
            )

            if campus.name != campus_data["name"]:
                raise ValueError(
                    f"Campus code conflict: {campus.code}. "
                    "Existing campus was not modified."
                )

            print(
                f"\nCampus: {campus.name} "
                f"({'created' if created else 'already exists'})"
            )

            users = get_demo_users(db, campus)

            items, _units, suppliers = seed_master_data(db, campus)

            headcounts_created = seed_daily_headcounts(
                db,
                campus,
                days=90,
            )

            print(
                f"  Daily headcounts: {headcounts_created} new records "
                "(90-day target)"
            )

            # Five arguments only: units is not required here.
            seed_purchase_and_receipt(
                db,
                campus,
                users,
                items,
                suppliers,
            )

            historical_created = seed_historical_purchases(
                db,
                campus,
                users,
                items,
                suppliers,
            )

            print(
                f"  Historical purchases: {historical_created} new bills "
                "(3-month history)"
            )

            print("  Demo users: 4")
            print(f"  Categories: {len(CATEGORIES)}")
            print(f"  Units: {len(UNITS)}")
            print(
                "  Items: "
                f"{sum(len(names) for names in ITEM_GROUPS.values())}"
            )
            print(f"  Suppliers: {len(SUPPLIERS)}")
            print(f"  Menus: {len(MENUS)}")
            print("  Purchase, receipt and partial payment: seeded")

        db.commit()

        print("\nDemo data seeded successfully!")
        print("Existing Zaitoon campus and users were not modified.")

        print("\nDemo login accounts:")

        for campus_data in DEMO_CAMPUSES:
            code = campus_data["code"].lower()

            for role in ROLE_NAMES:
                print(
                    f"{role.value}: "
                    f"{code}.{role.value.lower()}@kitchencopilot.test"
                )

        print(
            "\nUse the demo password you entered when "
            "creating the demo accounts."
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


# ---------------------------------------------------------
# COMMAND-LINE ENTRY POINT
# ---------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Kitchen Copilot database seed utility"
    )

    parser.add_argument(
        "--demo",
        action="store_true",
        help="Create repeatable synthetic demonstration data",
    )

    args = parser.parse_args()

    if args.demo:
        seed_demo()
    else:
        setup_administrator()


if __name__ == "__main__":
    main()
