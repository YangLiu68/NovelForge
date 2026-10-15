Corpus `syn-1000-s7` (1000 chapters, 125 labelled contradictions, 148 negatives); extractor `rules-v2`, embedder `fastembed:BAAI/bge-small-en-v1.5`, k=5.

| System | TP | FP | FN | Precision | Recall | Negatives violated | Citation P | Avg claims seen | Seconds |
|---|---|---|---|---|---|---|---|---|---|
| no-memory | 26 | 6 | 99 | 0.8125 | 0.208 | 6/148 | 1.0 | 2.5 | 1.14 |
| vector-only | 56 | 24 | 69 | 0.7 | 0.448 | 16/148 | 0.7946 | 13.4 | 103.57 |
| hybrid | 49 | 26 | 76 | 0.6533 | 0.392 | 19/148 | 0.7282 | 14.8 | 114.06 |
| structured | 67 | 13 | 58 | 0.8375 | 0.536 | 19/148 | 0.6647 | 2491 | 0.36 |

Recall by category (structured):
- abilities: 8/10 detected, 0 FP
- identity: 21/44 detected, 8 FP
- location: 16/16 detected, 5 FP
- timeline: 22/27 detected, 0 FP
- world_rules: 0/28 detected, 0 FP
