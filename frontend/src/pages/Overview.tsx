import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { ApiError, api } from "../api";
import { useWorkspace } from "./workspaceContext";

export default function Overview() {
  const { novel, chapters, refreshNovel } = useWorkspace();
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(novel.title);
  const [synopsis, setSynopsis] = useState(novel.synopsis);
  const [error, setError] = useState<string | null>(null);
  const words = chapters.reduce((n, c) => n + c.word_count, 0);

  useEffect(() => {
    refreshNovel();
  }, [refreshNovel]);

  const startEdit = () => {
    setTitle(novel.title);
    setSynopsis(novel.synopsis);
    setError(null);
    setEditing(true);
  };

  const save = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await api.updateNovel(novel.id, novel.version, { title, synopsis });
      await refreshNovel();
      setEditing(false);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) await refreshNovel();
      setError((err as Error).message);
    }
  };

  return (
    <div className="page">
      {editing ? (
        <form onSubmit={save} className="character-form">
          <label>
            Title
            <input aria-label="Novel title" value={title} onChange={(e) => setTitle(e.target.value)} />
          </label>
          <label>
            Synopsis
            <textarea
              aria-label="Synopsis"
              rows={4}
              value={synopsis}
              onChange={(e) => setSynopsis(e.target.value)}
            />
          </label>
          {error && <p className="error">{error}</p>}
          <div className="form-actions">
            <button type="submit" disabled={!title.trim()}>
              Save
            </button>
            <button type="button" className="ghost" onClick={() => setEditing(false)}>
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <>
          <div className="row">
            <h1>{novel.title}</h1>
            <button className="ghost" onClick={startEdit}>
              Edit details
            </button>
          </div>
          {novel.synopsis && <p className="synopsis">{novel.synopsis}</p>}
        </>
      )}
      <p className="muted">
        {chapters.length} chapters · {words.toLocaleString()} words · {novel.character_count}{" "}
        characters
      </p>
      <div className="quick-links">
        <Link to="contradictions" className="button">
          Check contradictions
        </Link>
        <Link to="search" className="button secondary">
          Search the manuscript
        </Link>
      </div>
    </div>
  );
}
