"""Basic contradiction report (M1).

Three checks over extracted claims at or above a confidence threshold:
- canon_conflict: a claim disagrees with the character sheet (author-entered canon).
- attribute_conflict: claims disagree on a static attribute and there is no canon to arbitrate.
- age_timeline: two ages for one character do not fit the in-story days between them.

Claims whose effective time is unknown are never used for the age check; the report says
nothing rather than guessing chapter chronology.
"""

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field

from novelforge.core.domain import ChapterRef, CharacterRef, ExtractedClaim

DAYS_PER_YEAR = 365.25

PREDICATES: dict[str, dict[str, str]] = {
    "eye_color": {"label": "eye colour", "category": "identity", "kind": "static"},
    "hair_color": {"label": "hair colour", "category": "identity", "kind": "static"},
    "handedness": {"label": "handedness", "category": "identity", "kind": "static"},
    "birthplace": {"label": "birthplace", "category": "identity", "kind": "static"},
    "age": {"label": "age", "category": "timeline", "kind": "temporal"},
}

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


@dataclass(frozen=True)
class Evidence:
    claim_id: str
    chapter_id: str
    chapter_number: int
    chapter_title: str
    chapter_version: int
    start: int
    end: int
    quote: str
    value: str
    modality: str
    confidence: float
    effective_day: int | None
    time_certainty: str


@dataclass
class Finding:
    id: str
    kind: str
    category: str
    subject_id: str
    subject_name: str
    predicate: str
    severity: str
    explanation: str
    suggestion: str
    evidence: list[Evidence] = field(default_factory=list)
    canon_value: str | None = None


def _canon_value(character: CharacterRef, predicate: str) -> str | None:
    raw = character.attributes.get(predicate)
    if raw is None or str(raw).strip() == "":
        return None
    value = str(raw).strip()
    if predicate in ("eye_color", "hair_color", "handedness"):
        value = value.lower()
        value = {"gray": "grey", "blonde": "blond"}.get(value, value)
    return value


def _finding_id(kind: str, subject_id: str, predicate: str, claims: list[ExtractedClaim]) -> str:
    key = "|".join([kind, subject_id, predicate, *sorted(c.id for c in claims)])
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def _chapter_list(numbers: list[int]) -> str:
    uniq = sorted(set(numbers))
    words = [f"chapter {n}" for n in uniq]
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def detect_contradictions(
    claims: list[ExtractedClaim],
    chapters: list[ChapterRef],
    characters: list[CharacterRef],
    min_confidence: float = 0.6,
) -> list[Finding]:
    chapter_by_id = {c.id: c for c in chapters}
    character_by_id = {c.id: c for c in characters}

    def evidence(claim: ExtractedClaim) -> list[Evidence]:
        ch = chapter_by_id[claim.chapter_id]
        return [
            Evidence(
                claim_id=claim.id,
                chapter_id=ch.id,
                chapter_number=ch.number,
                chapter_title=ch.title,
                chapter_version=span.chapter_version,
                start=span.start,
                end=span.end,
                quote=span.quote,
                value=claim.value,
                modality=claim.modality,
                confidence=claim.confidence,
                effective_day=claim.effective_day,
                time_certainty=claim.time_certainty,
            )
            for span in claim.spans
        ]

    def order(claim: ExtractedClaim) -> tuple[int, int]:
        return chapter_by_id[claim.chapter_id].number, claim.spans[0].start

    groups: dict[tuple[str, str], list[ExtractedClaim]] = defaultdict(list)
    for claim in claims:
        if (
            claim.confidence >= min_confidence
            and claim.predicate in PREDICATES
            and claim.chapter_id in chapter_by_id
            and claim.subject_id in character_by_id
        ):
            groups[(claim.subject_id, claim.predicate)].append(claim)

    findings: list[Finding] = []
    for (subject_id, predicate), group in groups.items():
        group.sort(key=order)
        character = character_by_id[subject_id]
        info = PREDICATES[predicate]
        if info["kind"] == "static":
            findings.extend(_static_findings(character, predicate, group, evidence, order))
        else:
            findings.extend(_age_findings(character, group, evidence, chapter_by_id))

    findings.sort(
        key=lambda f: (
            SEVERITY_ORDER[f.severity],
            min(e.chapter_number for e in f.evidence),
            f.subject_name,
            f.predicate,
        )
    )
    return findings


def _static_findings(character, predicate, group, evidence, order) -> list[Finding]:
    label = PREDICATES[predicate]["label"]
    category = PREDICATES[predicate]["category"]
    name = character.name
    canon = _canon_value(character, predicate)
    by_value: dict[str, list[ExtractedClaim]] = defaultdict(list)
    for claim in group:
        by_value[claim.value].append(claim)

    if canon is not None:
        out = []
        for value, conflicting in by_value.items():
            if value == canon:
                continue
            chapters = [order(c)[0] for c in conflicting]
            out.append(
                Finding(
                    id=_finding_id("canon_conflict", character.id, predicate, conflicting),
                    kind="canon_conflict",
                    category=category,
                    subject_id=character.id,
                    subject_name=name,
                    predicate=predicate,
                    severity="high",
                    explanation=(
                        f"The character sheet gives {name}'s {label} as '{canon}', but "
                        f"{_chapter_list(chapters)} {'says' if len(set(chapters)) == 1 else 'say'}"
                        f" '{value}'."
                    ),
                    suggestion=(
                        f"Change the text in {_chapter_list(chapters)} to '{canon}', or update the "
                        f"character sheet if '{value}' is now intended."
                    ),
                    evidence=[e for c in conflicting for e in evidence(c)],
                    canon_value=canon,
                )
            )
        return out

    if len(by_value) < 2:
        return []
    # Majority value wins the suggestion; ties go to the value stated first.
    ranked = sorted(by_value.items(), key=lambda kv: (-len(kv[1]), order(kv[1][0])))
    keep_value = ranked[0][0]
    others = [c for v, cs in ranked[1:] for c in cs]
    all_claims = [c for _, cs in ranked for c in cs]
    all_claims.sort(key=order)
    sides = "; ".join(f"'{v}' in {_chapter_list([order(c)[0] for c in cs])}" for v, cs in ranked)
    asserted = all(c.modality == "asserted" for c in all_claims)
    return [
        Finding(
            id=_finding_id("attribute_conflict", character.id, predicate, all_claims),
            kind="attribute_conflict",
            category=category,
            subject_id=character.id,
            subject_name=name,
            predicate=predicate,
            severity="high" if asserted else "medium",
            explanation=f"{name}'s {label} is stated inconsistently: {sides}.",
            suggestion=(
                f"Make {_chapter_list([order(c)[0] for c in others])} say '{keep_value}' "
                f"(the most frequent or earliest value), or record the intended {label} on the "
                f"character sheet."
            ),
            evidence=[e for c in all_claims for e in evidence(c)],
        )
    ]


def _age_findings(character, group, evidence, chapter_by_id) -> list[Finding]:
    name = character.name
    timed = [c for c in group if c.effective_day is not None]
    timed.sort(
        key=lambda c: (c.effective_day, chapter_by_id[c.chapter_id].number, c.spans[0].start)
    )
    out = []
    for a, b in zip(timed, timed[1:], strict=False):
        elapsed_days = b.effective_day - a.effective_day
        elapsed_years = elapsed_days / DAYS_PER_YEAR
        low = int(elapsed_years)
        delta = int(b.value) - int(a.value)
        if low <= delta <= low + 1:
            continue
        ch_a = chapter_by_id[a.chapter_id].number
        ch_b = chapter_by_id[b.chapter_id].number
        allowed = f"{int(a.value) + low} or {int(a.value) + low + 1}"
        out.append(
            Finding(
                id=_finding_id("age_timeline", character.id, "age", [a, b]),
                kind="age_timeline",
                category="timeline",
                subject_id=character.id,
                subject_name=name,
                predicate="age",
                severity="medium",
                explanation=(
                    f"{name} is {a.value} on story day {a.effective_day} (chapter {ch_a}) and "
                    f"{b.value} on story day {b.effective_day} (chapter {ch_b}). "
                    f"{elapsed_days} days pass between them, so the age should be {allowed}."
                ),
                suggestion=(
                    f"Change the age in chapter {ch_b} to {allowed}, or move chapter {ch_b} "
                    f"to about {delta} years after chapter {ch_a} on the timeline."
                    if delta > 0
                    else f"Change the age in chapter {ch_b} to {allowed}; an age cannot go down "
                    f"as story time moves forward."
                ),
                evidence=evidence(a) + evidence(b),
            )
        )
    return out
