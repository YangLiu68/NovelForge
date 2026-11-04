import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from novelforge.api.deps import SessionDep, novel_dep
from novelforge.llm.registry import allowed_llm
from novelforge.models import Novel, StoryAuditRun
from novelforge.services import story_audit

router = APIRouter(prefix="/api", tags=["story"])


class StartIn(BaseModel):
    llm: str | None = Field(None, max_length=120)


@router.post("/novels/{novel_id}/story-audits", status_code=202)
def start(body: StartIn, novel: Novel = Depends(novel_dep), session: Session = SessionDep):
    run = story_audit.start_audit(session, novel, allowed_llm(body.llm))
    session.commit()
    return story_audit.to_out(session, run, with_result=False)


@router.get("/novels/{novel_id}/story-audits")
def list_runs(novel: Novel = Depends(novel_dep), session: Session = SessionDep):
    runs = session.scalars(
        select(StoryAuditRun)
        .where(StoryAuditRun.novel_id == novel.id)
        .order_by(StoryAuditRun.created_at.desc())
        .limit(20)
    )
    return [story_audit.to_out(session, r, with_result=False) for r in runs]


@router.get("/novels/{novel_id}/llm-estimate")
def llm_estimate(
    task: str = "story",
    llm: str | None = None,
    novel: Novel = Depends(novel_dep),
    session: Session = SessionDep,
):
    """A rough cost of running the story audit (`task=story`) or LLM fact extraction
    (`task=extract`) on this novel with the configured model, before starting it."""
    from fastapi import HTTPException

    from novelforge.llm.estimate import estimate
    from novelforge.services.derived import chapter_ref
    from novelforge.services.extraction_jobs import max_words_for

    if task not in ("story", "extract"):
        raise HTTPException(422, "task must be story or extract")
    spec = allowed_llm(llm)
    chapters, _ = story_audit._inputs(session, novel.id)
    return estimate([chapter_ref(c) for c in chapters], spec, task, max_words_for(spec))


@router.get("/story-audits/{run_id}")
def get_run(run_id: uuid.UUID, session: Session = SessionDep):
    return story_audit.to_out(session, story_audit.get_run(session, run_id))
