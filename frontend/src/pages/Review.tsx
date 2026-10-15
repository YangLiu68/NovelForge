import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { ApiError, api } from "../api";
import { spanHref } from "../spans";
import type { ReviewItem, ReviewPage } from "../types";
import { predicateLabel, timeLabel } from "./Contradictions";
import { useWorkspace } from "./workspaceContext";

const FAMILIES = [
  { id: "", label: "All" },
  { id: "attributes", label: "Attributes" },
  { id: "presence", label: "Places & deaths" },
  { id: "abilities", label: "Abilities" },
  { id: "world", label: "Rules, events, threads" },
];

function label(item: ReviewItem): string {
  if (item.predicate.startsWith("ability:")) {
    return `${item.value} ${item.predicate.split(":")[1]}`;
  }
  return predicateLabel(item.predicate);
}

function ReviewCard({
  novelId,
  item,
  onDone,
}: {
  novelId: string;
  item: ReviewItem;
  onDone: () => void;
}) {
  const [value, setValue] = useState(item.value);
  const [conflict, setConflict] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const accept = async (replace = false) => {
    setBusy(true);
    setError(null);
    try {
      await api.acceptClaim(item.id, {
        replace_canon: replace,
        value: value !== item.value ? value : undefined,
      });
      onDone();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) setConflict(e.message);
      else setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const reject = async () => {
    setBusy(true);
    try {
      await api.rejectClaim(item.id);
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const differs = item.canon_value !== null && item.canon_value.toLowerCase() !== value.toLowerCase();
  return (
    <li className={`card review-card ${item.modality !== "asserted" ? "uncertain" : ""}`}
        data-testid="review-item">
      <div className="review-head">
        <strong>{item.subject_name}</strong>
        <span className="muted">· {label(item)}</span>
        {item.status === "proposed" ? (
          <input
            aria-label="Value"
            className="value-input"
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
        ) : (
          <span className="value">{item.value}</span>
        )}
        <span className={`badge modality-${item.modality}`}>{item.modality}</span>
        <span className="muted small">
          {Math.round(item.confidence * 100)}% · {timeLabel(item)} · {item.extractor}
        </span>
      </div>
      {item.evidence.map((e) => (
        <Link
          key={`${e.chapter_id}-${e.start}`}
          to={spanHref(novelId, e.chapter_id, e.start, e.end, e.chapter_version)}
          className="evidence-link"
        >
          Ch {e.chapter_number}: <span className="quote">“{e.quote}”</span>
        </Link>
      ))}
      {differs && !conflict && (
        <p className="small warn-text">
          Canon says “{item.canon_value}”. Accepting will ask before replacing it.
        </p>
      )}
      {conflict && (
        <div className="banner warn small" role="alert">
          {conflict}
          <div className="banner-actions">
            <button onClick={() => accept(true)} disabled={busy}>
              Replace canon
            </button>
            <button className="secondary" onClick={() => setConflict(null)}>
              Keep canon
            </button>
          </div>
        </div>
      )}
      {error && <p className="error small">{error}</p>}
      {item.status === "proposed" ? (
        <div className="actions">
          <button onClick={() => accept(false)} disabled={busy}>
            Accept
          </button>
          <button className="ghost" onClick={reject} disabled={busy}>
            Reject
          </button>
        </div>
      ) : (
        item.review_note && <p className="muted small">Note: {item.review_note}</p>
      )}
    </li>
  );
}

export default function Review() {
  const { novel } = useWorkspace();
  const [status, setStatus] = useState("proposed");
  const [family, setFamily] = useState("");
  const [page, setPage] = useState<ReviewPage | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [llm, setLlm] = useState<string | null>(null);

  const load = useCallback(
    () => api.review(novel.id, status, family || undefined).then(setPage),
    [novel.id, status, family],
  );

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    api.llmConfig().then((c) => setLlm(c.llm)).catch(() => setLlm(null));
  }, []);

  const acceptVisible = async () => {
    if (!page) return;
    const ids = page.items.filter((i) => i.modality === "asserted").map((i) => i.id);
    const r = await api.acceptBatch(novel.id, ids);
    setMessage(
      `Accepted ${r.accepted.length}; skipped ${r.skipped.length} that would change canon.`,
    );
    load();
  };

  const runExtraction = async () => {
    const r = await api.extract(novel.id);
    setMessage(`Queued LLM extraction (${r.llm}) for ${r.queued_for} chapters.`);
  };

  return (
    <div className="page">
      <h1>Review</h1>
      <p className="muted small">
        Extracted facts are proposals. Nothing reaches the character sheet, timeline or world
        rules until you accept it, and accepting never silently overwrites canon. Decisions are
        remembered when a chapter is edited and re-extracted.
      </p>
      <div className="toolbar">
        <div className="segmented" role="radiogroup" aria-label="Status">
          {["proposed", "accepted", "rejected"].map((s) => (
            <button
              key={s}
              role="radio"
              aria-checked={status === s}
              className={status === s ? "seg active" : "seg"}
              onClick={() => setStatus(s)}
            >
              {s} {page?.counts[s] ? `(${page.counts[s]})` : ""}
            </button>
          ))}
        </div>
        <select aria-label="Kind" value={family} onChange={(e) => setFamily(e.target.value)}>
          {FAMILIES.map((f) => (
            <option key={f.id} value={f.id}>
              {f.label}
            </option>
          ))}
        </select>
        <div className="actions">
          {status === "proposed" && (
            <button className="secondary" onClick={acceptVisible} disabled={!page?.items.length}>
              Accept all shown (asserted only)
            </button>
          )}
          <button className="ghost" onClick={runExtraction}>
            Run LLM extraction{llm ? ` (${llm})` : ""}
          </button>
        </div>
      </div>
      {message && <p className="banner info small">{message}</p>}
      {!page ? (
        <p className="muted">Loading…</p>
      ) : page.items.length === 0 ? (
        <p>Nothing here.</p>
      ) : (
        <>
          <p className="muted small">
            Showing {page.items.length} of {page.total}
          </p>
          <ul className="card-list">
            {page.items.map((item) => (
              <ReviewCard key={item.id} novelId={novel.id} item={item} onDone={load} />
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
