/**
 * Spending analysis (DASH01–DASH05) and report catalogue shapes (Stage 9).
 * Calculations happen in the API (app/services/purchase_analytics.py);
 * the screens only display them.
 */

export type CompareMode = "elapsed" | "full" | "previous";

export type ItemComparison = {
  item_id: number;
  item_name: string | null;
  category_name: string | null;
  standard_unit_symbol: string | null;
  status: "COMPARABLE" | "NEW" | "NOT_BOUGHT_NOW" | "INCOMPATIBLE";
  previous_quantity: string;
  current_quantity: string;
  quantity_change: string;
  quantity_change_percent: string | null;
  previous_price: string | null;
  current_price: string | null;
  price_change: string | null;
  price_change_percent: string | null;
  previous_value: string;
  current_value: string;
  value_change: string;
  value_change_percent: string | null;
  price_effect: string | null;
  quantity_effect: string | null;
  excluded_lines: number;
};

export type SpendingAnalysis = {
  periods: {
    current: { date_from: string; date_to: string; days: number };
    previous: { date_from: string; date_to: string; days: number };
    mode: CompareMode;
  };
  filters: { supplier_name: string | null; category_name: string | null; item_name: string | null };
  totals: {
    basis: string;
    current: string;
    previous: string;
    change: string;
    change_percent: string | null;
    current_bills: { bill_count: number; subtotal: string; discount: string; extra_charges: string; grand_total: string } | null;
    previous_bills: { bill_count: number; subtotal: string; discount: string; extra_charges: string; grand_total: string } | null;
    current_lines: number;
    previous_lines: number;
    line_change: string;
    price_effect: string;
    quantity_effect: string;
    excluded_lines: number;
    unexplained_by_items: string;
  };
  categories: { category_id: number; category_name: string | null; current_value: string; previous_value: string; value_change: string; value_change_percent: string | null }[];
  items: ItemComparison[];
  top_price_increases: ItemComparison[];
  monthly: { month: string; expenditure: string; basis: string; quantity: string | null; average_price: string | null }[];
  notes: string[];
};

export type AnalyticsOptions = {
  today: string;
  first_bill_date: string | null;
  categories: { id: number; name: string }[];
  items: { id: number; name: string; category_id: number; standard_unit_symbol: string | null }[];
  suppliers: { id: number; name: string }[];
};

export type TransactionLine = {
  purchase_item_id: number;
  purchase_id: number;
  invoice_number: string;
  purchase_date: string;
  supplier_name: string | null;
  item_name: string | null;
  category_name: string | null;
  quantity: string;
  unit_symbol: string | null;
  standard_quantity: string | null;
  standard_unit_symbol: string | null;
  unit_rate: string | null;
  line_total: string;
  attachment_count: number;
};

export const STATUS_LABELS: Record<ItemComparison["status"], string> = {
  COMPARABLE: "Comparable",
  NEW: "Not bought before",
  NOT_BOUGHT_NOW: "Not bought now",
  INCOMPATIBLE: "No conversion",
};

// ---------------- report catalogue ----------------

export type ReportFilter = "period" | "supplier" | "category" | "item" | "meal_session" | "compare";

export type CatalogEntry = {
  key: string;
  title: string;
  description: string;
  group: string;
  filters: ReportFilter[];
  period_required: boolean;
  href: string | null;
};

export type ReportColumn = { key: string; label: string; kind: "text" | "date" | "qty" | "money" | "number" | "percent"; unit_key: string | null };

export type ReportData = {
  key: string;
  title: string;
  description: string;
  campus: { id: number; name: string | null };
  period: { date_from: string; date_to: string } | null;
  as_of: string | null;
  filters: { label: string; value: string | null }[];
  columns: ReportColumn[];
  rows: Record<string, string | number | null>[];
  row_count: number;
  totals: { label: string; value: string | null; kind: string; unit?: string }[];
  notes: string[];
  comparison: SpendingAnalysis["periods"] | null;
  generated_at: string;
};
