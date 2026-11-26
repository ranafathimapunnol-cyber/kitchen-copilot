/**
 * Stock ledger (Stage 4, slice 4a): API shapes, labels and who may do what.
 * The API re-checks every permission and keeps data campus-scoped.
 *
 * - inventory.read — stock balances, replenishment list, item ledger and
 *   the movement log (ADMIN, KITCHEN_MANAGER; STAFF when assigned);
 * - opening stock (record, list, reverse) — ADMIN and KITCHEN_MANAGER by
 *   role, never STAFF, whatever codes a STAFF user holds (decision S3).
 */

import type { Page } from "@/lib/payments";

export type StockBalance = {
  item_id: number;
  item_name: string;
  category_id: number;
  category_name: string | null;
  unit_id: number;
  unit_symbol: string | null;
  is_active: boolean;
  balance: string;
  minimum_stock: string;
  has_minimum: boolean;
  below_minimum: boolean;
  shortfall: string;
  last_movement_at: string | null;
};

export type BalanceSummary = {
  items: number;
  below_minimum: number;
  zero_or_less: number;
  without_minimum: number;
};

export type BalancesResponse = Page<StockBalance> & { summary: BalanceSummary };

export type ReplenishmentResponse = {
  generated_at: string;
  campus_date: string;
  items: StockBalance[];
  total: number;
};

export type LedgerMovement = {
  id: number;
  movement_type: string;
  direction: number;
  quantity: string;
  signed_quantity: string;
  balance_after: string | null;
  unit_symbol: string | null;
  effective_at: string;
  created_at: string;
  source_key: string;
  reference_type: string;
  reference_id: number;
  receipt_id: number | null;
  opening_id: number | null;
  /** KI-00001 / KR-00001 for kitchen issues and returns (slice 4b), SC-00001
   * for a count adjustment (slice 4c). */
  document_number: string | null;
  kitchen_issue_id: number | null;
  stock_count_id: number | null;
  invoice_number: string | null;
  supplier_name: string | null;
  reversal_of_id: number | null;
  reversed_by_movement_id: number | null;
  remarks: string | null;
  created_by_name: string | null;
};

export type ItemLedgerResponse = Page<never> & {
  item: StockBalance;
  movements: LedgerMovement[];
};

export type OpeningStatus = "ACTIVE" | "REVERSED";

export type OpeningEntry = {
  id: number;
  item_id: number;
  item_name: string | null;
  quantity: string;
  unit_id: number;
  unit_symbol: string | null;
  conversion_factor: string;
  standard_quantity: string;
  standard_unit_symbol: string | null;
  effective_date: string;
  remarks: string | null;
  status: OpeningStatus;
  created_by_name: string | null;
  created_at: string;
  movement_id: number | null;
  reversed_by_name: string | null;
  reversed_at: string | null;
  reversal_reason: string | null;
  reversal_movement_id: number | null;
};

export type OpeningListResponse = Page<OpeningEntry> & {
  status_counts: Record<OpeningStatus, number>;
  items_with_active_opening: number[];
};

/** Every ledger movement type. Supplier returns wait for PUR05 (Q6). */
export const MOVEMENT_TYPE_LABELS: Record<string, string> = {
  OPENING: "Opening stock",
  RECEIPT: "Receipt",
  ISSUE: "Kitchen issue",
  UNUSED_RETURN: "Unused return",
  SUPPLIER_RETURN: "Supplier return",
  ADJUSTMENT: "Adjustment",
  REVERSAL: "Reversal",
};

/** The types that can exist today, for filters. */
export const CURRENT_MOVEMENT_TYPES = ["OPENING", "RECEIPT", "ISSUE", "UNUSED_RETURN", "ADJUSTMENT", "REVERSAL"] as const;

export function movementLabel(type: string): string {
  return MOVEMENT_TYPE_LABELS[type] ?? type;
}

export function movementTone(type: string): "success" | "brand" | "warning" | "danger" | "neutral" {
  switch (type) {
    case "RECEIPT":
    case "UNUSED_RETURN":
      return "success";
    case "OPENING":
      return "brand";
    case "REVERSAL":
      return "warning";
    case "ISSUE":
    case "SUPPLIER_RETURN":
      return "danger";
    default:
      return "neutral";
  }
}

export const canViewStock = (role: string, permissions: string[]) =>
  role.toUpperCase() === "ADMIN" || permissions.includes("inventory.read");

/** Opening stock and its reversal: ADMIN and KITCHEN_MANAGER only. */
export const canManageOpeningStock = (role: string) =>
  ["ADMIN", "KITCHEN_MANAGER"].includes(role.toUpperCase());
