Corpus `syn-1000-s7` (1000 chapters, 125 labelled contradictions, 148 negatives); extractor `rules-v6`, embedder `fastembed:BAAI/bge-small-en-v1.5`, k=5.

| System | TP | FP | FN | Precision | Recall | Negatives violated | Citation P | Avg claims seen | Seconds |
|---|---|---|---|---|---|---|---|---|---|
| no-memory | 35 | 0 | 90 | 1.0 | 0.28 | 0/148 | 0.9273 | 2.8 | 1.68 |
| vector-only | 73 | 0 | 52 | 1.0 | 0.584 | 0/148 | 0.7838 | 15.9 | 277.4 |
| hybrid | 64 | 2 | 61 | 0.9697 | 0.512 | 2/148 | 0.741 | 18.0 | 288.96 |
| structured | 83 | 0 | 42 | 1.0 | 0.664 | 0/148 | 0.6516 | 2806 | 0.47 |

Recall by category (structured):
- abilities: 10/10 detected, 0 FP
- identity: 30/44 detected, 0 FP
- location: 16/16 detected, 0 FP
- timeline: 27/27 detected, 0 FP
- world_rules: 0/28 detected, 0 FP
