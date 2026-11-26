// Unit tests for the bill screen's exact arithmetic and validation.
// Run with: npm test   (Node's built-in runner; no extra dependency)

import { test } from "node:test";
import assert from "node:assert/strict";

import {
  billTotals,
  fromScaled,
  hasErrors,
  lineTotal,
  toScaled,
  validateBillDraft,
} from "../src/lib/billMath.ts";

const line = (overrides = {}) => ({
  itemId: "1", quantity: "1", unitId: "10", unitRate: "1", remarks: "", ...overrides,
});
const draft = (overrides = {}) => ({
  supplierId: "5", invoiceNumber: "INV-1", purchaseDate: "2026-11-03",
  discount: "", extraCharges: "", remarks: "", lines: [line()], ...overrides,
});
const anyUnit = () => ["10"];

test("parses and formats scaled decimals without floating point", () => {
  assert.equal(toScaled("12.5", 2), BigInt(1250));
  assert.equal(toScaled("0.333", 3), BigInt(333));
  assert.equal(toScaled("1.005", 2), null);   // too many places
  assert.equal(toScaled("-1", 2), null);      // negatives are not amounts
  assert.equal(toScaled("1e3", 2), null);
  assert.equal(toScaled(" 7 ", 2), BigInt(700));
  assert.equal(fromScaled(BigInt(5), 2), "0.05");
  assert.equal(fromScaled(BigInt(-10050), 2), "-100.50");
});

test("line totals match the API: quantity × rate, half up to the paisa", () => {
  assert.equal(lineTotal("2.5", "45.50"), "113.75");
  assert.equal(lineTotal("0.333", "10.005"), "3.33");       // 3.331665
  assert.equal(lineTotal("1", "0.005"), "0.01");            // exactly half rounds up
  assert.equal(lineTotal("1", "0.0049"), "0.00");
  assert.equal(lineTotal("3", "0.1"), "0.30");              // 0.1 × 3 is exact here
  // (10^13 − 0.001) × (10^4 − 0.0001) = 10^17 − 10^9 − 10 + 10^-7:
  // exact to the last digit, where floating point would lose it.
  assert.equal(lineTotal("9999999999999.999", "9999.9999"),
               "99999998999999990.00");
  assert.equal(lineTotal("1.0001", "1"), null);
  assert.equal(lineTotal("1", "1.00001"), null);
});

test("bill totals: subtotal − discount + extra charges", () => {
  const totals = billTotals(draft({
    lines: [line({ quantity: "2.5", unitRate: "45.50" }),
            line({ quantity: "0.333", unitRate: "10.005" })],
    discount: "1.08", extraCharges: "2",
  }));
  assert.deepEqual(totals, {
    lineTotals: ["113.75", "3.33"], subtotal: "117.08", discount: "1.08",
    extraCharges: "2.00", grandTotal: "118.00", complete: true,
  });
  assert.equal(billTotals(draft({ lines: [line({ quantity: "" })] })).complete, false);
});

test("a complete draft has no errors", () => {
  assert.equal(hasErrors(validateBillDraft(draft(), anyUnit)), false);
});

test("validation mirrors the API's rules", () => {
  const errors = validateBillDraft(draft({
    supplierId: "", invoiceNumber: "   ", purchaseDate: "",
    discount: "1.001", extraCharges: "x",
    lines: [line({ itemId: "", quantity: "0", unitId: "", unitRate: "1.00001" })],
  }), anyUnit);

  assert.equal(errors.supplier, "Choose the supplier.");
  assert.equal(errors.invoiceNumber, "Enter the invoice number.");
  assert.equal(errors.purchaseDate, "Enter the bill date.");
  assert.equal(errors.discount, "Up to two decimal places.");
  assert.equal(errors.extraCharges, "Up to two decimal places.");
  assert.deepEqual(errors.lineErrors[0], {
    item: "Choose an item.", quantity: "Must be more than zero.",
    unit: "Choose a unit.", unitRate: "Up to four decimal places.",
  });
  assert.equal(hasErrors(errors), true);
});

test("a unit the item cannot be converted to is rejected", () => {
  const errors = validateBillDraft(draft({ lines: [line({ unitId: "99" })] }), anyUnit);
  assert.match(errors.lineErrors[0].unit, /cannot be converted/);
});

test("the discount cannot exceed the subtotal", () => {
  const errors = validateBillDraft(draft({
    lines: [line({ quantity: "1", unitRate: "10" })], discount: "10.01",
  }), anyUnit);
  assert.equal(errors.discount, "The discount cannot exceed the subtotal.");
  assert.equal(validateBillDraft(draft({
    lines: [line({ quantity: "1", unitRate: "10" })], discount: "10.00",
  }), anyUnit).discount, undefined);
});

test("a bill needs at least one line", () => {
  assert.equal(validateBillDraft(draft({ lines: [] }), anyUnit).lines,
               "Add at least one item line.");
});
