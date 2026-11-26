/**
 * Meal planning (Stage 6, PLAN01–PLAN08): API shapes, labels and who may do
 * what (docs/STAGE-6-PLANNING-PLAN.md). The API re-checks every rule.
 *
 * - Planning is ADMIN and KITCHEN_MANAGER work (6-3, 6-4): the planning
 *   codes (portion_standard.*, meal_plan.*) are not STAFF-assignable and the
 *   API refuses STAFF whatever grants exist.
 * - Approving standards and plans: ADMIN and KITCHEN_MANAGER (6-5; approving
 *   one's own draft is allowed — interim until client question Q3).
 * - Item kind: set or changed by ADMIN and KITCHEN_MANAGER only (6-8).
 *
 * Interim (not client decisions): effective-dated versions plus one-day
 * overrides (client questions §5.3); explicit conversions only (Q7/Q8);
 * same-named meal sessions reported, never linked (C5); cancel-and-replace
 * for approved plans (proposal §4.2).
 */

import type { Page } from "@/lib/payments";

export type ItemKind = "RAW" | "PREPARED" | "OUTSOURCED";
export const ITEM_KINDS: ItemKind[] = ["RAW", "PREPARED", "OUTSOURCED"];
export const KIND_LABELS: Record<ItemKind, string> = { RAW: "Raw", PREPARED: "Prepared", OUTSOURCED: "Outsourced" };

export type StandardStatus = "DRAFT" | "APPROVED" | "CANCELLED";
export type StandardState = "DRAFT" | "CANCELLED" | "IN_EFFECT" | "SCHEDULED" | "SUPERSEDED";
export const STANDARD_STATE_LABELS: Record<StandardState, string> = {
  DRAFT: "Draft — needs approval",
  CANCELLED: "Cancelled",
  IN_EFFECT: "In effect",
  SCHEDULED: "Scheduled",
  SUPERSEDED: "Superseded",
};
export const STANDARD_STATE_TONES: Record<StandardState, "warning" | "success" | "neutral" | "brand"> = {
  DRAFT: "warning",
  CANCELLED: "neutral",
  IN_EFFECT: "success",
  SCHEDULED: "brand",
  SUPERSEDED: "neutral",
};
export const SOURCE_LABELS: Record<string, string> = {
  MANUAL: "Entered",
  COPIED: "Copied from menu main items",
  SUGGESTED: "Suggested from past meals",
};

export type PlanStatus = "DRAFT" | "APPROVED" | "CANCELLED";
export const PLAN_STATUSES: PlanStatus[] = ["DRAFT", "APPROVED", "CANCELLED"];
export const PLAN_STATUS_LABELS: Record<PlanStatus, string> = { DRAFT: "Draft", APPROVED: "Approved", CANCELLED: "Cancelled" };
export const PLAN_STATUS_TONES: Record<PlanStatus, "warning" | "success" | "neutral"> = {
  DRAFT: "warning",
  APPROVED: "success",
  CANCELLED: "neutral",
};

export type UnitChoice = { id: number; symbol: string; dimension: string; factor_to_base: string };

export type HistoryEntry = { id: number; action: string; user_name: string | null; created_at: string; details: Record<string, unknown> };

export const STANDARD_HISTORY_LABELS: Record<string, string> = {
  CREATE: "Draft created",
  UPDATE: "Draft changed",
  APPROVE: "Approved",
  CANCEL: "Cancelled",
};
export const PLAN_HISTORY_LABELS: Record<string, string> = {
  CREATE: "Plan created",
  UPDATE: "Plan changed",
  APPROVE: "Approved",
  CANCEL: "Cancelled",
};

export type StandardRow = {
  id: number;
  menu_id: number;
  menu_name: string | null;
  meal_session_name: string | null;
  item_id: number;
  item_name: string | null;
  item_kind: ItemKind | null;
  quantity_per_person: string;
  unit_id: number;
  unit_symbol: string | null;
  base_unit_symbol: string | null;
  effective_from: string;
  version_no: number | null;
  status: StandardStatus;
  state: StandardState;
  source: string;
  copied_from_menu_main_item_id: number | null;
  notes: string | null;
  created_by_name: string | null;
  created_at: string;
  approved_by_name: string | null;
  approved_at: string | null;
  cancelled_by_name: string | null;
  cancelled_at: string | null;
  cancellation_reason: string | null;
};

export type StandardDetail = StandardRow & {
  today: string;
  approval_problems: string[];
  versions: StandardRow[];
  basis: { meal_record_id: number; meal_date: string; meal_session_name: string | null; quantity_used: string; unit_symbol: string | null; people_served: number }[];
  basis_totals: { quantity_used: string; people_served: number; per_person: string; unit_symbol: string | null } | null;
  history: HistoryEntry[];
};

export type StandardListResponse = Page<StandardRow> & { today: string; status_counts: Record<StandardStatus, number> };

export type StandardOptions = {
  today: string;
  menus: { id: number; name: string; meal_session_id: number; meal_session_name: string | null }[];
  items: { id: number; name: string; item_kind: ItemKind | null; base_unit_id: number; base_unit_symbol: string | null; unit_choices: UnitChoice[] }[];
};

export type CopyResult = {
  menu_id: number;
  menu_name: string;
  created: { id: number; item_name: string; quantity_per_person: string; unit_symbol: string | null }[];
  skipped: { menu_main_item_id: number; item_name: string; reason: string }[];
  note: string;
};

export type SuggestionRecord = {
  id: number;
  meal_date: string;
  meal_session_name: string | null;
  actual_total: number | null;
  net_quantity: string;
  unit_symbol: string | null;
};

export type Suggestion = {
  item_name: string;
  base_unit_symbol: string | null;
  records: { meal_record_id: number; meal_date: string; meal_session_name: string | null; status: string; people_served: number | null;
    quantity_used: string | null; included: boolean; excluded_reason: string | null }[];
  included_count: number;
  total_quantity_used: string;
  total_people_served: number;
  per_person_in_base_unit: string | null;
  unit_symbol: string | null;
  per_person_in_unit: string | null;
  suggested_quantity_per_person: string | null;
};

export type PlanStandardRef = { id: number; version_no: number | null; quantity_per_person: string; unit_id: number; unit_symbol: string | null; effective_from: string | null };

export type PlanLine = {
  id: number;
  item_id: number;
  item_name: string;
  item_kind: ItemKind | null;
  base_unit_id: number;
  base_unit_symbol: string | null;
  standard: PlanStandardRef | null;
  override: { quantity_per_person: string; unit_id: number; unit_symbol: string | null; reason: string } | null;
  quantity_per_person: string | null;
  unit_id: number | null;
  unit_symbol: string | null;
  per_person_in_base_unit: string | null;
  required_quantity: string | null;
  required_display: { quantity: string; unit_symbol: string }[];
  rounded_up: boolean;
  conversion_factor: string | null;
  required_base_quantity: string | null;
  available_stock: string;
  procurement_gap: string | null;
  unit_choices: UnitChoice[];
  problems: string[];
};

export type RecordRef = { id: number; status: string; meal_date: string; expected_total: number; actual_total: number | null };
export type PlanRef = { id: number; plan_number: string; status: PlanStatus; expected_headcount: number };

export type PlanDetail = {
  id: number;
  plan_number: string;
  plan_date: string;
  meal_session_id: number;
  meal_session_name: string | null;
  menu_id: number;
  menu_name: string | null;
  expected_headcount: number;
  status: PlanStatus;
  notes: string | null;
  calculation: "LIVE" | "SNAPSHOT";
  editable: boolean;
  created_by_name: string | null;
  created_at: string;
  updated_at: string | null;
  approved_by_name: string | null;
  approved_at: string | null;
  cancelled_by_name: string | null;
  cancelled_at: string | null;
  cancellation_reason: string | null;
  today: string;
  availability_note: string;
  lines: PlanLine[];
  approval_problems: string[];
  meal_record: RecordRef | null;
  session_warnings: string[];
  history: HistoryEntry[];
};

export type PlanSummary = {
  id: number;
  plan_number: string;
  plan_date: string;
  meal_session_name: string | null;
  menu_name: string | null;
  expected_headcount: number;
  status: PlanStatus;
  line_count: number;
  created_by_name: string | null;
  approved_by_name: string | null;
  approved_at: string | null;
  meal_record_id: number | null;
};

export type PlanListResponse = Page<PlanSummary> & { status_counts: Record<PlanStatus, number> };

export type PlanOptions = {
  today: string;
  meal_sessions: { id: number; name: string; notes: string[] }[];
  menus: { id: number; name: string; meal_session_id: number }[];
  availability_note: string;
};

export type PrefillItem = {
  item_id: number;
  item_name: string;
  item_kind: ItemKind;
  base_unit_id: number;
  base_unit_symbol: string;
  base_unit_dimension: string;
  standard: { id: number; version_no: number; quantity_per_person: string; unit_id: number; unit_symbol: string;
    unit_dimension: string; effective_from: string; factor_to_base: string };
  display: { unit_symbol: string; factor: string } | null;
  unit_choices: UnitChoice[];
  available_stock: string;
};

export type Prefill = {
  plan_date: string;
  today: string;
  meal_record: RecordRef | null;
  existing_plan: PlanRef | null;
  session_warnings: string[];
  items: PrefillItem[];
  unavailable_items: { item_id: number; item_name: string; reason: string }[];
  availability_note: string;
};

export type ComparisonItem = {
  item_id: number;
  item_name: string | null;
  unit_symbol: string | null;
  planned: boolean;
  planned_quantity: string | null;
  actual_net_quantity: string | null;
  difference: string | null;
  planned_per_person: string | null;
  actual_per_person: string | null;
};

export type Comparison = {
  plan: PlanRef & { plan_date: string; calculation: "LIVE" | "SNAPSHOT" };
  meal_record: RecordRef | null;
  record_note: string | null;
  headcounts: { plan_expected: number; record_expected: number; record_actual: number | null } | null;
  usage_source?: "CLOSING" | "LIVE";
  items: ComparisonItem[];
  dishes: { dish_name: string; unit_symbol: string | null; kind: "PREPARED" | "CARRIED" | "RECEIVED"; prepared_quantity: string;
    carried_quantity: string; received_quantity?: string; distributed_quantity: string | null; remaining_quantity: string | null;
    leftovers: Record<string, string | null> }[];
  notes: string[];
  session_warnings?: string[];
};

/** The meal record page's planning panel (ADMIN and KITCHEN_MANAGER only). */
export type PlanningPanel = { plan: PlanRef | null; session_warnings: string[]; comparison: Comparison | null };

/** Planning screens, standards and plans: ADMIN and KITCHEN_MANAGER only. */
export const canPlan = (role: string) => ["ADMIN", "KITCHEN_MANAGER"].includes(role.toUpperCase());
/** Approving standards and plans, cancelling approved plans, classifying items. */
export const canApprovePlanning = canPlan;
export const canClassifyItems = canPlan;
