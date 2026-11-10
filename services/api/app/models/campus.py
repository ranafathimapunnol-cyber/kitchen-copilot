from sqlalchemy import Boolean, String  # pyright: ignore[reportMissingImports]
from sqlalchemy.orm import Mapped, mapped_column  # type: ignore

from app.db.base import Base


class Campus(Base):
    __tablename__ = "campuses"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
