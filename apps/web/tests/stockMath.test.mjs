// Unit tests for the stock ledger display and opening-stock entry rules
// (Stage 4, slice 4a). Run with: npm test

import { test } from "node:test";
import assert from "node:assert/strict";

import {
  checkOpening,
  levelRatio,
  plainQuantity,
  signedQuantity,
  stockState,
} from "../src/lib/stockMath.ts";

test("quantities drop trailing zeros and keep exact thousandths", () => {
  assert.equal(plainQuantity("40.000"), "40");
  assert.equal(plainQuantity("12.500"), "12.5");
  assert.equal(plainQuantity("0.125"), "0.125");
  assert.equal(plainQuantity("-8.000"), "−8");
  assert.equal(plainQuantity("0.000"), "0");
  assert.equal(plainQuantity(null), "—");
});

test("movement quantities carry their direction", () => {
  assert.equal(signedQuantity(1, "40.000"), "+40");
  assert.equal(signedQuantity(-1, "40.000"), "−40");
  assert.equal(signedQuantity(-1, "-2.500"), "−2.5");
});

test("stock state against the minimum", () => {
  const row = (balance, minimum, below) => ({
    balance,
    minimum_stock: minimum,
    has_minimum: minimum !== "0.000",
    below_minimum: below,
  });
  assert.equal(stockState(row("30.000", "50.000", true)), "below");
  assert.equal(stockState(row("50.000", "50.000", false)), "ok");
  assert.equal(stockState(row("0.000", "50.000", true)), "out");
  assert.equal(stockState(row("0.000", "0.000", false)), "no-minimum");
  assert.equal(stockState(row("12.000", "0.000", false)), "no-minimum");
});

test("level ratio is capped and safe", () => {
  assert.equal(levelRatio("25.000", "50.000"), 0.5);
  assert.equal(levelRatio("80.000", "50.000"), 1);
  assert.equal(levelRatio("5.000", "0.000"), 0);
  assert.equal(levelRatio("-1.000", "5.000"), 0);
});

const line = (key, itemId, quantity, unitId = "1") => ({ key, itemId, quantity, unitId, remarks: "" });

test("a valid opening entry passes", () => {
  const check = checkOpening("2026-11-01", "2026-11-23", [line("a", "1", "40"), line("b", "2", "1.25")], []);
  assert.deepEqual(check, { valid: true, lines: {} });
});

test("the date must be today or earlier", () => {
  assert.equal(checkOpening("2026-11-24", "2026-11-23", [line("a", "1", "4")], []).form,
    "Opening stock cannot be dated in the future.");
  assert.equal(checkOpening("", "2026-11-23", [line("a", "1", "4")], []).valid, false);
  assert.equal(checkOpening("2026-11-23", "2026-11-23", [line("a", "1", "4")], []).valid, true);
});

test("quantities must be positive with at most three decimals", () => {
  const check = checkOpening("2026-11-01", "2026-11-23", [
    line("zero", "1", "0"), line("neg", "2", "-1"), line("dp", "3", "1.0005"),
    line("text", "4", "ten"), line("empty", "5", ""),
  ], []);
  assert.equal(check.valid, false);
  assert.equal(check.lines.zero.quantity, "Must be more than zero.");
  assert.equal(check.lines.neg.quantity, "Use a number with up to 3 decimal places.");
  assert.equal(check.lines.dp.quantity, "Use a number with up to 3 decimal places.");
  assert.equal(check.lines.text.quantity, "Use a number with up to 3 decimal places.");
  assert.equal(check.lines.empty.quantity, "Enter the quantity.");
});

test("an item appears once and not when it already has opening stock", () => {
  const check = checkOpening("2026-11-01", "2026-11-23",
    [line("a", "1", "4"), line("b", "1", "5"), line("c", "7", "2")], [7]);
  assert.equal(check.lines.a, undefined);
  assert.equal(check.lines.b.item, "This item is already in the list.");
  assert.equal(check.lines.c.item, "Already has opening stock. Reverse it first.");
});

test("blank lines are ignored but an entry needs one item", () => {
  assert.equal(checkOpening("2026-11-01", "2026-11-23", [line("a", "", "")], []).form, "Add at least one item.");
  assert.equal(checkOpening("2026-11-01", "2026-11-23", [line("a", "1", "3"), line("b", "", "")], []).valid, true);
  assert.equal(checkOpening("2026-11-01", "2026-11-23", [line("a", "", "3")], []).lines.a.item, "Choose an item.");
  assert.equal(checkOpening("2026-11-01", "2026-11-23", [line("a", "1", "3", "")], []).lines.a.unit, "Choose a unit.");
});
