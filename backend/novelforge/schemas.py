"""Request/response models for the HTTP API."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
ATTRIBUTE_KEY_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789_")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# Novels


class NovelCreate(BaseModel):
    title: Title
    synopsis: str = Field("", max_length=20_000)


class NovelUpdate(BaseModel):
    version: int
    title: Title | None = None
    synopsis: str | None = Field(None, max_length=20_000)


class NovelOut(ORM):
    id: uuid.UUID
    slug: str | None
    title: str
    synopsis: str
    version: int
    created_at: datetime
    updated_at: datetime
    chapter_count: int = 0
    character_count: int = 0


# Chapters


class ChapterCreate(BaseModel):
    title: Title
    body: str = Field("", max_length=2_000_000)
    number: int | None = Field(None, ge=1)
    story_day: int | None = None
    story_time_label: str | None = Field(None, max_length=200)


class ChapterUpdate(BaseModel):
    version: int
    title: Title | None = None
    body: str | None = Field(None, max_length=2_000_000)
    number: int | None = Field(None, ge=1)
    story_day: int | None = None
    story_time_label: str | None = Field(None, max_length=200)


class ChapterSummary(ORM):
    id: uuid.UUID
    novel_id: uuid.UUID
    number: int
    title: str
    story_day: int | None
    story_time_label: str | None
    version: int
    updated_at: datetime
    word_count: int = 0


class ChapterOut(ChapterSummary):
    body: str
    content_hash: str


class RevisionSummary(ORM):
    id: uuid.UUID
    version: int
    title: str
    content_hash: str
    created_at: datetime


class RevisionOut(RevisionSummary):
    body: str


# Characters


class CharacterCreate(BaseModel):
    name: Name
    aliases: list[str] = Field(default_factory=list, max_length=50)
    description: str = Field("", max_length=20_000)
    attributes: dict[str, str] = Field(default_factory=dict)

    @field_validator("attributes")
    @classmethod
    def _keys(cls, v: dict[str, str]) -> dict[str, str]:
        return _validate_attributes(v)


class CharacterUpdate(BaseModel):
    version: int
    name: Name | None = None
    aliases: list[str] | None = Field(None, max_length=50)
    description: str | None = Field(None, max_length=20_000)
    attributes: dict[str, str] | None = None

    @field_validator("attributes")
    @classmethod
    def _keys(cls, v: dict[str, str] | None) -> dict[str, str] | None:
        return None if v is None else _validate_attributes(v)


def _validate_attributes(v: dict[str, str]) -> dict[str, str]:
    for key in v:
        if not key or len(key) > 64 or not set(key) <= ATTRIBUTE_KEY_CHARS:
            raise ValueError(f"attribute key '{key}' must be lowercase snake_case")
    return {k: val.strip() for k, val in v.items() if val.strip()}


class CharacterOut(ORM):
    id: uuid.UUID
    novel_id: uuid.UUID
    name: str
    aliases: list[str]
    description: str
    attributes: dict[str, str]
    version: int
    updated_at: datetime


# Evidence, claims, search, report


class SpanOut(BaseModel):
    chapter_id: uuid.UUID
    chapter_number: int
    chapter_title: str
    chapter_version: int
    start: int
    end: int
    quote: str


class ClaimOut(BaseModel):
    id: uuid.UUID
    subject_character_id: uuid.UUID | None
    subject_name: str
    predicate: str
    value: str
    raw_value: str
    modality: str
    confidence: float
    status: str
    extractor: str
    effective_day: int | None
    time_certainty: str
    evidence: list[SpanOut]


class SearchHitOut(BaseModel):
    passage_id: uuid.UUID
    chapter_id: uuid.UUID
    chapter_number: int
    chapter_title: str
    chapter_version: int
    start: int
    end: int
    text: str
    score: float
    highlights: list[tuple[int, int]]


class SearchOut(BaseModel):
    query: str
    hits: list[SearchHitOut]
    took_ms: float


class EvidenceOut(BaseModel):
    claim_id: uuid.UUID
    chapter_id: uuid.UUID
    chapter_number: int
    chapter_title: str
    chapter_version: int
    start: int
    end: int
    quote: str
    value: str
    modality: str
    confidence: float
    effective_day: int | None
    time_certainty: str


class FindingOut(BaseModel):
    id: str
    kind: str
    category: str
    subject_id: uuid.UUID
    subject_name: str
    predicate: str
    severity: str
    explanation: str
    suggestion: str
    canon_value: str | None
    evidence: list[EvidenceOut]


class ReportOut(BaseModel):
    novel_id: uuid.UUID
    min_confidence: float
    claims_considered: int
    findings: list[FindingOut]
    took_ms: float


class SampleOut(BaseModel):
    name: str


class ImportOut(BaseModel):
    novel_id: uuid.UUID
    created: bool
