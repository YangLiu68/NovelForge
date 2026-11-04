*Anne of Green Gables* (L. M. Montgomery; v4 held-out book): 38 chapters, 101,964 words, 23 characters listed. Extractor `llm:openrouter:anthropic/claude-haiku-5.5`, 0.45 s, 48 claims.

Source https://www.gutenberg.org/cache/epub/45/pg45.txt (sha256 matches the labelled file).

| Claims | Correct | Modality wrong | Wrong | Unlabelled | Fact precision | Strict precision |
|---|---|---|---|---|---|---|
| overall | 9 | 1 | 1 | 37 | 0.9091 | 0.8182 |
| asserted_only | 4 | 1 | 0 | 0 | 1.0 | 0.8 |
| ability | 1 | 0 | 0 | 7 | 1.0 | 1.0 |
| age | 1 | 0 | 1 | 12 | 0.5 | 0.5 |
| birthplace | 0 | 0 | 0 | 1 | None | None |
| eye_color | 2 | 0 | 0 | 4 | 1.0 | 1.0 |
| hair_color | 5 | 1 | 0 | 8 | 1.0 | 0.8333 |
| status | 0 | 0 | 0 | 5 | None | None |

Recall on 151 candidate sentences (0 unlabelled):

| Facts | Labelled | Found | Recall |
|---|---|---|---|
| all | 47 | 16 | 0.3404 |
| hair_color | 24 | 6 | 0.25 |
| asserted | 29 | 8 | 0.2759 |
| eye_color | 16 | 6 | 0.375 |
| birthplace | 1 | 0 | 0.0 |
| age | 6 | 4 | 0.6667 |

Contradiction report: 0 findings, 0 real inconsistencies, 0 false alarms, 0 unlabelled.
Errors by cause: modality 1, wrong_value 1.
