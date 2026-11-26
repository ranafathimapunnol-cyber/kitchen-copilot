/**
 * Stock ledger display and opening-stock entry rules (Stage 4, slice 4a).
 * The API applies the same rules; these give immediate feedback.
 * Quantities are handled as whole thousandths so 0.1 + 0.2 is exactly 0.3.
 *
 * No imports: tested directly with node --test.
 */

/** Up to 12 whole digits and 3 decimal places (the API allows 3). */
const QUANTITY = /^\d{1,12}(\.\d{1,3})?$/;

function toMilli(text: string): number | null {
  const value = text.trim().replace(/^-/, "");
  if (value === "" || !QUANTITY.test(value)) return null;
  const [whole, fraction = ""] = value.split(".");
  return Number(whole) * 1000 + Number(fraction.padEnd(3, "0"));
}

/** "40.000" → "40", "12.500" → "12.5"; keeps a leading minus. */
export function plainQuantity(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const text = String(value).trim();
  const negative = text.startsWith("-");
  const milli = toMilli(text);
  if (milli === null) return text;
  const whole = Math.floor(milli / 1000);
  const fraction = String(milli % 1000).padStart(3, "0").replace(/0+$/, "");
  const shown = fraction ? `${whole}.${fraction}` : String(whole);
  return negative && milli !== 0 ? `−${shown}` : shown;
}

/** A movement quantity with its sign: "+40", "−12.5" (a true minus sign). */
export function signedQuantity(direction: number, quantity: string): string {
  const shown = plainQuantity(quantity).replace(/^−/, "");
  return `${direction < 0 ? "−" : "+"}${shown}`;
}

export type StockState = "below" | "ok" | "no-minimum" | "out";

/** Where an item stands against its minimum stock. "out" = nothing left
 * while a minimum is set; items without a minimum are never "below". */
export function stockState(row: {
  balance: string;
  minimum_stock: string;
  has_minimum: boolean;
  below_minimum: boolean;
}): StockState {
  if (!row.has_minimum) return "no-minimum";
  const balance = row.balance.trim();
  if (balance.startsWith("-") || toMilli(balance) === 0) return "out";
  return row.below_minimum ? "below" : "ok";
}

/** Balance as a share of the minimum, 0–1, for a small level bar. */
export function levelRatio(balance: string, minimum: string): number {
  const have = toMilli(balance);
  const need = toMilli(minimum);
  if (have === null || need === null || need === 0 || balance.trim().startsWith("-")) return 0;
  return Math.min(1, have / need);
}

export type OpeningLineDraft = {
  key: string;
  itemId: string;
  quantity: string;
  unitId: string;
  remarks: string;
};

export type OpeningLineErrors = { item?: string; quantity?: string; unit?: string };

export type OpeningCheck = {
  valid: boolean;
  lines: Record<string, OpeningLineErrors>;
  /** A problem with the whole entry (date, or no lines). */
  form?: string;
};

/**
 * Checks an opening-stock entry before it is sent:
 * - the date is today or earlier (campus calendar, as the browser sees it);
 * - every line has an item, a unit and a quantity above zero with at most
 *   three decimals;
 * - an item appears once, and not if it already has active opening stock.
 * Empty lines (no item and no quantity) are ignored.
 */
export function checkOpening(
  effectiveDate: string,
  today: string,
  lines: OpeningLineDraft[],
  itemsWithActiveOpening: number[],
): OpeningCheck {
  const result: OpeningCheck = { valid: true, lines: {} };
  if (!effectiveDate) {
    result.form = "Choose the date the opening stock applies from.";
  } else if (effectiveDate > today) {
    result.form = "Opening stock cannot be dated in the future.";
  }

  const used = lines.filter((line) => line.itemId || line.quantity.trim());
  if (used.length === 0 && !result.form) {
    result.form = "Add at least one item.";
  }

  const seen = new Set<string>();
  for (const line of used) {
    const errors: OpeningLineErrors = {};
    if (!line.itemId) {
      errors.item = "Choose an item.";
    } else if (seen.has(line.itemId)) {
      errors.item = "This item is already in the list.";
    } else if (itemsWithActiveOpening.includes(Number(line.itemId))) {
      errors.item = "Already has opening stock. Reverse it first.";
    }
    if (line.itemId) seen.add(line.itemId);

    const milli = line.quantity.trim().startsWith("-") ? null : toMilli(line.quantity);
    if (!line.quantity.trim()) {
      errors.quantity = "Enter the quantity.";
    } else if (milli === null) {
      errors.quantity = "Use a number with up to 3 decimal places.";
    } else if (milli === 0) {
      errors.quantity = "Must be more than zero.";
    }
    if (line.itemId && !line.unitId) errors.unit = "Choose a unit.";

    if (errors.item || errors.quantity || errors.unit) {
      result.lines[line.key] = errors;
    }
  }

  result.valid = !result.form && Object.keys(result.lines).length === 0;
  return result;
}
