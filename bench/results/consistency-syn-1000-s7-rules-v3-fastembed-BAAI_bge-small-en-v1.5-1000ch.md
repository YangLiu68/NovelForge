Corpus `syn-1000-s7` (1000 chapters, 125 labelled contradictions, 148 negatives); extractor `rules-v3`, embedder `fastembed:BAAI/bge-small-en-v1.5`, k=5.

| System | TP | FP | FN | Precision | Recall | Negatives violated | Citation P | Avg claims seen | Seconds |
|---|---|---|---|---|---|---|---|---|---|
| no-memory | 28 | 0 | 97 | 1.0 | 0.224 | 0/148 | 0.9565 | 2.6 | 5.47 |
| vector-only | 62 | 0 | 63 | 1.0 | 0.496 | 0/148 | 0.8293 | 14.0 | 288.41 |
| hybrid | 53 | 2 | 72 | 0.9636 | 0.424 | 2/148 | 0.789 | 15.7 | 299.44 |
| structured | 72 | 0 | 53 | 1.0 | 0.576 | 0/148 | 0.744 | 2580 | 0.79 |

Recall by category (structured):
- abilities: 10/10 detected, 0 FP
- identity: 19/44 detected, 0 FP
- location: 16/16 detected, 0 FP
- timeline: 27/27 detected, 0 FP
- world_rules: 0/28 detected, 0 FP
