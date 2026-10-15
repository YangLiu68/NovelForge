import json
import time
import uuid

import pytest

from novelforge.db import get_sessionmaker
from novelforge.drafting import engine
from novelforge.llm.base import LLMError
from novelforge.llm.registry import get_llm

PLAN = "1. Mara reaches the archive.\n2. She finds the drowned ledger.\nContinuity: grey eyes."
CLEAN_DRAFT = "The archive door gave at last. Mara's eyes were grey in the lamplight, and she read."
BAD_DRAFT = "The archive door gave at last. Mara's eyes were blue, and Tomas was born in Hollin."


@pytest.fixture
def mock_llm():
    llm = get_llm("mock")
    llm.text_queue.clear()
    llm.chunk_delay = 0
    yield llm
    llm.text_queue.clear()
    llm.chunk_delay = 0


def chapter(client, nid, number):
    return next(
        c for c in client.get(f"/api/novels/{nid}/chapters").json() if c["number"] == number
    )


def start(client, nid, **body):
    r = client.post(
        f"/api/novels/{nid}/workflows", json={"goal": "Mara searches the archive", **body}
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_plan_approve_draft_apply(client, sample_novel_id, mock_llm):
    ch3 = chapter(client, sample_novel_id, 3)
    mock_llm.queue_text(PLAN, CLEAN_DRAFT)
    run = start(client, sample_novel_id, chapter_id=ch3["id"])
    assert run["status"] == "awaiting_plan_approval" and run["plan"] == PLAN
    assert run["base_version"] == ch3["version"]
    # Nothing has touched the manuscript yet.
    assert client.get(f"/api/chapters/{ch3['id']}").json()["version"] == ch3["version"]

    edited = PLAN + "\n3. Added beat."
    r = client.post(f"/api/workflows/{run['id']}/approve-plan", json={"plan": edited}).json()
    assert r["status"] == "awaiting_decision" and r["plan"] == edited
    assert r["draft"] == CLEAN_DRAFT and r["critique"]["issues"] == []
    assert r["critique"]["draft_facts"] >= 1

    r = client.post(f"/api/workflows/{run['id']}/decide", json={"action": "apply"}).json()
    assert r["status"] == "applied" and r["version"] == ch3["version"] + 1
    body = client.get(f"/api/chapters/{ch3['id']}").json()["body"]
    assert body == CLEAN_DRAFT
    revs = client.get(f"/api/chapters/{ch3['id']}/revisions").json()
    assert [rv["version"] for rv in revs][:2] == [ch3["version"] + 1, ch3["version"]]
    steps = client.get(f"/api/workflows/{run['id']}").json()["steps"]
    assert [(s["kind"], s["status"]) for s in steps] == [("plan", "done"), ("draft", "done")]


def test_critic_cites_contradictions_and_revision_is_bounded(client, sample_novel_id, mock_llm):
    ch3 = chapter(client, sample_novel_id, 3)
    mock_llm.queue_text(PLAN, BAD_DRAFT, CLEAN_DRAFT)
    run = start(client, sample_novel_id, chapter_id=ch3["id"], max_iterations=2)
    r = client.post(f"/api/workflows/{run['id']}/approve-plan", json={}).json()
    issues = r["critique"]["issues"]
    kinds = {(i["kind"], i["subject"]) for i in issues}
    assert ("attribute_conflict", "Mara Venn") in kinds  # grey in chapter 1 vs blue in draft
    assert ("canon_conflict", "Tomas Hale") in kinds  # sheet says Varrow
    eye = next(i for i in issues if i["subject"] == "Mara Venn")
    assert eye["draft_evidence"][0]["quote"] == "Mara's eyes were blue"
    assert BAD_DRAFT[eye["draft_evidence"][0]["start"] : eye["draft_evidence"][0]["end"]] == (
        "Mara's eyes were blue"
    )
    assert eye["established_evidence"][0]["chapter_number"] == 1

    r = client.post(f"/api/workflows/{run['id']}/decide", json={"action": "revise"}).json()
    assert r["run"]["iteration"] == 2 and r["run"]["critique"]["issues"] == []
    # The revise prompt carried the issues with their evidence.
    assert "Mara's eyes were blue" in mock_llm.calls[-1]["prompt"]
    r = client.post(f"/api/workflows/{run['id']}/decide", json={"action": "revise"})
    assert r.status_code == 409 and "no revisions left" in r.json()["detail"]


def test_iteration_cap_is_enforced(client, sample_novel_id):
    r = client.post(
        f"/api/novels/{sample_novel_id}/workflows", json={"goal": "x" * 10, "max_iterations": 9}
    )
    assert r.status_code == 422


def test_apply_refuses_to_overwrite_newer_edits_unless_forced(client, sample_novel_id, mock_llm):
    ch2 = chapter(client, sample_novel_id, 2)
    mock_llm.queue_text(PLAN, CLEAN_DRAFT)
    run = start(client, sample_novel_id, chapter_id=ch2["id"])
    client.post(f"/api/workflows/{run['id']}/approve-plan", json={})
    full = client.get(f"/api/chapters/{ch2['id']}").json()
    client.patch(
        f"/api/chapters/{ch2['id']}",
        json={"version": full["version"], "body": full["body"] + "\n\nAuthor edit."},
    )
    r = client.post(f"/api/workflows/{run['id']}/decide", json={"action": "apply"})
    assert r.status_code == 409 and "changed since this run started" in r.json()["detail"]
    r = client.post(f"/api/workflows/{run['id']}/decide", json={"action": "apply", "force": True})
    assert r.status_code == 200
    revs = client.get(f"/api/chapters/{ch2['id']}/revisions").json()
    old = client.get(f"/api/chapters/{ch2['id']}/revisions/{revs[1]['version']}").json()
    assert old["body"].endswith("Author edit.")  # the author's edit is kept in history


def test_new_chapter_run_creates_a_chapter(client, sample_novel_id, mock_llm):
    mock_llm.queue_text(PLAN, CLEAN_DRAFT)
    run = start(client, sample_novel_id, goal="Chapter four: the archive")
    client.post(f"/api/workflows/{run['id']}/approve-plan", json={})
    r = client.post(f"/api/workflows/{run['id']}/decide", json={"action": "apply"}).json()
    new = client.get(f"/api/chapters/{r['chapter_id']}").json()
    assert new["number"] == 4 and new["title"] == "Chapter four: the archive"


def test_discard_leaves_manuscript_untouched(client, sample_novel_id, mock_llm):
    ch1 = chapter(client, sample_novel_id, 1)
    mock_llm.queue_text(PLAN, BAD_DRAFT)
    run = start(client, sample_novel_id, chapter_id=ch1["id"])
    client.post(f"/api/workflows/{run['id']}/approve-plan", json={})
    r = client.post(f"/api/workflows/{run['id']}/decide", json={"action": "discard"}).json()
    assert r["status"] == "discarded"
    assert client.get(f"/api/chapters/{ch1['id']}").json()["version"] == ch1["version"]
    assert (
        client.post(f"/api/workflows/{run['id']}/decide", json={"action": "apply"}).status_code
        == 409
    )


def test_cancel_mid_stream_then_retry(client, sample_novel_id, mock_llm):
    maker = get_sessionmaker()
    with maker() as s:
        novel = s.get(engine.Novel, uuid.UUID(sample_novel_id))
        new_id = engine.create_run(s, novel, "Cancel me", None, "mock", 2).id
        s.commit()
    mock_llm.chunk_delay = 0.02
    mock_llm.queue_text(" ".join(f"w{i}" for i in range(2000)))
    engine.start_step(maker, new_id, "plan", background=True)
    stream = engine.STREAMS[new_id]
    deadline = time.time() + 5
    while not any(e["type"] == "token" for e in stream.events) and time.time() < deadline:
        time.sleep(0.01)
    assert engine.cancel(new_id) is True
    with stream.cond:
        stream.cond.wait_for(lambda: stream.finished, timeout=5)
    data = client.get(f"/api/workflows/{new_id}").json()
    assert data["status"] == "plan_cancelled"
    cancelled = data["steps"][0]
    assert cancelled["status"] == "cancelled" and cancelled["chars"] > 0
    assert data["plan"] is None  # partial output is never treated as an approved artifact

    mock_llm.chunk_delay = 0
    mock_llm.queue_text(PLAN)
    data = client.post(f"/api/workflows/{new_id}/retry").json()
    assert data["status"] == "awaiting_plan_approval" and data["plan"] == PLAN
    steps = client.get(f"/api/workflows/{new_id}").json()["steps"]
    assert [(s["attempt"], s["status"]) for s in steps] == [(1, "cancelled"), (2, "done")]
    assert client.post(f"/api/workflows/{new_id}/retry").status_code == 409


def test_sse_stream_replays_tokens_and_done(client, sample_novel_id, mock_llm):
    maker = get_sessionmaker()
    with maker() as s:
        novel = s.get(engine.Novel, uuid.UUID(sample_novel_id))
        run = engine.create_run(s, novel, "Stream me", None, "mock", 2)
        s.commit()
        rid = run.id
    mock_llm.queue_text("alpha beta gamma delta epsilon zeta eta theta")
    engine.start_step(maker, rid, "plan", background=False)
    with client.stream("GET", f"/api/workflows/{rid}/stream") as r:
        events = [json.loads(line[6:]) for line in r.iter_lines() if line.startswith("data: ")]
    types = [e["type"] for e in events]
    assert types[0] == "status" and types[-1] == "done" and "token" in types
    assert "".join(e["text"] for e in events if e["type"] == "token").strip() == (
        "alpha beta gamma delta epsilon zeta eta theta"
    )
    assert events[-1]["status"] == "awaiting_plan_approval"
    # From a later offset only the remaining events are sent.
    with client.stream(
        "GET", f"/api/workflows/{rid}/stream", params={"from": len(events) - 1}
    ) as r:
        tail = [json.loads(line[6:]) for line in r.iter_lines() if line.startswith("data: ")]
    assert [e["type"] for e in tail] == ["done"]


def test_llm_failure_is_retryable(client, sample_novel_id, mock_llm, monkeypatch):
    calls = {"n": 0}
    original = mock_llm.stream_text

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise LLMError("transport", "connection reset")
        return original(*a, **k)

    monkeypatch.setattr(mock_llm, "stream_text", flaky)
    mock_llm.queue_text(PLAN)
    run = start(client, sample_novel_id)
    assert run["status"] == "plan_failed" and "connection reset" in run["error"]
    data = client.post(f"/api/workflows/{run['id']}/retry").json()
    assert data["status"] == "awaiting_plan_approval"


def test_clients_cannot_choose_an_unconfigured_llm(client, sample_novel_id):
    r = client.post(
        f"/api/novels/{sample_novel_id}/workflows",
        json={"goal": "Try a paid model", "llm": "anthropic:claude-opus-5-5"},
    )
    assert r.status_code == 400 and "not enabled" in r.json()["detail"]
    r = client.post(f"/api/novels/{sample_novel_id}/extract", params={"llm": "ollama:anything"})
    assert r.status_code == 400
