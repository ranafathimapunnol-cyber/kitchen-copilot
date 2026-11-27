
import enum

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, FetchedValue, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserRole(str, enum.Enum):
    # Stage 11: the platform (organisation-level) role. It has no campus and
    # no campus permission; it signs in through the platform sign-in only.
    # The database role type gains it with migration M1 (d5e8f0b2a314).
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    KITCHEN_MANAGER = "KITCHEN_MANAGER"
    STAFF = "STAFF"


class User(Base):
    __tablename__ = "users"
    __mapper_args__ = {"eager_defaults": False}
    __table_args__ = (
        # Only SUPER_ADMIN has no campus; every other account has one (M1).
        CheckConstraint(
            "(CAST(role AS VARCHAR) = 'SUPER_ADMIN') = (campus_id IS NULL)",
            name="ck_user_campus_by_role",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)

    # None only for SUPER_ADMIN (M1 makes the column nullable).
    campus_id: Mapped[int | None] = mapped_column(
        ForeignKey("campuses.id"),
        nullable=True,
    )

    # M1: the organisation a SUPER_ADMIN manages (None = every organisation).
    # Deferred, so campus code never selects it and keeps working on a
    # database that does not have the column yet.
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id"),
        nullable=True,
        deferred=True,
        # Left out of INSERTs unless set (see Campus for why).
        server_default=FetchedValue(),
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
