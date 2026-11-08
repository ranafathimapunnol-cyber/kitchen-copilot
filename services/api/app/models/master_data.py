from sqlalchemy import (
    String, Boolean, ForeignKey, Numeric, UniqueConstraint,
    CheckConstraint
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy import DateTime
from datetime import datetime

from app.db.base import Base


class CampusScoped:
    campus_id: Mapped[int] = mapped_column(
        ForeignKey("campuses.id"), nullable=False, index=True
    )


class Category(CampusScoped, Base):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("campus_id", "name", name="uq_category_campus_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Unit(CampusScoped, Base):
    __tablename__ = "units"
    __table_args__ = (
        UniqueConstraint("campus_id", "name", name="uq_unit_campus_name"),
        UniqueConstraint("campus_id", "symbol", name="uq_unit_campus_symbol"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    dimension: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class UnitConversion(CampusScoped, Base):
    __tablename__ = "unit_conversions"
    __table_args__ = (
        UniqueConstraint(
            "campus_id", "from_unit_id", "to_unit_id",
            name="uq_unit_conversion"
        ),
        CheckConstraint("factor > 0", name="ck_conversion_factor_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    from_unit_id: Mapped[int] = mapped_column(
        ForeignKey("units.id"), nullable=False
    )
    to_unit_id: Mapped[int] = mapped_column(
        ForeignKey("units.id"), nullable=False
    )
    factor: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)


class Item(CampusScoped, Base):
    __tablename__ = "items"
    __table_args__ = (
        UniqueConstraint("campus_id", "name", name="uq_item_campus_name"),
        CheckConstraint("minimum_stock >= 0", name="ck_item_minimum_stock"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id"), nullable=False
    )
    standard_unit_id: Mapped[int] = mapped_column(
        ForeignKey("units.id"), nullable=False
    )
    minimum_stock: Mapped[float] = mapped_column(
        Numeric(18, 3), default=0, nullable=False
    )
    description: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Supplier(CampusScoped, Base):
    __tablename__ = "suppliers"
    __table_args__ = (
        UniqueConstraint("campus_id", "name", name="uq_supplier_campus_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class MealSession(CampusScoped, Base):
    __tablename__ = "meal_sessions"
    __table_args__ = (
        UniqueConstraint("campus_id", "name", name="uq_meal_session_campus"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Menu(CampusScoped, Base):
    __tablename__ = "menus"
    __table_args__ = (
        UniqueConstraint("campus_id", "name", name="uq_menu_campus_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    meal_session_id: Mapped[int] = mapped_column(
        ForeignKey("meal_sessions.id"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class MenuMainItem(CampusScoped, Base):
    __tablename__ = "menu_main_items"
    __table_args__ = (
        UniqueConstraint("campus_id", "menu_id", "item_id",
                         name="uq_menu_main_item"),
        CheckConstraint(
            "quantity_per_person > 0",
            name="ck_menu_quantity_positive"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    menu_id: Mapped[int] = mapped_column(
        ForeignKey("menus.id"), nullable=False
    )
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id"), nullable=False
    )
    quantity_per_person: Mapped[float] = mapped_column(
        Numeric(18, 3), nullable=False
    )
    unit_id: Mapped[int] = mapped_column(
        ForeignKey("units.id"), nullable=False
    )
