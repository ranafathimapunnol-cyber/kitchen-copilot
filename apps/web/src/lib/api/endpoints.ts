export const ENDPOINTS = {
  login: "/api/auth/login",
  csrf: "/api/auth/csrf",
  refresh: "/api/auth/refresh",
  logout: "/api/auth/logout",
  me: "/api/auth/me",

  createUser: "/api/auth/users",

  passwordForgot: "/api/auth/password/forgot",
  passwordVerify: "/api/auth/password/verify",
  passwordSetup: "/api/auth/password/setup",
  passwordReset: "/api/auth/password/reset",

  authorizationMe: "/api/authorization/me",
  authorizationModules: "/api/authorization/modules",
  staff: "/api/authorization/staff",

  categories: "/api/master/categories",
  units: "/api/master/units",
  items: "/api/master/items",
  suppliers: "/api/master/suppliers",
  mealSessions: "/api/master/meal-sessions",
  menus: "/api/master/menus",
  unitConversions: "/api/master/unit-conversions",
  menuMainItems: "/api/master/menu-main-items",

  wasteRecords: "/api/waste/records",

  supplierPayments: "/api/supplier-payments",
  supplierBalances: "/api/supplier-balances",
  supplierBillBalances: "/api/supplier-balances/bills",

  supplierBills: "/api/purchases/",
  purchasesVsPaymentsReport: "/api/reports/purchases-vs-payments",
  purchasesVsPaymentsExport: "/api/reports/purchases-vs-payments/export",
} as const;

/** Attachments of one supplier bill (GET lists, POST uploads). */
export function billAttachmentsEndpoint(purchaseId: number): string {
  return `/api/purchases/${purchaseId}/attachments`;
}

/** One attached file, as a download or for viewing in the browser. */
export function billAttachmentFileEndpoint(
  purchaseId: number,
  attachmentId: number,
  inline = false,
): string {
  return `/api/purchases/${purchaseId}/attachments/${attachmentId}/file${inline ? "?disposition=inline" : ""}`;
}

export function duplicateCheckEndpoint(supplierId: string, invoiceNumber: string): string {
  return `/api/purchases/duplicate-check?supplier_id=${encodeURIComponent(supplierId)}&invoice_number=${encodeURIComponent(invoiceNumber)}`;
}

export const POSSIBLE_DUPLICATES_ENDPOINT = "/api/purchases/possible-duplicates";

/** Purchase orders (Stage 3). */
export const PURCHASE_ORDERS_ENDPOINT = "/api/purchase-orders";

export function purchaseOrderEndpoint(orderId: number | string): string {
  return `/api/purchase-orders/${orderId}`;
}

export function purchaseOrderActionEndpoint(
  orderId: number,
  action: "place" | "close" | "cancel",
): string {
  return `/api/purchase-orders/${orderId}/${action}`;
}

/** Placed orders of a supplier, for entering a bill against one. */
export function billableOrdersEndpoint(supplierId: string): string {
  return `/api/purchase-orders/billable?supplier_id=${encodeURIComponent(supplierId)}`;
}

/** Goods receipts (PUR03) and the stock movement log. */
export const RECEIPTS_ENDPOINT = "/api/receipts";
export const RECEIVABLE_BILLS_ENDPOINT = "/api/receipts/receivable-bills";
export const STOCK_MOVEMENTS_ENDPOINT = "/api/stock-movements";

/** Stock ledger (Stage 4, slice 4a). */
export const STOCK_BALANCES_ENDPOINT = "/api/stock/balances";
export const STOCK_REPLENISHMENT_ENDPOINT = "/api/stock/replenishment";
export const STOCK_OPENINGS_ENDPOINT = "/api/stock/openings";

export function itemLedgerEndpoint(itemId: number | string): string {
  return `/api/stock/items/${itemId}/ledger`;
}

export function reverseOpeningEndpoint(openingId: number): string {
  return `/api/stock/openings/${openingId}/reverse`;
}

/** Kitchen issues and unused returns (Stage 4, slice 4b). */
export const KITCHEN_ISSUES_ENDPOINT = "/api/kitchen-issues";
export const KITCHEN_ISSUE_OPTIONS_ENDPOINT = "/api/kitchen-issues/options";

export function kitchenIssueEndpoint(issueId: number | string): string {
  return `/api/kitchen-issues/${issueId}`;
}

export function kitchenIssueActionEndpoint(issueId: number, action: "confirm" | "cancel" | "reverse" | "returns"): string {
  return `/api/kitchen-issues/${issueId}/${action}`;
}

export function kitchenReturnActionEndpoint(returnId: number, action: "confirm" | "cancel" | "reverse"): string {
  return `/api/kitchen-returns/${returnId}/${action}`;
}

export function receiptEndpoint(receiptId: number | string): string {
  return `/api/receipts/${receiptId}`;
}

export function receiptAcceptEndpoint(receiptId: number): string {
  return `/api/receipts/${receiptId}/accept`;
}

export function receiptCancelEndpoint(receiptId: number): string {
  return `/api/receipts/${receiptId}/cancel`;
}

/** POST records a draft receipt against the bill. */
export function billReceiptsEndpoint(purchaseId: number): string {
  return `/api/purchases/${purchaseId}/receipts`;
}

export function billReceivingEndpoint(purchaseId: number): string {
  return `/api/purchases/${purchaseId}/receiving`;
}

export function duplicateReviewEndpoint(purchaseId: number): string {
  return `/api/purchases/${purchaseId}/duplicate-review`;
}

/** One supplier bill with its lines. */
export function supplierBillEndpoint(purchaseId: number): string {
  return `/api/purchases/${purchaseId}`;
}

/** Payments recorded against one supplier bill (GET lists, POST records). */
export function billPaymentsEndpoint(purchaseId: number): string {
  return `/api/purchases/${purchaseId}/payments`;
}

// Physical stock counts and adjustments (Stage 4, slice 4c).
export const STOCK_COUNTS_ENDPOINT = "/api/stock-counts";
export const STOCK_COUNT_OPTIONS_ENDPOINT = "/api/stock-counts/options";
export const STOCK_ADJUSTMENTS_ENDPOINT = "/api/stock-adjustments";

export function stockCountEndpoint(countId: number | string): string {
  return `/api/stock-counts/${countId}`;
}

export function stockCountAdjustmentEndpoint(countId: number, lineId: number): string {
  return `/api/stock-counts/${countId}/lines/${lineId}/adjustment`;
}

export function stockAdjustmentEndpoint(adjustmentId: number | string): string {
  return `/api/stock-adjustments/${adjustmentId}`;
}

export function stockAdjustmentActionEndpoint(adjustmentId: number, action: "approve" | "reject"): string {
  return `/api/stock-adjustments/${adjustmentId}/${action}`;
}

// Meal records (Stage 5).
export const MEAL_RECORDS_ENDPOINT = "/api/meal-records";
export const MEAL_OPTIONS_ENDPOINT = "/api/meal-records/options";
export const MEAL_RETAINED_ENDPOINT = "/api/meal-records/retained";

export function mealRecordEndpoint(recordId: number | string): string {
  return `/api/meal-records/${recordId}`;
}

export function mealActionEndpoint(recordId: number, action: "close" | "cancel" | "reopen" | "history" | "carry" | "dishes"): string {
  return `/api/meal-records/${recordId}/${action}`;
}

export function mealDishEndpoint(recordId: number, dishId: number, part?: "distribution" | "remarks"): string {
  return `/api/meal-records/${recordId}/dishes/${dishId}${part ? `/${part}` : ""}`;
}

// Meal planning (Stage 6).
export const PORTION_STANDARDS_ENDPOINT = "/api/portion-standards";
export const PORTION_STANDARD_OPTIONS_ENDPOINT = "/api/portion-standards/options";
export const PORTION_STANDARD_COPY_ENDPOINT = "/api/portion-standards/copy-from-menu";
export const PORTION_STANDARD_SUGGESTION_RECORDS_ENDPOINT = "/api/portion-standards/suggestion/records";
export const PORTION_STANDARD_SUGGESTION_PREVIEW_ENDPOINT = "/api/portion-standards/suggestion/preview";
export const PORTION_STANDARD_SUGGESTION_ENDPOINT = "/api/portion-standards/suggestion";
export const MEAL_PLANS_ENDPOINT = "/api/meal-plans";
export const MEAL_PLAN_OPTIONS_ENDPOINT = "/api/meal-plans/options";
export const MEAL_PLAN_PREFILL_ENDPOINT = "/api/meal-plans/prefill";

export function portionStandardEndpoint(standardId: number | string): string {
  return `/api/portion-standards/${standardId}`;
}

export function portionStandardActionEndpoint(standardId: number, action: "approve" | "cancel"): string {
  return `/api/portion-standards/${standardId}/${action}`;
}

export function mealPlanEndpoint(planId: number | string): string {
  return `/api/meal-plans/${planId}`;
}

export function mealPlanActionEndpoint(planId: number, action: "approve" | "cancel" | "comparison"): string {
  return `/api/meal-plans/${planId}/${action}`;
}

/** Item classification (raw, prepared, outsourced): ADMIN and KITCHEN_MANAGER only. */
export function itemKindEndpoint(itemId: number | string): string {
  return `/api/items/${itemId}/kind`;
}

// Outsourced food (Stage 8a): orders by ADMIN and KITCHEN_MANAGER; deliveries
// through outsourced_food.create/update; costs only with purchase_bill.read.
export const OUTSOURCED_ORDERS_ENDPOINT = "/api/outsourced-orders";
export const OUTSOURCED_OPTIONS_ENDPOINT = "/api/outsourced-orders/options";
export const OUTSOURCED_REPORT_ENDPOINT = "/api/outsourced-food/report";
export const OUTSOURCED_REPORT_EXPORT_ENDPOINT = "/api/outsourced-food/report/export";

export function outsourcedOrderEndpoint(orderId: number | string): string {
  return `/api/outsourced-orders/${orderId}`;
}

export function outsourcedOrderActionEndpoint(
  orderId: number,
  action: "place" | "cancel" | "history" | "deliveries"
): string {
  return `/api/outsourced-orders/${orderId}/${action}`;
}

export function outsourcedDeliveryEndpoint(deliveryId: number): string {
  return `/api/outsourced-deliveries/${deliveryId}`;
}

export function outsourcedDeliveryActionEndpoint(deliveryId: number, action: "confirm" | "cancel"): string {
  return `/api/outsourced-deliveries/${deliveryId}/${action}`;
}

export function outsourcedLineBillEndpoint(lineId: number, what: "bill-line" | "bill-candidates"): string {
  return `/api/outsourced-order-lines/${lineId}/${what}`;
}

export function billOutsourcedLinksEndpoint(purchaseId: number): string {
  return `/api/purchases/${purchaseId}/outsourced-links`;
}

// Stage 9: spending analysis (DASH01–DASH05) and the report catalogue (§5.8).
export const DASHBOARD_OVERVIEW_ENDPOINT = "/api/dashboard/overview";
export const ANALYTICS_OPTIONS_ENDPOINT = "/api/analytics/options";
export const ANALYTICS_SPENDING_ENDPOINT = "/api/analytics/spending";
export const ANALYTICS_TRANSACTIONS_ENDPOINT = "/api/analytics/transactions";
export const REPORT_CATALOG_ENDPOINT = "/api/reports/catalog";
export const REPORT_LOOKUPS_ENDPOINT = "/api/reports/lookups";

export function reportEndpoint(key: string): string {
  return `/api/reports/${key}`;
}

export function reportExportEndpoint(key: string): string {
  return `/api/reports/${key}/export`;
}

// Stage 10: user accounts (ADMIN), audit viewer (audit.read), sign out everywhere.
export const ADMIN_USERS_ENDPOINT = "/api/admin/users";
export const AUDIT_ENDPOINT = "/api/audit";
export const AUDIT_OPTIONS_ENDPOINT = "/api/audit/options";
export const LOGOUT_ALL_ENDPOINT = "/api/auth/logout-all";

// Stage 11: platform management (SUPER_ADMIN).
export const PLATFORM_ENDPOINT = "/api/platform";

// Stage 12: Kitchen Copilot.
export const AGENT_ENDPOINT = "/api/agent";
