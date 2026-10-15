"""Plain data types shared by the extraction and contradiction code (no database access)."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CharacterRef:
    id: str
    name: str
    aliases: tuple[str, ...] = ()
    attributes: dict[str, str] = field(default_factory=dict)  # canon from the character sheet


@dataclass(frozen=True)
class ChapterRef:
    id: str
    number: int
    title: str
    body: str
    version: int
    story_day: int | None = None


@dataclass(frozen=True)
class Span:
    chapter_id: str
    chapter_version: int
    start: int
    end: int
    quote: str


@dataclass(frozen=True)
class ExtractedClaim:
    id: str
    chapter_id: str
    chapter_version: int
    subject_id: str
    subject_text: str
    predicate: str
    value: str
    raw_value: str
    modality: str  # asserted | hedged | reported
    confidence: float
    effective_day: int | None
    time_certainty: str  # chapter_day | unknown
    extractor: str
    spans: tuple[Span, ...]
    details: dict[str, Any] = field(default_factory=dict)
