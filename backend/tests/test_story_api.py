"""Story audits through the API: jobs, idempotent starts, staleness, the LLM allow-list, and
replaying a recorded run (the same prompts from the database as from files)."""

from __future__ import annotations

from novelforge.llm.cache import CachingLLM
from novelforge.llm.mock import MockLLM
from novelforge.narrative.audit import audit_story
from tests.test_story_audit import BEATS as SCRIPT_BEATS
from tests.test_story_audit import (
    CAST,
    chapter_of,
    chapters,
    later_answer,
    motive_answer,
    plan_answer,
    plot_answer,
)
from tests.test_story_audit import NOTES as SCRIPT_NOTES


def _import_sample(client) -> str:
    r = client.post("/api/samples/xueye-dangpu/import")
    assert r.status_code == 200, r.text
    return r.json()["novel_id"]


def test_start_run_and_reuse(client, run_jobs):
    novel_id = _import_sample(client)
    r = client.post(f"/api/novels/{novel_id}/story-audits", json={})
    assert r.status_code == 202, r.text
    run = r.json()
    assert run["status"] == "queued" and run["llm"] == "mock"
    assert run_jobs() >= 1
    done = client.get(f"/api/story-audits/{run['id']}").json()
    assert done["status"] == "done", done
    assert done["result"]["language"] == "zh"
    assert [c["number"] for c in done["result"]["chapters"]] == list(range(1, 9))
    assert done["stale_chapters"] == [] and len(done["chapter_ids"]) == 8
    # Same text, model and prompts: the finished run is returned, nothing is queued.
    again = client.post(f"/api/novels/{novel_id}/story-audits", json={}).json()
    assert again["id"] == run["id"]
    assert [x["id"] for x in client.get(f"/api/novels/{novel_id}/story-audits").json()] == [
        run["id"]
    ]


def test_edits_make_a_run_stale_and_a_new_start_reads_the_new_text(client, run_jobs):
    novel_id = _import_sample(client)
    run = client.post(f"/api/novels/{novel_id}/story-audits", json={}).json()
    run_jobs()
    ch = client.get(f"/api/novels/{novel_id}/chapters").json()[1]
    full = client.get(f"/api/chapters/{ch['id']}").json()
    r = client.patch(
        f"/api/chapters/{ch['id']}",
        json={"version": full["version"], "body": full["body"] + "\n\n她把剩下的钱收好。"},
    )
    assert r.status_code == 200, r.text
    assert client.get(f"/api/story-audits/{run['id']}").json()["stale_chapters"] == [ch["id"]]
    fresh = client.post(f"/api/novels/{novel_id}/story-audits", json={}).json()
    assert fresh["id"] != run["id"]


def test_only_offline_or_configured_models_are_allowed(client):
    novel_id = _import_sample(client)
    r = client.post(f"/api/novels/{novel_id}/story-audits", json={"llm": "anthropic"})
    assert r.status_code == 400 and "not enabled" in r.json()["detail"]


def _scripted(name: str) -> MockLLM:
    llm = MockLLM(name=name)
    llm.on_schema("character_notes", lambda s, p, _: {"notes": SCRIPT_NOTES[chapter_of(p)]})
    llm.on_schema("chapter_beats", lambda s, p, _: SCRIPT_BEATS[chapter_of(p)])
    llm.on_schema("motive_check", lambda s, p, _: motive_answer(p))
    llm.on_schema("later_explanation", lambda s, p, _: later_answer(p))
    llm.on_schema("plot_check", lambda s, p, _: plot_answer(p))
    llm.on_schema("revision_plan", lambda s, p, _: plan_answer(p))
    return llm


def test_a_recorded_run_replays_through_the_api(client, run_jobs, tmp_path, monkeypatch):
    # Record: the scripted model, named like a local model, on the story read from "files".
    recorder = CachingLLM(_scripted("ollama:fake"), tmp_path / "story-fake.jsonl")
    direct = audit_story(chapters(), CAST, recorder)
    assert recorder.misses > 0

    # The same story typed in through the API.
    novel = client.post("/api/novels", json={"title": "暗柜"}).json()
    for ch in chapters():
        r = client.post(
            f"/api/novels/{novel['id']}/chapters", json={"title": ch.title, "body": ch.body}
        )
        assert r.status_code == 201, r.text
    for m in CAST:
        r = client.post(
            f"/api/novels/{novel['id']}/characters",
            json={"name": m.name, "aliases": list(m.aliases), "description": m.description},
        )
        assert r.status_code == 201, r.text

    from novelforge.config import get_settings
    from novelforge.llm.registry import get_llm

    monkeypatch.setenv("REPLAY_DIR", str(tmp_path))
    get_settings.cache_clear()
    get_llm.cache_clear()
    try:
        run = client.post(
            f"/api/novels/{novel['id']}/story-audits", json={"llm": "replay:ollama:fake"}
        ).json()
        run_jobs()
        done = client.get(f"/api/story-audits/{run['id']}").json()
        assert done["status"] == "done", done
        replayed = done["result"]
        assert replayed["llm"] == "replay:ollama:fake"
        assert [(i["kind"], i["chapter"]) for i in replayed["issues"]] == [
            (i.kind, i.chapter) for i in direct.issues
        ]
        assert replayed["usage"]["cost_usd"] == 0.0

        # Change the text: the prompts differ, so replay refuses instead of inventing answers.
        ch = client.get(f"/api/novels/{novel['id']}/chapters").json()[0]
        full = client.get(f"/api/chapters/{ch['id']}").json()
        client.patch(
            f"/api/chapters/{ch['id']}", json={"version": full["version"], "body": "改过的正文。"}
        )
        run2 = client.post(
            f"/api/novels/{novel['id']}/story-audits", json={"llm": "replay:ollama:fake"}
        ).json()
        run_jobs()
        failed = client.get(f"/api/story-audits/{run2['id']}").json()
        assert failed["status"] == "failed" and "no recorded answer" in failed["error"]
    finally:
        get_settings.cache_clear()
        get_llm.cache_clear()


def test_llm_estimate_before_a_run(client):
    novel_id = client.post("/api/samples/qingshi-du/import").json()["novel_id"]
    r = client.get(f"/api/novels/{novel_id}/llm-estimate", params={"task": "story"})
    assert r.status_code == 200, r.text
    e = r.json()
    # The configured model in tests is the offline mock: free, but the calls are still counted.
    assert e["free"] and e["cost_usd"] == 0.0 and e["calls"] == 8 * 7 + 10 and e["language"] == "zh"
    assert (
        client.get(f"/api/novels/{novel_id}/llm-estimate", params={"task": "x"}).status_code == 422
    )
    # A client cannot price a model the server has not enabled.
    r = client.get(
        f"/api/novels/{novel_id}/llm-estimate",
        params={"llm": "openrouter:anthropic/claude-opus-5.5"},
    )
    assert r.status_code >= 400


def test_estimate_prices_hosted_models_and_admits_unknown_ones():
    from novelforge.core.domain import ChapterRef
    from novelforge.llm.estimate import estimate

    chapters = [ChapterRef(f"c{i}", i, "", "word " * 3000, 1, 0) for i in range(1, 4)]
    e = estimate(chapters, "openrouter:anthropic/claude-haiku-5.5", "extract", 6000)
    assert e["calls"] == 3 and e["input_tokens"] == 3 * 1760 + 3 * 4500
    assert e["output_tokens"] == int(e["input_tokens"] * 0.6)
    assert e["low_usd"] < e["cost_usd"] < e["high_usd"]
    assert (
        estimate(chapters, "openrouter:anthropic/claude-haiku-5.5", "extract", 1000)["calls"] == 9
    )
    assert estimate(chapters, "openrouter:someone/new-model", "story", 6000)["cost_usd"] is None
    assert estimate(chapters, "ollama:qwen2.5:7b", "story", 500)["free"]
