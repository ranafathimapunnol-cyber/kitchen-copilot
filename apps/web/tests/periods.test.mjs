// Unit tests for the report period presets.
// Run with: npm test   (Node's built-in runner; no extra dependency)

import { test } from "node:test";
import assert from "node:assert/strict";

import {
  financialYearToDate,
  isValidPeriod,
  monthToDate,
  previousMonth,
} from "../src/lib/periods.ts";

test("month to date starts on the 1st", () => {
  assert.deepEqual(monthToDate(new Date(2026, 10, 17)),
                   { from: "2026-11-01", to: "2026-11-17" });
});

test("previous month covers the whole month, across a year end", () => {
  assert.deepEqual(previousMonth(new Date(2026, 10, 17)),
                   { from: "2026-10-01", to: "2026-10-31" });
  assert.deepEqual(previousMonth(new Date(2027, 0, 5)),
                   { from: "2026-12-01", to: "2026-12-31" });
  assert.deepEqual(previousMonth(new Date(2028, 2, 1)),
                   { from: "2028-02-01", to: "2028-02-29" });  // leap year
});

test("the financial year starts on 1 April", () => {
  assert.deepEqual(financialYearToDate(new Date(2026, 10, 17)),
                   { from: "2026-04-01", to: "2026-11-17" });
  assert.deepEqual(financialYearToDate(new Date(2027, 1, 10)),
                   { from: "2026-04-01", to: "2027-02-10" });
});

test("a period must run forwards", () => {
  assert.equal(isValidPeriod({ from: "2026-11-01", to: "2026-11-01" }), true);
  assert.equal(isValidPeriod({ from: "2026-11-02", to: "2026-11-01" }), false);
  assert.equal(isValidPeriod({ from: "", to: "2026-11-01" }), false);
});
