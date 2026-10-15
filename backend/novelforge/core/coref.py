"""Precision-first pronoun resolution for the rule extractor (no models, no database).

A wrong attribution is worse than a missed one: it puts one character's eye colour on another
and produces a false contradiction. So a pronoun is resolved only when the text leaves exactly
one candidate, and otherwise the fact is left to the LLM extractor:

- candidates are narrator mentions (outside dialogue) of listed characters in the same
  paragraph, in the pronoun's sentence or the `SENTENCES_BACK` sentences before it; the
  nearest sentence naming someone of the right (or unknown) gender decides;
- a candidate must have the pronoun's gender, either declared on the character sheet
  (`pronouns: she/her`) or inferred from the chapter (`infer_pronouns`);
- nothing is resolved when two different characters fit, when a candidate's pronouns are
  unknown, when a person noun of the same gender ("the girl", "her mother") or a titled
  unlisted name ("Mrs. Moffat") stands between the mention and the pronoun, or when the
  pronoun is inside dialogue. "they" is resolved only when one character is in the window.
"""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from novelforge.core.domain import CharacterRef
from novelforge.core.text import inside_dialogue, sentence_bounds

SENTENCES_BACK = 2
PRONOUNS = {
    "she": ("she", "her", "hers", "herself"),
    "he": ("he", "him", "his", "himself"),
    "they": ("they", "them", "their", "theirs", "themselves", "themself"),
}
KIND = {w: k for k, words in PRONOUNS.items() for w in words}

_PERSON_NOUNS = {
    "she": "girl|girls|woman|women|lady|ladies|sister|mother|mamma|mama|daughter|aunt|wife|"
    "queen|maid|maiden|princess|widow|niece|grandmother|bride|mistress|lass|governess|nurse",
    "he": "boy|boys|man|men|gentleman|gentlemen|brother|father|papa|son|uncle|husband|king|lad|"
    "fellow|prince|nephew|grandfather|grandpa|groom|master|lord|duke|sir",
}
_PERSON = {k: re.compile(rf"\b(?:{v})\b", re.IGNORECASE) for k, v in _PERSON_NOUNS.items()}
_ANY_PERSON = re.compile(
    rf"\b(?:{_PERSON_NOUNS['she']}|{_PERSON_NOUNS['he']}|child|children|baby|stranger|person|"
    r"people|figure|youth|friend|cousin|servant|someone|somebody|everyone|nobody|whose)\b",
    re.IGNORECASE,
)
_TITLED = re.compile(
    r"\b(?:Mr|Mrs|Ms|Miss|Dr|Aunt|Uncle|Sir|Lady|Lord|Madame|Mme|Mademoiselle|Professor|Captain|"
    r"Colonel)\.? [A-Z][a-z]"
)
# "she", "herself", "his", and "her" when a word that can follow a possessive comes next
_VOTE = re.compile(
    r"\b(?P<w>she|he|they|herself|himself|themselves|themself|his|their|her)\b"
    r"(?P<next>\s+[a-z]+)?",
    re.IGNORECASE,
)
_NOT_AFTER_POSSESSIVE = {
    "and", "as", "at", "but", "by", "for", "from", "in", "into", "of", "off", "on", "or", "out",
    "so", "than", "that", "the", "a", "an", "to", "up", "down", "away", "back", "again", "with",
    "when", "while", "then", "too", "now", "very", "all", "is", "was", "had", "would", "could",
}  # fmt: skip


@dataclass(frozen=True)
class Mention:
    start: int
    end: int
    character: CharacterRef


def declared_pronouns(character: CharacterRef) -> str | None:
    """'she', 'he' or 'they' from a `pronouns` entry on the character sheet ("she/her")."""
    raw = str(character.attributes.get("pronouns") or "").strip().lower()
    first = re.split(r"[/,\s]+", raw)[0] if raw else ""
    return KIND.get(first)


def narrator_mentions(body: str, who: re.Pattern[str], lookup: dict) -> list[Mention]:
    out = []
    for m in who.finditer(body):
        character = lookup.get(m.group("who").lower())
        if character is not None and not inside_dialogue(body, m.start()):
            out.append(Mention(m.start(), m.end(), character))
    return out


def infer_pronouns(body: str, mentions: list[Mention]) -> dict[str, str]:
    """Pronouns per character id from this chapter, where the evidence is clear.

    A vote is the first third-person pronoun after a mention in the same sentence, if no
    other mention or person noun comes first ("Jo laughed as she ..." votes 'she' for Jo).
    Object "her"/"him"/"them" are not votes (they usually mean someone else). A character
    needs two votes and a four-to-one majority.
    """
    votes: dict[str, Counter[str]] = defaultdict(Counter)
    for i, m in enumerate(mentions):
        _, sentence_end = sentence_bounds(body, m.start, m.end)
        limit = sentence_end
        if i + 1 < len(mentions):
            limit = min(limit, mentions[i + 1].start)
        for v in _VOTE.finditer(body, m.end, limit):
            if _ANY_PERSON.search(body, m.end, v.start()) or inside_dialogue(body, v.start()):
                break
            word = v.group("w").lower()
            if word == "her":
                nxt = (v.group("next") or "").strip().lower()
                if not nxt or nxt in _NOT_AFTER_POSSESSIVE:
                    continue  # probably object "her": not a vote, keep looking
            votes[m.character.id][KIND[word]] += 1
            break
    out = {}
    for cid, counts in votes.items():
        kind, n = counts.most_common(1)[0]
        if n >= 2 and n >= 0.8 * sum(counts.values()):
            out[cid] = kind
    return out


def _sentence_starts(body: str, a: int, b: int) -> list[int]:
    starts = [a]
    pos = a
    while pos < b:
        _, end = sentence_bounds(body, pos, pos)
        nxt = end
        while nxt < len(body) and body[nxt].isspace():
            nxt += 1
        if nxt >= b or nxt <= pos:
            break
        starts.append(nxt)
        pos = nxt
    return starts


def resolve(
    body: str,
    pos: int,
    pronoun: str,
    mentions: list[Mention],
    pronouns: dict[str, str],
) -> Mention | None:
    """The one mention a pronoun at `pos` can refer to, or None.

    The nearest sentence that mentions a possible referent decides: the pronoun's own sentence
    (before it), else the previous one, else the one before that. A sentence that names only
    people of the other gender is skipped ("his" cannot be Mara). The deciding sentence must
    hold exactly one character of the pronoun's gender and none of unknown gender; otherwise
    nothing is resolved (earlier sentences are not consulted, since the nearer ambiguity
    already makes it unsafe).
    """
    kind = KIND.get(pronoun.lower())
    if kind is None or inside_dialogue(body, pos):
        return None
    para = body.rfind("\n\n", 0, pos)
    para = 0 if para < 0 else para + 2
    starts = _sentence_starts(body, para, pos)
    window = starts[max(0, len(starts) - 1 - SENTENCES_BACK)]
    in_window = [m for m in mentions if window <= m.start and m.end <= pos]
    if not in_window:
        return None
    if kind == "they" and len({m.character.id for m in in_window}) != 1:
        return None  # "they" may be plural whenever two people are in view
    bounds = [*starts[max(0, len(starts) - 1 - SENTENCES_BACK) :], pos]
    for lo, hi in reversed(list(zip(bounds, bounds[1:], strict=False))):
        level = [m for m in in_window if lo <= m.start < hi]
        if not level:
            continue
        if any(pronouns.get(m.character.id) is None for m in level):
            return None
        fits = [m for m in level if pronouns[m.character.id] == kind]
        if not fits:
            continue  # only people of the other gender here: look one sentence further back
        if len({m.character.id for m in fits}) != 1:
            return None
        last = fits[-1]
        between = body[last.end : pos]
        if kind in _PERSON and _PERSON[kind].search(between):
            return None
        for t in _TITLED.finditer(between):
            if not any(m.start <= last.end + t.start() < m.end for m in mentions):
                return None
        return last
    return None
