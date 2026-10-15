import json
import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from novelforge.api.deps import SessionDep, novel_dep
from novelforge.config import get_settings
from novelforge.db import get_sessionmaker
from novelforge.drafting import engine
from novelforge.llm.registry import allowed_llm
from novelforge.models import Chapter, Novel, WorkflowRun, WorkflowStep
from novelforge.services.errors import NotFound

router = APIRouter(prefix="/api", tags=["workflows"])


class StartIn(BaseModel):
    goal: str = Field(..., min_length=3, max_length=4000)
    chapter_id: uuid.UUID | None = None
    llm: str | None = Field(None, max_length=120)
    max_iterations: int = Field(2, ge=1, le=engine.HARD_MAX_ITERATIONS)


class PlanIn(BaseModel):
    plan: str | None = Field(None, max_length=20_000)


class DecideIn(BaseModel):
    action: str = Field(..., pattern="^(apply|revise|discard)$")
    force: bool = False


def _out(session: Session, run: WorkflowRun, with_steps: bool = False) -> dict:
    data = {
        "id": str(run.id),
        "novel_id": str(run.novel_id),
        "chapter_id": str(run.chapter_id) if run.chapter_id else None,
        "base_version": run.base_version,
        "goal": run.goal,
        "llm": run.llm,
        "status": run.status,
        "iteration": run.iteration,
        "max_iterations": run.max_iterations,
        "plan": run.plan,
        "draft": run.draft,
        "critique": run.critique,
        "applied_chapter_id": str(run.applied_chapter_id) if run.applied_chapter_id else None,
        "applied_version": run.applied_version,
        "input_tokens": run.input_tokens,
        "output_tokens": run.output_tokens,
        "cost_usd": run.cost_usd,
        "error": run.error,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
    }
    if with_steps:
        data["steps"] = [
            {
                "id": str(s.id),
                "kind": s.kind,
                "iteration": s.iteration,
                "attempt": s.attempt,
                "status": s.status,
                "chars": len(s.output or ""),
                "output_tokens": s.output_tokens,
                "error": s.error,
                "started_at": s.started_at,
                "finished_at": s.finished_at,
            }
            for s in session.scalars(
                select(WorkflowStep)
                .where(WorkflowStep.run_id == run.id)
                .order_by(WorkflowStep.started_at)
            )
        ]
    return data


def _run(session: Session, run_id: uuid.UUID) -> WorkflowRun:
    run = session.get(WorkflowRun, run_id)
    if run is None:
        raise NotFound("Workflow", run_id)
    return run


def _background() -> bool:
    return not get_settings().workflow_inline


@router.post("/novels/{novel_id}/workflows", status_code=201)
def start(payload: StartIn, novel: Novel = Depends(novel_dep), session: Session = SessionDep):
    chapter = session.get(Chapter, payload.chapter_id) if payload.chapter_id else None
    if payload.chapter_id and chapter is None:
        raise NotFound("Chapter", payload.chapter_id)
    run = engine.create_run(
        session,
        novel,
        payload.goal,
        chapter,
        allowed_llm(payload.llm),
        payload.max_iterations,
    )
    session.commit()
    engine.start_step(get_sessionmaker(), run.id, "plan", background=_background())
    session.expire_all()
    return _out(session, _run(session, run.id))


@router.get("/novels/{novel_id}/workflows")
def list_runs(novel: Novel = Depends(novel_dep), session: Session = SessionDep):
    runs = session.scalars(
        select(WorkflowRun)
        .where(WorkflowRun.novel_id == novel.id)
        .order_by(WorkflowRun.created_at.desc())
        .limit(50)
    ).all()
    return [_out(session, r) for r in runs]


@router.get("/workflows/{run_id}")
def get_run(run_id: uuid.UUID, session: Session = SessionDep):
    return _out(session, _run(session, run_id), with_steps=True)


@router.get("/workflows/{run_id}/stream")
def stream(
    run_id: uuid.UUID, start: int = Query(0, ge=0, alias="from"), session: Session = SessionDep
):
    """Server-sent events for the running step; a snapshot when nothing is running."""
    run = _run(session, run_id)
    live = engine.STREAMS.get(run_id)
    snapshot = {
        "type": "snapshot",
        "status": run.status,
        "plan": run.plan,
        "draft": run.draft,
        "critique": run.critique,
    }
    # Release the pooled connection now: the stream can stay open for minutes.
    session.close()

    def events():
        if live is None:
            yield f"data: {json.dumps(snapshot, default=str)}\n\n"
            return
        for ev in live.follow(start):
            yield f"data: {json.dumps(ev, default=str)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/workflows/{run_id}/approve-plan")
def approve_plan(run_id: uuid.UUID, payload: PlanIn, session: Session = SessionDep):
    run = _run(session, run_id)
    engine.approve_plan(session, run, payload.plan)
    session.commit()
    engine.start_step(get_sessionmaker(), run.id, "draft", background=_background())
    session.expire_all()
    return _out(session, _run(session, run_id))


@router.post("/workflows/{run_id}/decide")
def decide(run_id: uuid.UUID, payload: DecideIn, session: Session = SessionDep):
    run = _run(session, run_id)
    result = engine.decide(session, run, payload.action, payload.force)
    session.commit()
    if payload.action == "revise":
        engine.start_step(get_sessionmaker(), run.id, "revise", background=_background())
    session.expire_all()
    return {**result, "run": _out(session, _run(session, run_id))}


@router.post("/workflows/{run_id}/cancel")
def cancel(run_id: uuid.UUID, session: Session = SessionDep):
    _run(session, run_id)
    return {"cancelled": engine.cancel(run_id)}


@router.post("/workflows/{run_id}/retry")
def retry(run_id: uuid.UUID, session: Session = SessionDep):
    run = _run(session, run_id)
    kind = engine.retry_kind(run)
    engine.start_step(get_sessionmaker(), run.id, kind, background=_background())
    session.expire_all()
    return _out(session, _run(session, run_id))
