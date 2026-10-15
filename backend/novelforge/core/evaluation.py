"""Score contradiction findings against labelled ground truth.

Matching rule: a finding detects a labelled contradiction when
- the categories agree (identity, timeline, location, abilities, world_rules),
- the subject agrees (character name; for world rules any rule finding qualifies), and
- a cited span overlaps the planted statement itself (the last labelled evidence span). Citing
  only the earlier, correct statement is not enough: a false alarm about the same character can
  cite it by accident.
Kinds are reported but not required to match: a conflict reported against the character sheet
instead of against an earlier sentence is still the same error.

A second finding for an already-detected contradiction is a duplicate, not a false positive.
A negative case is violated when a false-positive finding cites a span overlapping the
negative's evidence (or, for labels without evidence, has the negative's subject and predicate).
Citation precision: share of cited spans in true-positive findings that overlap labelled
evidence of the matched contradiction.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

KIND_CATEGORY = {
    "attribute_conflict": "identity",
    "canon_conflict": "identity",
    "age_timeline": "timeline",
    "dead_character_active": "timeline",
    "location_conflict": "location",
    "ability_conflict": "abilities",
    "world_rule_violation": "world_rules",
}


@dataclass
class EvalResult:
    findings: int
    true_positives: int
    false_positives: int
    duplicates: int
    false_negatives: int
    precision: float | None
    recall_all: float | None
    recall_detectable: float | None
    negatives: int
    negatives_violated: int
    cited_spans: int
    cited_spans_correct: int
    citation_precision: float | None
    labelled_spans_covered: int
    labelled_spans_total: int
    citation_recall: float | None
    by_category: dict[str, dict[str, Any]]
    matched: list[str]
    missed: list[dict]
    false_positive_findings: list[dict]
    violated_negatives: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


def _ratio(num: int, den: int) -> float | None:
    return None if den == 0 else round(num / den, 4)


def normalize_finding(f: Any) -> dict[str, Any]:
    """Accept core Finding objects or stored-finding dicts."""
    get = f.get if isinstance(f, dict) else lambda k, d=None: getattr(f, k, d)
    evidence = get("evidence") or []
    spans = []
    for e in evidence:
        eg = e.get if isinstance(e, dict) else lambda k, d=None, e=e: getattr(e, k, d)
        spans.append((eg("chapter_number"), eg("start"), eg("end")))
    kind = get("kind")
    return {
        "kind": kind,
        "category": get("category") or KIND_CATEGORY.get(kind, "identity"),
        "subject": get("subject_name"),
        "predicate": get("predicate"),
        "spans": spans,
    }


def _labelled_spans(item: dict, bodies: dict[int, str]) -> list[tuple[int, int, int]]:
    spans = []
    for ev in item.get("evidence", []):
        if "start" in ev:
            spans.append((ev["chapter"], ev["start"], ev["end"]))
            continue
        body = bodies[ev["chapter"]]
        start = body.find(ev["text"])
        if start < 0:
            raise ValueError(f"{item['id']}: evidence text not found in chapter {ev['chapter']}")
        spans.append((ev["chapter"], start, start + len(ev["text"])))
    return spans


def _overlaps(a: tuple[int, int, int], b: tuple[int, int, int]) -> bool:
    return a[0] == b[0] and a[1] < b[2] and b[1] < a[2]


def evaluate(findings: list[Any], ground_truth: dict, bodies: dict[int, str]) -> EvalResult:
    """`bodies` maps chapter number to chapter body text."""
    gt = ground_truth.get("contradictions", [])
    negatives = ground_truth.get("negatives", [])
    norm = [normalize_finding(f) for f in findings]
    labelled = {g["id"]: _labelled_spans(g, bodies) for g in gt}
    for g in gt:
        g.setdefault("category", KIND_CATEGORY.get(g.get("kind"), "identity"))

    matched: dict[str, dict] = {}
    fps: list[dict] = []
    duplicates = 0
    cited = correct = 0
    for f in norm:
        candidates = [
            g
            for g in gt
            if g["category"] == f["category"]
            and (g["category"] == "world_rules" or g["subject"] == f["subject"])
            and any(_overlaps(s, labelled[g["id"]][-1]) for s in f["spans"])
        ]
        if not candidates:
            fps.append(f)
            continue
        # Prefer a contradiction nobody has matched yet (two labels can share a sentence, e.g.
        # the death sentence behind two "dead character active" labels).
        open_ = [g for g in candidates if g["id"] not in matched]
        if not open_:
            duplicates += 1
            continue
        target = open_[0]
        matched[target["id"]] = f
        for s in f["spans"]:
            cited += 1
            correct += any(_overlaps(s, ls) for ls in labelled[target["id"]])

    covered = total = 0
    for gid, f in matched.items():
        for ls in labelled[gid]:
            total += 1
            covered += any(_overlaps(s, ls) for s in f["spans"])

    # A negative is violated by a false alarm about it. A correct finding for a labelled
    # contradiction may legitimately cite the same sentence (e.g. "her hair was red now", followed
    # later by a planted "grey"), so only unmatched findings count here.
    violated = []
    for n in negatives:
        n_spans = _labelled_spans(n, bodies) if n.get("evidence") else []
        if n_spans:
            hit = any(_overlaps(s, ns) for f in fps for s in f["spans"] for ns in n_spans)
        else:
            hit = any(
                f["subject"] == n["subject"] and f["predicate"] == n["predicate"] for f in fps
            )
        if hit:
            violated.append(n["id"])

    by_category: dict[str, dict[str, Any]] = {}
    for g in gt:
        c = by_category.setdefault(g["category"], {"labelled": 0, "detected": 0, "fp": 0})
        c["labelled"] += 1
        c["detected"] += g["id"] in matched
    for f in fps:
        by_category.setdefault(f["category"], {"labelled": 0, "detected": 0, "fp": 0})["fp"] += 1
    for c in by_category.values():
        c["recall"] = _ratio(c["detected"], c["labelled"])

    detectable = [g for g in gt if g.get("m1_detectable", True) is not False]
    tp = len(matched)
    return EvalResult(
        findings=len(norm),
        true_positives=tp,
        false_positives=len(fps),
        duplicates=duplicates,
        false_negatives=len(gt) - tp,
        precision=_ratio(tp, tp + len(fps)),
        recall_all=_ratio(tp, len(gt)),
        recall_detectable=_ratio(
            len([g for g in detectable if g["id"] in matched]), len(detectable)
        ),
        negatives=len(negatives),
        negatives_violated=len(violated),
        cited_spans=cited,
        cited_spans_correct=correct,
        citation_precision=_ratio(correct, cited),
        labelled_spans_covered=covered,
        labelled_spans_total=total,
        citation_recall=_ratio(covered, total),
        by_category=dict(sorted(by_category.items())),
        matched=sorted(matched),
        missed=[
            {
                "id": g["id"],
                "category": g["category"],
                "kind": g.get("kind"),
                "reason": g.get("miss_reason", ""),
            }
            for g in gt
            if g["id"] not in matched
        ],
        false_positive_findings=[
            {
                "kind": f["kind"],
                "subject": f["subject"],
                "predicate": f["predicate"],
                "spans": f["spans"],
            }
            for f in fps[:20]
        ],
        violated_negatives=violated,
    )
