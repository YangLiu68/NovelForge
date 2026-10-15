"""Embedding passages: cache-aware, idempotent, run as `embed_chapter` jobs."""

from __future__ import annotations

import re
import time
import uuid
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from novelforge.jobs import SkipJob, enqueue, handler
from novelforge.models import Chapter, EmbeddingCache, Passage
from novelforge.retrieval.embedders import Embedder, canonical, get_embedder

_SAFE_MODEL = re.compile(r"^[A-Za-z0-9_.:/-]+$")


def enqueue_chapter_embedding(session: Session, chapter: Chapter, model: str) -> None:
    model = canonical(model)
    enqueue(
        session,
        "embed_chapter",
        f"embed:{chapter.id}:{chapter.version}:{model}",
        {"chapter_id": str(chapter.id), "version": chapter.version, "model": model},
    )


def embed_passages(
    session: Session, passages: list[Passage], embedder: Embedder, batch: int = 64
) -> dict[str, Any]:
    """Fill `passage.embedding` from the cache, embedding only texts never seen before."""
    todo = [p for p in passages if p.embedding_model != embedder.name or p.embedding is None]
    hashes = sorted({p.text_hash for p in todo})
    cached: dict[str, Any] = {}
    for i in range(0, len(hashes), 500):
        rows = session.execute(
            select(EmbeddingCache.text_hash, EmbeddingCache.embedding).where(
                EmbeddingCache.model == embedder.name,
                EmbeddingCache.text_hash.in_(hashes[i : i + 500]),
            )
        ).all()
        cached.update({h: e for h, e in rows})
    missing: dict[str, str] = {}
    for p in todo:
        if p.text_hash not in cached:
            missing.setdefault(p.text_hash, p.text)
    started = time.perf_counter()
    tokens, exact = 0, True
    items = list(missing.items())
    for i in range(0, len(items), batch):
        chunk = items[i : i + batch]
        result = embedder.embed_documents([t for _, t in chunk])
        tokens += result.tokens
        exact = exact and result.tokens_exact
        rows = []
        for (h, _), vec in zip(chunk, result.vectors, strict=True):
            cached[h] = vec
            rows.append({"model": embedder.name, "text_hash": h, "dim": len(vec), "embedding": vec})
        session.execute(insert(EmbeddingCache).values(rows).on_conflict_do_nothing())
    for p in todo:
        p.embedding = cached[p.text_hash]
        p.embedding_model = embedder.name
    return {
        "passages": len(passages),
        "updated": len(todo),
        "cache_hits": len(todo) - sum(1 for p in todo if p.text_hash in missing),
        "embedded": len(missing),
        "tokens": tokens,
        "tokens_exact": exact,
        "embed_ms": round((time.perf_counter() - started) * 1000, 1),
    }


@handler("embed_chapter")
def embed_chapter_job(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    chapter = session.get(Chapter, uuid.UUID(payload["chapter_id"]))
    if chapter is None:
        raise SkipJob("chapter deleted")
    if chapter.version != payload["version"]:
        raise SkipJob(f"chapter is at version {chapter.version}, job was for {payload['version']}")
    embedder = get_embedder(payload["model"])
    passages = list(session.scalars(select(Passage).where(Passage.chapter_id == chapter.id)))
    return embed_passages(session, passages, embedder)


def hnsw_index_name(model: str, dim: int) -> str:
    import hashlib

    return f"ix_passage_hnsw_{hashlib.sha1(f'{model}|{dim}'.encode()).hexdigest()[:12]}"


def ensure_hnsw_index(session: Session, model: str, dim: int) -> str:
    """Partial HNSW index for one embedding model (cosine distance)."""
    if not _SAFE_MODEL.match(model):
        raise ValueError(f"unsafe model name {model!r}")
    name = hnsw_index_name(model, dim)
    session.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS {name} ON passage USING hnsw "
            f"((embedding::vector({int(dim)})) vector_cosine_ops) "
            f"WHERE embedding_model = '{model}'"
        )
    )
    return name


def coverage(session: Session, novel_id: uuid.UUID, model: str) -> dict[str, int]:
    row = session.execute(
        text(
            "SELECT count(*) AS total, count(*) FILTER (WHERE embedding_model = :m) AS embedded "
            "FROM passage WHERE novel_id = :n"
        ),
        {"m": model, "n": novel_id},
    ).one()
    return {"total": row.total, "embedded": row.embedded}
