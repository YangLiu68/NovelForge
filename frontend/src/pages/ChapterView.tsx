import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { ApiError, api } from "../api";
import { parseSpan, segments } from "../spans";
import type { Chapter, Revision, RevisionSummary } from "../types";
import { useWorkspace } from "./workspaceContext";

type Mode = "edit" | "preview" | "source";

interface Draft {
  title: string;
  body: string;
  storyDay: string;
  storyLabel: string;
}

const toDraft = (c: Chapter): Draft => ({
  title: c.title,
  body: c.body,
  storyDay: c.story_day === null ? "" : String(c.story_day),
  storyLabel: c.story_time_label ?? "",
});

export default function ChapterView() {
  const { chapterId } = useParams<{ chapterId: string }>();
  const [params, setParams] = useSearchParams();
  const span = parseSpan(params);
  const { novel, refreshChapters } = useWorkspace();
  const navigate = useNavigate();

  const [chapter, setChapter] = useState<Chapter | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [mode, setMode] = useState<Mode>(span ? "source" : "edit");
  const [conflict, setConflict] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [revisions, setRevisions] = useState<RevisionSummary[] | null>(null);
  const [viewing, setViewing] = useState<Revision | null>(null);
  const markRef = useRef<HTMLElement | null>(null);

  const load = useCallback(async () => {
    if (!chapterId) return;
    const c = await api.getChapter(chapterId);
    setChapter(c);
    setDraft(toDraft(c));
    setConflict(null);
    setViewing(null);
    setRevisions(null);
  }, [chapterId]);

  useEffect(() => {
    setError(null);
    setStatus(null);
    load().catch((e: Error) => setError(e.message));
  }, [load]);

  // Following a citation link switches to the source view.
  const spanKey = span ? `${span.start}-${span.end}` : "";
  useEffect(() => {
    if (spanKey) {
      setMode("source");
      setViewing(null);
    }
  }, [spanKey, chapterId]);

  useEffect(() => {
    if (mode === "source" && markRef.current) {
      markRef.current.scrollIntoView({ block: "center" });
    }
  }, [mode, spanKey, chapter]);

  const dirty =
    !!chapter &&
    !!draft &&
    (draft.title !== chapter.title ||
      draft.body !== chapter.body ||
      draft.storyDay !== (chapter.story_day === null ? "" : String(chapter.story_day)) ||
      draft.storyLabel !== (chapter.story_time_label ?? ""));

  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const save = useCallback(
    async (overwrite = false) => {
      if (!chapter || !draft) return;
      const day = draft.storyDay.trim();
      if (day !== "" && !/^-?\d+$/.test(day)) {
        setError("Story day must be a whole number (days since the story's day 0) or blank.");
        return;
      }
      setSaving(true);
      setError(null);
      try {
        // "Save mine anyway" saves on top of the newest version; the version it replaces stays
        // in the revision history.
        const version = overwrite ? (await api.getChapter(chapter.id)).version : chapter.version;
        const updated = await api.updateChapter(chapter.id, version, {
          title: draft.title,
          body: draft.body,
          story_day: day === "" ? null : Number(day),
          story_time_label: draft.storyLabel.trim() || null,
        });
        setChapter(updated);
        setDraft(toDraft(updated));
        setConflict(null);
        setStatus(`Saved version ${updated.version}`);
        setRevisions(null);
        await refreshChapters();
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) setConflict(e.message);
        else setError((e as Error).message);
      } finally {
        setSaving(false);
      }
    },
    [chapter, draft, refreshChapters],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "s") {
        e.preventDefault();
        if (dirty && !saving) save();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [dirty, saving, save]);

  const remove = async () => {
    if (!chapter) return;
    if (!window.confirm(`Delete chapter ${chapter.number} “${chapter.title}”?`)) return;
    await api.deleteChapter(chapter.id);
    await refreshChapters();
    navigate(`/novels/${novel.id}`);
  };

  const toggleHistory = async () => {
    if (!chapter) return;
    setRevisions(revisions ? null : await api.listRevisions(chapter.id));
  };

  const openRevision = async (version: number) => {
    if (!chapter) return;
    setViewing(await api.getRevision(chapter.id, version));
    setMode("source");
  };

  const clearSpan = () => {
    params.delete("start");
    params.delete("end");
    params.delete("v");
    setParams(params, { replace: true });
  };

  if (error && !chapter) return <div className="page error">{error}</div>;
  if (!chapter || !draft) return <div className="page muted">Loading…</div>;

  const sourceText = viewing ? viewing.body : chapter.body;
  const ranges: [number, number][] = span && !viewing ? [[span.start, span.end]] : [];
  const staleSpan = span && !viewing && span.version !== null && span.version !== chapter.version;

  return (
    <div className="page chapter">
      <div className="chapter-head">
        <span className="chapter-num">Chapter {chapter.number}</span>
        <input
          className="title-input"
          aria-label="Chapter title"
          value={draft.title}
          onChange={(e) => setDraft({ ...draft, title: e.target.value })}
        />
      </div>
      <div className="meta-row">
        <label>
          Story day
          <input
            aria-label="Story day"
            className="day-input"
            inputMode="numeric"
            placeholder="unknown"
            value={draft.storyDay}
            onChange={(e) => setDraft({ ...draft, storyDay: e.target.value })}
          />
        </label>
        <label className="grow">
          Time label
          <input
            aria-label="Time label"
            placeholder="e.g. Day 3, or Five years later"
            value={draft.storyLabel}
            onChange={(e) => setDraft({ ...draft, storyLabel: e.target.value })}
          />
        </label>
        <span className="muted small">
          v{chapter.version} · {chapter.word_count.toLocaleString()}{" "}
          {chapter.length_unit === "characters" ? "characters" : "words"}
        </span>
      </div>

      <div className="toolbar">
        <div className="tabs" role="tablist">
          {(["edit", "preview", "source"] as Mode[]).map((m) => (
            <button
              key={m}
              role="tab"
              aria-selected={mode === m}
              className={mode === m ? "tab active" : "tab"}
              onClick={() => {
                setMode(m);
                if (m !== "source") setViewing(null);
              }}
            >
              {m === "edit" ? "Write" : m === "preview" ? "Preview" : "Source"}
            </button>
          ))}
        </div>
        <div className="actions">
          {status && !dirty && <span className="muted small">{status}</span>}
          {dirty && <span className="dirty small">Unsaved changes</span>}
          <button onClick={() => save()} disabled={!dirty || saving}>
            {saving ? "Saving…" : "Save"}
          </button>
          <button className="ghost" onClick={toggleHistory}>
            History
          </button>
          <button
            className="ghost"
            onClick={() => navigate(`/novels/${novel.id}/draft?chapter=${chapter.id}`)}
          >
            Draft with assistant
          </button>
          <button className="ghost danger" onClick={remove}>
            Delete
          </button>
        </div>
      </div>

      {conflict && (
        <div className="banner warn" role="alert">
          <strong>Not saved.</strong> {conflict}
          <div className="banner-actions">
            <button onClick={() => load()}>Load latest (discard my edits)</button>
            <button className="secondary" onClick={() => save(true)}>
              Save mine anyway
            </button>
          </div>
        </div>
      )}
      {error && <div className="banner error">{error}</div>}

      {revisions && (
        <div className="panel revisions">
          <h3>History</h3>
          <ul>
            {revisions.map((r) => (
              <li key={r.id}>
                <button className="link" onClick={() => openRevision(r.version)}>
                  Version {r.version}
                </button>{" "}
                <span className="muted small">{new Date(r.created_at).toLocaleString()}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {mode === "edit" && (
        <textarea
          className="editor"
          aria-label="Chapter text"
          value={draft.body}
          spellCheck
          onChange={(e) => setDraft({ ...draft, body: e.target.value })}
          placeholder="Write in Markdown…"
        />
      )}

      {mode === "preview" && (
        <article className="prose">
          <ReactMarkdown>{draft.body}</ReactMarkdown>
        </article>
      )}

      {mode === "source" && (
        <>
          {viewing && (
            <div className="banner info">
              Viewing version {viewing.version} (read-only).{" "}
              <button
                className="link"
                onClick={() => {
                  setDraft({ ...draft, body: viewing.body });
                  setViewing(null);
                  setMode("edit");
                }}
              >
                Copy this text into the editor
              </button>
            </div>
          )}
          {ranges.length > 0 && (
            <div className="banner info">
              Showing the cited span (characters {span!.start}–{span!.end}).{" "}
              <button className="link" onClick={clearSpan}>
                Clear highlight
              </button>
              {staleSpan && (
                <div className="small">
                  The citation was made against version {span!.version}; this chapter is now
                  version {chapter.version}, so the highlight may have shifted.
                </div>
              )}
              {dirty && (
                <div className="small">
                  You have unsaved edits; the source view shows the saved text.
                </div>
              )}
            </div>
          )}
          <pre className="source" data-testid="chapter-source">
            {segments(sourceText, ranges).map((seg, i) =>
              seg.marked ? (
                <mark key={i} ref={markRef} data-testid="span-highlight">
                  {seg.text}
                </mark>
              ) : (
                <span key={i}>{seg.text}</span>
              ),
            )}
          </pre>
        </>
      )}
    </div>
  );
}
