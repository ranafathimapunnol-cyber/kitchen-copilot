/**
 * Kitchen issue and unused-return entry rules (Stage 4, slice 4b). The API
 * applies the same rules and re-checks stock on confirmation; these give
 * immediate feedback. Quantities are whole thousandths, so 0.1 + 0.2 is
 * exactly 0.3.
 *
 * No imports: tested directly with node --test.
 */

const QUANTITY = /^\d{1,12}(\.\d{1,3})?$/;

/** "6.125" → 6125; anything that is not a plain quantity → null. */
export function milli(text: string): number | null {
  const value = text.trim();
  if (value === "" || !QUANTITY.test(value)) return null;
  const [whole, fraction = ""] = value.split(".");
  return Number(whole) * 1000 + Number(fraction.padEnd(3, "0"));
}

export type IssueLineDraft = {
  key: string;
  itemId: string;
  quantity: string;
  unitId: string;
  remarks: string;
};

export type LineErrors = { item?: string; quantity?: string; unit?: string };

export type FormCheck = {
  valid: boolean;
  fields: { date?: string; session?: string; menu?: string; lines?: string };
  lines: Record<string, LineErrors>;
};

function quantityError(text: string): string | undefined {
  if (!text.trim()) return "Enter the quantity.";
  const value = text.trim().startsWith("-") ? null : milli(text);
  if (value === null) return "Use a number with up to 3 decimal places.";
  if (value === 0) return "Must be more than zero.";
  return undefined;
}

/**
 * An issue: date today or earlier; a meal session and a menu of that
 * session; at least one line; each line an item (once), a unit and a
 * quantity above zero. Blank lines are ignored. Stock is not checked here:
 * a draft may be saved when stock is short; confirmation is refused then.
 */
export function checkIssue(
  input: { date: string; sessionId: string; menuId: string; menuSessionId: string | null; lines: IssueLineDraft[] },
  today: string,
): FormCheck {
  const result: FormCheck = { valid: true, fields: {}, lines: {} };
  if (!input.date) result.fields.date = "Choose the issue date.";
  else if (input.date > today) result.fields.date = "An issue cannot be dated in the future.";
  if (!input.sessionId) result.fields.session = "Choose the meal session.";
  if (!input.menuId) result.fields.menu = "Choose the menu.";
  else if (input.sessionId && input.menuSessionId !== input.sessionId)
    result.fields.menu = "This menu belongs to another meal session.";

  const used = input.lines.filter((line) => line.itemId || line.quantity.trim());
  if (used.length === 0) result.fields.lines = "Add at least one item.";
  const seen = new Set<string>();
  for (const line of used) {
    const errors: LineErrors = {};
    if (!line.itemId) errors.item = "Choose an item.";
    else if (seen.has(line.itemId)) errors.item = "This item is already in the issue.";
    if (line.itemId) seen.add(line.itemId);
    const quantity = quantityError(line.quantity);
    if (quantity) errors.quantity = quantity;
    if (line.itemId && !line.unitId) errors.unit = "Choose a unit.";
    if (errors.item || errors.quantity || errors.unit) result.lines[line.key] = errors;
  }
  result.valid = Object.keys(result.fields).length === 0 && Object.keys(result.lines).length === 0;
  return result;
}

export type ReturnLineDraft = {
  key: string;
  quantity: string;
  /** Conversion of the chosen unit to the item's standard unit, e.g. 0.001 for g → kg. */
  factor: number;
  /** What can still be returned, in the standard unit ("2.500"). */
  returnable: string;
};

/**
 * A return: date today or earlier and not before its issue; at least one
 * quantity; each no more than the line can still give back (converted to
 * the standard unit and rounded to thousandths as the API does).
 */
export function checkReturn(
  input: { date: string; issueDate: string; lines: ReturnLineDraft[] },
  today: string,
): { valid: boolean; date?: string; form?: string; lines: Record<string, string> } {
  const result: { valid: boolean; date?: string; form?: string; lines: Record<string, string> } = { valid: true, lines: {} };
  if (!input.date) result.date = "Choose the return date.";
  else if (input.date > today) result.date = "A return cannot be dated in the future.";
  else if (input.date < input.issueDate) result.date = "A return cannot be dated before its issue.";

  const used = input.lines.filter((line) => line.quantity.trim());
  if (used.length === 0) result.form = "Enter at least one quantity to return.";
  for (const line of used) {
    const error = quantityError(line.quantity);
    if (error) {
      result.lines[line.key] = error;
      continue;
    }
    const standard = Math.round((milli(line.quantity) as number) * line.factor);
    const left = milli(line.returnable) ?? 0;
    if (standard > left) result.lines[line.key] = `No more than ${line.returnable.replace(/\.?0+$/, "")} can be returned.`;
  }
  result.valid = !result.date && !result.form && Object.keys(result.lines).length === 0;
  return result;
}
