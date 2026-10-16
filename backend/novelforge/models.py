"""SQLAlchemy ORM models.

Workspace: Novel, Chapter, Revision, Character. Evidence: Passage (search unit, with an
optional embedding), Claim, EvidenceSpan. Infrastructure: EmbeddingCache, Job.
"""

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
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
        back_populates="novel",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Chapter.number",
    )
    characters: Mapped[list["Character"]] = relationship(
        back_populates="novel",
        cascade="all, delete-orphan",
        passive_deletes=True,
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
        Index("ix_passage_embedding_model", "novel_id", "embedding_model"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    novel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("novel.id", ondelete="CASCADE"))
    chapter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chapter.id", ondelete="CASCADE"))
    ordinal: Mapped[int] = mapped_column(Integer)
    start: Mapped[int] = mapped_column(Integer)  # code-point offsets into chapter.body
    end: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    # Chinese passages are indexed as character bigrams (see core.text.cjk_search_text); null
    # for text without Chinese, which is indexed as it is.
    search_text: Mapped[str | None] = mapped_column(Text)
    tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', coalesce(search_text, text))", persisted=True),
    )
    text_hash: Mapped[str] = mapped_column(String(64))
    # Dimension-less vector column: different embedders have different sizes. Each model gets its
    # own partial HNSW index on (embedding::vector(dim)) WHERE embedding_model = '<model>'.
    embedding: Mapped[Any | None] = mapped_column(Vector())
    embedding_model: Mapped[str | None] = mapped_column(String(120))


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
        Index("ix_claim_novel_status", "novel_id", "status"),
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
    # Predicates: eye_color, hair_color, handedness, birthplace, age, location, status,
    # ability:<skill>, event, relationship, world_rule, foreshadowing, causal.
    predicate: Mapped[str] = mapped_column(String(64))
    value: Mapped[str] = mapped_column(String(500))  # normalised
    raw_value: Mapped[str] = mapped_column(String(500))  # as written
    modality: Mapped[str] = mapped_column(String(16))  # asserted | hedged | reported | recalled
    confidence: Mapped[float] = mapped_column(Float)
    # proposed -> accepted | rejected. Only a human review moves a claim out of "proposed".
    status: Mapped[str] = mapped_column(String(16), default="proposed")
    extractor: Mapped[str] = mapped_column(String(64))
    effective_day: Mapped[int | None] = mapped_column(Integer)
    time_certainty: Mapped[str] = mapped_column(String(16))  # chapter_day | unknown
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # Stable identity of "the same statement" across re-extractions (subject, predicate, value,
    # quote); used to re-apply earlier review decisions after the chapter is edited.
    fingerprint: Mapped[str] = mapped_column(String(40), default="")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _now_column()

    evidence: Mapped[list["EvidenceSpan"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True, order_by="EvidenceSpan.start"
    )


class EvidenceSpan(Base):
    __tablename__ = "evidence_span"
    __table_args__ = (
        CheckConstraint('start >= 0 AND "end" > start', name="span_bounds"),
        Index("ix_evidence_span_claim", "claim_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claim.id", ondelete="CASCADE"))
    chapter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chapter.id", ondelete="CASCADE"))
    chapter_version: Mapped[int] = mapped_column(Integer)
    start: Mapped[int] = mapped_column(Integer)  # code-point offsets into chapter.body
    end: Mapped[int] = mapped_column(Integer)
    quote: Mapped[str] = mapped_column(Text)


class EmbeddingCache(Base):
    """Content-addressed embeddings: unchanged paragraphs are never embedded twice."""

    __tablename__ = "embedding_cache"

    model: Mapped[str] = mapped_column(String(120), primary_key=True)
    text_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    dim: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[Any] = mapped_column(Vector())
    created_at: Mapped[datetime] = _now_column()


class Job(Base):
    """A unit of background work. `key` makes enqueueing idempotent."""

    __tablename__ = "job"
    __table_args__ = (Index("ix_job_queue", "status", "run_after"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(64))
    key: Mapped[str] = mapped_column(String(300), unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    error: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    run_after: Mapped[datetime] = _now_column()
    created_at: Mapped[datetime] = _now_column()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Scene(Base):
    """A scene: the part of a chapter between scene breaks (a line of `* * *`, `***` or `---`)."""

    __tablename__ = "scene"
    __table_args__ = (UniqueConstraint("chapter_id", "ordinal"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    novel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("novel.id", ondelete="CASCADE"))
    chapter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chapter.id", ondelete="CASCADE"))
    ordinal: Mapped[int] = mapped_column(Integer)
    start: Mapped[int] = mapped_column(Integer)
    end: Mapped[int] = mapped_column(Integer)


class Location(Base):
    __tablename__ = "location"
    __table_args__ = (UniqueConstraint("novel_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    novel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("novel.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    aliases: Mapped[list[str]] = mapped_column(JSONB, default=list)
    description: Mapped[str] = mapped_column(Text, default="")
    # Minimum travel time in days to other locations, by name. Used by the travel check.
    travel_days: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = _now_column()

    __mapper_args__ = {"version_id_col": version, "eager_defaults": True}


class WorldRule(Base):
    """Canon: a rule of the story world (accepted from a claim or entered by the author)."""

    __tablename__ = "world_rule"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    novel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("novel.id", ondelete="CASCADE"))
    statement: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | retired
    source_claim_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("claim.id", ondelete="SET NULL")
    )
    source_chapter_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("chapter.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = _now_column()


class TimelineEvent(Base):
    """Canon: something that happened at a point in story time."""

    __tablename__ = "timeline_event"
    __table_args__ = (Index("ix_timeline_novel_day", "novel_id", "story_day"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    novel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("novel.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(32))  # death | travel | learned | event
    description: Mapped[str] = mapped_column(Text)
    subject_character_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("character.id", ondelete="CASCADE")
    )
    location: Mapped[str | None] = mapped_column(String(200))
    story_day: Mapped[int | None] = mapped_column(Integer)
    chapter_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("chapter.id", ondelete="SET NULL")
    )
    source_claim_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("claim.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = _now_column()


class PlotThread(Base):
    """Canon: a set-up the story owes a pay-off for (foreshadowing)."""

    __tablename__ = "plot_thread"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    novel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("novel.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open")  # open | resolved | dropped
    setup_chapter_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("chapter.id", ondelete="SET NULL")
    )
    payoff_chapter_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("chapter.id", ondelete="SET NULL")
    )
    source_claim_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("claim.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = _now_column()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Relationship(Base):
    __tablename__ = "relationship"
    __table_args__ = (
        UniqueConstraint("novel_id", "source_character_id", "target_character_id", "kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    novel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("novel.id", ondelete="CASCADE"))
    source_character_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("character.id", ondelete="CASCADE")
    )
    target_character_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("character.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(64))  # e.g. sibling, rival, employer, friend
    description: Mapped[str] = mapped_column(Text, default="")
    source_claim_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("claim.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = _now_column()


class CanonChange(Base):
    """Audit trail: every change to canon, who made it and which claim it came from."""

    __tablename__ = "canon_change"
    __table_args__ = (Index("ix_canon_change_novel", "novel_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    novel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("novel.id", ondelete="CASCADE"))
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[uuid.UUID | None] = mapped_column()
    field: Mapped[str] = mapped_column(String(64))
    old_value: Mapped[Any | None] = mapped_column(JSONB)
    new_value: Mapped[Any | None] = mapped_column(JSONB)
    source_claim_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("claim.id", ondelete="SET NULL")
    )
    actor: Mapped[str] = mapped_column(String(64), default="author")
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _now_column()


class ReviewDecision(Base):
    """A review decision keyed by claim fingerprint, re-applied when the claim is re-extracted."""

    __tablename__ = "review_decision"

    novel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("novel.id", ondelete="CASCADE"), primary_key=True
    )
    fingerprint: Mapped[str] = mapped_column(String(40), primary_key=True)
    decision: Mapped[str] = mapped_column(String(16))  # accepted | rejected
    note: Mapped[str | None] = mapped_column(Text)
    value: Mapped[str | None] = mapped_column(String(500))  # value edited during review
    decided_at: Mapped[datetime] = _now_column()


class StoredFinding(Base):
    """A contradiction finding with a lifecycle: open -> dismissed | resolved.

    `fingerprint` identifies the finding by its kind, subject and the evidence text (not offsets),
    so a dismissed finding stays dismissed across re-runs and edits elsewhere in the chapter,
    and comes back only when its evidence changes.
    """

    __tablename__ = "finding"
    __table_args__ = (
        UniqueConstraint("novel_id", "fingerprint"),
        Index("ix_finding_novel_status", "novel_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    novel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("novel.id", ondelete="CASCADE"))
    fingerprint: Mapped[str] = mapped_column(String(40))
    detector: Mapped[str] = mapped_column(String(64))  # rules | rule-judge:<llm>
    kind: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(32))
    subject_character_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("character.id", ondelete="CASCADE")
    )
    subject_name: Mapped[str] = mapped_column(String(200))
    predicate: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(16))
    explanation: Mapped[str] = mapped_column(Text)
    suggestion: Mapped[str] = mapped_column(Text)
    canon_value: Mapped[str | None] = mapped_column(String(500))
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(16), default="open")
    status_note: Mapped[str | None] = mapped_column(Text)
    auto_resolved: Mapped[bool] = mapped_column(default=False)
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = _now_column()
    last_seen_at: Mapped[datetime] = _now_column()


class WorkflowRun(Base):
    """A bounded plan -> draft -> critique (-> revise) run with human checkpoints.

    Status: planning | awaiting_plan_approval | drafting | critiquing | awaiting_decision |
    revising | applied | discarded | cancelled | failed.
    Nothing a run produces touches the manuscript or canon until the author applies the draft,
    which goes through the normal optimistic-locked chapter save.
    """

    __tablename__ = "workflow_run"
    __table_args__ = (Index("ix_workflow_novel", "novel_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    novel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("novel.id", ondelete="CASCADE"))
    chapter_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("chapter.id", ondelete="SET NULL")
    )
    base_version: Mapped[int | None] = mapped_column(Integer)  # chapter version when started
    goal: Mapped[str] = mapped_column(Text)
    llm: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(32), default="planning")
    iteration: Mapped[int] = mapped_column(Integer, default=0)
    max_iterations: Mapped[int] = mapped_column(Integer, default=2)
    plan: Mapped[str | None] = mapped_column(Text)
    draft: Mapped[str | None] = mapped_column(Text)
    critique: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    applied_chapter_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("chapter.id", ondelete="SET NULL")
    )
    applied_version: Mapped[int | None] = mapped_column(Integer)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float | None] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _now_column()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WorkflowStep(Base):
    """One LLM step of a run. (run, kind, iteration, attempt) is unique, so retries are explicit."""

    __tablename__ = "workflow_step"
    __table_args__ = (UniqueConstraint("run_id", "kind", "iteration", "attempt"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_run.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(16))  # plan | draft | revise | critique
    iteration: Mapped[int] = mapped_column(Integer)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(
        String(16), default="running"
    )  # running|done|cancelled|failed
    output: Mapped[str] = mapped_column(Text, default="")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float | None] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = _now_column()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StoryAuditRun(Base):
    """One story-logic audit of a whole novel (character motives, plot logic, pacing, plan).

    The audit is an LLM job, so the result is stored whole (JSONB) with the chapter versions it
    read; evidence in a chapter edited since is shown as stale instead of being re-anchored.
    Status: queued | running | done | failed.
    """

    __tablename__ = "story_audit"
    __table_args__ = (Index("ix_story_audit_novel", "novel_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    novel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("novel.id", ondelete="CASCADE"))
    llm: Mapped[str] = mapped_column(String(120))
    prompt_version: Mapped[str] = mapped_column(String(32))
    chapter_versions: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    progress: Mapped[str | None] = mapped_column(String(200))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float | None] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = _now_column()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
