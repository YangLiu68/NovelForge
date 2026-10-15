import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from novelforge.api.deps import SessionDep, novel_dep
from novelforge.config import get_settings
from novelforge.jobs import queue_stats
from novelforge.llm.registry import allowed_llm
from novelforge.models import (
    CanonChange,
    Chapter,
    Character,
    Claim,
    Location,
    Novel,
    PlotThread,
    Relationship,
    TimelineEvent,
    WorldRule,
)
from novelforge.services import review
from novelforge.services.errors import NotFound
from novelforge.services.extraction_jobs import enqueue_llm_extraction

router = APIRouter(prefix="/api", tags=["review"])

FAMILIES = {
    "attributes": ["eye_color", "hair_color", "handedness", "birthplace", "age"],
    "presence": ["location", "status"],
    "abilities": ["ability:%"],
    "world": ["world_rule", "foreshadowing", "event", "causal", "relationship"],
}


class AcceptIn(BaseModel):
    replace_canon: bool = False
    value: str | None = Field(None, max_length=500)
    note: str | None = Field(None, max_length=2000)


class RejectIn(BaseModel):
    note: str | None = Field(None, max_length=2000)


class BatchIn(BaseModel):
    claim_ids: list[uuid.UUID] = Field(..., max_length=500)


def _claim_out(session: Session, c: Claim, chapters: dict, names: dict) -> dict:
    ch = chapters.get(c.chapter_id)
    return {
        "id": str(c.id),
        "subject_character_id": str(c.subject_character_id) if c.subject_character_id else None,
        "subject_name": names.get(c.subject_character_id, c.subject_text),
        "predicate": c.predicate,
        "value": c.value,
        "modality": c.modality,
        "confidence": c.confidence,
        "status": c.status,
        "extractor": c.extractor,
        "effective_day": c.effective_day,
        "time_certainty": c.time_certainty,
        "details": c.details or {},
        "review_note": c.review_note,
        "canon_value": review.canon_value(session, c),
        "evidence": [
            {
                "chapter_id": str(s.chapter_id),
                "chapter_number": ch.number if ch else None,
                "chapter_title": ch.title if ch else None,
                "chapter_version": s.chapter_version,
                "start": s.start,
                "end": s.end,
                "quote": s.quote,
            }
            for s in c.evidence
        ],
    }


@router.get("/novels/{novel_id}/review")
def review_queue(
    status: str = Query("proposed", pattern="^(proposed|accepted|rejected)$"),
    family: str | None = Query(None, pattern="^(attributes|presence|abilities|world)$"),
    extractor: str | None = Query(None, max_length=64),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    novel: Novel = Depends(novel_dep),
    session: Session = SessionDep,
):
    query = select(Claim).where(Claim.novel_id == novel.id, Claim.status == status)
    if family:
        conds = [
            Claim.predicate.like(p) if p.endswith("%") else Claim.predicate == p
            for p in FAMILIES[family]
        ]
        from sqlalchemy import or_

        query = query.where(or_(*conds))
    if extractor:
        query = query.where(Claim.extractor == extractor)
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    chapters = {
        c.id: c for c in session.scalars(select(Chapter).where(Chapter.novel_id == novel.id))
    }
    names = {
        c.id: c.name
        for c in session.scalars(select(Character).where(Character.novel_id == novel.id))
    }
    rows = session.scalars(
        query.options(selectinload(Claim.evidence))
        .join(Chapter, Chapter.id == Claim.chapter_id)
        .order_by(Chapter.number, Claim.predicate, Claim.id)
        .limit(limit)
        .offset(offset)
    ).all()
    counts = dict(
        session.execute(
            select(Claim.status, func.count())
            .where(Claim.novel_id == novel.id)
            .group_by(Claim.status)
        ).all()
    )
    return {
        "total": total,
        "counts": counts,
        "items": [_claim_out(session, c, chapters, names) for c in rows],
    }


def _get_claim(session: Session, claim_id: uuid.UUID) -> Claim:
    # Row lock: a double-submitted accept waits, then sees "accepted" and does nothing.
    claim = session.get(Claim, claim_id, with_for_update=True)
    if claim is None:
        raise NotFound("Claim", claim_id)
    return claim


@router.post("/claims/{claim_id}/accept")
def accept_claim(claim_id: uuid.UUID, payload: AcceptIn, session: Session = SessionDep):
    claim = _get_claim(session, claim_id)
    result = review.accept(session, claim, payload.replace_canon, payload.value, payload.note)
    session.commit()
    return result


@router.post("/claims/{claim_id}/reject")
def reject_claim(claim_id: uuid.UUID, payload: RejectIn, session: Session = SessionDep):
    claim = _get_claim(session, claim_id)
    result = review.reject(session, claim, payload.note)
    session.commit()
    return result


@router.post("/novels/{novel_id}/review/accept-batch")
def accept_batch(
    payload: BatchIn, novel: Novel = Depends(novel_dep), session: Session = SessionDep
):
    """Accept several claims; ones that would overwrite canon are skipped and reported."""
    results = {"accepted": [], "skipped": []}
    for claim_id in payload.claim_ids:
        claim = session.get(Claim, claim_id)
        if claim is None or claim.novel_id != novel.id:
            results["skipped"].append({"id": str(claim_id), "reason": "not found"})
            continue
        try:
            with session.begin_nested():
                review.accept(session, claim)
            results["accepted"].append(str(claim_id))
        except review.Conflict as exc:
            results["skipped"].append({"id": str(claim_id), "reason": str(exc)})
    session.commit()
    return results


@router.get("/novels/{novel_id}/canon")
def canon(novel: Novel = Depends(novel_dep), session: Session = SessionDep):
    nid = novel.id
    names = {
        c.id: c.name for c in session.scalars(select(Character).where(Character.novel_id == nid))
    }
    chapters = {
        c.id: c.number for c in session.scalars(select(Chapter).where(Chapter.novel_id == nid))
    }
    return {
        "characters": [
            {"id": str(c.id), "name": c.name, "attributes": c.attributes}
            for c in session.scalars(
                select(Character).where(Character.novel_id == nid).order_by(Character.name)
            )
        ],
        "locations": [
            {"id": str(loc.id), "name": loc.name, "travel_days": loc.travel_days}
            for loc in session.scalars(
                select(Location).where(Location.novel_id == nid).order_by(Location.name)
            )
        ],
        "world_rules": [
            {
                "id": str(r.id),
                "statement": r.statement,
                "status": r.status,
                "chapter_number": chapters.get(r.source_chapter_id),
            }
            for r in session.scalars(select(WorldRule).where(WorldRule.novel_id == nid))
        ],
        "timeline": [
            {
                "id": str(e.id),
                "kind": e.kind,
                "description": e.description,
                "character": names.get(e.subject_character_id),
                "location": e.location,
                "story_day": e.story_day,
                "chapter_number": chapters.get(e.chapter_id),
            }
            for e in session.scalars(
                select(TimelineEvent)
                .where(TimelineEvent.novel_id == nid)
                .order_by(TimelineEvent.story_day.nulls_last(), TimelineEvent.created_at)
            )
        ],
        "plot_threads": [
            {
                "id": str(t.id),
                "title": t.title,
                "status": t.status,
                "setup_chapter": chapters.get(t.setup_chapter_id),
                "payoff_chapter": chapters.get(t.payoff_chapter_id),
            }
            for t in session.scalars(select(PlotThread).where(PlotThread.novel_id == nid))
        ],
        "relationships": [
            {
                "id": str(r.id),
                "source": names.get(r.source_character_id),
                "target": names.get(r.target_character_id),
                "kind": r.kind,
            }
            for r in session.scalars(select(Relationship).where(Relationship.novel_id == nid))
        ],
    }


@router.get("/novels/{novel_id}/canon/changes")
def canon_changes(
    limit: int = Query(100, ge=1, le=1000),
    novel: Novel = Depends(novel_dep),
    session: Session = SessionDep,
):
    rows = session.scalars(
        select(CanonChange)
        .where(CanonChange.novel_id == novel.id)
        .order_by(CanonChange.created_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": str(r.id),
            "entity_type": r.entity_type,
            "field": r.field,
            "old_value": r.old_value,
            "new_value": r.new_value,
            "source_claim_id": str(r.source_claim_id) if r.source_claim_id else None,
            "actor": r.actor,
            "note": r.note,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.post("/novels/{novel_id}/extract")
def extract(
    llm: str | None = Query(None, max_length=120),
    novel: Novel = Depends(novel_dep),
    session: Session = SessionDep,
):
    """Queue LLM extraction for every chapter (idempotent per chapter version, model, prompt)."""
    spec = allowed_llm(llm)
    chapters = session.scalars(select(Chapter).where(Chapter.novel_id == novel.id)).all()
    for chapter in chapters:
        enqueue_llm_extraction(session, chapter, spec)
    session.commit()
    return {"queued_for": len(chapters), "llm": spec, "queue": queue_stats(session)}


@router.post("/novels/{novel_id}/judge-rules")
def judge_rules(
    llm: str | None = Query(None, max_length=120),
    novel: Novel = Depends(novel_dep),
    session: Session = SessionDep,
):
    """Queue the LLM world-rule judge (idempotent for unchanged chapters and rules)."""
    from novelforge.services.rule_judge import collect_rules, enqueue_judge

    spec = allowed_llm(llm)
    key = enqueue_judge(session, novel, spec)
    session.commit()
    return {"queued": key, "rules": len(collect_rules(session, novel.id)), "llm": spec}


@router.get("/novels/{novel_id}/graph")
def graph(novel: Novel = Depends(novel_dep), session: Session = SessionDep):
    from novelforge.services.graph import character_graph

    return character_graph(session, novel.id)


@router.get("/novels/{novel_id}/timeline")
def timeline(novel: Novel = Depends(novel_dep), session: Session = SessionDep):
    from novelforge.services.findings import refresh_findings
    from novelforge.services.graph import timeline as build_timeline

    refresh_findings(session, novel.id, get_settings().report_min_confidence)
    session.commit()
    return build_timeline(session, novel.id)


@router.get("/llm")
def llm_config():
    s = get_settings()
    return {"llm": s.llm, "llm_extraction_on_save": s.llm_extraction, "effort": s.llm_effort}
