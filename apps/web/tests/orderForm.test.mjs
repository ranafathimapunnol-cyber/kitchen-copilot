// Unit tests for the purchase-order form rules and bill pre-filling (Stage 3).
// Run with: npm test   (Node's built-in runner; no extra dependency)

import { test } from "node:test";
import assert from "node:assert/strict";

import {
  billLinesFromOrder,
  exceedsOrder,
  hasOrderErrors,
  orderPayload,
  trimQuantity,
  validQuantity,
  validateOrderDraft,
} from "../src/lib/orderForm.ts";

const line = (patch = {}) => ({ itemId: "1", quantity: "50", unitId: "10", remarks: "", ...patch });
const draft = (patch = {}) => ({
  supplierId: "3", orderDate: "2026-11-10", expectedDate: "", remarks: "", lines: [line()], ...patch,
});
const units = () => ["10", "11"];
const TODAY = "2026-11-18";

test("a complete draft has no errors", () => {
  assert.equal(hasOrderErrors(validateOrderDraft(draft(), units, TODAY)), false);
});

test("supplier and dates are checked", () => {
  const errors = validateOrderDraft(draft({ supplierId: "", orderDate: "2026-11-19" }), units, TODAY);
  assert.match(errors.supplier, /supplier/);
  assert.match(errors.orderDate, /future/);
  const early = validateOrderDraft(draft({ expectedDate: "2026-11-09" }), units, TODAY);
  assert.match(early.expectedDate, /before the order date/);
  assert.equal(validateOrderDraft(draft({ expectedDate: "2026-11-10" }), units, TODAY).expectedDate, undefined);
});

test("each item once, a positive quantity and an allowed unit", () => {
  const errors = validateOrderDraft(draft({ lines: [
    line(), line({ quantity: "2" }), line({ itemId: "2", quantity: "0", unitId: "99" }), line({ itemId: "", unitId: "" }),
  ] }), units, TODAY);
  assert.match(errors.lineErrors[1].item, /already on the order/);
  assert.match(errors.lineErrors[2].quantity, /above 0/);
  assert.match(errors.lineErrors[2].unit, /cannot be used/);
  assert.match(errors.lineErrors[3].item, /Choose an item/);
  assert.match(errors.lineErrors[3].unit, /Choose a unit/);
  assert.match(validateOrderDraft(draft({ lines: [] }), units, TODAY).lines, /at least one/);
});

test("quantities have up to 3 decimal places and are above zero", () => {
  for (const ok of ["1", "0.001", "12.5", " 7 "]) assert.equal(validQuantity(ok), true, ok);
  for (const bad of ["0", "0.000", "-1", "1.2345", "abc", "", "1e3"]) assert.equal(validQuantity(bad), false, bad);
});

test("bill lines are filled from what is left to bill, linked to the order lines", () => {
  const lines = billLinesFromOrder([
    { id: 7, item_id: 1, unit_id: 10, left_to_bill: "20.000" },
    { id: 8, item_id: 2, unit_id: 11, left_to_bill: "0.000" },
    { id: 9, item_id: 3, unit_id: 10, left_to_bill: "2.500" },
  ]);
  assert.deepEqual(lines, [
    { itemId: "1", quantity: "20", unitId: "10", unitRate: "", remarks: "", orderLineId: 7 },
    { itemId: "3", quantity: "2.5", unitId: "10", unitRate: "", remarks: "", orderLineId: 9 },
  ]);
});

test("billing more than is left is detected only in the order line's unit", () => {
  const orderLine = { unit_id: 10, left_to_bill: "20.000" };
  assert.equal(exceedsOrder("20", "10", orderLine), false);
  assert.equal(exceedsOrder("20.001", "10", orderLine), true);
  assert.equal(exceedsOrder("25000", "11", orderLine), false, "other unit: shown on the order instead");
  assert.equal(exceedsOrder("abc", "10", orderLine), false);
  assert.equal(exceedsOrder("5", "10", undefined), false);
});

test("display trims trailing zeros", () => {
  assert.equal(trimQuantity("50.000"), "50");
  assert.equal(trimQuantity("12.500"), "12.5");
  assert.equal(trimQuantity("7"), "7");
});

test("the request body carries ids as numbers and blanks as null", () => {
  assert.deepEqual(orderPayload(draft({ remarks: "  ", lines: [line({ quantity: " 5 ", remarks: "Fine grade" })] })), {
    supplier_id: 3, order_date: "2026-11-10", expected_date: null, remarks: null,
    items: [{ item_id: 1, quantity: "5", unit_id: 10, remarks: "Fine grade" }],
  });
});
