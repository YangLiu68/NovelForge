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


def to_predicate(kind: str, value: str, obj: str) -> tuple[str, str] | None:
    """Map an LLM fact onto (predicate, value). None means the fact is malformed."""
    value = value.strip()
    obj = obj.strip().lower()
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
