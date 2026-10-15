import { useCallback, useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate, useParams } from "react-router-dom";

import { api } from "../api";
import type { ChapterSummary, Novel } from "../types";
import type { WorkspaceContext } from "./workspaceContext";

export default function Workspace() {
  const { novelId } = useParams<{ novelId: string }>();
  const [novel, setNovel] = useState<Novel | null>(null);
  const [chapters, setChapters] = useState<ChapterSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [pendingJobs, setPendingJobs] = useState(0);
  const navigate = useNavigate();

  // Background indexing indicator: poll while jobs are queued or running.
  useEffect(() => {
    let timer: number | undefined;
    let cancelled = false;
    const poll = async () => {
      try {
        const stats = await api.jobs();
        const pending = (stats.counts.queued ?? 0) + (stats.counts.running ?? 0);
        if (!cancelled) setPendingJobs(pending);
        timer = window.setTimeout(poll, pending > 0 ? 1500 : 10000);
      } catch {
        timer = window.setTimeout(poll, 10000);
      }
    };
    poll();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [chapters]);

  const refreshChapters = useCallback(async () => {
    if (!novelId) return;
    setChapters(await api.listChapters(novelId));
  }, [novelId]);

  const refreshNovel = useCallback(async () => {
    if (!novelId) return;
    setNovel(await api.getNovel(novelId));
  }, [novelId]);

  useEffect(() => {
    setError(null);
    refreshNovel().catch((e: Error) => setError(e.message));
    refreshChapters().catch((e: Error) => setError(e.message));
  }, [refreshNovel, refreshChapters]);

  const addChapter = async () => {
    if (!novelId) return;
    const chapter = await api.createChapter(novelId, `Chapter ${chapters.length + 1}`);
    await refreshChapters();
    navigate(`/novels/${novelId}/chapters/${chapter.id}`);
  };

  if (error) return <main className="page">{error}</main>;
  if (!novel) return <main className="page muted">Loading…</main>;

  const ctx: WorkspaceContext = { novel, chapters, refreshChapters, refreshNovel };
  const base = `/novels/${novel.id}`;
  return (
    <div className="workspace">
      <aside className="sidebar">
        <NavLink to={base} end className="novel-title">
          {novel.title}
        </NavLink>
        <nav className="tools">
          <NavLink to={`${base}/contradictions`}>Contradictions</NavLink>
          <NavLink to={`${base}/review`}>Review</NavLink>
          <NavLink to={`${base}/canon`}>Canon</NavLink>
          <NavLink to={`${base}/search`}>Search</NavLink>
          <NavLink to={`${base}/facts`}>Extracted facts</NavLink>
          <NavLink to={`${base}/characters`}>Characters</NavLink>
        </nav>
        <div className="sidebar-heading">
          <span>Chapters</span>
          <button className="ghost small" onClick={addChapter} aria-label="Add chapter">
            + New
          </button>
        </div>
        {pendingJobs > 0 && (
          <div className="indexing" data-testid="indexing">
            Indexing… {pendingJobs} job{pendingJobs === 1 ? "" : "s"} left
          </div>
        )}
        <ol className="chapter-list">
          {chapters.map((c) => (
            <li key={c.id}>
              <NavLink to={`${base}/chapters/${c.id}`}>
                <span className="num">{c.number}</span> {c.title}
              </NavLink>
            </li>
          ))}
        </ol>
      </aside>
      <main className="content">
        <Outlet context={ctx} />
      </main>
    </div>
  );
}
