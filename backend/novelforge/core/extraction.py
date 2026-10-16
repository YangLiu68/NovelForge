"""Rule-based fact extractor (`rules-v6`): a deterministic, explainable baseline.

It finds facts stated next to a character's name or alias:
- attributes: eye colour, hair colour, age, handedness, birthplace
- location: "X was in P", "X arrived in P", "X had reached P"
- status: "X died ...", "X was dead", "X was alive"
- abilities: "X could not swim" (cannot), "X learned to swim" (learned), "X swam ..." (used)
- changes: "X dyed her hair red" (a hair_color claim marked as a change, see contradictions)
- time offsets inside a chapter: "Three days later X was in P" shifts that claim's story day

and, for attributes, two indirect forms (v4), each attributed only when unambiguous
(`core/coref.py`):
- a pronoun: "Mara looked up, her grey eyes narrowing", "She had ... gray eyes", "Ashford,
  where she was born"; the claim records the pronoun and its antecedent in `details.resolved`
- a "with" phrase on the sentence's subject: "Brooke was a grave, silent young man, with
  handsome brown eyes"

v4 over v3 (from reading real novels, `bench/real/`): the two indirect forms; ages in
apposition ("Margaret, the eldest of the four, was sixteen") and capitalised number words
("Fifteen-year-old Jo"); "yellow" hair and "curls"/"locks"; "sailed" counts as the skill only
with a vessel ("Amy sailed away" is travel); "wrote no more" is not a use; perception words hedge
only the words they govern ("Jo read as if alone" is still reading); conditionals hedge; titles
are never implicit aliases ("Miss" in "Miss Stacy" is not a name).

v5 over v4 (from the held-out books, so v5 is scored on a fresh held-out book): an age, place or
death inside a time clause ("ever since he was twenty", "before Anne came to Green Gables") is
`recalled`, not a statement about this point of the story; a "with" phrase whose owner is in the
previous sentence quotes from the pronoun, not across the sentence break.

v6 over v5 (one wrong attribution on the v5 held-out book): a sentence that opens with its
subject pronoun never takes a later name as the owner of a "with" phrase, and a sentence that
names only people of the other gender no longer stops a pronoun from reaching back further.

It does not read world rules, similes ("eyes the colour of sea glass") or implications
("Being left-handed, ..."); the LLM extractor is measured against this baseline.

Modality:
- reported: inside dialogue quotes (a character's words, not the narrator's)
- recalled: memory, habit or a time clause ("remembered how X used to ...", "since X was
  twenty"), not an event at this time
- hedged: perception governing the fact ("X's eyes seemed grey"), rumour or doubt anywhere in
  the clause ("some said", "perhaps"), or a condition before it ("if X was in P")
- asserted: everything else
"""

import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from novelforge.core.coref import (
    KIND,
    Mention,
    declared_pronouns,
    infer_pronouns,
    narrator_mentions,
    resolve,
)
from novelforge.core.domain import ChapterRef, CharacterRef, ExtractedClaim, Span
from novelforge.core.extraction_zh import EXTRACTOR_ZH, extract_claims_zh
from novelforge.core.lang import is_chinese
from novelforge.core.text import NUMBER_PATTERN, inside_dialogue, parse_number, sentence_bounds

EXTRACTOR = "rules-v6"
CLAIM_NAMESPACE = uuid.UUID("6c1f5c1e-2b7a-4c55-9a43-6f0d5e0b7a01")

CONFIDENCE = {"asserted": 0.9, "recalled": 0.8, "reported": 0.5, "hedged": 0.4}
RESOLVED_PENALTY = 0.1  # a fact reached through a pronoun or a "with" phrase is less certain
SKILL_VERBS = {
    "swim": "swam|swims|swimming",
    "ride": "rode|rides|riding",
    "read": "read|reads|reading",
    "sail": "sailed|sails|sailing",
    "write": "wrote|writes|writing",
}
_SKILL = r"(?P<val>swim|ride|read|sail|write)"
# "Amy sailed away" is travel, not the skill: bare "sailed" is not a use (see the vessel rule).
_USED = r"(?P<val>" + "|".join(f for k, f in SKILL_VERBS.items() if k != "sail") + r")"
_NOT_A_USE = r"(?! no more\b| nothing\b| never\b)"
_VESSEL = r"(?:boat|skiff|dinghy|yacht|sloop|ketch|cutter|schooner|ship)"
_VERB_TO_SKILL = {v: k for k, forms in SKILL_VERBS.items() for v in forms.split("|")}

_EYE = r"(?P<val>grey|gray|green|blue|brown|hazel|amber|black|violet)"
_HAIR = (
    r"(?P<val>black|brown|blond|blonde|red|auburn|grey|gray|white|silver|copper|chestnut|"
    r"golden|fair|yellow)"
)
_HAIR_NOUN = r"(?:hair|curls|locks|ringlets|tresses|braids|plaits)"
_ADJ = r"(?:[a-z]+(?:-[a-z]+)?,? ){0,2}?"
_POSS = r"(?:['’]s|['’])"
_PLACE = r"(?P<val>[A-Z][a-z'’-]+(?: [A-Z][a-z'’-]+){0,3})"
_NUM = rf"(?P<val>(?i:{NUMBER_PATTERN}))"
# Commas-and-"and" lists inside one clause: "a decided mouth, a comical nose, and sharp, "
_LIST = r"(?:[a-z-]+,? (?:and )?){0,10}?"
# Parenthetical phrases after a name: "Margaret, the eldest of the four, was ..."
_APPOS = r"(?:, [^,.;:!?“”\"]{1,40}){1,3},"
_PERSON_OF = r"(?:girl|boy|man|woman|lad|lass|child|youth|maiden|fellow|creature)"
# Perception hedges only the words it governs (inside the match): "X's eyes seemed grey" is
# hedged, "X read as if alone" and "X looked up, her grey eyes ..." are not.
_PERCEPTION = re.compile(r"\b(?:seemed|seem|seems|looked|appeared|almost|nearly)\b", re.I)
# A condition or supposition before the fact, in the same clause: "If X was in P".
_CONDITION = re.compile(
    r"\b(?:if|unless|whether|suppose|supposing|imagine|imagined|wish|wished|as if|as though|"
    r"seemed that|it seemed|it appeared)\b",
    re.IGNORECASE,
)
# Doubt or rumour anywhere in the clause.
_HEDGES = re.compile(
    r"\b(?:perhaps|maybe|might|probably|supposedly|apparently|rumou?red|rumou?rs?|some said|"
    r"it was said|they said|people said|or so)\b",
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
    ("hair_color", rf"{{who}}{_POSS} {_ADJ}{_HAIR} {_HAIR_NOUN}\b"),
    (
        "hair_color",
        rf"{{who}}{_POSS} hair (?:was|is|had been|seemed|looked)(?: almost| a| an)* "
        rf"{_ADJ}{_HAIR}\b",
    ),
    ("hair_color", rf"{{who}} (?:had|has) {_ADJ}{_HAIR} hair\b"),
    ("hair_color.change", rf"{{who}} (?:dyed|coloured|colored) (?:her|his|their) hair {_HAIR}\b"),
    (
        "age",
        rf"{{who}} (?:was|is|had turned|turned|was now|is now) {_NUM}"
        r"(?= years? old| years of age|\s*[,.;:!?—])",
    ),
    ("age", rf"{{who}}, (?:now |then |aged )?{_NUM}(?=,)"),
    (
        "age",
        rf"{{who}}{_APPOS} (?:was|is) {_NUM}(?= years? old| years of age|\s*[,.;:!?—])",
    ),
    ("age", rf"{{who}}, who (?:was|is) (?:now |then )?{_NUM}(?= years? old|\s*[,.;:!?—])"),
    (
        "age",
        rf"{{who}}(?:{_APPOS})? (?:was|is) an? (?:[a-z-]+,? ){{0,4}}{_PERSON_OF} of {_NUM}\b",
    ),
    ("age", rf"\b{_NUM}-year-old {{who}}"),
    ("age", rf"\b[Aa]t {_NUM}, {{who}}\b"),
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
    ("ability.used", rf"{{who}} {_USED}\b{_NOT_A_USE}"),
    # "X dove from the pier and swam ...": a second verb in the same clause.
    ("ability.used", rf"{{who}} [a-z]+(?: [a-z']+){{0,6}} and {_USED}\b{_NOT_A_USE}"),
    (
        "ability.used",
        rf"{{who}} (?P<val>sailed|sails) (?:the|a|an|her|his|their) (?:[a-z]+ )?{_VESSEL}\b",
    ),
]

# Attribute statements through a pronoun; "{pro}" is resolved by core/coref.py.
_PRO_POSS = r"(?P<pro>[Hh]is|[Hh]er|[Tt]heir)"
_PRO_SUBJ = r"(?P<pro>[Hh]e|[Ss]he|[Tt]hey)"
# "her wonderfully fair complexion, keen blue eyes": a list of features after one possessive,
# as long as no other owner ("his", "the", "of ...") starts inside it.
_OTHER_OWNER = r"(?!(?:his|her|their|its|my|your|our|the|a|an|of|with)\b)"
_POSS_LIST = rf"(?:{_OTHER_OWNER}[a-z-]+,? (?:and )?){{0,6}}?"
PRONOUN_RULES: list[tuple[str, str]] = [
    ("eye_color", rf"\b{_PRO_POSS} {_POSS_LIST}{_EYE} eyes\b"),
    (
        "eye_color",
        rf"\b{_PRO_POSS} eyes (?:were|was|are|is|had been|had always been|seemed|looked|appeared)"
        rf"(?: almost| nearly| a| an)* {_ADJ}{_EYE}\b",
    ),
    ("eye_color", rf"\b{_PRO_SUBJ} (?:had|has) {_LIST}{_ADJ}{_EYE} eyes\b"),
    ("hair_color", rf"\b{_PRO_POSS} {_POSS_LIST}{_HAIR} {_HAIR_NOUN}\b"),
    (
        "hair_color",
        rf"\b{_PRO_POSS} hair (?:was|is|had been|seemed|looked)(?: almost| a| an)* {_ADJ}{_HAIR}\b",
    ),
    ("hair_color", rf"\b{_PRO_SUBJ} (?:had|has) {_LIST}{_ADJ}{_HAIR} {_HAIR_NOUN}\b"),
    (
        "hair_color.change",
        rf"\b{_PRO_SUBJ} (?:dyed|coloured|colored) (?:her|his|their) hair {_HAIR}\b",
    ),
    ("handedness", rf"\b{_PRO_SUBJ} (?:was|is|had always been) (?P<val>left|right)-handed\b"),
    ("birthplace", rf"\b{_PRO_SUBJ} (?:was|had been) born in {_PLACE}"),
    ("birthplace", rf"\b{_PLACE}, where {_PRO_SUBJ} (?:was|had been) born\b"),
    (
        "age",
        rf"\b{_PRO_SUBJ} (?:was|is|had turned|turned|was now|is now) {_NUM}"
        r"(?= years? old| years of age|\s*[,.;:!?—])",
    ),
]

# "with ... grey eyes" belongs to the sentence's subject (a name or a resolvable pronoun).
_ITEMS = r"(?:[a-z-]+(?: [a-z-]+){0,4}, (?:and )?){0,4}"
WITH_RULES: list[tuple[str, str]] = [
    ("eye_color", rf"\bwith {_ITEMS}(?:[a-z-]+,? ){{0,3}}?{_EYE} eyes\b"),
    ("hair_color", rf"\bwith {_ITEMS}(?:[a-z-]+,? ){{0,3}}?{_HAIR} {_HAIR_NOUN}\b"),
]
_SENTENCE_LEAD = re.compile(r"[\s“”\"‘’'(—–-]*(?:(?:And|But|Then|So|Now|Yet),? )?")
_PREDICATE_NOMINAL = re.compile(
    r"\b(?:was|is|became|remained|seemed|looked)\s+(?:an?|the)\s+(?:[a-z-]+,?\s+){0,4}$"
)
_PERSON_WORD = re.compile(
    r"\b(?:girl|boy|woman|man|lady|gentleman|child|baby|stranger|person|figure|youth|lad|"
    r"lass|maid|maiden|fellow|sister|brother|mother|father|aunt|uncle|wife|husband|daughter|son|"
    r"friend|cousin|nurse|servant|people|children|women|men|girls|boys|whose|who)\b",
    re.IGNORECASE,
)
_CLAUSE_STOP = re.compile(r"[;:—–]| - ")
_TITLES = frozenset(
    {
        "mr", "mrs", "ms", "miss", "dr", "sir", "lady", "lord", "aunt", "uncle", "colonel",
        "captain", "professor", "old", "young", "little", "madame", "mme", "mademoiselle",
        "father", "mother", "saint", "st", "master", "mistress", "dame",
    }
)  # fmt: skip


@dataclass(frozen=True)
class _Surface:
    text: str
    character: CharacterRef


def surface_forms(characters: Iterable[CharacterRef]) -> list[_Surface]:
    """Names and aliases that unambiguously refer to one character.

    A character's first name counts as an implicit alias when no other character shares it
    and it is not a title ("Miss Stacy" does not make "Miss" a name). Any surface form claimed
    by two characters is dropped rather than guessed.
    """
    chars = list(characters)
    owners: dict[str, set[str]] = {}
    by_id = {c.id: c for c in chars}
    for c in chars:
        forms = {c.name.strip(), *(a.strip() for a in c.aliases)}
        first = c.name.split()[0] if c.name.split() else ""
        if len(first) >= 3 and first.rstrip(".").lower() not in _TITLES:
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
    if predicate == "hair_color.change":
        v = raw.lower()
        return "hair_color", {"gray": "grey", "blonde": "blond"}.get(v, v)
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


_OFFSET = re.compile(
    rf"\b(?:(?P<n>{NUMBER_PATTERN}|a|an) (?P<unit>days?|weeks?) later|"
    r"the (?:next|following) (?:day|morning|evening))\b",
    re.IGNORECASE,
)


def day_offset(body: str, start: int) -> int:
    """Days after the chapter's start, from a time phrase earlier in the same sentence."""
    s, _ = sentence_bounds(body, start, start + 1)
    found = list(_OFFSET.finditer(body, s, start))
    m = found[-1] if found else None
    if m is None:
        return 0
    if m.group("unit") is None:
        return 1
    raw = m.group("n").lower()
    n = 1 if raw in ("a", "an") else parse_number(raw) or 0
    return n * (7 if m.group("unit").lower().startswith("week") else 1)


# A state in a time clause belongs to another time: "ever since he was twenty", "since Jane
# was sixteen", "before Anne came to Green Gables" (found on the held-out books, see v5).
_PAST_CLAUSE = re.compile(r"\b(?:ever since|since|before|until|till|after)\s+$", re.IGNORECASE)
_PAST_AGE_CLAUSE = re.compile(r"\b(?:when|once)\s+$", re.IGNORECASE)
_TIMED = ("age", "location", "status")


def _modality(body: str, start: int, end: int, predicate: str | None = None) -> str:
    if inside_dialogue(body, start):
        return "reported"
    if predicate in _TIMED:
        before = body[max(0, start - 12) : start]
        if _PAST_CLAUSE.search(before) or (predicate == "age" and _PAST_AGE_CLAUSE.search(before)):
            return "recalled"
    s, e = sentence_bounds(body, start, end)
    clause_start = s
    for m in _CLAUSE_BREAK.finditer(body, s, start):
        clause_start = m.end()
    nxt = _CLAUSE_BREAK.search(body, end, e)
    clause_end = nxt.start() if nxt else e
    if _RECALL.search(body, clause_start, clause_end):
        return "recalled"
    if (
        _HEDGES.search(body, clause_start, clause_end)
        or _CONDITION.search(body, clause_start, end)
        or _PERCEPTION.search(body, start, end)
    ):
        return "hedged"
    return "asserted"


@dataclass(frozen=True)
class _Match:
    predicate: str
    raw: str
    character: CharacterRef
    subject_text: str
    start: int  # span start (the name, or the antecedent when it is in the same sentence)
    end: int
    resolved: dict | None = None
    phrase_start: int | None = None  # where the attribute words begin, for modality


def _sentence_subject(
    body: str,
    pos: int,
    end: int,
    mentions: list[Mention],
    all_mentions: list[Mention],
    pronouns: dict,
) -> tuple[Mention, dict] | None:
    """The character a "with ..." phrase at body[pos:end] describes: the sentence's subject, if
    it is a name or a resolvable pronoun and no other person comes between ("Mara sat with the
    girl with blue eyes" is not about Mara)."""
    s, _ = sentence_bounds(body, pos, pos + 1)
    lead = _SENTENCE_LEAD.match(body, s)
    first = lead.end() if lead else s
    owner = next((m for m in mentions if m.start == first), None)
    starts_with_pronoun = re.compile(r"(?:He|She|They)\b").match(body, first) is not None
    if owner is None and not starts_with_pronoun:
        # After an introductory phrase: "Lying on the grass ..., Mr. Brooke began ...". Not
        # when the sentence opens with its subject pronoun: in "He did look funny, Mary
        # thought, with his round blue eyes" the eyes are his, not Mary's (v6).
        lead_in = next((m for m in all_mentions if first <= m.start < pos), None)
        if (
            lead_in is not None
            and lead_in in mentions
            and body[lead_in.start - 2 : lead_in.start] == ", "
            and re.match(r" [a-z]", body[lead_in.end : lead_in.end + 2])
            and not _PERSON_WORD.search(body, first, lead_in.start)
            and not _CLAUSE_STOP.search(body, first, lead_in.start)
            and not inside_dialogue(body, first)
        ):
            owner = lead_in
    via: dict = {"via": "sentence_subject"}
    if owner is None:
        pro = re.compile(r"(?:He|She|They)\b").match(body, first)
        if pro is None:
            return None
        owner = resolve(body, first, pro.group(0), mentions, pronouns)
        if owner is None:
            return None
        via = {"via": "sentence_subject", "pronoun": pro.group(0), "pronoun_start": first}
        after = first + len(pro.group(0))
    else:
        after = owner.end
    between = body[after:end]
    if _CLAUSE_STOP.search(between) or inside_dialogue(body, pos):
        return None
    if any(after <= m.start < end for m in all_mentions):
        return None
    for w in _PERSON_WORD.finditer(between):
        if not _PREDICATE_NOMINAL.search(between[: w.start()]):
            return None
    return owner, via


def extractor_for(text: str) -> str:
    """The rule extractor's name for a text: `rules-zh-*` for Chinese, `rules-v6` otherwise."""
    return EXTRACTOR_ZH if is_chinese(text) else EXTRACTOR


def extract_claims(chapter: ChapterRef, characters: Iterable[CharacterRef]) -> list[ExtractedClaim]:
    if chapter.body and is_chinese(chapter.body):
        return extract_claims_zh(chapter, characters)
    characters = list(characters)
    forms = surface_forms(characters)
    if not forms or not chapter.body:
        return []
    who_src = who_pattern(forms)
    who = re.compile(who_src)
    lookup = {f.text.lower(): f.character for f in forms}
    body = chapter.body

    all_mentions = [
        Mention(m.start(), m.end(), lookup[m.group("who").lower()])
        for m in who.finditer(body)
        if m.group("who").lower() in lookup
    ]
    matches: list[_Match] = []
    for predicate, template in RULES:
        pattern = re.compile(template.replace("{who}", who_src))
        if template.startswith("{who}"):
            # Anchored at each mention: far cheaper than scanning every position.
            found = (pattern.match(body, m.start) for m in all_mentions)
        else:
            found = pattern.finditer(body)
        for m in found:
            if m is None:
                continue
            character = lookup.get(m.group("who").lower())
            if character is not None:
                matches.append(
                    _Match(predicate, m.group("val"), character, m.group("who"), m.start(), m.end())
                )

    narrator = narrator_mentions(body, who, lookup)
    pronouns = infer_pronouns(body, narrator)
    for c in characters:
        declared = declared_pronouns(c)
        if declared:
            pronouns[c.id] = declared
    for predicate, template in PRONOUN_RULES:
        for m in re.finditer(template, body):
            word = m.group("pro")
            if KIND.get(word.lower()) is None:
                continue
            ante = resolve(body, m.start("pro"), word, narrator, pronouns)
            if ante is None:
                continue
            s, _ = sentence_bounds(body, m.start(), m.end())
            start = ante.start if ante.start >= s else m.start()
            matches.append(
                _Match(
                    predicate,
                    m.group("val"),
                    ante.character,
                    body[ante.start : ante.end],
                    start,
                    m.end(),
                    {
                        "via": "pronoun",
                        "pronoun": word,
                        "pronoun_start": m.start("pro"),
                        "antecedent_start": ante.start,
                    },
                    m.start(),
                )
            )
    for predicate, template in WITH_RULES:
        for m in re.finditer(template, body):
            found = _sentence_subject(body, m.start(), m.end(), narrator, all_mentions, pronouns)
            if found is None:
                continue
            owner, via = found
            s, _ = sentence_bounds(body, m.start(), m.end())
            # The quote starts at the owner when it is in this sentence, else at the pronoun.
            start = owner.start if owner.start >= s else via.get("pronoun_start", m.start())
            matches.append(
                _Match(
                    predicate,
                    m.group("val"),
                    owner.character,
                    body[owner.start : owner.end],
                    start,
                    m.end(),
                    {**via, "antecedent_start": owner.start},
                    m.start(),
                )
            )

    seen: set[tuple[str, int, int]] = set()
    phrase_ends: set[tuple[str, int]] = set()
    claims: list[ExtractedClaim] = []
    for mt in matches:
        normalized = _normalize(mt.predicate, mt.raw)
        if normalized is None:
            continue
        final_predicate, value = normalized
        start, end = mt.start, mt.end
        if (final_predicate, start, end) in seen or (final_predicate, end) in phrase_ends:
            continue  # the same words already gave this fact (name rules come first)
        seen.add((final_predicate, start, end))
        phrase_ends.add((final_predicate, end))
        # "Mara looked up, her grey eyes": the perception check reads only the attribute words.
        modality = _modality(
            body, start if mt.phrase_start is None else mt.phrase_start, end, final_predicate
        )
        offset = day_offset(body, start)
        details: dict = {"change": True} if mt.predicate.endswith(".change") else {}
        if offset:
            details["day_offset"] = offset
        confidence = CONFIDENCE[modality]
        if mt.resolved is not None:
            details["resolved"] = mt.resolved
            confidence = round(confidence - RESOLVED_PENALTY, 2)
        key = f"{chapter.id}|{chapter.version}|{EXTRACTOR}|{final_predicate}|{start}|{end}"
        claims.append(
            ExtractedClaim(
                id=str(uuid.uuid5(CLAIM_NAMESPACE, key)),
                chapter_id=chapter.id,
                chapter_version=chapter.version,
                subject_id=mt.character.id,
                subject_text=mt.subject_text,
                predicate=final_predicate,
                value=value,
                raw_value=mt.raw,
                modality=modality,
                confidence=confidence,
                effective_day=None if chapter.story_day is None else chapter.story_day + offset,
                time_certainty="unknown" if chapter.story_day is None else "chapter_day",
                extractor=EXTRACTOR,
                spans=(Span(chapter.id, chapter.version, start, end, body[start:end]),),
                details=details,
            )
        )
    claims.sort(key=lambda c: (c.spans[0].start, c.predicate))
    return claims
