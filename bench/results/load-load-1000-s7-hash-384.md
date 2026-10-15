`load-1000-s7`: 1000 chapters, 1,250,697 words, 33,277 passages, 4,111 claims; embedder `hash:384`.

| Measure | Value |
|---|---|
| Import (split, extract, revisions) | 59.7 s (16.7 chapters/s) |
| Embedding index | 17.85 s (1864.5 passages/s) |
| HNSW build | 10.08 s |
| Search `keyword` p50 / p95 | 3.8 / 4.87 ms |
| Search `fts` p50 / p95 | 13.56 / 30.1 ms |
| Search `vector` p50 / p95 | 126.73 / 143.39 ms |
| Search `hybrid` p50 / p95 | 135.63 / 159.12 ms |
| Search `vector_hnsw` p50 / p95 | 100.93 / 123.31 ms |
| HNSW top-10 agreement with exact | 1.0 |
| Contradiction report (refresh) p50 | 523.8 ms |
| Character graph p50 | 2037.2 ms |
| Timeline p50 | 448.67 ms |
| Chapter save (re-split, re-extract, revision) p50 / p95 | 213.14 / 327.58 ms |
| Database size | 257.3 MB |
| Peak RSS (benchmark process) | 837.2 MB |
