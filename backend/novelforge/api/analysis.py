import time

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from novelforge.api.deps import SessionDep, novel_dep
from novelforge.config import get_settings
from novelforge.models import Chapter, Character, Novel
from novelforge.schemas import ClaimOut, ReportOut, SearchOut, SpanOut
from novelforge.services.report import contradiction_report, load_claims
from novelforge.services.search import search_passages

router = APIRouter(prefix="/api/novels/{novel_id}", tags=["analysis"])


@router.get("/search", response_model=SearchOut)
def search(q: str = Query(..., min_length=1, max_length=500),
           limit: int = Query(20, ge=1, le=100),
           novel: Novel = Depends(novel_dep), session: Session = SessionDep):
    hits, took_ms = search_passages(session, novel.id, q, limit)
    return {"query": q, "hits": [h.__dict__ for h in hits], "took_ms": round(took_ms, 2)}


@router.get("/claims", response_model=list[ClaimOut])
def list_claims(novel: Novel = Depends(novel_dep), session: Session = SessionDep):
    chapters = {
        c.id: c for c in session.scalars(select(Chapter).where(Chapter.novel_id == novel.id))
    }
    names = {
        c.id: c.name
        for c in session.scalars(select(Character).where(Character.novel_id == novel.id))
    }
    claims = load_claims(session, novel.id)
    claims.sort(key=lambda c: (chapters[c.chapter_id].number, c.evidence[0].start))
    return [
        ClaimOut(
            id=c.id, subject_character_id=c.subject_character_id,
            subject_name=names.get(c.subject_character_id, c.subject_text),
            predicate=c.predicate, value=c.value, raw_value=c.raw_value, modality=c.modality,
            confidence=c.confidence, status=c.status, extractor=c.extractor,
            effective_day=c.effective_day, time_certainty=c.time_certainty,
            evidence=[
                SpanOut(
                    chapter_id=s.chapter_id, chapter_number=chapters[s.chapter_id].number,
                    chapter_title=chapters[s.chapter_id].title,
                    chapter_version=s.chapter_version, start=s.start, end=s.end, quote=s.quote,
                )
                for s in c.evidence
            ],
        )
        for c in claims
    ]


@router.get("/contradictions", response_model=ReportOut)
def contradictions(min_confidence: float | None = Query(None, ge=0, le=1),
                   novel: Novel = Depends(novel_dep), session: Session = SessionDep):
    threshold = get_settings().report_min_confidence if min_confidence is None else min_confidence
    started = time.perf_counter()
    findings, claim_count = contradiction_report(session, novel.id, threshold)
    return {
        "novel_id": novel.id,
        "min_confidence": threshold,
        "claims_considered": claim_count,
        "findings": [
            {**f.__dict__, "evidence": [e.__dict__ for e in f.evidence]} for f in findings
        ],
        "took_ms": round((time.perf_counter() - started) * 1000, 2),
    }
