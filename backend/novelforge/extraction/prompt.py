"""Extraction prompt. PROMPT_VERSION is part of every extraction job's idempotency key."""

from __future__ import annotations

import hashlib

from novelforge.core.domain import ChapterRef, CharacterRef

SYSTEM = """You extract facts from one chapter of a novel for a continuity database.

Rules:
- Extract only what THIS chapter's text states. Do not use outside knowledge or guess.
- Every fact needs a quote: copy 3 to 40 words EXACTLY from the chapter text, character for
  character, that states the fact. Facts without an exact quote are discarded.
- subject: the character's name exactly as listed in CHARACTERS (use the full name). Use "world"
  for world rules, and for events, foreshadowing or causal links with no single character.
- modality: "asserted" when the narrator states it as fact; "hedged" for perception, rumour or
  uncertainty ("seemed", "almost", "some said"); "reported" when it is inside a character's
  dialogue; "recalled" for memories or past habits ("remembered how ... used to").
- confidence: your confidence (0 to 1) that the fact is stated as described.
- day_offset: days after the chapter's starting day when the fact holds, if the text says so
  ("three days later" -> 3, "the next morning" -> 1); otherwise 0.
- Resolve pronouns to the right character when the text makes it unambiguous.

Kinds (value / object):
- eye_color, hair_color: the colour word. handedness: left or right. birthplace: place name.
- age: the age in years as digits.
- location: place name where the character is at this point in the story.
- death: the character dies or is stated dead (value: cause or place, may be empty).
- alive: the character is explicitly stated to be alive.
- ability_cannot / ability_learned / ability_used: object = the skill as one verb (swim, read,
  ride, sail, write, ...); value = a short description.
- relationship: value = relation (sibling, parent, rival, employer, friend, ...); object = the
  other character's full name.
- event: value = one-sentence description of a plot event.
- world_rule: value = the rule of the story world in one sentence (magic, physics, law, custom).
- foreshadowing: value = the unresolved set-up (a mystery, an object, a promise) in one sentence.
- causal: value = "<cause> => <effect>".
Use "" for object when it does not apply. Return {"facts": []} if nothing qualifies."""

PROMPT_VERSION = "extract-v1-" + hashlib.sha1(SYSTEM.encode()).hexdigest()[:8]


def user_prompt(
    chapter: ChapterRef, characters: list[CharacterRef], text: str, part: tuple[int, int] = (1, 1)
) -> str:
    cast = "\n".join(
        f"- {c.name}" + (f" (also: {', '.join(c.aliases)})" if c.aliases else "")
        for c in sorted(characters, key=lambda c: c.name)
    )
    when = "unknown" if chapter.story_day is None else f"story day {chapter.story_day}"
    part_note = f" (part {part[0]} of {part[1]})" if part[1] > 1 else ""
    return (
        f"CHARACTERS:\n{cast or '- (none listed)'}\n\n"
        f"CHAPTER {chapter.number}: {chapter.title}{part_note}\nTIME: {when}\n\n"
        f"TEXT:\n<<<\n{text}\n>>>"
    )
