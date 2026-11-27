from datetime import datetime

from sqlalchemy import Boolean, DateTime, FetchedValue, ForeignKey, Index, String, func  # pyright: ignore[reportMissingImports]
from sqlalchemy.orm import Mapped, mapped_column  # type: ignore

from app.db.base import Base


class Campus(Base):
    __tablename__ = "campuses"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Stage 11 (migration M1). Deferred, so campus screens never select these
    # columns, and marked FetchedValue (with eager_defaults off), so an INSERT
    # leaves them out unless they are set: campus code keeps working on a
    # database without them. Only the platform routes (which need M1) use them.
    __mapper_args__ = {"eager_defaults": False}
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id"), nullable=True, deferred=True, server_default=FetchedValue())
    address: Mapped[str | None] = mapped_column(String(500), nullable=True, deferred=True, server_default=FetchedValue())
    contact_name: Mapped[str | None] = mapped_column(String(150), nullable=True, deferred=True, server_default=FetchedValue())
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True, deferred=True, server_default=FetchedValue())
    contact_phone: Mapped[str | None] = mapped_column(String(40), nullable=True, deferred=True, server_default=FetchedValue())
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, deferred=True, server_default=FetchedValue())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, deferred=True, server_default=FetchedValue())
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, deferred=True, server_default=FetchedValue())
    deactivation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True, deferred=True, server_default=FetchedValue())

    # Campus logo and photo (migration e2b7c4d9a5f1): the storage key of the
    # current file of each, re-encoded by app/services/campus_media.py.
    logo_key: Mapped[str | None] = mapped_column(String(200), nullable=True, deferred=True, server_default=FetchedValue())
    photo_key: Mapped[str | None] = mapped_column(String(200), nullable=True, deferred=True, server_default=FetchedValue())
    media_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, deferred=True, server_default=FetchedValue())


# M1: no two campuses whose name or code differ only in letter case.
Index("uq_campuses_name_ci", func.lower(Campus.name), unique=True)
Index("uq_campuses_code_ci", func.lower(Campus.code), unique=True)
