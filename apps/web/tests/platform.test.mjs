// Unit tests for the platform (organisation-level) helpers. Run with: npm test

import { test } from "node:test";
import assert from "node:assert/strict";

import { auditSentence, monthToDate, query } from "../src/lib/platform.ts";
import { canAccessPath, homePath } from "../src/lib/auth/permissions.ts";

const row = (over) => ({ id: 1, occurred_at: "", actor_user_id: 1, actor_email: "a@x", action: "LOGIN",
  target_type: "PLATFORM_SESSION", target_id: null, campus_id: null, outcome: "SUCCESS", ip_address: null, details: {}, ...over });

test("audit rows read as one plain sentence", () => {
  assert.equal(auditSentence(row({})), "Sign-in");
  assert.equal(auditSentence(row({ outcome: "FAILURE" })), "Sign-in (failed)");
  assert.equal(auditSentence(row({ outcome: "DENIED" })), "Sign-in (refused)");
  assert.equal(auditSentence(row({ action: "DEACTIVATE", target_type: "CAMPUS", campus_id: 4 }), { 4: "Hill" }), "Deactivated · Hill");
  assert.equal(auditSentence(row({ action: "CONFIGURE_INTEGRATION", target_type: "CAMPUS_INTEGRATION" })), "Integration settings changed · campus integration");
});

test("query strings skip empty filters", () => {
  assert.equal(query({ a: "", b: null, c: undefined }), "");
  assert.equal(query({ date_from: "2026-11-01", campus_id: 3, q: "" }), "?date_from=2026-11-01&campus_id=3");
});

test("month to date starts on the 1st", () => {
  assert.deepEqual(monthToDate(new Date(2026, 10, 27)), { date_from: "2026-11-01", date_to: "2026-11-27" });
  assert.deepEqual(monthToDate(new Date(2026, 0, 5)), { date_from: "2026-01-01", date_to: "2026-01-05" });
});

test("platform and campus apps never mix", () => {
  assert.equal(homePath("SUPER_ADMIN"), "/platform");
  assert.equal(homePath("ADMIN"), "/dashboard");
  assert.equal(canAccessPath("SUPER_ADMIN", "/dashboard", []), false);
  assert.equal(canAccessPath("ADMIN", "/dashboard/platform", []), false);
});
