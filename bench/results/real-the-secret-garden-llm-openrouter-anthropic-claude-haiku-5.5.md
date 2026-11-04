*The Secret Garden* (Frances Hodgson Burnett; v5 held-out book): 27 chapters, 80,312 words, 16 characters listed. Extractor `llm:openrouter:anthropic/claude-haiku-5.5`, 0.4 s, 47 claims.

Source https://www.gutenberg.org/cache/epub/113/pg113.txt (sha256 matches the labelled file).

| Claims | Correct | Modality wrong | Wrong | Unlabelled | Fact precision | Strict precision |
|---|---|---|---|---|---|---|
| overall | 33 | 4 | 10 | 0 | 0.7872 | 0.7021 |
| asserted_only | 22 | 4 | 3 | 0 | 0.8966 | 0.7586 |
| ability | 20 | 3 | 10 | 0 | 0.697 | 0.6061 |
| age | 5 | 1 | 0 | 0 | 1.0 | 0.8333 |
| birthplace | 2 | 0 | 0 | 0 | 1.0 | 1.0 |
| eye_color | 2 | 0 | 0 | 0 | 1.0 | 1.0 |
| hair_color | 1 | 0 | 0 | 0 | 1.0 | 1.0 |
| status | 3 | 0 | 0 | 0 | 1.0 | 1.0 |

Recall on 113 candidate sentences (0 unlabelled):

| Facts | Labelled | Found | Recall |
|---|---|---|---|
| all | 38 | 12 | 0.3158 |
| hair_color | 3 | 1 | 0.3333 |
| asserted | 25 | 7 | 0.28 |
| birthplace | 2 | 2 | 1.0 |
| age | 9 | 4 | 0.4444 |
| status | 10 | 3 | 0.3 |
| eye_color | 14 | 2 | 0.1429 |

Contradiction report: 0 findings, 0 real inconsistencies, 0 false alarms, 0 unlabelled.
Errors by cause: modality 4, not_stated 4, figurative 1, overstated 1, wrong_value 1, inferred 1, wrong_character 1, intention 1.
