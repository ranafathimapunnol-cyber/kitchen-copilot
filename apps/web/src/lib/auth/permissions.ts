const PATH_PERMISSIONS: Record<string, string> = {
  "/dashboard/categories": "inventory.read",
  "/dashboard/units": "inventory.read",
  "/dashboard/unit-conversions": "inventory.read",
  "/dashboard/items": "inventory.read",
  "/dashboard/suppliers": "inventory.read",

  "/dashboard/meal-sessions": "menu.read",
  "/dashboard/menus": "menu.read",
  "/dashboard/menu-main-items": "menu.read",

  "/dashboard/waste-tracking": "waste_tracking.read",

  // Supplier payments and balances follow the supplier-bill permission
  // (purchase_bill.*, split from purchase_order.* on 18 November 2026),
  // the same check the API applies. ADMIN and KITCHEN_MANAGER hold it;
  // STAFF only through an explicit assignment. Recording a payment also
  // needs purchase_bill.create, checked on the page and by the API.
  "/dashboard/supplier-payments": "purchase_bill.read",
  "/dashboard/supplier-balances": "purchase_bill.read",

  // Supplier bills follow the same codes the bill API checks. The entry
  // page must come before the list: the first matching prefix wins.
  "/dashboard/supplier-bills/new": "purchase_bill.create",
  "/dashboard/supplier-bills": "purchase_bill.read",
  "/dashboard/purchase-payment-report": "purchase_bill.read",

  // Genuine purchase orders (Stage 3). Editing, placing, closing and
  // cancelling (purchase_order.update) are checked on the page and by the API.
  "/dashboard/purchase-orders/new": "purchase_order.create",
  "/dashboard/purchase-orders": "purchase_order.read",

  // Goods receipts and the stock log use the codes the receipts API checks.
  // Correcting, accepting and cancelling (inventory.update) are checked on
  // the receipt page and by the API.
  "/dashboard/receipts/new": "inventory.create",
  "/dashboard/receipts": "inventory.read",
  "/dashboard/stock-movements": "inventory.read",

  // Stock ledger (Stage 4): balances, replenishment list and item ledgers.
  "/dashboard/stock": "inventory.read",

  // Kitchen issues and unused returns (slice 4b). Editing, cancelling and
  // confirming (consumption.update) and reversing (ADMIN and KITCHEN_MANAGER)
  // are checked on the page and by the API.
  "/dashboard/kitchen-issues/new": "consumption.create",
  "/dashboard/kitchen-issues": "consumption.read",

  // Physical stock counts and adjustments (slice 4c, decision S1). Raising an
  // adjustment needs stock_count.create; approving and rejecting are ADMIN
  // and KITCHEN_MANAGER who did not count, checked on the page and by the API.
  "/dashboard/stock-counts/new": "stock_count.create",
  "/dashboard/stock-counts": "stock_count.read",
  "/dashboard/stock-adjustments": "stock_count.read",

  // Meal records (Stage 5, decision 5-1). Editing, closing and cancelling
  // (meal.update) and reopening (ADMIN and KITCHEN_MANAGER) are checked on
  // the page and by the API.
  "/dashboard/meals/new": "meal.create",
  "/dashboard/meals": "meal.read",

  // Outsourced food (Stage 8a, P8-3 option b): viewing, the report and
  // recording deliveries follow outsourced_food.*; creating orders is
  // ADMIN and KITCHEN_MANAGER only (ROLE_PATHS below). Editing, placing and
  // cancelling orders, confirming and cancelling deliveries and linking bill
  // lines are checked on the page and by the API.
  "/dashboard/outsourced-food": "outsourced_food.read",

  // Stage 9: spending analysis needs supplier-bill access (amounts); the
  // report catalogue needs the dashboard code, and each report checks its
  // own module permission in the API.
  "/dashboard/analytics": "purchase_bill.read",
  "/dashboard/reports": "dashboard.read",

  // Stage 10: the audit viewer (ADMIN and KITCHEN_MANAGER hold audit.read;
  // it is never STAFF-assignable).
  "/dashboard/audit": "audit.read",
};

// Pages decided by role, not by an assignable code. Opening stock is
// ADMIN and KITCHEN_MANAGER work (decision S3); the API checks the same.
const ROLE_PATHS: Record<string, string[]> = {
  "/dashboard/opening-stock": ["ADMIN", "KITCHEN_MANAGER"],
  // Meal planning (Stage 6, decisions 6-3 to 6-5): ADMIN and KITCHEN_MANAGER
  // only. The planning codes (portion_standard.*, meal_plan.*) are not
  // STAFF-assignable, and the API refuses STAFF whatever grants exist.
  "/dashboard/portion-standards": ["ADMIN", "KITCHEN_MANAGER"],
  "/dashboard/meal-plans": ["ADMIN", "KITCHEN_MANAGER"],
  // Outsourced orders are created by ADMIN and KITCHEN_MANAGER only, whatever
  // outsourced_food.* grants STAFF hold (Stage 8a, P8-3 option b).
  "/dashboard/outsourced-food/new": ["ADMIN", "KITCHEN_MANAGER"],
  // Stage 10: campus user accounts are managed by the campus ADMIN only.
  "/dashboard/users": ["ADMIN"],
  // Stage 12: Kitchen Copilot for every campus user; each job checks its own
  // permissions in the API.
  "/dashboard/copilot": ["ADMIN", "KITCHEN_MANAGER", "STAFF"],
  // Everyone signed in manages their own sessions.
  "/dashboard/account": ["SUPER_ADMIN", "ADMIN", "KITCHEN_MANAGER", "STAFF"],
};

/** Where each role lands; SUPER_ADMIN has no campus dashboard (Stage 11). */
export function homePath(role: string): string {
  return role === "SUPER_ADMIN" ? "/dashboard/platform" : "/dashboard";
}

export function canAccessPath(
  role: string,
  pathname: string,
  permissions: string[]
): boolean {
  // SUPER_ADMIN manages organisations and campuses only (Stage 11).
  if (role === "SUPER_ADMIN") {
    return (
      pathname === "/dashboard/platform" ||
      pathname.startsWith("/dashboard/platform/") ||
      pathname === "/dashboard/account"
    );
  }
  if (pathname === "/dashboard/platform" || pathname.startsWith("/dashboard/platform/")) {
    return false;
  }

  if (pathname === "/dashboard") {
    return true;
  }

  if (
    pathname === "/dashboard/staff" ||
    pathname.startsWith("/dashboard/staff/")
  ) {
    return role === "ADMIN";
  }

  const rolePath = Object.keys(ROLE_PATHS).find(
    (path) => pathname === path || pathname.startsWith(`${path}/`)
  );

  if (rolePath) {
    return ROLE_PATHS[rolePath].includes(role);
  }

  if (role === "ADMIN") {
    return true;
  }

  const matchingPath = Object.keys(PATH_PERMISSIONS).find(
    (path) =>
      pathname === path || pathname.startsWith(`${path}/`)
  );

  if (!matchingPath) {
    return false;
  }

  return permissions.includes(PATH_PERMISSIONS[matchingPath]);
}
