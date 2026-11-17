
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import (
    STAFF_ASSIGNABLE_PERMISSIONS,
    get_current_user,
    require_roles,
)
from app.db.session import get_db
from app.models.authorization import (
    Module,
    Permission,
    StaffAccessAssignment,
)
from app.models.audit_log import AuditLog
from app.models.user import User, UserRole


router = APIRouter(
    prefix="/api/authorization",
    tags=["Authorization"],
)


# ============================================================
# REQUEST SCHEMAS
# ============================================================

class StaffPermissionUpdate(BaseModel):
    permission_ids: list[int] = Field(default_factory=list)


# ============================================================
# HELPERS
# ============================================================

def get_campus_staff(
    user_id: int,
    admin: User,
    db: Session,
) -> User:
    staff = (
        db.query(User)
        .filter(
            User.id == user_id,
            User.campus_id == admin.campus_id,
            User.role == UserRole.STAFF,
            User.is_active.is_(True),
        )
        .first()
    )

    if not staff:
        raise HTTPException(
            status_code=404,
            detail="Staff member not found.",
        )

    return staff


def get_active_staff_permissions(
    staff_user_id: int,
    db: Session,
):
    rows = (
        db.query(
            Permission.id,
            Permission.permission_code,
            Permission.action,
            Module.id.label("module_id"),
            Module.name.label("module_name"),
            Module.code.label("module_code"),
        )
        .join(Module, Module.id == Permission.module_id)
        .join(
            StaffAccessAssignment,
            StaffAccessAssignment.permission_id == Permission.id,
        )
        .filter(
            StaffAccessAssignment.staff_user_id == staff_user_id,
            StaffAccessAssignment.is_active.is_(True),
        )
        .order_by(Module.id, Permission.id)
        .all()
    )

    return [
        {
            "id": row.id,
            "permission_code": row.permission_code,
            "action": row.action,
            "module_id": row.module_id,
            "module_name": row.module_name,
            "module_code": row.module_code,
            "assignable": (
                row.permission_code in STAFF_ASSIGNABLE_PERMISSIONS
            ),
        }
        for row in rows
    ]


# ============================================================
# CURRENT USER PERMISSIONS
# ============================================================

@router.get("/me")
def get_my_permissions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role == UserRole.ADMIN:
        permissions = [
            permission.permission_code
            for permission in db.query(Permission)
            .order_by(Permission.id)
            .all()
        ]

    elif current_user.role == UserRole.KITCHEN_MANAGER:
        from app.api.dependencies import KITCHEN_MANAGER_PERMISSIONS

        permissions = sorted(KITCHEN_MANAGER_PERMISSIONS)

    else:
        permissions = [
            item["permission_code"]
            for item in get_active_staff_permissions(
                current_user.id,
                db,
            )
        ]

    return {
        "user_id": current_user.id,
        "role": current_user.role.value,
        "permissions": permissions,
    }


# ============================================================
# ADMIN: LIST MODULES AND PERMISSIONS
# ============================================================

@router.get("/modules")
def list_modules_and_permissions(
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(UserRole.ADMIN)),
):
    modules = (
        db.query(Module)
        .order_by(Module.id)
        .all()
    )

    result = []

    for module in modules:
        permissions = (
            db.query(Permission)
            .filter(Permission.module_id == module.id)
            .order_by(Permission.id)
            .all()
        )

        result.append({
            "id": module.id,
            "name": module.name,
            "code": module.code,
            "permissions": [
                {
                    "id": permission.id,
                    "action": permission.action,
                    "permission_code": permission.permission_code,
                    # Whether an ADMIN may assign it to a STAFF user.
                    "assignable": (
                        permission.permission_code
                        in STAFF_ASSIGNABLE_PERMISSIONS
                    ),
                }
                for permission in permissions
            ],
        })

    return result


# ============================================================
# ADMIN: LIST STAFF
# ============================================================

@router.get("/staff")
def list_staff(
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(UserRole.ADMIN)),
):
    staff_members = (
        db.query(User)
        .filter(
            User.campus_id == admin.campus_id,
            User.role == UserRole.STAFF,
            User.is_active.is_(True),
        )
        .order_by(User.full_name)
        .all()
    )

    return [
        {
            "id": staff.id,
            "full_name": staff.full_name,
            "email": staff.email,
            "is_active": staff.is_active,
        }
        for staff in staff_members
    ]


# ============================================================
# ADMIN: VIEW ONE STAFF MEMBER'S PERMISSIONS
# ============================================================

@router.get("/staff/{user_id}")
def get_staff_permissions(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(UserRole.ADMIN)),
):
    staff = get_campus_staff(user_id, admin, db)

    return {
        "staff": {
            "id": staff.id,
            "full_name": staff.full_name,
            "email": staff.email,
            "is_active": staff.is_active,
        },
        "permissions": get_active_staff_permissions(staff.id, db),
    }


# ============================================================
# ADMIN: ASSIGN OR REPLACE STAFF PERMISSIONS
# ============================================================

@router.put("/staff/{user_id}/permissions")
def update_staff_permissions(
    user_id: int,
    data: StaffPermissionUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(UserRole.ADMIN)),
):
    staff = get_campus_staff(user_id, admin, db)

    if len(data.permission_ids) != len(set(data.permission_ids)):
        raise HTTPException(
            status_code=422,
            detail="Duplicate permission IDs are not allowed.",
        )

    selected_ids = set(data.permission_ids)

    if selected_ids:
        existing_permissions = (
            db.query(Permission.id, Permission.permission_code)
            .filter(Permission.id.in_(selected_ids))
            .all()
        )

        existing_ids = {row.id for row in existing_permissions}

        if existing_ids != selected_ids:
            raise HTTPException(
                status_code=422,
                detail="One or more permission IDs are invalid.",
            )

        not_assignable = sorted(
            row.permission_code
            for row in existing_permissions
            if row.permission_code not in STAFF_ASSIGNABLE_PERMISSIONS
        )

        if not_assignable:
            raise HTTPException(
                status_code=422,
                detail=(
                    "These permissions cannot be assigned to staff: "
                    f"{', '.join(not_assignable)}."
                ),
            )

    assignable_ids = {
        row.id
        for row in db.query(Permission.id).filter(
            Permission.permission_code.in_(STAFF_ASSIGNABLE_PERMISSIONS)
        )
    }

    assignments = (
        db.query(StaffAccessAssignment)
        .filter(
            StaffAccessAssignment.staff_user_id == staff.id,
        )
        .all()
    )

    assignment_by_permission = {
        assignment.permission_id: assignment
        for assignment in assignments
    }

    newly_assigned = []
    reactivated = []
    revoked = []
    kept_not_assignable = []

    # Reactivate existing assignments or create new ones.
    for permission_id in selected_ids:
        assignment = assignment_by_permission.get(permission_id)

        if assignment:
            if not assignment.is_active:
                assignment.is_active = True
                assignment.assigned_by = admin.id
                reactivated.append(permission_id)
        else:
            db.add(
                StaffAccessAssignment(
                    staff_user_id=staff.id,
                    permission_id=permission_id,
                    assigned_by=admin.id,
                    is_active=True,
                )
            )
            newly_assigned.append(permission_id)

    # Deactivate assignable permissions that are no longer selected.
    # Older assignments that are no longer assignable are kept unchanged
    # until a separately approved cleanup.
    for assignment in assignments:
        if (
            not assignment.is_active
            or assignment.permission_id in selected_ids
        ):
            continue

        if assignment.permission_id not in assignable_ids:
            kept_not_assignable.append(assignment.permission_id)
            continue

        assignment.is_active = False
        revoked.append(assignment.permission_id)

    db.add(
        AuditLog(
            campus_id=admin.campus_id,
            user_id=admin.id,
            action="UPDATE",
            entity_type="STAFF_ACCESS",
            entity_id=staff.id,
            details={
                "staff_user_id": staff.id,
                "newly_assigned": newly_assigned,
                "reactivated": reactivated,
                "revoked": revoked,
                "kept_not_assignable": sorted(kept_not_assignable),
                "active_permission_ids": sorted(
                    selected_ids | set(kept_not_assignable)
                ),
            },
        )
    )

    db.commit()

    return {
        "message": "Staff permissions updated successfully.",
        "staff_user_id": staff.id,
        "permissions": get_active_staff_permissions(staff.id, db),
    }


# ============================================================
# ADMIN: REVOKE ONE STAFF PERMISSION
# ============================================================

@router.delete("/staff/{user_id}/permissions/{permission_id}")
def revoke_staff_permission(
    user_id: int,
    permission_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(UserRole.ADMIN)),
):
    staff = get_campus_staff(user_id, admin, db)

    assignment = (
        db.query(StaffAccessAssignment)
        .filter(
            StaffAccessAssignment.staff_user_id == staff.id,
            StaffAccessAssignment.permission_id == permission_id,
        )
        .first()
    )

    if not assignment or not assignment.is_active:
        raise HTTPException(
            status_code=404,
            detail="Active permission assignment not found.",
        )

    assignment.is_active = False

    db.add(
        AuditLog(
            campus_id=admin.campus_id,
            user_id=admin.id,
            action="DELETE",
            entity_type="STAFF_ACCESS",
            entity_id=staff.id,
            details={
                "staff_user_id": staff.id,
                "revoked_permission_id": permission_id,
            },
        )
    )

    db.commit()

    return {
        "message": "Staff permission revoked successfully.",
        "staff_user_id": staff.id,
        "permission_id": permission_id,
    }
