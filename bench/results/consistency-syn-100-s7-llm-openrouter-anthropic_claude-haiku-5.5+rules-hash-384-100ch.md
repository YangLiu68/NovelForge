Corpus `syn-100-s7` (100 chapters, 12 labelled contradictions, 13 negatives); extractor `llm:openrouter:anthropic/claude-haiku-5.5`, embedder `hash:384`, k=5.

| System | TP | FP | FN | Precision | Recall | Negatives violated | Citation P | Avg claims seen | Seconds |
|---|---|---|---|---|---|---|---|---|---|
| no-memory | 4 | 0 | 8 | 1.0 | 0.3333 | 0/13 | 1.0 | 9.1 | 0.49 |
| vector-only | 6 | 0 | 6 | 1.0 | 0.5 | 0/13 | 1.0 | 56.0 | 6.28 |
| hybrid | 6 | 0 | 6 | 1.0 | 0.5 | 0/13 | 1.0 | 55.7 | 8.88 |
| structured | 12 | 0 | 0 | 1.0 | 1.0 | 0/13 | 0.8621 | 906 | 0.25 |

Recall by category (structured):
- abilities: 2/2 detected, 0 FP
- identity: 4/4 detected, 0 FP
- location: 2/2 detected, 0 FP
- timeline: 3/3 detected, 0 FP
- world_rules: 1/1 detected, 0 FP
