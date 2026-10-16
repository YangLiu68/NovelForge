"""Retrieval over passages: keyword, full-text, vector, hybrid (RRF) and hybrid + rerank.

Modes
- keyword: web-search syntax (`"phrase"`, `-word`, `or`), all words required. Interactive search.
- fts: any query word may match (OR of stemmed lexemes), ranked by `ts_rank_cd`. Baseline.
- vector: cosine distance between the query embedding and passage embeddings.
- hybrid: reciprocal rank fusion of fts and vector candidates (k = 60).
- hybrid_rerank: hybrid candidates re-scored by a reranker.

Every result carries the stage ranks that produced it, so the UI can show why a passage was
returned, and every call reports per-stage latency.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from novelforge.core.text import cjk_query_spans, cjk_search_text
from novelforge.retrieval.embedders import Embedder
from novelforge.retrieval.rerankers import Reranker

Mode = Literal["keyword", "fts", "vector", "hybrid", "hybrid_rerank"]
MODES: tuple[str, ...] = ("keyword", "fts", "vector", "hybrid", "hybrid_rerank")
RRF_K = 60
START_MARK = ""
STOP_MARK = ""

# The query's English-stemmed lexemes, quoted and OR-ed, parsed with the 'simple' config so they
# are not stemmed twice. A query with only stop words yields a lexeme that matches nothing.
OR_QUERY = (
    "to_tsquery('simple', coalesce(nullif(array_to_string(ARRAY("
    "SELECT quote_literal(l) FROM unnest(tsvector_to_array(to_tsvector('english', :query))) l"
    "), ' | '), ''), '''___'''))"
)

_KEYWORD = text(
    """
    SELECT p.id, ts_rank_cd(p.tsv, q) AS score
    FROM passage p, websearch_to_tsquery('english', :query) q
    WHERE p.novel_id = :novel_id AND p.tsv @@ q
    ORDER BY score DESC, p.chapter_id, p.ordinal
    LIMIT :limit
    """
)

# OR over the query's stemmed lexemes: a question like "What colour are Mara's eyes?" should
# match passages that contain some of its words, not only passages that contain all of them.
_FTS = text(
    f"""
    WITH q AS (SELECT {OR_QUERY} AS q)
    SELECT p.id, ts_rank_cd(p.tsv, q.q, 1) AS score
    FROM passage p, q
    WHERE p.novel_id = :novel_id AND p.tsv @@ q.q
    ORDER BY score DESC, p.chapter_id, p.ordinal
    LIMIT :limit
    """
)


def _vector_sql(dim: int, exact: bool) -> str:
    # Exact search materialises the novel's passages first, so the planner cannot use the global
    # HNSW index and silently drop matches that fall outside the index's candidate list.
    if exact:
        return f"""
            WITH cand AS MATERIALIZED (
                SELECT id, embedding FROM passage
                WHERE novel_id = :novel_id AND embedding_model = :model
            )
            SELECT id, 1 - (embedding::vector({dim}) <=> CAST(:qvec AS vector({dim}))) AS score
            FROM cand
            ORDER BY embedding::vector({dim}) <=> CAST(:qvec AS vector({dim}))
            LIMIT :limit
        """
    return f"""
        SELECT id, 1 - (embedding::vector({dim}) <=> CAST(:qvec AS vector({dim}))) AS score
        FROM passage
        WHERE novel_id = :novel_id AND embedding_model = :model
        ORDER BY embedding::vector({dim}) <=> CAST(:qvec AS vector({dim}))
        LIMIT :limit
    """


_HYDRATE = text(
    f"""
    SELECT p.id, p.chapter_id, p.start, p.text, c.number, c.title, c.version,
           ts_headline('english', p.text, q,
                       'StartSel=' || :start_mark || ', StopSel=' || :stop_mark
                       || ', HighlightAll=true') AS marked
    FROM passage p
    JOIN chapter c ON c.id = p.chapter_id,
         {OR_QUERY} q
    WHERE p.id = ANY(:ids)
    """
)


@dataclass
class Hit:
    passage_id: str
    chapter_id: str
    chapter_number: int
    chapter_title: str
    chapter_version: int
    start: int
    end: int
    text: str
    score: float
    highlights: list[tuple[int, int]] = field(default_factory=list)
    ranks: dict[str, int] = field(default_factory=dict)  # stage -> 1-based rank


@dataclass
class SearchResult:
    hits: list[Hit]
    timings_ms: dict[str, float]
    query_tokens: int = 0
    rerank_pairs: int = 0


def parse_marked(marked: str, original: str) -> list[tuple[int, int]] | None:
    """Offsets (relative to `original`) of marked words; None if the text does not round-trip."""
    plain: list[str] = []
    spans: list[tuple[int, int]] = []
    pos = 0
    open_at: int | None = None
    for ch in marked:
        if ch == START_MARK:
            open_at = pos
        elif ch == STOP_MARK:
            if open_at is not None and pos > open_at:
                spans.append((open_at, pos))
            open_at = None
        else:
            plain.append(ch)
            pos += 1
    return spans if "".join(plain) == original else None


def _ranked(session: Session, sql, params: dict) -> list[tuple[str, float]]:
    return [(str(r.id), float(r.score)) for r in session.execute(sql, params)]


def search(
    session: Session,
    novel_id: uuid.UUID,
    query: str,
    mode: Mode = "hybrid",
    k: int = 10,
    embedder: Embedder | None = None,
    reranker: Reranker | None = None,
    candidates: int = 50,
    rerank_depth: int = 30,
    exact: bool = True,
) -> SearchResult:
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")
    if mode in ("vector", "hybrid", "hybrid_rerank") and embedder is None:
        raise ValueError(f"mode {mode!r} needs an embedder")
    if mode == "hybrid_rerank" and reranker is None:
        raise ValueError("mode 'hybrid_rerank' needs a reranker")
    timings: dict[str, float] = {}
    total_start = time.perf_counter()
    # Chinese in the query is matched as bigrams, like Chinese passages are indexed.
    base = {"novel_id": novel_id, "query": cjk_search_text(query) or query}
    depth = k if mode in ("keyword", "fts", "vector") else candidates
    lists: dict[str, list[tuple[str, float]]] = {}
    query_tokens = 0

    if mode == "keyword":
        t = time.perf_counter()
        lists["keyword"] = _ranked(session, _KEYWORD, {**base, "limit": depth})
        timings["keyword"] = (time.perf_counter() - t) * 1000
    if mode in ("fts", "hybrid", "hybrid_rerank"):
        t = time.perf_counter()
        lists["fts"] = _ranked(session, _FTS, {**base, "limit": depth})
        timings["fts"] = (time.perf_counter() - t) * 1000
    if mode in ("vector", "hybrid", "hybrid_rerank"):
        assert embedder is not None
        t = time.perf_counter()
        q = embedder.embed_query(query)
        query_tokens = q.tokens
        timings["embed_query"] = (time.perf_counter() - t) * 1000
        t = time.perf_counter()
        sql = text(_vector_sql(embedder.dim, exact))
        lists["vector"] = _ranked(
            session,
            sql,
            {
                "novel_id": novel_id,
                "model": embedder.name,
                "qvec": str(q.vectors[0]),
                "limit": depth,
            },
        )
        timings["vector"] = (time.perf_counter() - t) * 1000

    ranks: dict[str, dict[str, int]] = {}
    for stage, items in lists.items():
        for i, (pid, _) in enumerate(items):
            ranks.setdefault(pid, {})[stage] = i + 1

    if mode in ("keyword", "fts", "vector"):
        ordered = [(pid, score) for pid, score in lists[mode]]
    else:
        fused = {
            pid: sum(1.0 / (RRF_K + r) for r in stage_ranks.values())
            for pid, stage_ranks in ranks.items()
        }
        ordered = sorted(fused.items(), key=lambda kv: (-kv[1], kv[0]))
        for i, (pid, _) in enumerate(ordered):
            ranks[pid]["rrf"] = i + 1

    rerank_pairs = 0
    if mode == "hybrid_rerank":
        assert reranker is not None
        head = ordered[:rerank_depth]
        texts = _texts(session, [pid for pid, _ in head])
        t = time.perf_counter()
        scores = reranker.score(query, [texts[pid] for pid, _ in head])
        timings["rerank"] = (time.perf_counter() - t) * 1000
        rerank_pairs = len(head)
        ordered = sorted(
            zip([pid for pid, _ in head], scores, strict=True), key=lambda kv: (-kv[1], kv[0])
        )
        for i, (pid, _) in enumerate(ordered):
            ranks[pid]["rerank"] = i + 1

    top = ordered[:k]
    t = time.perf_counter()
    hits = _hydrate(session, base["query"], top, ranks, query)
    timings["hydrate"] = (time.perf_counter() - t) * 1000
    timings["total"] = (time.perf_counter() - total_start) * 1000
    return SearchResult(
        hits=hits,
        timings_ms={k: round(v, 2) for k, v in timings.items()},
        query_tokens=query_tokens,
        rerank_pairs=rerank_pairs,
    )


def _texts(session: Session, ids: list[str]) -> dict[str, str]:
    if not ids:
        return {}
    rows = session.execute(
        text("SELECT id, text FROM passage WHERE id = ANY(:ids)"),
        {"ids": [uuid.UUID(i) for i in ids]},
    )
    return {str(r.id): r.text for r in rows}


def _hydrate(
    session: Session,
    query: str,
    top: list[tuple[str, float]],
    ranks: dict[str, dict[str, int]],
    original_query: str | None = None,
) -> list[Hit]:
    if not top:
        return []
    rows = {
        str(r.id): r
        for r in session.execute(
            _HYDRATE,
            {
                "ids": [uuid.UUID(pid) for pid, _ in top],
                "query": query,
                "start_mark": START_MARK,
                "stop_mark": STOP_MARK,
            },
        )
    }
    hits = []
    for pid, score in top:
        r = rows.get(pid)
        if r is None:  # deleted between ranking and hydration
            continue
        rel = parse_marked(r.marked, r.text) or []
        if original_query is not None and r.text != (cjk_search_text(r.text) or r.text):
            # ts_headline cannot mark bigrams inside unspaced Chinese: mark the query's runs.
            rel = sorted(set(rel) | set(cjk_query_spans(original_query, r.text)))
        hits.append(
            Hit(
                passage_id=pid,
                chapter_id=str(r.chapter_id),
                chapter_number=r.number,
                chapter_title=r.title,
                chapter_version=r.version,
                start=r.start,
                end=r.start + len(r.text),
                text=r.text,
                score=round(float(score), 6),
                highlights=[(r.start + s, r.start + e) for s, e in rel],
                ranks=ranks.get(pid, {}),
            )
        )
    return hits
