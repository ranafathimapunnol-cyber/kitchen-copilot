
import jwt  # type: ignore

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User, UserRole
from app.models.authorization import Permission, StaffAccessAssignment


# ============================================================
# KITCHEN MANAGER PERMISSIONS
# ============================================================

# Approved matrix: Kitchen Managers have no access to supplier bills.
# The current purchase_order.* codes guard the supplier bill endpoints
# (/api/purchases), so they are deliberately not granted here. Real
# purchase orders, which Kitchen Managers may use, will have their own
# endpoints when they are built.
#
# Suppliers share the inventory.* codes with other master data, so the
# Kitchen Manager's read-only supplier access is enforced on the supplier
# endpoints themselves (see master_data.ensure_supplier_write_allowed).

KITCHEN_MANAGER_PERMISSIONS = {
    "dashboard.read",

    "headcount.create",
    "headcount.read",
    "headcount.update",

    "inventory.create",
    "inventory.read",
    "inventory.update",

    "consumption.create",
    "consumption.read",
    "consumption.update",

    "outsourced_food.create",
    "outsourced_food.read",
    "outsourced_food.update",

    "menu.create",
    "menu.read",
    "menu.update",

    "audit.read",

    "waste_tracking.create",
    "waste_tracking.read",
    "waste_tracking.update",
}


# ============================================================
# STAFF ASSIGNABLE PERMISSIONS
# ============================================================

# The only permissions an ADMIN may newly assign to a STAFF user, mapped
# from the approved permission matrix onto today's codes. A code is listed
# only when every action it unlocks may be assigned to STAFF individually:
# - never assignable: audit.read, menu.create, menu.update (menu and
#   portion standards stay read-only for STAFF);
# - not assignable until split into separate codes: inventory.create and
#   inventory.update (they also cover supplier writes and goods-receipt
#   acceptance) and purchase_order.* (they guard supplier bills).
# STAFF users never receive anything by default. Existing assignments
# outside this list are kept unchanged until a separately approved cleanup.

STAFF_ASSIGNABLE_PERMISSIONS = frozenset({
    "dashboard.read",

    "headcount.create",
    "headcount.read",
    "headcount.update",

    "inventory.read",

    "consumption.create",
    "consumption.read",
    "consumption.update",

    "outsourced_food.create",
    "outsourced_food.read",
    "outsourced_food.update",

    "menu.read",

    "waste_tracking.create",
    "waste_tracking.read",
    "waste_tracking.update",
})


# ============================================================
# AUTHENTICATION
# ============================================================

def get_current_user(
    access_token: str | None = Cookie(
        default=None,
        alias=settings.ACCESS_COOKIE_NAME,
    ),
    db: Session = Depends(get_db),
) -> User:

    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Cookie"},
    )

    if not access_token:
        raise credentials_error

    try:
        payload = decode_access_token(access_token)

        if payload.get("type") != "access":
            raise credentials_error

        user_id = int(payload["sub"])

    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        raise credentials_error

    user = (
        db.query(User)
        .filter(User.id == user_id)
        .first()
    )

    if not user or not user.is_active:
        raise credentials_error

    return user


# ============================================================
# ROLE-BASED AUTHORIZATION
# ============================================================

def require_roles(*roles: UserRole):

    def role_checker(
        current_user: User = Depends(get_current_user),
    ) -> User:

        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )

        return current_user

    return role_checker


# ============================================================
# PERMISSION-BASED AUTHORIZATION
# ============================================================

def require_permission(permission_code: str):

    def permission_checker(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:

        # ----------------------------------------------------
        # ADMIN: FULL ACCESS
        # ----------------------------------------------------

        if current_user.role == UserRole.ADMIN:
            return current_user

        # ----------------------------------------------------
        # KITCHEN MANAGER: APPROVED PERMISSIONS ONLY
        # ----------------------------------------------------

        if current_user.role == UserRole.KITCHEN_MANAGER:

            if permission_code in KITCHEN_MANAGER_PERMISSIONS:
                return current_user

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Kitchen Manager does not have this permission.",
            )

        # ----------------------------------------------------
        # STAFF: ADMIN-ASSIGNED PERMISSIONS ONLY
        # ----------------------------------------------------

        if current_user.role == UserRole.STAFF:

            assignment = (
                db.query(StaffAccessAssignment)
                .join(
                    Permission,
                    StaffAccessAssignment.permission_id == Permission.id,
                )
                .filter(
                    StaffAccessAssignment.staff_user_id == current_user.id,
                    StaffAccessAssignment.permission_id == Permission.id,
                    StaffAccessAssignment.is_active.is_(True),
                    Permission.permission_code == permission_code,
                )
                .first()
            )

            if assignment:
                return current_user

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This permission has not been assigned to you.",
            )

        # ----------------------------------------------------
        # UNKNOWN ROLE: DENY ACCESS
        # ----------------------------------------------------

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action.",
        )

    return permission_checker
