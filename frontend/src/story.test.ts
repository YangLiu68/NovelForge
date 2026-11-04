import assert from "node:assert/strict";
import { test } from "node:test";

import {
  beatsByCharacter,
  estimateLabel,
  isChinese,
  kindLabel,
  revisionGoal,
  severityClass,
  severityLabel,
  tensionCurve,
} from "./story.ts";
import type { LlmEstimate, StoryAuditResult, StoryPulse } from "./types.ts";

const pulse = (chapter: number, tension: number, hook = false): StoryPulse => ({
  chapter,
  tension,
  hook,
  summary: "",
  emotions: [],
  hook_quote: null,
  hook_start: null,
  hook_end: null,
});

test("language follows the text", () => {
  assert.equal(isChinese("雪夜当铺"), true);
  assert.equal(isChinese("The Secret Garden"), false);
  assert.equal(isChinese("第 1 章 Mara"), true);
  assert.equal(isChinese(""), false);
});

test("labels in both languages, unknown kinds pass through", () => {
  assert.equal(kindLabel("zh", "malice_without_cause"), "为坏而坏");
  assert.equal(kindLabel("en", "deus_ex_machina"), "deus ex machina");
  assert.equal(kindLabel("zh", "something_new"), "something_new");
  assert.deepEqual([3, 2, 1].map((s) => severityLabel("zh", s)), ["严重", "明显", "轻微"]);
  assert.deepEqual([3, 2, 1].map(severityClass), ["high", "medium", "low"]);
});

test("tension curve maps 1..5 onto the drawing and skips chapters without a reading", () => {
  const pts = tensionCurve([pulse(2, 5, true), pulse(1, 1), pulse(3, 0)], 200, 100, 10);
  assert.deepEqual(
    pts.map((p) => p.chapter),
    [1, 2],
  );
  assert.equal(pts[0].x, 10);
  assert.equal(pts[1].x, 190);
  assert.equal(pts[0].y, 90); // tension 1 at the bottom
  assert.equal(pts[1].y, 10); // tension 5 at the top
  assert.equal(pts[1].hook, true);
  const one = tensionCurve([pulse(4, 3)], 200, 100, 10);
  assert.equal(one[0].x, 100);
  assert.equal(one[0].y, 50);
});

test("beats are grouped by character in story order, unjudged beats left out", () => {
  const beat = (id: string, chapter: number, character: string) => ({
    id,
    chapter,
    character,
    listed: true,
    action: id,
    quote: "q",
    start: 0,
    end: 1,
    hostile: false,
    target: "",
    cost: "",
    located: "exact",
  });
  const judgement = (b: string, verdict: string) => ({
    beat: b,
    model_verdict: verdict,
    verdict,
    severity: 2,
    reasoning: "",
    motives: [],
    conflicts: [],
    fixes: [],
    explained_by: null,
    explained_why: null,
    checks: [],
  });
  const result = {
    beats: [beat("B1", 1, "甲"), beat("B2", 2, "乙"), beat("B3", 3, "甲"), beat("B4", 3, "丙")],
    judgements: [judgement("B3", "contradicts"), judgement("B1", "consistent"), judgement("B2", "delayed")],
  } as unknown as StoryAuditResult;
  const groups = beatsByCharacter(result);
  assert.deepEqual([...groups.keys()], ["甲", "乙"]);
  assert.deepEqual(
    groups.get("甲")!.map((r) => [r.beat.id, r.judgement.verdict]),
    [
      ["B1", "consistent"],
      ["B3", "contradicts"],
    ],
  );
});

test("a suggestion becomes a draft-assistant goal", () => {
  const goal = revisionGoal("zh", {
    targets: ["I1"],
    chapter: 2,
    technique: "setup",
    change: "在第 1 章补一段她讨过饭的经历",
    why: "让施舍有来由",
    sample: "",
  });
  assert.equal(goal, "修改方案（补伏笔）：在第 1 章补一段她讨过饭的经历\n目的：让施舍有来由");
  const long = revisionGoal("en", { targets: [], chapter: 1, technique: "cut", change: "x".repeat(5000), why: "", sample: "" });
  assert.equal(long.length, 4000);
});

test("estimateLabel says what a run will cost, or that it is free or unpriced", () => {
  const e: LlmEstimate = {
    llm: "openrouter:anthropic/claude-opus-5.5", task: "story", language: "zh", chapters: 8,
    calls: 66, input_tokens: 90000, output_tokens: 38000, free: false,
    cost_usd: 1.12, low_usd: 0.56, high_usd: 2.24, basis: "",
  };
  assert.equal(estimateLabel("zh", e), "约 66 次模型调用，预计 $1.12（$0.56–$2.24，按已记录的运行估算）");
  assert.equal(
    estimateLabel("en", { ...e, cost_usd: 0.012, low_usd: 0.006, high_usd: 0.024 }),
    "about 66 model calls, about $0.012 ($0.006–$0.024, from recorded runs)",
  );
  assert.match(estimateLabel("zh", { ...e, free: true, cost_usd: 0 }), /不收费/);
  assert.match(estimateLabel("en", { ...e, cost_usd: null }), /price is unknown/);
});
