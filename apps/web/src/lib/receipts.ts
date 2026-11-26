/**
 * Goods receipts (PUR03) and the stock movement log: API shapes and who may
 * do what. The API re-checks every permission and keeps data campus-scoped.
 *
 * Permission codes (unchanged, as the API checks them):
 * - inventory.read   — view receipts, bill receiving progress, stock log;
 * - inventory.create — record a draft receipt;
 * - inventory.update — correct, accept or cancel a draft.
 */

import type { Page } from "@/lib/payments";

export type ReceiptStatus = "DRAFT" | "ACCEPTED" | "CANCELLED";

export const RECEIPT_STATUSES: ReceiptStatus[] = ["DRAFT", "ACCEPTED", "CANCELLED"];

export const RECEIPT_STATUS_LABELS: Record<ReceiptStatus, string> = {
  DRAFT: "Draft",
  ACCEPTED: "Accepted",
  CANCELLED: "Cancelled",
};

export type ReceiptLine = {
  id: number;
  purchase_item_id: number;
  item_id: number | null;
  item_name: string | null;
  billed_quantity: string | null;
  unit_symbol: string | null;
  quantity_received: string;
  quantity_accepted: string;
  quantity_rejected: string;
  remarks: string | null;
};

export type PostedMovement = {
  id: number;
  receipt_item_id: number | null;
  item_name: string | null;
  quantity: string;
  unit_symbol: string | null;
};

export type Receipt = {
  id: number;
  purchase_id: number;
  invoice_number: string | null;
  purchase_date: string | null;
  supplier_id: number | null;
  supplier_name: string | null;
  receipt_date: string;
  status: ReceiptStatus;
  remarks: string | null;
  accepted_by: number | null;
  accepted_by_name: string | null;
  accepted_at: string | null;
  created_by: number;
  created_by_name: string | null;
  created_at: string;
  cancellation: {
    reason: string | null;
    cancelled_by: number | null;
    cancelled_by_name: string | null;
    cancelled_at: string;
  } | null;
  items: ReceiptLine[];
  stock_movements: PostedMovement[];
};

export type ReceiptSummary = {
  id: number;
  purchase_id: number;
  invoice_number: string;
  supplier_id: number;
  supplier_name: string | null;
  receipt_date: string;
  status: ReceiptStatus;
  line_count: number;
  remarks: string | null;
  created_by_name: string | null;
  created_at: string;
  accepted_by_name: string | null;
  accepted_at: string | null;
};

export type ReceiptListResponse = Page<ReceiptSummary> & {
  status_counts: Record<ReceiptStatus, number>;
};

export type ReceivableBill = {
  purchase_id: number;
  invoice_number: string;
  supplier_id: number;
  supplier_name: string | null;
  purchase_date: string;
  line_count: number;
  open_line_count: number;
};

export type ReceivingLine = {
  purchase_item_id: number;
  /** The purchase-order line this bill line bills for, if any. */
  purchase_order_item_id?: number | null;
  /** The order line's quantity, in this bill line's unit (Stage 3). */
  ordered_quantity?: string | null;
  item_id: number;
  item_name: string | null;
  category_name: string | null;
  unit_id: number;
  unit_symbol: string | null;
  billed_quantity: string;
  received_quantity: string;
  accepted_quantity: string;
  rejected_quantity: string;
  in_draft_quantity: string;
  remaining_quantity: string;
};

export type Receiving = {
  purchase_id: number;
  invoice_number: string;
  supplier_id: number;
  supplier_name: string | null;
  purchase_date: string;
  purchase_order_id?: number | null;
  purchase_order_number?: string | null;
  lines: ReceivingLine[];
  /** Stage 8a: outsourced food on the bill, received as outsourced deliveries, never into stock. */
  outsourced_lines?: { purchase_item_id: number; item_id: number; item_name: string | null; unit_symbol: string | null; billed_quantity: string }[];
  receipt_counts: Record<ReceiptStatus, number>;
  fully_received: boolean;
};

export type StockMovementRow = {
  id: number;
  /** When the movement was posted. */
  created_at: string;
  /** When the stock moved (Stage 4 ledger). */
  effective_at?: string;
  item_id: number;
  item_name: string | null;
  movement_type: string;
  /** +1 stock in, -1 stock out; quantity is always positive. */
  direction?: number;
  quantity: string;
  unit_symbol: string | null;
  reference_type: string;
  reference_id: number;
  source_key?: string;
  receipt_id: number | null;
  opening_id?: number | null;
  document_number?: string | null;
  kitchen_issue_id?: number | null;
  stock_count_id?: number | null;
  invoice_number: string | null;
  supplier_name: string | null;
  reversal_of_id?: number | null;
  reversed_by_movement_id?: number | null;
  remarks: string | null;
  created_by_name: string | null;
};

export { MOVEMENT_TYPE_LABELS } from "@/lib/stock";

function holds(role: string, permissions: string[], code: string): boolean {
  return role.toUpperCase() === "ADMIN" || permissions.includes(code);
}

export const canViewReceipts = (role: string, permissions: string[]) =>
  holds(role, permissions, "inventory.read");

export const canRecordReceipts = (role: string, permissions: string[]) =>
  holds(role, permissions, "inventory.create");

/** Correct, accept or cancel a draft. */
export const canManageReceipts = (role: string, permissions: string[]) =>
  holds(role, permissions, "inventory.update");
