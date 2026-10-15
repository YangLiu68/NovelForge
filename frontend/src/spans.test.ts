import assert from "node:assert/strict";
import { test } from "node:test";

import { cpToUtf16, parseSpan, segments, sliceCp, spanHref } from "./spans.ts";

test("code-point offsets equal UTF-16 offsets for BMP text", () => {
  const text = "Mara's grey eyes";
  assert.equal(cpToUtf16(text, 7), 7);
  assert.equal(sliceCp(text, 7, 11), "grey");
});

test("astral characters count as one code point", () => {
  // Python: len("🌊 Mara") == 6, "🌊 Mara"[2:6] == "Mara"
  const text = "🌊 Mara";
  assert.equal(text.length, 7);
  assert.equal(cpToUtf16(text, 2), 3);
  assert.equal(sliceCp(text, 2, 6), "Mara");
});

test("offsets past the end clamp", () => {
  assert.equal(cpToUtf16("abc", 10), 3);
  assert.equal(cpToUtf16("abc", -1), 0);
});

test("segments mark ranges and keep all text", () => {
  const text = "a 🌊 flood and a flooded street";
  const parts = segments(text, [[16, 23], [4, 9]]);
  assert.equal(parts.map((p) => p.text).join(""), text);
  assert.deepEqual(parts.filter((p) => p.marked).map((p) => p.text), ["flood", "flooded"]);
});

test("overlapping ranges keep the earlier one", () => {
  const parts = segments("abcdef", [[0, 3], [2, 5]]);
  assert.deepEqual(parts.filter((p) => p.marked).map((p) => p.text), ["abc"]);
});

test("span links round-trip", () => {
  const href = spanHref("n1", "c1", 5, 9, 3);
  const params = new URLSearchParams(href.split("?")[1]);
  assert.deepEqual(parseSpan(params), { start: 5, end: 9, version: 3 });
  assert.equal(parseSpan(new URLSearchParams("start=9&end=5")), null);
  assert.equal(parseSpan(new URLSearchParams("start=x&end=5")), null);
});
