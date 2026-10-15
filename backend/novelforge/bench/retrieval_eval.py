"""Retrieval benchmark: recall@k, MRR, nDCG, citation precision, latency and token cost.

The corpus is imported into a freshly created database, every passage is embedded with the
chosen embedder (timed, token-counted), and each labelled query is run in every mode. A passage
counts as relevant when it overlaps one of the query's labelled evidence spans.

Nothing here is estimated except where the output says so (`tokens_exact: false`).
"""

from __future__ import annotations

import json
import math
import platform
import statistics
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import create_engine, select
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker

from novelforge.models import Chapter, Novel, Passage
from novelforge.retrieval.embedders import get_embedder
from novelforge.retrieval.index import embed_passages
from novelforge.retrieval.rerankers import get_reranker
from novelforge.retrieval.search import search
from novelforge.services.importer import import_folder

KS = (1, 3, 5, 10)


def recreate_database(base: URL, name: str) -> str:
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        conn.exec_driver_sql(f'CREATE DATABASE "{name}"')
    admin.dispose()
    return base.set(database=name).render_as_string(hide_password=False)


def migrate(url: str) -> None:
    from alembic import command

    from novelforge.cli import _alembic_config

    cfg = _alembic_config()
    cfg.attributes["url"] = url
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")


def percentile(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    idx = (len(ordered) - 1) * p
    lo, hi = math.floor(idx), math.ceil(idx)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (idx - lo)


def _git_commit() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def run(
    corpus: Path,
    base_url: URL,
    embedder_spec: str,
    reranker_spec: str,
    modes: list[str],
    database: str = "novelforge_bench",
    max_queries: int | None = None,
) -> dict[str, Any]:
    gt = yaml.safe_load((corpus / "ground_truth.yaml").read_text(encoding="utf-8"))
    queries = gt["queries"][:max_queries] if max_queries else gt["queries"]
    url = recreate_database(base_url, database)
    migrate(url)
    engine = create_engine(url)
    maker = sessionmaker(bind=engine, expire_on_commit=False)

    embedder = get_embedder(embedder_spec)
    reranker = get_reranker(reranker_spec)

    with maker() as session:
        t = time.perf_counter()
        novel: Novel = import_folder(session, corpus).novel
        session.commit()
        import_s = time.perf_counter() - t

        passages = list(session.scalars(select(Passage).where(Passage.novel_id == novel.id)))
        t = time.perf_counter()
        index_stats = embed_passages(session, passages, embedder)
        session.commit()
        index_s = time.perf_counter() - t

        chapter_ids = {
            c.number: str(c.id)
            for c in session.scalars(select(Chapter).where(Chapter.novel_id == novel.id))
        }
        results = {
            mode: evaluate_mode(session, novel.id, queries, chapter_ids, mode, embedder, reranker)
            for mode in modes
        }

    engine.dispose()
    return {
        "corpus": corpus.name,
        "generator": gt.get("generator"),
        "embedder": embedder.name,
        "embedder_local": embedder.local,
        "reranker": reranker.name,
        "queries": len(queries),
        "query_kinds": {
            k: sum(1 for q in queries if q["kind"] == k)
            for k in sorted({q["kind"] for q in queries})
        },
        "passages": len(passages),
        "chapters": len(chapter_ids),
        "import_seconds": round(import_s, 2),
        "index_seconds": round(index_s, 2),
        "index": index_stats,
        "cost_usd": 0.0 if embedder.local else None,
        "modes": results,
        "environment": {
            "machine": platform.machine(),
            "system": f"{platform.system()} {platform.release()}",
            "python": platform.python_version(),
            "commit": _git_commit(),
        },
    }


def _relevant(hit, relevant: list[dict], chapter_ids: dict[int, str]) -> bool:
    return any(
        chapter_ids.get(r["chapter"]) == hit.chapter_id
        and hit.start < r["end"]
        and r["start"] < hit.end
        for r in relevant
    )


def evaluate_mode(
    session: Session,
    novel_id: uuid.UUID,
    queries: list[dict],
    chapter_ids: dict[int, str],
    mode: str,
    embedder,
    reranker,
) -> dict[str, Any]:
    # Warm up (model load, statement caches) outside the timed loop.
    search(session, novel_id, "warm up query", mode, 10, embedder, reranker)  # type: ignore[arg-type]
    per_kind: dict[str, dict[str, list[float]]] = {}
    rel_cache: dict[tuple, int] = {}
    latencies: list[float] = []
    stage_times: dict[str, list[float]] = {}
    query_tokens = 0
    rerank_pairs = 0
    for q in queries:
        result = search(session, novel_id, q["query"], mode, 10, embedder, reranker)  # type: ignore[arg-type]
        latencies.append(result.timings_ms["total"])
        for stage, ms in result.timings_ms.items():
            stage_times.setdefault(stage, []).append(ms)
        query_tokens += result.query_tokens
        rerank_pairs += result.rerank_pairs
        flags = [_relevant(h, q["relevant"], chapter_ids) for h in result.hits]
        n_rel = _count_relevant_passages(session, novel_id, q["relevant"], chapter_ids, rel_cache)
        metrics = {f"recall@{k}": float(any(flags[:k])) for k in KS}
        first = next((i for i, f in enumerate(flags) if f), None)
        metrics["mrr@10"] = 0.0 if first is None else 1.0 / (first + 1)
        dcg = sum(1.0 / math.log2(i + 2) for i, f in enumerate(flags) if f)
        idcg = sum(1.0 / math.log2(i + 2) for i in range(min(n_rel, 10)))
        metrics["ndcg@10"] = dcg / idcg if idcg else 0.0
        top3 = flags[:3]
        metrics["citation_precision@3"] = sum(top3) / len(top3) if top3 else 0.0
        for kind in ("all", q["kind"]):
            bucket = per_kind.setdefault(kind, {})
            for name, value in metrics.items():
                bucket.setdefault(name, []).append(value)
    return {
        "metrics": {
            kind: {name: round(statistics.fmean(vals), 4) for name, vals in bucket.items()}
            for kind, bucket in per_kind.items()
        },
        "latency_ms": {
            "p50": round(percentile(latencies, 0.5), 2),
            "p95": round(percentile(latencies, 0.95), 2),
            "mean": round(statistics.fmean(latencies), 2),
        },
        "stage_p50_ms": {s: round(percentile(v, 0.5), 2) for s, v in stage_times.items()},
        "query_tokens": query_tokens,
        "rerank_pairs": rerank_pairs,
    }


def _count_relevant_passages(session, novel_id, relevant, chapter_ids, cache) -> int:
    """Number of passages overlapping the labelled spans (the ideal ranking's length for nDCG)."""
    key = tuple((r["chapter"], r["start"], r["end"]) for r in relevant)
    if key not in cache:
        count = 0
        for p in session.scalars(
            select(Passage).where(
                Passage.novel_id == novel_id,
                Passage.chapter_id.in_(
                    [
                        uuid.UUID(chapter_ids[r["chapter"]])
                        for r in relevant
                        if r["chapter"] in chapter_ids
                    ]
                ),
            )
        ):
            if any(
                chapter_ids.get(r["chapter"]) == str(p.chapter_id)
                and p.start < r["end"]
                and r["start"] < p.end
                for r in relevant
            ):
                count += 1
        cache[key] = count
    return cache[key]


def to_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"Corpus `{report['corpus']}` ({report['chapters']} chapters, "
        f"{report['passages']} passages, {report['queries']} queries {report['query_kinds']}); "
        f"embedder `{report['embedder']}`, reranker `{report['reranker']}`.",
        "",
        "| Mode | Queries | R@1 | R@3 | R@5 | R@10 | MRR@10 | nDCG@10 | P@3 | p50 ms | p95 ms |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for mode, res in report["modes"].items():
        for kind in ["all", *sorted(k for k in res["metrics"] if k != "all")]:
            m = res["metrics"][kind]
            lat = res["latency_ms"] if kind == "all" else {"p50": "", "p95": ""}
            lines.append(
                f"| {mode} | {kind} | {m['recall@1']:.3f} | {m['recall@3']:.3f} | "
                f"{m['recall@5']:.3f} | {m['recall@10']:.3f} | {m['mrr@10']:.3f} | "
                f"{m['ndcg@10']:.3f} | {m['citation_precision@3']:.3f} | "
                f"{lat['p50']} | {lat['p95']} |"
            )
    idx = report["index"]
    lines += [
        "",
        f"Indexing: {idx['embedded']} passages embedded in {report['index_seconds']} s, "
        f"{idx['tokens']} tokens ({'exact' if idx['tokens_exact'] else 'estimated'}), "
        f"cost {'$0 (local)' if report['cost_usd'] == 0 else 'n/a'}.",
    ]
    return "\n".join(lines)


def save(report: dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)

    def safe(name: str) -> str:
        return name.replace("/", "_").replace(":", "-")

    path = out_dir / (
        f"retrieval-{report['corpus']}-{safe(report['embedder'])}-{safe(report['reranker'])}.json"
    )
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    path.with_suffix(".md").write_text(to_markdown(report) + "\n", encoding="utf-8")
    return path
