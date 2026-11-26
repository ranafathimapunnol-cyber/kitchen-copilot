// Unit tests for search-as-you-type selection lists (Stage 7 S7-A). Run with: npm test

import { test } from "node:test";
import assert from "node:assert/strict";

import { edgeIndex, filterOptions, labelFor, normalise, stepIndex } from "../src/lib/searchSelect.ts";

const items = [
  { value: "1", label: "Rice" },
  { value: "2", label: "Basmati Rice" },
  { value: "3", label: "Toor Dal" },
  { value: "4", label: "Chicken" },
  { value: "5", label: "Rice Flour", detail: "Grains" },
  { value: "6", label: "Jeera (cumin)", detail: "Spices" },
  { value: "7", label: "Old Millet (inactive)", disabled: true },
];
const values = (list) => list.map((o) => o.value);

test("matching ignores letter case, accents and extra spaces", () => {
  assert.equal(normalise("  Crème   Brûlée "), "creme brulee");
  assert.deepEqual(values(filterOptions(items, "rICE")), ["1", "5", "2"]);
  assert.deepEqual(values(filterOptions(items, "  toor   dal ")), ["3"]);
  assert.deepEqual(values(filterOptions([{ value: "9", label: "Crème fraîche" }], "creme")), ["9"]);
});

test("labels starting with the query come first, then word starts, then the rest; order kept within each", () => {
  assert.deepEqual(values(filterOptions(items, "ri")), ["1", "5", "2"]);
  // "ice" is inside "Rice" (three labels) and inside the detail "Spices".
  assert.deepEqual(values(filterOptions(items, "ice")), ["1", "2", "5", "6"]);
});

test("every word must match, in any order, in the label or the detail", () => {
  assert.deepEqual(values(filterOptions(items, "flour rice")), ["5"]);
  assert.deepEqual(values(filterOptions(items, "spices")), ["6"]);
  assert.deepEqual(values(filterOptions(items, "cumin")), ["6"]);
  assert.deepEqual(values(filterOptions(items, "rice chicken")), []);
});

test("an empty query keeps every option in order; a limit caps the list", () => {
  assert.deepEqual(values(filterOptions(items, "")), ["1", "2", "3", "4", "5", "6", "7"]);
  assert.deepEqual(values(filterOptions(items, "   ")), values(items));
  assert.deepEqual(values(filterOptions(items, "", 2)), ["1", "2"]);
  assert.deepEqual(filterOptions([], "rice"), []);
});

test("keyboard steps skip disabled options and wrap around", () => {
  assert.equal(stepIndex(items, -1, 1), 0);
  assert.equal(stepIndex(items, -1, -1), 5); // the last enabled option
  assert.equal(stepIndex(items, 5, 1), 0); // wraps past the disabled last option
  assert.equal(stepIndex(items, 0, -1), 5);
  assert.equal(stepIndex(items, 2, 1), 3);
  assert.equal(stepIndex([], -1, 1), -1);
  assert.equal(stepIndex([{ value: "x", label: "x", disabled: true }], -1, 1), -1);
  assert.equal(edgeIndex(items, "first"), 0);
  assert.equal(edgeIndex(items, "last"), 5);
});

test("the chosen value shows its label; nothing chosen shows nothing", () => {
  assert.equal(labelFor(items, "4"), "Chicken");
  assert.equal(labelFor(items, ""), "");
  assert.equal(labelFor(items, "99"), "");
});
