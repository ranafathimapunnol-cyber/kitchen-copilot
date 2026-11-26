/**
 * Outsourced food entry rules (Stage 8a, OUT01, OUT03 criterion 1). The API
 * applies the same rules; these give immediate feedback. Quantities are
 * whole thousandths and money whole paise, so totals are exact.
 *
 * No imports: tested directly with node --test.
 */

const QUANTITY = /^\d{1,12}(\.\d{1,3})?$/;
const RATE = /^\d{1,10}(\.\d{1,4})?$/;

/** "6.125" → 6125; anything that is not a plain quantity → null. */
export function milli(text: string): number | null {
  const value = String(text ?? "").trim();
  if (value === "" || !QUANTITY.test(value)) return null;
  const [whole, fraction = ""] = value.split(".");
  return Number(whole) * 1000 + Number(fraction.padEnd(3, "0"));
}

export function fromMilli(value: number): string {
  const negative = value < 0;
  const abs = Math.abs(value);
  const whole = Math.trunc(abs / 1000);
  const fraction = String(abs % 1000).padStart(3, "0").replace(/0+$/, "");
  return `${negative ? "-" : ""}${fraction ? `${whole}.${fraction}` : String(whole)}`;
}

/** Quantity × rate, rounded half up to paise, as "3500.00" (the API's rule). Null when either is invalid. */
export function lineTotal(quantity: string, rate: string): string | null {
  const q = String(quantity ?? "").trim();
  const r = String(rate ?? "").trim();
  if (!QUANTITY.test(q) || !RATE.test(r)) return null;
  const [qw, qf = ""] = q.split(".");
  const [rw, rf = ""] = r.split(".");
  const qMilli = BigInt(qw) * BigInt(1000) + BigInt(qf.padEnd(3, "0"));
  const rTenThousandths = BigInt(rw) * BigInt(10000) + BigInt(rf.padEnd(4, "0"));
  // milli × 1/10000 = 1e-7 units; paise are 1e-2 → divide by 1e5, half up.
  const product = qMilli * rTenThousandths;
  const paise = (product + BigInt(50000)) / BigInt(100000);
  const rupees = paise / BigInt(100);
  const cents = String(paise % BigInt(100)).padStart(2, "0");
  return `${rupees}.${cents}`;
}

/** Sum of "123.45" amounts, exactly. */
export function sumMoney(values: (string | null)[]): string {
  let paise = BigInt(0);
  for (const value of values) {
    if (!value) continue;
    const [w, f = ""] = value.split(".");
    paise += BigInt(w) * BigInt(100) + BigInt(f.padEnd(2, "0").slice(0, 2));
  }
  return `${paise / BigInt(100)}.${String(paise % BigInt(100)).padStart(2, "0")}`;
}

// ============================================================
// ORDERS
// ============================================================

export type OrderLineDraft = { itemId: string; quantity: string; unitId: string; rate: string; remarks: string };
export type OrderDraft = {
  orderDate: string;
  mealDate: string;
  sessionId: string;
  supplierId: string;
  notes: string;
  lines: OrderLineDraft[];
};
export type OrderLineErrors = Partial<Record<"item" | "quantity" | "unit" | "rate", string>>;
export type OrderErrors = {
  supplier?: string;
  session?: string;
  orderDate?: string;
  mealDate?: string;
  lines?: string;
  lineErrors: OrderLineErrors[];
};

/** `today` and `latest` are YYYY-MM-DD (the campus calendar from the API options). */
export function validateOrder(draft: OrderDraft, today: string, latest: string): OrderErrors {
  const errors: OrderErrors = { lineErrors: [] };
  if (!draft.supplierId) errors.supplier = "Choose the supplier.";
  if (!draft.sessionId) errors.session = "Choose the meal session.";
  if (!draft.orderDate) errors.orderDate = "Enter the order date.";
  else if (draft.orderDate > today) errors.orderDate = "The order date cannot be in the future.";
  if (!draft.mealDate) errors.mealDate = "Enter the meal date.";
  else if (draft.orderDate && draft.mealDate < draft.orderDate) errors.mealDate = "The meal date cannot be before the order date.";
  else if (draft.mealDate > latest) errors.mealDate = `Meals can be ordered up to ${latest}.`;
  if (draft.lines.length === 0) errors.lines = "Add at least one item.";
  const seen = new Set<string>();
  draft.lines.forEach((line, index) => {
    const lineErrors: OrderLineErrors = {};
    if (!line.itemId) lineErrors.item = "Choose an item.";
    else if (seen.has(line.itemId)) lineErrors.item = "This item is already on the order.";
    seen.add(line.itemId);
    const quantity = milli(line.quantity);
    if (quantity === null) lineErrors.quantity = "Enter a quantity (up to 3 decimals).";
    else if (quantity <= 0) lineErrors.quantity = "Must be more than 0.";
    if (!line.unitId) lineErrors.unit = "Choose a unit.";
    if (!RATE.test(String(line.rate ?? "").trim())) lineErrors.rate = "Enter the rate (0 or more, up to 4 decimals).";
    errors.lineErrors[index] = lineErrors;
  });
  return errors;
}

export function hasOrderErrors(errors: OrderErrors): boolean {
  return Boolean(
    errors.supplier || errors.session || errors.orderDate || errors.mealDate || errors.lines ||
      errors.lineErrors.some((line) => Object.keys(line).length > 0),
  );
}

export function orderPayload(draft: OrderDraft) {
  return {
    order_date: draft.orderDate,
    meal_date: draft.mealDate,
    meal_session_id: Number(draft.sessionId),
    supplier_id: Number(draft.supplierId),
    notes: draft.notes.trim() || null,
    lines: draft.lines.map((line) => ({
      item_id: Number(line.itemId),
      ordered_quantity: line.quantity.trim(),
      unit_id: Number(line.unitId),
      unit_rate: line.rate.trim(),
      remarks: line.remarks.trim() || null,
    })),
  };
}

// ============================================================
// DELIVERIES (received, rejected, accepted)
// ============================================================

export type DeliveryLineDraft = {
  orderLineId: number;
  include: boolean;
  received: string;
  rejected: string;
  reason: string;
  remarks: string;
};
export type DeliveryLineErrors = Partial<Record<"received" | "rejected" | "reason", string>>;
export type DeliveryErrors = { date?: string; lines?: string; lineErrors: Record<number, DeliveryLineErrors> };

/** Accepted = received − rejected, as text; null while either is invalid or rejected > received. */
export function acceptedText(received: string, rejected: string): string | null {
  const r = milli(received);
  const x = rejected.trim() === "" ? 0 : milli(rejected);
  if (r === null || x === null || x > r) return null;
  return fromMilli(r - x);
}

/**
 * `remaining` (milli text from the API, e.g. "45.000") per order line is
 * what may still be accepted: ordered − accepted − held in other drafts.
 */
export function validateDelivery(
  draft: { date: string; lines: DeliveryLineDraft[] },
  today: string,
  orderDate: string,
  remaining: Record<number, string>,
): DeliveryErrors {
  const errors: DeliveryErrors = { lineErrors: {} };
  if (!draft.date) errors.date = "Enter the delivery date.";
  else if (draft.date > today) errors.date = "A delivery cannot be dated in the future.";
  else if (draft.date < orderDate) errors.date = "A delivery cannot be dated before the order date.";
  const included = draft.lines.filter((line) => line.include);
  if (included.length === 0) errors.lines = "Record at least one delivered item.";
  for (const line of included) {
    const lineErrors: DeliveryLineErrors = {};
    const received = milli(line.received);
    const rejected = line.rejected.trim() === "" ? 0 : milli(line.rejected);
    if (received === null || received <= 0) lineErrors.received = "Enter the quantity received (more than 0).";
    if (rejected === null) lineErrors.rejected = "Enter 0 or more (up to 3 decimals).";
    else if (received !== null && rejected > received) lineErrors.rejected = "Cannot be more than received.";
    if (rejected !== null && rejected > 0 && line.reason.trim().length < 3)
      lineErrors.reason = "Give the reason for rejecting (at least 3 characters).";
    if (received !== null && rejected !== null && rejected <= received && !lineErrors.received) {
      const left = milli(remaining[line.orderLineId] ?? "0") ?? 0;
      if (received - rejected > left)
        lineErrors.received = `Only ${fromMilli(left)} remain to be received; record the excess as rejected.`;
    }
    if (Object.keys(lineErrors).length) errors.lineErrors[line.orderLineId] = lineErrors;
  }
  return errors;
}

export function hasDeliveryErrors(errors: DeliveryErrors): boolean {
  return Boolean(errors.date || errors.lines || Object.keys(errors.lineErrors).length);
}

export function deliveryPayload(draft: { date: string; remarks: string; lines: DeliveryLineDraft[] }) {
  return {
    delivery_date: draft.date,
    remarks: draft.remarks.trim() || null,
    lines: draft.lines
      .filter((line) => line.include)
      .map((line) => {
        const rejected = line.rejected.trim() === "" ? "0" : line.rejected.trim();
        return {
          order_line_id: line.orderLineId,
          received_quantity: line.received.trim(),
          rejected_quantity: rejected,
          rejection_reason: milli(rejected) ? line.reason.trim() : null,
          remarks: line.remarks.trim() || null,
        };
      }),
  };
}

// ============================================================
// REPORT PERIODS (today, this week, this month, custom)
// ============================================================

export type Preset = "today" | "week" | "month" | "custom";

function iso(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

/** Monday-to-today for "week"; the 1st to today for "month". */
export function presetPeriod(preset: Exclude<Preset, "custom">, today: Date): { from: string; to: string } {
  if (preset === "today") return { from: iso(today), to: iso(today) };
  if (preset === "week") {
    const offset = (today.getDay() + 6) % 7; // Monday = 0
    return { from: iso(new Date(today.getFullYear(), today.getMonth(), today.getDate() - offset)), to: iso(today) };
  }
  return { from: iso(new Date(today.getFullYear(), today.getMonth(), 1)), to: iso(today) };
}

export function periodError(from: string, to: string): string | undefined {
  const pattern = /^\d{4}-\d{2}-\d{2}$/;
  if (!pattern.test(from) || !pattern.test(to)) return "Choose both dates.";
  if (from > to) return "The start date must be on or before the end date.";
  const days = (Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86400000;
  if (days >= 366) return "Choose a period of at most 366 days.";
  return undefined;
}

/** Same rule as the API's export_filename. */
export function outsourcedExportName(
  period: { date_from: string; date_to: string },
  filters: { supplier_name: string | null; item_name: string | null; meal_session_name: string | null },
  format: "xlsx" | "pdf",
): string {
  let name = `outsourced-food_${period.date_from}_${period.date_to}`;
  for (const value of [filters.supplier_name, filters.item_name, filters.meal_session_name]) {
    if (!value) continue;
    const slug = value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 30);
    if (slug) name += `_${slug}`;
  }
  return `${name}.${format}`;
}
