"""A mock LLM that answers extraction prompts using the rule extractor.

It reads the character list and text back out of the prompt, runs the rule extractor on the text and
returns the facts in the LLM schema. This exercises the whole LLM path (windows, schema
validation, quote verification, persistence, review) offline and deterministically. Benchmarks
label it `mock`; its quality is, by construction, the rule extractor's.
"""

from __future__ import annotations

import re
from typing import Any

from novelforge.core.domain import ChapterRef, CharacterRef
from novelforge.core.extraction import extract_claims
from novelforge.llm.mock import MockLLM

_CAST_LINE = re.compile(r"^- (?P<name>[^(\n]+?)(?: \(also: (?P<aliases>[^)]*)\))?$", re.M)


def _respond(system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
    cast_block = prompt.split("CHARACTERS:\n", 1)[1].split("\n\n", 1)[0]
    characters = [
        CharacterRef(
            id=m.group("name").strip(),
            name=m.group("name").strip(),
            aliases=tuple(a.strip() for a in (m.group("aliases") or "").split(",") if a.strip()),
        )
        for m in _CAST_LINE.finditer(cast_block)
        if m.group("name").strip() != "(none listed)"
    ]
    text = prompt.split("TEXT:\n<<<\n", 1)[1].rsplit("\n>>>", 1)[0]
    facts = []
    for c in extract_claims(ChapterRef("mock", 0, "", text, 0, None), characters):
        kind, obj = c.predicate, ""
        if c.predicate == "status":
            kind = "death" if c.value == "dead" else "alive"
        elif c.predicate.startswith("ability:"):
            kind, obj = f"ability_{c.value}", c.predicate.split(":", 1)[1]
        facts.append(
            {
                "subject": c.subject_id,
                "kind": kind,
                "value": c.raw_value if kind.startswith("ability_") else c.value,
                "object": obj,
                "quote": c.spans[0].quote,
                "modality": c.modality,
                "confidence": c.confidence,
                "day_offset": 0,
            }
        )
    return {"facts": facts}


def rules_backed_mock() -> MockLLM:
    llm = MockLLM(name="mock")
    llm.on_schema("chapter_extraction", _respond)
    return llm
