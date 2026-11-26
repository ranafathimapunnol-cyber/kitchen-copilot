/**
 * Purchase-order form rules (Stage 3) and filling bill lines from an order.
 * The API applies the same rules; these give immediate feedback.
 *
 * No imports: tested directly with node --test.
 */

export type OrderLineDraft = {
  itemId: string;
  quantity: string;
  unitId: string;
  remarks: string;
};

export type OrderDraft = {
  supplierId: string;
  orderDate: string;
  expectedDate: string;
  remarks: string;
  lines: OrderLineDraft[];
};

export type OrderLineErrors = Partial<Record<"item" | "quantity" | "unit", string>>;

export type OrderErrors = {
  supplier?: string;
  orderDate?: string;
  expectedDate?: string;
  lines?: string;
  lineErrors: OrderLineErrors[];
};

/** Up to 12 whole digits and 3 decimal places, more than zero. */
const QUANTITY = /^\d{1,12}(\.\d{1,3})?$/;

export function validQuantity(text: string): boolean {
  const value = text.trim();
  return QUANTITY.test(value) && Number(value) > 0;
}

/**
 * @param unitsFor the unit ids (as strings) the line's item may use
 * @param today    YYYY-MM-DD in the campus/browser calendar
 */
export function validateOrderDraft(
  draft: OrderDraft,
  unitsFor: (line: OrderLineDraft) => string[],
  today: string,
): OrderErrors {
  const errors: OrderErrors = { lineErrors: draft.lines.map(() => ({})) };
  if (!draft.supplierId) errors.supplier = "Choose a supplier.";
  if (!draft.orderDate) errors.orderDate = "Enter the order date.";
  else if (draft.orderDate > today) errors.orderDate = "The order date cannot be in the future.";
  if (draft.expectedDate && draft.orderDate && draft.expectedDate < draft.orderDate) {
    errors.expectedDate = "Cannot be before the order date.";
  }
  if (draft.lines.length === 0) errors.lines = "Add at least one item.";

  const seen = new Map<string, number>();
  draft.lines.forEach((line, index) => {
    const lineErrors = errors.lineErrors[index];
    if (!line.itemId) {
      lineErrors.item = "Choose an item.";
    } else if (seen.has(line.itemId)) {
      lineErrors.item = "This item is already on the order.";
    } else {
      seen.set(line.itemId, index);
    }
    if (!validQuantity(line.quantity)) {
      lineErrors.quantity = "Enter a quantity above 0 with up to 3 decimal places.";
    }
    if (!line.unitId) lineErrors.unit = "Choose a unit.";
    else if (line.itemId && !unitsFor(line).includes(line.unitId)) {
      lineErrors.unit = "This unit cannot be used for the item.";
    }
  });
  return errors;
}

/** The API request body for a draft (create or edit). */
export function orderPayload(draft: OrderDraft) {
  return {
    supplier_id: Number(draft.supplierId),
    order_date: draft.orderDate,
    expected_date: draft.expectedDate || null,
    remarks: draft.remarks.trim() || null,
    items: draft.lines.map((line) => ({
      item_id: Number(line.itemId),
      quantity: line.quantity.trim(),
      unit_id: Number(line.unitId),
      remarks: line.remarks.trim() || null,
    })),
  };
}

export function hasOrderErrors(errors: OrderErrors): boolean {
  return Boolean(
    errors.supplier || errors.orderDate || errors.expectedDate || errors.lines ||
      errors.lineErrors.some((line) => Object.keys(line).length > 0),
  );
}

/** "50.000" → "50", "12.500" → "12.5" (display only). */
export function trimQuantity(value: string): string {
  return value.includes(".") ? value.replace(/\.?0+$/, "") : value;
}

export type BillableOrderLine = {
  id: number;
  item_id: number;
  unit_id: number;
  left_to_bill: string;
};

export type LinkedBillLine = {
  itemId: string;
  quantity: string;
  unitId: string;
  unitRate: string;
  remarks: string;
  orderLineId: number;
};

/**
 * Bill lines pre-filled from a placed order: one per order line with
 * something left to bill, in the order line's unit, linked to it. Rates are
 * left for the user to copy from the supplier's bill.
 */
export function billLinesFromOrder(lines: BillableOrderLine[]): LinkedBillLine[] {
  return lines
    .filter((line) => Number(line.left_to_bill) > 0)
    .map((line) => ({
      itemId: String(line.item_id),
      quantity: trimQuantity(line.left_to_bill),
      unitId: String(line.unit_id),
      unitRate: "",
      remarks: "",
      orderLineId: line.id,
    }));
}

/**
 * Whether a linked bill line bills more than is left on its order line.
 * Only compared when the bill line uses the order line's unit; the order
 * itself shows any excess after saving. Never blocks saving.
 */
export function exceedsOrder(
  quantity: string,
  unitId: string,
  orderLine: { unit_id: number; left_to_bill: string } | undefined,
): boolean {
  if (!orderLine || unitId !== String(orderLine.unit_id) || !validQuantity(quantity)) return false;
  const toMilli = (text: string) => {
    const [whole, fraction = ""] = text.trim().split(".");
    return Number(whole) * 1000 + Number(fraction.padEnd(3, "0").slice(0, 3));
  };
  return toMilli(quantity) > toMilli(orderLine.left_to_bill);
}
