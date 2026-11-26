/**
 * Meal record entry rules (Stage 5, MEAL01–MEAL05). The API applies the same
 * rules; these give immediate feedback. Quantities are whole thousandths, so
 * reconciliation is exact (36.5 + 3.5 is exactly 40).
 *
 * No imports: tested directly with node --test.
 */

const QUANTITY = /^\d{1,12}(\.\d{1,3})?$/;
const COUNT = /^\d{1,6}$/;

/** "6.125" → 6125; anything that is not a plain quantity → null. */
export function milli(text: string): number | null {
  const value = text.trim();
  if (value === "" || !QUANTITY.test(value)) return null;
  const [whole, fraction = ""] = value.split(".");
  return Number(whole) * 1000 + Number(fraction.padEnd(3, "0"));
}

export function fromMilli(value: number): string {
  const whole = Math.trunc(value / 1000);
  const fraction = String(value % 1000).padStart(3, "0").replace(/0+$/, "");
  return fraction ? `${whole}.${fraction}` : String(whole);
}

/** A head count: a whole number, 0 or more. Blank → error. */
export function countError(text: string): string | undefined {
  const value = text.trim();
  if (value === "") return "Enter a number (0 if none).";
  if (!COUNT.test(value)) return "Use a whole number, 0 or more.";
  return undefined;
}

export type CountsCheck = { valid: boolean; fields: Record<string, string>; form?: string };

/**
 * Expected counts are required; actual counts are all three or none, and
 * only on or after the meal date. People counts are never quantities.
 */
export function checkCounts(
  input: { expected: [string, string, string]; actual: [string, string, string]; actualAllowed: boolean },
): CountsCheck {
  const result: CountsCheck = { valid: true, fields: {} };
  const names = ["students", "staff", "guests"];
  input.expected.forEach((value, i) => {
    const error = countError(value);
    if (error) result.fields[`expected_${names[i]}`] = error;
  });
  const given = input.actual.filter((v) => v.trim() !== "").length;
  if (given > 0 && !input.actualAllowed) result.form = "Actual people served can be recorded on or after the meal date.";
  else if (given > 0 && given < 3) result.form = "Record the actual students, staff and guests together (0 where none).";
  else if (given === 3)
    input.actual.forEach((value, i) => {
      const error = countError(value);
      if (error) result.fields[`actual_${names[i]}`] = error;
    });
  result.valid = !result.form && Object.keys(result.fields).length === 0;
  return result;
}

/** A prepared dish: a name, an output above zero (3 decimals) and a unit. */
export function checkDish(input: { name: string; output: string; unitId: string }): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!input.name.trim()) errors.name = "Give the dish a name.";
  const output = input.output.trim().startsWith("-") ? null : milli(input.output);
  if (!input.output.trim()) errors.output = "Enter the output quantity.";
  else if (output === null) errors.output = "Use a number with up to 3 decimal places.";
  else if (output === 0) errors.output = "Must be more than zero.";
  if (!input.unitId) errors.unit = "Choose a unit.";
  return errors;
}

export type LeftoverDraft = { classification: string; quantity: string; remarks: string };

export type DistributionCheck = {
  valid: boolean;
  distributed?: string;
  remaining?: string;
  balance?: string;
  leftovers: Record<string, string>;
  leftoverTotal?: string;
  classified: number;
};

/**
 * Available = distributed + remaining, exactly. Leftovers are either not
 * classified yet (all blank) or add up exactly to the remaining quantity,
 * each with remarks (at least 3 characters).
 */
export function checkDistribution(input: {
  available: string;
  distributed: string;
  remaining: string;
  leftovers: LeftoverDraft[];
  unit: string;
}): DistributionCheck {
  const result: DistributionCheck = { valid: true, leftovers: {}, classified: 0 };
  const available = milli(input.available) ?? 0;
  const distributed = milli(input.distributed);
  const remaining = milli(input.remaining);
  if (distributed === null) result.distributed = "Enter the distributed quantity (0 or more).";
  if (remaining === null) result.remaining = "Enter the remaining quantity (0 or more).";
  if (distributed !== null && remaining !== null && distributed + remaining !== available) {
    result.balance = `Available ${fromMilli(available)} ${input.unit} must equal distributed + remaining (now ${fromMilli(distributed + remaining)} ${input.unit}).`;
  }
  const used = input.leftovers.filter((l) => l.quantity.trim() || l.remarks.trim());
  for (const line of used) {
    const quantity = milli(line.quantity);
    if (quantity === null || quantity === 0) result.leftovers[line.classification] = "Enter a quantity above zero.";
    else if (line.remarks.trim().length < 3) result.leftovers[line.classification] = "Give remarks (at least 3 characters).";
    else result.classified += quantity;
  }
  if (used.length > 0 && remaining !== null && Object.keys(result.leftovers).length === 0 && result.classified !== remaining) {
    result.leftoverTotal = `The leftovers add up to ${fromMilli(result.classified)} ${input.unit} but ${fromMilli(remaining)} ${input.unit} remains.`;
  }
  if (used.length > 0 && remaining === 0) result.leftoverTotal = "Nothing remains, so there are no leftovers to classify.";
  result.valid = !result.distributed && !result.remaining && !result.balance && !result.leftoverTotal
    && Object.keys(result.leftovers).length === 0;
  return result;
}
