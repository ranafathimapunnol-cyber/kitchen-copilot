from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import (
    KITCHEN_MANAGER_PERMISSIONS,
    STAFF_EXCLUDED_PERMISSIONS,
    require_permission,
)
from app.api.routes.supplier_payments import (
    balance_totals,
    bill_balance,
    bill_paid_subquery,
    money_text,
    serialize_supplier_balance,
    supplier_balance_subquery,
)
from app.core.clock import campus_today
from app.db.session import get_db
from app.models import Campus
from app.models.authorization import Permission, StaffAccessAssignment
from app.models.audit_log import AuditLog
from app.services import dashboard_sections as sections
from app.models.master_data import Item, Menu, MealSession, Supplier, Unit
from app.models.purchases import (
    GoodsReceipt,
    Purchase,
    StockMovement,
    SupplierPayment,
)
from app.models.user import User, UserRole
from app.models.waste import WasteRecord, WasteItem

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

# Money in the overview is returned as decimal strings with two places,
# matching the supplier payment endpoints.


def get_user_permissions(db: Session, user: User) -> set[str]:
    role = getattr(user.role, "value", user.role)

    if role == UserRole.SUPER_ADMIN.value:
        return set()

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
        # Purchase-order codes never apply to STAFF (kept rows grant nothing).
        return {row[0] for row in rows} - STAFF_EXCLUDED_PERMISSIONS

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
    # Campus-local date: the server clock is UTC in the Docker image.
    today = campus_today()
    week_start = today - timedelta(days=6)
    month_start = today.replace(day=1)

    permissions = get_user_permissions(db, user)

    can_headcount = has_permission(permissions, "headcount.read")
    can_inventory = has_permission(permissions, "inventory.read")
    can_purchases = has_permission(permissions, "purchase_bill.read")
    can_orders = has_permission(permissions, "purchase_order.read")
    can_menu = has_permission(permissions, "menu.read")
    can_waste = has_permission(permissions, "waste_tracking.read")
    can_audit = has_permission(permissions, "audit.read")

    role = getattr(user.role, "value", user.role)

    result = {
        "campus_id": campus_id,
        "campus_name": db.query(Campus.name)
        .filter(Campus.id == campus_id)
        .scalar(),
        "role": role,
        "generated_at": datetime.now(timezone.utc),
        "permissions": sorted(permissions),
        "kpis": {},
    }

    # --------------------------------------------------
    # HEADCOUNT (Stage 9: from meal records, the single source of
    # headcounts; daily_headcounts is no longer read)
    # --------------------------------------------------

    if can_headcount or has_permission(permissions, "meal.read"):
        result["headcount"] = sections.headcount(db, campus_id, today)
        result["kpis"]["headcount_today"] = result["headcount"]["today"]

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
                    "direction": movement.direction,
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

        monthly_total = money_text(
            monthly_purchases.with_entities(
                func.coalesce(func.sum(Purchase.grand_total), 0)
            ).scalar()
        )

        paid_by_bill = bill_paid_subquery(db, campus_id)

        recent_purchases = (
            db.query(
                Purchase,
                func.coalesce(paid_by_bill.c.paid, 0),
                Supplier.name,
            )
            .outerjoin(
                paid_by_bill, paid_by_bill.c.purchase_id == Purchase.id
            )
            .outerjoin(
                Supplier,
                (Supplier.id == Purchase.supplier_id)
                & (Supplier.campus_id == campus_id),
            )
            .filter(Purchase.campus_id == campus_id)
            .order_by(
                Purchase.purchase_date.desc(),
                Purchase.id.desc(),
            )
            .limit(6)
            .all()
        )

        recent_rows = []
        for purchase, paid, supplier_name in recent_purchases:
            balance = bill_balance(purchase, paid, supplier_name)
            recent_rows.append({
                "id": purchase.id,
                "invoice_number": purchase.invoice_number,
                "supplier_name": supplier_name,
                "purchase_date": purchase.purchase_date,
                "grand_total": balance["grand_total"],
                "paid_total": balance["paid_total"],
                "outstanding": balance["outstanding"],
                "payment_status": balance["payment_status"],
                "status": purchase.status,
            })

        result["purchases"] = {
            "count_this_month": purchase_count,
            "total_this_month": monthly_total,
            "recent": recent_rows,
        }

        result["kpis"]["purchases_this_month"] = purchase_count
        result["kpis"]["purchase_spending_this_month"] = monthly_total

        # ----------------------------------------------
        # SUPPLIER PAYMENTS AND BALANCES (PUR04)
        # Same permission as supplier bills.
        # ----------------------------------------------

        balances = supplier_balance_subquery(db, campus_id)
        totals = balance_totals(db, balances)

        top_suppliers = (
            db.query(balances, Supplier.name)
            .outerjoin(
                Supplier,
                (Supplier.id == balances.c.supplier_id)
                & (Supplier.campus_id == campus_id),
            )
            .filter(balances.c.outstanding > 0)
            .order_by(balances.c.outstanding.desc(), Supplier.name)
            .limit(5)
            .all()
        )

        suppliers_owed = safe_count(
            db.query(func.count()).select_from(balances).filter(
                balances.c.outstanding > 0
            )
        )

        monthly_payments = db.query(SupplierPayment).filter(
            SupplierPayment.campus_id == campus_id,
            SupplierPayment.payment_date >= month_start,
            SupplierPayment.payment_date <= today,
        )

        paid_this_month = money_text(
            monthly_payments.with_entities(
                func.coalesce(func.sum(SupplierPayment.amount), 0)
            ).scalar()
        )

        recent_payments = (
            db.query(SupplierPayment, Purchase.invoice_number, Supplier.name)
            .join(
                Purchase,
                (Purchase.id == SupplierPayment.purchase_id)
                & (Purchase.campus_id == campus_id),
            )
            .outerjoin(
                Supplier,
                (Supplier.id == Purchase.supplier_id)
                & (Supplier.campus_id == campus_id),
            )
            .filter(SupplierPayment.campus_id == campus_id)
            .order_by(
                SupplierPayment.payment_date.desc(),
                SupplierPayment.id.desc(),
            )
            .limit(6)
            .all()
        )

        result["payments"] = {
            "paid_this_month": paid_this_month,
            "count_this_month": safe_count(
                monthly_payments.with_entities(func.count(SupplierPayment.id))
            ),
            "total_billed": totals["total_billed"],
            "total_paid": totals["total_paid"],
            "outstanding": totals["outstanding"],
            "overpaid": totals["overpaid"],
            "open_bill_count": totals["open_bill_count"],
            "suppliers_owed": suppliers_owed,
            "top_outstanding": [
                serialize_supplier_balance(row, row.name)
                for row in top_suppliers
            ],
            "recent": [
                {
                    "id": payment.id,
                    "purchase_id": payment.purchase_id,
                    "invoice_number": invoice_number,
                    "supplier_name": supplier_name,
                    "payment_date": payment.payment_date,
                    "amount": money_text(payment.amount),
                    "payment_method": payment.payment_method,
                }
                for payment, invoice_number, supplier_name in recent_payments
            ],
        }

        result["kpis"]["outstanding_payables"] = totals["outstanding"]
        result["kpis"]["supplier_payments_this_month"] = paid_this_month

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

        # Quantities are recorded in different units (kg, litres,
        # pieces), so they are counted as lines, never summed.
        waste_totals = (
            db.query(
                func.count(WasteItem.id),
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

        waste_cost_today = money_text(waste_totals[1])

        result["waste"] = {
            "records_today": waste_today_count,
            "items_today": int(waste_totals[0] or 0),
            "estimated_cost_today": waste_cost_today,
            "cost_trend": [
                {"date": row[0], "estimated_cost": money_text(row[1])}
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
        result["kpis"]["waste_cost_today"] = waste_cost_today

    # --------------------------------------------------
    # STAGE 9 SECTIONS: stock, meals, planning, outsourced food,
    # kitchen issues, counts and spending (each with its own permission)
    # --------------------------------------------------

    if can_inventory:
        result["stock"] = sections.stock(db, campus_id)
        result["kpis"]["below_minimum"] = result["stock"]["below_minimum"]
    if has_permission(permissions, "meal.read"):
        result["meals"] = sections.meals(db, campus_id, today)
    if role in (UserRole.ADMIN.value, UserRole.KITCHEN_MANAGER.value) and has_permission(permissions, "meal_plan.read"):
        result["planning"] = sections.planning(db, campus_id, today)
    if has_permission(permissions, "outsourced_food.read"):
        result["outsourced"] = sections.outsourced(db, campus_id, today, can_purchases)
    if has_permission(permissions, "consumption.read"):
        result["kitchen"] = sections.kitchen(db, campus_id, today)
    if has_permission(permissions, "stock_count.read"):
        result["counts"] = sections.counts(db, campus_id)
    if can_purchases:
        result["spending"] = sections.spending(db, campus_id, today)

    # --------------------------------------------------
    # TEAM AND ACCESS (ADMIN only: users and permissions
    # are managed by ADMIN alone)
    # --------------------------------------------------

    if role == UserRole.ADMIN.value:
        role_counts = dict(
            db.query(User.role, func.count(User.id))
            .filter(User.campus_id == campus_id, User.is_active.is_(True))
            .group_by(User.role)
            .all()
        )

        def active_count(member_role: UserRole) -> int:
            return int(
                role_counts.get(member_role)
                or role_counts.get(member_role.value)
                or 0
            )

        inactive_users = safe_count(
            db.query(func.count(User.id)).filter(
                User.campus_id == campus_id,
                User.is_active.is_(False),
            )
        )

        staff_with_access = select(StaffAccessAssignment.staff_user_id).where(
            StaffAccessAssignment.is_active.is_(True)
        )

        staff_without_access = safe_count(
            db.query(func.count(User.id)).filter(
                User.campus_id == campus_id,
                User.is_active.is_(True),
                User.role == UserRole.STAFF,
                User.id.notin_(staff_with_access),
            )
        )

        result["team"] = {
            "active_admins": active_count(UserRole.ADMIN),
            "active_kitchen_managers": active_count(UserRole.KITCHEN_MANAGER),
            "active_staff": active_count(UserRole.STAFF),
            "inactive_users": inactive_users,
            "staff_without_access": staff_without_access,
        }

        result["kpis"]["active_users"] = sum(
            active_count(member_role) for member_role in UserRole
        )

    # --------------------------------------------------
    # RECENT AUDIT ACTIVITY
    # --------------------------------------------------

    if can_audit:
        activity_query = (
            db.query(AuditLog, User.full_name)
            .outerjoin(User, User.id == AuditLog.user_id)
            .filter(AuditLog.campus_id == campus_id)
        )

        # Bill, payment and report-export entries carry invoice numbers or
        # amounts, so they appear only to users who may read supplier bills.
        if not can_purchases:
            activity_query = activity_query.filter(
                AuditLog.entity_type.notin_(
                    ("PURCHASE", "SUPPLIER_PAYMENT", "PURCHASE_REPORT",
                     "PURCHASE_ATTACHMENT")
                )
            )
        # Purchase-order entries appear only to users who may read orders.
        if not can_orders:
            activity_query = activity_query.filter(
                AuditLog.entity_type != "PURCHASE_ORDER"
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
                "details": (
                    log.details if can_orders else {
                        key: value for key, value in (log.details or {}).items()
                        if key not in ("purchase_order_id", "purchase_order_number")
                    }
                ),
                "created_at": log.created_at,
            }
            for log, user_name in activity_rows
        ]

    return result
