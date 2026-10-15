"""Data derived from chapter text: search passages and extracted claims.

Both are rebuilt in the same transaction as the edit that changed their inputs, keyed by
chapter id, chapter version and extractor, so running a rebuild twice gives identical rows.
"""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from novelforge.config import get_settings
from novelforge.core.domain import ChapterRef, CharacterRef
from novelforge.core.extraction import EXTRACTOR, extract_claims
from novelforge.core.text import content_hash, split_passages
from novelforge.models import Chapter, Character, Claim, EvidenceSpan, Passage
from novelforge.retrieval.index import enqueue_chapter_embedding

PASSAGE_NAMESPACE = uuid.UUID("a3c6f0f4-8f0e-4c2b-9a51-0d6c7e1b9f02")
SPAN_NAMESPACE = uuid.UUID("d2f1b6a9-3e47-4b8c-8f4d-5a0e6c9b1d03")


def chapter_ref(chapter: Chapter) -> ChapterRef:
    return ChapterRef(
        id=str(chapter.id),
        number=chapter.number,
        title=chapter.title,
        body=chapter.body,
        version=chapter.version,
        story_day=chapter.story_day,
    )


def character_refs(session: Session, novel_id: uuid.UUID) -> list[CharacterRef]:
    rows = session.scalars(select(Character).where(Character.novel_id == novel_id)).all()
    return [
        CharacterRef(
            id=str(c.id),
            name=c.name,
            aliases=tuple(c.aliases or ()),
            attributes=dict(c.attributes or {}),
        )
        for c in rows
    ]


def rebuild_passages(session: Session, chapter: Chapter) -> None:
    session.execute(delete(Passage).where(Passage.chapter_id == chapter.id))
    for i, span in enumerate(split_passages(chapter.body)):
        session.add(
            Passage(
                id=uuid.uuid5(PASSAGE_NAMESPACE, f"{chapter.id}|{chapter.version}|{i}"),
                novel_id=chapter.novel_id,
                chapter_id=chapter.id,
                ordinal=i,
                start=span.start,
                end=span.end,
                text=span.text,
                text_hash=content_hash(span.text),
            )
        )
    # Embeddings are computed by a background job (cache-aware: unchanged paragraphs are free).
    enqueue_chapter_embedding(session, chapter, get_settings().embedder)


def rebuild_claims(
    session: Session, chapter: Chapter, characters: list[CharacterRef] | None = None
) -> int:
    if characters is None:
        characters = character_refs(session, chapter.novel_id)
    session.execute(
        delete(Claim).where(Claim.chapter_id == chapter.id, Claim.extractor == EXTRACTOR)
    )
    extracted = extract_claims(chapter_ref(chapter), characters)
    for c in extracted:
        claim = Claim(
            id=uuid.UUID(c.id),
            novel_id=chapter.novel_id,
            chapter_id=chapter.id,
            chapter_version=c.chapter_version,
            subject_character_id=uuid.UUID(c.subject_id),
            subject_text=c.subject_text,
            predicate=c.predicate,
            value=c.value,
            raw_value=c.raw_value,
            modality=c.modality,
            confidence=c.confidence,
            status="proposed",
            extractor=c.extractor,
            effective_day=c.effective_day,
            time_certainty=c.time_certainty,
        )
        claim.evidence = [
            EvidenceSpan(
                id=uuid.uuid5(SPAN_NAMESPACE, f"{c.id}|{s.start}|{s.end}"),
                chapter_id=chapter.id,
                chapter_version=s.chapter_version,
                start=s.start,
                end=s.end,
                quote=s.quote,
            )
            for s in c.spans
        ]
        session.add(claim)
    return len(extracted)


def rebuild_chapter(session: Session, chapter: Chapter) -> None:
    rebuild_passages(session, chapter)
    rebuild_claims(session, chapter)


def rebuild_novel_claims(session: Session, novel_id: uuid.UUID) -> None:
    """Re-run extraction for every chapter, e.g. after a character's names change."""
    session.flush()
    characters = character_refs(session, novel_id)
    for chapter in session.scalars(select(Chapter).where(Chapter.novel_id == novel_id)):
        rebuild_claims(session, chapter, characters)
