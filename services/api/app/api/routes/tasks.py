"""Staff tasks (owner request 27 Nov 2026, migration a7d3e9b1c4f2).

- ADMIN: create, assign (to an active STAFF user of the same campus), edit,
  cancel and reopen tasks; sees every task of the campus.
- KITCHEN_MANAGER: sees every task of the campus (task.read); does not
  assign or edit.
- STAFF: with task.read, sees only their own tasks; with task.update, moves
  their own task OPEN -> IN_PROGRESS -> DONE (or back to IN_PROGRESS) and
  adds a note. Never cancels, reassigns or edits.
Campus comes from the session. Every change is in the campus audit log.
"""

from datetime import date, datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_roles, user_has_permission
from app.api.routes.master_data import record_audit
from app.core.clock import utc_iso
from app.db.session import get_db
from app.models.tasks import CATEGORIES, PRIORITIES, StaffTask
from app.models.user import User, UserRole

router = APIRouter(prefix="/api/tasks", tags=["Staff tasks"])
admins = require_roles(UserRole.ADMIN)

Category = Literal["PURCHASE", "INVENTORY", "STOCK_COUNT", "GOODS_RECEIPT", "MEAL_PREPARATION", "CLEANING", "WASTE",
                   "GENERAL"]
Priority = Literal["LOW", "NORMAL", "HIGH"]
STAFF_MOVES = {("OPEN", "IN_PROGRESS"), ("IN_PROGRESS", "DONE"), ("OPEN", "DONE"), ("DONE", "IN_PROGRESS")}


def tidy(value: str | None) -> str | None:
    value = " ".join(value.split()) if value else None
    return value or None


class TaskInput(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    category: Category
    priority: Priority = "NORMAL"
    assigned_to: int = Field(gt=0)
    due_date: date | None = None

    @field_validator("title")
    @classmethod
    def clean_title(cls, v: str) -> str:
        v = tidy(v) or ""
        if len(v) < 3:
            raise ValueError("Enter at least three characters.")
        return v

    @field_validator("description")
    @classmethod
    def clean_description(cls, v: str | None) -> str | None:
        return v.strip() or None if v else None


class StatusInput(BaseModel):
    status: Literal["OPEN", "IN_PROGRESS", "DONE", "CANCELLED"]
    note: str | None = Field(default=None, max_length=1000)
    version: int = Field(ge=1)


def reader(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
    if not user_has_permission(db, user, "task.read"):
        raise HTTPException(status_code=403, detail="Tasks have not been assigned to you.")
    return user


def assignee(db: Session, campus_id: int, user_id: int) -> User:
    person = db.query(User).filter(User.id == user_id, User.campus_id == campus_id).first()
    if not person or person.role != UserRole.STAFF or not person.is_active:
        raise HTTPException(status_code=422, detail="Assign the task to an active Staff member of this campus.")
    return person


def task_for(db: Session, user: User, task_id: int, lock: bool = False) -> StaffTask:
    query = db.query(StaffTask).filter(StaffTask.id == task_id, StaffTask.campus_id == user.campus_id)
    if user.role == UserRole.STAFF:
        query = query.filter(StaffTask.assigned_to == user.id)
    task = (query.with_for_update() if lock else query).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def out(task: StaffTask, people: dict[int, str]) -> dict:
    return {"id": task.id, "title": task.title, "description": task.description, "category": task.category,
            "priority": task.priority, "status": task.status, "assigned_to": task.assigned_to,
            "assigned_to_name": people.get(task.assigned_to), "due_date": task.due_date.isoformat() if task.due_date else None,
            "staff_note": task.staff_note, "created_by": task.created_by, "created_by_name": people.get(task.created_by),
            "created_at": utc_iso(task.created_at), "updated_at": utc_iso(task.updated_at),
            "completed_at": utc_iso(task.completed_at) if task.completed_at else None, "version": task.version}


def names(db: Session, ids) -> dict[int, str]:
    ids = {i for i in ids if i}
    return dict(db.query(User.id, User.full_name).filter(User.id.in_(ids or {0})))


@router.get("")
def list_tasks(status: Literal["OPEN", "IN_PROGRESS", "DONE", "CANCELLED", "ACTIVE"] | None = None,
               category: Category | None = None, assigned_to: int | None = Query(default=None, gt=0),
               q: str | None = Query(default=None, max_length=100),
               db: Session = Depends(get_db), user: User = Depends(reader)):
    query = db.query(StaffTask).filter(StaffTask.campus_id == user.campus_id)
    if user.role == UserRole.STAFF:
        query = query.filter(StaffTask.assigned_to == user.id)
    elif assigned_to:
        query = query.filter(StaffTask.assigned_to == assigned_to)
    if status == "ACTIVE":
        query = query.filter(StaffTask.status.in_(["OPEN", "IN_PROGRESS"]))
    elif status:
        query = query.filter(StaffTask.status == status)
    if category:
        query = query.filter(StaffTask.category == category)
    if q:
        like = f"%{q.strip().lower()}%"
        query = query.filter(or_(func.lower(StaffTask.title).like(like), func.lower(StaffTask.description).like(like)))
    rows = query.order_by(StaffTask.status.in_(["DONE", "CANCELLED"]), StaffTask.due_date.is_(None), StaffTask.due_date,
                          StaffTask.id.desc()).limit(500).all()
    people = names(db, [t.assigned_to for t in rows] + [t.created_by for t in rows])
    can_manage = user.role == UserRole.ADMIN
    staff = []
    if can_manage:
        staff = [{"id": s.id, "full_name": s.full_name} for s in db.query(User).filter(
            User.campus_id == user.campus_id, User.role == UserRole.STAFF, User.is_active.is_(True)).order_by(User.full_name)]
    return {"items": [out(t, people) for t in rows], "can_manage": can_manage,
            "can_update_own": user.role == UserRole.ADMIN or user_has_permission(db, user, "task.update"),
            "staff": staff, "categories": list(CATEGORIES), "priorities": list(PRIORITIES)}


@router.post("", status_code=201)
def create_task(payload: TaskInput, db: Session = Depends(get_db), admin: User = Depends(admins)):
    person = assignee(db, admin.campus_id, payload.assigned_to)
    task = StaffTask(campus_id=admin.campus_id, title=payload.title, description=payload.description,
                     category=payload.category, priority=payload.priority, assigned_to=person.id,
                     due_date=payload.due_date, created_by=admin.id, status="OPEN", version=1)
    db.add(task)
    db.flush()
    record_audit(db, admin, "CREATE", "STAFF_TASK", task.id, {"title": task.title, "category": task.category,
                                                               "assigned_to": person.id, "due_date": payload.due_date})
    db.commit()
    return out(task, names(db, [task.assigned_to, task.created_by]))


@router.put("/{task_id}")
def edit_task(task_id: int, payload: TaskInput, version: int = Query(ge=1), db: Session = Depends(get_db),
              admin: User = Depends(admins)):
    task = task_for(db, admin, task_id, lock=True)
    if task.version != version:
        raise HTTPException(status_code=409, detail="Someone else changed this task. Reload and try again.")
    if task.status in ("DONE", "CANCELLED"):
        raise HTTPException(status_code=409, detail="Reopen the task before editing it.")
    person = assignee(db, admin.campus_id, payload.assigned_to)
    fields = ("title", "description", "category", "priority", "assigned_to", "due_date")
    before = {f: getattr(task, f) for f in fields}
    task.title, task.description, task.category = payload.title, payload.description, payload.category
    task.priority, task.assigned_to, task.due_date = payload.priority, person.id, payload.due_date
    changes = {f: {"from": before[f], "to": getattr(task, f)} for f in fields if before[f] != getattr(task, f)}
    if changes:
        task.version += 1
        task.updated_at = datetime.now(timezone.utc)
        record_audit(db, admin, "UPDATE", "STAFF_TASK", task.id, {"changes": changes})
    db.commit()
    return out(task, names(db, [task.assigned_to, task.created_by]))


@router.post("/{task_id}/status")
def change_status(task_id: int, payload: StatusInput, db: Session = Depends(get_db), user: User = Depends(reader)):
    task = task_for(db, user, task_id, lock=True)
    if task.version != payload.version:
        raise HTTPException(status_code=409, detail="Someone else changed this task. Reload and try again.")
    move = (task.status, payload.status)
    if task.status == payload.status:
        raise HTTPException(status_code=409, detail=f"The task is already {task.status.replace('_', ' ').lower()}.")
    if user.role == UserRole.ADMIN:
        pass                                                         # any move, including cancel and reopen
    elif user.role == UserRole.STAFF and user_has_permission(db, user, "task.update"):
        if move not in STAFF_MOVES:
            raise HTTPException(status_code=403, detail="Staff can start, finish or restart their own tasks only.")
    else:
        raise HTTPException(status_code=403, detail="You cannot change this task's status.")
    task.status = payload.status
    task.completed_at = datetime.now(timezone.utc) if payload.status == "DONE" else None
    if payload.note is not None and payload.note.strip():
        task.staff_note = payload.note.strip()
    task.version += 1
    task.updated_at = datetime.now(timezone.utc)
    record_audit(db, user, "STATUS", "STAFF_TASK", task.id, {"from": move[0], "to": move[1],
                                                             "note": task.staff_note if payload.note else None})
    db.commit()
    return out(task, names(db, [task.assigned_to, task.created_by]))
