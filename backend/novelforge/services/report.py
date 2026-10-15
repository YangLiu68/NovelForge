"""Load claims from the database and run the (pure) contradiction checks over them."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from novelforge.core.contradictions import Finding, detect_contradictions
from novelforge.core.domain import ExtractedClaim, Span
from novelforge.models import Chapter, Claim
from novelforge.services.derived import chapter_ref, character_refs


def load_claims(session: Session, novel_id: uuid.UUID) -> list[Claim]:
    return list(
        session.scalars(
            select(Claim)
            .where(Claim.novel_id == novel_id, Claim.status != "rejected")
            .options(selectinload(Claim.evidence))
            .order_by(Claim.chapter_id, Claim.predicate)
        )
    )


def to_extracted(claim: Claim) -> ExtractedClaim:
    return ExtractedClaim(
        id=str(claim.id),
        chapter_id=str(claim.chapter_id),
        chapter_version=claim.chapter_version,
        subject_id=str(claim.subject_character_id) if claim.subject_character_id else "",
        subject_text=claim.subject_text,
        predicate=claim.predicate,
        value=claim.value,
        raw_value=claim.raw_value,
        modality=claim.modality,
        confidence=claim.confidence,
        effective_day=claim.effective_day,
        time_certainty=claim.time_certainty,
        extractor=claim.extractor,
        spans=tuple(
            Span(str(s.chapter_id), s.chapter_version, s.start, s.end, s.quote)
            for s in claim.evidence
        ),
        details=dict(claim.details or {}),
    )


def contradiction_report(
    session: Session,
    novel_id: uuid.UUID,
    min_confidence: float,
    modalities: frozenset[str] = frozenset({"asserted"}),
    travel: dict[tuple[str, str], int] | None = None,
) -> tuple[list[Finding], int]:
    chapters = [
        chapter_ref(c) for c in session.scalars(select(Chapter).where(Chapter.novel_id == novel_id))
    ]
    claims = [to_extracted(c) for c in load_claims(session, novel_id)]
    findings = detect_contradictions(
        claims,
        chapters,
        character_refs(session, novel_id),
        min_confidence=min_confidence,
        modalities=modalities,
        travel=travel,
    )
    return findings, len(claims)
