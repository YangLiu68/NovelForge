`load-100-s7`: 100 chapters, 124,999 words, 3,342 passages, 457 claims; embedder `hash:384`.

| Measure | Value |
|---|---|
| Import (split, extract, revisions) | 4.0 s (25.0 chapters/s) |
| Embedding index | 2.5 s (1334.7 passages/s) |
| HNSW build | 1.34 s |
| Search `keyword` p50 / p95 | 4.17 / 6.9 ms |
| Search `fts` p50 / p95 | 14.81 / 20.0 ms |
| Search `vector` p50 / p95 | 17.81 / 19.91 ms |
| Search `hybrid` p50 / p95 | 33.35 / 38.44 ms |
| Search `vector_hnsw` p50 / p95 | 16.52 / 18.33 ms |
| HNSW top-10 agreement with exact | 1.0 |
| Contradiction report (refresh) p50 | 49.87 ms |
| Character graph p50 | 144.59 ms |
| Timeline p50 | 43.28 ms |
| Chapter save (re-split, re-extract, revision) p50 / p95 | 60.21 / 69.72 ms |
| Database size | 36.4 MB |
| Peak RSS (benchmark process) | 169.5 MB |
