// Unit tests for the dashboard helpers (Stage 9). Run with: npm test

import { test } from "node:test";
import assert from "node:assert/strict";

import { percentText } from "../src/lib/dashboard.ts";

test("percentages show a sign, and 'Not comparable' when the API has none (DASH02, AT07)", () => {
  assert.equal(percentText("12.5"), "+12.5%");
  assert.equal(percentText("-100.0"), "-100.0%");
  assert.equal(percentText("0.0"), "0.0%");
  assert.equal(percentText(null), "Not comparable");
  assert.equal(percentText(undefined), "Not comparable");
});
