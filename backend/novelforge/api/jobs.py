from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from novelforge.api.deps import SessionDep, novel_dep
from novelforge.config import get_settings
from novelforge.jobs import queue_stats
from novelforge.models import Chapter, Job, Novel
from novelforge.retrieval.embedders import canonical
from novelforge.retrieval.index import coverage, enqueue_chapter_embedding

router = APIRouter(prefix="/api", tags=["jobs"])


@router.get("/jobs")
def job_stats(session: Session = SessionDep):
    recent = session.scalars(select(Job).order_by(Job.created_at.desc()).limit(20)).all()
    return {
        "counts": queue_stats(session),
        "recent": [
            {
                "id": str(j.id),
                "kind": j.kind,
                "status": j.status,
                "attempts": j.attempts,
                "error": (j.error or "").split("\n")[0] or None,
                "created_at": j.created_at,
                "finished_at": j.finished_at,
            }
            for j in recent
        ],
    }


@router.get("/novels/{novel_id}/index")
def index_status(novel: Novel = Depends(novel_dep), session: Session = SessionDep):
    settings = get_settings()
    return {
        "embedder": settings.embedder,
        "reranker": settings.reranker,
        "embedder_name": canonical(settings.embedder),
        "coverage": coverage(session, novel.id, canonical(settings.embedder)),
    }


@router.post("/novels/{novel_id}/reindex")
def reindex(novel: Novel = Depends(novel_dep), session: Session = SessionDep):
    """Queue embedding jobs for every chapter (idempotent per chapter version and model)."""
    model = get_settings().embedder
    chapters = session.scalars(select(Chapter).where(Chapter.novel_id == novel.id)).all()
    for chapter in chapters:
        enqueue_chapter_embedding(session, chapter, model)
    session.commit()
    return {"queued_for": len(chapters), "embedder": model}
