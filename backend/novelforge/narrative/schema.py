"""JSON schemas for the story-logic stages, and the verdict and issue vocabularies.

Every schema is strict (all properties required, no extra keys) so the same schema works for
Claude structured outputs and for Ollama's `format`. Enumerations are English identifiers; the
text fields are written in the novel's language.
"""

from __future__ import annotations

NOTE_KINDS = (
    "background",  # family, history, past life
    "personality",  # temperament, principles, how they decide
    "goal",  # what they want
    "wound",  # trauma, fear, grudge
    "situation",  # money, status, health, who controls them
    "relationship",  # ties, debts, grudges with someone else
    "knowledge",  # a key piece of information and where it came from
)

VERDICTS = ("consistent", "unmotivated", "contradicts", "malice_without_cause")
# Computed verdicts can also be:
#   routine     not a choice that needs a reason (an everyday action, a natural reaction)
#   delayed     a later chapter explains it (a planted reveal, not a flaw)
#   unverified  (story-v1 runs only) called consistent with nothing cited
FINAL_VERDICTS = (*VERDICTS, "routine", "delayed", "unverified")
PROBLEM_VERDICTS = ("unmotivated", "contradicts", "malice_without_cause")

PLOT_KINDS = ("knowledge_leak", "deus_ex_machina", "dangling_setup", "causality")
# Asked for in the whole-story call; the other kinds have their own targeted checks.
PLOT_CALL_KINDS = ("causality",)
PACING_KINDS = ("flat_stretch", "no_hook")
EMOTIONS = ("thrill", "heartache", "suspense", "tension", "warmth", "anger", "calm")
TECHNIQUES = (
    "setup",  # plant a reason earlier
    "rewrite_motive",
    "blessing_in_disguise",  # a setback that opens an opportunity
    "reversal",
    "past_life_memory",
    "golden_finger",  # a special advantage that explains a fast rise
    "cliffhanger",
    "cost_and_payoff",
    "cut",
    "other",
)


def _obj(properties: dict, title: str | None = None) -> dict:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": list(properties),
        "properties": properties,
    }
    if title:
        schema = {"title": title, **schema}
    return schema


_STR = {"type": "string"}
_INT = {"type": "integer"}
_BOOL = {"type": "boolean"}
_STRS = {"type": "array", "items": _STR}

NOTES_SCHEMA = _obj(
    {
        "notes": {
            "type": "array",
            "items": _obj(
                {
                    "character": _STR,
                    "kind": {"type": "string", "enum": list(NOTE_KINDS)},
                    "text": _STR,
                    "quote": _STR,
                }
            ),
        }
    },
    "character_notes",
)

BEATS_SCHEMA = _obj(
    {
        "beats": {
            "type": "array",
            "items": _obj(
                {
                    "character": _STR,
                    "action": _STR,
                    "quote": _STR,
                    "hostile": _BOOL,
                    "target": _STR,
                    "cost": _STR,
                    "resolves_crisis": _BOOL,
                    "uses_secret": _BOOL,
                    "secret": _STR,
                }
            ),
        },
    },
    "chapter_beats",
)

SHAPE_SCHEMA = _obj(
    {
        "summary": _STR,
        "tension": _INT,
        "emotions": {"type": "array", "items": {"type": "string", "enum": list(EMOTIONS)}},
        "hook": _obj({"present": _BOOL, "quote": _STR}),
        "setups": {"type": "array", "items": _obj({"key": _STR, "text": _STR, "quote": _STR})},
    },
    "chapter_shape",
)

LEAK_SCHEMA = _obj(
    {
        "how": {"type": "string", "enum": ["saw", "heard", "told", "past_life", "none"]},
        "source": _STR,
        "source_notes": _STRS,
        "source_quote": _STR,
    },
    "knowledge_source",
)

# One beat per call. The model answers grounded sub-questions; the verdict is computed in code
# (audit._verdict), so a small model never has to weigh them up itself.
MOTIVE_SCHEMA = _obj(
    {
        "is_choice": _BOOL,
        "reason": _STR,
        "reason_notes": _STRS,
        "against": _STR,
        "against_notes": _STRS,
        "explanation": _STR,
        "severity": _INT,
        "fixes": _STRS,
    },
    "motive_check",
)

RESCUE_SCHEMA = _obj({"deus_ex_machina": _BOOL, "why": _STR, "fixes": _STRS}, "rescue_check")

LATER_SCHEMA = _obj({"explained_by": _STR, "why": _STR}, "later_explanation")

PLOT_SCHEMA = _obj(
    {
        "issues": {
            "type": "array",
            "items": _obj(
                {
                    "kind": {"type": "string", "enum": list(PLOT_CALL_KINDS)},
                    "chapter": _INT,
                    "character": _STR,
                    "refs": _STRS,
                    "explanation": _STR,
                    "severity": _INT,
                    "fixes": _STRS,
                }
            ),
        }
    },
    "plot_check",
)

PAYOFF_SCHEMA = _obj({"paid_off_by": _STR, "why": _STR}, "setup_payoff")

PLAN_SCHEMA = _obj(
    {
        "suggestions": {
            "type": "array",
            "items": _obj(
                {
                    "targets": _STRS,
                    "chapter": _INT,
                    "technique": {"type": "string", "enum": list(TECHNIQUES)},
                    "change": _STR,
                    "why": _STR,
                    "sample": _STR,
                }
            ),
        }
    },
    "revision_plan",
)
