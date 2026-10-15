Corpus `syn-100-s7` (100 chapters, 12 labelled contradictions, 13 negatives); extractor `rules-v2`, embedder `fastembed:BAAI/bge-small-en-v1.5`, k=5.

| System | TP | FP | FN | Precision | Recall | Negatives violated | Citation P | Avg claims seen | Seconds |
|---|---|---|---|---|---|---|---|---|---|
| no-memory | 3 | 0 | 9 | 1.0 | 0.25 | 0/13 | 1.0 | 2.7 | 0.42 |
| vector-only | 8 | 0 | 4 | 1.0 | 0.6667 | 0/13 | 1.0 | 10.5 | 10.68 |
| hybrid | 7 | 0 | 5 | 1.0 | 0.5833 | 0/13 | 1.0 | 11.3 | 10.19 |
| structured | 9 | 0 | 3 | 1.0 | 0.75 | 0/13 | 0.9444 | 271 | 0.05 |

Recall by category (structured):
- abilities: 2/2 detected, 0 FP
- identity: 2/4 detected, 0 FP
- location: 2/2 detected, 0 FP
- timeline: 3/3 detected, 0 FP
- world_rules: 0/1 detected, 0 FP
