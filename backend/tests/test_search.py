def test_search_returns_exact_highlight_offsets(client, sample_novel_id):
    r = client.get(f"/api/novels/{sample_novel_id}/search", params={"q": "flood"})
    assert r.status_code == 200
    data = r.json()
    assert data["hits"] and data["took_ms"] >= 0
    for hit in data["hits"]:
        body = client.get(f"/api/chapters/{hit['chapter_id']}").json()["body"]
        assert body[hit["start"]:hit["end"]] == hit["text"]
        assert hit["highlights"], hit
        for s, e in hit["highlights"]:
            assert body[s:e].lower().startswith("flood")  # "flood", "flooded" (stemmed)


def test_search_phrases_and_ranking(client, sample_novel_id):
    hits = client.get(f"/api/novels/{sample_novel_id}/search",
                      params={"q": '"sea wall"'}).json()["hits"]
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
    client.post(f"/api/novels/{other['id']}/chapters",
                json={"title": "X", "body": "A flood of letters."})
    hits = client.get(f"/api/novels/{other['id']}/search", params={"q": "flood"}).json()["hits"]
    assert [h["chapter_title"] for h in hits] == ["X"]


def test_search_reflects_edits(client, sample_novel_id):
    url = f"/api/novels/{sample_novel_id}/search"
    assert client.get(url, params={"q": "kraken"}).json()["hits"] == []
    ch = client.get(f"/api/novels/{sample_novel_id}/chapters").json()[0]
    full = client.get(f"/api/chapters/{ch['id']}").json()
    client.patch(f"/api/chapters/{ch['id']}",
                 json={"version": full["version"], "body": full["body"] + "\n\nA kraken rose."})
    hits = client.get(url, params={"q": "kraken"}).json()["hits"]
    assert len(hits) == 1 and hits[0]["chapter_version"] == full["version"] + 1
