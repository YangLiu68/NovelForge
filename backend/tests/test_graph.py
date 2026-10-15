def test_character_graph_cooccurrence(client, sample_novel_id):
    g = client.get(f"/api/novels/{sample_novel_id}/graph").json()
    names = {n["id"]: n["name"] for n in g["nodes"]}
    assert set(names.values()) == {"Mara Venn", "Tomas Hale", "Ilsa Corr"}
    mara = next(n for n in g["nodes"] if n["name"] == "Mara Venn")
    assert mara["mentions"] > 0 and mara["first_chapter"] == 1
    pair = {frozenset((names[e["source"]], names[e["target"]])): e for e in g["edges"]}
    edge = pair[frozenset(("Mara Venn", "Tomas Hale"))]
    assert edge["weight"] >= 1 and edge["samples"]
    for s in edge["samples"]:
        body = client.get(f"/api/chapters/{s['chapter_id']}").json()["body"]
        assert body[s["start"] : s["end"]].startswith(s["quote"][:50])


def test_timeline_lanes_and_findings(client, sample_novel_id):
    t = client.get(f"/api/novels/{sample_novel_id}/timeline").json()
    lanes = {lane["name"]: lane for lane in t["lanes"]}
    ilsa = lanes["Ilsa Corr"]["events"]
    assert [(e["day"], e["predicate"], e["value"]) for e in ilsa if e["predicate"] == "age"] == [
        (0, "age", "40"),
        (3, "age", "46"),
    ]
    assert t["day_range"] == [0, 1827]
    age = next(f for f in t["findings"] if f["kind"] == "age_timeline")
    lane_ids = {e["claim_id"] for e in ilsa}
    assert set(age["claim_ids"]) <= lane_ids
    assert [c["number"] for c in t["chapters"]] == [1, 2, 3]
