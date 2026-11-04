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

Scored predicates are the ones the samples' writers were asked to label exhaustively (eye and
hair colour, handedness, birthplace, age, dead/alive, and swim/ride/read), plus any other
predicate a sample labels (only 雾港信札 labels `location`). Other claims (`presence`, used only
to catch a dead character acting; the LLM's places, other skills, relationships, events, world
rules) are not labelled, so they are counted by predicate, not scored.

The finding-level score on the same sample is `novelforge eval-sample`. Both score the rule
extractor by default, or an LLM's claims (`--llm SPEC`), alone or together with the rules
(`--with-rules`, how the app runs: rules on every save, the LLM as a background job). LLM answers
are recorded in bench/results/llm-cache/, so a run is paid for once and `--replay` re-scores it
offline.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from novelforge.core.domain import ChapterRef, CharacterRef, ExtractedClaim
from novelforge.core.extraction import extract_claims, extractor_for
from novelforge.core.sample import load_folder

TRACKED = (
    "eye_color", "hair_color", "handedness", "birthplace", "age", "status",
    "ability:swim", "ability:ride", "ability:read",
)  # fmt: skip
CACHE_DIR = Path(__file__).resolve().parents[3] / "bench" / "results" / "llm-cache"


def llm_for(sample: str, spec: str, replay: bool = False, cache_dir: Path = CACHE_DIR):
    """The LLM for a fact run on a sample: recorded to (or replayed from) its own cache file."""
    from novelforge.llm.cache import CachingLLM, ReplayLLM
    from novelforge.llm.registry import get_llm

    if replay:
        return ReplayLLM(spec, cache_dir)
    if spec == "mock":
        return get_llm(spec)  # offline and deterministic: nothing to record
    safe = spec.replace(":", "-").replace("/", "-")
    return CachingLLM(get_llm(spec), cache_dir / f"facts-{sample}-{safe}.jsonl")


def sample_claims(
    chapters: list[ChapterRef], cast: list[CharacterRef], llm=None, with_rules: bool = True
) -> tuple[list[tuple[int, ExtractedClaim]], str, dict[str, Any]]:
    """Claims per chapter number from the rules, an LLM, or both, with the extractor label and
    the LLM's usage. With both, an LLM claim that repeats a rule claim (same subject, predicate
    and value over an overlapping span) is dropped: the app stores both, but one fact is one
    claim for scoring."""
    from novelforge.extraction.runner import extract_with_llm
    from novelforge.services.extraction_jobs import max_words_for

    rules = extractor_for(chapters[0].body if chapters else "")
    out: list[tuple[int, ExtractedClaim]] = []
    usage: dict[str, Any] = {}
    for ch in chapters:
        mine = extract_claims(ch, cast) if with_rules or llm is None else []
        if llm is not None:
            run = extract_with_llm(ch, cast, llm, max_words=max_words_for(llm.name))
            for k in ("calls", "input_tokens", "output_tokens"):
                usage[k] = usage.get(k, 0) + getattr(run, k)
            usage["cost_usd"] = round(usage.get("cost_usd", 0.0) + (run.cost_usd or 0.0), 6)
            usage["rejected"] = usage.get("rejected", 0) + len(run.rejected)
            usage["prompt_version"] = run.prompt_version
            usage.setdefault("rejected_items", []).extend(
                {"chapter": ch.number, **r} for r in run.rejected
            )
            usage.setdefault("errors", []).extend(run.errors)
            mine += [c for c in run.claims if not any(_same(c, r) for r in mine)]
        out += [(ch.number, c) for c in mine]
    if llm is None:
        return out, rules, usage
    name = llm.name.removeprefix("replay:")
    return out, (f"{rules}+llm:{name}" if with_rules else f"llm:{name}"), usage


def _same(a: ExtractedClaim, b: ExtractedClaim) -> bool:
    sa, sb = a.spans[0], b.spans[0]
    return (
        (a.subject_id, a.predicate, a.value) == (b.subject_id, b.predicate, b.value)
        and sa.start < sb.end
        and sb.start < sa.end
    )


def _occurrences(body: str, text: str) -> list[tuple[int, int]]:
    out, i = [], body.find(text)
    while i >= 0:
        out.append((i, i + len(text)))
        i = body.find(text, i + 1)
    return out


def run(folder: Path, llm=None, with_rules: bool = True) -> dict[str, Any]:
    novel = load_folder(folder)
    facts = list(novel.ground_truth.get("facts") or [])
    cast = [
        CharacterRef(str(c.id), c.name, tuple(c.aliases), c.attributes) for c in novel.characters
    ]
    names = {str(c.id): c.name for c in novel.characters}
    bodies = {c.number: c.body for c in novel.chapters}
    refs = [
        ChapterRef(str(c.id), c.number, c.title, c.body, 1, c.story_day) for c in novel.chapters
    ]
    claims, extractor, usage = sample_claims(refs, cast, llm, with_rules)
    scored = set(TRACKED) | {f["predicate"] for f in facts}
    unscored = [cl for _, cl in claims if cl.predicate not in scored]
    claims = [(n, cl) for n, cl in claims if cl.predicate in scored]

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
        "extractor": extractor,
        "llm_usage": usage,
        "facts": len(facts),
        "claims": len(rows),
        "unscored_claims": len(unscored),
        "unscored_by_predicate": dict(sorted(Counter(c.predicate for c in unscored).items())),
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
