Corpus `syn-1000-s7` (1000 chapters, 125 labelled contradictions, 148 negatives); extractor `rules-v2`, embedder `fastembed:BAAI/bge-small-en-v1.5`, k=5.

| System | TP | FP | FN | Precision | Recall | Negatives violated | Citation P | Avg claims seen | Seconds |
|---|---|---|---|---|---|---|---|---|---|
| no-memory | 26 | 6 | 99 | 0.8125 | 0.208 | 6/148 | 1.0 | 2.5 | 2.52 |
| vector-only | 55 | 25 | 70 | 0.6875 | 0.44 | 15/148 | 0.8333 | 13.4 | 246.46 |
| hybrid | 48 | 27 | 77 | 0.64 | 0.384 | 18/148 | 0.7755 | 14.8 | 196.24 |
| structured | 65 | 15 | 60 | 0.8125 | 0.52 | 18/148 | 0.7255 | 2491 | 0.46 |

Recall by category (structured):
- abilities: 8/10 detected, 0 FP
- identity: 19/44 detected, 10 FP
- location: 16/16 detected, 5 FP
- timeline: 22/27 detected, 0 FP
- world_rules: 0/28 detected, 0 FP
