"""Score a story audit against a sample's labelled problems and traps (narrative_truth.yaml).

A reported issue finds a labelled problem when its kind is one the label accepts and it is in
the labelled chapter (an issue at the right place with another diagnosis is reported as
`located_other_kind`, not counted as found); character problems and knowledge leaks also need
the same character and a beat quote in the same paragraph as a labelled evidence span. A trap is
set off by a problem verdict on the same character in the trap's paragraph (for a knowledge
trap: a knowledge_leak for that character whose beat is in that paragraph; for a plot trap: an
issue of a forbidden kind in that chapter; for a pacing trap: a pacing issue covering that
chapter). Issues on an `ambiguous` label count as neither. Issues that match no label are listed
as unlabelled for a person to judge: they are not counted as false alarms, because the labels do
not claim to be complete.
"""

from __future__ import annotations

from typing import Any

from novelforge.core.domain import ChapterRef
from novelforge.core.text import split_passages
from novelforge.narrative.audit import Issue, StoryAudit
from novelforge.narrative.schema import PROBLEM_VERDICTS


def _paragraphs(chapter: ChapterRef, texts: list[str]) -> list[tuple[int, int]]:
    out = []
    for t in texts:
        pos = chapter.body.find(t)
        if pos < 0:
            raise ValueError(f"label text not in chapter {chapter.number}: {t!r}")
        for p in split_passages(chapter.body):
            if p.start <= pos < p.end or (pos <= p.start < pos + len(t)):
                out.append((p.start, p.end))
    return out


def _overlaps(issue: Issue, chapter: int, spans: list[tuple[int, int]], role: str = "beat") -> bool:
    return any(
        e.chapter == chapter and e.role == role and any(e.start < b and a < e.end for a, b in spans)
        for e in issue.evidence
    )


def _overlaps_any(issue: Issue, chapter: int, spans: list[tuple[int, int]]) -> bool:
    return any(
        e.chapter == chapter and any(e.start < b and a < e.end for a, b in spans)
        for e in issue.evidence
    )


def score(audit: StoryAudit, truth: dict[str, Any], chapters: list[ChapterRef]) -> dict[str, Any]:
    by_number = {c.number: c for c in chapters}

    def spans(item: dict[str, Any]) -> list[tuple[int, int]]:
        texts = [e["text"] for e in item["evidence"] if e["chapter"] == item["chapter"]]
        return _paragraphs(by_number[item["chapter"]], texts)

    matched: dict[str, str] = {}  # issue id -> label id
    problems = []
    for prob in truth.get("problems", []):
        hits = []
        for issue in audit.issues:
            if issue.kind not in prob["accept"]:
                continue
            if prob["kind"] == "pacing":
                ok = prob["chapter"] in issue.chapters
            elif issue.family == "character" or issue.kind == "knowledge_leak":
                ok = (
                    issue.chapter == prob["chapter"]
                    and issue.character == prob["character"]
                    and _overlaps(issue, prob["chapter"], spans(prob))
                )
            else:
                ok = issue.chapter == prob["chapter"]
            if ok:
                hits.append(issue.id)
                matched.setdefault(issue.id, prob["id"])
        # Flagged at the labelled place with another diagnosis (e.g. "against the character"
        # where the label says "villainy without cause"): reported, not counted as found.
        elsewhere = (
            [
                issue.id
                for issue in audit.issues
                if issue.id not in hits
                and issue.kind not in ("flat_stretch", "no_hook")
                and issue.chapter == prob["chapter"]
                and (not prob.get("character") or issue.character == prob["character"])
                and _overlaps_any(issue, prob["chapter"], spans(prob))
            ]
            if prob["kind"] != "pacing"
            else []
        )
        if not hits:
            for h in elsewhere:
                matched.setdefault(h, prob["id"])
        problems.append(
            {
                "id": prob["id"],
                "kind": prob["kind"],
                "found": bool(hits),
                "issues": hits,
                "located_other_kind": [] if hits else elsewhere,
            }
        )

    def flags(issue: Issue, item: dict[str, Any]) -> bool:
        """Does this issue land on a trap or an ambiguous label?"""
        kind = item.get("kind", "character")
        if kind == "knowledge":
            return (
                issue.kind == "knowledge_leak"
                and issue.character == item["character"]
                and _overlaps(issue, item["chapter"], spans(item))
            )
        if kind == "plot":
            # The trap's own passage, not any plot finding in its chapter: on 青崖问剑 a dangling
            # "why did he do it" in chapter 2 was first counted against the trap about a powder
            # paid off under another name in the same chapter.
            return (
                issue.family == "plot"
                and issue.kind in item["forbid"]
                and issue.chapter == item["chapter"]
                and (not item.get("evidence") or _overlaps_any(issue, item["chapter"], spans(item)))
            )
        if kind == "pacing":
            return issue.family == "pacing" and item["chapter"] in issue.chapters
        return (
            issue.family == "character"
            and issue.kind in PROBLEM_VERDICTS
            and issue.character == item["character"]
            and _overlaps(issue, item["chapter"], spans(item))
        )

    traps = []
    for trap in truth.get("traps", []):
        hits = [issue.id for issue in audit.issues if flags(issue, trap)]
        for h in hits:
            matched.setdefault(h, trap["id"])
        verdicts = []
        if trap.get("kind", "character") == "character":
            for j in audit.judgements:
                b = audit.beat(j.beat)
                if (
                    b.character == trap["character"]
                    and b.chapter == trap["chapter"]
                    and any(b.start < e and s < b.end for s, e in spans(trap))
                ):
                    verdicts.append(j.verdict)
        traps.append(
            {"id": trap["id"], "set_off": bool(hits), "issues": hits, "verdicts": verdicts}
        )

    ambiguous = []
    for amb in truth.get("ambiguous", []):
        hits = [issue.id for issue in audit.issues if flags(issue, amb)]
        for h in hits:
            matched.setdefault(h, amb["id"])
        ambiguous.append({"id": amb["id"], "flagged": bool(hits), "issues": hits})

    found = sum(p["found"] for p in problems)
    located = sum(bool(p["found"] or p["located_other_kind"]) for p in problems)
    set_off = sum(t["set_off"] for t in traps)
    by_kind: dict[str, dict[str, int]] = {}
    for p in problems:
        k = by_kind.setdefault(p["kind"], {"labelled": 0, "found": 0})
        k["labelled"] += 1
        k["found"] += int(p["found"])
    return {
        "problems_found": found,
        "problems": len(problems),
        "recall": round(found / len(problems), 3) if problems else None,
        "located": located,
        "by_kind": by_kind,
        "traps_set_off": set_off,
        "traps": len(traps),
        "issues_reported": len(audit.issues),
        "issues_on_labels": len(matched),
        "unlabelled_issues": [i.id for i in audit.issues if i.id not in matched],
        "problem_rows": problems,
        "trap_rows": traps,
        "ambiguous_rows": ambiguous,
    }
