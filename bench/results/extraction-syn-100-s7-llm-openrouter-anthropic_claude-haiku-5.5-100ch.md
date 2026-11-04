Corpus `syn-100-s7` (100 chapters), extractor `llm:openrouter:anthropic/claude-haiku-5.5`, 0.06 s.

| Predicate | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| overall | 273 | 5 | 11 | 0.982 | 0.9613 | 0.9715 |
| ability | 28 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| age | 32 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| birthplace | 27 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| eye_color | 23 | 0 | 8 | 1.0 | 0.7419 | 0.8519 |
| hair_color | 23 | 0 | 1 | 1.0 | 0.9583 | 0.9787 |
| handedness | 33 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| location | 103 | 5 | 2 | 0.9537 | 0.981 | 0.9671 |
| status | 4 | 0 | 0 | 1.0 | 1.0 | 1.0 |

Negative cases (hedged/dialogue/memory) kept out of `asserted`: 5 of 5 extracted claims.
Location day accuracy: {'correct': 103, 'total': 103}.
World-rule statements found: {'found': 4, 'total': 4, 'recall': 1.0}; foreshadowing set-ups: {'found': 14, 'total': 14, 'recall': 1.0}; causal links: {'found': 8, 'total': 8, 'recall': 1.0}.
LLM calls 100, tokens in/out 197699/118242, cost 0.07889090000000003, rejected facts 8 {'malformed value': 8}.
