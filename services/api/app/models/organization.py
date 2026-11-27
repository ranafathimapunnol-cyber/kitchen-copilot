"""Organisations (Stage 11). An organisation groups campuses. SUPER_ADMIN
accounts manage the organisation and its campuses and never take part in
campus operations."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


Index("uq_organizations_name_ci", func.lower(Organization.name), unique=True)
Index("uq_organizations_code_ci", func.lower(Organization.code), unique=True)
