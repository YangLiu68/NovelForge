import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { ApiError, api } from "../api";
import { segments, spanHref } from "../spans";
import type { WorkflowRun } from "../types";
import { useWorkspace } from "./workspaceContext";

const RUNNING = new Set(["planning", "drafting", "revising", "critiquing"]);
const STEPS = [
  { key: "plan", label: "Plan" },
  { key: "approve", label: "Approve plan" },
  { key: "draft", label: "Draft" },
  { key: "check", label: "Check" },
  { key: "decide", label: "Apply / revise" },
];

function stepIndex(status: string): number {
  if (status.startsWith("plan")) return 0;
  if (status === "awaiting_plan_approval") return 1;
  if (status.startsWith("draft") || status.startsWith("revis")) return 2;
  if (status === "critiquing") return 3;
  return 4;
}

function RunView({ runId, onChanged }: { runId: string; onChanged: () => void }) {
  const { novel, refreshChapters } = useWorkspace();
  const [run, setRun] = useState<WorkflowRun | null>(null);
  const [live, setLive] = useState("");
  const [plan, setPlan] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState<string | null>(null);
  const sourceRef = useRef<EventSource | null>(null);

  const load = useCallback(async () => {
    const r = await api.getWorkflow(runId);
    setRun(r);
    setPlan(r.plan ?? "");
    return r;
  }, [runId]);

  const follow = useCallback(() => {
    sourceRef.current?.close();
    setLive("");
    const es = new EventSource(`/api/workflows/${runId}/stream`);
    sourceRef.current = es;
    es.onmessage = (msg) => {
      const ev = JSON.parse(msg.data);
      if (ev.type === "token") setLive((t) => t + ev.text);
      if (ev.type === "done" || ev.type === "snapshot") {
        es.close();
        load().then(onChanged);
      }
    };
    es.onerror = () => es.close();
  }, [runId, load, onChanged]);

  useEffect(() => {
    load().then((r) => {
      if (RUNNING.has(r.status)) follow();
    });
    return () => sourceRef.current?.close();
  }, [load, follow]);

  const act = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
      const r = await load();
      if (RUNNING.has(r.status)) follow();
      onChanged();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409 && e.message.includes("changed since")) {
        setConflict(e.message);
      } else {
        setError((e as Error).message);
      }
    }
  };

  if (!run) return <p className="muted">Loading…</p>;
  const running = RUNNING.has(run.status);
  const current = stepIndex(run.status);
  const issues = run.critique?.issues ?? [];
  const draftMarks: [number, number][] = issues.flatMap((i) =>
    i.draft_evidence.map((e) => [e.start, e.end] as [number, number]),
  );

  return (
    <div className="run-view" data-testid="workflow-run">
      <ol className="stepper">
        {STEPS.map((s, i) => (
          <li key={s.key} className={i < current ? "done" : i === current ? "current" : ""}>
            {s.label}
          </li>
        ))}
      </ol>
      <p className="muted small">
        <span className="badge" data-testid="workflow-status">
          {run.status.replaceAll("_", " ")}
        </span>{" "}
        · draft {Math.max(run.iteration, 1)} of {run.max_iterations} · {run.llm} · tokens{" "}
        {run.input_tokens}/{run.output_tokens}
        {run.cost_usd !== null && ` · $${run.cost_usd.toFixed(4)}`}
      </p>
      <p>
        <strong>Goal:</strong> {run.goal}
      </p>
      {error && <p className="banner error">{error}</p>}
      {run.error && <p className="banner error">Step failed: {run.error}</p>}

      {running && (
        <section className="panel">
          <div className="row">
            <h3>Writing…</h3>
            <button className="ghost danger" onClick={() => act(() => api.cancelWorkflow(run.id))}>
              Cancel
            </button>
          </div>
          <pre className="source live" data-testid="live-output">
            {live || "…"}
          </pre>
        </section>
      )}

      {(run.status.endsWith("_cancelled") || run.status.endsWith("_failed")) && (
        <div className="banner warn">
          The {run.status.split("_")[0]} step was {run.status.endsWith("_failed") ? "not completed" : "cancelled"}.
          Partial output was not used.{" "}
          <button onClick={() => act(() => api.retryWorkflow(run.id))}>Retry</button>
        </div>
      )}

      {run.status === "awaiting_plan_approval" && (
        <section className="panel">
          <h3>Plan (edit before approving)</h3>
          <textarea
            aria-label="Plan"
            className="editor plan-editor"
            value={plan}
            onChange={(e) => setPlan(e.target.value)}
          />
          <div className="actions">
            <button onClick={() => act(() => api.approvePlan(run.id, plan))}>
              Approve plan and draft
            </button>
          </div>
        </section>
      )}

      {run.draft && run.status !== "awaiting_plan_approval" && !running && (
        <>
          <section className="panel">
            <h3>
              Check: {issues.length === 0 ? "no conflicts found" : `${issues.length} issue(s)`}
            </h3>
            <p className="muted small">
              {run.critique?.draft_facts} facts read from the draft, checked against{" "}
              {run.critique?.checked_against_facts} established facts and the character sheets.
            </p>
            <ul className="card-list">
              {issues.map((i, n) => (
                <li key={n} className={`card finding sev-${i.severity}`} data-testid="critique-issue">
                  <p className="explanation">{i.explanation}</p>
                  {i.established_evidence.map((e) => (
                    <Link
                      key={`${e.chapter_id}-${e.start}`}
                      to={spanHref(novel.id, e.chapter_id, e.start, e.end, e.chapter_version)}
                      className="evidence-link"
                    >
                      Ch {e.chapter_number}: <span className="quote">“{e.quote}”</span>
                    </Link>
                  ))}
                  {i.canon_value && (
                    <p className="small muted">Character sheet: {i.canon_value}</p>
                  )}
                </li>
              ))}
            </ul>
          </section>
          <section className="panel">
            <h3>Draft</h3>
            <pre className="source" data-testid="draft-text">
              {segments(run.draft, draftMarks).map((seg, i) =>
                seg.marked ? <mark key={i}>{seg.text}</mark> : <span key={i}>{seg.text}</span>,
              )}
            </pre>
            {conflict && (
              <div className="banner warn" role="alert">
                {conflict}
                <div className="banner-actions">
                  <button
                    onClick={() =>
                      act(async () => {
                        await api.decide(run.id, "apply", true);
                        setConflict(null);
                        await refreshChapters();
                      })
                    }
                  >
                    Apply anyway (keeps the current text in history)
                  </button>
                </div>
              </div>
            )}
            {run.status === "awaiting_decision" && (
              <div className="actions">
                <button
                  onClick={() =>
                    act(async () => {
                      await api.decide(run.id, "apply");
                      await refreshChapters();
                    })
                  }
                >
                  Apply as new chapter version
                </button>
                <button
                  className="secondary"
                  disabled={run.iteration >= run.max_iterations}
                  onClick={() => act(() => api.decide(run.id, "revise"))}
                >
                  Revise ({run.max_iterations - run.iteration} left)
                </button>
                <button className="ghost danger" onClick={() => act(() => api.decide(run.id, "discard"))}>
                  Discard
                </button>
              </div>
            )}
            {run.status === "applied" && run.applied_chapter_id && (
              <p className="banner info">
                Applied as version {run.applied_version}.{" "}
                <Link to={`/novels/${novel.id}/chapters/${run.applied_chapter_id}`}>Open chapter</Link>
              </p>
            )}
          </section>
        </>
      )}
    </div>
  );
}

export default function DraftAssistant() {
  const { novel, chapters } = useWorkspace();
  const [params, setParams] = useSearchParams();
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [goal, setGoal] = useState("");
  const [chapterId, setChapterId] = useState(params.get("chapter") ?? "");
  const [maxIterations, setMaxIterations] = useState(2);
  const [error, setError] = useState<string | null>(null);
  const selected = params.get("run");

  const loadRuns = useCallback(() => {
    api.listWorkflows(novel.id).then(setRuns);
  }, [novel.id]);

  useEffect(loadRuns, [loadRuns]);

  const start = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const run = await api.startWorkflow(novel.id, {
        goal,
        chapter_id: chapterId || null,
        max_iterations: maxIterations,
      });
      setGoal("");
      setParams({ run: run.id });
      loadRuns();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <div className="page">
      <h1>Draft assistant</h1>
      <p className="muted small">
        Plan → you approve → draft → automatic consistency check against everything established →
        you apply, revise (bounded) or discard. Nothing changes the manuscript or canon until you
        apply, and applying is a normal versioned save.
      </p>
      <div className="assistant">
        <aside className="runs">
          <form onSubmit={start} className="character-form panel">
            <label>
              Goal
              <textarea
                aria-label="Goal"
                rows={3}
                value={goal}
                placeholder="e.g. Mara and Tomas reach the drowned archive and find the ledger"
                onChange={(e) => setGoal(e.target.value)}
              />
            </label>
            <label>
              Chapter
              <select
                aria-label="Target chapter"
                value={chapterId}
                onChange={(e) => setChapterId(e.target.value)}
              >
                <option value="">New chapter</option>
                {chapters.map((c) => (
                  <option key={c.id} value={c.id}>
                    Revise {c.number}: {c.title}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Drafts allowed
              <select
                aria-label="Drafts allowed"
                value={maxIterations}
                onChange={(e) => setMaxIterations(Number(e.target.value))}
              >
                {[1, 2, 3].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
            {error && <p className="error small">{error}</p>}
            <button type="submit" disabled={goal.trim().length < 3}>
              Start
            </button>
          </form>
          <ul className="run-list">
            {runs.map((r) => (
              <li key={r.id}>
                <button
                  className={r.id === selected ? "link active" : "link"}
                  onClick={() => setParams({ run: r.id })}
                >
                  {r.goal.slice(0, 48)}
                </button>
                <span className="muted small"> {r.status.replaceAll("_", " ")}</span>
              </li>
            ))}
          </ul>
        </aside>
        <div className="run-main">
          {selected ? (
            <RunView key={selected} runId={selected} onChanged={loadRuns} />
          ) : (
            <p className="muted">Start a run or pick one from the list.</p>
          )}
        </div>
      </div>
    </div>
  );
}
