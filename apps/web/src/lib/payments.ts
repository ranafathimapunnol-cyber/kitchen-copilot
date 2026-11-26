/**
 * Types and formatting for supplier payments and balances (PUR04).
 *
 * The API returns money as two-place decimal strings ("1250.50"). They are
 * kept as strings in state and only converted to numbers for display and
 * comparisons, so the value sent back is exactly what the user typed.
 */

import { api } from "@/lib/api/client";

export const PAYMENT_METHODS = [
  { value: "BANK_TRANSFER", label: "Bank transfer" },
  { value: "UPI", label: "UPI" },
  { value: "CASH", label: "Cash" },
  { value: "CHEQUE", label: "Cheque" },
  { value: "OTHER", label: "Other" },
] as const;

export type PaymentMethod = (typeof PAYMENT_METHODS)[number]["value"];

export type PaymentStatus = "UNPAID" | "PARTIALLY_PAID" | "PAID" | "OVERPAID";

export type BillBalance = {
  purchase_id: number;
  supplier_id: number;
  supplier_name: string | null;
  invoice_number: string;
  purchase_date: string;
  grand_total: string;
  paid_total: string;
  outstanding: string;
  overpaid: string;
  payment_status: PaymentStatus;
};

export type SupplierPayment = {
  id: number;
  purchase_id: number;
  payment_date: string;
  amount: string;
  payment_method: string;
  reference_number: string | null;
  remarks: string | null;
  created_by: number | null;
  created_by_name: string | null;
  created_at: string;
  invoice_number?: string;
  supplier_id?: number;
  supplier_name?: string | null;
};

export type SupplierBalance = {
  supplier_id: number;
  supplier_name: string | null;
  bill_count: number;
  open_bill_count: number;
  total_billed: string;
  total_paid: string;
  outstanding: string;
  overpaid: string;
};

export type BalanceTotals = {
  total_billed: string;
  total_paid: string;
  outstanding: string;
  overpaid: string;
  open_bill_count: number;
  supplier_count: number;
};

export type Page<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

export type PaymentListResponse = Page<SupplierPayment> & {
  total_paid: string;
};

export type SupplierBalanceResponse = Page<SupplierBalance> & {
  totals: BalanceTotals;
};

export type RecordPaymentResponse = {
  payment: SupplierPayment;
  bill: BillBalance;
};

/** A supplier bill as GET/POST /api/purchases returns it. */
export type SupplierBill = Partial<DuplicateStatus> & {
  id: number;
  supplier_id: number;
  supplier_name: string | null;
  invoice_number: string;
  purchase_date: string;
  subtotal: string;
  discount: string;
  extra_charges: string;
  grand_total: string;
  remarks: string | null;
  status: string;
  created_at: string;
  /** The purchase order the bill was entered against, if any (Stage 3). */
  purchase_order_id?: number | null;
  purchase_order_number?: string | null;
  items: {
    id: number;
    item_id: number;
    item_name: string | null;
    category_name: string | null;
    quantity: number | string;
    unit_id: number;
    unit_symbol: string | null;
    unit_rate: string;
    line_total: string;
    remarks: string | null;
    purchase_order_item_id?: number | null;
  }[];
};

export type SimilarBill = {
  purchase_id: number;
  invoice_number: string;
  purchase_date: string;
  grand_total: string;
};

export type DuplicateReview = {
  reviewed_at: string;
  reviewed_by: number;
  reviewed_by_name: string | null;
  note: string | null;
};

/** Possible-duplicate status of one bill (PUR01). */
export type DuplicateStatus = {
  possible_duplicates: SimilarBill[];
  duplicate_review: DuplicateReview | null;
  flagged_as_possible_duplicate: boolean;
};

export type PossibleDuplicate = {
  purchase_id: number;
  supplier_id: number;
  supplier_name: string | null;
  invoice_number: string;
  purchase_date: string;
  grand_total: string;
  possible_duplicates: SimilarBill[];
  duplicate_review: DuplicateReview | null;
};

export type BillAttachment = {
  id: number;
  purchase_id: number;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  checksum_sha256: string;
  remarks: string | null;
  uploaded_by: number;
  uploaded_by_name: string | null;
  uploaded_at: string;
};

/** Whether the signed-in user may review possible duplicates. */
export function canReviewDuplicates(role: string, permissions: string[]) {
  return role.toUpperCase() === "ADMIN" || permissions.includes("purchase_bill.update");
}

/** A new bill's balance, before any payment: what the payment dialog
 * needs to pay it straight away. */
export function newBillBalance(bill: SupplierBill): BillBalance {
  const zero = toAmount(bill.grand_total) === 0;
  return {
    purchase_id: bill.id,
    supplier_id: bill.supplier_id,
    supplier_name: bill.supplier_name,
    invoice_number: bill.invoice_number,
    purchase_date: bill.purchase_date,
    grand_total: bill.grand_total,
    paid_total: "0.00",
    outstanding: bill.grand_total,
    overpaid: "0.00",
    payment_status: zero ? "PAID" : "UNPAID",
  };
}

export type ReportSupplierRow = {
  supplier_id: number;
  supplier_name: string | null;
  bill_count: number;
  billed: string;
  payment_count: number;
  paid: string;
  paid_cash: string;
  opening_balance: string;
  closing_balance: string;
};

export type PurchasesVsPaymentsReport = {
  period: { date_from: string; date_to: string };
  filters: { supplier_id: number | null; supplier_name: string | null };
  campus: { id: number; name: string | null };
  currency: string;
  basis: Record<string, string>;
  generated_at: string;
  suppliers: ReportSupplierRow[];
  totals: Omit<ReportSupplierRow, "supplier_id" | "supplier_name"> & {
    supplier_count: number;
    paid_by_method: { payment_method: string; payment_count: number; amount: string }[];
  };
};

/** The PUR04 list endpoints' maximum page size. */
const FULL_PAGE = 100;

/** Safety cap: 50 × 100 rows. */
const MAX_PAGES = 50;

/**
 * Loads every page of a paginated PUR04 list, for dropdowns that must not
 * silently stop at the first page (a daily supplier can pass 100 open
 * bills). Returns the rows and the first page's envelope (totals etc.).
 */
export async function fetchAllPages<T, R extends Page<T> = Page<T>>(
  endpoint: string
): Promise<{ items: T[]; first: R; truncated: boolean }> {
  const separator = endpoint.includes("?") ? "&" : "?";
  const url = (page: number) =>
    `${endpoint}${separator}page=${page}&page_size=${FULL_PAGE}`;

  const first = await api.get<R>(url(1));
  const items = [...first.items];
  const pages = Math.min(first.total_pages, MAX_PAGES);

  for (let page = 2; page <= pages; page++) {
    const next = await api.get<R>(url(page));
    items.push(...next.items);
  }

  return { items, first, truncated: first.total_pages > MAX_PAGES };
}

export function toAmount(value: unknown): number {
  const number = Number(value ?? 0);
  return Number.isFinite(number) ? number : 0;
}

const rupees = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** "1250.5" → "₹1,250.50". Payments are shown to the paisa. */
export function formatRupees(value: unknown): string {
  return rupees.format(toAmount(value));
}

export function methodLabel(method: string): string {
  return (
    PAYMENT_METHODS.find((option) => option.value === method)?.label ?? method
  );
}

/** "2026-11-05" → "05 Nov 2026", parsed as a local date (no UTC shift). */
export function formatDay(value?: string | null): string {
  if (!value) return "—";

  const [year, month, day] = value.slice(0, 10).split("-").map(Number);
  if (![year, month, day].every(Number.isFinite)) return "—";

  return new Date(year, month - 1, day).toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

/**
 * A moment in time (an ISO timestamp with offset) → "18 Nov 2026, 10:32 am"
 * in the browser's time zone. Use formatDay for plain dates instead: slicing a
 * UTC timestamp would give yesterday's date before 05:30 in India.
 */
export function formatDateTime(value?: string | null): string {
  if (!value) return "—";
  const moment = new Date(value);
  return Number.isNaN(moment.getTime())
    ? "—"
    : moment.toLocaleString("en-IN", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
}

/** Today's date in the browser's time zone, as YYYY-MM-DD. */
export function todayISO(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

/** A positive amount with at most two decimal places, e.g. "1250.50". */
export const AMOUNT_PATTERN = /^\d{1,16}(\.\d{1,2})?$/;

export function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

/** Whether the signed-in user may record payments (the API re-checks). */
export function canRecordPayments(role: string, permissions: string[]) {
  return (
    role.toUpperCase() === "ADMIN" ||
    permissions.includes("purchase_bill.create")
  );
}

/** Entering a bill needs the same code as recording a payment. */
export const canEnterBills = canRecordPayments;
