`load-100-s7`: 100 chapters, 124,999 words, 3,342 passages, 433 claims; embedder `hash:384`.

| Measure | Value |
|---|---|
| Import (split, extract, revisions) | 4.44 s (22.5 chapters/s) |
| Embedding index | 1.81 s (1841.4 passages/s) |
| HNSW build | 0.85 s |
| Search `keyword` p50 / p95 | 1.75 / 3.57 ms |
| Search `fts` p50 / p95 | 5.33 / 7.0 ms |
| Search `vector` p50 / p95 | 12.5 / 16.46 ms |
| Search `hybrid` p50 / p95 | 17.25 / 23.14 ms |
| Search `vector_hnsw` p50 / p95 | 11.99 / 15.74 ms |
| HNSW top-10 agreement with exact | 1.0 |
| Contradiction report (refresh) p50 | 36.72 ms |
| Character graph p50 | 102.41 ms |
| Timeline p50 | 36.94 ms |
| Chapter save (re-split, re-extract, revision) p50 / p95 | 52.82 / 70.17 ms |
| Database size | 35.2 MB |
| Peak RSS (benchmark process) | 167.9 MB |
