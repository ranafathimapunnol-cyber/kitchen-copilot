// Unit tests for the meal planning figures (Stage 6). Run with: npm test

import { test } from "node:test";
import assert from "node:assert/strict";

import {
  convert,
  gap,
  headcountError,
  lineFigures,
  milliText,
  overrideErrors,
  perPersonError,
  required,
  toMilli,
} from "../src/lib/planMath.ts";

const KG = "0.001000000000"; // explicit g → kg record

test("AT05: biryani for 450 — rice 67.5 kg and chicken 90 kg", () => {
  const rice = lineFigures({ headcount: 450, perPerson: "150", unitDimension: "weight", factorToBase: KG,
    baseDimension: "weight", available: "20.000", display: { unit_symbol: "kg", factor: KG } });
  assert.deepEqual(rice, { required: "67500", roundedUp: false, display: "67.5 kg", base: "67.5", gap: "47.5" });
  const chicken = lineFigures({ headcount: 450, perPerson: "200", unitDimension: "weight", factorToBase: KG,
    baseDimension: "weight", available: "0.000", display: null });
  assert.equal(chicken.base, "90");
  assert.equal(chicken.gap, "90");
});

test("changing the headcount recalculates immediately", () => {
  const at = (headcount) => lineFigures({ headcount, perPerson: "150", unitDimension: "weight", factorToBase: KG,
    baseDimension: "weight", available: "20", display: null });
  assert.equal(at(500).base, "75");
  assert.equal(at(100).base, "15");
  assert.equal(at(100).gap, "0"); // max(0, 15 − 20)
});

test("count-based quantities round up to whole pieces", () => {
  assert.deepEqual(required(451, "0.5", true), { milli: 226000n, roundedUp: true });
  assert.deepEqual(required(450, "0.5", true), { milli: 225000n, roundedUp: false });
  assert.deepEqual(required(451, "0.5", false), { milli: 225500n, roundedUp: false });
  assert.equal(convert(1500n, "1", true), 2000n);
});

test("arithmetic is exact for large headcounts and small portions", () => {
  assert.equal(milliText(required(100000, "999999.999", false).milli), "99999999900");
  assert.equal(milliText(convert(required(3, "0.333", false).milli, KG, false)), "0.001");
  assert.equal(milliText(convert(toMilli("0.4"), "0.001000000000", false)), "0"); // 0.0004 kg rounds to 0
  assert.equal(convert(toMilli("1"), "not a factor", false), null);
});

test("the gap is never negative and uses current stock as given", () => {
  assert.equal(gap(15000n, "20"), 0n);
  assert.equal(gap(67500n, "20.000"), 47500n);
  assert.equal(gap(1000n, "-2"), 3000n);
});

test("headcount, per-person quantities and overrides are validated", () => {
  assert.equal(headcountError("450"), undefined);
  assert.equal(headcountError("0"), "Use a whole number from 1 to 100,000.");
  assert.equal(headcountError("12.5"), "Use a whole number from 1 to 100,000.");
  assert.equal(headcountError(""), "Enter the expected headcount.");
  assert.equal(perPersonError("0.150"), undefined);
  assert.equal(perPersonError("0"), "Must be more than 0.");
  assert.equal(perPersonError("0.1505"), "Use a number with up to 3 decimals.");
  assert.deepEqual(overrideErrors({ quantity: "0.2", unitId: "3", reason: "Exam week" }), {});
  assert.deepEqual(Object.keys(overrideErrors({ quantity: "", unitId: "", reason: " " })).sort(), ["quantity", "reason", "unit"]);
  assert.equal(lineFigures({ headcount: 0, perPerson: "1", unitDimension: "weight", factorToBase: "1", baseDimension: "weight",
    available: "0", display: null }), null);
});
