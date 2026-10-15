import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import { spanHref } from "../spans";
import type { Evidence, Finding, Report } from "../types";
import { useWorkspace } from "./workspaceContext";

const KIND_LABEL: Record<string, string> = {
  attribute_conflict: "Conflicting statements",
  canon_conflict: "Contradicts character sheet",
  age_timeline: "Age vs. timeline",
  dead_character_active: "Dead character appears",
  location_conflict: "Impossible journey",
  ability_conflict: "Skill used before it is learned",
  world_rule_violation: "World rule broken",
};

const CATEGORIES = ["identity", "timeline", "location", "abilities", "world_rules"];

const PREDICATE_LABEL: Record<string, string> = {
  eye_color: "eye colour",
  hair_color: "hair colour",
  handedness: "handedness",
  birthplace: "birthplace",
  age: "age",
  location: "location",
  status: "alive / dead",
  world_rule: "world rule",
};

export const predicateLabel = (p: string) =>
  PREDICATE_LABEL[p] ?? (p.startsWith("ability:") ? `can ${p.slice(8)}` : p.replaceAll("_", " "));

export function timeLabel(e: { effective_day: number | null; time_certainty: string }) {
  return e.effective_day === null ? "time unknown" : `story day ${e.effective_day}`;
}

function EvidenceItem({ novelId, e }: { novelId: string; e: Evidence }) {
  return (
    <li className="evidence">
      <Link
        to={spanHref(novelId, e.chapter_id, e.start, e.end, e.chapter_version)}
        className="evidence-link"
        data-testid="evidence-link"
      >
        <span className="quote">“{e.quote}”</span>
      </Link>
      <span className="muted small">
        Ch {e.chapter_number} · {e.chapter_title} · {timeLabel(e)} · value “{e.value}”
        {e.modality !== "asserted" && ` · ${e.modality}`}
      </span>
    </li>
  );
}

function FindingCard({
  novelId,
  f,
  onChange,
}: {
  novelId: string;
  f: Finding;
  onChange: () => void;
}) {
  const [dismissing, setDismissing] = useState(false);
  const [reason, setReason] = useState("");
  const act = async (action: "dismiss" | "resolve" | "reopen", note?: string) => {
    await api.setFindingStatus(f.id, action, note);
    onChange();
  };
  return (
    <li className={`card finding sev-${f.severity}`} data-testid="finding">
      <div className="finding-head">
        <span className={`badge sev-${f.severity}`}>{f.severity}</span>
        <span className="finding-kind">{KIND_LABEL[f.kind] ?? f.kind}</span>
        <span className="muted small">
          {f.subject_name} · {predicateLabel(f.predicate)} · {f.category.replace("_", " ")}
          {f.detector !== "rules" && ` · ${f.detector}`}
        </span>
      </div>
      <p className="explanation">{f.explanation}</p>
      <ul className="evidence-list">
        {f.canon_value !== null && f.kind === "canon_conflict" && (
          <li className="evidence">
            <Link to={`/novels/${novelId}/characters`} className="evidence-link">
              Character sheet: {predicateLabel(f.predicate)} = “{f.canon_value}”
            </Link>
          </li>
        )}
        {f.evidence.map((e) => (
          <EvidenceItem key={`${e.chapter_id}-${e.start}`} novelId={novelId} e={e} />
        ))}
      </ul>
      <p className="suggestion">
        <strong>Suggestion:</strong> {f.suggestion}
      </p>
      {f.status_note && (
        <p className="muted small">
          {f.status === "dismissed" ? "Dismissed" : "Note"}: {f.status_note}
        </p>
      )}
      {f.status !== "preview" && (
        <div className="actions">
          {f.status === "open" && !dismissing && (
            <>
              <button className="ghost" onClick={() => setDismissing(true)}>
                Dismiss…
              </button>
              <button className="ghost" onClick={() => act("resolve", "Marked fixed")}>
                Mark resolved
              </button>
            </>
          )}
          {f.status !== "open" && (
            <button className="ghost" onClick={() => act("reopen")}>
              Reopen
            </button>
          )}
          {dismissing && (
            <form
              className="inline-form dismiss-form"
              onSubmit={(e) => {
                e.preventDefault();
                if (reason.trim()) act("dismiss", reason.trim());
              }}
            >
              <input
                aria-label="Reason"
                placeholder="Why is this fine? e.g. intentional: unreliable narrator"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
              <button type="submit" disabled={!reason.trim()}>
                Dismiss
              </button>
              <button type="button" className="ghost" onClick={() => setDismissing(false)}>
                Cancel
              </button>
            </form>
          )}
        </div>
      )}
    </li>
  );
}

export default function Contradictions() {
  const { novel, chapters } = useWorkspace();
  const [includeLow, setIncludeLow] = useState(false);
  const [status, setStatus] = useState("open");
  const [category, setCategory] = useState("");
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  // Only the newest request may update the page: a slow earlier response (e.g. the stored
  // report) must not overwrite a newer one (e.g. the preview).
  const latest = useRef(0);
  const load = useCallback(() => {
    const id = ++latest.current;
    setReport(null);
    api
      .contradictions(novel.id, includeLow, status)
      .then((r) => id === latest.current && setReport(r))
      .catch((e: Error) => id === latest.current && setError(e.message));
  }, [novel.id, includeLow, status]);

  // Re-run when chapters change (an edit re-extracts facts).
  useEffect(load, [load, chapters]);

  const judge = async () => {
    const r = await api.judgeRules(novel.id);
    setMessage(
      r.rules === 0
        ? "No world rules yet: accept some in Review (LLM extraction proposes them)."
        : `Checking ${r.rules} world rule${r.rules === 1 ? "" : "s"} with ${r.llm} in the background. Reload in a moment.`,
    );
  };

  const shown = report?.findings.filter((f) => !category || f.category === category) ?? [];
  const counts = report?.status_counts ?? {};
  return (
    <div className="page">
      <h1>Contradictions</h1>
      <p className="muted small">
        Checks extracted facts for conflicting attributes, ages and deaths that do not fit the
        timeline, impossible journeys, skills used before they are learned, and (with an LLM)
        broken world rules. Only narrator statements count unless you include uncertain ones.
      </p>
      <div className="toolbar">
        {!includeLow ? (
          <div className="segmented" role="radiogroup" aria-label="Finding status">
            {["open", "dismissed", "resolved"].map((s) => (
              <button
                key={s}
                role="radio"
                aria-checked={status === s}
                className={status === s ? "seg active" : "seg"}
                onClick={() => setStatus(s)}
              >
                {s} {counts[s] ? `(${counts[s]})` : ""}
              </button>
            ))}
          </div>
        ) : (
          <span className="muted small">Preview (not saved)</span>
        )}
        <select aria-label="Category" value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">All categories</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c.replace("_", " ")}
            </option>
          ))}
        </select>
        <button className="ghost" onClick={judge}>
          Check world rules (LLM)
        </button>
      </div>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={includeLow}
          onChange={(e) => setIncludeLow(e.target.checked)}
        />
        Include hedged statements and dialogue (“seemed”, quoted speech)
      </label>
      {message && <p className="banner info small">{message}</p>}
      {error && <p className="error">{error}</p>}
      {!report ? (
        <p className="muted">Checking…</p>
      ) : (
        <>
          <p className="muted small" data-testid="report-summary">
            {shown.length} finding{shown.length === 1 ? "" : "s"} from {report.claims_considered}{" "}
            extracted facts · confidence ≥ {report.min_confidence} · {report.took_ms} ms
          </p>
          {shown.length === 0 && <p>No contradictions here.</p>}
          <ul className="card-list">
            {shown.map((f) => (
              <FindingCard key={f.id} novelId={novel.id} f={f} onChange={load} />
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
