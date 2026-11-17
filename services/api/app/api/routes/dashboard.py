from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.dependencies import (
    KITCHEN_MANAGER_PERMISSIONS,
    require_permission,
)
from app.db.session import get_db
from app.models.authorization import Permission, StaffAccessAssignment
from app.models.audit_log import AuditLog
from app.models.daily_headcount import DailyHeadcount
from app.models.master_data import Item, Menu, MealSession, Supplier, Unit
from app.models.purchases import Purchase, GoodsReceipt, StockMovement
from app.models.user import User, UserRole
from app.models.waste import WasteRecord, WasteItem

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


def get_user_permissions(db: Session, user: User) -> set[str]:
    role = getattr(user.role, "value", user.role)

    if role == UserRole.ADMIN.value:
        return {
            row[0]
            for row in db.query(Permission.permission_code).all()
        }

    if role == UserRole.KITCHEN_MANAGER.value:
        return set(KITCHEN_MANAGER_PERMISSIONS)

    if role == UserRole.STAFF.value:
        rows = (
            db.query(Permission.permission_code)
            .join(
                StaffAccessAssignment,
                StaffAccessAssignment.permission_id == Permission.id,
            )
            .filter(
                StaffAccessAssignment.staff_user_id == user.id,
                StaffAccessAssignment.is_active.is_(True),
            )
            .all()
        )
        return {row[0] for row in rows}

    return set()


def has_permission(permissions: set[str], code: str) -> bool:
    return code in permissions


def safe_count(query) -> int:
    return int(query.scalar() or 0)


@router.get("/overview")
def dashboard_overview(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("dashboard.read")),
):
    campus_id = user.campus_id
    today = date.today()
    week_start = today - timedelta(days=6)
    month_start = today.replace(day=1)

    permissions = get_user_permissions(db, user)

    can_headcount = has_permission(permissions, "headcount.read")
    can_inventory = has_permission(permissions, "inventory.read")
    can_purchases = has_permission(permissions, "purchase_order.read")
    can_menu = has_permission(permissions, "menu.read")
    can_waste = has_permission(permissions, "waste_tracking.read")
    can_audit = has_permission(permissions, "audit.read")

    result = {
        "campus_id": campus_id,
        "role": getattr(user.role, "value", user.role),
        "generated_at": datetime.now(timezone.utc),
        "permissions": sorted(permissions),
        "kpis": {},
    }

    # --------------------------------------------------
    # HEADCOUNT
    # --------------------------------------------------

    if can_headcount:
        today_headcount = (
            db.query(DailyHeadcount.student_count)
            .filter(
                DailyHeadcount.campus_id == campus_id,
                DailyHeadcount.headcount_date == today,
            )
            .scalar()
        )

        headcount_rows = (
            db.query(
                DailyHeadcount.headcount_date,
                DailyHeadcount.student_count,
            )
            .filter(
                DailyHeadcount.campus_id == campus_id,
                DailyHeadcount.headcount_date >= week_start,
                DailyHeadcount.headcount_date <= today,
            )
            .order_by(DailyHeadcount.headcount_date)
            .all()
        )

        result["headcount"] = {
            "today": today_headcount,
            "trend": [
                {"date": row.headcount_date, "count": row.student_count}
                for row in headcount_rows
            ],
        }

        result["kpis"]["headcount_today"] = today_headcount

    # --------------------------------------------------
    # INVENTORY
    # --------------------------------------------------

    if can_inventory:
        active_items = safe_count(
            db.query(func.count(Item.id)).filter(
                Item.campus_id == campus_id,
                Item.is_active.is_(True),
            )
        )

        active_suppliers = safe_count(
            db.query(func.count(Supplier.id)).filter(
                Supplier.campus_id == campus_id,
                Supplier.is_active.is_(True),
            )
        )

        movements = (
            db.query(StockMovement, Item.name, Unit.symbol)
            .join(
                Item,
                (Item.id == StockMovement.item_id)
                & (Item.campus_id == campus_id),
            )
            .join(
                Unit,
                (Unit.id == StockMovement.unit_id)
                & (Unit.campus_id == campus_id),
            )
            .filter(StockMovement.campus_id == campus_id)
            .order_by(StockMovement.created_at.desc())
            .limit(6)
            .all()
        )

        result["inventory"] = {
            "active_items": active_items,
            "active_suppliers": active_suppliers,
            "recent_movements": [
                {
                    "id": movement.id,
                    "item_name": item_name,
                    "movement_type": movement.movement_type,
                    "quantity": movement.quantity,
                    "unit": unit_symbol,
                    "created_at": movement.created_at,
                }
                for movement, item_name, unit_symbol in movements
            ],
        }

        result["kpis"]["inventory_items"] = active_items
        result["kpis"]["active_suppliers"] = active_suppliers

    # --------------------------------------------------
    # PURCHASES
    # --------------------------------------------------

    if can_purchases:
        purchase_query = db.query(Purchase).filter(
            Purchase.campus_id == campus_id
        )

        monthly_purchases = purchase_query.filter(
            Purchase.purchase_date >= month_start,
            Purchase.purchase_date <= today,
        )

        purchase_count = safe_count(
            db.query(func.count(Purchase.id)).filter(
                Purchase.campus_id == campus_id,
                Purchase.purchase_date >= month_start,
                Purchase.purchase_date <= today,
            )
        )

        monthly_total = (
            monthly_purchases.with_entities(
                func.coalesce(func.sum(Purchase.grand_total), 0)
            ).scalar()
            or 0
        )

        recent_purchases = (
            db.query(Purchase)
            .filter(Purchase.campus_id == campus_id)
            .order_by(
                Purchase.purchase_date.desc(),
                Purchase.id.desc(),
            )
            .limit(6)
            .all()
        )

        result["purchases"] = {
            "count_this_month": purchase_count,
            "total_this_month": monthly_total,
            "recent": [
                {
                    "id": purchase.id,
                    "invoice_number": purchase.invoice_number,
                    "purchase_date": purchase.purchase_date,
                    "grand_total": purchase.grand_total,
                    "status": purchase.status,
                }
                for purchase in recent_purchases
            ],
        }

        result["kpis"]["purchases_this_month"] = purchase_count
        result["kpis"]["purchase_spending_this_month"] = monthly_total

    # --------------------------------------------------
    # GOODS RECEIPTS
    # --------------------------------------------------

    if can_inventory:
        receipt_count = safe_count(
            db.query(func.count(GoodsReceipt.id)).filter(
                GoodsReceipt.campus_id == campus_id,
                GoodsReceipt.receipt_date >= month_start,
                GoodsReceipt.receipt_date <= today,
            )
        )

        recent_receipts = (
            db.query(GoodsReceipt)
            .filter(GoodsReceipt.campus_id == campus_id)
            .order_by(
                GoodsReceipt.receipt_date.desc(),
                GoodsReceipt.id.desc(),
            )
            .limit(6)
            .all()
        )

        result["receipts"] = {
            "count_this_month": receipt_count,
            "recent": [
                {
                    "id": receipt.id,
                    "purchase_id": receipt.purchase_id,
                    "receipt_date": receipt.receipt_date,
                    "status": receipt.status,
                }
                for receipt in recent_receipts
            ],
        }

        result["kpis"]["receipts_this_month"] = receipt_count

    # --------------------------------------------------
    # MENUS
    # --------------------------------------------------

    if can_menu:
        menus = (
            db.query(Menu, MealSession.name)
            .join(
                MealSession,
                (MealSession.id == Menu.meal_session_id)
                & (MealSession.campus_id == campus_id),
            )
            .filter(
                Menu.campus_id == campus_id,
                Menu.is_active.is_(True),
            )
            .order_by(Menu.id.desc())
            .limit(8)
            .all()
        )

        menu_count = safe_count(
            db.query(func.count(Menu.id)).filter(
                Menu.campus_id == campus_id,
                Menu.is_active.is_(True),
            )
        )

        result["menus"] = {
            "active_count": menu_count,
            "recent": [
                {
                    "id": menu.id,
                    "name": menu.name,
                    "meal_session": session_name,
                }
                for menu, session_name in menus
            ],
        }

        result["kpis"]["active_menus"] = menu_count

    # --------------------------------------------------
    # WASTE TRACKING
    # --------------------------------------------------

    if can_waste:
        waste_today_count = safe_count(
            db.query(func.count(WasteRecord.id)).filter(
                WasteRecord.campus_id == campus_id,
                WasteRecord.waste_date == today,
            )
        )

        waste_totals = (
            db.query(
                func.coalesce(func.sum(WasteItem.quantity), 0),
                func.coalesce(func.sum(WasteItem.estimated_cost), 0),
            )
            .join(
                WasteRecord,
                (WasteRecord.id == WasteItem.waste_record_id)
                & (WasteRecord.campus_id == campus_id),
            )
            .filter(
                WasteItem.campus_id == campus_id,
                WasteRecord.waste_date == today,
            )
            .first()
        )

        waste_trend_rows = (
            db.query(
                WasteRecord.waste_date,
                func.coalesce(func.sum(WasteItem.estimated_cost), 0),
            )
            .join(
                WasteItem,
                (WasteItem.waste_record_id == WasteRecord.id)
                & (WasteItem.campus_id == campus_id),
            )
            .filter(
                WasteRecord.campus_id == campus_id,
                WasteRecord.waste_date >= week_start,
                WasteRecord.waste_date <= today,
            )
            .group_by(WasteRecord.waste_date)
            .order_by(WasteRecord.waste_date)
            .all()
        )

        recent_waste = (
            db.query(WasteRecord)
            .filter(WasteRecord.campus_id == campus_id)
            .order_by(
                WasteRecord.waste_date.desc(),
                WasteRecord.id.desc(),
            )
            .limit(6)
            .all()
        )

        result["waste"] = {
            "records_today": waste_today_count,
            "quantity_today": waste_totals[0],
            "estimated_cost_today": waste_totals[1],
            "cost_trend": [
                {"date": row[0], "estimated_cost": row[1]}
                for row in waste_trend_rows
            ],
            "recent": [
                {
                    "id": record.id,
                    "waste_date": record.waste_date,
                    "notes": record.notes,
                }
                for record in recent_waste
            ],
        }

        result["kpis"]["waste_records_today"] = waste_today_count
        result["kpis"]["waste_cost_today"] = waste_totals[1]

    # --------------------------------------------------
    # RECENT AUDIT ACTIVITY
    # --------------------------------------------------

    if can_audit:
        activity_query = (
            db.query(AuditLog, User.full_name)
            .outerjoin(User, User.id == AuditLog.user_id)
            .filter(AuditLog.campus_id == campus_id)
        )

        # Kitchen Managers have no access to supplier bills. Bill audit
        # entries carry invoice numbers and totals, so they are left out
        # of the Kitchen Manager's activity feed.
        if result["role"] == UserRole.KITCHEN_MANAGER.value:
            activity_query = activity_query.filter(
                AuditLog.entity_type != "PURCHASE"
            )

        activity_rows = (
            activity_query
            .order_by(AuditLog.created_at.desc())
            .limit(10)
            .all()
        )

        result["activity"] = [
            {
                "id": log.id,
                "user_name": user_name or "System",
                "action": log.action,
                "entity_type": log.entity_type,
                "entity_id": log.entity_id,
                "details": log.details,
                "created_at": log.created_at,
            }
            for log, user_name in activity_rows
        ]

    return result
