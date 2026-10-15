Corpus `syn-40-s7` (15 chapters), extractor `llm:ollama:qwen2.5:3b`, 280.96 s.

| Predicate | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| overall | 2 | 1 | 53 | 0.6667 | 0.0364 | 0.069 |
| ability | 0 | 0 | 15 | None | 0.0 | None |
| age | 0 | 0 | 4 | None | 0.0 | None |
| birthplace | 0 | 0 | 5 | None | 0.0 | None |
| eye_color | 0 | 0 | 5 | None | 0.0 | None |
| hair_color | 2 | 0 | 5 | 1.0 | 0.2857 | 0.4444 |
| handedness | 0 | 0 | 3 | None | 0.0 | None |
| location | 0 | 1 | 16 | 0.0 | 0.0 | None |

Negative cases (hedged/dialogue/memory) kept out of `asserted`: 1 of 1 extracted claims.
Location day accuracy: {'correct': 0, 'total': 0}.
World-rule statements found: {'found': 1, 'total': 4, 'recall': 0.25}; foreshadowing set-ups: {'found': 0, 'total': 1, 'recall': 0.0}; causal links: {'found': 0, 'total': 2, 'recall': 0.0}.
LLM calls 15, tokens in/out 11591/6360, cost 0.0, rejected facts 53 {'value not in quote': 18, 'quote not found': 19, 'malformed value': 16}.
