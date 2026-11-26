// Unit tests for the bill attachment pre-check.
// Run with: npm test   (Node's built-in runner; no extra dependency)

import { test } from "node:test";
import assert from "node:assert/strict";

import {
  MAX_ATTACHMENT_BYTES,
  checkFiles,
  formatBytes,
} from "../src/lib/attachments.ts";

const file = (name, size = 1000, type = "") => ({ name, size, type });

test("accepts the four approved formats by type or extension", () => {
  const result = checkFiles([
    file("bill.pdf"), file("scan.JPG"), file("photo.jpeg"),
    file("x.png"), file("y.webp"), file("noext", 10, "application/pdf"),
  ], 0);
  assert.equal(result.accepted.length, 6);
  assert.deepEqual(result.rejected, []);
});

test("refuses other formats, empty files and files over 10 MB", () => {
  const result = checkFiles([
    file("bill.gif", 10, "image/gif"), file("bill.docx"), file("empty.pdf", 0),
    file("big.pdf", MAX_ATTACHMENT_BYTES + 1), file("edge.pdf", MAX_ATTACHMENT_BYTES),
  ], 0);
  assert.deepEqual(result.accepted.map((f) => f.name), ["edge.pdf"]);
  assert.deepEqual(result.rejected.map((r) => r.reason), [
    "Only PDF, JPEG, PNG or WEBP files.", "Only PDF, JPEG, PNG or WEBP files.",
    "The file is empty.", "Larger than 10 MB.",
  ]);
});

test("never goes past ten files on one bill", () => {
  const result = checkFiles([file("a.pdf"), file("b.pdf"), file("c.pdf")], 8);
  assert.deepEqual(result.accepted.map((f) => f.name), ["a.pdf", "b.pdf"]);
  assert.match(result.rejected[0].reason, /at most 10/);
  assert.equal(checkFiles([file("a.pdf")], 10).accepted.length, 0);
});

test("formats sizes for people", () => {
  assert.equal(formatBytes(512), "512 B");
  assert.equal(formatBytes(1536), "1.5 KB");
  assert.equal(formatBytes(10 * 1024 * 1024), "10 MB");
  assert.equal(formatBytes(2.25 * 1024 * 1024), "2.3 MB");
});
