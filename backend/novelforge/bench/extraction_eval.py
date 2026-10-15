"""Extraction benchmark: claims from an extractor vs the generator's labelled facts.

Scored predicates (the generator labels every statement of these):
  eye_color, hair_color, handedness, birthplace, age, location, status=dead,
  ability:<skill>=cannot|learned
A claim is a true positive when it has the same chapter, subject, predicate and value as a
labelled fact and its span overlaps the labelled sentence. Only claims the extractor marked
`asserted` count for precision: hedged/reported/recalled extractions are judged separately by
"negative-case modality accuracy" (did the extractor avoid asserting them?).

Unlabelled predicates (ability used, alive, events, relationships) are counted but not scored.
World rules, foreshadowing set-ups and causal links are scored for recall only (span overlap).
"""

from __future__ import annotations

import platform
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from novelforge.bench.retrieval_eval import _git_commit
from novelforge.core.domain import ChapterRef, CharacterRef, ExtractedClaim
from novelforge.core.extraction import EXTRACTOR, extract_claims
from novelforge.core.sample import load_folder

SCORED = (
    "eye_color",
    "hair_color",
    "handedness",
    "birthplace",
    "age",
    "location",
    "status",
    "ability",
)


def _family(predicate: str) -> str:
    return "ability" if predicate.startswith("ability:") else predicate


def _gt_key(f: dict) -> tuple[str, str] | None:
    p = f["predicate"]
    if p == "death":
        return "status", "dead"
    if p == "ability":
        if f["value"] not in ("cannot", "learned"):
            return None
        return f"ability:{f['skill']}", f["value"]
    v = str(f["value"])
    return p, v.lower() if p in ("eye_color", "hair_color", "handedness") else v


def _overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def run(
    corpus: Path,
    extractor: str,
    max_chapters: int | None = None,
    cache: Path | None = None,
    check_values: bool = True,
    sheet_pronouns: bool = True,
) -> dict[str, Any]:
    novel = load_folder(corpus)
    gt = yaml.safe_load((corpus / "ground_truth.yaml").read_text(encoding="utf-8"))
    chapters = novel.chapters[:max_chapters] if max_chapters else novel.chapters
    numbers = {c.number for c in chapters}
    refs = [ChapterRef(str(c.id), c.number, c.title, c.body, 1, c.story_day) for c in chapters]
    by_id = {r.id: r for r in refs}
    cast = [
        CharacterRef(
            str(c.id),
            c.name,
            tuple(c.aliases),
            c.attributes
            if sheet_pronouns
            else {k: v for k, v in c.attributes.items() if k != "pronouns"},
        )
        for c in novel.characters
    ]
    names = {str(c.id): c.name for c in novel.characters}

    claims: list[ExtractedClaim] = []
    usage = {
        "calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.0,
        "rejected": 0,
        "rejected_by_reason": defaultdict(int),
        "errors": [],
    }
    started = time.perf_counter()
    if extractor == "rules":
        for r in refs:
            claims += extract_claims(r, cast)
        name = EXTRACTOR
    else:
        from novelforge.extraction.runner import extract_with_llm
        from novelforge.llm.registry import get_llm
        from novelforge.services.extraction_jobs import max_words_for

        llm = get_llm(extractor)
        if cache is not None:
            from novelforge.llm.cache import CachingLLM

            llm = CachingLLM(llm, cache)
        name = f"llm:{llm.name}"
        for r in refs:
            result = extract_with_llm(
                r, cast, llm, max_words=max_words_for(extractor), check_values=check_values
            )
            claims += result.claims
            usage["calls"] += result.calls
            usage["input_tokens"] += result.input_tokens
            usage["output_tokens"] += result.output_tokens
            if usage["cost_usd"] is not None:
                usage["cost_usd"] = (
                    None if result.cost_usd is None else usage["cost_usd"] + result.cost_usd
                )
            usage["rejected"] += len(result.rejected)
            for rej in result.rejected:
                usage["rejected_by_reason"][rej["reason"]] += 1
            usage["errors"] += [f"ch{r.number}: {e}" for e in result.errors]
    elapsed = time.perf_counter() - started

    facts = [f for f in gt["facts"] if f["chapter"] in numbers]
    labelled = []
    for f in facts:
        key = _gt_key(f)
        if key is None:
            continue
        ev = f["evidence"][0]
        labelled.append(
            {
                "chapter": f["chapter"],
                "subject": f["subject"],
                "predicate": key[0],
                "value": key[1],
                "span": (ev["start"], ev["end"]),
                "template": f.get("template"),
                "day": f.get("day"),
                "matched": False,
            }
        )

    per: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    by_template: dict[str, dict[str, int]] = defaultdict(lambda: {"found": 0, "total": 0})
    unscored: dict[str, int] = defaultdict(int)
    day_checks = {"correct": 0, "total": 0}
    fp_examples: list[dict] = []
    for c in claims:
        fam = _family(c.predicate)
        if (
            fam not in SCORED
            or (c.predicate == "status" and c.value != "dead")
            or (fam == "ability" and c.value not in ("cannot", "learned"))
        ):
            unscored[c.predicate if fam != "ability" else f"ability:{c.value}"] += 1
            continue
        if c.modality != "asserted":
            continue
        ch = by_id[c.chapter_id].number
        span = (c.spans[0].start, c.spans[0].end)
        match = next(
            (
                g
                for g in labelled
                if not g["matched"]
                and g["chapter"] == ch
                and g["predicate"] == c.predicate
                and g["value"].lower() == c.value.lower()
                and g["subject"] == names.get(c.subject_id)
                and _overlap(g["span"], span)
            ),
            None,
        )
        if match is None:
            per[fam]["fp"] += 1
            if len(fp_examples) < 15:
                fp_examples.append(
                    {
                        "chapter": ch,
                        "predicate": c.predicate,
                        "value": c.value,
                        "subject": names.get(c.subject_id, c.subject_text),
                        "quote": c.spans[0].quote,
                    }
                )
            continue
        match["matched"] = True
        per[fam]["tp"] += 1
        if fam == "location" and match["day"] is not None:
            day_checks["total"] += 1
            day_checks["correct"] += int(c.effective_day == match["day"])
    for g in labelled:
        fam = _family(g["predicate"])
        by_template[f"{fam}/{g['template']}"]["total"] += 1
        if g["matched"]:
            by_template[f"{fam}/{g['template']}"]["found"] += 1
        else:
            per[fam]["fn"] += 1

    def prf(d: dict[str, int]) -> dict[str, Any]:
        p = d["tp"] / (d["tp"] + d["fp"]) if d["tp"] + d["fp"] else None
        r = d["tp"] / (d["tp"] + d["fn"]) if d["tp"] + d["fn"] else None
        f1 = 2 * p * r / (p + r) if p and r else None
        return {**d, "precision": _r(p), "recall": _r(r), "f1": _r(f1)}

    total = {
        "tp": sum(d["tp"] for d in per.values()),
        "fp": sum(d["fp"] for d in per.values()),
        "fn": sum(d["fn"] for d in per.values()),
    }

    # Negative cases whose evidence contains an extracted claim: was it kept out of "asserted"?
    neg = {"asserted": 0, "not_asserted": 0}
    for n in gt["negatives"]:
        if n["kind"] not in ("hedged", "dialogue", "memory"):
            continue
        for e in n["evidence"]:
            if e["chapter"] not in numbers:
                continue
            for c in claims:
                if by_id[c.chapter_id].number == e["chapter"] and _overlap(
                    (c.spans[0].start, c.spans[0].end), (e["start"], e["end"])
                ):
                    neg["asserted" if c.modality == "asserted" else "not_asserted"] += 1

    def recall_of(spans: list[tuple[int, int, int]], predicate: str) -> dict[str, Any]:
        found = sum(
            1
            for ch, s, e in spans
            if any(
                c.predicate == predicate
                and by_id[c.chapter_id].number == ch
                and _overlap((c.spans[0].start, c.spans[0].end), (s, e))
                for c in claims
            )
        )
        return {
            "found": found,
            "total": len(spans),
            "recall": _r(found / len(spans)) if spans else None,
        }

    rule_spans = [
        (m["evidence"]["chapter"], m["evidence"]["start"], m["evidence"]["end"])
        for m in gt.get("rule_mentions", [])
        if m["kind"] == "statement" and m["evidence"]["chapter"] in numbers
    ]
    setup_spans = [
        (f["setup"]["chapter"], f["setup"]["start"], f["setup"]["end"])
        for f in gt.get("foreshadowing", [])
        if f["setup"]["chapter"] in numbers
    ]
    causal_spans = [
        (c["evidence"]["chapter"], c["evidence"]["start"], c["evidence"]["end"])
        for c in gt.get("causal_links", [])
        if c["evidence"]["chapter"] in numbers
    ]
    usage["rejected_by_reason"] = dict(usage["rejected_by_reason"])
    return {
        "corpus": corpus.name,
        "generator": gt.get("generator"),
        "extractor": name,
        "value_check": check_values,
        "sheet_pronouns": sheet_pronouns,
        "cache": None
        if cache is None or extractor == "rules"
        else {
            "file": cache.name,
            "hits": getattr(llm, "hits", 0),
            "misses": getattr(llm, "misses", 0),
        },
        "chapters": len(refs),
        "seconds": round(elapsed, 2),
        "claims": len(claims),
        "scored": {"overall": prf(total), **{k: prf(v) for k, v in sorted(per.items())}},
        "recall_by_template": {k: v for k, v in sorted(by_template.items())},
        "location_day_accuracy": day_checks,
        "negative_modality": neg,
        "world_rule_statements": recall_of(rule_spans, "world_rule"),
        "foreshadowing_setups": recall_of(setup_spans, "foreshadowing"),
        "causal_links": recall_of(causal_spans, "causal"),
        "unscored_claims": dict(unscored),
        "usage": usage,
        "false_positive_examples": fp_examples,
        "environment": {
            "machine": platform.machine(),
            "python": platform.python_version(),
            "commit": _git_commit(),
        },
    }


def _r(x: float | None) -> float | None:
    return None if x is None else round(x, 4)


def to_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"Corpus `{report['corpus']}` ({report['chapters']} chapters), extractor "
        f"`{report['extractor']}`, {report['seconds']} s.",
        "",
        "| Predicate | TP | FP | FN | Precision | Recall | F1 |",
        "|---|---|---|---|---|---|---|",
    ]
    for k, v in report["scored"].items():
        lines.append(
            f"| {k} | {v['tp']} | {v['fp']} | {v['fn']} | {v['precision']} | "
            f"{v['recall']} | {v['f1']} |"
        )
    u = report["usage"]
    neg = report["negative_modality"]
    lines += [
        "",
        f"Negative cases (hedged/dialogue/memory) kept out of `asserted`: "
        f"{neg['not_asserted']} of {neg['asserted'] + neg['not_asserted']} extracted claims.",
        f"Location day accuracy: {report['location_day_accuracy']}.",
        f"World-rule statements found: {report['world_rule_statements']}; foreshadowing set-ups: "
        f"{report['foreshadowing_setups']}; causal links: {report['causal_links']}.",
        f"LLM calls {u['calls']}, tokens in/out {u['input_tokens']}/{u['output_tokens']}, "
        f"cost {u['cost_usd']}, rejected facts {u['rejected']} {u['rejected_by_reason']}.",
    ]
    return "\n".join(lines)
