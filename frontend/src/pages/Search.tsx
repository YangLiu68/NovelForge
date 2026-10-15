import { useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "../api";
import { segments, spanHref } from "../spans";
import type { SearchResult } from "../types";
import { useWorkspace } from "./workspaceContext";

export default function Search() {
  const { novel } = useWorkspace();
  const [params, setParams] = useSearchParams();
  const query = params.get("q") ?? "";
  const [input, setInput] = useState(query);
  const [result, setResult] = useState<SearchResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setInput(query);
    if (!query.trim()) {
      setResult(null);
      return;
    }
    api
      .search(novel.id, query)
      .then(setResult)
      .catch((e: Error) => setError(e.message));
  }, [novel.id, query]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setParams(input.trim() ? { q: input.trim() } : {});
  };

  return (
    <div className="page">
      <h1>Search</h1>
      <form onSubmit={submit} className="inline-form">
        <input
          aria-label="Search query"
          placeholder='Words or "a phrase"; -word to exclude'
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
        <button type="submit">Search</button>
      </form>
      <p className="muted small">
        Full-text search (PostgreSQL, English stemming) over paragraphs. Semantic and hybrid
        search come in a later milestone.
      </p>
      {error && <p className="error">{error}</p>}
      {result && (
        <>
          <p className="muted small" data-testid="search-summary">
            {result.hits.length} result{result.hits.length === 1 ? "" : "s"} · {result.took_ms} ms
          </p>
          <ul className="card-list">
            {result.hits.map((h) => (
              <li key={h.passage_id} className="card" data-testid="search-hit">
                <Link
                  to={spanHref(novel.id, h.chapter_id, h.start, h.end, h.chapter_version)}
                  className="hit-link"
                  data-testid="search-hit-link"
                >
                  Ch {h.chapter_number} · {h.chapter_title}
                </Link>
                <p className="snippet">
                  {segments(
                    h.text,
                    h.highlights.map(([s, e]) => [s - h.start, e - h.start] as [number, number]),
                  ).map((seg, i) => (seg.marked ? <mark key={i}>{seg.text}</mark> : seg.text))}
                </p>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
