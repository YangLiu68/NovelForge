*Anne of Green Gables* (L. M. Montgomery; v4 held-out book): 38 chapters, 101,964 words, 23 characters listed. Extractor `llm:openrouter:anthropic/claude-haiku-5.5`, 0.27 s, 46 claims.

Source https://www.gutenberg.org/cache/epub/45/pg45.txt (sha256 matches the labelled file).

| Claims | Correct | Modality wrong | Wrong | Unlabelled | Fact precision | Strict precision |
|---|---|---|---|---|---|---|
| overall | 41 | 2 | 3 | 0 | 0.9348 | 0.8913 |
| asserted_only | 17 | 2 | 0 | 0 | 1.0 | 0.8947 |
| ability | 8 | 0 | 1 | 0 | 0.8889 | 0.8889 |
| age | 10 | 2 | 1 | 0 | 0.9231 | 0.7692 |
| birthplace | 1 | 0 | 0 | 0 | 1.0 | 1.0 |
| eye_color | 7 | 0 | 0 | 0 | 1.0 | 1.0 |
| hair_color | 13 | 0 | 0 | 0 | 1.0 | 1.0 |
| status | 2 | 0 | 1 | 0 | 0.6667 | 0.6667 |

Recall on 151 candidate sentences (0 unlabelled):

| Facts | Labelled | Found | Recall |
|---|---|---|---|
| all | 47 | 20 | 0.4255 |
| hair_color | 24 | 8 | 0.3333 |
| asserted | 29 | 13 | 0.4483 |
| eye_color | 16 | 7 | 0.4375 |
| birthplace | 1 | 0 | 0.0 |
| age | 6 | 5 | 0.8333 |

Contradiction report: 0 findings, 0 real inconsistencies, 0 false alarms, 0 unlabelled.
Errors by cause: modality 2, word_sense 1, wrong_value 1, condition 1.
