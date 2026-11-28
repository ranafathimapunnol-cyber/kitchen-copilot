"""Staff tasks (migration a7d3e9b1c4f2). A campus ADMIN creates, assigns,
edits and cancels tasks for the campus's STAFF; the assignee updates the
status of their own task (task.update); task.read lets STAFF see their own
tasks. Every change is in the campus audit log."""

from datetime import date, datetime, timezone

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

CATEGORIES = ("PURCHASE", "INVENTORY", "STOCK_COUNT", "GOODS_RECEIPT", "MEAL_PREPARATION", "CLEANING", "WASTE",
              "GENERAL")
PRIORITIES = ("LOW", "NORMAL", "HIGH")
STATUSES = ("OPEN", "IN_PROGRESS", "DONE", "CANCELLED")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class StaffTask(Base):
    __tablename__ = "staff_tasks"
    __table_args__ = (
        CheckConstraint("category IN ('" + "','".join(CATEGORIES) + "')", name="ck_staff_task_category"),
        CheckConstraint("priority IN ('" + "','".join(PRIORITIES) + "')", name="ck_staff_task_priority"),
        CheckConstraint("status IN ('" + "','".join(STATUSES) + "')", name="ck_staff_task_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    campus_id: Mapped[int] = mapped_column(ForeignKey("campuses.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default="NORMAL")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")
    assigned_to: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    staff_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
