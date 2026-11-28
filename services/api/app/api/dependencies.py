
import jwt  # type: ignore

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_access_token, fingerprint_matches
from app.db.session import get_db
from app.models.user import User, UserRole
from app.models.authorization import Permission, StaffAccessAssignment


# ============================================================
# KITCHEN MANAGER PERMISSIONS
# ============================================================

# Kitchen Managers have the same operational authority as ADMIN: every
# operational permission code, including purchase_bill.* (supplier bills,
# recording and viewing supplier payments, supplier balances),
# purchase_order.* (genuine purchase orders, from 18 November 2026) and full
# supplier management. Role rules confirmed 17 November 2026; there is no
# payment or purchase approval step.
#
# What stays ADMIN-only is enforced by role, not by these codes:
# - creating users and managing staff permissions (require_roles ADMIN);
# - permanently deleting master data and waste records (ADMIN-only
#   delete endpoints). Kitchen Managers may still deactivate records.

KITCHEN_MANAGER_PERMISSIONS = {
    "dashboard.read",

    "headcount.create",
    "headcount.read",
    "headcount.update",

    "inventory.create",
    "inventory.read",
    "inventory.update",

    "purchase_bill.create",
    "purchase_bill.read",
    "purchase_bill.update",

    "purchase_order.create",
    "purchase_order.read",
    "purchase_order.update",

    "consumption.create",
    "consumption.read",
    "consumption.update",

    # Physical stock counts (Stage 4 slice 4c, decision S1, approved 23
    # November 2026). Approving or rejecting an adjustment is a role check
    # (ADMIN or KITCHEN_MANAGER who did not count), not one of these codes.
    "stock_count.create",
    "stock_count.read",

    # Meal records (Stage 5, decision 5-1, approved 23 November 2026).
    # Reopening a closed record is a role check (ADMIN, KITCHEN_MANAGER).
    "meal.create",
    "meal.read",
    "meal.update",

    # Meal planning (Stage 6, decisions 6-3 to 6-5, approved 24 November
    # 2026). Not STAFF-assignable; the planning endpoints also require the
    # ADMIN or KITCHEN_MANAGER role, and approving is a role check.
    "portion_standard.create",
    "portion_standard.read",
    "portion_standard.update",
    "meal_plan.create",
    "meal_plan.read",
    "meal_plan.update",

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

    # Migration a7d3e9b1c4f2 (27 November 2026): the Kitchen Manager keeps
    # every kitchen operation it had (goods receipts were inventory.*), sees
    # reports, uses Copilot and sees the campus's tasks. Assigning tasks and
    # managing users or permissions stay with the ADMIN.
    "goods_receipt.create",
    "goods_receipt.read",
    "goods_receipt.update",
    "report.read",
    "task.read",
    "copilot.read",
}


# ============================================================
# STAFF ASSIGNABLE PERMISSIONS
# ============================================================

# The only permissions an ADMIN may newly assign to a STAFF user, mapped
# from the approved permission matrix onto today's codes. A code is listed
# only when every action it unlocks may be assigned to STAFF individually:
# - never assignable: audit.read, menu.create, menu.update (menu and
#   portion standards stay read-only for STAFF), and the Stage 6 planning
#   codes portion_standard.* and meal_plan.* (decision 6-3);
# - not assignable until split into separate codes: inventory.create and
#   inventory.update (they also cover supplier writes and goods-receipt
#   acceptance);
# - not assignable until the STAFF list is changed by approval:
#   purchase_bill.* (supplier bills) and purchase_order.* (purchase orders,
#   which guarded bills until 18 November 2026). Older STAFF grants of
#   purchase_order.* were copied to purchase_bill.* by migration
#   a3c9e1f47b20; the copies keep bill access, and the original rows stay
#   unchanged as history but grant a STAFF user nothing
#   (STAFF_EXCLUDED_PERMISSIONS below).
# STAFF users never receive anything by default. Existing assignments
# outside this list are kept unchanged until a separately approved cleanup.

# Purchase orders are ADMIN and KITCHEN_MANAGER work (decision 20 November
# 2026). A STAFF user never holds these codes, whatever assignments exist:
# migration a3c9e1f47b20 kept older purchase_order.* rows (which guarded
# supplier bills until 18 November 2026) and copied them to purchase_bill.*.
# Those rows stay unchanged as history but grant nothing; bill access comes
# from the purchase_bill.* copies.
STAFF_EXCLUDED_PERMISSIONS = frozenset({
    "purchase_order.create",
    "purchase_order.read",
    "purchase_order.update",
})

STAFF_ASSIGNABLE_PERMISSIONS = frozenset({
    "dashboard.read",

    "headcount.create",
    "headcount.read",
    "headcount.update",

    "inventory.read",

    "consumption.create",
    "consumption.read",
    "consumption.update",

    # Decision S1 (23 November 2026): recording counts and raising
    # adjustment requests, and viewing them. Never approving them.
    "stock_count.create",
    "stock_count.read",

    # Decision 5-1 (23 November 2026): an Admin may assign meal recording to
    # kitchen staff; never granted by default. Reopening is never STAFF.
    "meal.create",
    "meal.read",
    "meal.update",

    "outsourced_food.create",
    "outsourced_food.read",
    "outsourced_food.update",

    "menu.read",

    "waste_tracking.create",
    "waste_tracking.read",
    "waste_tracking.update",

    # Owner request 27 November 2026 (Admin → Staff permissions):
    # supplier bills (purchasing), goods receipts (their own codes, so a
    # receipt grant no longer needs inventory.create/update, which also cover
    # items and suppliers), reports, tasks and Kitchen Copilot. Purchase
    # orders stay ADMIN and KITCHEN_MANAGER only (STAFF_EXCLUDED_PERMISSIONS).
    "purchase_bill.create",
    "purchase_bill.read",
    "purchase_bill.update",
    "goods_receipt.create",
    "goods_receipt.read",
    "goods_receipt.update",
    "report.read",
    "task.read",
    "task.update",
    "copilot.read",
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

    # Stage 11: platform accounts never hold a campus session; they use the
    # separate platform sign-in (app/api/platform_auth.py).
    if user.role == UserRole.SUPER_ADMIN or user.campus_id is None:
        raise credentials_error

    # The token must carry the fingerprint of the current password. After
    # a password reset it no longer matches, so every session issued before
    # the reset is rejected.
    if not fingerprint_matches(payload, user.password_hash):
        raise credentials_error

    # Stage 10: "sign out everywhere", deactivation and Admin revocation
    # refuse every token issued before that moment.
    if session_revoked(user, payload):
        raise credentials_error

    # Stage 11: a deactivated campus keeps all its records, but its users
    # cannot use the application until the campus is activated again.
    if not campus_is_active(db, user.campus_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=CAMPUS_INACTIVE_MESSAGE)

    return user


CAMPUS_INACTIVE_MESSAGE = ("This campus has been deactivated. Its records are kept; "
                           "contact your organisation's platform administrator.")


def campus_is_active(db: Session, campus_id: int | None) -> bool:
    from app.models.campus import Campus

    active = db.query(Campus.is_active).filter(Campus.id == campus_id).scalar()
    return active is not False


def session_revoked(user: User, payload: dict) -> bool:
    revoked_at = getattr(user, "sessions_revoked_at", None)
    if revoked_at is None:
        return False
    try:
        issued = int(payload.get("iat"))
    except (TypeError, ValueError):
        return True
    if revoked_at.tzinfo is None:
        from datetime import timezone

        revoked_at = revoked_at.replace(tzinfo=timezone.utc)
    return issued < int(revoked_at.timestamp())


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
        # SUPER_ADMIN: organisations and campuses only (Stage 11)
        # ----------------------------------------------------

        if current_user.role == UserRole.SUPER_ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Super administrators manage organisations and campuses, not campus operations.",
            )

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

            if permission_code in STAFF_EXCLUDED_PERMISSIONS:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Purchase orders are handled by Admins and Kitchen Managers only.",
                )

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


def require_any_permission(*codes: str):
    """Passes when the user holds any one of the codes (same rules as
    require_permission for each)."""

    def checker(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        if any(user_has_permission(db, current_user, code) for code in codes):
            return current_user
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You do not have permission to perform this action.")

    return checker


def user_has_permission(db: Session, user: User, permission_code: str) -> bool:
    """The same rule as require_permission, without raising."""
    if user.role == UserRole.SUPER_ADMIN:
        return False
    if user.role == UserRole.ADMIN:
        return True
    if user.role == UserRole.KITCHEN_MANAGER:
        return permission_code in KITCHEN_MANAGER_PERMISSIONS
    if user.role == UserRole.STAFF:
        if permission_code in STAFF_EXCLUDED_PERMISSIONS:
            return False
        return (
            db.query(StaffAccessAssignment.id)
            .join(Permission, StaffAccessAssignment.permission_id == Permission.id)
            .filter(
                StaffAccessAssignment.staff_user_id == user.id,
                StaffAccessAssignment.is_active.is_(True),
                Permission.permission_code == permission_code,
            )
            .first()
            is not None
        )
    return False
