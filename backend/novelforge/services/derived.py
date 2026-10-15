"""Data derived from chapter text: search passages and extracted claims.

Both are rebuilt in the same transaction as the edit that changed their inputs, keyed by
chapter id, chapter version and extractor, so running a rebuild twice gives identical rows.
"""

import hashlib
import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from novelforge.config import get_settings
from novelforge.core.domain import ChapterRef, CharacterRef, ExtractedClaim
from novelforge.core.extraction import extract_claims
from novelforge.core.text import content_hash, split_passages, split_scenes
from novelforge.models import (
    Chapter,
    Character,
    Claim,
    EvidenceSpan,
    Passage,
    ReviewDecision,
    Scene,
)
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


def claim_fingerprint(chapter_id: str, subject: str, predicate: str, value: str, quote: str) -> str:
    """Identity of a statement independent of its offsets: survives edits elsewhere in the
    chapter. Scoped to the chapter, so the same sentence in another chapter is its own fact."""
    norm_quote = " ".join(quote.lower().split())
    key = f"{chapter_id}|{subject}|{predicate}|{value.lower()}|{norm_quote}"
    return hashlib.sha1(key.encode()).hexdigest()


def persist_claims(
    session: Session, chapter: Chapter, extracted: list[ExtractedClaim], replace_like: str
) -> dict[str, int]:
    """Replace this chapter's claims from one extractor family and re-apply past decisions.

    `replace_like` is an extractor name ("llm:mock") or a LIKE prefix pattern ("rules-%").
    """
    same_extractor = (
        Claim.extractor.like(replace_like)
        if replace_like.endswith("%")
        else Claim.extractor == replace_like
    )
    session.execute(delete(Claim).where(Claim.chapter_id == chapter.id, same_extractor))
    fingerprints = {
        c.id: claim_fingerprint(
            str(chapter.id), c.subject_id or c.subject_text, c.predicate, c.value, c.spans[0].quote
        )
        for c in extracted
    }
    decisions = (
        {
            d.fingerprint: d
            for d in session.scalars(
                select(ReviewDecision).where(
                    ReviewDecision.novel_id == chapter.novel_id,
                    ReviewDecision.fingerprint.in_(list(fingerprints.values())),
                )
            )
        }
        if fingerprints
        else {}
    )
    reapplied = 0
    for c in extracted:
        decision = decisions.get(fingerprints[c.id])
        claim = Claim(
            id=uuid.UUID(c.id),
            novel_id=chapter.novel_id,
            chapter_id=chapter.id,
            chapter_version=c.chapter_version,
            subject_character_id=uuid.UUID(c.subject_id) if c.subject_id else None,
            subject_text=c.subject_text,
            predicate=c.predicate,
            value=(decision.value if decision and decision.value else c.value),
            raw_value=c.raw_value,
            modality=c.modality,
            confidence=c.confidence,
            status=decision.decision if decision else "proposed",
            reviewed_at=decision.decided_at if decision else None,
            review_note=decision.note if decision else None,
            extractor=c.extractor,
            effective_day=c.effective_day,
            time_certainty=c.time_certainty,
            details=dict(c.details),
            fingerprint=fingerprints[c.id],
        )
        reapplied += decision is not None
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
    return {"claims": len(extracted), "decisions_reapplied": reapplied}


def rebuild_claims(
    session: Session, chapter: Chapter, characters: list[CharacterRef] | None = None
) -> int:
    if characters is None:
        characters = character_refs(session, chapter.novel_id)
    # Replace every rule-based claim for this chapter, including ones from older rule versions.
    extracted = extract_claims(chapter_ref(chapter), characters)
    persist_claims(session, chapter, extracted, "rules-%")
    return len(extracted)


def rebuild_scenes(session: Session, chapter: Chapter) -> None:
    session.execute(delete(Scene).where(Scene.chapter_id == chapter.id))
    for i, span in enumerate(split_scenes(chapter.body)):
        session.add(
            Scene(
                id=uuid.uuid5(PASSAGE_NAMESPACE, f"scene|{chapter.id}|{chapter.version}|{i}"),
                novel_id=chapter.novel_id,
                chapter_id=chapter.id,
                ordinal=i,
                start=span.start,
                end=span.end,
            )
        )


def rebuild_chapter(session: Session, chapter: Chapter) -> None:
    # Claims from any extractor that point at an older version of this chapter describe text
    # that may no longer exist; drop them (the LLM job re-extracts the new version if enabled).
    session.execute(
        delete(Claim).where(
            Claim.chapter_id == chapter.id, Claim.chapter_version != chapter.version
        )
    )
    rebuild_passages(session, chapter)
    rebuild_scenes(session, chapter)
    rebuild_claims(session, chapter)
    settings = get_settings()
    if settings.llm_extraction:
        from novelforge.services.extraction_jobs import enqueue_llm_extraction

        enqueue_llm_extraction(session, chapter, settings.llm)


def rebuild_novel_claims(session: Session, novel_id: uuid.UUID) -> None:
    """Re-run extraction for every chapter, e.g. after a character's names change."""
    session.flush()
    characters = character_refs(session, novel_id)
    for chapter in session.scalars(select(Chapter).where(Chapter.novel_id == novel_id)):
        rebuild_claims(session, chapter, characters)
