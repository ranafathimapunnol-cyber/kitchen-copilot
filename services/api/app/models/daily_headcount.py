from datetime import date, datetime

from sqlalchemy import (  # type: ignore
    CheckConstraint,
    Date,
    DateTime,
    Integer,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column  # type: ignore

from app.db.base import Base
from app.models.master_data import CampusScoped


class DailyHeadcount(CampusScoped, Base):
    __tablename__ = "daily_headcounts"
    __table_args__ = (
        UniqueConstraint(
            "campus_id",
            "headcount_date",
            name="uq_daily_headcount_campus_date",
        ),
        CheckConstraint(
            "student_count >= 0",
            name="ck_daily_headcount_nonnegative",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    headcount_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    student_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
