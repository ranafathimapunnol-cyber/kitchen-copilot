/**
 * Home dashboard payload (GET /api/dashboard/overview). Every section is
 * present only when the user holds its read permission (the API decides);
 * money appears only with supplier-bill access. Headcount comes from meal
 * records (Stage 9).
 */

export type Kpis = Record<string, number | string | null>;

export type DashboardOverview = {
  campus_id: number;
  campus_name?: string | null;
  role: string;
  generated_at: string;
  permissions: string[];
  kpis: Kpis;
  headcount?: {
    today: number | null;
    today_basis: "actual" | "expected" | null;
    source: string;
    sessions: { meal_record_id: number; meal_session_name: string | null; status: string; expected: number | null; actual: number | null }[];
    tomorrow: { meal_record_id: number; meal_session_name: string | null; expected: number | null }[];
    trend: { date: string; count: number | null; actual: number | null; expected: number | null }[];
  };
  inventory?: {
    active_items: number;
    active_suppliers: number;
    recent_movements: { id: number; item_name: string; movement_type: string; direction?: number; quantity: number | string; unit: string; created_at: string }[];
  };
  stock?: {
    items_tracked: number;
    below_minimum: number;
    out_of_stock: number;
    lowest: { item_id: number; item_name: string; balance: string; minimum: string; needed: string; unit: string | null }[];
    last_movement_at: string | null;
  };
  meals?: {
    open_count: number;
    awaiting_close_count: number;
    awaiting_close: { id: number; meal_date: string; meal_session_name: string | null }[];
    week_status_counts: Record<string, number>;
    dishes_today: number;
  };
  planning?: {
    upcoming: { id: number; plan_number: string; plan_date: string; status: string; meal_session_name: string | null; expected_headcount: number }[];
    draft_plans: number;
    draft_standards: number;
    approved_standards: number;
  };
  outsourced?: {
    orders: { id: number; order_number: string; meal_date: string; meal_session_name: string | null; supplier_name: string | null; receiving_status: string | null }[];
    draft_orders: number;
    draft_deliveries: number;
    waiting_for_meal_record: number;
    planned_cost_this_month?: string;
  };
  kitchen?: { issues_today: number; draft_issues: number };
  counts?: { pending_adjustments: number };
  spending?: {
    periods: { current: { date_from: string; date_to: string }; previous: { date_from: string; date_to: string } };
    current: string;
    previous: string;
    change: string;
    change_percent: string | null;
    bills: number;
    top_categories: { category_id: number; category_name: string | null; value: string }[];
  };
  purchases?: { count_this_month: number; total_this_month: number | string };
  payments?: {
    paid_this_month: string;
    outstanding: string;
    open_bill_count: number;
    suppliers_owed: number;
    top_outstanding: { supplier_id: number; supplier_name: string | null; open_bill_count: number; outstanding: string }[];
  };
  receipts?: { count_this_month: number };
  waste?: { records_today: number; estimated_cost_today: number | string };
  activity?: { id: number; user_name: string; action: string; entity_type: string; entity_id?: number | null; created_at: string }[];
  team?: { active_admins: number; active_kitchen_managers: number; active_staff: number; inactive_users: number; staff_without_access: number };
};

/** "Not comparable" when the API returns no percentage (previous value zero or missing). */
export function percentText(value: string | null | undefined): string {
  if (value === null || value === undefined) return "Not comparable";
  const number = Number(value);
  return `${number > 0 ? "+" : ""}${value}%`;
}
