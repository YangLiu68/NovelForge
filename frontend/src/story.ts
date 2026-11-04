// Labels and pure helpers for the story-logic page. The page speaks the novel's language: a
// Chinese novel gets Chinese labels, everything else English.

import type {
  LlmEstimate,
  StoryAuditResult,
  StoryNote,
  StoryPulse,
  StorySuggestion,
} from "./types";

export type Lang = "zh" | "en";

export function isChinese(text: string): boolean {
  const cjk = (text.match(/[㐀-䶿一-鿿]/g) ?? []).length;
  const latin = (text.match(/[A-Za-z]/g) ?? []).length;
  return cjk > 0 && cjk >= latin / 2;
}

const KIND: Record<Lang, Record<string, string>> = {
  zh: {
    consistent: "合理",
    unmotivated: "动机缺失",
    contradicts: "与人设冲突",
    malice_without_cause: "为坏而坏",
    routine: "日常",
    delayed: "后文有解释",
    unverified: "依据不足",
    knowledge_leak: "信息来源不明",
    deus_ex_machina: "天降解围",
    dangling_setup: "伏笔未回收",
    causality: "因果不通",
    flat_stretch: "节奏平",
    no_hook: "章末无钩子",
  },
  en: {
    consistent: "consistent",
    unmotivated: "no motive",
    contradicts: "against the character",
    malice_without_cause: "villainy without cause",
    routine: "routine",
    delayed: "explained later",
    unverified: "not grounded",
    knowledge_leak: "knowledge leak",
    deus_ex_machina: "deus ex machina",
    dangling_setup: "dangling setup",
    causality: "broken causality",
    flat_stretch: "flat stretch",
    no_hook: "no ending hook",
  },
};

const TECHNIQUE: Record<Lang, Record<string, string>> = {
  zh: {
    setup: "补伏笔",
    rewrite_motive: "改写动机",
    blessing_in_disguise: "因祸得福",
    reversal: "反转",
    past_life_memory: "前世记忆",
    golden_finger: "金手指",
    cliffhanger: "悬念钩子",
    cost_and_payoff: "代价与回报",
    cut: "删改",
    other: "其他",
  },
  en: {
    setup: "plant a setup",
    rewrite_motive: "rewrite the motive",
    blessing_in_disguise: "blessing in disguise",
    reversal: "reversal",
    past_life_memory: "past-life memory",
    golden_finger: "special advantage",
    cliffhanger: "cliffhanger",
    cost_and_payoff: "cost and payoff",
    cut: "cut",
    other: "other",
  },
};

const NOTE_KIND: Record<Lang, Record<string, string>> = {
  zh: {
    sheet: "设定",
    background: "身世",
    personality: "性格",
    goal: "目标",
    wound: "创伤",
    situation: "处境",
    relationship: "关系",
    knowledge: "信息",
  },
  en: {
    sheet: "sheet",
    background: "background",
    personality: "personality",
    goal: "goal",
    wound: "wound",
    situation: "situation",
    relationship: "relationship",
    knowledge: "knowledge",
  },
};

const ROLE: Record<Lang, Record<string, string>> = {
  zh: { beat: "行为", conflict: "冲突的前文", setup: "伏笔", knowledge: "信息", chapter: "章末" },
  en: { beat: "beat", conflict: "conflicts with", setup: "setup", knowledge: "knowledge", chapter: "ending" },
};

const EMOTION: Record<Lang, Record<string, string>> = {
  zh: {
    thrill: "爽",
    heartache: "虐",
    suspense: "悬念",
    tension: "紧张",
    warmth: "温情",
    anger: "愤怒",
    calm: "平淡",
  },
  en: {
    thrill: "thrill",
    heartache: "heartache",
    suspense: "suspense",
    tension: "tension",
    warmth: "warmth",
    anger: "anger",
    calm: "calm",
  },
};

export const kindLabel = (lang: Lang, k: string) => KIND[lang][k] ?? k;
export const techniqueLabel = (lang: Lang, k: string) => TECHNIQUE[lang][k] ?? k;
export const noteKindLabel = (lang: Lang, k: string) => NOTE_KIND[lang][k] ?? k;
export const roleLabel = (lang: Lang, k: string) => ROLE[lang][k] ?? k;
export const emotionLabel = (lang: Lang, k: string) => EMOTION[lang][k] ?? k;

export function severityLabel(lang: Lang, s: number): string {
  if (lang === "zh") return s >= 3 ? "严重" : s === 2 ? "明显" : "轻微";
  return s >= 3 ? "serious" : s === 2 ? "clear" : "minor";
}

/** CSS class shared with the contradiction cards (sev-high / sev-medium / sev-low). */
export const severityClass = (s: number) => (s >= 3 ? "high" : s === 2 ? "medium" : "low");

export function chapterLabel(lang: Lang, n: number): string {
  return lang === "zh" ? `第 ${n} 章` : `Ch ${n}`;
}

/** Notes by id, for showing what a motive or conflict cites. */
export function noteIndex(result: StoryAuditResult): Map<string, StoryNote> {
  return new Map(result.notes.map((n) => [n.id, n]));
}

/** Per character: their judged beats in story order, with the judgement. */
export function beatsByCharacter(result: StoryAuditResult) {
  const judged = new Map(result.judgements.map((j) => [j.beat, j]));
  const out = new Map<string, { beat: StoryAuditResult["beats"][number]; judgement: StoryAuditResult["judgements"][number] }[]>();
  for (const b of result.beats) {
    const j = judged.get(b.id);
    if (!j) continue;
    const list = out.get(b.character) ?? [];
    list.push({ beat: b, judgement: j });
    out.set(b.character, list);
  }
  return out;
}

export interface CurvePoint {
  chapter: number;
  x: number;
  y: number;
  tension: number;
  hook: boolean;
}

/** Points for the tension chart: x spread over the width, tension 1..5 mapped onto the height. */
export function tensionCurve(
  pulses: StoryPulse[],
  width: number,
  height: number,
  pad = 24,
): CurvePoint[] {
  const ps = pulses.filter((p) => p.tension > 0).sort((a, b) => a.chapter - b.chapter);
  if (ps.length === 0) return [];
  const step = ps.length > 1 ? (width - 2 * pad) / (ps.length - 1) : 0;
  return ps.map((p, i) => ({
    chapter: p.chapter,
    x: ps.length > 1 ? pad + i * step : width / 2,
    y: height - pad - ((Math.min(5, Math.max(1, p.tension)) - 1) / 4) * (height - 2 * pad),
    tension: p.tension,
    hook: p.hook,
  }));
}

/** The draft-assistant goal for a revision suggestion (kept under the API's 4,000 characters). */
export function revisionGoal(lang: Lang, s: StorySuggestion): string {
  const parts =
    lang === "zh"
      ? [`修改方案（${techniqueLabel(lang, s.technique)}）：${s.change}`, s.why && `目的：${s.why}`, s.sample && `示范：${s.sample}`]
      : [`Revision (${techniqueLabel(lang, s.technique)}): ${s.change}`, s.why && `Why: ${s.why}`, s.sample && `Sample: ${s.sample}`];
  return parts.filter(Boolean).join("\n").slice(0, 4000);
}

/** One line for the cost of a run before it starts, e.g. "约 66 次模型调用，预计 $1.12（…）". */
export function estimateLabel(lang: Lang, e: LlmEstimate): string {
  const usd = (x: number) => `$${x < 0.1 ? x.toFixed(3) : x.toFixed(2)}`;
  if (lang === "zh") {
    const calls = `约 ${e.calls} 次模型调用`;
    if (e.free) return `${calls}，不收费（本地、回放或模拟）`;
    if (e.cost_usd === null) return `${calls}，这个模型的价格未知`;
    return `${calls}，预计 ${usd(e.cost_usd)}（${usd(e.low_usd!)}–${usd(e.high_usd!)}，按已记录的运行估算）`;
  }
  const calls = `about ${e.calls} model calls`;
  if (e.free) return `${calls}, free (local, replay or mock)`;
  if (e.cost_usd === null) return `${calls}; this model's price is unknown`;
  return `${calls}, about ${usd(e.cost_usd)} (${usd(e.low_usd!)}–${usd(e.high_usd!)}, from recorded runs)`;
}
