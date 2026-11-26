/**
 * Purchase orders (Stage 3): API shapes and who may do what. The API
 * re-checks every permission and keeps data campus-scoped.
 *
 * - purchase_order.read   — view orders;
 * - purchase_order.create — create a draft order;
 * - purchase_order.update — edit a draft, place, close or cancel.
 * Entering a bill against an order is part of bill entry
 * (purchase_bill.create).
 */

import type { Page } from "@/lib/payments";

export type OrderStatus = "DRAFT" | "PLACED" | "CLOSED" | "CANCELLED";
export type ReceivingState = "NOT_RECEIVED" | "PARTLY_RECEIVED" | "RECEIVED";

export const ORDER_STATUSES: OrderStatus[] = ["DRAFT", "PLACED", "CLOSED", "CANCELLED"];

export const ORDER_STATUS_LABELS: Record<OrderStatus, string> = {
  DRAFT: "Draft",
  PLACED: "Placed",
  CLOSED: "Closed",
  CANCELLED: "Cancelled",
};

export const RECEIVING_LABELS: Record<ReceivingState, string> = {
  NOT_RECEIVED: "Not received",
  PARTLY_RECEIVED: "Partly received",
  RECEIVED: "Fully received",
};

export const HISTORY_LABELS: Record<string, string> = {
  CREATE: "Created",
  UPDATE: "Edited",
  PLACE: "Placed with supplier",
  CLOSE: "Closed",
  CANCEL: "Cancelled",
};

export type OrderActions = {
  edit: boolean;
  place: boolean;
  close: boolean;
  cancel: boolean;
  bill: boolean;
};

export type OrderSummary = {
  id: number;
  order_number: string;
  supplier_id: number;
  supplier_name: string | null;
  order_date: string;
  expected_date: string | null;
  status: OrderStatus;
  remarks: string | null;
  line_count: number;
  bill_count: number;
  receiving_state: ReceivingState;
  over_billed: boolean;
  created_by_name: string | null;
  created_at: string;
  updated_at: string | null;
  placed_by_name: string | null;
  placed_at: string | null;
  closed_by_name: string | null;
  closed_at: string | null;
  close_reason: string | null;
  cancelled_by_name: string | null;
  cancelled_at: string | null;
  cancel_reason: string | null;
  actions: OrderActions;
};

export type OrderLine = {
  id: number;
  item_id: number;
  item_name: string | null;
  category_name: string | null;
  unit_id: number;
  unit_symbol: string | null;
  remarks: string | null;
  ordered_quantity: string;
  billed_quantity: string;
  received_quantity: string;
  accepted_quantity: string;
  rejected_quantity: string;
  in_draft_quantity: string;
  left_to_bill: string;
  left_to_receive: string;
  over_billed: string;
  over_received: string;
  unconvertible: boolean;
};

export type OrderDetail = OrderSummary & {
  items: OrderLine[];
  bills: { purchase_id: number; invoice_number: string; purchase_date: string }[];
  history: { action: string; user_name: string; at: string; reason: string | null }[];
};

export type OrderListResponse = Page<OrderSummary> & {
  status_counts: Record<OrderStatus, number>;
};

export type BillableOrder = {
  id: number;
  order_number: string;
  order_date: string;
  expected_date: string | null;
  items: {
    id: number;
    item_id: number;
    item_name: string | null;
    unit_id: number;
    unit_symbol: string | null;
    ordered_quantity: string;
    billed_quantity: string;
    left_to_bill: string;
  }[];
};

function holds(role: string, permissions: string[], code: string): boolean {
  // Purchase orders are Admin and Kitchen Manager work: STAFF never have
  // access, whatever older assignments exist (the API applies the same rule).
  if (role.toUpperCase() === "STAFF") return false;
  return role.toUpperCase() === "ADMIN" || permissions.includes(code);
}

export const canViewOrders = (role: string, permissions: string[]) =>
  holds(role, permissions, "purchase_order.read");

export const canCreateOrders = (role: string, permissions: string[]) =>
  holds(role, permissions, "purchase_order.create");

/** Edit a draft, place, close or cancel. */
export const canManageOrders = (role: string, permissions: string[]) =>
  holds(role, permissions, "purchase_order.update");
