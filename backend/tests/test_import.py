from sqlalchemy import select

from novelforge.models import Chapter, Character, Claim, EvidenceSpan, Passage


def snapshot(session):
    def rows(model, *cols):
        return sorted(
            tuple(str(getattr(r, c)) for c in cols) for r in session.scalars(select(model))
        )

    return {
        "chapters": rows(Chapter, "id", "number", "title", "content_hash", "story_day"),
        "characters": rows(Character, "id", "name", "aliases", "attributes"),
        "claims": rows(
            Claim,
            "id",
            "subject_character_id",
            "predicate",
            "value",
            "modality",
            "effective_day",
            "time_certainty",
        ),
        "spans": rows(EvidenceSpan, "id", "claim_id", "start", "end", "quote"),
        "passages": rows(Passage, "id", "start", "end"),
    }


def test_import_is_deterministic_across_reimports(client, session):
    first = client.post("/api/samples/lanternfall/import").json()
    assert first["created"] is True
    snap1 = snapshot(session)
    assert len(snap1["chapters"]) == 3 and len(snap1["characters"]) == 3
    assert len(snap1["claims"]) > 0

    client.delete(f"/api/novels/{first['novel_id']}")
    session.expire_all()
    second = client.post("/api/samples/lanternfall/import").json()
    assert second == first
    session.expire_all()
    assert snapshot(session) == snap1


def test_import_is_idempotent(client, session):
    a = client.post("/api/samples/lanternfall/import").json()
    snap = snapshot(session)
    b = client.post("/api/samples/lanternfall/import").json()
    assert b == {"novel_id": a["novel_id"], "created": False}
    session.expire_all()
    assert snapshot(session) == snap
    assert len(client.get("/api/novels").json()) == 1


def test_unknown_sample(client):
    assert client.post("/api/samples/nope/import").status_code == 404
    names = [s["name"] for s in client.get("/api/samples").json()]
    assert names == [
        "lanternfall",
        "linjiang-biaoqi",
        "qingshi-du",
        "taiye-qiushen",
        "tuoling-guoqi",
        "wugang-xinzha",
        "wuling-chashi",
        "xueye-dangpu",
        "xueye-dangpu-revised",
    ]


def test_every_claim_is_grounded_and_timed(client, sample_novel_id, session):
    claims = client.get(f"/api/novels/{sample_novel_id}/claims").json()
    assert len(claims) == 17
    bodies = {str(c.id): c.body for c in session.scalars(select(Chapter))}
    for claim in claims:
        assert claim["evidence"], claim
        for span in claim["evidence"]:
            assert bodies[span["chapter_id"]][span["start"] : span["end"]] == span["quote"]
        if claim["time_certainty"] == "unknown":
            assert claim["effective_day"] is None
        else:
            assert isinstance(claim["effective_day"], int)


def test_plain_text_novel_imports_with_pronoun_attribution(session):
    from novelforge.core.plaintext import split_chapters
    from novelforge.core.sample import text_novel
    from novelforge.services.importer import import_novel

    text = (
        "CHAPTER I\n\nMara Venn came in from the rain. She had a sharp\nface and grey eyes.\n\n"
        "CHAPTER II\n\nMara was in Varrow by nightfall.\n"
    )
    chapters = [(c.title, c.body) for c in split_chapters(text)]
    cast = [{"name": "Mara Venn", "pronouns": "she/her"}]
    novel = text_novel("test-text", "Test", chapters, cast)
    result = import_novel(session, novel)
    session.commit()
    assert result.created and len(chapters) == 2
    claims = session.scalars(select(Claim).where(Claim.novel_id == result.novel.id)).all()
    facts = sorted((c.predicate, c.value, c.time_certainty) for c in claims)
    # "She had a sharp face and grey eyes" (one line once unwrapped) is attributed to Mara.
    assert facts == [("eye_color", "grey", "unknown"), ("location", "Varrow", "unknown")]
    assert import_novel(session, novel).created is False
