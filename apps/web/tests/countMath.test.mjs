// Unit tests for the physical count entry rules (Stage 4, slice 4c).
// Run with: npm test

import { test } from "node:test";
import assert from "node:assert/strict";

import { checkCount, quantityProblem, signedDifference } from "../src/lib/countMath.ts";

const line = (key, itemId, quantity, unitId = "1") => ({ key, itemId, quantity, unitId, remarks: "" });

test("blank means not counted; zero means counted and none found", () => {
  const check = checkCount({ reason: "Monthly check", lines: [line("a", "1", ""), line("b", "2", "0")] }, 500);
  assert.equal(check.valid, true);
  assert.deepEqual(check.counted.map((l) => l.itemId), ["2"]);
});

test("at least one counted item and a reason", () => {
  assert.equal(checkCount({ reason: "Monthly check", lines: [line("a", "1", "")] }, 500).form,
    "Enter the quantity found for at least one item.");
  assert.equal(checkCount({ reason: "", lines: [line("a", "1", "2")] }, 500).reason, "Give the reason for the count.");
  assert.equal(checkCount({ reason: " ok ", lines: [line("a", "1", "2")] }, 500).reason, "At least 3 characters.");
});

test("quantities: zero or more, up to three decimals", () => {
  assert.equal(quantityProblem("12.125"), undefined);
  assert.equal(quantityProblem("0"), undefined);
  assert.equal(quantityProblem("-1"), "A count cannot be negative.");
  assert.equal(quantityProblem("1.0005"), "Use a number with up to 3 decimal places.");
  assert.equal(quantityProblem("abc"), "Use a number with up to 3 decimal places.");
  const check = checkCount({ reason: "Monthly check", lines: [line("a", "1", "1.0005"), line("b", "2", "3", "")] }, 500);
  assert.deepEqual(check.lines, { a: { quantity: "Use a number with up to 3 decimal places." }, b: { unit: "Choose a unit." } });
  assert.equal(check.valid, false);
});

test("each item once, and no more lines than the API accepts", () => {
  const twice = checkCount({ reason: "Monthly check", lines: [line("a", "1", "2"), line("b", "1", "3")] }, 500);
  assert.equal(twice.lines.b.quantity, "This item is already counted.");
  const many = checkCount({ reason: "Monthly check", lines: [line("a", "1", "2"), line("b", "2", "3")] }, 1);
  assert.equal(many.form, "At most 1 items per count; save this one and start another.");
});

test("differences are shown with their sign", () => {
  assert.equal(signedDifference("-1.500"), "−1.5");
  assert.equal(signedDifference("2.000"), "+2");
  assert.equal(signedDifference("0.000"), "0");
  assert.equal(signedDifference("10.250"), "+10.25");
});
