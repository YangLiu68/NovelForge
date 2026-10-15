def make_novel(client, title="Draft"):
    r = client.post("/api/novels", json={"title": title})
    assert r.status_code == 201, r.text
    return r.json()


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_novel_crud(client):
    novel = make_novel(client, "  The Book  ")
    assert novel["title"] == "The Book" and novel["version"] == 1
    assert [n["id"] for n in client.get("/api/novels").json()] == [novel["id"]]

    r = client.patch(f"/api/novels/{novel['id']}", json={"version": 1, "synopsis": "S"})
    assert r.status_code == 200 and r.json()["version"] == 2 and r.json()["synopsis"] == "S"

    assert client.delete(f"/api/novels/{novel['id']}").status_code == 204
    assert client.get(f"/api/novels/{novel['id']}").status_code == 404


def test_validation_errors(client):
    assert client.post("/api/novels", json={"title": "   "}).status_code == 422
    assert client.get("/api/novels/not-a-uuid").status_code == 422
    novel = make_novel(client)
    r = client.post(f"/api/novels/{novel['id']}/characters",
                    json={"name": "X", "attributes": {"Eye Color": "blue"}})
    assert r.status_code == 422


def test_chapter_crud_numbering_and_revisions(client):
    novel = make_novel(client)
    base = f"/api/novels/{novel['id']}/chapters"
    c1 = client.post(base, json={"title": "One", "body": "Hello  \r\n\r\nWorld"}).json()
    c2 = client.post(base, json={"title": "Two"}).json()
    assert (c1["number"], c2["number"]) == (1, 2)
    assert c1["body"] == "Hello\n\nWorld" and c1["word_count"] == 2
    assert client.post(base, json={"title": "Dup", "number": 1}).status_code == 409

    r = client.patch(f"/api/chapters/{c1['id']}", json={"version": 1, "body": "Hello again"})
    assert r.status_code == 200 and r.json()["version"] == 2
    revs = client.get(f"/api/chapters/{c1['id']}/revisions").json()
    assert [rv["version"] for rv in revs] == [2, 1]
    old = client.get(f"/api/chapters/{c1['id']}/revisions/1").json()
    assert old["body"] == "Hello\n\nWorld"

    # A no-op save does not bump the version or add a revision.
    r = client.patch(f"/api/chapters/{c1['id']}", json={"version": 2, "body": "Hello again"})
    assert r.json()["version"] == 2
    assert len(client.get(f"/api/chapters/{c1['id']}/revisions").json()) == 2

    assert [c["title"] for c in client.get(base).json()] == ["One", "Two"]
    assert client.delete(f"/api/chapters/{c2['id']}").status_code == 204
    assert client.get(f"/api/chapters/{c2['id']}").status_code == 404


def test_stale_chapter_save_is_rejected_and_changes_nothing(client):
    novel = make_novel(client)
    ch = client.post(f"/api/novels/{novel['id']}/chapters",
                     json={"title": "One", "body": "v1"}).json()
    assert client.patch(f"/api/chapters/{ch['id']}",
                        json={"version": 1, "body": "edit A"}).status_code == 200
    r = client.patch(f"/api/chapters/{ch['id']}", json={"version": 1, "body": "edit B"})
    assert r.status_code == 409
    assert r.json()["current_version"] == 2
    current = client.get(f"/api/chapters/{ch['id']}").json()
    assert current["body"] == "edit A" and current["version"] == 2


def test_stale_character_and_novel_saves_are_rejected(client):
    novel = make_novel(client)
    assert client.patch(f"/api/novels/{novel['id']}",
                        json={"version": 7, "title": "X"}).status_code == 409
    ch = client.post(f"/api/novels/{novel['id']}/characters", json={"name": "Mara"}).json()
    assert client.patch(f"/api/characters/{ch['id']}",
                        json={"version": 1, "description": "a"}).status_code == 200
    assert client.patch(f"/api/characters/{ch['id']}",
                        json={"version": 1, "description": "b"}).status_code == 409


def test_character_crud(client):
    novel = make_novel(client)
    base = f"/api/novels/{novel['id']}/characters"
    r = client.post(base, json={"name": "Mara Venn", "aliases": [" the cartographer ", ""],
                                "attributes": {"eye_color": "grey", "notes": "  "}})
    assert r.status_code == 201
    ch = r.json()
    assert ch["aliases"] == ["the cartographer"] and ch["attributes"] == {"eye_color": "grey"}
    assert client.post(base, json={"name": "Mara Venn"}).status_code == 409
    r = client.patch(f"/api/characters/{ch['id']}", json={"version": 1, "name": "Mara V."})
    assert r.json()["name"] == "Mara V." and r.json()["version"] == 2
    assert client.delete(f"/api/characters/{ch['id']}").status_code == 204
    assert client.get(base).json() == []


def test_deleting_a_novel_cascades(client, session):
    from sqlalchemy import func, select

    from novelforge.models import Chapter, Character, Claim, EvidenceSpan, Passage, Revision

    novel = make_novel(client)
    client.post(f"/api/novels/{novel['id']}/characters", json={"name": "Mara Venn"})
    client.post(f"/api/novels/{novel['id']}/chapters",
                json={"title": "One", "body": "Mara's eyes were grey."})
    assert session.scalar(select(func.count()).select_from(Claim)) == 1
    client.delete(f"/api/novels/{novel['id']}")
    for model in (Chapter, Character, Claim, EvidenceSpan, Passage, Revision):
        assert session.scalar(select(func.count()).select_from(model)) == 0, model
