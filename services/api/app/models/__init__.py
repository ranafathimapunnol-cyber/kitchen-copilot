from app.models.audit_log import AuditLog
from app.models.authorization import (
    Module,
    Permission,
    StaffAccessAssignment,
)
from app.models.campus import Campus
from app.models.master_data import (
    Category,
    Item,
    MealSession,
    Menu,
    MenuMainItem,
    Supplier,
    Unit,
    UnitConversion,
)
from app.models.user import User, UserRole

__all__ = [
    "Campus", "User", "UserRole", "AuditLog",
    "Category", "Unit", "UnitConversion", "Item",
    "Supplier", "MealSession", "Menu", "MenuMainItem","Module",
"Permission",
"StaffAccessAssignment",
]

from app.models.purchases import (
    Purchase,
    PurchaseAttachment,
    PurchaseItem,
    PurchaseOrder,
    PurchaseOrderItem,
    GoodsReceipt,
    GoodsReceiptItem,
    StockMovement,
    SupplierPayment,
    SupplierReturn,
    SupplierReturnItem,
)

__all__ += [
    "Purchase",
    "PurchaseAttachment",
    "PurchaseItem",
    "PurchaseOrder",
    "PurchaseOrderItem",
    "GoodsReceipt",
    "GoodsReceiptItem",
    "StockMovement",
    "SupplierPayment",
    "SupplierReturn",
    "SupplierReturnItem",
]

from app.models.daily_headcount import DailyHeadcount
__all__ += ["DailyHeadcount"]
from app.models.authorization import (
    Module,
    Permission,
    StaffAccessAssignment,
)

__all__ += [
    "Module",
    "Permission",
    "StaffAccessAssignment",
]
from app.models.waste import WasteRecord, WasteItem

__all__ += [
    "WasteRecord",
    "WasteItem",
]

from app.models.stock import (
    KitchenIssue,
    KitchenIssueItem,
    KitchenReturn,
    KitchenReturnItem,
    StockAdjustment,
    StockCount,
    StockCountItem,
    StockOpening,
)

__all__ += [
    "StockOpening",
    "KitchenIssue",
    "KitchenIssueItem",
    "KitchenReturn",
    "KitchenReturnItem",
    "StockCount",
    "StockCountItem",
    "StockAdjustment",
]

from app.models.meals import MealDish, MealLeftover, MealRecord

__all__ += [
    "MealRecord",
    "MealDish",
    "MealLeftover",
]

# The stock ledger is append-only (decision 4b-5): registers the database
# triggers for new schemas and the application guard on every session.
import app.models.ledger_guard  # noqa: E402,F401

from app.models.planning import MealPlan, MealPlanLine, PortionStandard, PortionStandardBasis

__all__ += [
    "PortionStandard",
    "PortionStandardBasis",
    "MealPlan",
    "MealPlanLine",
]

from app.models.outsourced import (  # noqa: E402
    OutsourcedDelivery,
    OutsourcedDeliveryLine,
    OutsourcedOrder,
    OutsourcedOrderLine,
)

__all__ += [
    "OutsourcedOrder",
    "OutsourcedOrderLine",
    "OutsourcedDelivery",
    "OutsourcedDeliveryLine",
]

from app.models.security import LoginAttempt  # noqa: E402

__all__ += ["LoginAttempt"]

from app.models.agent import AgentConversation, AgentMessage, AgentProposal, AgentStep  # noqa: E402

__all__ += ["AgentConversation", "AgentMessage", "AgentStep", "AgentProposal"]
