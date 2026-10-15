Corpus `syn-100-s7` (100 chapters, 842 passages, 352 queries {'lexical': 176, 'paraphrase': 176}); embedder `fastembed:BAAI/bge-small-en-v1.5`, reranker `cross-encoder:Xenova/ms-marco-MiniLM-L-6-v2`.

| Mode | Queries | R@1 | R@3 | R@5 | R@10 | MRR@10 | nDCG@10 | P@3 | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|---|---|
| keyword | all | 0.230 | 0.236 | 0.244 | 0.250 | 0.235 | 0.210 | 0.225 | 1.23 | 3.65 |
| keyword | lexical | 0.460 | 0.472 | 0.489 | 0.500 | 0.470 | 0.420 | 0.450 |  |  |
| keyword | paraphrase | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |  |  |
| fts | all | 0.588 | 0.835 | 0.895 | 0.972 | 0.723 | 0.753 | 0.361 | 3.5 | 6.05 |
| fts | lexical | 0.619 | 0.852 | 0.909 | 0.983 | 0.748 | 0.780 | 0.379 |  |  |
| fts | paraphrase | 0.557 | 0.818 | 0.881 | 0.960 | 0.698 | 0.725 | 0.343 |  |  |
| vector | all | 0.599 | 0.858 | 0.943 | 0.977 | 0.742 | 0.779 | 0.385 | 19.45 | 41.96 |
| vector | lexical | 0.625 | 0.864 | 0.943 | 0.977 | 0.754 | 0.794 | 0.396 |  |  |
| vector | paraphrase | 0.574 | 0.852 | 0.943 | 0.977 | 0.730 | 0.764 | 0.373 |  |  |
| hybrid | all | 0.742 | 0.943 | 0.963 | 1.000 | 0.842 | 0.865 | 0.433 | 19.8 | 34.62 |
| hybrid | lexical | 0.773 | 0.955 | 0.972 | 1.000 | 0.862 | 0.888 | 0.453 |  |  |
| hybrid | paraphrase | 0.710 | 0.932 | 0.955 | 1.000 | 0.823 | 0.841 | 0.413 |  |  |
| hybrid_rerank | all | 0.881 | 0.980 | 0.980 | 1.000 | 0.931 | 0.944 | 0.487 | 235.66 | 326.34 |
| hybrid_rerank | lexical | 0.915 | 1.000 | 1.000 | 1.000 | 0.956 | 0.963 | 0.502 |  |  |
| hybrid_rerank | paraphrase | 0.847 | 0.960 | 0.960 | 1.000 | 0.907 | 0.924 | 0.472 |  |  |

Indexing: 835 passages embedded in 17.72 s, 44658 tokens (exact), cost $0 (local).
