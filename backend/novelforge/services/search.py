"""Basic full-text search over passages (PostgreSQL `websearch_to_tsquery` + `ts_rank_cd`).

Highlights come from `ts_headline(... HighlightAll=true)` with private-use marker characters,
so the highlighted words are exactly the ones Postgres matched (after stemming), and their
offsets are mapped back into the chapter body.
"""

import time
import uuid
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.orm import Session

START_MARK = ""
STOP_MARK = ""

_SQL = text(
    """
    SELECT p.id, p.chapter_id, p.start, p.text, c.number, c.title, c.version,
           ts_rank_cd(p.tsv, q) AS score,
           ts_headline('english', p.text, q,
                       'StartSel=' || :start_mark || ', StopSel=' || :stop_mark
                       || ', HighlightAll=true') AS marked
    FROM passage p
    JOIN chapter c ON c.id = p.chapter_id,
         websearch_to_tsquery('english', :query) q
    WHERE p.novel_id = :novel_id AND p.tsv @@ q
    ORDER BY score DESC, c.number, p.ordinal
    LIMIT :limit
    """
)


@dataclass
class SearchHit:
    passage_id: str
    chapter_id: str
    chapter_number: int
    chapter_title: str
    chapter_version: int
    start: int
    end: int
    text: str
    score: float
    highlights: list[tuple[int, int]] = field(default_factory=list)  # absolute body offsets


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


def search_passages(session: Session, novel_id: uuid.UUID, query: str,
                    limit: int = 20) -> tuple[list[SearchHit], float]:
    started = time.perf_counter()
    rows = session.execute(
        _SQL,
        {"novel_id": novel_id, "query": query, "limit": limit,
         "start_mark": START_MARK, "stop_mark": STOP_MARK},
    ).all()
    hits = []
    for r in rows:
        rel = parse_marked(r.marked, r.text) or []
        hits.append(
            SearchHit(
                passage_id=str(r.id), chapter_id=str(r.chapter_id), chapter_number=r.number,
                chapter_title=r.title, chapter_version=r.version, start=r.start,
                end=r.start + len(r.text), text=r.text, score=float(r.score),
                highlights=[(r.start + s, r.start + e) for s, e in rel],
            )
        )
    return hits, (time.perf_counter() - started) * 1000
