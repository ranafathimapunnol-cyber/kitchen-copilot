// Unit tests for the goods-receipt entry rules (PUR03).
// Run with: npm test   (Node's built-in runner; no extra dependency)

import { test } from "node:test";
import assert from "node:assert/strict";

import {
  checkLine,
  checkReceipt,
  formatQuantity,
  fromMilli,
  rejectedRemainder,
  suggestedRejected,
  toMilli,
  updateLineInput,
} from "../src/lib/receiptMath.ts";

test("quantities are exact thousandths", () => {
  assert.equal(toMilli("6.125"), 6125);
  assert.equal(toMilli(" 10 "), 10000);
  assert.equal(toMilli(""), 0);
  assert.equal(toMilli("0.1") + toMilli("0.2"), toMilli("0.3"));
  for (const bad of ["1.2345", "-1", "1e3", "abc", "1,5", ".5"]) {
    assert.equal(toMilli(bad), null, bad);
  }
  assert.equal(fromMilli(6125), "6.125");
  assert.equal(fromMilli(5), "0.005");
});

test("display drops trailing zeros only", () => {
  assert.equal(formatQuantity("10.000"), "10");
  assert.equal(formatQuantity("5.500"), "5.5");
  assert.equal(formatQuantity("0.000"), "0");
  assert.equal(formatQuantity("100.010"), "100.01");
  assert.equal(formatQuantity(null), "—");
});

test("a line with nothing received is left out", () => {
  assert.deepEqual(checkLine({ received: "", accepted: "", rejected: "" }, "4"),
    { error: null, complete: true, included: false });
  assert.match(checkLine({ received: "0", accepted: "1", rejected: "" }, "4").error, /received quantity first/);
});

test("accepted plus rejected cannot exceed received", () => {
  assert.match(checkLine({ received: "6", accepted: "5", rejected: "1.001" }, "10").error, /more than received/);
  const ok = checkLine({ received: "6", accepted: "5", rejected: "1" }, "10");
  assert.deepEqual(ok, { error: null, complete: true, included: true });
});

test("a partly classified line can be saved but is not complete", () => {
  const partial = checkLine({ received: "6", accepted: "4", rejected: "" }, "10");
  assert.equal(partial.error, null);
  assert.equal(partial.complete, false);
});

test("received cannot exceed what is left on the bill line", () => {
  assert.match(checkLine({ received: "4.001", accepted: "", rejected: "" }, "4").error, /Only 4 left/);
  assert.match(checkLine({ received: "1", accepted: "", rejected: "" }, "0.000").error, /Nothing is left/);
  assert.equal(checkLine({ received: "4", accepted: "4", rejected: "0" }, "4.000").error, null);
});

test("invalid numbers are reported", () => {
  assert.match(checkLine({ received: "1.2345", accepted: "", rejected: "" }, "10").error, /3 decimal places/);
});

test("a receipt needs at least one received line and no errors", () => {
  const empty = checkReceipt([{ input: { received: "", accepted: "", rejected: "" }, remaining: "5" }]);
  assert.equal(empty.canSave, false);

  const mixed = checkReceipt([
    { input: { received: "2", accepted: "2", rejected: "0" }, remaining: "5" },
    { input: { received: "", accepted: "", rejected: "" }, remaining: "3" },
  ]);
  assert.equal(mixed.canSave, true);
  assert.equal(mixed.allClassified, true);

  const unclassified = checkReceipt([
    { input: { received: "2", accepted: "1", rejected: "" }, remaining: "5" },
  ]);
  assert.equal(unclassified.canSave, true);
  assert.equal(unclassified.allClassified, false);

  const bad = checkReceipt([
    { input: { received: "9", accepted: "", rejected: "" }, remaining: "5" },
    { input: { received: "1", accepted: "1", rejected: "" }, remaining: "5" },
  ]);
  assert.equal(bad.canSave, false);
});

test("rejected fills in from received and accepted until the user overrides it", () => {
  let line = { received: "", accepted: "", rejected: "" };
  line = updateLineInput(line, { received: "6" });
  assert.equal(line.rejected, "", "nothing suggested before an accepted quantity");
  line = updateLineInput(line, { accepted: "5" });
  assert.equal(line.rejected, "1");
  line = updateLineInput(line, { received: "6.5" });
  assert.equal(line.rejected, "1.5", "keeps following");
  line = updateLineInput(line, { rejected: "0.25" });
  line = updateLineInput(line, { accepted: "6" });
  assert.equal(line.rejected, "0.25", "a typed value is kept");
  assert.equal(suggestedRejected("4", ""), "");
});

test("rejected defaults to received minus accepted", () => {
  assert.equal(rejectedRemainder("6", "5.5"), "0.5");
  assert.equal(rejectedRemainder("6", "6"), "0");
  assert.equal(rejectedRemainder("", ""), "0");
  assert.equal(rejectedRemainder("6", "7"), "");
});
