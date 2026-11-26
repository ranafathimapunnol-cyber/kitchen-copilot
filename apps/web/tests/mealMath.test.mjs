// Unit tests for the meal record entry rules (Stage 5). Run with: npm test

import { test } from "node:test";
import assert from "node:assert/strict";

import { checkCounts, checkDish, checkDistribution, countError, fromMilli, milli } from "../src/lib/mealMath.ts";

const dist = (overrides = {}) => ({ available: "40", distributed: "36.5", remaining: "3.5", leftovers: [], unit: "kg", ...overrides });
const left = (classification, quantity, remarks = "Plate waste") => ({ classification, quantity, remarks });

test("quantities are exact thousandths", () => {
  assert.equal(milli("36.5") + milli("3.5"), milli("40"));
  assert.equal(milli("0.1") + milli("0.2"), milli("0.3"));
  assert.equal(milli("1.0005"), null);
  assert.equal(fromMilli(3500), "3.5");
  assert.equal(fromMilli(40000), "40");
});

test("head counts are whole numbers, never quantities", () => {
  assert.equal(countError("120"), undefined);
  assert.equal(countError("0"), undefined);
  assert.equal(countError(""), "Enter a number (0 if none).");
  assert.equal(countError("12.5"), "Use a whole number, 0 or more.");
  assert.equal(countError("-1"), "Use a whole number, 0 or more.");
});

test("actual counts: all three or none, only on or after the meal date", () => {
  const base = { expected: ["100", "5", "0"], actual: ["", "", ""], actualAllowed: true };
  assert.equal(checkCounts(base).valid, true);
  assert.equal(checkCounts({ ...base, actual: ["90", "", ""] }).form, "Record the actual students, staff and guests together (0 where none).");
  assert.equal(checkCounts({ ...base, actual: ["90", "5", "0"], actualAllowed: false }).form,
    "Actual people served can be recorded on or after the meal date.");
  assert.equal(checkCounts({ ...base, actual: ["90", "5", "0"] }).valid, true);
  assert.equal(checkCounts({ ...base, expected: ["", "5", "0"] }).fields.expected_students, "Enter a number (0 if none).");
});

test("a dish needs a name, an output above zero and a unit", () => {
  assert.deepEqual(checkDish({ name: "Veg biryani", output: "42.5", unitId: "1" }), {});
  assert.deepEqual(checkDish({ name: " ", output: "0", unitId: "" }),
    { name: "Give the dish a name.", output: "Must be more than zero.", unit: "Choose a unit." });
});

test("available must equal distributed + remaining exactly", () => {
  assert.equal(checkDistribution(dist()).valid, true);
  assert.equal(checkDistribution(dist({ remaining: "3" })).balance,
    "Available 40 kg must equal distributed + remaining (now 39.5 kg).");
});

test("leftovers: none yet, or exactly the remaining quantity, each with remarks", () => {
  assert.equal(checkDistribution(dist({ leftovers: [left("RETAINED", "2", "Kept"), left("WASTED", "1.5")] })).valid, true);
  assert.equal(checkDistribution(dist({ leftovers: [left("WASTED", "3")] })).leftoverTotal,
    "The leftovers add up to 3 kg but 3.5 kg remains.");
  assert.equal(checkDistribution(dist({ leftovers: [left("WASTED", "3.5", "x")] })).leftovers.WASTED,
    "Give remarks (at least 3 characters).");
  assert.equal(checkDistribution(dist({ distributed: "40", remaining: "0", leftovers: [left("WASTED", "1")] })).leftoverTotal,
    "Nothing remains, so there are no leftovers to classify.");
});
