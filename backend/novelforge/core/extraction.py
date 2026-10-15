"""Rule-based fact extractor (`rules-v1`): a deterministic, explainable baseline.

It finds a small set of character attributes stated next to a character's name or alias:
eye colour, hair colour, age, handedness and birthplace. It does not resolve pronouns
("Her eyes were grey" is missed) or paraphrase; the LLM extractor in M3 is meant to close
that gap and is measured against this baseline.

Modality:
- reported: inside dialogue quotes (a character's words, not the narrator's)
- hedged: perception or rumour ("seemed", "almost", "some said")
- asserted: everything else
"""

import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from novelforge.core.domain import ChapterRef, CharacterRef, ExtractedClaim, Span
from novelforge.core.text import NUMBER_PATTERN, inside_dialogue, parse_number, sentence_bounds

EXTRACTOR = "rules-v1"
CLAIM_NAMESPACE = uuid.UUID("6c1f5c1e-2b7a-4c55-9a43-6f0d5e0b7a01")

CONFIDENCE = {"asserted": 0.9, "reported": 0.5, "hedged": 0.4}

_EYE = r"(?P<val>grey|gray|green|blue|brown|hazel|amber|black|violet)"
_HAIR = (
    r"(?P<val>black|brown|blond|blonde|red|auburn|grey|gray|white|silver|copper|chestnut|"
    r"golden|fair)"
)
_ADJ = r"(?:[a-z]+(?:-[a-z]+)?,? ){0,2}?"
_POSS = r"(?:['’]s|['’])"
_PLACE = r"(?P<val>[A-Z][a-z'’-]+(?: [A-Z][a-z'’-]+){0,3})"
_NUM = rf"(?P<val>{NUMBER_PATTERN})"
_HEDGES = re.compile(
    r"\b(?:seemed|seem|seems|looked|appeared|almost|nearly|perhaps|maybe|might|probably|"
    r"supposedly|apparently|rumou?red|rumou?rs?|as if|as though|some said|it was said|"
    r"they said|people said|or so)\b",
    re.IGNORECASE,
)
_CLAUSE_BREAK = re.compile(r"[;:—–]| - ")

# (predicate, pattern template). "{who}" becomes the character-name alternation.
RULES: list[tuple[str, str]] = [
    ("eye_color", rf"{{who}}{_POSS} {_ADJ}{_EYE} eyes\b"),
    (
        "eye_color",
        rf"{{who}}{_POSS} eyes (?:were|are|was|had been|had always been|seemed|looked|appeared)"
        rf"(?: almost| nearly| a| an)* {_ADJ}{_EYE}\b",
    ),
    ("eye_color", rf"{{who}} (?:had|has) {_ADJ}{_EYE} eyes\b"),
    ("hair_color", rf"{{who}}{_POSS} {_ADJ}{_HAIR} hair\b"),
    (
        "hair_color",
        rf"{{who}}{_POSS} hair (?:was|is|had been|seemed|looked)(?: almost| a| an)* "
        rf"{_ADJ}{_HAIR}\b",
    ),
    ("hair_color", rf"{{who}} (?:had|has) {_ADJ}{_HAIR} hair\b"),
    (
        "age",
        rf"{{who}} (?:was|is|had turned|turned|was now|is now) {_NUM}"
        r"(?= years? old| years of age|\s*[,.;:!?—])",
    ),
    ("age", rf"{{who}}, (?:now |then |aged )?{_NUM}(?=,)"),
    ("age", rf"\b{_NUM}-year-old {{who}}"),
    ("handedness", r"{who} (?:was|is|had always been) (?P<val>left|right)-handed\b"),
    ("handedness", r"\b(?:the|a) (?P<val>left|right)-handed {who}"),
    ("birthplace", rf"{{who}} (?:was|had been) born in {_PLACE}"),
    ("birthplace", rf"{{who}}, born in {_PLACE}"),
]


@dataclass(frozen=True)
class _Surface:
    text: str
    character: CharacterRef


def surface_forms(characters: Iterable[CharacterRef]) -> list[_Surface]:
    """Names and aliases that unambiguously refer to one character.

    A character's first name counts as an implicit alias when no other character shares it.
    Any surface form claimed by two characters is dropped rather than guessed.
    """
    chars = list(characters)
    owners: dict[str, set[str]] = {}
    by_id = {c.id: c for c in chars}
    for c in chars:
        forms = {c.name.strip(), *(a.strip() for a in c.aliases)}
        first = c.name.split()[0] if c.name.split() else ""
        if len(first) >= 3:
            forms.add(first)
        for f in forms:
            if f:
                owners.setdefault(f, set()).add(c.id)
    explicit: dict[str, set[str]] = {}
    for c in chars:
        for f in {c.name.strip(), *(a.strip() for a in c.aliases)}:
            explicit.setdefault(f, set()).add(c.id)
    out = []
    for form, ids in owners.items():
        # An implicit first-name alias loses to any explicit owner of the same text.
        if len(ids) > 1 and len(explicit.get(form, set())) == 1:
            ids = explicit[form]
        if len(ids) == 1:
            out.append(_Surface(form, by_id[next(iter(ids))]))
    return sorted(out, key=lambda s: (-len(s.text), s.text))


def _who_pattern(forms: list[_Surface]) -> str:
    alts = []
    for f in forms:
        escaped = re.escape(f.text)
        if f.text[0].isalpha():
            escaped = f"[{f.text[0].upper()}{f.text[0].lower()}]" + escaped[1:]
        alts.append(escaped)
    return r"(?<![\w'’])(?P<who>" + "|".join(alts) + r")(?!\w)"


def _normalize(predicate: str, raw: str) -> str | None:
    raw = raw.strip()
    if predicate in ("eye_color", "hair_color"):
        v = raw.lower()
        return {"gray": "grey", "blonde": "blond"}.get(v, v)
    if predicate == "age":
        n = parse_number(raw)
        return None if n is None or n > 130 else str(n)
    if predicate == "handedness":
        return raw.lower()
    return raw


def _modality(body: str, start: int, end: int) -> str:
    if inside_dialogue(body, start):
        return "reported"
    s, e = sentence_bounds(body, start, end)
    clause_start = s
    for m in _CLAUSE_BREAK.finditer(body, s, start):
        clause_start = m.end()
    nxt = _CLAUSE_BREAK.search(body, end, e)
    clause_end = nxt.start() if nxt else e
    if _HEDGES.search(body, clause_start, clause_end):
        return "hedged"
    return "asserted"


def extract_claims(chapter: ChapterRef, characters: Iterable[CharacterRef]) -> list[ExtractedClaim]:
    forms = surface_forms(characters)
    if not forms or not chapter.body:
        return []
    who = _who_pattern(forms)
    lookup = {f.text.lower(): f.character for f in forms}
    body = chapter.body
    seen: set[tuple[str, int, int]] = set()
    claims: list[ExtractedClaim] = []
    for predicate, template in RULES:
        pattern = re.compile(template.replace("{who}", who))
        for m in pattern.finditer(body):
            character = lookup.get(m.group("who").lower())
            value = _normalize(predicate, m.group("val"))
            if character is None or value is None:
                continue
            start, end = m.start(), m.end()
            if (predicate, start, end) in seen:
                continue
            seen.add((predicate, start, end))
            modality = _modality(body, start, end)
            key = f"{chapter.id}|{chapter.version}|{EXTRACTOR}|{predicate}|{start}|{end}"
            claims.append(
                ExtractedClaim(
                    id=str(uuid.uuid5(CLAIM_NAMESPACE, key)),
                    chapter_id=chapter.id,
                    chapter_version=chapter.version,
                    subject_id=character.id,
                    subject_text=m.group("who"),
                    predicate=predicate,
                    value=value,
                    raw_value=m.group("val"),
                    modality=modality,
                    confidence=CONFIDENCE[modality],
                    effective_day=chapter.story_day,
                    time_certainty="unknown" if chapter.story_day is None else "chapter_day",
                    extractor=EXTRACTOR,
                    spans=(Span(chapter.id, chapter.version, start, end, body[start:end]),),
                )
            )
    claims.sort(key=lambda c: (c.spans[0].start, c.predicate))
    return claims
