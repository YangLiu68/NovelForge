import assert from "node:assert/strict";
import { test } from "node:test";

import { resolvedNote } from "./resolved.ts";

test("named facts need no note", () => {
  assert.equal(resolvedNote({ details: {}, subject_name: "Jo" }), null);
  assert.equal(resolvedNote({ details: null, subject_name: "Jo" }), null);
});

test("pronoun and sentence-subject attributions are explained", () => {
  const pronoun = resolvedNote({
    details: { resolved: { via: "pronoun", pronoun: "her" } },
    subject_name: "Jo",
  });
  assert.match(pronoun ?? "", /through “her”: Jo is the only character/);
  const subject = resolvedNote({
    details: { resolved: { via: "sentence_subject" } },
    subject_name: "Brooke",
  });
  assert.match(subject ?? "", /Brooke as the subject of the sentence/);
});
