/**
 * Outsourced food (Stage 8a: OUT01, OUT02, OUT03 criterion 1, AT04): API
 * shapes, labels and who may do what (docs/STAGE-8-IMPLEMENTATION-PLAN.md,
 * P8-3 option b). The API re-checks every rule.
 *
 * - Orders (create, edit, place, cancel): ADMIN and KITCHEN_MANAGER only,
 *   whatever codes STAFF hold.
 * - outsourced_food.create — record a delivery; outsourced_food.update — edit,
 *   confirm or cancel a draft delivery; outsourced_food.read — view.
 * - Cancelling a confirmed delivery: ADMIN and KITCHEN_MANAGER.
 * - Rates, totals, bill links and costs: only with purchase_bill.read (the API
 *   leaves those fields out otherwise); linking bill lines: purchase_bill.update.
 *
 * Interim (not client decisions): rejected food is recorded with no credit
 * (client question Q6); meal sessions are matched exactly (C5); units are
 * explicit (Q7).
 */

import type { Page } from "@/lib/payments";

export type OutsourcedStatus = "DRAFT" | "ORDERED" | "CANCELLED";
export type DeliveryStatus = "DRAFT" | "CONFIRMED" | "CANCELLED";
export type ReceivingStatus = "NOT_RECEIVED" | "PARTLY_RECEIVED" | "RECEIVED";
export type MealLinkState = "ADDED" | "PENDING_NO_RECORD" | "PENDING_CLOSED" | "NOT_CONFIRMED" | "NOTHING_ACCEPTED";

export const ORDER_STATUSES: OutsourcedStatus[] = ["DRAFT", "ORDERED", "CANCELLED"];
export const ORDER_STATUS_LABELS: Record<OutsourcedStatus, string> = {
  DRAFT: "Draft",
  ORDERED: "Ordered",
  CANCELLED: "Cancelled",
};
export const DELIVERY_STATUS_LABELS: Record<DeliveryStatus, string> = {
  DRAFT: "Draft",
  CONFIRMED: "Confirmed",
  CANCELLED: "Cancelled",
};
export const RECEIVING_LABELS: Record<ReceivingStatus, string> = {
  NOT_RECEIVED: "Not received",
  PARTLY_RECEIVED: "Partly received",
  RECEIVED: "Fully received",
};
export const MEAL_LINK_LABELS: Record<MealLinkState, string> = {
  ADDED: "On the meal record",
  PENDING_NO_RECORD: "Waiting for meal record",
  PENDING_CLOSED: "Reconciliation pending",
  NOT_CONFIRMED: "Not confirmed",
  NOTHING_ACCEPTED: "Nothing accepted",
};
export const REPORT_STATUS_LABELS: Record<string, string> = {
  RECONCILED: "Reconciled",
  PENDING_MEAL_RECORD: "Waiting for meal record",
  DISTRIBUTION_NOT_RECORDED: "Distribution not recorded",
  LEFTOVERS_NOT_CLASSIFIED: "Leftovers not classified",
  NOT_DELIVERED: "Not delivered",
  ALL_REJECTED: "All rejected",
};
export const HISTORY_LABELS: Record<string, string> = {
  CREATE: "Recorded",
  UPDATE: "Edited",
  PLACE: "Ordered from supplier",
  CANCEL: "Cancelled",
  CONFIRM: "Confirmed",
  ADDED_TO_MEAL_RECORD: "Added to meal record",
  LINK_BILL: "Bill line linked",
  UNLINK_BILL: "Bill line unlinked",
};

/** Shown wherever rejected quantities appear (client question Q6). */
export const Q6_NOTE = "Credit not recorded because client question Q6 (supplier credits and rejected deliveries) remains unresolved.";

export type MealRecordRef = { id: number; status: string; meal_date: string; meal_session_name: string | null };

export type BillLineLink = {
  purchase_item_id: number;
  purchase_id: number;
  invoice_number: string;
  purchase_date: string;
  quantity: string;
  unit_id: number;
  unit_rate: string;
  line_total: string;
};

export type OutsourcedOrderLine = {
  id: number;
  item_id: number;
  item_name: string | null;
  unit_id: number;
  unit_symbol: string | null;
  ordered_quantity: string;
  received_quantity: string;
  rejected_quantity: string;
  accepted_quantity: string;
  in_draft_quantity: string;
  remaining_quantity: string;
  remarks: string | null;
  /** Only with purchase_bill.read. */
  unit_rate?: string;
  line_total?: string;
  bill_line?: BillLineLink | null;
};

export type MealLink = {
  state: MealLinkState;
  message: string;
  meal_record?: MealRecordRef | null;
  dish_id?: number;
};

export type DeliveryLine = {
  id: number;
  order_line_id: number;
  item_name: string | null;
  unit_symbol: string | null;
  received_quantity: string;
  rejected_quantity: string;
  accepted_quantity: string;
  rejection_reason: string | null;
  remarks: string | null;
  meal_link: MealLink | null;
};

export type OutsourcedDelivery = {
  id: number;
  delivery_number: string;
  delivery_date: string;
  status: DeliveryStatus;
  remarks: string | null;
  created_by_name: string | null;
  created_at: string;
  updated_at: string | null;
  confirmed_by_name: string | null;
  confirmed_at: string | null;
  cancelled_by_name: string | null;
  cancelled_at: string | null;
  cancellation_reason: string | null;
  lines: DeliveryLine[];
};

export type OutsourcedOrderDetail = {
  id: number;
  order_number: string;
  order_date: string;
  meal_date: string;
  meal_session_id: number;
  meal_session_name: string | null;
  supplier_id: number;
  supplier_name: string | null;
  status: OutsourcedStatus;
  notes: string | null;
  receiving_status: ReceivingStatus | null;
  created_by_name: string | null;
  created_at: string;
  updated_at: string | null;
  ordered_by_name: string | null;
  ordered_at: string | null;
  cancelled_by_name: string | null;
  cancelled_at: string | null;
  cancellation_reason: string | null;
  lines: OutsourcedOrderLine[];
  deliveries: OutsourcedDelivery[];
  meal_record: MealRecordRef | null;
  meal_link_state: "ADDED" | "PENDING_NO_RECORD" | "PENDING_CLOSED" | null;
  session_warnings: string[];
  rejection_note: string | null;
  costs_visible: boolean;
  planned_total?: string;
  billed_total?: string;
  permissions: {
    can_edit: boolean;
    can_place: boolean;
    can_cancel: boolean;
    can_record_delivery: boolean;
    can_update_delivery: boolean;
    can_cancel_confirmed_delivery: boolean;
    can_link_bill: boolean;
  };
};

export type OutsourcedOrderSummary = {
  id: number;
  order_number: string;
  order_date: string;
  meal_date: string;
  meal_session_name: string | null;
  supplier_name: string | null;
  status: OutsourcedStatus;
  receiving_status: ReceivingStatus | null;
  item_names: (string | null)[];
  line_count: number;
  delivery_count: number;
  planned_total?: string;
};

export type OutsourcedListResponse = Page<OutsourcedOrderSummary> & {
  status_counts: Record<OutsourcedStatus, number>;
  costs_visible: boolean;
};

export type OutsourcedOptions = {
  today: string;
  latest_meal_date: string;
  meal_sessions: { id: number; name: string; is_active: boolean }[];
  suppliers: { id: number; name: string; is_active: boolean }[];
  items: { id: number; name: string; is_active: boolean; standard_unit_id: number; standard_unit_symbol: string | null }[];
  units: { id: number; name: string; symbol: string }[];
  can_manage_orders: boolean;
  costs_visible: boolean;
};

export type BillCandidate = {
  purchase_item_id: number;
  purchase_id: number;
  invoice_number: string;
  purchase_date: string;
  quantity: string;
  unit_id: number;
  unit_symbol: string | null;
  unit_rate: string;
  line_total: string;
  same_unit: boolean;
  linked_here: boolean;
};

export type OutsourcedHistoryEntry = {
  id: number;
  action: string;
  entity: "order" | "delivery";
  delivery_number: string | null;
  user_name: string | null;
  created_at: string;
  details: Record<string, unknown> | null;
};

type QuantityKeys =
  | "ordered_quantity" | "received_quantity" | "rejected_quantity" | "accepted_quantity" | "added_quantity"
  | "pending_quantity" | "distributed_quantity" | "remaining_quantity" | "retained_quantity"
  | "returned_to_supplier_quantity" | "wasted_quantity" | "disposed_quantity";

export type ReportLine = Record<QuantityKeys, string> & {
  order_id: number;
  order_number: string;
  order_line_id: number;
  meal_date: string;
  meal_session_id: number;
  meal_session_name: string | null;
  supplier_id: number;
  supplier_name: string | null;
  item_id: number;
  item_name: string | null;
  unit_id: number;
  unit_symbol: string | null;
  distribution_recorded: boolean;
  meal_record_ids: number[];
  status: string;
  unit_rate?: string;
  planned_cost?: string;
  billed_cost?: string | null;
  bill_invoice_number?: string | null;
  bill_purchase_id?: number | null;
};

export type ReportGroup = Record<QuantityKeys, string> & {
  item_id?: number;
  item_name?: string | null;
  unit_id: number;
  unit_symbol: string | null;
  lines: number;
  planned_cost?: string;
  billed_cost?: string;
};

export type OutsourcedReport = {
  campus: { id: number; name: string | null };
  period: { date_from: string; date_to: string };
  filters: {
    supplier_id: number | null;
    supplier_name: string | null;
    item_id: number | null;
    item_name: string | null;
    meal_session_id: number | null;
    meal_session_name: string | null;
  };
  lines: ReportLine[];
  by_item: ReportGroup[];
  totals_by_unit: ReportGroup[];
  line_count: number;
  unreconciled_count: number;
  rejected_note: string | null;
  costs_visible: boolean;
  cost_totals?: { planned_cost: string; billed_cost: string; lines_without_bill: number };
  basis: { orders: string; quantities: string; costs: string; rejected: string };
  generated_at: string;
};

const MANAGERS = ["ADMIN", "KITCHEN_MANAGER"];

function holds(role: string, permissions: string[], code: string): boolean {
  return role.toUpperCase() === "ADMIN" || permissions.includes(code);
}

export const canViewOutsourced = (role: string, permissions: string[]) =>
  holds(role, permissions, "outsourced_food.read");

/** Create, edit, place and cancel orders: ADMIN and KITCHEN_MANAGER only. */
export const canManageOutsourcedOrders = (role: string, permissions: string[]) =>
  MANAGERS.includes(role.toUpperCase()) && holds(role, permissions, "outsourced_food.create");

export const canRecordDeliveries = (role: string, permissions: string[]) =>
  holds(role, permissions, "outsourced_food.create");

export const canSeeOutsourcedCosts = (role: string, permissions: string[]) =>
  holds(role, permissions, "purchase_bill.read");
