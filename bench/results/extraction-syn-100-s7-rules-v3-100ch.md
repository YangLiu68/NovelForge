Corpus `syn-100-s7` (100 chapters), extractor `rules-v3`, 0.32 s.

| Predicate | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| overall | 226 | 1 | 57 | 0.9956 | 0.7986 | 0.8863 |
| ability | 28 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| age | 32 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| birthplace | 14 | 0 | 13 | 1.0 | 0.5185 | 0.6829 |
| eye_color | 18 | 0 | 13 | 1.0 | 0.5806 | 0.7347 |
| hair_color | 17 | 1 | 6 | 0.9444 | 0.7391 | 0.8293 |
| handedness | 8 | 0 | 25 | 1.0 | 0.2424 | 0.3902 |
| location | 105 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| status | 4 | 0 | 0 | 1.0 | 1.0 | 1.0 |

Negative cases (hedged/dialogue/memory) kept out of `asserted`: 5 of 5 extracted claims.
Location day accuracy: {'correct': 105, 'total': 105}.
World-rule statements found: {'found': 0, 'total': 4, 'recall': 0.0}; foreshadowing set-ups: {'found': 0, 'total': 14, 'recall': 0.0}; causal links: {'found': 0, 'total': 8, 'recall': 0.0}.
LLM calls 0, tokens in/out 0/0, cost 0.0, rejected facts 0 {}.
