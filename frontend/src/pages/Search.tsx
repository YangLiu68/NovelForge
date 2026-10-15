import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "../api";
import { segments, spanHref } from "../spans";
import type { SearchMode, SearchResult } from "../types";
import { useWorkspace } from "./workspaceContext";

const MODES: { id: SearchMode; label: string; help: string }[] = [
  {
    id: "hybrid",
    label: "Hybrid",
    help: "Word matches and meaning, fused with reciprocal rank fusion.",
  },
  {
    id: "hybrid_rerank",
    label: "Hybrid + rerank",
    help: "Hybrid candidates re-scored by a reranker.",
  },
  { id: "vector", label: "Meaning", help: "Embedding similarity only." },
  { id: "fts", label: "Any word", help: "Passages containing any of the words, best first." },
  {
    id: "keyword",
    label: "Exact",
    help: 'All words required. Supports "a phrase", -exclude and or.',
  },
];

const STAGE_LABEL: Record<string, string> = {
  keyword: "exact",
  fts: "words",
  vector: "meaning",
  rrf: "fused",
  rerank: "reranked",
};

const isMode = (m: string | null): m is SearchMode => MODES.some((x) => x.id === m);

export default function Search() {
  const { novel } = useWorkspace();
  const [params, setParams] = useSearchParams();
  const query = params.get("q") ?? "";
  const modeParam = params.get("mode");
  const mode: SearchMode = isMode(modeParam) ? modeParam : "hybrid";
  const [input, setInput] = useState(query);
  const [result, setResult] = useState<SearchResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const latest = useRef(0);

  // Sync the box from the URL only when the query itself changes, so switching modes keeps
  // whatever the user is typing.
  useEffect(() => {
    setInput(query);
  }, [query]);

  useEffect(() => {
    if (!query.trim()) {
      setResult(null);
      return;
    }
    const id = ++latest.current;
    setLoading(true);
    setError(null);
    api
      .search(novel.id, query, mode)
      .then((r) => id === latest.current && setResult(r))
      .catch((e: Error) => id === latest.current && setError(e.message))
      .finally(() => id === latest.current && setLoading(false));
  }, [novel.id, query, mode]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setParams(input.trim() ? { q: input.trim(), mode } : { mode });
  };

  const setMode = (m: SearchMode) => {
    const q = input.trim() || query;
    setParams(q ? { q, mode: m } : { mode: m });
  };
  const cov = result?.index_coverage;

  return (
    <div className="page">
      <h1>Search</h1>
      <form onSubmit={submit} className="inline-form">
        <input
          aria-label="Search query"
          placeholder="Ask a question or type words, e.g. What colour are Mara's eyes?"
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
        <button type="submit">Search</button>
      </form>
      <div className="segmented" role="radiogroup" aria-label="Search mode">
        {MODES.map((m) => (
          <button
            key={m.id}
            role="radio"
            aria-checked={mode === m.id}
            className={mode === m.id ? "seg active" : "seg"}
            title={m.help}
            onClick={() => setMode(m.id)}
          >
            {m.label}
          </button>
        ))}
      </div>
      <p className="muted small">{MODES.find((m) => m.id === mode)?.help}</p>
      {cov && cov.embedded < cov.total && (
        <p className="banner info small">
          Meaning index is still building: {cov.embedded} of {cov.total} paragraphs embedded.
          Results from the meaning side are incomplete until it finishes.
        </p>
      )}
      {error && <p className="error">{error}</p>}
      {loading && !result && <p className="muted">Searching…</p>}
      {result && (
        <>
          <p className="muted small" data-testid="search-summary">
            {result.hits.length} result{result.hits.length === 1 ? "" : "s"} · {result.took_ms} ms
            {result.embedder && ` · embedder ${result.embedder}`}
            {result.reranker && ` · reranker ${result.reranker}`}
          </p>
          <ul className="card-list">
            {result.hits.map((h) => (
              <li key={h.passage_id} className="card" data-testid="search-hit">
                <div className="hit-head">
                  <Link
                    to={spanHref(novel.id, h.chapter_id, h.start, h.end, h.chapter_version)}
                    className="hit-link"
                    data-testid="search-hit-link"
                  >
                    Ch {h.chapter_number} · {h.chapter_title}
                  </Link>
                  <span className="why" title="Rank of this paragraph in each stage">
                    {Object.entries(h.ranks).map(([stage, rank]) => (
                      <span key={stage} className="chip">
                        {STAGE_LABEL[stage] ?? stage} #{rank}
                      </span>
                    ))}
                  </span>
                </div>
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
