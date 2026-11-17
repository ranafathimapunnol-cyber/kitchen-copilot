from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.master_data import CampusScoped


class WasteRecord(CampusScoped, Base):
    """
    Main waste report for a particular date and meal session.
    """

    __tablename__ = "waste_records"

    __table_args__ = (
        Index(
            "ix_waste_records_campus_date",
            "campus_id",
            "waste_date",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    waste_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    meal_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("meal_sessions.id"),
        nullable=True,
    )

    recorded_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class WasteItem(CampusScoped, Base):
    """
    Individual raw ingredient or prepared food waste entry.

    RAW_INGREDIENT:
        item_id is required.

    PREPARED_FOOD:
        food_name is required.
        item_id must be NULL.
        menu_id can optionally identify the related menu.
    """

    __tablename__ = "waste_items"

    __table_args__ = (
        CheckConstraint(
            "quantity > 0",
            name="ck_waste_item_quantity_positive",
        ),
        CheckConstraint(
            "estimated_cost >= 0",
            name="ck_waste_item_cost_nonnegative",
        ),
        CheckConstraint(
            "waste_type IN ('RAW_INGREDIENT', 'PREPARED_FOOD')",
            name="ck_waste_item_type",
        ),
        CheckConstraint(
            """
            (
                waste_type = 'RAW_INGREDIENT'
                AND item_id IS NOT NULL
            )
            OR
            (
                waste_type = 'PREPARED_FOOD'
                AND item_id IS NULL
                AND length(trim(food_name)) > 0
            )
            """,
            name="ck_waste_item_type_reference",
        ),
        CheckConstraint(
            """
            waste_stage IN (
                'STORAGE',
                'PREPARATION',
                'COOKING',
                'SERVING',
                'AFTER_MEAL'
            )
            """,
            name="ck_waste_item_stage",
        ),
        CheckConstraint(
            """
            waste_reason IN (
                'SPOILED',
                'EXPIRED',
                'DAMAGED',
                'OVERPRODUCTION',
                'LEFTOVER',
                'PLATE_WASTE',
                'OTHER'
            )
            """,
            name="ck_waste_item_reason",
        ),
        Index(
            "ix_waste_items_record_id",
            "waste_record_id",
        ),
        Index(
            "ix_waste_items_campus_type",
            "campus_id",
            "waste_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    waste_record_id: Mapped[int] = mapped_column(
        ForeignKey("waste_records.id"),
        nullable=False,
    )

    item_id: Mapped[int | None] = mapped_column(
        ForeignKey("items.id"),
        nullable=True,
    )

    menu_id: Mapped[int | None] = mapped_column(
        ForeignKey("menus.id"),
        nullable=True,
    )

    unit_id: Mapped[int] = mapped_column(
        ForeignKey("units.id"),
        nullable=False,
    )

    food_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    waste_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 3),
        nullable=False,
    )

    waste_stage: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    waste_reason: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    estimated_cost: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=Decimal("0"),
        nullable=False,
    )
