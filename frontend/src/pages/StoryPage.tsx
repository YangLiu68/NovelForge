import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import { spanHref } from "../spans";
import {
  beatsByCharacter,
  chapterLabel,
  emotionLabel,
  isChinese,
  kindLabel,
  type Lang,
  noteIndex,
  noteKindLabel,
  revisionGoal,
  roleLabel,
  severityClass,
  severityLabel,
  techniqueLabel,
  tensionCurve,
} from "../story";
import type {
  StoryAuditResult,
  StoryAuditRun,
  StoryEvidence,
  StoryIssue,
  StoryNote,
  StorySuggestion,
} from "../types";
import { useWorkspace } from "./workspaceContext";

const T = {
  zh: {
    title: "人物与故事线",
    intro:
      "逐个检查关键行为背后的动机：和人物的身世、性格、处境对不对得上，反派坏得有没有理由；再查故事线的逻辑漏洞和节奏，并给出修改方案。每条结论都附原文，引用由程序逐字核对。",
    model: "模型",
    configured: "服务器配置的模型",
    replay: "回放录制的 qwen2.5:7b 结果",
    mock: "离线模拟（无分析）",
    run: "开始审查",
    running: "审查中",
    queued: "排队中",
    failed: "审查失败",
    none: "还没有审查结果。",
    problems: "重大事故点",
    noProblems: "没有发现问题。",
    plan: "修改方案",
    motives: "人物动机",
    pacing: "节奏曲线",
    dossier: "人物档案",
    checks: "检查记录",
    fixes: "修改建议",
    motive: "动机",
    conflicts: "冲突",
    explained: "后文交代",
    stale: "这些章节在审查之后改过，相关引文可能已经对不上：",
    fixesIssues: "解决",
    tension: "紧张度",
    hook: "章末钩子",
    usage: (r: StoryAuditRun) =>
      `${r.llm} · ${r.input_tokens.toLocaleString()} 输入 / ${r.output_tokens.toLocaleString()} 输出 token · 费用 ${r.cost_usd === null ? "未知" : `$${r.cost_usd.toFixed(4)}`}`,
    replayNote: "回放：这是本地 qwen2.5:7b 模型对这部小说的真实输出，录制后原样重放；改过正文就无法回放。",
    rejected: "被程序拦下的模型输出",
    changed: "被程序改判的结论",
    sample: "示范",
    draft: "用这条方案改稿（写作助手：先出提纲，你批准后才起草）",
    secret: "用到的信息",
    modelSaid: "模型原话：",
    setups: "伏笔",
    paid: "已回收",
    unpaid: "未回收",
  },
  en: {
    title: "Story logic",
    intro:
      "Checks the motive behind every key beat against the character's background, personality and situation, asks whether villains have a reason, then checks the plot for holes and the pacing, and proposes revisions. Every finding cites the text; quotes are verified by code.",
    model: "Model",
    configured: "server's configured model",
    replay: "replay the recorded qwen2.5:7b run",
    mock: "offline mock (no analysis)",
    run: "Run audit",
    running: "Running",
    queued: "Queued",
    failed: "Audit failed",
    none: "No audit yet.",
    problems: "Major problems",
    noProblems: "No problems found.",
    plan: "Revision plan",
    motives: "Character motives",
    pacing: "Pacing",
    dossier: "Character files",
    checks: "Checks",
    fixes: "Fixes",
    motive: "Motive",
    conflicts: "Conflicts",
    explained: "Explained later",
    stale: "These chapters changed after the audit; their quotes may no longer line up:",
    fixesIssues: "Fixes",
    tension: "tension",
    hook: "ending hook",
    usage: (r: StoryAuditRun) =>
      `${r.llm} · ${r.input_tokens.toLocaleString()} in / ${r.output_tokens.toLocaleString()} out tokens · cost ${r.cost_usd === null ? "unknown" : `$${r.cost_usd.toFixed(4)}`}`,
    replayNote: "Replay: real output of the local qwen2.5:7b model on this novel, recorded and replayed as is; it stops working once the text changes.",
    rejected: "Model output stopped by the checks",
    changed: "Verdicts changed by the checks",
    sample: "Sample",
    draft: "Revise with this (draft assistant: plan first, drafts only after you approve)",
    secret: "Information used",
    modelSaid: "The model said:",
    setups: "Setups",
    paid: "paid off",
    unpaid: "never paid off",
  },
};

const PROBLEMS = ["unmotivated", "contradicts", "malice_without_cause"];

interface Ctx {
  lang: Lang;
  t: (typeof T)["zh"];
  novelId: string;
  run: StoryAuditRun;
  result: StoryAuditResult;
}

function evidenceHref(c: Ctx, e: { chapter: number; start: number | null; end: number | null }) {
  const id = c.run.chapter_ids[String(e.chapter)];
  if (!id || e.start === null || e.end === null) return null;
  return spanHref(c.novelId, id, e.start, e.end, c.run.chapter_versions[id]);
}

function draftHref(c: Ctx, s: StorySuggestion): string {
  const params = new URLSearchParams({ goal: revisionGoal(c.lang, s) });
  const id = c.run.chapter_ids[String(s.chapter)];
  if (id) params.set("chapter", id);
  return `/novels/${c.novelId}/draft?${params.toString()}`;
}

function Quote({ c, e, role }: { c: Ctx; e: StoryEvidence | StoryNote; role?: string }) {
  if (!e.quote || e.chapter === null) return null;
  const href = evidenceHref(c, e as { chapter: number; start: number; end: number });
  const body = <span className="quote">“{e.quote}”</span>;
  return (
    <li className="evidence">
      {href ? (
        <Link to={href} className="evidence-link" data-testid="story-evidence">
          {body}
        </Link>
      ) : (
        body
      )}
      <span className="muted small">
        {chapterLabel(c.lang, e.chapter)}
        {role && ` · ${roleLabel(c.lang, role)}`}
      </span>
    </li>
  );
}

function IssueCard({ c, issue }: { c: Ctx; issue: StoryIssue }) {
  return (
    <li className={`card finding sev-${severityClass(issue.severity)}`} id={issue.id} data-testid="story-issue">
      <div className="finding-head">
        <span className={`badge sev-${severityClass(issue.severity)}`}>
          {severityLabel(c.lang, issue.severity)}
        </span>
        <span className="finding-kind">{kindLabel(c.lang, issue.kind)}</span>
        <span className="muted small">
          {issue.id} · {issue.chapters.map((n) => chapterLabel(c.lang, n)).join("、")}
          {issue.character && ` · ${issue.character}`}
        </span>
      </div>
      <p className="story-title">{issue.title}</p>
      {issue.rationale && issue.rationale !== issue.title && (
        <p data-testid="story-rationale">{issue.rationale}</p>
      )}
      {issue.explanation && ![issue.title, issue.rationale].includes(issue.explanation) && (
        <p className="muted small">
          {c.t.modelSaid} {issue.explanation}
        </p>
      )}
      <ul className="evidence-list">
        {issue.evidence.map((e, i) => (
          <Quote key={i} c={c} e={e} role={e.role} />
        ))}
      </ul>
      {issue.fixes.length > 0 && (
        <div className="story-fixes">
          <span className="muted small">{c.t.fixes}</span>
          <ul>
            {issue.fixes.map((f, i) => (
              <li key={i}>{f}</li>
            ))}
          </ul>
        </div>
      )}
    </li>
  );
}

function SuggestionCard({ c, s }: { c: Ctx; s: StorySuggestion }) {
  return (
    <li className="card" data-testid="story-suggestion">
      <div className="finding-head">
        <span className="badge modality-asserted">{techniqueLabel(c.lang, s.technique)}</span>
        <span className="muted small">
          {chapterLabel(c.lang, s.chapter)}
          {s.targets.length > 0 && <> · {c.t.fixesIssues} </>}
          {s.targets.map((id) => (
            <a key={id} href={`#${id}`} className="story-target">
              {id}
            </a>
          ))}
        </span>
      </div>
      <p className="story-title">{s.change}</p>
      {s.why && <p className="muted">{s.why}</p>}
      {s.sample && (
        <blockquote className="story-sample">
          <span className="muted small">{c.t.sample}</span>
          <p>{s.sample}</p>
        </blockquote>
      )}
      <p className="small">
        <Link to={draftHref(c, s)} data-testid="story-draft-link">
          {c.t.draft}
        </Link>
      </p>
    </li>
  );
}

function Motives({ c }: { c: Ctx }) {
  const notes = useMemo(() => noteIndex(c.result), [c.result]);
  const groups = useMemo(() => beatsByCharacter(c.result), [c.result]);
  const cite = (id: string) => {
    const n = notes.get(id);
    return n ? `${id} ${noteKindLabel(c.lang, n.kind)}：${n.text}` : id;
  };
  return (
    <div className="story-motives">
      {[...groups.entries()].map(([who, rows]) => (
        <details key={who} open={rows.some((r) => PROBLEMS.includes(r.judgement.verdict))}>
          <summary>
            <strong>{who}</strong>{" "}
            <span className="muted small">
              {rows.map((r) => kindLabel(c.lang, r.judgement.verdict)).join(" · ")}
            </span>
          </summary>
          <ol className="story-beats">
            {rows.map(({ beat, judgement: j }) => (
              <li key={beat.id} data-testid="story-beat">
                <div>
                  <span className={`verdict verdict-${j.verdict}`}>{kindLabel(c.lang, j.verdict)}</span>{" "}
                  <span className="muted small">
                    {beat.id} · {chapterLabel(c.lang, beat.chapter)}
                  </span>{" "}
                  {beat.action}
                </div>
                <ul className="evidence-list">
                  <Quote c={c} e={{ ...beat, role: "beat" }} />
                </ul>
                {beat.uses_secret && beat.secret && (
                  <p className="small">
                    <span className="muted">{c.t.secret}</span> {beat.secret}
                  </p>
                )}
                {j.motives.length > 0 && (
                  <ul className="story-reasons">
                    {j.motives.map((m, i) => (
                      <li key={i}>
                        <span className="muted small">{c.t.motive}</span> {m.motive}
                        {m.support.map((id) => (
                          <span key={id} className="story-cite" title={cite(id)}>
                            {id}
                          </span>
                        ))}
                      </li>
                    ))}
                  </ul>
                )}
                {j.conflicts.length > 0 && (
                  <ul className="story-reasons">
                    {j.conflicts.map((x, i) => (
                      <li key={i}>
                        <span className="muted small">{c.t.conflicts}</span> {x.why}
                        <span className="story-cite" title={cite(x.note)}>
                          {x.note}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
                {j.explained_by && (
                  <p className="small">
                    <span className="muted">{c.t.explained}</span> {j.explained_why}{" "}
                    <span className="story-cite" title={cite(j.explained_by)}>
                      {j.explained_by}
                    </span>
                  </p>
                )}
                {j.reasoning && <p className="muted small">{j.reasoning}</p>}
              </li>
            ))}
          </ol>
        </details>
      ))}
    </div>
  );
}

function PacingChart({ c }: { c: Ctx }) {
  const width = 640;
  const height = 180;
  const pts = tensionCurve(c.result.pulses, width, height);
  if (pts.length === 0) return null;
  const path = pts.map((p, i) => `${i ? "L" : "M"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  const flat = new Set(
    c.result.issues.filter((i) => i.kind === "flat_stretch").flatMap((i) => i.chapters),
  );
  const dangling = new Set(
    c.result.issues.filter((i) => i.kind === "dangling_setup").flatMap((i) => i.refs),
  );
  return (
    <div className="story-pacing">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={c.t.pacing} className="story-chart">
        {[1, 2, 3, 4, 5].map((v) => {
          const y = height - 24 - ((v - 1) / 4) * (height - 48);
          return (
            <g key={v}>
              <line x1={24} x2={width - 24} y1={y} y2={y} className="grid" />
              <text x={6} y={y + 4} className="axis">
                {v}
              </text>
            </g>
          );
        })}
        <path d={path} className="curve" />
        {pts.map((p) => (
          <g key={p.chapter}>
            <circle cx={p.x} cy={p.y} r={flat.has(p.chapter) ? 7 : 5} className={flat.has(p.chapter) ? "dot flat" : "dot"} />
            {p.hook && <text x={p.x} y={p.y - 11} className="hook">▲</text>}
            <text x={p.x} y={height - 6} className="axis" textAnchor="middle">
              {p.chapter}
            </text>
          </g>
        ))}
      </svg>
      <p className="muted small">
        {c.t.tension} 1–5 · ▲ {c.t.hook}
      </p>
      {c.result.setups.length > 0 && (
        <>
          <h3>{c.t.setups}</h3>
          <ul className="story-notes">
            {c.result.setups.map((x) => {
              const open = dangling.has(x.id);
              return (
                <li key={x.id} data-testid="story-setup">
                  <span className={`verdict ${open ? "verdict-unmotivated" : "verdict-consistent"}`}>
                    {open ? c.t.unpaid : c.t.paid}
                  </span>{" "}
                  <span className="muted small">
                    {x.id} · {chapterLabel(c.lang, x.chapter)}
                    {x.key && ` · ${x.key}`}
                  </span>{" "}
                  {x.text}
                </li>
              );
            })}
          </ul>
        </>
      )}
      <ol className="story-pulses">
        {c.result.pulses.map((p) => (
          <li key={p.chapter}>
            <span className="muted small">{chapterLabel(c.lang, p.chapter)}</span> {p.summary}{" "}
            {p.emotions.map((e) => (
              <span key={e} className="chip">
                {emotionLabel(c.lang, e)}
              </span>
            ))}
          </li>
        ))}
      </ol>
    </div>
  );
}

function Dossier({ c }: { c: Ctx }) {
  const byWho = new Map<string, StoryNote[]>();
  for (const n of c.result.notes) {
    const list = byWho.get(n.character) ?? [];
    list.push(n);
    byWho.set(n.character, list);
  }
  return (
    <div className="story-dossier">
      {[...byWho.entries()].map(([who, notes]) => (
        <details key={who}>
          <summary>
            <strong>{who}</strong> <span className="muted small">{notes.length}</span>
          </summary>
          <ul className="story-notes">
            {notes.map((n) => (
              <li key={n.id}>
                <span className="chip">{noteKindLabel(c.lang, n.kind)}</span>{" "}
                <span className="muted small">
                  {n.id}
                  {n.chapter !== null && ` · ${chapterLabel(c.lang, n.chapter)}`}
                </span>{" "}
                {n.text}
                {n.quote && (
                  <ul className="evidence-list">
                    <Quote c={c} e={n} />
                  </ul>
                )}
              </li>
            ))}
          </ul>
        </details>
      ))}
    </div>
  );
}

function Checks({ c }: { c: Ctx }) {
  const rejected = new Map<string, number>();
  for (const r of c.result.rejected) {
    const k = `${r.stage}: ${r.reason}`;
    rejected.set(k, (rejected.get(k) ?? 0) + 1);
  }
  const changed = new Map<string, number>();
  for (const j of c.result.judgements) {
    if (j.verdict === j.model_verdict) continue;
    const k = `${kindLabel(c.lang, j.model_verdict)} → ${kindLabel(c.lang, j.verdict)}`;
    changed.set(k, (changed.get(k) ?? 0) + 1);
  }
  return (
    <div className="story-checks small">
      <p>
        <strong>{c.t.rejected}</strong>
      </p>
      <ul>
        {[...rejected.entries()].map(([k, n]) => (
          <li key={k}>
            {k}: {n}
          </li>
        ))}
      </ul>
      <p>
        <strong>{c.t.changed}</strong>
      </p>
      <ul>
        {[...changed.entries()].map(([k, n]) => (
          <li key={k}>
            {k}: {n}
          </li>
        ))}
      </ul>
      {c.result.errors.length > 0 && (
        <ul className="muted">
          {c.result.errors.map((e, i) => (
            <li key={i}>{e}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function StoryPage() {
  const { novel, chapters } = useWorkspace();
  const [runs, setRuns] = useState<StoryAuditRun[]>([]);
  const [run, setRun] = useState<StoryAuditRun | null>(null);
  const [llm, setLlm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"problems" | "motives" | "pacing" | "dossier" | "checks">("problems");

  const lang: Lang =
    run?.result?.language ?? (isChinese(novel.title + chapters.map((c) => c.title).join("")) ? "zh" : "en");
  const t = T[lang];

  const load = useCallback(async () => {
    const list = await api.listStoryAudits(novel.id);
    setRuns(list);
    if (list.length) setRun(await api.getStoryAudit(list[0].id));
  }, [novel.id]);

  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);

  // Poll while the run is queued or running.
  useEffect(() => {
    if (!run || run.status === "done" || run.status === "failed") return;
    const timer = window.setTimeout(async () => {
      try {
        setRun(await api.getStoryAudit(run.id));
      } catch (e) {
        setError((e as Error).message);
      }
    }, 1200);
    return () => window.clearTimeout(timer);
  }, [run]);

  const start = async () => {
    setError(null);
    try {
      const started = await api.startStoryAudit(novel.id, llm || undefined);
      setRun(await api.getStoryAudit(started.id));
      setRuns(await api.listStoryAudits(novel.id));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const ctx: Ctx | null =
    run && run.result ? { lang, t, novelId: novel.id, run, result: run.result } : null;
  const staleTitles = run
    ? chapters.filter((c) => run.stale_chapters.includes(c.id)).map((c) => c.title)
    : [];

  return (
    <main className="page story-page">
      <h1>{t.title}</h1>
      <p className="muted">{t.intro}</p>
      <div className="toolbar">
        <label>
          {t.model}{" "}
          <select value={llm} onChange={(e) => setLlm(e.target.value)} data-testid="story-llm">
            <option value="">{t.configured}</option>
            <option value="replay:ollama:qwen2.5:7b">{t.replay}</option>
            <option value="mock">{t.mock}</option>
          </select>
        </label>
        <button onClick={start} disabled={run?.status === "running" || run?.status === "queued"}>
          {t.run}
        </button>
        {runs.length > 1 && (
          <select
            value={run?.id ?? ""}
            onChange={async (e) => setRun(await api.getStoryAudit(e.target.value))}
            aria-label="runs"
          >
            {runs.map((r) => (
              <option key={r.id} value={r.id}>
                {new Date(r.created_at).toLocaleString()} · {r.llm} · {r.status}
              </option>
            ))}
          </select>
        )}
      </div>
      {error && <p className="error">{error}</p>}
      {!run && <p className="muted">{t.none}</p>}
      {run && (run.status === "queued" || run.status === "running") && (
        <p className="muted" data-testid="story-status">
          {run.status === "queued" ? t.queued : t.running}… {run.progress ?? ""}
        </p>
      )}
      {run?.status === "failed" && (
        <p className="error" data-testid="story-status">
          {t.failed}: {run.error}
        </p>
      )}
      {ctx && (
        <>
          <p className="muted small" data-testid="story-usage">
            {t.usage(run!)}
          </p>
          {run!.llm.startsWith("replay:") && <p className="banner info small">{t.replayNote}</p>}
          {staleTitles.length > 0 && (
            <p className="banner warn small">
              {t.stale} {staleTitles.join("、")}
            </p>
          )}
          <nav className="tabs">
            {(
              [
                ["problems", `${t.problems} (${ctx.result.issues.length})`],
                ["motives", t.motives],
                ["pacing", t.pacing],
                ["dossier", t.dossier],
                ["checks", t.checks],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                className={`tab ${tab === key ? "active" : ""}`}
                onClick={() => setTab(key)}
              >
                {label}
              </button>
            ))}
          </nav>
          {tab === "problems" && (
            <>
              {ctx.result.issues.length === 0 ? (
                <p className="muted">{t.noProblems}</p>
              ) : (
                <ul className="card-list">
                  {ctx.result.issues.map((i) => (
                    <IssueCard key={i.id} c={ctx} issue={i} />
                  ))}
                </ul>
              )}
              {ctx.result.suggestions.length > 0 && (
                <>
                  <h2>{t.plan}</h2>
                  <ul className="card-list">
                    {ctx.result.suggestions.map((s, i) => (
                      <SuggestionCard key={i} c={ctx} s={s} />
                    ))}
                  </ul>
                </>
              )}
            </>
          )}
          {tab === "motives" && <Motives c={ctx} />}
          {tab === "pacing" && <PacingChart c={ctx} />}
          {tab === "dossier" && <Dossier c={ctx} />}
          {tab === "checks" && <Checks c={ctx} />}
        </>
      )}
    </main>
  );
}
