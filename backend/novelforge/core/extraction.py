"""Rule-based fact extractor (`rules-v2`): a deterministic, explainable baseline.

It finds facts stated next to a character's name or alias:
- attributes: eye colour, hair colour, age, handedness, birthplace
- location: "X was in P", "X arrived in P", "X had reached P"
- status: "X died ...", "X was dead", "X was alive"
- abilities: "X could not swim" (cannot), "X learned to swim" (learned), "X swam ..." (used)

It does not resolve pronouns ("Her eyes were grey" is missed) or paraphrase, and it does not
read world rules; the LLM extractor is measured against this baseline.

Modality:
- reported: inside dialogue quotes (a character's words, not the narrator's)
- recalled: memory or habit ("remembered how X used to ..."), not an event at this time
- hedged: perception or rumour ("seemed", "almost", "some said")
- asserted: everything else
"""

import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from novelforge.core.domain import ChapterRef, CharacterRef, ExtractedClaim, Span
from novelforge.core.text import NUMBER_PATTERN, inside_dialogue, parse_number, sentence_bounds

EXTRACTOR = "rules-v2"
CLAIM_NAMESPACE = uuid.UUID("6c1f5c1e-2b7a-4c55-9a43-6f0d5e0b7a01")

CONFIDENCE = {"asserted": 0.9, "recalled": 0.8, "reported": 0.5, "hedged": 0.4}
SKILL_VERBS = {
    "swim": "swam|swims|swimming",
    "ride": "rode|rides|riding",
    "read": "read|reads|reading",
    "sail": "sailed|sails|sailing",
    "write": "wrote|writes|writing",
}
_SKILL = r"(?P<val>swim|ride|read|sail|write)"
_USED = r"(?P<val>" + "|".join(SKILL_VERBS.values()) + r")"
_VERB_TO_SKILL = {v: k for k, forms in SKILL_VERBS.items() for v in forms.split("|")}

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
_RECALL = re.compile(
    r"\b(?:remembered|remembers|recalled|recalls|used to|in those days|long ago)\b",
    re.IGNORECASE,
)

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
    ("location", rf"{{who}} (?:was|were|is|stood|waited) (?:back )?(?:in|at) {_PLACE}"),
    ("location", rf"{{who}} (?:arrived|landed) (?:in|at) {_PLACE}"),
    ("location", rf"{{who}} (?:had )?(?:reached|returned to|came to) {_PLACE}"),
    ("status", r"{who} (?P<val>died|drowned|was killed|had died)\b"),
    ("status", r"{who} (?:was|lay) (?P<val>dead|alive)\b"),
    ("ability.cannot", rf"{{who}} (?:could not|couldn't|could never|was unable to) {_SKILL}\b"),
    ("ability.cannot", rf"{{who}} (?:had )?never learned (?:how )?to {_SKILL}\b"),
    ("ability.learned", rf"{{who}} (?:finally |had )?(?:learned|learnt) (?:how )?to {_SKILL}\b"),
    ("ability.learned", rf"{{who}} taught (?:himself|herself|themselves|themself) to {_SKILL}\b"),
    ("ability.used", rf"{{who}} {_USED}\b"),
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


def who_pattern(forms: list[_Surface]) -> str:
    alts = []
    for f in forms:
        escaped = re.escape(f.text)
        if f.text[0].isalpha():
            escaped = f"[{f.text[0].upper()}{f.text[0].lower()}]" + escaped[1:]
        alts.append(escaped)
    return r"(?<![\w'’])(?P<who>" + "|".join(alts) + r")(?!\w)"


def _normalize(predicate: str, raw: str) -> tuple[str, str] | None:
    """(final predicate, normalised value), or None to drop the match."""
    raw = raw.strip()
    if predicate.startswith("ability."):
        mode = predicate.split(".", 1)[1]
        skill = _VERB_TO_SKILL.get(raw.lower(), raw.lower()) if mode == "used" else raw.lower()
        return f"ability:{skill}", mode
    if predicate == "status":
        return "status", "alive" if raw.lower() == "alive" else "dead"
    value = _normalize_value(predicate, raw)
    return None if value is None else (predicate, value)


def _normalize_value(predicate: str, raw: str) -> str | None:
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
    if _RECALL.search(body, clause_start, clause_end):
        return "recalled"
    if _HEDGES.search(body, clause_start, clause_end):
        return "hedged"
    return "asserted"


def extract_claims(chapter: ChapterRef, characters: Iterable[CharacterRef]) -> list[ExtractedClaim]:
    forms = surface_forms(characters)
    if not forms or not chapter.body:
        return []
    who = who_pattern(forms)
    lookup = {f.text.lower(): f.character for f in forms}
    body = chapter.body
    seen: set[tuple[str, int, int]] = set()
    claims: list[ExtractedClaim] = []
    for predicate, template in RULES:
        pattern = re.compile(template.replace("{who}", who))
        for m in pattern.finditer(body):
            character = lookup.get(m.group("who").lower())
            normalized = _normalize(predicate, m.group("val"))
            if character is None or normalized is None:
                continue
            final_predicate, value = normalized
            start, end = m.start(), m.end()
            if (final_predicate, start, end) in seen:
                continue
            seen.add((final_predicate, start, end))
            modality = _modality(body, start, end)
            key = f"{chapter.id}|{chapter.version}|{EXTRACTOR}|{final_predicate}|{start}|{end}"
            claims.append(
                ExtractedClaim(
                    id=str(uuid.uuid5(CLAIM_NAMESPACE, key)),
                    chapter_id=chapter.id,
                    chapter_version=chapter.version,
                    subject_id=character.id,
                    subject_text=m.group("who"),
                    predicate=final_predicate,
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
