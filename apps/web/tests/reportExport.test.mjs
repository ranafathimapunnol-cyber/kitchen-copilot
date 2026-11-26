// Unit tests for report export file names.
// Run with: npm test   (Node's built-in runner; no extra dependency)

import { test } from "node:test";
import assert from "node:assert/strict";

import { exportFileName, fileNameFromDisposition } from "../src/lib/reportExport.ts";

const period = { date_from: "2026-11-01", date_to: "2026-11-15" };

test("reads the file name the API sends", () => {
  assert.equal(
    fileNameFromDisposition('attachment; filename="purchases-vs-payments_2026-11-01_2026-11-15.pdf"'),
    "purchases-vs-payments_2026-11-01_2026-11-15.pdf"
  );
  assert.equal(fileNameFromDisposition("attachment; filename=report.xlsx"), "report.xlsx");
  assert.equal(fileNameFromDisposition(null), null);
  assert.equal(fileNameFromDisposition("attachment"), null);
});

test("a server-supplied name cannot point into a folder", () => {
  assert.equal(fileNameFromDisposition('attachment; filename="../../x.pdf"'), ".._.._x.pdf");
});

test("builds the same name as the API", () => {
  assert.equal(exportFileName(period, { id: null, name: null }, "xlsx"),
               "purchases-vs-payments_2026-11-01_2026-11-15.xlsx");
  // Matches the API test: "Other A" → "other-a".
  assert.equal(exportFileName(period, { id: 7, name: "Other A" }, "pdf"),
               "purchases-vs-payments_2026-11-01_2026-11-15_other-a.pdf");
  assert.equal(exportFileName(period, { id: 7, name: "  Fresh & Co. (Pune) " }, "pdf"),
               "purchases-vs-payments_2026-11-01_2026-11-15_fresh-co-pune.pdf");
  assert.equal(exportFileName(period, { id: 9, name: "ಅನ್ನಪೂರ್ಣ" }, "pdf"),
               "purchases-vs-payments_2026-11-01_2026-11-15_supplier-9.pdf");
});
