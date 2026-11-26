
import enum

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserRole(str, enum.Enum):
    # Stage 11 (dormant): the database role type gains SUPER_ADMIN only with
    # migration M1, which needs its own explicit authorization. Until then no
    # account can have it; the guards for it are already in place.
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    KITCHEN_MANAGER = "KITCHEN_MANAGER"
    STAFF = "STAFF"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)

    campus_id: Mapped[int] = mapped_column(
        ForeignKey("campuses.id"),
        nullable=False,
    )

    full_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="userrole"),
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Stage 10: tokens issued before this moment are refused (sign out
    # everywhere, deactivation, Admin revocation).
    sessions_revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
