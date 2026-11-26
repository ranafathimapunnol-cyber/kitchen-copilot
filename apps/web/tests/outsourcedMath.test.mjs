// Unit tests for outsourced food entry (Stage 8a). Run with: npm test

import { test } from "node:test";
import assert from "node:assert/strict";

import {
  acceptedText,
  deliveryPayload,
  hasDeliveryErrors,
  hasOrderErrors,
  lineTotal,
  orderPayload,
  outsourcedExportName,
  periodError,
  presetPeriod,
  sumMoney,
  validateDelivery,
  validateOrder,
} from "../src/lib/outsourcedMath.ts";

const line = (patch = {}) => ({ itemId: "1", quantity: "100", unitId: "5", rate: "35", remarks: "", ...patch });
const order = (patch = {}) => ({
  orderDate: "2026-11-24", mealDate: "2026-11-25", sessionId: "2", supplierId: "3", notes: "", lines: [line()], ...patch,
});

test("line totals are exact and rounded half up to paise, like the API", () => {
  assert.equal(lineTotal("100", "35"), "3500.00");
  assert.equal(lineTotal("40", "80.5"), "3220.00");
  assert.equal(lineTotal("0.333", "10"), "3.33");
  assert.equal(lineTotal("1", "0.005"), "0.01"); // half up
  assert.equal(lineTotal("1", "0.0049"), "0.00");
  assert.equal(lineTotal("12.5", "33.3333"), "416.67");
  assert.equal(lineTotal("abc", "1"), null);
  assert.equal(lineTotal("1", "1.23456"), null);
  assert.equal(sumMoney(["3500.00", "3220.00", null, "0.01"]), "6720.01");
});

test("orders need supplier, session, dates in range and valid distinct lines", () => {
  assert.equal(hasOrderErrors(validateOrder(order(), "2026-11-24", "2026-12-24")), false);
  const blank = validateOrder(order({ supplierId: "", sessionId: "", lines: [] }), "2026-11-24", "2026-12-24");
  assert.equal(blank.supplier, "Choose the supplier.");
  assert.equal(blank.session, "Choose the meal session.");
  assert.equal(blank.lines, "Add at least one item.");
  assert.match(validateOrder(order({ orderDate: "2026-11-25" }), "2026-11-24", "2026-12-24").orderDate, /future/);
  assert.match(validateOrder(order({ mealDate: "2026-11-23" }), "2026-11-24", "2026-12-24").mealDate, /before the order date/);
  assert.match(validateOrder(order({ mealDate: "2026-12-25" }), "2026-11-24", "2026-12-24").mealDate, /up to 2026-12-24/);
  const lines = validateOrder(order({ lines: [line(), line(), line({ itemId: "9", quantity: "0", rate: "-1", unitId: "" })] }),
    "2026-11-24", "2026-12-24").lineErrors;
  assert.match(lines[1].item, /already on the order/);
  assert.equal(lines[2].quantity, "Must be more than 0.");
  assert.match(lines[2].rate, /rate/);
  assert.equal(lines[2].unit, "Choose a unit.");
  assert.deepEqual(orderPayload(order({ notes: "  ", lines: [line({ remarks: " Hot " })] })), {
    order_date: "2026-11-24", meal_date: "2026-11-25", meal_session_id: 2, supplier_id: 3, notes: null,
    lines: [{ item_id: 1, ordered_quantity: "100", unit_id: 5, unit_rate: "35", remarks: "Hot" }],
  });
});

test("deliveries: accepted = received − rejected; rejection needs a reason; never more than remains", () => {
  assert.equal(acceptedText("60", "5"), "55");
  assert.equal(acceptedText("60", ""), "60");
  assert.equal(acceptedText("1.5", "0.25"), "1.25");
  assert.equal(acceptedText("5", "6"), null);
  const dl = (patch = {}) => ({ orderLineId: 7, include: true, received: "60", rejected: "5", reason: "Cold", remarks: "", ...patch });
  const remaining = { 7: "100.000", 8: "10.000" };
  const check = (lines, date = "2026-11-24") => validateDelivery({ date, lines }, "2026-11-24", "2026-11-20", remaining);
  assert.equal(hasDeliveryErrors(check([dl()])), false);
  assert.match(check([dl({ reason: "" })]).lineErrors[7].reason, /reason/);
  assert.match(check([dl({ rejected: "61" })]).lineErrors[7].rejected, /more than received/);
  assert.match(check([dl({ received: "0" })]).lineErrors[7].received, /more than 0/);
  assert.match(check([dl({ orderLineId: 8, received: "12", rejected: "1", reason: "Cold" })]).lineErrors[8].received,
    /Only 10 remain/);
  assert.equal(hasDeliveryErrors(check([dl({ orderLineId: 8, received: "12", rejected: "2", reason: "Extra" })])), false);
  assert.match(check([dl({ include: false })]).lines, /at least one/);
  assert.match(check([dl()], "2026-11-25").date, /future/);
  assert.match(check([dl()], "2026-11-19").date, /before the order date/);
  assert.deepEqual(deliveryPayload({ date: "2026-11-24", remarks: "", lines: [dl(), dl({ orderLineId: 8, include: false }),
    dl({ orderLineId: 9, rejected: "", reason: "ignored" })] }), {
    delivery_date: "2026-11-24", remarks: null, lines: [
      { order_line_id: 7, received_quantity: "60", rejected_quantity: "5", rejection_reason: "Cold", remarks: null },
      { order_line_id: 9, received_quantity: "60", rejected_quantity: "0", rejection_reason: null, remarks: null },
    ],
  });
});

test("report periods: today, this week (from Monday), this month; at most 366 days", () => {
  const wednesday = new Date(2026, 10, 25); // 25 Nov 2026 is a Wednesday
  assert.deepEqual(presetPeriod("today", wednesday), { from: "2026-11-25", to: "2026-11-25" });
  assert.deepEqual(presetPeriod("week", wednesday), { from: "2026-11-23", to: "2026-11-25" });
  assert.deepEqual(presetPeriod("week", new Date(2026, 10, 29)), { from: "2026-11-23", to: "2026-11-29" }); // Sunday
  assert.deepEqual(presetPeriod("month", wednesday), { from: "2026-11-01", to: "2026-11-25" });
  assert.equal(periodError("2026-11-02", "2026-11-01"), "The start date must be on or before the end date.");
  assert.equal(periodError("2024-01-01", "2025-01-01"), "Choose a period of at most 366 days."); // 366 days (leap year)
  assert.equal(periodError("2025-01-01", "2026-01-01"), undefined); // 365 days
  assert.equal(periodError("", "2026-01-01"), "Choose both dates.");
});

test("export file names follow the API's rule", () => {
  const period = { date_from: "2026-11-01", date_to: "2026-11-30" };
  assert.equal(outsourcedExportName(period, { supplier_name: null, item_name: null, meal_session_name: null }, "pdf"),
    "outsourced-food_2026-11-01_2026-11-30.pdf");
  assert.equal(outsourcedExportName(period, { supplier_name: "Annapurna Caterers", item_name: "Idli set",
    meal_session_name: "Breakfast" }, "xlsx"), "outsourced-food_2026-11-01_2026-11-30_annapurna-caterers_idli-set_breakfast.xlsx");
});
