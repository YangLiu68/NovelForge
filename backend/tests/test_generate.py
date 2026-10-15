import filecmp

import pytest
import yaml

from novelforge.bench.generate import generate
from novelforge.core.sample import load_folder


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    out = tmp_path_factory.mktemp("syn") / "syn-60"
    gt = generate(out, 60, seed=11)
    return out, gt


def test_same_seed_same_bytes(tmp_path, corpus):
    out, _ = corpus
    again = tmp_path / "again"
    generate(again, 60, seed=11)
    names = sorted(p.name for p in out.iterdir())
    assert names == sorted(p.name for p in again.iterdir())
    match, mismatch, errors = filecmp.cmpfiles(out, again, names, shallow=False)
    assert not mismatch and not errors


def test_different_seed_differs(tmp_path, corpus):
    out, _ = corpus
    other = tmp_path / "other"
    generate(other, 60, seed=12)
    assert (out / "ch0010.md").read_text() != (other / "ch0010.md").read_text()


def test_every_labelled_span_is_exact(corpus):
    out, gt = corpus
    novel = load_folder(out)
    bodies = {c.number: c.body for c in novel.chapters}
    spans = [e for c in gt["contradictions"] for e in c["evidence"]]
    spans += [e for n in gt["negatives"] for e in n["evidence"]]
    spans += [e for f in gt["facts"] for e in f["evidence"]]
    spans += [r for q in gt["queries"] for r in q["relevant"]]
    spans += [f["setup"] for f in gt["foreshadowing"]]
    assert len(spans) > 100
    for s in spans:
        assert bodies[s["chapter"]][s["start"] : s["end"]] == s["text"], s


def test_coverage_of_categories_and_negatives(corpus):
    _, gt = corpus
    cats = {c["category"] for c in gt["contradictions"]}
    assert {"identity", "timeline", "location", "world_rules"} <= cats
    assert len(gt["contradictions"]) >= 6 and len(gt["negatives"]) >= 6
    assert {q["kind"] for q in gt["queries"]} == {"lexical", "paraphrase"}
    for q in gt["queries"]:
        assert q["relevant"], q


def test_ground_truth_round_trips_through_yaml(corpus):
    out, gt = corpus
    assert yaml.safe_load((out / "ground_truth.yaml").read_text()) == gt


def test_tiny_corpus(tmp_path):
    gt = generate(tmp_path / "tiny", 3, seed=1)
    assert len(list((tmp_path / "tiny").glob("ch*.md"))) == 3
    assert gt["generator"]["chapters"] == 3


def test_corpus_imports(client, tmp_path):
    from novelforge.db import get_sessionmaker
    from novelforge.services.importer import import_folder

    out = tmp_path / "imp"
    generate(out, 12, seed=3)
    with get_sessionmaker()() as s:
        result = import_folder(s, out)
        s.commit()
    novel_id = str(result.novel.id)
    assert len(client.get(f"/api/novels/{novel_id}/chapters").json()) == 12
    assert client.get(f"/api/novels/{novel_id}/contradictions").status_code == 200


def test_consistency_benchmark_runs_and_structured_memory_wins(tmp_path, database_url):
    from sqlalchemy.engine import make_url

    from novelforge.bench import consistency_eval

    out = tmp_path / "c"
    generate(out, 40, seed=5)
    base = make_url(database_url).set(database="postgres")
    report = consistency_eval.run(out, base, database="novelforge_test_consistency")
    systems = report["systems"]
    assert set(systems) == {"no-memory", "vector-only", "hybrid", "structured"}
    assert systems["structured"]["recall_all"] >= systems["no-memory"]["recall_all"]
    assert systems["structured"]["negatives_violated"] == 0
    assert consistency_eval.to_markdown(report).count("|") > 20


def test_long_corpora_stay_plausible(tmp_path):
    gt = generate(tmp_path / "long", 1000, seed=7)
    ages = [int(f["value"]) for f in gt["facts"] if f["predicate"] == "age"]
    assert ages and max(ages) < 100
    assert len(gt["contradictions"]) >= 100 and len(gt["negatives"]) >= 100
