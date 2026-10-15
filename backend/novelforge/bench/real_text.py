"""Real-prose evaluation: the extractor and the contradiction report on public-domain novels.

The synthetic benchmarks know every answer but are written in the generator's templates. This
one runs on novels nobody wrote for NovelForge. There is no complete ground truth, so it
measures **precision**: every claim the extractor makes and every finding the report raises is
judged by hand, and the judgements live in `bench/real/labels/<book>.jsonl`, keyed by content
(chapter, subject, predicate, value, quote, occurrence), not by extractor or offsets. A rerun
scores what is labelled and lists what is not, so a new extractor version only needs its new
claims judged.

A claim label records two judgements, so it stays valid when an extractor version changes
only the modality:
- `fact`: `right` if the quoted text states this fact about this character, else `wrong`
  (wrong character, wrong value, figurative, negated, ...), with an `error` category
- `asserted`: whether the narrator asserts it as true at that point (dialogue, perception,
  memory, conditionals are not assertions)
A claim is then `correct` (right fact, and marked `asserted` exactly when it is asserted),
`modality` (right fact, wrong modality; counts against strict precision only) or `wrong`.
For findings: `true` (the book really is inconsistent here) or `false` (a false alarm).

**Recall** is estimated on candidate sentences: every sentence that matches a keyword filter
for the identity facts (a colour word before "eyes"/"hair", an age phrase, "born", "died"/
"dead", "-handed") is labelled with the facts it states about listed characters (possibly
none). A fact counts as found when a claim has its chapter, character, predicate and value and
overlaps the sentence. Facts stated without those keywords ("Beth ... a sharp struggle of the
young life with death") are outside the estimate, so it is an upper bound on true recall.

Book texts come from Project Gutenberg at run time and are cached under `bench/corpora/real/`
(not committed). The manifest pins each file's SHA-256; a mismatch is reported, since labels
were made against that file.
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
import time
import urllib.request
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from novelforge.bench.retrieval_eval import _git_commit
from novelforge.core.contradictions import detect_contradictions
from novelforge.core.domain import ChapterRef, CharacterRef, ExtractedClaim, Span
from novelforge.core.extraction import EXTRACTOR, extract_claims
from novelforge.core.plaintext import DEFAULT_HEADING, split_chapters, strip_gutenberg
from novelforge.core.text import sentence_bounds

CLAIM_VERDICTS = ("correct", "modality", "wrong")
RECALL_PREDICATES = ("eye_color", "hair_color", "age", "birthplace", "handedness", "status")
_COLOURS = (
    "grey|gray|green|blue|brown|hazel|amber|black|violet|red|auburn|white|silver|copper|"
    "chestnut|golden|fair|yellow|blond|blonde|flaxen|ginger|dark|light|sandy"
)
_NUMBER_WORD = (
    "two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|"
    "sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety"
)
CANDIDATE = re.compile(
    rf"\b(?:{_COLOURS})\b(?:[ ,-]+[a-z]+){{0,3}}?[ -](?:eyes|eyed|hair|haired|curls|locks|"
    r"ringlets|tresses|braids|plaits)\b"
    rf"|\b(?:eyes|hair) (?:was|were|is|are|had been) (?:[a-z]+ ){{0,2}}(?:{_COLOURS})\b"
    rf"|\byears? old\b|-year-old\b|\bof (?:{_NUMBER_WORD})\b(?:-[a-z]+)?(?! (?:the|them|us|you))"
    rf"|\b(?:was|is|turned|aged|now|at) (?:{_NUMBER_WORD})(?:-[a-z]+)?(?=[,.;:!?—])"
    r"|\bborn\b|\b(?:died|dead|killed|drowned)\b|-handed\b",
    re.IGNORECASE,
)
FINDING_VERDICTS = ("true", "false")


def load_manifest(path: Path) -> dict[str, dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {b["id"]: b for b in data["books"]}


def fetch(book: dict[str, Any], cache_dir: Path) -> tuple[str, str]:
    """(text, sha256) of the book, downloaded once into `cache_dir`."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{book['id']}.txt"
    if not path.exists():
        req = urllib.request.Request(book["url"], headers={"User-Agent": "novelforge-bench"})
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (manifest URL)
            path.write_bytes(resp.read())
    raw = path.read_bytes()
    return raw.decode("utf-8-sig"), hashlib.sha256(raw).hexdigest()


def book_chapters(book: dict[str, Any], text: str) -> list[ChapterRef]:
    body = strip_gutenberg(text)
    if book.get("stop_at"):
        # The last occurrence: front matter may carry the same heading as the end matter.
        found = list(re.finditer(book["stop_at"], body, re.M))
        body = body[: found[-1].start()] if found else body
    chapters = split_chapters(
        body, book.get("heading", DEFAULT_HEADING), book.get("title_lines", 0)
    )
    return [ChapterRef(f"ch{c.number}", c.number, c.title, c.body, 1, None) for c in chapters]


PRONOUNS_BY_GENDER = {"f": "she/her", "m": "he/him", "n": "they/them"}


def book_characters(book: dict[str, Any], pronouns: bool = True) -> list[CharacterRef]:
    """The manifest's cast. `pronouns` puts each character's pronouns on the sheet, as an
    author would; without it the extractor infers them from each chapter."""
    return [
        CharacterRef(
            _slug(c["name"]),
            c["name"],
            tuple(c.get("aliases") or ()),
            {"pronouns": PRONOUNS_BY_GENDER[c["gender"]]} if pronouns and c.get("gender") else {},
        )
        for c in book["characters"]
    ]


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def candidate_key(chapter: int, sentence: str) -> str:
    raw = json.dumps([chapter, sentence], ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def candidates(chapter: ChapterRef) -> list[tuple[int, int]]:
    """Sentence bounds that may state an identity fact (see the module docstring)."""
    out: list[tuple[int, int]] = []
    for m in CANDIDATE.finditer(chapter.body):
        bounds = sentence_bounds(chapter.body, m.start(), m.end())
        if not out or out[-1] != bounds:
            out.append(bounds)
    return sorted(set(out))


def claim_key(chapter: int, subject: str, predicate: str, value: str, quote: str, n: int) -> str:
    raw = json.dumps([chapter, subject, predicate, value, quote, n], ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def finding_key(kind: str, subject: str, quotes: list[str]) -> str:
    raw = json.dumps([kind, subject, sorted(quotes)], ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _context(body: str, start: int, end: int, width: int = 160) -> str:
    s, e = sentence_bounds(body, start, end)
    s, e = max(0, min(s, start - width)), min(len(body), max(e, end + width))
    return body[s:start] + "[[" + body[start:end] + "]]" + body[end:e]


def dump_claims(claims: list[ExtractedClaim], path: Path) -> None:
    rows = [{**asdict(c), "spans": [asdict(s) for s in c.spans]} for c in claims]
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def load_claims(path: Path) -> list[ExtractedClaim]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            row["spans"] = tuple(Span(**s) for s in row["spans"])
            out.append(ExtractedClaim(**row))
    return out


def load_labels(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    labels = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            labels[item["key"]] = item
    return labels


def run(
    book_id: str,
    manifest: Path,
    cache_dir: Path,
    labels_dir: Path,
    sheet_pronouns: bool = True,
    claims_file: Path | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """(report, unlabelled items). Unlabelled items carry context for a reviewer.

    `claims_file` scores claims produced elsewhere (JSONL of ExtractedClaim fields, for example
    an older extractor version run from a git worktree) instead of running the extractor.
    """
    book = load_manifest(manifest)[book_id]
    text, sha = fetch(book, cache_dir)
    chapters = book_chapters(book, text)
    cast = book_characters(book, pronouns=sheet_pronouns)
    names = {c.id: c.name for c in cast}
    by_id = {c.id: c for c in chapters}

    started = time.perf_counter()
    claims: list[ExtractedClaim] = []
    extractor = EXTRACTOR
    if claims_file is not None:
        claims = load_claims(claims_file)
        extractor = claims[0].extractor if claims else "unknown"
    else:
        for ch in chapters:
            claims += extract_claims(ch, cast)
    findings = detect_contradictions(claims, chapters, cast)
    elapsed = time.perf_counter() - started

    labels = load_labels(labels_dir / f"{book_id}.jsonl")
    todo: list[dict[str, Any]] = []
    seen: Counter[tuple] = Counter()
    per: dict[str, Counter[str]] = defaultdict(Counter)
    by_modality: dict[str, Counter[str]] = defaultdict(Counter)
    errors: Counter[str] = Counter()
    wrong_examples: list[dict[str, Any]] = []
    for c in claims:
        ch = by_id[c.chapter_id]
        quote = c.spans[0].quote
        ident = (ch.number, names[c.subject_id], c.predicate, c.value, quote)
        n = seen[ident]
        seen[ident] += 1
        key = claim_key(*ident, n)
        family = "ability" if c.predicate.startswith("ability:") else c.predicate
        label = labels.get(key)
        if label is None:
            per[family]["unlabelled"] += 1
            todo.append(
                {
                    "key": key,
                    "type": "claim",
                    "chapter": ch.number,
                    "subject": names[c.subject_id],
                    "predicate": c.predicate,
                    "value": c.value,
                    "modality": c.modality,
                    "quote": quote,
                    "occurrence": n,
                    "context": _context(ch.body, c.spans[0].start, c.spans[0].end),
                }
            )
            continue
        verdict = _verdict(label, c.modality)
        per[family][verdict] += 1
        by_modality[c.modality][verdict] += 1
        if verdict != "correct":
            errors[label.get("error") if verdict == "wrong" else "modality"] += 1
            if len(wrong_examples) < 25:
                wrong_examples.append(
                    {
                        "chapter": ch.number,
                        "subject": names[c.subject_id],
                        "predicate": c.predicate,
                        "value": c.value,
                        "modality": c.modality,
                        "quote": quote,
                        "verdict": verdict,
                        "error": label.get("error")
                        or f"modality: should be {'' if label['asserted'] else 'not '}asserted",
                        "note": label.get("note"),
                    }
                )

    recall: dict[str, Counter[str]] = defaultdict(Counter)
    missed: list[dict[str, Any]] = []
    n_candidates = 0
    for ch in chapters:
        for s0, e0 in candidates(ch):
            n_candidates += 1
            sentence = ch.body[s0:e0]
            key = candidate_key(ch.number, sentence)
            label = labels.get(key)
            if label is None:
                recall["all"]["unlabelled_sentences"] += 1
                todo.append(
                    {
                        "key": key,
                        "type": "candidate",
                        "chapter": ch.number,
                        "sentence": sentence,
                        "context": _context(ch.body, s0, e0, width=200),
                        "facts": [],
                    }
                )
                continue
            for fact in label["facts"]:
                hit = any(
                    by_id[c.chapter_id].number == ch.number
                    and names[c.subject_id] == fact["subject"]
                    and c.predicate == fact["predicate"]
                    and _same(c.value, fact["value"])
                    and c.spans[0].start < e0
                    and s0 < c.spans[0].end
                    for c in claims
                )
                for bucket in ("all", fact["predicate"]) + (
                    ("asserted",) if fact["asserted"] else ()
                ):
                    recall[bucket]["facts"] += 1
                    recall[bucket]["found"] += int(hit)
                if not hit and len(missed) < 40:
                    missed.append({"chapter": ch.number, "sentence": sentence, **fact})

    finding_rows = []
    finding_counts: Counter[str] = Counter()
    for f in findings:
        quotes = [e.quote for e in f.evidence]
        key = finding_key(f.kind, f.subject_name, quotes)
        label = labels.get(key)
        verdict = label["verdict"] if label else "unlabelled"
        finding_counts[verdict] += 1
        row = {
            "key": key,
            "type": "finding",
            "kind": f.kind,
            "subject": f.subject_name,
            "chapters": sorted({e.chapter_number for e in f.evidence}),
            "quotes": quotes,
            "verdict": verdict,
            "note": label.get("note") if label else None,
        }
        finding_rows.append(row)
        if label is None:
            todo.append(
                {
                    **{k: v for k, v in row.items() if k != "verdict"},
                    "explanation": f.explanation,
                    "contexts": [
                        _context(by_id[e.chapter_id].body, e.start, e.end) for e in f.evidence
                    ],
                }
            )

    def precision(counts: Counter[str]) -> dict[str, Any]:
        judged = sum(counts[v] for v in CLAIM_VERDICTS)
        return {
            **{v: counts[v] for v in (*CLAIM_VERDICTS, "unlabelled")},
            "fact_precision": _r((counts["correct"] + counts["modality"]) / judged)
            if judged
            else None,
            "strict_precision": _r(counts["correct"] / judged) if judged else None,
        }

    overall: Counter[str] = Counter()
    for counts in per.values():
        overall.update(counts)
    asserted = by_modality["asserted"]
    report = {
        "book": book_id,
        "title": book["title"],
        "author": book["author"],
        "role": book.get("role"),
        "source": {"url": book["url"], "sha256": sha, "matches_manifest": sha == book["sha256"]},
        "extractor": extractor,
        "claims_from": claims_file.name if claims_file else None,
        "sheet_pronouns": sheet_pronouns,
        "chapters": len(chapters),
        "words": sum(len(c.body.split()) for c in chapters),
        "characters": len(cast),
        "seconds": round(elapsed, 2),
        "claims": len(claims),
        "precision": {
            "overall": precision(overall),
            "asserted_only": precision(asserted),
            **{k: precision(v) for k, v in sorted(per.items())},
        },
        "by_modality": {k: dict(v) for k, v in sorted(by_modality.items())},
        "errors": dict(errors.most_common()),
        "recall": {
            "candidate_sentences": n_candidates,
            "unlabelled_sentences": recall["all"]["unlabelled_sentences"],
            **{
                k: {
                    "facts": v["facts"],
                    "found": v["found"],
                    "recall": _r(v["found"] / v["facts"]) if v["facts"] else None,
                }
                for k, v in recall.items()
                if v["facts"]
            },
        },
        "missed_examples": missed,
        "findings": {
            "total": len(findings),
            **{v: finding_counts[v] for v in (*FINDING_VERDICTS, "unlabelled")},
            "rows": finding_rows,
        },
        "wrong_examples": wrong_examples,
        "environment": {
            "machine": platform.machine(),
            "python": platform.python_version(),
            "commit": _git_commit(),
        },
    }
    return report, todo


def _same(a: str, b: str) -> bool:
    def norm(v: str) -> str:
        v = str(v).casefold()
        return {"gray": "grey", "blonde": "blond"}.get(v, v)

    return norm(a) == norm(b)


def _verdict(label: dict[str, Any], modality: str) -> str:
    if label["fact"] != "right":
        return "wrong"
    return "correct" if (modality == "asserted") == bool(label["asserted"]) else "modality"


def _r(x: float | None) -> float | None:
    return None if x is None else round(x, 4)


def to_markdown(report: dict[str, Any]) -> str:
    src = report["source"]
    lines = [
        f"*{report['title']}* ({report['author']}; {report['role']} book): {report['chapters']} "
        f"chapters, {report['words']:,} words, {report['characters']} characters listed. "
        f"Extractor `{report['extractor']}`"
        + ("" if report["sheet_pronouns"] else " (pronouns inferred, none on the sheets)")
        + f", {report['seconds']} s, {report['claims']} claims.",
        "",
        f"Source {src['url']} (sha256 {'matches' if src['matches_manifest'] else 'DIFFERS FROM'} "
        "the labelled file).",
        "",
        "| Claims | Correct | Modality wrong | Wrong | Unlabelled | Fact precision | "
        "Strict precision |",
        "|---|---|---|---|---|---|---|",
    ]
    for k, v in report["precision"].items():
        lines.append(
            f"| {k} | {v['correct']} | {v['modality']} | {v['wrong']} | {v['unlabelled']} | "
            f"{v['fact_precision']} | {v['strict_precision']} |"
        )
    rec = report["recall"]
    lines += [
        "",
        f"Recall on {rec['candidate_sentences']} candidate sentences "
        f"({rec['unlabelled_sentences']} unlabelled):",
        "",
        "| Facts | Labelled | Found | Recall |",
        "|---|---|---|---|",
    ]
    for k, v in rec.items():
        if isinstance(v, dict):
            lines.append(f"| {k} | {v['facts']} | {v['found']} | {v['recall']} |")
    f = report["findings"]
    lines += [
        "",
        f"Contradiction report: {f['total']} findings, {f['true']} real inconsistencies, "
        f"{f['false']} false alarms, {f['unlabelled']} unlabelled.",
    ]
    if report["errors"]:
        lines.append(
            "Errors by cause: " + ", ".join(f"{k} {v}" for k, v in report["errors"].items()) + "."
        )
    return "\n".join(lines)
