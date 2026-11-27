// Unit tests for page access by role (Stages 10-12). Run with: npm test

import { test } from "node:test";
import assert from "node:assert/strict";

import { canAccessPath, homePath } from "../src/lib/auth/permissions.ts";
import { proposalLines } from "../src/lib/agent.ts";

test("SUPER_ADMIN uses only the separate platform app, never a campus screen", () => {
  assert.equal(homePath("SUPER_ADMIN"), "/platform");
  for (const path of ["/dashboard", "/dashboard/platform", "/dashboard/account", "/dashboard/items", "/dashboard/users", "/dashboard/copilot", "/dashboard/audit"]) {
    assert.equal(canAccessPath("SUPER_ADMIN", path, []), false, path);
  }
});

test("campus roles never reach the platform; only ADMIN manages user accounts", () => {
  for (const role of ["ADMIN", "KITCHEN_MANAGER", "STAFF"]) {
    assert.equal(canAccessPath(role, "/dashboard/platform", ["audit.read"]), false, role);
    assert.equal(canAccessPath(role, "/dashboard/copilot", []), true, role);
    assert.equal(canAccessPath(role, "/dashboard/account", []), true, role);
  }
  assert.equal(canAccessPath("ADMIN", "/dashboard/users", []), true);
  assert.equal(canAccessPath("KITCHEN_MANAGER", "/dashboard/users", ["audit.read"]), false);
  assert.equal(canAccessPath("KITCHEN_MANAGER", "/dashboard/audit", ["audit.read"]), true);
  assert.equal(canAccessPath("STAFF", "/dashboard/audit", []), false);
});

test("a purchase-order proposal lists exactly what will be created", () => {
  const lines = proposalLines({
    action_type: "CREATE_PURCHASE_ORDER_DRAFT",
    payload: { supplier_name: "Fresh Farms", expected_date: "2026-11-27",
      items: [{ item_name: "Rice", quantity: "47.500", unit_symbol: "kg" }] },
  });
  assert.deepEqual(lines, ["Supplier: Fresh Farms", "Rice: 47.500 kg", "Expected by 2026-11-27"]);
});
