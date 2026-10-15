Corpus `syn-100-s7` (100 chapters, 842 passages, 352 queries {'lexical': 176, 'paraphrase': 176}); embedder `fastembed:BAAI/bge-small-en-v1.5`, reranker `cross-encoder:Xenova/ms-marco-MiniLM-L-6-v2`.

| Mode | Queries | R@1 | R@3 | R@5 | R@10 | MRR@10 | nDCG@10 | P@3 | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|---|---|
| keyword | all | 0.230 | 0.236 | 0.244 | 0.250 | 0.235 | 0.208 | 0.225 | 1.01 | 2.32 |
| keyword | lexical | 0.460 | 0.472 | 0.489 | 0.500 | 0.470 | 0.417 | 0.450 |  |  |
| keyword | paraphrase | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |  |  |
| fts | all | 0.591 | 0.835 | 0.895 | 0.972 | 0.726 | 0.753 | 0.368 | 4.94 | 7.95 |
| fts | lexical | 0.625 | 0.852 | 0.909 | 0.983 | 0.752 | 0.781 | 0.386 |  |  |
| fts | paraphrase | 0.557 | 0.818 | 0.881 | 0.960 | 0.699 | 0.726 | 0.350 |  |  |
| vector | all | 0.631 | 0.858 | 0.943 | 0.977 | 0.758 | 0.790 | 0.396 | 13.61 | 23.12 |
| vector | lexical | 0.659 | 0.864 | 0.943 | 0.977 | 0.771 | 0.805 | 0.407 |  |  |
| vector | paraphrase | 0.602 | 0.852 | 0.943 | 0.977 | 0.744 | 0.775 | 0.385 |  |  |
| hybrid | all | 0.761 | 0.943 | 0.963 | 1.000 | 0.853 | 0.871 | 0.443 | 19.03 | 32.23 |
| hybrid | lexical | 0.790 | 0.955 | 0.972 | 1.000 | 0.871 | 0.893 | 0.462 |  |  |
| hybrid | paraphrase | 0.733 | 0.932 | 0.955 | 1.000 | 0.834 | 0.849 | 0.424 |  |  |
| hybrid_rerank | all | 0.903 | 0.980 | 0.980 | 1.000 | 0.943 | 0.952 | 0.498 | 179.62 | 238.43 |
| hybrid_rerank | lexical | 0.932 | 1.000 | 1.000 | 1.000 | 0.964 | 0.970 | 0.513 |  |  |
| hybrid_rerank | paraphrase | 0.875 | 0.960 | 0.960 | 1.000 | 0.922 | 0.935 | 0.483 |  |  |

Indexing: 835 passages embedded in 14.67 s, 44658 tokens (exact), cost $0 (local).
