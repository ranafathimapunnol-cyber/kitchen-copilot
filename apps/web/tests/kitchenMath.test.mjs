// Unit tests for the kitchen issue and unused-return entry rules
// (Stage 4, slice 4b). Run with: npm test

import { test } from "node:test";
import assert from "node:assert/strict";

import { checkIssue, checkReturn, milli } from "../src/lib/kitchenMath.ts";

const TODAY = "2026-11-23";
const line = (key, itemId, quantity, unitId = "1") => ({ key, itemId, quantity, unitId, remarks: "" });
const issue = (overrides = {}) => ({
  date: TODAY, sessionId: "1", menuId: "4", menuSessionId: "1",
  lines: [line("a", "10", "4")], ...overrides,
});

test("quantities are exact thousandths", () => {
  assert.equal(milli("6.125"), 6125);
  assert.equal(milli("0.1"), 100);
  assert.equal(milli("1.0005"), null);
  assert.equal(milli("-1"), null);
});

test("a complete issue passes", () => {
  assert.deepEqual(checkIssue(issue(), TODAY), { valid: true, fields: {}, lines: {} });
});

test("issue header: date, session and a menu of that session", () => {
  assert.equal(checkIssue(issue({ date: "2026-11-24" }), TODAY).fields.date, "An issue cannot be dated in the future.");
  assert.equal(checkIssue(issue({ date: "2026-11-20" }), TODAY).valid, true); // backdated is allowed
  assert.equal(checkIssue(issue({ sessionId: "" }), TODAY).fields.session, "Choose the meal session.");
  assert.equal(checkIssue(issue({ menuId: "" }), TODAY).fields.menu, "Choose the menu.");
  assert.equal(checkIssue(issue({ menuSessionId: "2" }), TODAY).fields.menu, "This menu belongs to another meal session.");
});

test("issue lines: one per item, a unit and a positive quantity", () => {
  const check = checkIssue(issue({ lines: [
    line("a", "10", "4"), line("b", "10", "1"), line("c", "11", "0"), line("d", "12", "1.0005"), line("e", "13", "2", ""),
    line("blank", "", ""),
  ] }), TODAY);
  assert.equal(check.valid, false);
  assert.equal(check.lines.a, undefined);
  assert.equal(check.lines.b.item, "This item is already in the issue.");
  assert.equal(check.lines.c.quantity, "Must be more than zero.");
  assert.equal(check.lines.d.quantity, "Use a number with up to 3 decimal places.");
  assert.equal(check.lines.e.unit, "Choose a unit.");
  assert.equal(check.lines.blank, undefined);
  assert.equal(checkIssue(issue({ lines: [line("x", "", "")] }), TODAY).fields.lines, "Add at least one item.");
});

const returned = (key, quantity, returnable, factor = 1) => ({ key, quantity, returnable, factor });

test("a return within what each line can still give back passes", () => {
  const check = checkReturn({ date: TODAY, issueDate: "2026-11-21", lines: [returned("a", "1.5", "2.500"), returned("b", "", "1.000")] }, TODAY);
  assert.deepEqual(check, { valid: true, lines: {} });
});

test("return quantities are converted before comparing with what is left", () => {
  const ok = checkReturn({ date: TODAY, issueDate: TODAY, lines: [returned("g", "2500", "2.500", 0.001)] }, TODAY);
  assert.equal(ok.valid, true);
  const tooMuch = checkReturn({ date: TODAY, issueDate: TODAY, lines: [returned("g", "2501", "2.500", 0.001)] }, TODAY);
  assert.equal(tooMuch.lines.g, "No more than 2.5 can be returned.");
});

test("return date: not in the future, not before the issue; at least one quantity", () => {
  assert.equal(checkReturn({ date: "2026-11-24", issueDate: TODAY, lines: [returned("a", "1", "2.000")] }, TODAY).date,
    "A return cannot be dated in the future.");
  assert.equal(checkReturn({ date: "2026-11-20", issueDate: "2026-11-21", lines: [returned("a", "1", "2.000")] }, TODAY).date,
    "A return cannot be dated before its issue.");
  assert.equal(checkReturn({ date: TODAY, issueDate: TODAY, lines: [returned("a", "", "2.000")] }, TODAY).form,
    "Enter at least one quantity to return.");
});
