"""Load test on a generated corpus: throughput, latency, memory and storage.

Everything is measured in this process against a fresh database; nothing is extrapolated.
Peak memory is this Python process's maximum resident set size (the API/worker side), not the
PostgreSQL server's.
"""

from __future__ import annotations

import platform
import resource
import statistics
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

from novelforge.bench.retrieval_eval import _git_commit, migrate, percentile, recreate_database
from novelforge.core.extraction import EXTRACTOR
from novelforge.models import Chapter, Claim, Passage
from novelforge.retrieval.embedders import get_embedder
from novelforge.retrieval.index import embed_passages, ensure_hnsw_index
from novelforge.retrieval.search import search
from novelforge.services import workspace
from novelforge.services.findings import refresh_findings
from novelforge.services.graph import character_graph, timeline
from novelforge.services.importer import import_folder


def _peak_rss_mb() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(peak / (1024 * 1024) if sys.platform == "darwin" else peak / 1024, 1)


def _timed(fn, repeat: int) -> dict[str, float]:
    samples = []
    for _ in range(repeat):
        t = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t) * 1000)
    return {
        "p50": round(percentile(samples, 0.5), 2),
        "p95": round(percentile(samples, 0.95), 2),
        "mean": round(statistics.fmean(samples), 2),
        "n": repeat,
    }


def run(
    corpus: Path,
    base_url: URL,
    embedder_spec: str = "hash",
    queries: int = 50,
    database: str = "novelforge_bench_load",
) -> dict[str, Any]:
    gt = yaml.safe_load((corpus / "ground_truth.yaml").read_text(encoding="utf-8"))
    url = recreate_database(base_url, database)
    migrate(url)
    engine = create_engine(url)
    maker = sessionmaker(bind=engine, expire_on_commit=False)
    embedder = get_embedder(embedder_spec)
    report: dict[str, Any] = {
        "corpus": corpus.name,
        "generator": gt.get("generator"),
        "embedder": embedder.name,
    }
    with maker() as session:
        t = time.perf_counter()
        novel = import_folder(session, corpus).novel
        session.commit()
        import_s = time.perf_counter() - t
        nid = novel.id
        chapters = session.scalar(
            select(func.count()).select_from(Chapter).where(Chapter.novel_id == nid)
        )
        words = session.scalar(
            select(
                func.sum(func.array_length(func.regexp_split_to_array(Chapter.body, r"\s+"), 1))
            ).where(Chapter.novel_id == nid)
        )
        claims = session.scalar(
            select(func.count()).select_from(Claim).where(Claim.novel_id == nid)
        )
        passages = list(session.scalars(select(Passage).where(Passage.novel_id == nid)))
        report["size"] = {
            "chapters": chapters,
            "words": int(words or 0),
            "passages": len(passages),
            "claims": claims,
        }
        report["import"] = {
            "seconds": round(import_s, 2),
            "chapters_per_s": round(chapters / import_s, 1),
            "note": "includes passage split, scenes, rule extraction, revisions",
            "extractor": EXTRACTOR,
        }

        t = time.perf_counter()
        stats = embed_passages(session, passages, embedder)
        session.commit()
        embed_s = time.perf_counter() - t
        report["index"] = {
            "seconds": round(embed_s, 2),
            "passages_per_s": round(len(passages) / max(embed_s, 1e-9), 1),
            **stats,
        }

        qs = [q["query"] for q in gt["queries"][:queries]]

        def per_mode(mode: str, exact: bool = True):
            it = iter(qs * 10)
            return _timed(
                lambda: search(session, nid, next(it), mode, 10, embedder, exact=exact), len(qs)
            )

        search(session, nid, "warm up", "hybrid", 10, embedder)
        report["search_ms"] = {m: per_mode(m) for m in ("keyword", "fts", "vector", "hybrid")}

        t = time.perf_counter()
        ensure_hnsw_index(session, embedder.name, embedder.dim)
        session.commit()
        report["hnsw_build_seconds"] = round(time.perf_counter() - t, 2)
        report["search_ms"]["vector_hnsw"] = per_mode("vector", exact=False)
        overlap = []
        for q in qs:
            a = [h.passage_id for h in search(session, nid, q, "vector", 10, embedder).hits]
            b = [
                h.passage_id
                for h in search(session, nid, q, "vector", 10, embedder, exact=False).hits
            ]
            overlap.append(len(set(a) & set(b)) / max(1, len(a)))
        report["hnsw_recall_at_10_vs_exact"] = round(statistics.fmean(overlap), 4)

        report["contradiction_report_ms"] = _timed(
            lambda: (refresh_findings(session, nid, 0.6), session.commit()), 3
        )
        report["graph_ms"] = _timed(lambda: character_graph(session, nid), 3)
        report["timeline_ms"] = _timed(lambda: timeline(session, nid), 3)

        sample = session.scalars(
            select(Chapter).where(Chapter.novel_id == nid).order_by(Chapter.number).limit(10)
        ).all()

        def save_one(state={"i": 0}):  # noqa: B006 - deliberate cycling counter
            ch = sample[state["i"] % len(sample)]
            state["i"] += 1
            workspace.update_chapter(
                session, ch, ch.version, {"body": ch.body + f"\n\nEdit {uuid.uuid4().hex[:6]}."}
            )
            session.commit()

        report["chapter_save_ms"] = _timed(save_one, 10)
        report["db_size_mb"] = round(
            session.scalar(text("SELECT pg_database_size(current_database())")) / 1024 / 1024, 1
        )
    engine.dispose()
    report["peak_rss_mb"] = _peak_rss_mb()
    report["environment"] = {
        "machine": platform.machine(),
        "system": platform.platform(),
        "python": platform.python_version(),
        "commit": _git_commit(),
    }
    return report


def to_markdown(r: dict[str, Any]) -> str:
    s = r["size"]
    lines = [
        f"`{r['corpus']}`: {s['chapters']} chapters, {s['words']:,} words, {s['passages']:,} "
        f"passages, {s['claims']:,} claims; embedder `{r['embedder']}`.",
        "",
        "| Measure | Value |",
        "|---|---|",
        f"| Import (split, extract, revisions) | {r['import']['seconds']} s "
        f"({r['import']['chapters_per_s']} chapters/s) |",
        f"| Embedding index | {r['index']['seconds']} s "
        f"({r['index']['passages_per_s']} passages/s) |",
        f"| HNSW build | {r['hnsw_build_seconds']} s |",
    ]
    for mode, m in r["search_ms"].items():
        lines.append(f"| Search `{mode}` p50 / p95 | {m['p50']} / {m['p95']} ms |")
    lines += [
        f"| HNSW top-10 agreement with exact | {r['hnsw_recall_at_10_vs_exact']} |",
        f"| Contradiction report (refresh) p50 | {r['contradiction_report_ms']['p50']} ms |",
        f"| Character graph p50 | {r['graph_ms']['p50']} ms |",
        f"| Timeline p50 | {r['timeline_ms']['p50']} ms |",
        f"| Chapter save (re-split, re-extract, revision) p50 / p95 | "
        f"{r['chapter_save_ms']['p50']} / {r['chapter_save_ms']['p95']} ms |",
        f"| Database size | {r['db_size_mb']} MB |",
        f"| Peak RSS (benchmark process) | {r['peak_rss_mb']} MB |",
    ]
    return "\n".join(lines)
