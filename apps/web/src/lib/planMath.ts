/**
 * Meal planning figures (Stage 6: PLAN04 recalculation, PLAN05 gap), the
 * same arithmetic as the API (services/api/app/api/routes/planning.py,
 * compute()), so the form recalculates immediately while typing. The API
 * recalculates and stores the figures; these are only for display.
 *
 * Exact: quantities are whole thousandths and conversion factors whole
 * 10^-12, multiplied as BigInt (450 × 150 g is exactly 67,500 g = 67.5 kg).
 *
 * - required = headcount × quantity per person; count units (pieces) round
 *   up to whole pieces;
 * - in the item's standard unit = required × the explicit conversion factor
 *   (rounded half up to thousandths; whole pieces for count units);
 * - gap = max(0, required − current stock), current availability only.
 *
 * No imports: tested directly with node --test.
 */

const QUANTITY = /^\d{1,12}(\.\d{1,3})?$/;
const FACTOR = /^\d{1,12}(\.\d{1,12})?$/;
const HEADCOUNT = /^\d{1,6}$/;
const THOUSAND = BigInt(1000);
const FACTOR_SCALE = BigInt("1000000000000");
const HALF_FACTOR = BigInt("500000000000");
const ZERO = BigInt(0);

/** "67.5" → 67500n (thousandths); anything else → null. */
export function toMilli(text: string | null | undefined): bigint | null {
  const value = String(text ?? "").trim();
  if (!QUANTITY.test(value)) return null;
  const [whole, fraction = ""] = value.split(".");
  return BigInt(whole) * THOUSAND + BigInt(fraction.padEnd(3, "0"));
}

function scaledFactor(text: string | null | undefined): bigint | null {
  const value = String(text ?? "").trim();
  if (!FACTOR.test(value)) return null;
  const [whole, fraction = ""] = value.split(".");
  return BigInt(whole) * FACTOR_SCALE + BigInt(fraction.padEnd(12, "0"));
}

/** 67500n → "67.5" (no trailing zeros). */
export function milliText(value: bigint): string {
  const negative = value < ZERO;
  const abs = negative ? -value : value;
  const whole = abs / THOUSAND;
  const fraction = String(abs % THOUSAND).padStart(3, "0").replace(/0+$/, "");
  return `${negative ? "−" : ""}${whole}${fraction ? `.${fraction}` : ""}`;
}

export function headcountError(text: string): string | undefined {
  const value = text.trim();
  if (value === "") return "Enter the expected headcount.";
  if (!HEADCOUNT.test(value) || Number(value) < 1 || Number(value) > 100000) {
    return "Use a whole number from 1 to 100,000.";
  }
  return undefined;
}

export function perPersonError(text: string): string | undefined {
  const value = toMilli(text);
  if (value === null) return "Use a number with up to 3 decimals.";
  if (value <= ZERO) return "Must be more than 0.";
  return undefined;
}

/** Required quantity in the per-person unit (thousandths). */
export function required(headcount: number, perPerson: string, countUnit: boolean): { milli: bigint; roundedUp: boolean } | null {
  const per = toMilli(perPerson);
  if (per === null || !Number.isInteger(headcount) || headcount < 1) return null;
  const raw = BigInt(headcount) * per;
  if (!countUnit || raw % THOUSAND === ZERO) return { milli: raw, roundedUp: false };
  return { milli: (raw / THOUSAND + BigInt(1)) * THOUSAND, roundedUp: true };
}

/** A quantity converted with an explicit factor (thousandths, half up; whole units for count). */
export function convert(milli: bigint, factor: string | null | undefined, toCountUnit: boolean): bigint | null {
  const scaled = scaledFactor(factor);
  if (scaled === null) return null;
  const product = milli * scaled; // thousandths × 10^12
  if (toCountUnit) {
    const unit = THOUSAND * FACTOR_SCALE;
    const whole = product / unit + (product % unit === ZERO ? ZERO : BigInt(1));
    return whole * THOUSAND;
  }
  return (product + HALF_FACTOR) / FACTOR_SCALE;
}

export function gap(requiredBase: bigint, available: string | null | undefined): bigint {
  const stock = toMilli(String(available ?? "0").replace(/^-/, "")) ?? ZERO;
  const signed = String(available ?? "").trim().startsWith("-") ? -stock : stock;
  const difference = requiredBase - signed;
  return difference > ZERO ? difference : ZERO;
}

export type LineInput = {
  headcount: number;
  perPerson: string;
  unitDimension: string;
  factorToBase: string | null;
  baseDimension: string;
  available: string;
  display: { unit_symbol: string; factor: string } | null;
};

export type LineFigures = {
  required: string;
  roundedUp: boolean;
  display: string | null;
  base: string | null;
  gap: string | null;
};

/** Everything a plan line shows, or null while the inputs are incomplete. */
export function lineFigures(input: LineInput): LineFigures | null {
  const need = required(input.headcount, input.perPerson, input.unitDimension === "count");
  if (!need) return null;
  const base = input.factorToBase ? convert(need.milli, input.factorToBase, input.baseDimension === "count") : null;
  const display = input.display ? convert(need.milli, input.display.factor, false) : null;
  return {
    required: milliText(need.milli),
    roundedUp: need.roundedUp,
    display: display === null || !input.display ? null : `${milliText(display)} ${input.display.unit_symbol}`,
    base: base === null ? null : milliText(base),
    gap: base === null ? null : milliText(gap(base, input.available)),
  };
}

export type OverrideDraft = { quantity: string; unitId: string; reason: string };

/** A one-day override needs a quantity, a unit and a reason (PLAN06). */
export function overrideErrors(draft: OverrideDraft): Record<string, string> {
  const errors: Record<string, string> = {};
  const quantity = perPersonError(draft.quantity);
  if (quantity) errors.quantity = quantity;
  if (!draft.unitId) errors.unit = "Choose a unit.";
  if (draft.reason.trim().length < 3) errors.reason = "Give a reason (at least 3 characters).";
  return errors;
}
