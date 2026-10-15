"""Plain-text import and the real-prose scorer, offline (a tiny book in a temporary cache)."""

import hashlib
import json

import yaml

from novelforge.bench import real_text
from novelforge.core.plaintext import split_chapters, strip_gutenberg, unwrap

BOOK = """The Project Gutenberg eBook of Test

*** START OF THE PROJECT GUTENBERG EBOOK TEST ***

CONTENTS

 CHAPTER ONE THE START
 CHAPTER TWO THE END

CHAPTER ONE
THE START

Mara's eyes were grey, and she
was born in Varrow.

Tomas waited by the door.

CHAPTER TWO
THE END

Mara's eyes were green that day.

*** END OF THE PROJECT GUTENBERG EBOOK TEST ***
Licence text.
"""


def test_strip_unwrap_split():
    body = strip_gutenberg(BOOK)
    assert "Licence" not in body and "eBook of Test" not in body
    assert unwrap("one\ntwo\n\nthree") == "one two\n\nthree"
    chapters = split_chapters(body, title_lines=1)
    assert [c.title for c in chapters] == ["CHAPTER ONE THE START", "CHAPTER TWO THE END"]
    assert chapters[0].body == (
        "Mara's eyes were grey, and she was born in Varrow.\n\nTomas waited by the door."
    )


def test_run_scores_labels_and_lists_unlabelled(tmp_path):
    raw = BOOK.encode()
    manifest = tmp_path / "books.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {
                "books": [
                    {
                        "id": "test",
                        "title": "Test",
                        "author": "Nobody",
                        "role": "dev",
                        "url": "https://example.invalid/test.txt",
                        "sha256": hashlib.sha256(raw).hexdigest(),
                        "title_lines": 1,
                        "characters": [
                            {"name": "Mara Venn", "aliases": [], "gender": "f"},
                            {"name": "Tomas Hale", "aliases": [], "gender": "m"},
                        ],
                    }
                ]
            }
        )
    )
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "test.txt").write_bytes(raw)  # no download
    labels = tmp_path / "labels"
    labels.mkdir()

    report, todo = real_text.run("test", manifest, cache, labels)
    assert report["source"]["matches_manifest"] is True
    assert report["claims"] == 3  # two eye colours and a birthplace (through "she")
    assert report["findings"]["total"] == 1  # grey vs green
    kinds = sorted(t["type"] for t in todo)
    assert kinds == ["candidate", "candidate", "claim", "claim", "claim", "finding"]

    # Label everything: one claim wrong, the finding true, candidates with their facts.
    rows = []
    for t in todo:
        if t["type"] == "claim":
            fact = "wrong" if t["predicate"] == "birthplace" else "right"
            rows.append({"key": t["key"], "type": "claim", "fact": fact, "asserted": True})
        elif t["type"] == "finding":
            rows.append({"key": t["key"], "type": "finding", "verdict": "true"})
        else:
            value = "grey" if "grey" in t["sentence"] else "green"
            rows.append(
                {
                    "key": t["key"],
                    "type": "candidate",
                    "facts": [
                        {
                            "subject": "Mara Venn",
                            "predicate": "eye_color",
                            "value": value,
                            "asserted": True,
                        }
                    ],
                }
            )
    (labels / "test.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))

    report, todo = real_text.run("test", manifest, cache, labels)
    assert todo == []
    overall = report["precision"]["overall"]
    assert (overall["correct"], overall["wrong"], overall["unlabelled"]) == (2, 1, 0)
    assert overall["fact_precision"] == round(2 / 3, 4)
    assert report["findings"]["true"] == 1
    assert report["recall"]["asserted"] == {"facts": 2, "found": 2, "recall": 1.0}
