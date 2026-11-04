"""Story audits as background jobs, stored per run with the chapter versions they read."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from novelforge.config import get_settings
from novelforge.core.domain import ChapterRef
from novelforge.jobs import SkipJob, enqueue, handler
from novelforge.llm.base import LLMError
from novelforge.llm.registry import get_llm
from novelforge.models import Chapter, Character, Novel, StoryAuditRun
from novelforge.narrative.audit import CastMember, StoryAuditor
from novelforge.narrative.prompts import AUDIT_VERSION
from novelforge.services.errors import NotFound


def _inputs(session: Session, novel_id: uuid.UUID) -> tuple[list[Chapter], list[CastMember]]:
    chapters = list(
        session.scalars(
            select(Chapter).where(Chapter.novel_id == novel_id).order_by(Chapter.number)
        )
    )
    cast = [
        CastMember(c.name, tuple(c.aliases or ()), c.description or "")
        for c in session.scalars(
            select(Character).where(Character.novel_id == novel_id).order_by(Character.name)
        )
    ]
    return chapters, cast


def start_audit(session: Session, novel: Novel, llm_spec: str) -> StoryAuditRun:
    """A new run, or the existing one for the same text, model and prompts (unless it failed)."""
    chapters, _ = _inputs(session, novel.id)
    versions = {str(c.id): c.version for c in chapters}
    existing = session.scalar(
        select(StoryAuditRun)
        .where(
            StoryAuditRun.novel_id == novel.id,
            StoryAuditRun.llm == llm_spec,
            StoryAuditRun.prompt_version == AUDIT_VERSION,
            StoryAuditRun.status != "failed",
        )
        .order_by(StoryAuditRun.created_at.desc())
    )
    if existing is not None and existing.chapter_versions == versions:
        return existing
    run = StoryAuditRun(
        novel_id=novel.id,
        llm=llm_spec,
        prompt_version=AUDIT_VERSION,
        chapter_versions=versions,
        status="queued",
        input_tokens=0,
        output_tokens=0,
        cost_usd=0.0,
    )
    session.add(run)
    session.flush()
    if get_settings().story_inline:
        execute(session, run)
    else:
        enqueue(session, "story_audit", f"story:{run.id}", {"run_id": str(run.id)}, max_attempts=2)
    return run


def execute(session: Session, run: StoryAuditRun) -> None:
    chapters, cast = _inputs(session, run.novel_id)
    refs = [ChapterRef(str(c.id), c.number, c.title, c.body, c.version) for c in chapters]
    run.status, run.progress, run.error = "running", None, None
    session.commit()

    def progress(msg: str) -> None:
        run.progress = msg[:200]
        session.commit()

    try:
        audit = StoryAuditor(refs, cast, get_llm(run.llm), progress=progress).run()
    except LLMError as exc:
        run.status, run.error, run.finished_at = "failed", str(exc), datetime.now(UTC)
        session.commit()
        return
    run.chapter_versions = {r.id: r.version for r in refs}
    run.result = audit.to_dict()
    run.input_tokens = audit.usage.get("input_tokens", 0)
    run.output_tokens = audit.usage.get("output_tokens", 0)
    run.cost_usd = audit.usage.get("cost_usd")
    run.status, run.progress, run.finished_at = "done", None, datetime.now(UTC)
    session.commit()


@handler("story_audit")
def story_audit_job(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    run = session.get(StoryAuditRun, uuid.UUID(payload["run_id"]))
    if run is None:
        raise SkipJob("audit run deleted")
    if run.status == "done":
        raise SkipJob("already done")
    execute(session, run)
    return {"status": run.status, "error": run.error}


def stale_chapters(session: Session, run: StoryAuditRun) -> list[str]:
    """Chapters edited or deleted since the audit read them."""
    current = {
        str(c.id): c.version
        for c in session.scalars(select(Chapter).where(Chapter.novel_id == run.novel_id))
    }
    return [cid for cid, v in run.chapter_versions.items() if current.get(cid) != v]


def to_out(session: Session, run: StoryAuditRun, with_result: bool = True) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": str(run.id),
        "novel_id": str(run.novel_id),
        "llm": run.llm,
        "prompt_version": run.prompt_version,
        "status": run.status,
        "progress": run.progress,
        "error": run.error,
        "input_tokens": run.input_tokens,
        "output_tokens": run.output_tokens,
        "cost_usd": run.cost_usd,
        "created_at": run.created_at,
        "finished_at": run.finished_at,
        "stale_chapters": stale_chapters(session, run),
        "chapter_versions": run.chapter_versions,
        "chapter_ids": {},
    }
    if run.result:
        issues = run.result.get("issues", [])
        out["counts"] = {
            "issues": len(issues),
            "severe": sum(1 for i in issues if i["severity"] >= 3),
            "suggestions": len(run.result.get("suggestions", [])),
        }
        numbers = {
            c.number: str(c.id)
            for c in session.scalars(select(Chapter).where(Chapter.novel_id == run.novel_id))
        }
        out["chapter_ids"] = {str(n): cid for n, cid in numbers.items()}
    if with_result:
        out["result"] = run.result
    return out


def get_run(session: Session, run_id: uuid.UUID) -> StoryAuditRun:
    run = session.get(StoryAuditRun, run_id)
    if run is None:
        raise NotFound("Story audit", run_id)
    return run
