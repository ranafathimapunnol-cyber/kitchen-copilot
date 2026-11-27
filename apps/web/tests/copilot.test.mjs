// Unit tests for the floating Copilot's page context and suggestions. Run with: npm test

import { test } from "node:test";
import assert from "node:assert/strict";

import { pageContext, pageTopic, suggestionsFor } from "../src/lib/agent.ts";

const ALL = { attention: true, plan_procure: true, explain_spending: true, stock_difference: true };

test("page context is sent only for dashboard paths the API accepts", () => {
  assert.equal(pageContext("/dashboard"), "/dashboard");
  assert.equal(pageContext("/dashboard/stock-counts/12"), "/dashboard/stock-counts/12");
  assert.equal(pageContext("/login"), null);
  assert.equal(pageContext("/dashboard/Stock"), null);
  assert.equal(pageContext("/dashboard/a/b/c/d/e"), null);
});

test("screens map to their topic", () => {
  assert.equal(pageTopic("/dashboard/stock"), "stock");
  assert.equal(pageTopic("/dashboard/stock-counts/3"), "stock");
  assert.equal(pageTopic("/dashboard/supplier-bills"), "purchasing");
  assert.equal(pageTopic("/dashboard/suppliers"), "purchasing");
  assert.equal(pageTopic("/dashboard/meal-plans/new"), "meals and planning");
  assert.equal(pageTopic("/dashboard/analytics"), "spending and reports");
  assert.equal(pageTopic("/dashboard"), null);
  assert.equal(pageTopic("/dashboard/users"), null);
});

test("suggestions follow the screen and hide jobs the user may not run", () => {
  assert.equal(suggestionsFor("/dashboard/stock", ALL)[0].workflow, "attention");
  assert.ok(suggestionsFor("/dashboard/stock", ALL).some((s) => s.workflow === "stock_difference"));
  assert.equal(suggestionsFor("/dashboard", ALL).length, 4);
  const staff = { attention: true, plan_procure: false, explain_spending: false, stock_difference: false };
  assert.deepEqual(suggestionsFor("/dashboard/supplier-bills", staff).map((s) => s.workflow), ["attention"]);
  assert.deepEqual(suggestionsFor("/dashboard", {}), []);
});
