`load-100-s7`: 100 chapters, 124,999 words, 3,342 passages, 425 claims; embedder `hash:384`.

| Measure | Value |
|---|---|
| Import (split, extract, revisions) | 8.31 s (12.0 chapters/s) |
| Embedding index | 3.74 s (893.8 passages/s) |
| HNSW build | 3.13 s |
| Search `keyword` p50 / p95 | 4.41 / 6.62 ms |
| Search `fts` p50 / p95 | 19.48 / 34.13 ms |
| Search `vector` p50 / p95 | 25.48 / 45.25 ms |
| Search `hybrid` p50 / p95 | 43.99 / 62.16 ms |
| Search `vector_hnsw` p50 / p95 | 23.48 / 36.65 ms |
| HNSW top-10 agreement with exact | 1.0 |
| Contradiction report (refresh) p50 | 88.64 ms |
| Character graph p50 | 194.07 ms |
| Timeline p50 | 78.24 ms |
| Chapter save (re-split, re-extract, revision) p50 / p95 | 112.08 / 166.85 ms |
| Database size | 36.4 MB |
| Peak RSS (benchmark process) | 159.7 MB |
