"""The drafting workflow state machine.

planning ──▶ awaiting_plan_approval ──(approve plan)──▶ drafting ──▶ critiquing
    ▲                                                                   │
    │                                   ┌───────────────────────────────┘
    │                                   ▼
    │                          awaiting_decision ──(apply)──▶ applied
    │                            │      ▲        └─(discard)─▶ discarded
    │                     (revise, while iteration < max_iterations)
    │                            ▼      │
    │                          revising ┘
Any LLM step can be cancelled (status "<kind>_cancelled") or fail ("<kind>_failed"); retry
starts a new attempt of the same step. Steps stream through an in-process StepStream that the
SSE endpoint follows; partial output is also persisted, so a reconnecting client (or another
process) can show what was generated so far.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from novelforge.drafting.context import build_context
from novelforge.drafting.critic import critique, issues_for_prompt
from novelforge.drafting.prompts import DRAFT_SYSTEM, PLAN_SYSTEM, REVISE_SYSTEM
from novelforge.llm.base import LLMError
from novelforge.llm.registry import get_llm
from novelforge.models import Chapter, Novel, WorkflowRun, WorkflowStep
from novelforge.services import workspace
from novelforge.services.errors import Conflict, NotFound

HARD_MAX_ITERATIONS = 3
STEP_STATUS = {"plan": "planning", "draft": "drafting", "revise": "revising"}


class StepStream:
    """Events of the step currently running for one workflow run (in-process)."""

    def __init__(self, step_id: uuid.UUID, kind: str):
        self.step_id, self.kind = step_id, kind
        self.events: list[dict[str, Any]] = []
        self.cond = threading.Condition()
        self.cancel = threading.Event()
        self.finished = False

    def push(self, event: dict[str, Any]) -> None:
        with self.cond:
            event["seq"] = len(self.events)
            self.events.append(event)
            self.cond.notify_all()

    def finish(self, event: dict[str, Any]) -> None:
        self.push(event)
        with self.cond:
            self.finished = True
            self.cond.notify_all()

    def follow(self, start: int = 0, timeout: float = 15.0) -> Iterator[dict[str, Any]]:
        """Replay from `start`, then yield new events until the step finishes.

        Yields {"type": "ping"} after `timeout` seconds without events (keeps proxies happy).
        """
        i = start
        while True:
            with self.cond:
                if i >= len(self.events) and not self.finished:
                    self.cond.wait(timeout)
                batch = self.events[i:]
                done = self.finished
            if not batch and not done:
                yield {"type": "ping"}
            yield from batch
            i += len(batch)
            if done and i >= len(self.events):
                return


STREAMS: dict[uuid.UUID, StepStream] = {}
_STREAMS_LOCK = threading.Lock()


def _now() -> datetime:
    return datetime.now(UTC)


def _get(session: Session, run_id: uuid.UUID) -> WorkflowRun:
    run = session.get(WorkflowRun, run_id)
    if run is None:
        raise NotFound("Workflow", run_id)
    return run


def _require(run: WorkflowRun, *statuses: str) -> None:
    if run.status not in statuses:
        raise Conflict(f"Workflow is '{run.status}'; this needs {' or '.join(statuses)}.")


def create_run(
    session: Session,
    novel: Novel,
    goal: str,
    chapter: Chapter | None,
    llm: str,
    max_iterations: int,
) -> WorkflowRun:
    if not 1 <= max_iterations <= HARD_MAX_ITERATIONS:
        raise Conflict(f"max_iterations must be between 1 and {HARD_MAX_ITERATIONS}.")
    if chapter is not None and chapter.novel_id != novel.id:
        raise Conflict("That chapter belongs to another novel.")
    run = WorkflowRun(
        novel_id=novel.id,
        chapter_id=chapter.id if chapter else None,
        base_version=chapter.version if chapter else None,
        goal=goal.strip(),
        llm=llm,
        status="created",
        iteration=0,
        max_iterations=max_iterations,
    )
    session.add(run)
    session.flush()
    return run


def _prompt(session: Session, run: WorkflowRun, kind: str) -> tuple[str, str]:
    context = build_context(session, run)
    if kind == "plan":
        return PLAN_SYSTEM, context
    if kind == "draft":
        return DRAFT_SYSTEM, f"{context}\n\nAPPROVED PLAN:\n{run.plan}"
    issues = issues_for_prompt(run.critique or {})
    return REVISE_SYSTEM, f"{context}\n\nDRAFT:\n{run.draft}\n\nISSUES:\n{issues}"


RUNNING_STATUSES = frozenset({*STEP_STATUS.values(), "critiquing"})


@dataclass
class StepTicket:
    run_id: uuid.UUID
    step_id: uuid.UUID
    kind: str
    attempt: int
    system: str
    prompt: str
    llm: str


def lock_run(session: Session, run_id: uuid.UUID) -> WorkflowRun:
    """Load the run with a row lock; every state transition happens under it."""
    run = session.get(WorkflowRun, run_id, with_for_update=True)
    if run is None:
        raise NotFound("Workflow", run_id)
    return run


def begin_step(session: Session, run: WorkflowRun, kind: str) -> StepTicket:
    """Within the caller's transaction (run locked): create the step and mark the run busy.

    Two requests racing to start a step serialise on the row lock; the second sees a busy run
    and is refused, so a run never has two steps writing to it.
    """
    if run.status in RUNNING_STATUSES:
        raise Conflict(f"A {run.status} step is already running for this workflow.")
    attempt = (
        session.scalar(
            select(func.max(WorkflowStep.attempt)).where(
                WorkflowStep.run_id == run.id,
                WorkflowStep.kind == kind,
                WorkflowStep.iteration == run.iteration,
            )
        )
        or 0
    ) + 1
    step = WorkflowStep(run_id=run.id, kind=kind, iteration=run.iteration, attempt=attempt)
    session.add(step)
    run.status = STEP_STATUS[kind]
    run.error = None
    system, prompt = _prompt(session, run, kind)
    session.flush()
    return StepTicket(run.id, step.id, kind, attempt, system, prompt, run.llm)


def launch(maker: sessionmaker[Session], ticket: StepTicket, background: bool = True) -> None:
    """After the transaction that began the step has committed: stream it."""
    stream = StepStream(ticket.step_id, ticket.kind)
    with _STREAMS_LOCK:
        STREAMS[ticket.run_id] = stream
    stream.push(
        {
            "type": "status",
            "status": STEP_STATUS[ticket.kind],
            "step": ticket.kind,
            "attempt": ticket.attempt,
        }
    )
    if background:
        threading.Thread(
            target=_execute,
            args=(maker, ticket, stream),
            daemon=True,
            name=f"workflow-{ticket.kind}",
        ).start()
    else:
        _execute(maker, ticket, stream)


def start_step(
    maker: sessionmaker[Session], run_id: uuid.UUID, kind: str, background: bool = True
) -> uuid.UUID:
    """Lock, begin, commit, launch: for callers with no other change to make in the same step."""
    with maker() as session:
        ticket = begin_step(session, lock_run(session, run_id), kind)
        session.commit()
    launch(maker, ticket, background)
    return ticket.step_id


def _execute(maker, ticket: StepTicket, stream: StepStream) -> None:
    parts: list[str] = []
    result = None
    cancelled = False
    error: str | None = None
    final: dict[str, Any] = {
        "type": "done",
        "status": f"{ticket.kind}_failed",
        "step": ticket.kind,
        "error": "internal error",
        "critique": None,
    }
    try:
        try:
            llm = get_llm(ticket.llm)
            stream_iter = llm.stream_text(ticket.system, ticket.prompt, cancel=stream.cancel)
            for i, chunk in enumerate(stream_iter):
                if chunk.text:
                    parts.append(chunk.text)
                    stream.push({"type": "token", "text": chunk.text})
                    if i % 40 == 0:
                        _save_partial(maker, ticket.step_id, "".join(parts))
                if chunk.done:
                    result, cancelled = chunk.result, chunk.cancelled
        except LLMError as exc:
            error = str(exc)
        except Exception as exc:  # noqa: BLE001 - surfaced to the user as a failed step
            error = f"{type(exc).__name__}: {exc}"
        final = _finalize(maker, ticket, "".join(parts).strip(), result, cancelled, error)
    except Exception as exc:  # noqa: BLE001 - finalisation itself failed (DB, critic, ...)
        final["error"] = f"{type(exc).__name__}: {exc}"
        _mark_failed(maker, ticket, final["error"])
    finally:
        # Always end the stream, so live SSE clients never wait forever.
        stream.finish(final)


def _finalize(
    maker, ticket: StepTicket, text: str, result, cancelled: bool, error: str | None
) -> dict[str, Any]:
    kind = ticket.kind
    with maker() as session:
        run = lock_run(session, ticket.run_id)
        step = session.get(WorkflowStep, ticket.step_id)
        step.output = text
        step.finished_at = _now()
        if result is not None:
            step.input_tokens, step.output_tokens = result.input_tokens, result.output_tokens
            step.cost_usd = result.cost_usd
            run.input_tokens += result.input_tokens
            run.output_tokens += result.output_tokens
            if run.cost_usd is not None:
                run.cost_usd = None if result.cost_usd is None else run.cost_usd + result.cost_usd
        if error is not None or (not text and not cancelled):
            step.status, step.error = "failed", error or "the model returned no text"
            run.status, run.error = f"{kind}_failed", step.error
        elif cancelled:
            step.status = "cancelled"
            run.status = f"{kind}_cancelled"
        else:
            step.status = "done"
            if kind == "plan":
                run.plan = text
                run.status = "awaiting_plan_approval"
            else:
                run.draft = text
                run.status = "critiquing"
                session.flush()
                run.critique = critique(session, run, text)
                run.status = "awaiting_decision"
        session.commit()
        return {
            "type": "done",
            "status": run.status,
            "step": kind,
            "error": run.error,
            "critique": run.critique if kind != "plan" else None,
        }


def _mark_failed(maker, ticket: StepTicket, message: str) -> None:
    try:
        with maker() as session:
            run = lock_run(session, ticket.run_id)
            step = session.get(WorkflowStep, ticket.step_id)
            if step is not None and step.status == "running":
                step.status, step.error, step.finished_at = "failed", message, _now()
            if run.status in RUNNING_STATUSES:
                run.status, run.error = f"{ticket.kind}_failed", message
            session.commit()
    except Exception:  # noqa: BLE001 - nothing more we can do; recover_interrupted cleans up
        pass


def recover_interrupted(maker: sessionmaker[Session]) -> int:
    """At startup: runs left mid-step by a previous process become retryable failures.

    Steps run inside the API process, so after a restart nothing is executing them. (Assumes
    one API process per database, which is how NovelForge is deployed.)
    """
    kind_of = {v: k for k, v in STEP_STATUS.items()} | {"critiquing": "draft"}
    with maker() as session:
        runs = session.scalars(
            select(WorkflowRun).where(WorkflowRun.status.in_(RUNNING_STATUSES)).with_for_update()
        ).all()
        for run in runs:
            run.status = f"{kind_of[run.status]}_failed"
            run.error = "Interrupted: the server restarted during this step. Retry it."
        for step in session.scalars(select(WorkflowStep).where(WorkflowStep.status == "running")):
            step.status, step.error, step.finished_at = "failed", "interrupted", _now()
        session.commit()
        return len(runs)


def _save_partial(maker, step_id: uuid.UUID, text: str) -> None:
    with maker() as session:
        step = session.get(WorkflowStep, step_id)
        if step is not None and step.status == "running":
            step.output = text
            session.commit()


def approve_plan(session: Session, run: WorkflowRun, plan: str | None) -> None:
    _require(run, "awaiting_plan_approval")
    if plan is not None and plan.strip():
        run.plan = plan.strip()
    run.iteration = 1


def decide(session: Session, run: WorkflowRun, action: str, force: bool = False) -> dict:
    _require(run, "awaiting_decision")
    if action == "discard":
        run.status, run.decided_at = "discarded", _now()
        return {"status": run.status}
    if action == "revise":
        if run.iteration >= run.max_iterations:
            raise Conflict(
                f"This run allows {run.max_iterations} draft(s); no revisions left. "
                f"Apply, discard, or start a new run."
            )
        run.iteration += 1
        return {"status": "revising"}
    if action != "apply":
        raise Conflict(f"unknown action {action!r}")
    if run.chapter_id is None:
        novel = session.get(Novel, run.novel_id)
        title = run.goal.split("\n")[0][:80] or "New chapter"
        chapter = workspace.create_chapter(session, novel, title, run.draft or "")
    else:
        chapter = session.get(Chapter, run.chapter_id)
        if chapter is None:
            raise Conflict("The target chapter was deleted.")
        version = chapter.version if force else run.base_version
        try:
            workspace.update_chapter(session, chapter, version, {"body": run.draft or ""})
        except Conflict as exc:
            raise Conflict(
                f"The chapter changed since this run started (now version {chapter.version}, run "
                f"based on {run.base_version}). Review it, then apply with force to save the "
                f"draft as a new version; the current text stays in the revision history.",
                current_version=chapter.version,
            ) from exc
    run.applied_chapter_id, run.applied_version = chapter.id, chapter.version
    run.status, run.decided_at = "applied", _now()
    return {"status": run.status, "chapter_id": str(chapter.id), "version": chapter.version}


def cancel(run_id: uuid.UUID) -> bool:
    stream = STREAMS.get(run_id)
    if stream is None or stream.finished:
        return False
    stream.cancel.set()
    return True


def retry_kind(run: WorkflowRun) -> str:
    for suffix in ("_cancelled", "_failed"):
        if run.status.endswith(suffix):
            return run.status[: -len(suffix)]
    raise Conflict(f"Nothing to retry: workflow is '{run.status}'.")
