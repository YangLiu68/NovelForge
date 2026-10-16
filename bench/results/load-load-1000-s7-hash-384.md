`load-1000-s7`: 1000 chapters, 1,250,697 words, 33,277 passages, 4,337 claims; embedder `hash:384`.

| Measure | Value |
|---|---|
| Import (split, extract, revisions) | 44.4 s (22.5 chapters/s) |
| Embedding index | 24.46 s (1360.5 passages/s) |
| HNSW build | 14.37 s |
| Search `keyword` p50 / p95 | 4.86 / 5.84 ms |
| Search `fts` p50 / p95 | 18.69 / 35.07 ms |
| Search `vector` p50 / p95 | 178.28 / 222.18 ms |
| Search `hybrid` p50 / p95 | 172.53 / 193.01 ms |
| Search `vector_hnsw` p50 / p95 | 137.64 / 151.12 ms |
| HNSW top-10 agreement with exact | 1.0 |
| Contradiction report (refresh) p50 | 774.3 ms |
| Character graph p50 | 2658.52 ms |
| Timeline p50 | 629.94 ms |
| Chapter save (re-split, re-extract, revision) p50 / p95 | 247.17 / 568.54 ms |
| Database size | 257.5 MB |
| Peak RSS (benchmark process) | 834.2 MB |
