"""Regression tests for issues found in the M6 code review."""

import threading
import uuid

from sqlalchemy import func, select

from novelforge.core.domain import ChapterRef, CharacterRef
from novelforge.core.evaluation import evaluate
from novelforge.db import get_sessionmaker
from novelforge.extraction.runner import extract_with_llm
from novelforge.extraction.verify import locate
from novelforge.llm.mock import MockLLM
from novelforge.models import Claim, WorldRule
from novelforge.services import review


def _chapters(client, nid):
    return client.get(f"/api/novels/{nid}/chapters").json()


def _edit(client, chapter_id, append):
    full = client.get(f"/api/chapters/{chapter_id}").json()
    r = client.patch(
        f"/api/chapters/{chapter_id}",
        json={"version": full["version"], "body": full["body"] + append},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_llm_claims_of_an_old_version_disappear_after_an_edit(
    client, sample_novel_id, run_jobs, session
):
    client.post(f"/api/novels/{sample_novel_id}/extract", params={"llm": "mock"})
    run_jobs()
    ch2 = _chapters(client, sample_novel_id)[1]
    before = session.scalar(
        select(func.count())
        .select_from(Claim)
        .where(Claim.chapter_id == uuid.UUID(ch2["id"]), Claim.extractor == "llm:mock")
    )
    assert before > 0
    _edit(client, ch2["id"], "\n\nThe end.")
    session.expire_all()
    after = session.scalar(
        select(func.count())
        .select_from(Claim)
        .where(Claim.chapter_id == uuid.UUID(ch2["id"]), Claim.extractor == "llm:mock")
    )
    assert after == 0  # LLM extraction on save is off, so nothing describes the new text yet


def test_one_quote_two_subjects_keeps_both():
    mara, tomas = CharacterRef("m", "Mara Venn"), CharacterRef("t", "Tomas Hale")
    body = "Mara and Tomas drowned in the flood."
    llm = MockLLM()
    fact = {
        "kind": "death",
        "value": "",
        "object": "",
        "quote": body,
        "modality": "asserted",
        "confidence": 0.9,
        "day_offset": 0,
    }
    llm.queue_json({"facts": [{**fact, "subject": "Mara Venn"}, {**fact, "subject": "Tomas Hale"}]})
    run = extract_with_llm(ChapterRef("c", 1, "t", body, 1, 5), [mara, tomas], llm)
    assert sorted(c.subject_id for c in run.claims) == ["m", "t"]
    assert len({c.id for c in run.claims}) == 2


def test_edited_value_is_remembered_after_reextraction(client, sample_novel_id):
    items = client.get(f"/api/novels/{sample_novel_id}/review", params={"limit": 200}).json()[
        "items"
    ]
    hollin = next(c for c in items if c["predicate"] == "birthplace" and c["value"] == "Hollin")
    # The reviewer decides the text should say Varrow (matching canon) and edits the value.
    r = client.post(f"/api/claims/{hollin['id']}/accept", json={"value": "Varrow"})
    assert r.status_code == 200
    ch2 = _chapters(client, sample_novel_id)[1]
    _edit(client, ch2["id"], "\n\nA gull cried.")
    accepted = client.get(
        f"/api/novels/{sample_novel_id}/review", params={"status": "accepted"}
    ).json()["items"]
    again = next(c for c in accepted if c["predicate"] == "birthplace")
    assert again["value"] == "Varrow" and again["id"] != hollin["id"]


def test_decisions_are_scoped_to_their_chapter(client):
    novel = client.post("/api/novels", json={"title": "Scoped"}).json()
    client.post(f"/api/novels/{novel['id']}/characters", json={"name": "Mara Venn"})
    a = client.post(
        f"/api/novels/{novel['id']}/chapters",
        json={"title": "A", "body": "Mara was in Harrowgate."},
    ).json()
    b = client.post(
        f"/api/novels/{novel['id']}/chapters",
        json={"title": "B", "body": "Mara was in Harrowgate."},
    ).json()
    items = client.get(f"/api/novels/{novel['id']}/review").json()["items"]
    in_a = next(c for c in items if c["evidence"][0]["chapter_id"] == a["id"])
    client.post(f"/api/claims/{in_a['id']}/reject", json={})
    _edit(client, b["id"], "\n\nRain.")  # chapter B is re-extracted
    proposed = client.get(f"/api/novels/{novel['id']}/review").json()["items"]
    assert [c["evidence"][0]["chapter_id"] for c in proposed] == [b["id"]]


def test_concurrent_report_refreshes_do_not_fail(client, sample_novel_id):
    results = []

    def call():
        results.append(client.get(f"/api/novels/{sample_novel_id}/contradictions").status_code)

    threads = [threading.Thread(target=call) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == [200] * 4
    assert client.get(f"/api/novels/{sample_novel_id}/contradictions").json()["status_counts"] == {
        "open": 4
    }


def test_custom_threshold_is_a_preview_and_resolves_nothing(client, sample_novel_id):
    client.get(f"/api/novels/{sample_novel_id}/contradictions")
    data = client.get(
        f"/api/novels/{sample_novel_id}/contradictions", params={"min_confidence": 1.0}
    ).json()
    assert data["status_counts"] == {"preview": 0}
    assert client.get(f"/api/novels/{sample_novel_id}/contradictions").json()["status_counts"] == {
        "open": 4
    }


def test_double_accept_creates_canon_once(sample_novel_id, session):
    nid = uuid.UUID(sample_novel_id)
    source = session.scalar(select(Claim).where(Claim.predicate == "eye_color").limit(1))
    rule = Claim(
        id=uuid.uuid4(),
        novel_id=nid,
        chapter_id=source.chapter_id,
        chapter_version=1,
        subject_character_id=None,
        subject_text="world",
        predicate="world_rule",
        value="Iron cannot be enchanted.",
        raw_value="",
        modality="asserted",
        confidence=0.9,
        status="proposed",
        extractor="llm:test",
        effective_day=0,
        time_certainty="chapter_day",
        details={},
        fingerprint="fp-rule",
    )
    session.add(rule)
    session.commit()
    maker = get_sessionmaker()
    barrier = threading.Barrier(2)

    def accept():
        with maker() as s:
            barrier.wait()
            claim = s.get(Claim, rule.id, with_for_update=True)
            review.accept(s, claim)
            s.commit()

    threads = [threading.Thread(target=accept) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert session.scalar(select(func.count()).select_from(WorldRule)) == 1


def test_failed_jobs_can_be_requeued(session):
    from novelforge.jobs import enqueue
    from novelforge.models import Job

    enqueue(session, "noop", "k-failed", {"a": 1})
    session.commit()
    session.execute(Job.__table__.update().values(status="failed", attempts=3, error="boom"))
    session.commit()
    enqueue(session, "noop", "k-failed", {"a": 2})
    session.commit()
    session.expire_all()
    job = session.scalar(select(Job))
    assert (job.status, job.attempts, job.error, job.payload) == ("queued", 0, None, {"a": 2})


def test_workflow_step_refuses_to_start_twice_and_recovers(client, sample_novel_id):
    from novelforge.drafting import engine
    from novelforge.services.errors import Conflict

    maker = get_sessionmaker()
    with maker() as s:
        run = engine.create_run(
            s, s.get(engine.Novel, uuid.UUID(sample_novel_id)), "g", None, "mock", 2
        )
        engine.begin_step(s, run, "plan")
        s.commit()
        rid = run.id
    with maker() as s:
        try:
            engine.begin_step(s, engine.lock_run(s, rid), "plan")
            raise AssertionError("second step started")
        except Conflict:
            s.rollback()
    # Simulated restart: the step row is "running" but nothing executes it.
    assert engine.recover_interrupted(maker) >= 1
    data = client.get(f"/api/workflows/{rid}").json()
    assert data["status"] == "plan_failed" and "restarted" in data["error"]
    assert data["steps"][0]["status"] == "failed"


def test_finalisation_errors_fail_the_step_and_end_the_stream(client, sample_novel_id, monkeypatch):
    from novelforge.drafting import engine
    from novelforge.llm.registry import get_llm

    get_llm("mock").text_queue.clear()
    get_llm("mock").chunk_delay = 0
    run = client.post(
        f"/api/novels/{sample_novel_id}/workflows", json={"goal": "Break the critic"}
    ).json()

    def broken(*a, **k):
        raise RuntimeError("critic crashed")

    monkeypatch.setattr(engine, "critique", broken)
    r = client.post(f"/api/workflows/{run['id']}/approve-plan", json={}).json()
    assert r["status"] == "draft_failed" and "critic crashed" in r["error"]
    assert engine.STREAMS[uuid.UUID(run["id"])].finished


def test_age_window_catches_non_adjacent_conflicts():
    from novelforge.core.contradictions import detect_contradictions
    from novelforge.core.extraction import extract_claims

    m = CharacterRef("m", "Mara Venn")
    texts, days = (
        ["Mara was thirty.", "Mara was thirty-one.", "Mara was thirty-two."],
        [0, 200, 300],
    )
    chs = [
        ChapterRef(f"c{i}", i, "x", t, 1, d)
        for i, (t, d) in enumerate(zip(texts, days, strict=True), 1)
    ]
    claims = [c for ch in chs for c in extract_claims(ch, [m])]
    [f] = detect_contradictions(claims, chs, [m])
    assert [e.value for e in f.evidence] == ["30", "32"] and "30 or 31" in f.explanation


def test_evaluation_matches_each_label_once():
    gt = {
        "contradictions": [
            {
                "id": "A",
                "category": "timeline",
                "subject": "K",
                "evidence": [
                    {"chapter": 1, "start": 0, "end": 5},
                    {"chapter": 2, "start": 0, "end": 5},
                ],
            },
            {
                "id": "B",
                "category": "timeline",
                "subject": "K",
                "evidence": [
                    {"chapter": 1, "start": 0, "end": 5},
                    {"chapter": 3, "start": 0, "end": 5},
                ],
            },
        ],
        "negatives": [],
    }

    def f(ch):
        return {
            "kind": "dead_character_active",
            "category": "timeline",
            "subject_name": "K",
            "predicate": "status",
            "evidence": [
                {"chapter_number": 1, "start": 0, "end": 5},
                {"chapter_number": ch, "start": 0, "end": 5},
            ],
        }

    r = evaluate([f(3), f(2)], gt, {1: "x", 2: "x", 3: "x"})
    assert r.true_positives == 2 and r.duplicates == 0


def test_null_in_patch_is_a_422(client):
    novel = client.post("/api/novels", json={"title": "N"}).json()
    ch = client.post(f"/api/novels/{novel['id']}/chapters", json={"title": "C"}).json()
    assert (
        client.patch(f"/api/chapters/{ch['id']}", json={"version": 1, "body": None}).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/chapters/{ch['id']}", json={"version": 1, "story_day": None}
        ).status_code
        == 200
    )
    c = client.post(f"/api/novels/{novel['id']}/characters", json={"name": "A"}).json()
    assert (
        client.patch(f"/api/characters/{c['id']}", json={"version": 1, "aliases": None}).status_code
        == 422
    )


def test_birthplace_compares_case_insensitively():
    from novelforge.core.contradictions import detect_contradictions
    from novelforge.core.extraction import extract_claims

    t = CharacterRef("t", "Tomas Hale", (), {"birthplace": "harrowgate"})
    ch = ChapterRef("c", 1, "x", "Tomas was born in Harrowgate.", 1, 0)
    assert detect_contradictions(extract_claims(ch, [t]), [ch], [t]) == []


def test_locate_keeps_offsets_with_length_changing_lowercase():
    body = "İstanbul was far. Mara's eyes were grey."
    found = locate(body, "mara's EYES were grey")
    assert found and body[found.start : found.end] == "Mara's eyes were grey"
