"""A small PostgreSQL-backed job queue.

- Enqueue is idempotent: every job has a unique `key`; enqueueing an existing key is a no-op.
- Workers claim jobs with `SELECT ... FOR UPDATE SKIP LOCKED`, so several workers (threads or
  processes) never run the same job twice.
- Failures retry with exponential backoff up to `max_attempts`, then stay `failed` with the error.
- Jobs left `running` by a crashed worker are re-queued after `stale_after` seconds.
- Enqueueing inside the caller's transaction means a job exists if and only if the change that
  needs it was committed.
"""

from __future__ import annotations

import logging
import threading
import time
import traceback
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from novelforge.models import Job

log = logging.getLogger("novelforge.jobs")

Handler = Callable[[Session, dict[str, Any]], dict[str, Any] | None]
HANDLERS: dict[str, Handler] = {}


class SkipJob(Exception):  # noqa: N818 - control flow, not an error
    """Raised by a handler when the job no longer applies (e.g. the chapter changed again)."""


def load_handlers() -> None:
    """Import the modules that register job handlers."""
    import novelforge.retrieval.index  # noqa: F401
    import novelforge.services.extraction_jobs  # noqa: F401
    import novelforge.services.rule_judge  # noqa: F401


def handler(kind: str) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        HANDLERS[kind] = fn
        return fn

    return register


def enqueue(
    session: Session, kind: str, key: str, payload: dict[str, Any], max_attempts: int = 3
) -> None:
    session.execute(
        insert(Job)
        .values(
            kind=kind,
            key=key,
            payload=payload,
            status="queued",
            attempts=0,
            max_attempts=max_attempts,
        )
        # Same key again is a no-op, except that a job which already failed for good is
        # re-armed: asking again (e.g. /extract after a provider outage) must be able to retry.
        .on_conflict_do_update(
            index_elements=["key"],
            set_={
                "status": "queued",
                "attempts": 0,
                "error": None,
                "run_after": func.now(),
                "payload": payload,
            },
            where=Job.status == "failed",
        )
    )


_CLAIM = text(
    """
    UPDATE job SET status = 'running', attempts = attempts + 1, started_at = now()
    WHERE id = (
        SELECT id FROM job
        WHERE status = 'queued' AND run_after <= now()
        ORDER BY created_at
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    RETURNING id
    """
)


def requeue_stale(session: Session, stale_after: float = 600) -> int:
    cutoff = datetime.now(UTC) - timedelta(seconds=stale_after)
    result = session.execute(
        update(Job)
        .where(Job.status == "running", Job.started_at < cutoff)
        .values(status="queued", error="requeued after worker timeout")
    )
    session.commit()
    return result.rowcount


def run_one(maker: sessionmaker[Session]) -> bool:
    """Claim and run one job. Returns False when the queue is empty."""
    with maker() as session:
        job_id = session.execute(_CLAIM).scalar()
        session.commit()
        if job_id is None:
            return False
        job = session.get(Job, job_id)
        assert job is not None
        started = time.perf_counter()
        fn = HANDLERS.get(job.kind)
        try:
            if fn is None:
                raise RuntimeError(f"no handler for job kind '{job.kind}'")
            result = fn(session, dict(job.payload)) or {}
            session.flush()
            job.status, job.result, job.error = "done", result, None
        except SkipJob as exc:
            session.rollback()
            job = session.get(Job, job_id)
            job.status, job.error = "skipped", str(exc)
        except Exception as exc:  # noqa: BLE001 - a job must never kill the worker
            session.rollback()
            job = session.get(Job, job_id)
            job.error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=5)}"
            if job.attempts >= job.max_attempts:
                job.status = "failed"
            else:
                job.status = "queued"
                job.run_after = datetime.now(UTC) + timedelta(seconds=2**job.attempts)
        job.finished_at = datetime.now(UTC)
        session.commit()
        log.info(
            '{"job": "%s", "kind": "%s", "status": "%s", "attempt": %d, "ms": %.1f}',
            job.id,
            job.kind,
            job.status,
            job.attempts,
            (time.perf_counter() - started) * 1000,
        )
        return True


def run_pending(maker: sessionmaker[Session], limit: int | None = None) -> int:
    """Run queued jobs until none are ready (or `limit` is reached). Returns jobs run."""
    count = 0
    while (limit is None or count < limit) and run_one(maker):
        count += 1
    return count


def queue_stats(session: Session) -> dict[str, int]:
    rows = session.execute(select(Job.status, func.count()).group_by(Job.status)).all()
    return {status: n for status, n in rows}


class Worker:
    """Background thread that drains the queue; used inside the API process."""

    def __init__(self, maker: sessionmaker[Session], poll_seconds: float = 0.5):
        self.maker, self.poll = maker, poll_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="novelforge-worker", daemon=True)

    def start(self) -> None:
        with self.maker() as session:
            requeue_stale(session)
        self._thread.start()

    def stop(self, timeout: float = 5) -> None:
        self._stop.set()
        self._thread.join(timeout)

    def _loop(self) -> None:
        last_reap = time.monotonic()
        while not self._stop.is_set():
            if time.monotonic() - last_reap > 60:
                # Periodically, not only at start: a job whose worker died (process crash,
                # restart within the lease window) is re-queued once its lease expires.
                last_reap = time.monotonic()
                try:
                    with self.maker() as session:
                        requeue_stale(session)
                except Exception:  # noqa: BLE001
                    log.exception("requeue_stale failed")
            try:
                ran = run_one(self.maker)
            except Exception:  # noqa: BLE001 - keep polling after DB hiccups
                log.exception("worker loop error")
                ran = False
            if not ran:
                self._stop.wait(self.poll)
