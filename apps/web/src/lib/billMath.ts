/**
 * Exact decimal arithmetic and validation for supplier bill entry (PUR02).
 *
 * Amounts are handled as scaled integers (BigInt), never as floating-point
 * numbers, and are rounded the same way as the API: line total =
 * quantity × unit rate, rounded half up to the paisa. The API recalculates
 * and is authoritative; these figures let the screen show the same totals
 * before saving.
 *
 * This module has no imports, so `node --test` can run its tests directly.
 */

export const QUANTITY_SCALE = 3;
export const RATE_SCALE = 4;
export const MONEY_SCALE = 2;

const TEN = BigInt(10);
const ZERO = BigInt(0);

function pow10(exponent: number): bigint {
  let result = BigInt(1);
  for (let i = 0; i < exponent; i++) result *= TEN;
  return result;
}

/** "12.5" at scale 2 → 1250n. Null when not a plain non-negative decimal
 * or when it has more decimal places than `scale`. */
export function toScaled(value: string, scale: number): bigint | null {
  const match = /^(\d{1,16})(?:\.(\d+))?$/.exec(value.trim());
  if (!match) return null;
  const whole = match[1];
  const fraction = match[2] ?? "";
  if (fraction.length > scale) return null;
  return BigInt(whole + fraction.padEnd(scale, "0"));
}

/** 1250n at scale 2 → "12.50". */
export function fromScaled(units: bigint, scale: number): string {
  const negative = units < ZERO;
  const digits = (negative ? -units : units).toString().padStart(scale + 1, "0");
  const text = scale
    ? `${digits.slice(0, digits.length - scale)}.${digits.slice(digits.length - scale)}`
    : digits;
  return negative ? `-${text}` : text;
}

/** Divide a non-negative scaled value, rounding half up. */
function roundHalfUp(value: bigint, dropDigits: number): bigint {
  const divisor = pow10(dropDigits);
  return (value + divisor / BigInt(2)) / divisor;
}

/** quantity × unit rate, rounded half up to two places, as the API does. */
export function lineTotal(quantity: string, unitRate: string): string | null {
  const q = toScaled(quantity, QUANTITY_SCALE);
  const r = toScaled(unitRate, RATE_SCALE);
  if (q === null || r === null) return null;
  return fromScaled(
    roundHalfUp(q * r, QUANTITY_SCALE + RATE_SCALE - MONEY_SCALE),
    MONEY_SCALE
  );
}

export type DraftLine = {
  itemId: string;
  quantity: string;
  unitId: string;
  unitRate: string;
  remarks: string;
  /** The purchase-order line this bill line bills for, if any (Stage 3). */
  orderLineId?: number | null;
};

export type BillDraft = {
  supplierId: string;
  invoiceNumber: string;
  purchaseDate: string;
  discount: string;
  extraCharges: string;
  remarks: string;
  lines: DraftLine[];
};

export type BillTotals = {
  lineTotals: (string | null)[];
  subtotal: string;
  discount: string;
  extraCharges: string;
  grandTotal: string;
  /** False while any figure is missing or malformed. */
  complete: boolean;
};

/** Totals the screen shows, using the API's rules: subtotal = sum of line
 * totals; grand total = subtotal − discount + extra charges. */
export function billTotals(draft: BillDraft): BillTotals {
  const lineTotals = draft.lines.map((line) => lineTotal(line.quantity, line.unitRate));
  const subtotal = lineTotals.reduce<bigint>(
    (sum, total) => sum + (total === null ? ZERO : (toScaled(total, MONEY_SCALE) ?? ZERO)),
    ZERO
  );
  const discount = toScaled(draft.discount || "0", MONEY_SCALE);
  const extra = toScaled(draft.extraCharges || "0", MONEY_SCALE);

  return {
    lineTotals,
    subtotal: fromScaled(subtotal, MONEY_SCALE),
    discount: fromScaled(discount ?? ZERO, MONEY_SCALE),
    extraCharges: fromScaled(extra ?? ZERO, MONEY_SCALE),
    grandTotal: fromScaled(subtotal - (discount ?? ZERO) + (extra ?? ZERO), MONEY_SCALE),
    complete:
      lineTotals.length > 0 &&
      lineTotals.every((total) => total !== null) &&
      discount !== null &&
      extra !== null,
  };
}

export type LineErrors = Partial<Record<"item" | "quantity" | "unit" | "unitRate" | "remarks", string>>;

export type DraftErrors = {
  supplier?: string;
  invoiceNumber?: string;
  purchaseDate?: string;
  discount?: string;
  extraCharges?: string;
  remarks?: string;
  lines?: string;
  lineErrors: LineErrors[];
};

/** Mirrors the API's checks so mistakes show before saving. `allowedUnits`
 * gives, per line, the unit ids that line's item may be bought in. */
export function validateBillDraft(
  draft: BillDraft,
  allowedUnits: (line: DraftLine) => string[]
): DraftErrors {
  const errors: DraftErrors = { lineErrors: draft.lines.map(() => ({})) };

  if (!draft.supplierId) errors.supplier = "Choose the supplier.";

  const invoice = draft.invoiceNumber.trim();
  if (!invoice) errors.invoiceNumber = "Enter the invoice number.";
  else if (invoice.length > 100) errors.invoiceNumber = "Use at most 100 characters.";

  if (!/^\d{4}-\d{2}-\d{2}$/.test(draft.purchaseDate)) {
    errors.purchaseDate = "Enter the bill date.";
  }

  if (draft.lines.length === 0) errors.lines = "Add at least one item line.";

  draft.lines.forEach((line, index) => {
    const lineErrors = errors.lineErrors[index];
    if (!line.itemId) lineErrors.item = "Choose an item.";

    const quantity = toScaled(line.quantity, QUANTITY_SCALE);
    if (quantity === null) {
      lineErrors.quantity = "Up to three decimal places.";
    } else if (quantity <= ZERO) {
      lineErrors.quantity = "Must be more than zero.";
    }

    if (!line.unitId) lineErrors.unit = "Choose a unit.";
    else if (line.itemId && !allowedUnits(line).includes(line.unitId)) {
      lineErrors.unit = "This unit cannot be converted to the item's standard unit.";
    }

    if (toScaled(line.unitRate, RATE_SCALE) === null) {
      lineErrors.unitRate = "Up to four decimal places.";
    }

    if (line.remarks.length > 500) lineErrors.remarks = "Use at most 500 characters.";
  });

  const discount = toScaled(draft.discount || "0", MONEY_SCALE);
  const extra = toScaled(draft.extraCharges || "0", MONEY_SCALE);
  if (discount === null) errors.discount = "Up to two decimal places.";
  if (extra === null) errors.extraCharges = "Up to two decimal places.";

  const totals = billTotals(draft);
  if (discount !== null && totals.complete) {
    const subtotal = toScaled(totals.subtotal, MONEY_SCALE) ?? ZERO;
    if (discount > subtotal) errors.discount = "The discount cannot exceed the subtotal.";
  }

  return errors;
}

export function hasErrors(errors: DraftErrors): boolean {
  const { lineErrors, ...rest } = errors;
  return (
    Object.values(rest).some(Boolean) ||
    lineErrors.some((line) => Object.values(line).some(Boolean))
  );
}
