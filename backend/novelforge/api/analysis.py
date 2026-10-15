import time
import uuid
from typing import cast

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from novelforge.api.deps import SessionDep, novel_dep
from novelforge.config import get_settings
from novelforge.core.contradictions import SEVERITY_ORDER
from novelforge.models import Chapter, Character, Novel, StoredFinding
from novelforge.retrieval.embedders import get_embedder
from novelforge.retrieval.index import coverage
from novelforge.retrieval.rerankers import get_reranker
from novelforge.retrieval.search import Mode
from novelforge.retrieval.search import search as retrieval_search
from novelforge.schemas import ClaimOut, ReportOut, SearchOut, SpanOut
from novelforge.services.errors import NotFound
from novelforge.services.findings import fingerprint, refresh_findings, set_status, travel_matrix
from novelforge.services.report import contradiction_report, load_claims

router = APIRouter(prefix="/api/novels/{novel_id}", tags=["analysis"])
findings_router = APIRouter(prefix="/api/findings", tags=["findings"])


@router.get("/search", response_model=SearchOut)
def search(
    q: str = Query(..., min_length=1, max_length=500),
    mode: str = Query("keyword", pattern="^(keyword|fts|vector|hybrid|hybrid_rerank)$"),
    limit: int = Query(20, ge=1, le=100),
    novel: Novel = Depends(novel_dep),
    session: Session = SessionDep,
):
    settings = get_settings()
    embedder = (
        get_embedder(settings.embedder) if mode in ("vector", "hybrid", "hybrid_rerank") else None
    )
    reranker = get_reranker(settings.reranker) if mode == "hybrid_rerank" else None
    result = retrieval_search(session, novel.id, q, cast(Mode, mode), limit, embedder, reranker)
    return {
        "query": q,
        "mode": mode,
        "embedder": embedder.name if embedder else None,
        "reranker": reranker.name if reranker else None,
        "hits": [h.__dict__ for h in result.hits],
        "took_ms": result.timings_ms["total"],
        "timings_ms": result.timings_ms,
        "index_coverage": coverage(session, novel.id, embedder.name) if embedder else None,
    }


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
            id=c.id,
            subject_character_id=c.subject_character_id,
            subject_name=names.get(c.subject_character_id, c.subject_text),
            predicate=c.predicate,
            value=c.value,
            raw_value=c.raw_value,
            modality=c.modality,
            confidence=c.confidence,
            status=c.status,
            extractor=c.extractor,
            effective_day=c.effective_day,
            time_certainty=c.time_certainty,
            evidence=[
                SpanOut(
                    chapter_id=s.chapter_id,
                    chapter_number=chapters[s.chapter_id].number,
                    chapter_title=chapters[s.chapter_id].title,
                    chapter_version=s.chapter_version,
                    start=s.start,
                    end=s.end,
                    quote=s.quote,
                )
                for s in c.evidence
            ],
        )
        for c in claims
    ]


@router.get("/contradictions", response_model=ReportOut)
def contradictions(
    status: str = Query("open", pattern="^(open|dismissed|resolved|all)$"),
    include_uncertain: bool = Query(
        False, description="Preview: also let hedged statements and dialogue create findings."
    ),
    min_confidence: float | None = Query(None, ge=0, le=1),
    novel: Novel = Depends(novel_dep),
    session: Session = SessionDep,
):
    started = time.perf_counter()
    default_threshold = get_settings().report_min_confidence
    # A non-default threshold is a what-if view: stored findings always use the default, so one
    # caller cannot resolve (or reopen) everyone's findings by changing a parameter.
    preview = include_uncertain or (
        min_confidence is not None and min_confidence != default_threshold
    )
    if preview:
        # A what-if preview: computed on the fly, never stored.
        threshold = (
            (0.3 if include_uncertain else default_threshold)
            if min_confidence is None
            else min_confidence
        )
        modalities = (
            frozenset({"asserted", "hedged", "reported"})
            if include_uncertain
            else frozenset({"asserted"})
        )
        findings, claim_count = contradiction_report(
            session,
            novel.id,
            threshold,
            modalities,
            travel=travel_matrix(session, novel.id),
        )
        items = [
            {
                **f.__dict__,
                "id": fingerprint(f),
                "status": "preview",
                "detector": "rules",
                "evidence": [e.__dict__ for e in f.evidence],
            }
            for f in findings
        ]
        counts = {"preview": len(items)}
    else:
        threshold = (
            get_settings().report_min_confidence if min_confidence is None else min_confidence
        )
        stats = refresh_findings(session, novel.id, threshold)
        session.commit()
        claim_count = stats["claims_considered"]
        query = select(StoredFinding).where(StoredFinding.novel_id == novel.id)
        if status != "all":
            query = query.where(StoredFinding.status == status)
        rows = session.scalars(query).all()
        rows.sort(
            key=lambda r: (
                SEVERITY_ORDER.get(r.severity, 3),
                min((e["chapter_number"] for e in r.evidence), default=0),
                r.subject_name,
                r.predicate,
            )
        )
        items = [
            {
                "id": str(r.id),
                "kind": r.kind,
                "category": r.category,
                "subject_id": str(r.subject_character_id) if r.subject_character_id else "",
                "subject_name": r.subject_name,
                "predicate": r.predicate,
                "severity": r.severity,
                "explanation": r.explanation,
                "suggestion": r.suggestion,
                "canon_value": r.canon_value,
                "evidence": r.evidence,
                "status": r.status,
                "status_note": r.status_note,
                "detector": r.detector,
                "auto_resolved": r.auto_resolved,
            }
            for r in rows
        ]
        counts = dict(
            session.execute(
                select(StoredFinding.status, func.count())
                .where(StoredFinding.novel_id == novel.id)
                .group_by(StoredFinding.status)
            ).all()
        )
    return {
        "novel_id": novel.id,
        "min_confidence": threshold,
        "claims_considered": claim_count,
        "status_counts": counts,
        "findings": items,
        "took_ms": round((time.perf_counter() - started) * 1000, 2),
    }


class StatusIn(BaseModel):
    note: str | None = Field(None, max_length=2000)


def _finding(session: Session, finding_id: uuid.UUID) -> StoredFinding:
    row = session.get(StoredFinding, finding_id)
    if row is None:
        raise NotFound("Finding", finding_id)
    return row


@findings_router.post("/{finding_id}/dismiss")
def dismiss(finding_id: uuid.UUID, payload: StatusIn, session: Session = SessionDep):
    row = _finding(session, finding_id)
    set_status(session, row, "dismissed", payload.note)
    session.commit()
    return {"id": str(row.id), "status": row.status}


@findings_router.post("/{finding_id}/resolve")
def resolve(finding_id: uuid.UUID, payload: StatusIn, session: Session = SessionDep):
    row = _finding(session, finding_id)
    set_status(session, row, "resolved", payload.note)
    session.commit()
    return {"id": str(row.id), "status": row.status}


@findings_router.post("/{finding_id}/reopen")
def reopen(finding_id: uuid.UUID, session: Session = SessionDep):
    row = _finding(session, finding_id)
    set_status(session, row, "open", None)
    session.commit()
    return {"id": str(row.id), "status": row.status}
