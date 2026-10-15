"""Score a contradiction report against labelled ground truth.

Matching rule: a finding matches a labelled contradiction when kind, subject name and
predicate agree. Citation accuracy is span-level: a cited span is correct when it overlaps a
labelled evidence span in the same chapter.
"""

from dataclasses import asdict, dataclass

from novelforge.core.contradictions import Finding


@dataclass
class EvalResult:
    findings: int
    true_positives: int
    false_positives: int
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
    matched: list[str]
    missed: list[dict]
    false_positive_findings: list[dict]
    violated_negatives: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


def _ratio(num: int, den: int) -> float | None:
    return None if den == 0 else round(num / den, 4)


def _labelled_spans(gt_item: dict, bodies: dict[int, str]) -> list[tuple[int, int, int]]:
    spans = []
    for ev in gt_item.get("evidence", []):
        body = bodies[ev["chapter"]]
        start = body.find(ev["text"])
        if start < 0:
            raise ValueError(f"{gt_item['id']}: evidence text not found in chapter {ev['chapter']}")
        spans.append((ev["chapter"], start, start + len(ev["text"])))
    return spans


def evaluate(findings: list[Finding], ground_truth: dict, bodies: dict[int, str]) -> EvalResult:
    """`bodies` maps chapter number to chapter body text."""
    gt = ground_truth.get("contradictions", [])
    negatives = ground_truth.get("negatives", [])

    def key(kind: str, subject: str, predicate: str) -> tuple[str, str, str]:
        return kind, subject, predicate

    gt_by_key = {key(g["kind"], g["subject"], g["predicate"]): g for g in gt}
    matched_ids: set[str] = set()
    fp: list[Finding] = []
    cited = correct = 0
    covered = total = 0
    for f in findings:
        g = gt_by_key.get(key(f.kind, f.subject_name, f.predicate))
        if g is None:
            fp.append(f)
            continue
        if g["id"] in matched_ids:
            fp.append(f)  # duplicate finding for an already-matched contradiction
            continue
        matched_ids.add(g["id"])
        labelled = _labelled_spans(g, bodies)
        for e in f.evidence:
            cited += 1
            if any(
                ch == e.chapter_number and e.start < end and start < e.end
                for ch, start, end in labelled
            ):
                correct += 1
        for ch, start, end in labelled:
            total += 1
            if any(e.chapter_number == ch and e.start < end and start < e.end for e in f.evidence):
                covered += 1

    violated = [
        n["id"]
        for n in negatives
        if any(f.subject_name == n["subject"] and f.predicate == n["predicate"] for f in findings)
    ]
    detectable = [g for g in gt if g.get("m1_detectable", True)]
    tp = len(matched_ids)
    return EvalResult(
        findings=len(findings),
        true_positives=tp,
        false_positives=len(fp),
        false_negatives=len(gt) - tp,
        precision=_ratio(tp, tp + len(fp)),
        recall_all=_ratio(tp, len(gt)),
        recall_detectable=_ratio(
            len([g for g in detectable if g["id"] in matched_ids]), len(detectable)
        ),
        negatives=len(negatives),
        negatives_violated=len(violated),
        cited_spans=cited,
        cited_spans_correct=correct,
        citation_precision=_ratio(correct, cited),
        labelled_spans_covered=covered,
        labelled_spans_total=total,
        citation_recall=_ratio(covered, total),
        matched=sorted(matched_ids),
        missed=[
            {"id": g["id"], "reason": g.get("miss_reason", "")}
            for g in gt
            if g["id"] not in matched_ids
        ],
        false_positive_findings=[
            {"kind": f.kind, "subject": f.subject_name, "predicate": f.predicate} for f in fp
        ],
        violated_negatives=violated,
    )
