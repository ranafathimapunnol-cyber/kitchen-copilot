/**
 * Physical stock counts and adjustments (Stage 4, slice 4c): API shapes,
 * labels and who may do what. The API re-checks every rule.
 *
 * - stock_count.create — record a count (blind) and raise an adjustment
 *   request from one of its lines;
 * - stock_count.read   — view counts and adjustments;
 * - approving or rejecting an adjustment — ADMIN and KITCHEN_MANAGER who
 *   did not perform the count (decision S6); no fallback approver while
 *   client question Q10 is open.
 */

import type { Page } from "@/lib/payments";

export { signedDifference } from "@/lib/countMath";

export type AdjustmentStatus = "PENDING" | "APPROVED" | "REJECTED";

export const ADJUSTMENT_STATUSES: AdjustmentStatus[] = ["PENDING", "APPROVED", "REJECTED"];

export const ADJUSTMENT_LABELS: Record<AdjustmentStatus, string> = {
  PENDING: "Pending approval",
  APPROVED: "Approved",
  REJECTED: "Rejected",
};

export const ADJUSTMENT_TONES: Record<AdjustmentStatus, "warning" | "success" | "danger"> = {
  PENDING: "warning",
  APPROVED: "success",
  REJECTED: "danger",
};

/** The count form's options: never a stock balance (blind count). */
export type CountOptions = {
  today: string;
  items: { id: number; name: string; category_name: string | null; standard_unit_id: number; is_active: boolean }[];
  units: { id: number; name: string; symbol: string; dimension: string; is_active: boolean }[];
  conversions: { from_unit_id: number; to_unit_id: number }[];
  max_lines: number;
};

export type CountPayload = {
  reason: string;
  remarks: string | null;
  lines: { item_id: number; quantity: string; unit_id: number; remarks: string | null }[];
};

export type AdjustmentCore = {
  id: number;
  status: AdjustmentStatus;
  reason: string;
  raised_by_name: string | null;
  raised_at: string;
  decided_by_name: string | null;
  decided_at: string | null;
  decision_reason: string | null;
  movement_id: number | null;
};

export type CountLine = {
  id: number;
  item_id: number;
  item_name: string | null;
  category_name: string | null;
  quantity: string;
  unit_id: number;
  unit_symbol: string | null;
  conversion_factor: string;
  physical_quantity: string;
  standard_unit_id: number;
  standard_unit_symbol: string | null;
  system_balance: string;
  difference: string;
  remarks: string | null;
  /** A movement dated at or before the count time was posted after it. */
  ledger_changed: boolean;
  adjustment: AdjustmentCore | null;
  other_pending_adjustment: { id: number; count_id: number; count_number: string } | null;
  can_raise: boolean;
};

export type StockCount = {
  id: number;
  count_number: string;
  counted_at: string;
  counted_by_id: number;
  counted_by_name: string | null;
  reason: string;
  remarks: string | null;
  line_count: number;
  difference_count: number;
  lines: CountLine[];
};

/** What a counter without stock_count.read gets back: no balances. */
export type CountReceipt = { id: number; count_number: string; counted_at: string; line_count: number };

export type CountSummary = {
  id: number;
  count_number: string;
  counted_at: string;
  counted_by_name: string | null;
  reason: string;
  item_names: string[];
  line_count: number;
  difference_count: number;
  not_raised_count: number;
  pending_count: number;
  approved_count: number;
  rejected_count: number;
};

export type MovementSinceCount = {
  id: number;
  movement_type: string;
  signed_quantity: string;
  effective_at: string;
  created_at: string;
  /** Dated at or before the count time although posted after it. */
  dated_before_count: boolean;
  document_number: string | null;
  created_by_name: string | null;
};

export type Adjustment = AdjustmentCore & {
  count_id: number;
  count_number: string;
  count_item_id: number;
  counted_at: string;
  counted_by_name: string | null;
  item_id: number;
  item_name: string | null;
  unit_symbol: string | null;
  entered_quantity: string;
  entered_unit_symbol: string | null;
  physical_quantity: string;
  system_balance_at_count: string;
  difference: string;
  ledger_changed: boolean;
  you_counted: boolean;
  can_decide: boolean;
  eligible_approver_count: number | null;
  /** Current figures are given only to users who hold inventory.read. */
  stock_visible: boolean;
  count_time_balance_now: string | null;
  balance_now: string | null;
  balance_after_approval: string | null;
  shortfall: { at: string; balance: string } | null;
  would_go_negative: boolean;
  movements_since_count_total: number | null;
  movements_since_count?: MovementSinceCount[] | null;
};

export type AdjustmentListResponse = Page<Adjustment> & {
  status_counts: Record<AdjustmentStatus, number>;
};

function holds(role: string, permissions: string[], code: string): boolean {
  return role.toUpperCase() === "ADMIN" || permissions.includes(code);
}

export const canViewCounts = (role: string, permissions: string[]) => holds(role, permissions, "stock_count.read");
/** Record counts and raise adjustment requests (ADMIN and KITCHEN_MANAGER hold the code). */
export const canRecordCounts = (role: string, permissions: string[]) => holds(role, permissions, "stock_count.create");
/** Approving and rejecting: ADMIN and KITCHEN_MANAGER only; never the counter (checked per adjustment by the API). */
export const canDecideAdjustments = (role: string) => ["ADMIN", "KITCHEN_MANAGER"].includes(role.toUpperCase());

/** Why a pending adjustment is still waiting, for the people who cannot decide it (Q10). */
export function waitingReason(adjustment: Adjustment): string {
  if (adjustment.you_counted) {
    return adjustment.eligible_approver_count === 0
      ? "You performed this count, and no other active Admin or Kitchen Manager exists on this campus. It stays pending until one is available (client question Q10: no fallback approver)."
      : "You performed this count, so another Admin or Kitchen Manager must approve it.";
  }
  if (adjustment.eligible_approver_count === 0) {
    return "No active Admin or Kitchen Manager other than the counter exists on this campus. It stays pending (client question Q10: no fallback approver).";
  }
  return "Waiting for an Admin or Kitchen Manager who did not perform the count.";
}
