import uuid

from sqlalchemy import select

from novelforge.models import CanonChange, Chapter, Claim, Location, ReviewDecision, Scene


def _claims(client, novel_id, **params):
    r = client.get(f"/api/novels/{novel_id}/review", params={"limit": 200, **params})
    assert r.status_code == 200, r.text
    return r.json()


def _find(items, predicate, value=None, subject=None):
    return next(
        c
        for c in items
        if c["predicate"] == predicate
        and (value is None or c["value"] == value)
        and (subject is None or c["subject_name"] == subject)
    )


def test_queue_lists_proposals_with_evidence_and_canon(client, sample_novel_id):
    data = _claims(client, sample_novel_id)
    assert data["counts"] == {"proposed": data["total"]}
    birthplace = _find(data["items"], "birthplace", "Hollin")
    assert birthplace["canon_value"] == "Varrow"
    assert birthplace["evidence"][0]["quote"] == "Tomas was born in Hollin"
    attrs = _claims(client, sample_novel_id, family="attributes")["items"]
    assert {c["predicate"] for c in attrs} <= {
        "eye_color",
        "hair_color",
        "handedness",
        "birthplace",
        "age",
    }


def test_accept_sets_canon_and_audits(client, sample_novel_id, session):
    items = _claims(client, sample_novel_id)["items"]
    grey = _find(items, "eye_color", "grey", "Mara Venn")
    r = client.post(f"/api/claims/{grey['id']}/accept", json={"note": "confirmed"})
    assert r.status_code == 200 and r.json()["changed"] == ["character.eye_color"]
    chars = {c["name"]: c for c in client.get(f"/api/novels/{sample_novel_id}/characters").json()}
    assert chars["Mara Venn"]["attributes"]["eye_color"] == "grey"
    changes = client.get(f"/api/novels/{sample_novel_id}/canon/changes").json()
    assert changes[0]["field"] == "attributes.eye_color" and changes[0]["new_value"] == "grey"
    assert changes[0]["source_claim_id"] == grey["id"]

    # The conflicting statement now also contradicts canon, and accepting it is refused.
    green = _find(items, "eye_color", "green", "Mara Venn")
    r = client.post(f"/api/claims/{green['id']}/accept", json={})
    assert r.status_code == 409 and r.json()["canon_value"] == "grey"
    assert chars["Mara Venn"]["attributes"]["eye_color"] == "grey"
    # ...unless the reviewer explicitly replaces canon.
    r = client.post(f"/api/claims/{green['id']}/accept", json={"replace_canon": True})
    assert r.status_code == 200
    session.expire_all()
    audit = session.scalars(select(CanonChange).order_by(CanonChange.created_at)).all()
    assert [(a.old_value, a.new_value) for a in audit if a.field == "attributes.eye_color"] == [
        (None, "grey"),
        ("grey", "green"),
    ]


def test_reject_removes_claim_from_report(client, sample_novel_id):
    items = _claims(client, sample_novel_id)["items"]
    right = _find(items, "handedness", "right")
    client.post(f"/api/claims/{right['id']}/reject", json={"note": "typo, fixing later"})
    findings = client.get(f"/api/novels/{sample_novel_id}/contradictions").json()["findings"]
    assert "handedness" not in {f["predicate"] for f in findings}
    assert _claims(client, sample_novel_id, status="rejected")["items"][0]["review_note"] == (
        "typo, fixing later"
    )


def test_decisions_survive_reextraction(client, sample_novel_id, session):
    items = _claims(client, sample_novel_id)["items"]
    right = _find(items, "handedness", "right")
    client.post(f"/api/claims/{right['id']}/reject", json={})
    # Edit another paragraph of chapter 2: claims are rebuilt with new ids.
    ch2 = next(
        c for c in client.get(f"/api/novels/{sample_novel_id}/chapters").json() if c["number"] == 2
    )
    full = client.get(f"/api/chapters/{ch2['id']}").json()
    client.patch(
        f"/api/chapters/{ch2['id']}",
        json={"version": full["version"], "body": full["body"] + "\n\nThe end."},
    )
    rejected = _claims(client, sample_novel_id, status="rejected")["items"]
    assert [c["value"] for c in rejected] == ["right"] and rejected[0]["id"] != right["id"]
    assert session.scalar(select(ReviewDecision.decision)) == "rejected"


def test_accept_location_creates_location_and_timeline(client, tmp_path, session):
    from novelforge.bench.generate import generate
    from novelforge.db import get_sessionmaker
    from novelforge.services.importer import import_folder

    generate(tmp_path / "g", 12, seed=3)
    with get_sessionmaker()() as s:
        nid = str(import_folder(s, tmp_path / "g").novel.id)
        s.commit()
    items = _claims(client, nid, family="presence")["items"]
    loc = next(c for c in items if c["predicate"] == "location")
    r = client.post(f"/api/claims/{loc['id']}/accept", json={})
    # Generated corpora ship their places (with travel times), so only the event is new.
    assert r.json()["changed"] == ["timeline_event"]
    canon = client.get(f"/api/novels/{nid}/canon").json()
    assert loc["value"] in {x["name"] for x in canon["locations"]}
    assert canon["timeline"][0]["kind"] == "travel"
    assert session.scalar(select(Location).where(Location.name == loc["value"])).travel_days


def test_batch_accept_skips_canon_conflicts(client, sample_novel_id):
    items = _claims(client, sample_novel_id)["items"]
    ids = [c["id"] for c in items if c["predicate"] in ("birthplace", "eye_color")]
    result = client.post(
        f"/api/novels/{sample_novel_id}/review/accept-batch", json={"claim_ids": ids}
    ).json()
    skipped = {s["id"]: s["reason"] for s in result["skipped"]}
    hollin = _find(items, "birthplace", "Hollin")["id"]
    assert hollin in skipped and "Varrow" in skipped[hollin]
    assert len(result["accepted"]) + len(result["skipped"]) == len(ids)


def test_llm_extraction_job_is_idempotent(client, sample_novel_id, run_jobs, session):
    r = client.post(f"/api/novels/{sample_novel_id}/extract", params={"llm": "mock"}).json()
    assert r["queued_for"] == 3
    run_jobs()
    llm_claims = session.scalars(select(Claim).where(Claim.extractor == "llm:mock")).all()
    assert llm_claims
    before = sorted(str(c.id) for c in llm_claims)
    client.post(f"/api/novels/{sample_novel_id}/extract", params={"llm": "mock"})
    assert run_jobs() == 0  # same chapter versions, model and prompt: nothing to do
    session.expire_all()
    after = sorted(
        str(c.id) for c in session.scalars(select(Claim).where(Claim.extractor == "llm:mock"))
    )
    assert after == before
    # The report de-duplicates identical facts from the two extractors.
    findings = client.get(f"/api/novels/{sample_novel_id}/contradictions").json()["findings"]
    assert len(findings) == 4
    for f in findings:
        spans = [(e["chapter_id"], e["start"], e["end"]) for e in f["evidence"]]
        assert len(spans) == len(set(spans))


def test_scenes_split_on_breaks(client, sample_novel_id, session):
    ch1 = session.scalar(select(Chapter).where(Chapter.number == 1))
    scenes = session.scalars(
        select(Scene).where(Scene.chapter_id == ch1.id).order_by(Scene.ordinal)
    ).all()
    assert len(scenes) == 2
    assert "* * *" not in ch1.body[scenes[0].start : scenes[0].end]
    assert ch1.body[scenes[1].start :].startswith("They climbed together.")
    assert uuid.UUID(str(scenes[0].id))
