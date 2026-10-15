Corpus `syn-1000-s7` (1000 chapters, 8277 passages, 800 queries {'lexical': 400, 'paraphrase': 400}); embedder `fastembed:BAAI/bge-small-en-v1.5`, reranker `cross-encoder:Xenova/ms-marco-MiniLM-L-6-v2`.

| Mode | Queries | R@1 | R@3 | R@5 | R@10 | MRR@10 | nDCG@10 | P@3 | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|---|---|
| keyword | all | 0.299 | 0.302 | 0.304 | 0.309 | 0.301 | 0.202 | 0.286 | 4.44 | 6.13 |
| keyword | lexical | 0.598 | 0.605 | 0.608 | 0.618 | 0.603 | 0.405 | 0.572 |  |  |
| keyword | paraphrase | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |  |  |
| fts | all | 0.584 | 0.796 | 0.861 | 0.938 | 0.706 | 0.641 | 0.465 | 9.07 | 16.33 |
| fts | lexical | 0.598 | 0.787 | 0.853 | 0.940 | 0.711 | 0.651 | 0.480 |  |  |
| fts | paraphrase | 0.570 | 0.805 | 0.870 | 0.935 | 0.701 | 0.631 | 0.451 |  |  |
| vector | all | 0.614 | 0.843 | 0.911 | 0.965 | 0.741 | 0.673 | 0.492 | 36.96 | 49.82 |
| vector | lexical | 0.632 | 0.843 | 0.915 | 0.970 | 0.749 | 0.675 | 0.494 |  |  |
| vector | paraphrase | 0.595 | 0.843 | 0.907 | 0.960 | 0.732 | 0.671 | 0.490 |  |  |
| hybrid | all | 0.774 | 0.919 | 0.960 | 0.985 | 0.851 | 0.804 | 0.620 | 39.22 | 50.01 |
| hybrid | lexical | 0.743 | 0.927 | 0.968 | 0.990 | 0.839 | 0.798 | 0.618 |  |  |
| hybrid | paraphrase | 0.805 | 0.910 | 0.953 | 0.980 | 0.864 | 0.811 | 0.623 |  |  |
| hybrid_rerank | all | 0.909 | 0.981 | 0.999 | 0.999 | 0.946 | 0.914 | 0.725 | 353.86 | 520.45 |
| hybrid_rerank | lexical | 0.863 | 0.970 | 1.000 | 1.000 | 0.918 | 0.905 | 0.704 |  |  |
| hybrid_rerank | paraphrase | 0.955 | 0.993 | 0.998 | 0.998 | 0.974 | 0.923 | 0.745 |  |  |

Indexing: 7710 passages embedded in 125.85 s, 425736 tokens (exact), cost $0 (local).
