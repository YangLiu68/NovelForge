import uuid

from sqlalchemy import select

from novelforge.llm.mock import MockLLM
from novelforge.models import Claim, StoredFinding
from novelforge.services import review
from novelforge.services.rule_judge import judge_novel


def report(client, nid, **params):
    r = client.get(f"/api/novels/{nid}/contradictions", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_findings_are_stored_with_ids_and_status(client, sample_novel_id):
    data = report(client, sample_novel_id)
    assert data["status_counts"] == {"open": 4}
    assert all(uuid.UUID(f["id"]) and f["status"] == "open" for f in data["findings"])
    # Refreshing again does not duplicate.
    assert report(client, sample_novel_id)["status_counts"] == {"open": 4}


def test_dismiss_needs_a_reason_and_survives_refresh_and_edits(client, sample_novel_id):
    f = next(
        x for x in report(client, sample_novel_id)["findings"] if x["predicate"] == "handedness"
    )
    assert client.post(f"/api/findings/{f['id']}/dismiss", json={}).status_code == 409
    r = client.post(
        f"/api/findings/{f['id']}/dismiss", json={"note": "intentional: Tomas lies about it"}
    )
    assert r.status_code == 200
    assert {x["predicate"] for x in report(client, sample_novel_id)["findings"]} == {
        "eye_color",
        "age",
        "birthplace",
    }
    # Edit chapter 3 elsewhere: the dismissed finding keeps its status.
    ch3 = client.get(f"/api/novels/{sample_novel_id}/chapters").json()[2]
    full = client.get(f"/api/chapters/{ch3['id']}").json()
    client.patch(
        f"/api/chapters/{ch3['id']}",
        json={"version": full["version"], "body": full["body"] + "\n\nA gull cried."},
    )
    dismissed = report(client, sample_novel_id, status="dismissed")["findings"]
    assert [x["predicate"] for x in dismissed] == ["handedness"]
    assert dismissed[0]["status_note"] == "intentional: Tomas lies about it"


def test_fixing_text_auto_resolves_and_reintroducing_reopens(client, sample_novel_id):
    report(client, sample_novel_id)
    ch3 = client.get(f"/api/novels/{sample_novel_id}/chapters").json()[2]
    full = client.get(f"/api/chapters/{ch3['id']}").json()
    fixed = full["body"].replace("Mara's eyes were green", "Mara's eyes were grey")
    v = client.patch(
        f"/api/chapters/{ch3['id']}", json={"version": full["version"], "body": fixed}
    ).json()["version"]
    resolved = report(client, sample_novel_id, status="resolved")["findings"]
    assert [x["predicate"] for x in resolved] == ["eye_color"] and resolved[0]["auto_resolved"]
    client.patch(f"/api/chapters/{ch3['id']}", json={"version": v, "body": full["body"]})
    open_ = report(client, sample_novel_id)["findings"]
    assert "eye_color" in {x["predicate"] for x in open_}
    assert report(client, sample_novel_id, status="resolved")["findings"] == []


def test_manual_resolve_and_reopen(client, sample_novel_id):
    f = report(client, sample_novel_id)["findings"][0]
    client.post(f"/api/findings/{f['id']}/resolve", json={"note": "fixed in draft 2"})
    assert report(client, sample_novel_id)["status_counts"]["resolved"] == 1
    client.post(f"/api/findings/{f['id']}/reopen")
    assert report(client, sample_novel_id)["status_counts"] == {"open": 4}


def test_preview_with_uncertain_statements_is_not_stored(client, sample_novel_id, session):
    data = report(client, sample_novel_id, include_uncertain=True)
    assert data["status_counts"] == {"preview": 6}
    assert session.scalar(select(StoredFinding.id).limit(1)) is None


def test_rule_judge_stores_verified_violations(client, sample_novel_id, run_jobs, session):
    run_jobs()  # embeddings for retrieval
    nid = uuid.UUID(sample_novel_id)
    # A proposed world rule (as an LLM extractor would produce it), from chapter 1's text.
    rule_source = session.scalar(select(Claim).where(Claim.predicate == "eye_color").limit(1))
    rule = Claim(
        id=uuid.uuid4(),
        novel_id=nid,
        chapter_id=rule_source.chapter_id,
        chapter_version=1,
        subject_character_id=None,
        subject_text="world",
        predicate="world_rule",
        value="No lamp burns below the sea wall.",
        raw_value="",
        modality="asserted",
        confidence=0.9,
        status="proposed",
        extractor="llm:test",
        effective_day=0,
        time_certainty="chapter_day",
        details={},
        fingerprint="f",
    )
    session.add(rule)
    session.commit()
    llm = MockLLM()
    llm.queue_json(
        {
            "violations": [
                {"passage": 1, "quote": "QUOTE_NOT_IN_TEXT", "explanation": "x", "confidence": 0.9},
            ]
        }
    )
    result = judge_novel(session, nid, llm)
    session.commit()
    assert result["rules"] == 1 and result["violations"] == 0  # unverifiable quote dropped
    prompt = llm.calls[0]["prompt"]
    first_passage = prompt.split("[1] (chapter ")[1].split("\n", 1)[1].split("\n\n")[0]
    quote = " ".join(first_passage.split()[:6])
    llm.queue_json(
        {
            "violations": [
                {
                    "passage": 1,
                    "quote": quote,
                    "explanation": "A lamp burns there.",
                    "confidence": 0.85,
                },
            ]
        }
    )
    judge_novel(session, nid, llm)
    session.commit()
    stored = session.scalars(
        select(StoredFinding).where(StoredFinding.kind == "world_rule_violation")
    ).all()
    assert len(stored) == 1 and stored[0].severity == "high"
    assert stored[0].evidence[-1]["quote"] == quote
    assert stored[0].detector == "rule-judge:mock"
    # Judging again with the same answer does not duplicate the finding.
    llm.queue_json(
        {
            "violations": [
                {
                    "passage": 1,
                    "quote": quote,
                    "explanation": "A lamp burns there.",
                    "confidence": 0.85,
                },
            ]
        }
    )
    judge_novel(session, nid, llm)
    session.commit()
    assert (
        session.scalar(
            select(StoredFinding.id).where(StoredFinding.kind == "world_rule_violation").offset(1)
        )
        is None
    )
    # Rule-based refreshes leave the judge's findings alone.
    assert any(
        f["kind"] == "world_rule_violation" for f in report(client, sample_novel_id)["findings"]
    )
    assert review  # imported for side effects in other tests


def test_a_failed_attempt_is_not_a_world_rule_violation():
    from novelforge.services.rule_judge import _FAILED_ATTEMPT

    assert _FAILED_ATTEMPT.search("Vesa tried to cut the saltglass, but the knife skidded off it.")
    assert _FAILED_ATTEMPT.search("她试图劈开盐晶，刀却滑开了。")
    assert _FAILED_ATTEMPT.search("They searched in vain for the bird.")
    # Done, or tried and done: still a violation.
    assert not _FAILED_ATTEMPT.search("A gull flew straight across the Grey Reach.")
    assert not _FAILED_ATTEMPT.search("He tried to light the lamp and it caught at once.")
    assert not _FAILED_ATTEMPT.search("剑光一闪，盐晶被劈成两半。")
