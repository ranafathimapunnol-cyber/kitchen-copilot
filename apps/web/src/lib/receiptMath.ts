/**
 * Receipt quantity rules for the entry form (PUR03). The API applies the
 * same rules; these give immediate feedback. Quantities are handled as
 * whole thousandths so that 0.1 + 0.2 is exactly 0.3.
 *
 * No imports: tested directly with node --test.
 */

/** Up to 12 whole digits and 3 decimal places (the API allows 3). */
const QUANTITY = /^\d{1,12}(\.\d{1,3})?$/;

/** "6.125" → 6125; "" → 0; anything else → null. */
export function toMilli(text: string): number | null {
  const value = text.trim();
  if (value === "") return 0;
  if (!QUANTITY.test(value)) return null;
  const [whole, fraction = ""] = value.split(".");
  return Number(whole) * 1000 + Number(fraction.padEnd(3, "0"));
}

/** 6125 → "6.125" (the API's exact form). */
export function fromMilli(milli: number): string {
  const whole = Math.floor(milli / 1000);
  const fraction = String(milli % 1000).padStart(3, "0");
  return `${whole}.${fraction}`;
}

/** "10.000" → "10", "5.500" → "5.5", for display. */
export function formatQuantity(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const milli = toMilli(String(value));
  if (milli === null) return String(value);
  return fromMilli(milli).replace(/\.?0+$/, "");
}

export type LineInput = {
  received: string;
  accepted: string;
  rejected: string;
};

export type LineCheck = {
  /** Why the line cannot be saved, or null. */
  error: string | null;
  /** Received is fully split into accepted and rejected (needed to accept). */
  complete: boolean;
  /** The line is part of the receipt (something was received). */
  included: boolean;
};

/**
 * One line against what is left to receive on the bill line. A line with
 * nothing received is left out of the receipt.
 */
export function checkLine(input: LineInput, remaining: string): LineCheck {
  const received = toMilli(input.received);
  const accepted = toMilli(input.accepted);
  const rejected = toMilli(input.rejected);
  const left = toMilli(remaining) ?? 0;

  if (received === null || accepted === null || rejected === null) {
    return { error: "Use numbers with up to 3 decimal places.", complete: false, included: true };
  }
  if (received === 0) {
    return accepted + rejected > 0
      ? { error: "Enter the received quantity first.", complete: false, included: true }
      : { error: null, complete: true, included: false };
  }
  if (accepted + rejected > received) {
    return { error: "Accepted and rejected cannot be more than received.", complete: false, included: true };
  }
  if (received > left) {
    return {
      error: left === 0 ? "Nothing is left to receive on this line." : `Only ${formatQuantity(fromMilli(left))} left to receive.`,
      complete: false,
      included: true,
    };
  }
  return { error: null, complete: accepted + rejected === received, included: true };
}

export type ReceiptCheck = {
  lines: LineCheck[];
  /** At least one line received and no line has an error. */
  canSave: boolean;
  /** Every included line is fully classified (needed before acceptance). */
  allClassified: boolean;
};

export function checkReceipt(
  lines: { input: LineInput; remaining: string }[],
): ReceiptCheck {
  const checked = lines.map(({ input, remaining }) => checkLine(input, remaining));
  const included = checked.filter((line) => line.included);
  return {
    lines: checked,
    canSave: included.length > 0 && checked.every((line) => line.error === null),
    allClassified: included.length > 0 && included.every((line) => line.complete),
  };
}

/** Rejected = received − accepted, when the user has not typed one. */
export function rejectedRemainder(received: string, accepted: string): string {
  const r = toMilli(received);
  const a = toMilli(accepted);
  if (r === null || a === null || a > r) return "";
  return formatQuantity(fromMilli(r - a));
}

/** What the form puts in "rejected" while the user has not overridden it:
 * nothing until an accepted quantity is entered, then the remainder. */
export function suggestedRejected(received: string, accepted: string): string {
  return accepted.trim() === "" ? "" : rejectedRemainder(received, accepted);
}

/**
 * Applies a change to received or accepted. Rejected keeps following the
 * suggestion as long as it still equals the previous suggestion (that is,
 * the user has not typed their own value).
 */
export function updateLineInput(current: LineInput, patch: Partial<LineInput>): LineInput {
  const next = { ...current, ...patch };
  const following = current.rejected === suggestedRejected(current.received, current.accepted);
  if (!("rejected" in patch) && following) {
    next.rejected = suggestedRejected(next.received, next.accepted);
  }
  return next;
}
