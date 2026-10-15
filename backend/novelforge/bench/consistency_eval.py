"""Consistency benchmark with a memory ablation.

The task: check each chapter for contradictions with the rest of the novel. All systems use the
same extracted claims and the same detectors; they differ only in what the checker can SEE when
it checks chapter c:

- no-memory      only chapter c's own claims (plus the character sheets and travel times)
- vector-only    chapter c's claims + claims found in the top-k earlier passages retrieved by
                 embedding similarity, one query per claim (its sentence)
- hybrid         the same with hybrid retrieval (full-text + vector, RRF)
- structured     every claim in the novel, indexed by character and predicate (NovelForge's
                 report), plus the LLM world-rule judge when an LLM is configured

Findings are kept only if they involve chapter c, then de-duplicated across chapters and scored
against the labelled ground truth (core/evaluation.py). The extractor is a separate axis:
rules-v2, the rule-backed mock, or a real LLM.
"""

from __future__ import annotations

import platform
import time
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import create_engine, select
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker

from novelforge.bench.retrieval_eval import _git_commit, migrate, recreate_database
from novelforge.core.contradictions import detect_contradictions
from novelforge.core.evaluation import evaluate
from novelforge.core.extraction import EXTRACTOR
from novelforge.models import Chapter, Novel, Passage
from novelforge.retrieval.embedders import get_embedder
from novelforge.retrieval.index import embed_passages
from novelforge.retrieval.search import search
from novelforge.services.derived import chapter_ref, character_refs, persist_claims
from novelforge.services.findings import fingerprint, travel_matrix
from novelforge.services.importer import import_folder
from novelforge.services.report import load_claims, to_extracted

SYSTEMS = ("no-memory", "vector-only", "hybrid", "structured")


def run(
    corpus: Path,
    base_url: URL,
    extractor: str = "rules",
    embedder_spec: str = "hash",
    systems: tuple[str, ...] = SYSTEMS,
    k: int = 5,
    max_chapters: int | None = None,
    database: str = "novelforge_bench_consistency",
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
        "extractor": extractor,
        "embedder": embedder.name,
        "k": k,
        "systems": {},
    }
    with maker() as session:
        novel: Novel = import_folder(session, corpus).novel
        session.commit()
        chapters = list(
            session.scalars(
                select(Chapter).where(Chapter.novel_id == novel.id).order_by(Chapter.number)
            )
        )
        if max_chapters:
            chapters = chapters[:max_chapters]
        numbers = {c.number for c in chapters}

        t = time.perf_counter()
        report["extraction"] = _extract(session, chapters, extractor)
        session.commit()
        report["extraction"]["seconds"] = round(time.perf_counter() - t, 2)

        passages = list(session.scalars(select(Passage).where(Passage.novel_id == novel.id)))
        t = time.perf_counter()
        embed_passages(session, passages, embedder)
        session.commit()
        report["index_seconds"] = round(time.perf_counter() - t, 2)

        bodies = {c.number: c.body for c in chapters}
        gt_scoped = _scope(gt, numbers)
        for system in systems:
            t = time.perf_counter()
            findings, context = _system_findings(
                session, novel.id, chapters, system, embedder, k, extractor
            )
            elapsed = time.perf_counter() - t
            result = evaluate(findings, gt_scoped, bodies).as_dict()
            result.update({"seconds": round(elapsed, 2), **context})
            report["systems"][system] = result
    engine.dispose()
    report["labelled_contradictions"] = len(gt_scoped["contradictions"])
    report["labelled_negatives"] = len(gt_scoped["negatives"])
    report["chapters"] = len(numbers)
    report["environment"] = {
        "machine": platform.machine(),
        "python": platform.python_version(),
        "commit": _git_commit(),
    }
    return report


def _scope(gt: dict, numbers: set[int]) -> dict:
    """Keep only labels whose evidence lies entirely in the evaluated chapters."""

    def inside(item: dict) -> bool:
        return all(e["chapter"] in numbers for e in item.get("evidence", []))

    return {
        "contradictions": [dict(c) for c in gt["contradictions"] if inside(c)],
        "negatives": [dict(n) for n in gt["negatives"] if inside(n)],
    }


def _extract(session: Session, chapters: list[Chapter], extractor: str) -> dict[str, Any]:
    if extractor == "rules":
        return {"extractor": EXTRACTOR, "note": "claims extracted during import"}
    from novelforge.extraction.runner import extract_with_llm
    from novelforge.llm.registry import get_llm
    from novelforge.services.extraction_jobs import max_words_for

    llm = get_llm(extractor)
    totals: dict[str, Any] = {
        "extractor": f"llm:{llm.name}",
        "calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.0,
        "claims": 0,
        "rejected": 0,
        "errors": 0,
    }
    novel_id = chapters[0].novel_id
    cast = character_refs(session, novel_id)
    for chapter in chapters:
        run = extract_with_llm(chapter_ref(chapter), cast, llm, max_words=max_words_for(extractor))
        persist_claims(session, chapter, run.claims, run.extractor)
        # The LLM run replaces the rule claims for this benchmark arm.
        persist_claims(session, chapter, [], "rules-%")
        totals["calls"] += run.calls
        totals["input_tokens"] += run.input_tokens
        totals["output_tokens"] += run.output_tokens
        totals["claims"] += len(run.claims)
        totals["rejected"] += len(run.rejected)
        totals["errors"] += len(run.errors)
        if totals["cost_usd"] is not None:
            totals["cost_usd"] = None if run.cost_usd is None else totals["cost_usd"] + run.cost_usd
    return totals


def _system_findings(session, novel_id, chapters, system, embedder, k, extractor):
    refs = [chapter_ref(c) for c in chapters]
    number = {r.id: r.number for r in refs}
    cast = character_refs(session, novel_id)
    travel = travel_matrix(session, novel_id)
    claims = [to_extracted(c) for c in load_claims(session, novel_id)]
    claims = [c for c in claims if c.chapter_id in number]
    by_chapter: dict[str, list] = defaultdict(list)
    for c in claims:
        by_chapter[c.chapter_id].append(c)

    def detect(subset):
        return detect_contradictions(subset, refs, cast, travel=travel)

    if system == "structured":
        findings = detect(claims)
        context = {"avg_context_claims": len(claims)}
        if extractor != "rules":
            findings = findings + _judge_findings(session, novel_id, extractor)
        return findings, context

    # Passage index: which claims each passage holds (for retrieval-based memory).
    passages = {
        str(p.id): p for p in session.scalars(select(Passage).where(Passage.novel_id == novel_id))
    }
    claims_in_passage: dict[str, list] = defaultdict(list)
    by_chapter_passages: dict[str, list[Passage]] = defaultdict(list)
    for p in passages.values():
        by_chapter_passages[str(p.chapter_id)].append(p)
    for c in claims:
        s = c.spans[0]
        for p in by_chapter_passages.get(c.chapter_id, []):
            if p.start <= s.start < p.end:
                claims_in_passage[str(p.id)].append(c)
                break

    mode = {"vector-only": "vector", "hybrid": "hybrid"}.get(system)
    seen: dict[str, Any] = {}
    context_sizes = []
    for ref in refs:
        own = by_chapter.get(ref.id, [])
        memory: dict[str, Any] = {}
        if mode:
            for c in own:
                hits = search(session, novel_id, c.spans[0].quote, mode, k * 4, embedder).hits
                earlier = [h for h in hits if number.get(h.chapter_id, 10**9) < ref.number][:k]
                for h in earlier:
                    for m in claims_in_passage.get(h.passage_id, []):
                        memory[m.id] = m
        subset = own + list(memory.values())
        context_sizes.append(len(subset))
        for f in detect(subset):
            if any(e.chapter_id == ref.id for e in f.evidence):
                seen.setdefault(fingerprint(f), f)
    avg = round(sum(context_sizes) / len(context_sizes), 1) if context_sizes else 0
    return list(seen.values()), {"avg_context_claims": avg}


def _judge_findings(session: Session, novel_id: uuid.UUID, extractor: str) -> list[dict]:
    from novelforge.llm.registry import get_llm
    from novelforge.models import StoredFinding
    from novelforge.services.rule_judge import judge_novel

    judge_novel(session, novel_id, get_llm(extractor))
    session.commit()
    return [
        {
            "kind": r.kind,
            "category": r.category,
            "subject_name": r.subject_name,
            "predicate": r.predicate,
            "evidence": r.evidence,
        }
        for r in session.scalars(
            select(StoredFinding).where(
                StoredFinding.novel_id == novel_id, StoredFinding.kind == "world_rule_violation"
            )
        )
    ]


def to_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"Corpus `{report['corpus']}` ({report['chapters']} chapters, "
        f"{report['labelled_contradictions']} labelled contradictions, "
        f"{report['labelled_negatives']} negatives); extractor "
        f"`{report['extraction']['extractor']}`, embedder `{report['embedder']}`, k={report['k']}.",
        "",
        "| System | TP | FP | FN | Precision | Recall | Negatives violated | Citation P | "
        "Avg claims seen | Seconds |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, r in report["systems"].items():
        lines.append(
            f"| {name} | {r['true_positives']} | {r['false_positives']} | {r['false_negatives']} | "
            f"{r['precision']} | {r['recall_all']} | {r['negatives_violated']}/{r['negatives']} | "
            f"{r['citation_precision']} | {r['avg_context_claims']} | {r['seconds']} |"
        )
    lines += ["", "Recall by category (structured):"]
    s = report["systems"].get("structured")
    if s:
        for cat, c in s["by_category"].items():
            lines.append(f"- {cat}: {c['detected']}/{c['labelled']} detected, {c['fp']} FP")
    return "\n".join(lines)
