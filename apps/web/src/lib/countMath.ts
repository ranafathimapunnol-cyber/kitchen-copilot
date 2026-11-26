/**
 * Physical count entry rules (Stage 4, slice 4c). The API applies the same
 * rules; these give immediate feedback. The count sheet lists every item;
 * a blank quantity means "not counted" and is left out, while 0 means
 * "counted, none found".
 *
 * No imports: tested directly with node --test.
 */

const QUANTITY = /^\d{1,12}(\.\d{1,3})?$/;

export type CountLineDraft = {
  key: string;
  itemId: string;
  quantity: string;
  unitId: string;
  remarks: string;
};

export type CountCheck = {
  valid: boolean;
  reason?: string;
  form?: string;
  lines: Record<string, { quantity?: string; unit?: string }>;
  counted: CountLineDraft[];
};

/** A counted quantity: blank (not counted), or zero or more with up to 3 decimals. */
export function quantityProblem(text: string): string | undefined {
  const value = text.trim();
  if (value === "") return undefined;
  if (value.startsWith("-")) return "A count cannot be negative.";
  if (!QUANTITY.test(value)) return "Use a number with up to 3 decimal places.";
  return undefined;
}

export function checkCount(input: { reason: string; lines: CountLineDraft[] }, maxLines: number): CountCheck {
  const result: CountCheck = { valid: true, lines: {}, counted: [] };
  const reason = input.reason.trim();
  if (!reason) result.reason = "Give the reason for the count.";
  else if (reason.length < 3) result.reason = "At least 3 characters.";

  const seen = new Set<string>();
  for (const line of input.lines) {
    if (!line.quantity.trim()) continue;
    const errors: { quantity?: string; unit?: string } = {};
    const problem = quantityProblem(line.quantity);
    if (problem) errors.quantity = problem;
    if (!line.unitId) errors.unit = "Choose a unit.";
    if (seen.has(line.itemId)) errors.quantity = "This item is already counted.";
    seen.add(line.itemId);
    if (errors.quantity || errors.unit) result.lines[line.key] = errors;
    result.counted.push(line);
  }
  if (result.counted.length === 0) result.form = "Enter the quantity found for at least one item.";
  else if (result.counted.length > maxLines) result.form = `At most ${maxLines} items per count; save this one and start another.`;

  result.valid = !result.reason && !result.form && Object.keys(result.lines).length === 0;
  return result;
}

/** "-1.500" → "−1.5", "2.000" → "+2"; "0.000" → "0". */
export function signedDifference(value: string): string {
  const number = Number(value);
  if (!number) return "0";
  const text = value.replace(/^-/, "").replace(/\.?0+$/, "");
  return `${number > 0 ? "+" : "−"}${text}`;
}
