"""SQLAlchemy ORM models.

M1 implements the entities the first vertical slice needs: Novel, Chapter, Revision, Passage,
Character, Claim, EvidenceSpan. Scene, Relationship, Location, WorldRule, TimelineEvent and
PlotThread arrive with the extraction pipeline in M3 (see PLAN.md).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _now_column() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Novel(Base):
    __tablename__ = "novel"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Set for imported samples so re-imports are idempotent; null for author-created novels.
    slug: Mapped[str | None] = mapped_column(String(100), unique=True)
    title: Mapped[str] = mapped_column(String(300))
    synopsis: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = _now_column()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    chapters: Mapped[list["Chapter"]] = relationship(
        back_populates="novel", cascade="all, delete-orphan", passive_deletes=True,
        order_by="Chapter.number",
    )
    characters: Mapped[list["Character"]] = relationship(
        back_populates="novel", cascade="all, delete-orphan", passive_deletes=True,
        order_by="Character.name",
    )

    __mapper_args__ = {"version_id_col": version, "eager_defaults": True}


class Chapter(Base):
    __tablename__ = "chapter"
    __table_args__ = (
        UniqueConstraint("novel_id", "number"),
        CheckConstraint("number >= 1", name="chapter_number_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    novel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("novel.id", ondelete="CASCADE"))
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text, default="")  # markdown source; spans index into it
    # In-story time: days since the story's day 0. Null means the chapter's time is unknown.
    story_day: Mapped[int | None] = mapped_column(Integer)
    story_time_label: Mapped[str | None] = mapped_column(String(200))
    content_hash: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = _now_column()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    novel: Mapped[Novel] = relationship(back_populates="chapters")
    passages: Mapped[list["Passage"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True, order_by="Passage.ordinal"
    )

    __mapper_args__ = {"version_id_col": version, "eager_defaults": True}


class Revision(Base):
    """Snapshot of a chapter after each successful save."""

    __tablename__ = "revision"
    __table_args__ = (UniqueConstraint("chapter_id", "version"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    chapter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chapter.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = _now_column()


class Passage(Base):
    """A paragraph-sized slice of a chapter body; the unit of search (and of embeddings in M2)."""

    __tablename__ = "passage"
    __table_args__ = (
        Index("ix_passage_tsv", "tsv", postgresql_using="gin"),
        Index("ix_passage_novel", "novel_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    novel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("novel.id", ondelete="CASCADE"))
    chapter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chapter.id", ondelete="CASCADE"))
    ordinal: Mapped[int] = mapped_column(Integer)
    start: Mapped[int] = mapped_column(Integer)  # code-point offsets into chapter.body
    end: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    tsv: Mapped[Any] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', text)", persisted=True)
    )


class Character(Base):
    __tablename__ = "character"
    __table_args__ = (UniqueConstraint("novel_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    novel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("novel.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    aliases: Mapped[list[str]] = mapped_column(JSONB, default=list)
    description: Mapped[str] = mapped_column(Text, default="")
    # Author-entered canon, e.g. {"eye_color": "grey"}. The character sheet is the source of
    # truth that extracted claims are checked against.
    attributes: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = _now_column()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    novel: Mapped[Novel] = relationship(back_populates="characters")

    __mapper_args__ = {"version_id_col": version, "eager_defaults": True}


class Claim(Base):
    """A fact extracted from text. Claims are proposals, never canon, until a human accepts them."""

    __tablename__ = "claim"
    __table_args__ = (
        Index("ix_claim_novel_subject", "novel_id", "subject_character_id", "predicate"),
        Index("ix_claim_chapter", "chapter_id"),
        CheckConstraint(
            "(time_certainty = 'unknown' AND effective_day IS NULL)"
            " OR (time_certainty <> 'unknown' AND effective_day IS NOT NULL)",
            name="claim_time_consistent",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    novel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("novel.id", ondelete="CASCADE"))
    chapter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chapter.id", ondelete="CASCADE"))
    chapter_version: Mapped[int] = mapped_column(Integer)
    subject_character_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("character.id", ondelete="CASCADE")
    )
    subject_text: Mapped[str] = mapped_column(String(200))
    predicate: Mapped[str] = mapped_column(String(64))
    value: Mapped[str] = mapped_column(String(200))  # normalised
    raw_value: Mapped[str] = mapped_column(String(200))  # as written
    modality: Mapped[str] = mapped_column(String(16))  # asserted | hedged | reported
    confidence: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default="proposed")
    extractor: Mapped[str] = mapped_column(String(32))
    effective_day: Mapped[int | None] = mapped_column(Integer)
    time_certainty: Mapped[str] = mapped_column(String(16))  # chapter_day | unknown
    created_at: Mapped[datetime] = _now_column()

    evidence: Mapped[list["EvidenceSpan"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True, order_by="EvidenceSpan.start"
    )


class EvidenceSpan(Base):
    __tablename__ = "evidence_span"
    __table_args__ = (
        CheckConstraint("start >= 0 AND \"end\" > start", name="span_bounds"),
        Index("ix_evidence_span_claim", "claim_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claim.id", ondelete="CASCADE"))
    chapter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chapter.id", ondelete="CASCADE"))
    chapter_version: Mapped[int] = mapped_column(Integer)
    start: Mapped[int] = mapped_column(Integer)  # code-point offsets into chapter.body
    end: Mapped[int] = mapped_column(Integer)
    quote: Mapped[str] = mapped_column(Text)
