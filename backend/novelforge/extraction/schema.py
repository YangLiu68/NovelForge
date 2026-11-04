"""The JSON schema the LLM must answer with, and how its kinds map onto claim predicates."""

from __future__ import annotations

KINDS = [
    "eye_color",
    "hair_color",
    "handedness",
    "birthplace",
    "age",
    "location",
    "death",
    "alive",
    "ability_cannot",
    "ability_learned",
    "ability_used",
    "relationship",
    "event",
    "world_rule",
    "foreshadowing",
    "causal",
]
MODALITIES = ["asserted", "hedged", "reported", "recalled"]

# Kinds whose subject may be the world rather than a character.
SUBJECTLESS = {"world_rule", "event", "foreshadowing", "causal"}

SCHEMA = {
    "title": "chapter_extraction",
    "type": "object",
    "additionalProperties": False,
    "required": ["facts"],
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "subject",
                    "kind",
                    "value",
                    "object",
                    "quote",
                    "modality",
                    "confidence",
                    "day_offset",
                ],
                "properties": {
                    "subject": {"type": "string"},
                    "kind": {"type": "string", "enum": KINDS},
                    "value": {"type": "string"},
                    "object": {"type": "string"},
                    "quote": {"type": "string"},
                    "modality": {"type": "string", "enum": MODALITIES},
                    "confidence": {"type": "number"},
                    "day_offset": {"type": "integer"},
                },
            },
        }
    },
}


# Chinese chapters add `presence` (on stage), which the Chinese rule extractor also emits so a
# dead character acting is caught without a place name. The English schema is unchanged, so
# recorded English runs still replay.
KINDS_ZH = [*KINDS, "presence"]
SCHEMA_ZH = {
    **SCHEMA,
    "properties": {
        "facts": {
            **SCHEMA["properties"]["facts"],
            "items": {
                **SCHEMA["properties"]["facts"]["items"],
                "properties": {
                    **SCHEMA["properties"]["facts"]["items"]["properties"],
                    "kind": {"type": "string", "enum": KINDS_ZH},
                },
            },
        }
    },
}


def _zh_colour(kind: str, value: str) -> str | None:
    """A Chinese colour word as written (琥珀色, 乌黑) -> the canonical value the rules use."""
    # The rule extractor's tables (that file is frozen as rules-zh-v3, so they are read, not moved).
    from novelforge.core.extraction_zh import _EYE_COLOURS as EYE
    from novelforge.core.extraction_zh import _HAIR_COLOURS as HAIR

    table = EYE if kind == "eye_color" else HAIR
    if value.lower() in set(table.values()):
        return value.lower()
    word = next((w for w in sorted(table, key=len, reverse=True) if w in value), None)
    return table[word] if word else None


def to_predicate(kind: str, value: str, obj: str, zh: bool = False) -> tuple[str, str] | None:
    """Map an LLM fact onto (predicate, value). None means the fact is malformed."""
    value = value.strip()
    obj = obj.strip().lower()
    if zh and kind in ("eye_color", "hair_color"):
        colour = _zh_colour(kind, value)
        return (kind, colour) if colour else None
    if zh and kind == "age":
        from novelforge.core.extraction_zh import parse_cn_number

        n = int(value) if value.isdigit() else parse_cn_number(value.removesuffix("岁"))
        return ("age", str(n)) if n is not None and 0 < n <= 130 else None
    if zh and kind == "presence":
        return "presence", "present"
    if kind in ("eye_color", "hair_color"):
        v = value.lower()
        return kind, {"gray": "grey", "blonde": "blond"}.get(v, v)
    if kind == "handedness":
        v = value.lower().replace("-handed", "").strip()
        return (kind, v) if v in ("left", "right") else None
    if kind == "age":
        from novelforge.core.text import parse_number

        n = parse_number(value.split()[0]) if value else None
        return ("age", str(n)) if n is not None and 0 < n <= 130 else None
    if kind in ("birthplace", "location"):
        return (kind, value) if value else None
    if kind == "death":
        return "status", "dead"
    if kind == "alive":
        return "status", "alive"
    if kind.startswith("ability_"):
        skill = obj.split()[0] if obj else ""
        return (f"ability:{skill}", kind.split("_", 1)[1]) if skill else None
    if kind in ("relationship", "event", "world_rule", "foreshadowing", "causal"):
        return (kind, value) if value else None
    return None
