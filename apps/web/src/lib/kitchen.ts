/**
 * Kitchen issues and unused returns (Stage 4, slice 4b): API shapes, labels
 * and who may do what. The API re-checks every permission and stock rule.
 *
 * - consumption.read   — view issues and returns;
 * - consumption.create — record a draft issue or return;
 * - consumption.update — edit, cancel or confirm a draft (including one's
 *   own, decision 4b-3);
 * - reversing a confirmed issue or return — ADMIN and KITCHEN_MANAGER only.
 */

import type { Page } from "@/lib/payments";

export type DocumentStatus = "DRAFT" | "CONFIRMED" | "CANCELLED" | "REVERSED";

export const DOCUMENT_STATUSES: DocumentStatus[] = ["DRAFT", "CONFIRMED", "CANCELLED", "REVERSED"];

export const STATUS_LABELS: Record<DocumentStatus, string> = {
  DRAFT: "Draft",
  CONFIRMED: "Confirmed",
  CANCELLED: "Cancelled",
  REVERSED: "Reversed",
};

export const STATUS_TONES: Record<DocumentStatus, "warning" | "success" | "neutral" | "danger"> = {
  DRAFT: "warning",
  CONFIRMED: "success",
  CANCELLED: "neutral",
  REVERSED: "danger",
};

type DocumentFields = {
  status: DocumentStatus;
  remarks: string | null;
  effective_at: string | null;
  created_by_name: string | null;
  created_at: string;
  updated_at: string | null;
  confirmed_by_name: string | null;
  confirmed_at: string | null;
  cancelled_by_name: string | null;
  cancelled_at: string | null;
  cancellation_reason: string | null;
  reversed_by_name: string | null;
  reversed_at: string | null;
  reversal_reason: string | null;
};

export type IssueLine = {
  id: number;
  item_id: number;
  item_name: string | null;
  quantity: string;
  unit_id: number;
  unit_symbol: string | null;
  conversion_factor: string;
  standard_quantity: string;
  standard_unit_id: number;
  standard_unit_symbol: string | null;
  remarks: string | null;
  returned_quantity: string;
  in_draft_return_quantity: string;
  returnable_quantity: string;
  net_quantity: string | null;
  movement_id: number | null;
  reversal_movement_id: number | null;
};

export type ReturnLine = {
  id: number;
  issue_item_id: number;
  item_name: string | null;
  quantity: string;
  unit_id: number;
  unit_symbol: string | null;
  standard_quantity: string;
  standard_unit_symbol: string | null;
  remarks: string | null;
  movement_id: number | null;
};

export type KitchenReturn = DocumentFields & {
  id: number;
  return_number: string;
  return_date: string;
  lines: ReturnLine[];
};

export type KitchenIssue = DocumentFields & {
  id: number;
  issue_number: string;
  issue_date: string;
  meal_session_id: number;
  meal_session_name: string | null;
  menu_id: number;
  menu_name: string | null;
  /** The meal record of the same date and session (Stage 5), if any. */
  meal_record: { id: number; status: "OPEN" | "CLOSED" | "CANCELLED" } | null;
  lines: IssueLine[];
  returns: KitchenReturn[];
};

export type IssueSummary = DocumentFields & {
  id: number;
  issue_number: string;
  issue_date: string;
  meal_session_name: string | null;
  menu_name: string | null;
  item_names: string[];
  line_count: number;
  confirmed_return_count: number;
};

export type IssueListResponse = Page<IssueSummary> & {
  status_counts: Record<DocumentStatus, number>;
};

export type FormOptions = {
  today: string;
  meal_sessions: { id: number; name: string }[];
  menus: { id: number; name: string; meal_session_id: number }[];
  items: { id: number; name: string; category_name: string | null; standard_unit_id: number; is_active: boolean }[];
  units: { id: number; name: string; symbol: string; dimension: string; is_active: boolean }[];
  conversions: { from_unit_id: number; to_unit_id: number }[];
  /** True only for users who hold inventory.read; balances are then given. */
  stock_visible: boolean;
  balances: Record<string, string> | null;
};

export type IssuePayload = {
  issue_date: string;
  meal_session_id: number;
  menu_id: number;
  remarks: string | null;
  lines: { item_id: number; quantity: string; unit_id: number; remarks: string | null }[];
};

function holds(role: string, permissions: string[], code: string): boolean {
  return role.toUpperCase() === "ADMIN" || permissions.includes(code);
}

export const canViewIssues = (role: string, permissions: string[]) => holds(role, permissions, "consumption.read");
export const canRecordIssues = (role: string, permissions: string[]) => holds(role, permissions, "consumption.create");
/** Edit, cancel or confirm a draft issue or return. */
export const canManageIssues = (role: string, permissions: string[]) => holds(role, permissions, "consumption.update");
/** Reversals: ADMIN and KITCHEN_MANAGER only, whatever codes STAFF hold. */
export const canReverseIssues = (role: string) => ["ADMIN", "KITCHEN_MANAGER"].includes(role.toUpperCase());
