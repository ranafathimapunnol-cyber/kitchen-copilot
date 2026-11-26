/**
 * Meal records (Stage 5, MEAL01–MEAL05): API shapes, labels and who may do
 * what (docs/STAGE-5-MEAL-PLAN.md). The API re-checks every rule.
 *
 * - meal.read   — view meal records;
 * - meal.create — record a new meal with its expected counts;
 * - meal.update — edit an OPEN record, close it (when it reconciles) and
 *   cancel it;
 * - reopening a CLOSED record and its change history — ADMIN and
 *   KITCHEN_MANAGER only, whatever codes STAFF hold.
 *
 * Interim (not client decisions): carrying retained food forward (client
 * question Q11) and reopening as the correction route (proposal §4.2).
 */

import type { Page } from "@/lib/payments";
import type { PlanningPanel } from "@/lib/planning";

export type MealStatus = "OPEN" | "CLOSED" | "CANCELLED";
export const MEAL_STATUSES: MealStatus[] = ["OPEN", "CLOSED", "CANCELLED"];

export const MEAL_STATUS_LABELS: Record<MealStatus, string> = { OPEN: "Open", CLOSED: "Closed", CANCELLED: "Cancelled" };
export const MEAL_STATUS_TONES: Record<MealStatus, "warning" | "success" | "neutral"> = {
  OPEN: "warning",
  CLOSED: "success",
  CANCELLED: "neutral",
};

export type LeftoverClass = "RETAINED" | "RETURNED_TO_SUPPLIER" | "WASTED" | "DISPOSED";
export const LEFTOVER_CLASSES: LeftoverClass[] = ["RETAINED", "RETURNED_TO_SUPPLIER", "WASTED", "DISPOSED"];
export const LEFTOVER_LABELS: Record<LeftoverClass, string> = {
  RETAINED: "Retained",
  RETURNED_TO_SUPPLIER: "Returned to supplier",
  WASTED: "Wasted",
  DISPOSED: "Otherwise disposed",
};

export type RecordRef = { id: number; meal_date: string; meal_session_name: string | null; status: MealStatus };

export type Leftover = {
  id: number;
  classification: LeftoverClass;
  quantity: string;
  remarks: string;
  carried_to: { dish_id: number; record: RecordRef | null } | null;
};

export type MealDish = {
  id: number;
  dish_name: string;
  menu_id: number | null;
  menu_name: string | null;
  unit_id: number;
  unit_symbol: string | null;
  output_quantity: string;
  carried_quantity: string;
  /** Stage 8a: outsourced food received through a confirmed delivery. */
  received_quantity: string;
  kind: "PREPARED" | "CARRIED" | "RECEIVED";
  available_quantity: string;
  distributed_quantity: string | null;
  remaining_quantity: string | null;
  classified_quantity: string;
  reconciled: boolean;
  remarks: string | null;
  carried_in: { leftover_id: number; dish_id: number; record: RecordRef | null } | null;
  /** Stage 8a: the outsourced delivery and order a received line came from. */
  received_from: {
    delivery_id: number;
    delivery_number: string;
    delivery_date: string;
    order_id: number;
    order_number: string;
    supplier_name: string | null;
    received_quantity: string;
    rejected_quantity: string;
    accepted_quantity: string;
  } | null;
  leftovers: Leftover[];
};

/** Stage 8a: confirmed outsourced food of the record's date and session not on it (while it is closed). */
export type OutsourcedPending = {
  delivery_line_id: number;
  delivery_id: number;
  delivery_number: string;
  order_id: number;
  order_number: string;
  item_name: string | null;
  accepted_quantity: string;
  unit_symbol: string | null;
};

export type UsageRow = {
  item_id: number;
  item_name: string | null;
  unit_symbol: string | null;
  issued_quantity: string;
  returned_quantity: string;
  net_quantity: string;
};

export type MealRecord = {
  id: number;
  meal_date: string;
  meal_session_id: number;
  meal_session_name: string | null;
  status: MealStatus;
  expected_students: number;
  expected_staff: number;
  expected_guests: number;
  expected_total: number;
  actual_students: number | null;
  actual_staff: number | null;
  actual_guests: number | null;
  actual_total: number | null;
  remarks: string | null;
  created_by_name: string | null;
  created_at: string;
  updated_at: string | null;
  closed_by_name: string | null;
  closed_at: string | null;
  reopened_by_name: string | null;
  reopened_at: string | null;
  reopen_reason: string | null;
  reopen_count: number;
  cancelled_by_name: string | null;
  cancelled_at: string | null;
  cancellation_reason: string | null;
  actual_allowed: boolean;
  dishes: MealDish[];
  reconciliation_problems: string[];
  outsourced_pending: OutsourcedPending[];
  linked_issues: { id: number; issue_number: string; status: string; menu_name: string | null }[];
  usage: UsageRow[];
  usage_changes_since_closing: { item_id: number; item_name: string | null; unit_symbol: string | null; net_at_closing: string; net_now: string }[];
  /** Stage 6: the plan of this exact date and session and plan vs actual (ADMIN and KITCHEN_MANAGER only; null otherwise). */
  planning: PlanningPanel | null;
};

export type MealSummary = {
  id: number;
  meal_date: string;
  meal_session_name: string | null;
  status: MealStatus;
  expected_total: number;
  actual_total: number | null;
  dish_count: number;
  created_by_name: string | null;
  closed_by_name: string | null;
  closed_at: string | null;
  reopen_count: number;
};

export type MealListResponse = Page<MealSummary> & { status_counts: Record<MealStatus, number> };

export type MealOptions = {
  today: string;
  latest_date: string;
  meal_sessions: { id: number; name: string }[];
  menus: { id: number; name: string; meal_session_id: number }[];
  units: { id: number; name: string; symbol: string; dimension: string }[];
};

export type RetainedFood = {
  leftover_id: number;
  dish_name: string;
  quantity: string;
  unit_symbol: string | null;
  remarks: string;
  record: { id: number; meal_date: string; meal_session_name: string | null };
};

export type HistoryEntry = { id: number; action: string; user_name: string | null; created_at: string; details: Record<string, unknown> };

export const HISTORY_LABELS: Record<string, string> = {
  CREATE: "Recorded",
  UPDATE_COUNTS: "Headcounts changed",
  ADD_DISH: "Dish added",
  UPDATE_DISH: "Dish changed",
  UPDATE_DISH_REMARKS: "Dish remarks changed",
  REMOVE_DISH: "Dish removed",
  REMOVE_CARRIED: "Carried-in food removed",
  SET_DISTRIBUTION: "Distribution and leftovers recorded",
  CLEAR_DISTRIBUTION: "Distribution cleared",
  CARRY_IN: "Retained food carried in",
  CARRIED_OUT: "Retained food carried to a later meal",
  CARRY_REMOVED: "Carried retained food returned",
  RECEIVE_OUTSOURCED: "Outsourced food received",
  REMOVE_RECEIVED: "Outsourced delivery cancelled",
  RECEIVED_RELEASED: "Outsourced food released",
  CLOSE: "Closed",
  REOPEN: "Reopened",
  CANCEL: "Cancelled",
};

function holds(role: string, permissions: string[], code: string): boolean {
  return role.toUpperCase() === "ADMIN" || permissions.includes(code);
}

export const canViewMeals = (role: string, permissions: string[]) => holds(role, permissions, "meal.read");
export const canCreateMeals = (role: string, permissions: string[]) => holds(role, permissions, "meal.create");
/** Edit, close and cancel an OPEN record. */
export const canEditMeals = (role: string, permissions: string[]) => holds(role, permissions, "meal.update");
/** Reopen a CLOSED record and see its change history: ADMIN and KITCHEN_MANAGER only. */
export const canReopenMeals = (role: string) => ["ADMIN", "KITCHEN_MANAGER"].includes(role.toUpperCase());

export function sessionLabel(ref: { meal_date: string; meal_session_name: string | null } | null | undefined): string {
  if (!ref) return "—";
  const day = new Date(`${ref.meal_date}T00:00:00`);
  const date = day.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
  return `${ref.meal_session_name ?? "Meal"} · ${date}`;
}
