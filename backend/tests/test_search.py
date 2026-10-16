def test_search_returns_exact_highlight_offsets(client, sample_novel_id):
    r = client.get(f"/api/novels/{sample_novel_id}/search", params={"q": "flood"})
    assert r.status_code == 200
    data = r.json()
    assert data["hits"] and data["took_ms"] >= 0
    for hit in data["hits"]:
        body = client.get(f"/api/chapters/{hit['chapter_id']}").json()["body"]
        assert body[hit["start"] : hit["end"]] == hit["text"]
        assert hit["highlights"], hit
        for s, e in hit["highlights"]:
            assert body[s:e].lower().startswith("flood")  # "flood", "flooded" (stemmed)


def test_search_phrases_and_ranking(client, sample_novel_id):
    hits = client.get(f"/api/novels/{sample_novel_id}/search", params={"q": '"sea wall"'}).json()[
        "hits"
    ]
    assert hits
    assert all("sea wall" in h["text"].lower() for h in hits)
    scores = [h["score"] for h in hits]
    assert scores == sorted(scores, reverse=True)


def test_search_no_match_and_stopwords(client, sample_novel_id):
    url = f"/api/novels/{sample_novel_id}/search"
    assert client.get(url, params={"q": "dragon"}).json()["hits"] == []
    assert client.get(url, params={"q": "the and of"}).json()["hits"] == []
    assert client.get(url, params={"q": ""}).status_code == 422


def test_search_is_scoped_to_the_novel(client, sample_novel_id):
    other = client.post("/api/novels", json={"title": "Other"}).json()
    client.post(
        f"/api/novels/{other['id']}/chapters", json={"title": "X", "body": "A flood of letters."}
    )
    hits = client.get(f"/api/novels/{other['id']}/search", params={"q": "flood"}).json()["hits"]
    assert [h["chapter_title"] for h in hits] == ["X"]


def test_search_reflects_edits(client, sample_novel_id):
    url = f"/api/novels/{sample_novel_id}/search"
    assert client.get(url, params={"q": "kraken"}).json()["hits"] == []
    ch = client.get(f"/api/novels/{sample_novel_id}/chapters").json()[0]
    full = client.get(f"/api/chapters/{ch['id']}").json()
    client.patch(
        f"/api/chapters/{ch['id']}",
        json={"version": full["version"], "body": full["body"] + "\n\nA kraken rose."},
    )
    hits = client.get(url, params={"q": "kraken"}).json()["hits"]
    assert len(hits) == 1 and hits[0]["chapter_version"] == full["version"] + 1


def test_chinese_search_matches_words_and_highlights_them(client):
    novel_id = client.post("/api/samples/xueye-dangpu/import").json()["novel_id"]
    url = f"/api/novels/{novel_id}/search"
    hits = client.get(url, params={"q": "沈若兰"}).json()["hits"]
    assert hits and all("沈若兰" in h["text"] for h in hits)
    assert {h["chapter_number"] for h in hits} == {1, 3}
    for hit in hits:
        body = client.get(f"/api/chapters/{hit['chapter_id']}").json()["body"]
        assert body[hit["start"] : hit["end"]] == hit["text"]
        assert [body[s:e] for s, e in hit["highlights"]] == ["沈若兰"] * hit["text"].count("沈若兰")
    # A quoted phrase must appear as written; its characters in another order do not match.
    assert [h["chapter_number"] for h in client.get(url, params={"q": '"二十文"'}).json()["hits"]]
    assert client.get(url, params={"q": '"文十二"'}).json()["hits"] == []
    # fts mode uses OR semantics: either word is enough.
    hits = client.get(url, params={"q": "乞丐 盐价", "mode": "fts"}).json()["hits"]
    assert any("乞丐" in h["text"] for h in hits) and any("盐价" in h["text"] for h in hits)
