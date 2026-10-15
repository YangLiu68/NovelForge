import threading
import uuid

from sqlalchemy import func, select

from novelforge.db import get_sessionmaker
from novelforge.jobs import (
    HANDLERS,
    SkipJob,
    enqueue,
    load_handlers,
    queue_stats,
    requeue_stale,
    run_pending,
)
from novelforge.models import Chapter, Job, Passage
from novelforge.services import workspace


def test_enqueue_is_idempotent(session):
    enqueue(session, "noop", "k1", {})
    enqueue(session, "noop", "k1", {"different": True})
    session.commit()
    assert session.scalar(select(func.count()).select_from(Job)) == 1


def test_handler_success_skip_retry_and_fail(session):
    calls = {"ok": 0, "flaky": 0}

    def ok(_s, payload):
        calls["ok"] += 1
        return {"echo": payload["x"]}

    def skip(_s, _p):
        raise SkipJob("not needed")

    def flaky(_s, _p):
        calls["flaky"] += 1
        raise RuntimeError("boom")

    HANDLERS.update({"t_ok": ok, "t_skip": skip, "t_flaky": flaky})
    try:
        enqueue(session, "t_ok", "a", {"x": 1})
        enqueue(session, "t_skip", "b", {})
        enqueue(session, "t_flaky", "c", {}, max_attempts=2)
        session.commit()
        maker = get_sessionmaker()
        run_pending(maker)
        jobs = {j.key: j for j in session.scalars(select(Job)).all()}
        session.expire_all()
        jobs = {j.key: j for j in session.scalars(select(Job)).all()}
        assert jobs["a"].status == "done" and jobs["a"].result == {"echo": 1}
        assert jobs["b"].status == "skipped" and "not needed" in jobs["b"].error
        # First failure is re-queued with backoff (run_after in the future).
        assert jobs["c"].status == "queued" and jobs["c"].attempts == 1
        assert "RuntimeError: boom" in jobs["c"].error
        session.execute(Job.__table__.update().values(run_after=func.now()))
        session.commit()
        run_pending(maker)
        session.expire_all()
        failed = session.scalar(select(Job).where(Job.key == "c"))
        assert failed.status == "failed" and failed.attempts == 2 and calls["flaky"] == 2
        assert queue_stats(session) == {"done": 1, "skipped": 1, "failed": 1}
    finally:
        for k in ("t_ok", "t_skip", "t_flaky"):
            HANDLERS.pop(k, None)


def test_concurrent_workers_run_each_job_once(session):
    seen: list[str] = []
    lock = threading.Lock()

    def record(_s, payload):
        with lock:
            seen.append(payload["i"])

    HANDLERS["t_record"] = record
    try:
        for i in range(40):
            enqueue(session, "t_record", f"r{i}", {"i": str(i)})
        session.commit()
        maker = get_sessionmaker()
        threads = [threading.Thread(target=run_pending, args=(maker,)) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert sorted(seen, key=int) == [str(i) for i in range(40)]
    finally:
        HANDLERS.pop("t_record", None)


def test_stale_running_jobs_are_requeued(session):
    enqueue(session, "noop", "stuck", {})
    session.commit()
    session.execute(
        Job.__table__.update().values(
            status="running", started_at=func.now() - func.make_interval(0, 0, 0, 0, 1)
        )
    )
    session.commit()
    assert requeue_stale(session, stale_after=60) == 1
    session.expire_all()
    assert session.scalar(select(Job.status)) == "queued"


def test_chapter_save_queues_embedding_and_uses_cache(session, run_jobs):
    load_handlers()
    novel = workspace.create_novel(session, "N")
    chapter = workspace.create_chapter(session, novel, "One", "First para.\n\nSecond para.")
    session.commit()
    assert run_jobs() == 1
    session.expire_all()
    passages = session.scalars(select(Passage).where(Passage.chapter_id == chapter.id)).all()
    assert all(p.embedding is not None and p.embedding_model == "hash:384" for p in passages)
    first = session.scalar(select(Job).where(Job.kind == "embed_chapter"))
    assert first.result["embedded"] == 2 and first.result["cache_hits"] == 0

    chapter = session.get(Chapter, chapter.id)
    workspace.update_chapter(session, chapter, chapter.version, {"body": "First para.\n\nNew."})
    session.commit()
    run_jobs()
    second = session.scalar(
        select(Job).where(Job.kind == "embed_chapter", Job.payload["version"].as_integer() == 2)
    )
    assert second.status == "done"
    assert second.result["cache_hits"] == 1 and second.result["embedded"] == 1


def test_embedding_job_for_an_old_version_is_skipped(session, run_jobs):
    novel = workspace.create_novel(session, "N")
    chapter = workspace.create_chapter(session, novel, "One", "Text.")
    workspace.update_chapter(session, chapter, 1, {"body": "Newer text."})
    session.commit()
    run_jobs()
    statuses = {
        j.payload["version"]: j.status
        for j in session.scalars(select(Job).where(Job.kind == "embed_chapter"))
    }
    assert statuses == {1: "skipped", 2: "done"}
    assert uuid.UUID(str(chapter.id))
