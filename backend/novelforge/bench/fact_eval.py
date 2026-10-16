"""Claim-level scoring of the rule extractor on a hand-labelled sample (`facts:` in
ground_truth.yaml), used for the Chinese samples.

Each labelled fact is {chapter, subject, predicate, value, modality, text}, where `text` is an
exact substring of the chapter and the labels list every statement of a checked predicate about
a listed character, asserted or not. A claim matches a fact when chapter, subject, predicate and
value agree and its span overlaps an occurrence of the fact's text. Reported:

- precision: matched claims / all claims (strict: the modality must agree too)
- recall: matched facts / facts, overall and for asserted facts (the ones that can create a
  contradiction)
- modality accuracy on matched claims, and every wrong, missed and mis-modalled item

The finding-level score on the same sample is `novelforge eval-sample`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from novelforge.core.domain import ChapterRef, CharacterRef
from novelforge.core.extraction import extract_claims, extractor_for
from novelforge.core.sample import load_folder


def _occurrences(body: str, text: str) -> list[tuple[int, int]]:
    out, i = [], body.find(text)
    while i >= 0:
        out.append((i, i + len(text)))
        i = body.find(text, i + 1)
    return out


def run(folder: Path) -> dict[str, Any]:
    novel = load_folder(folder)
    facts = list(novel.ground_truth.get("facts") or [])
    cast = [
        CharacterRef(str(c.id), c.name, tuple(c.aliases), c.attributes) for c in novel.characters
    ]
    names = {str(c.id): c.name for c in novel.characters}
    bodies = {c.number: c.body for c in novel.chapters}
    claims = []
    for c in novel.chapters:
        ref = ChapterRef(str(c.id), c.number, c.title, c.body, 1, c.story_day)
        claims += [(c.number, cl) for cl in extract_claims(ref, cast)]

    used: set[int] = set()
    rows = []
    for number, cl in claims:
        a, b = cl.spans[0].start, cl.spans[0].end
        hit = next(
            (
                i
                for i, f in enumerate(facts)
                if i not in used
                and f["chapter"] == number
                and f["subject"] == names[cl.subject_id]
                and f["predicate"] == cl.predicate
                and str(f["value"]) == cl.value
                and any(s < b and a < e for s, e in _occurrences(bodies[number], f["text"]))
            ),
            None,
        )
        if hit is not None:
            used.add(hit)
        rows.append(
            {
                "chapter": number,
                "subject": names[cl.subject_id],
                "predicate": cl.predicate,
                "value": cl.value,
                "modality": cl.modality,
                "quote": cl.spans[0].quote,
                "resolved": cl.details.get("resolved", {}).get("pronoun"),
                "fact": hit,
                "gold_modality": facts[hit]["modality"] if hit is not None else None,
            }
        )
    matched = [r for r in rows if r["fact"] is not None]
    strict = [r for r in matched if r["modality"] == r["gold_modality"]]
    asserted = [i for i, f in enumerate(facts) if f["modality"] == "asserted"]

    def ratio(a: int, b: int) -> float | None:
        return round(a / b, 3) if b else None

    return {
        "sample": folder.name,
        "extractor": extractor_for(next(iter(bodies.values()), "")),
        "facts": len(facts),
        "claims": len(rows),
        "matched": len(matched),
        "precision": ratio(len(matched), len(rows)),
        "strict_precision": ratio(len(strict), len(rows)),
        "recall": ratio(len(matched), len(facts)),
        "recall_asserted": ratio(len(used & set(asserted)), len(asserted)),
        "modality_accuracy": ratio(len(strict), len(matched)),
        "by_predicate": _by_predicate(facts, rows),
        "wrong": [r for r in rows if r["fact"] is None],
        "modality_errors": [r for r in matched if r["modality"] != r["gold_modality"]],
        "missed": [f for i, f in enumerate(facts) if i not in used],
    }


def _by_predicate(facts: list[dict], rows: list[dict]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for f in facts:
        family = f["predicate"].split(":")[0]
        out.setdefault(family, {"facts": 0, "found": 0, "claims": 0})["facts"] += 1
    for r in rows:
        family = r["predicate"].split(":")[0]
        row = out.setdefault(family, {"facts": 0, "found": 0, "claims": 0})
        row["claims"] += 1
        row["found"] += r["fact"] is not None
    return dict(sorted(out.items()))


def to_markdown(result: dict[str, Any]) -> str:
    r = result
    lines = [
        f"`{r['sample']}`, extractor `{r['extractor']}`: {r['claims']} claims, "
        f"{r['facts']} labelled facts.",
        "",
        f"Precision **{r['precision']}** (strict, modality too: {r['strict_precision']}); "
        f"recall **{r['recall']}** (asserted facts: {r['recall_asserted']}); "
        f"modality accuracy {r['modality_accuracy']}.",
        "",
        "| Predicate | Facts | Found | Claims |",
        "|---|---|---|---|",
        *[
            f"| {k} | {v['facts']} | {v['found']} | {v['claims']} |"
            for k, v in r["by_predicate"].items()
        ],
    ]
    for title, items, fmt in (
        (
            "Wrong claims",
            r["wrong"],
            "{chapter} {subject} {predicate}={value} ({modality}): {quote}",
        ),
        (
            "Modality errors",
            r["modality_errors"],
            "{chapter} {subject} {predicate}={value}: {modality}, label {gold_modality}: {quote}",
        ),
        (
            "Missed facts",
            r["missed"],
            "{chapter} {subject} {predicate}={value} ({modality}): {text}",
        ),
    ):
        if items:
            lines += ["", f"{title}:", *[f"- {fmt.format(**i)}" for i in items]]
    return "\n".join(lines) + "\n"
