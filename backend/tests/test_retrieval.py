import math

import pytest

from novelforge.retrieval.embedders import HashEmbedder, canonical, get_embedder
from novelforge.retrieval.index import ensure_hnsw_index
from novelforge.retrieval.rerankers import LexicalReranker
from novelforge.retrieval.search import MODES, search


def test_hash_embedder_is_deterministic_and_normalised():
    e = HashEmbedder(64)
    a = e.embed_documents(["Mara's grey eyes"]).vectors[0]
    b = e.embed_documents(["Mara's grey eyes"]).vectors[0]
    assert a == b and len(a) == 64
    assert math.isclose(sum(x * x for x in a), 1.0, rel_tol=1e-9)
    assert e.embed_query("grey eyes").tokens_exact is False


def test_canonical_names():
    assert canonical("hash") == "hash:384"
    assert canonical("fastembed") == "fastembed:BAAI/bge-small-en-v1.5"
    assert get_embedder("hash").name == "hash:384"
    with pytest.raises(ValueError):
        canonical("word2vec")


def test_lexical_reranker_prefers_query_terms():
    scores = LexicalReranker().score(
        "colour of Mara's eyes", ["The fog sat on the harbour.", "Mara's eyes were grey."]
    )
    assert scores[1] > scores[0]


@pytest.fixture
def indexed_sample(client, sample_novel_id, run_jobs):
    run_jobs()
    return sample_novel_id


def _top_texts(client, novel_id, q, mode, limit=5):
    r = client.get(f"/api/novels/{novel_id}/search", params={"q": q, "mode": mode, "limit": limit})
    assert r.status_code == 200, r.text
    return r.json()


def test_all_modes_return_grounded_hits(client, indexed_sample):
    for mode in MODES:
        data = _top_texts(client, indexed_sample, "Tomas swim deep water", mode)
        assert data["mode"] == mode and data["timings_ms"]["total"] >= 0
        for hit in data["hits"]:
            body = client.get(f"/api/chapters/{hit['chapter_id']}").json()["body"]
            assert body[hit["start"] : hit["end"]] == hit["text"]


def test_question_queries_need_or_semantics(client, indexed_sample):
    q = "What colour are Mara's eyes?"
    # keyword mode requires every word ("colour" never occurs), fts mode does not.
    assert _top_texts(client, indexed_sample, q, "keyword")["hits"] == []
    fts = _top_texts(client, indexed_sample, q, "fts")["hits"]
    assert any("Mara's grey eyes" in h["text"] for h in fts[:3])


def test_hybrid_reports_stage_ranks_and_rerank(client, indexed_sample):
    data = _top_texts(client, indexed_sample, "What colour are Mara's eyes?", "hybrid_rerank")
    assert data["embedder"] == "hash:384" and data["reranker"] == "lexical"
    assert data["index_coverage"]["embedded"] == data["index_coverage"]["total"] > 0
    assert {"fts", "embed_query", "vector", "rerank", "hydrate"} <= set(data["timings_ms"])
    top = data["hits"][0]
    assert "rerank" in top["ranks"] and "rrf" in top["ranks"]
    assert "eyes" in top["text"]


def test_stopword_only_query(client, indexed_sample):
    for mode in ("fts", "hybrid"):
        hits = _top_texts(client, indexed_sample, "the and of", mode)["hits"]
        assert mode == "hybrid" or hits == []


def test_vector_mode_before_indexing_returns_nothing(client, sample_novel_id):
    data = _top_texts(client, sample_novel_id, "grey eyes", "vector")
    assert data["hits"] == [] and data["index_coverage"]["embedded"] == 0


def test_hnsw_matches_exact_on_small_data(session, client, indexed_sample):
    import uuid

    embedder = get_embedder("hash")
    ensure_hnsw_index(session, embedder.name, embedder.dim)
    session.commit()
    nid = uuid.UUID(indexed_sample)
    exact = search(session, nid, "harbour office ledgers", "vector", 5, embedder, exact=True)
    approx = search(session, nid, "harbour office ledgers", "vector", 5, embedder, exact=False)
    assert [h.passage_id for h in exact.hits] == [h.passage_id for h in approx.hits]


def test_index_status_and_reindex(client, sample_novel_id, run_jobs):
    before = client.get(f"/api/novels/{sample_novel_id}/index").json()
    assert before["embedder_name"] == "hash:384" and before["coverage"]["embedded"] == 0
    run_jobs()
    after = client.get(f"/api/novels/{sample_novel_id}/index").json()
    assert after["coverage"]["embedded"] == after["coverage"]["total"]
    # Re-index is idempotent: the jobs for these chapter versions already exist.
    assert client.post(f"/api/novels/{sample_novel_id}/reindex").json()["queued_for"] == 3
    assert run_jobs() == 0
    stats = client.get("/api/jobs").json()
    assert stats["counts"] == {"done": 3}
