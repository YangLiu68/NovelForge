import argparse
import json

from novelforge.cli import cmd_eval_sample


def report(client, novel_id, **params):
    r = client.get(f"/api/novels/{novel_id}/contradictions", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_sample_report_finds_seeded_contradictions(client, sample_novel_id):
    data = report(client, sample_novel_id)
    got = {(f["kind"], f["subject_name"], f["predicate"]) for f in data["findings"]}
    assert got == {
        ("attribute_conflict", "Mara Venn", "eye_color"),
        ("attribute_conflict", "Tomas Hale", "handedness"),
        ("age_timeline", "Ilsa Corr", "age"),
        ("canon_conflict", "Tomas Hale", "birthplace"),
    }
    assert [f["severity"] for f in data["findings"]] == ["high", "high", "high", "medium"]
    for f in data["findings"]:
        assert f["explanation"] and f["suggestion"] and f["evidence"]
        for e in f["evidence"]:
            body = client.get(f"/api/chapters/{e['chapter_id']}").json()["body"]
            assert body[e["start"]:e["end"]] == e["quote"]


def test_low_confidence_threshold_surfaces_hedged_and_reported_claims(client, sample_novel_id):
    data = report(client, sample_novel_id, min_confidence=0.3)
    got = {(f["subject_name"], f["predicate"]) for f in data["findings"]}
    assert ("Ilsa Corr", "eye_color") in got  # "seemed almost black" vs canon brown
    assert ("Tomas Hale", "eye_color") in got  # clerk's "blue eyes" vs narration


def test_fixing_the_text_clears_the_finding(client, sample_novel_id):
    chapters = client.get(f"/api/novels/{sample_novel_id}/chapters").json()
    ch3 = client.get(f"/api/chapters/{chapters[2]['id']}").json()
    body = ch3["body"].replace("Mara's eyes were green", "Mara's eyes were grey")
    r = client.patch(f"/api/chapters/{ch3['id']}", json={"version": ch3["version"], "body": body})
    assert r.status_code == 200
    got = {(f["subject_name"], f["predicate"]) for f in report(client, sample_novel_id)["findings"]}
    assert ("Mara Venn", "eye_color") not in got and len(got) == 3


def test_character_sheet_change_reextracts(client, sample_novel_id):
    chars = {c["name"]: c for c in client.get(f"/api/novels/{sample_novel_id}/characters").json()}
    tomas = chars["Tomas Hale"]
    # Make Hollin canon: the canon conflict now points at chapter 1's "Varrow".
    r = client.patch(f"/api/characters/{tomas['id']}",
                     json={"version": tomas["version"], "attributes": {"birthplace": "Hollin"}})
    assert r.status_code == 200
    [f] = [f for f in report(client, sample_novel_id)["findings"]
           if f["predicate"] == "birthplace"]
    assert f["canon_value"] == "Hollin" and [e["quote"] for e in f["evidence"]] == [
        "Tomas, born in Varrow"
    ]
    # Dropping the name "Ilsa Corr" + alias removes Ilsa's claims, so the age finding goes.
    ilsa = chars["Ilsa Corr"]
    client.patch(f"/api/characters/{ilsa['id']}",
                 json={"version": ilsa["version"], "name": "Ilse Kor", "aliases": []})
    got = {(f["subject_name"], f["predicate"]) for f in report(client, sample_novel_id)["findings"]}
    assert ("Ilse Kor", "age") not in got


def test_cli_eval_db_matches_in_memory(database_url, capsys):
    cmd_eval_sample(argparse.Namespace(name="lanternfall", db=False, json=True))
    mem = json.loads(capsys.readouterr().out)
    cmd_eval_sample(argparse.Namespace(name="lanternfall", db=True, json=True))
    db = json.loads(capsys.readouterr().out)
    for result in (mem, db):
        assert result["true_positives"] == 4 and result["false_positives"] == 0
        assert result["negatives_violated"] == 0 and result["citation_precision"] == 1.0
        assert [m["id"] for m in result["missed"]] == ["GT5"]
    strip = {"mode"}
    assert {k: v for k, v in mem.items() if k not in strip} == {
        k: v for k, v in db.items() if k not in strip
    }
