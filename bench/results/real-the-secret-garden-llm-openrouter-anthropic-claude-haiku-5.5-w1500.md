*The Secret Garden* (Frances Hodgson Burnett; v5 held-out book): 27 chapters, 80,312 words, 16 characters listed. Extractor `llm:openrouter:anthropic/claude-haiku-5.5`, 0.36 s, 59 claims.

Source https://www.gutenberg.org/cache/epub/113/pg113.txt (sha256 matches the labelled file).

| Claims | Correct | Modality wrong | Wrong | Unlabelled | Fact precision | Strict precision |
|---|---|---|---|---|---|---|
| overall | 46 | 5 | 8 | 0 | 0.8644 | 0.7797 |
| asserted_only | 24 | 3 | 4 | 0 | 0.871 | 0.7742 |
| ability | 22 | 2 | 7 | 0 | 0.7742 | 0.7097 |
| age | 9 | 2 | 0 | 0 | 1.0 | 0.8182 |
| birthplace | 3 | 0 | 1 | 0 | 0.75 | 0.75 |
| eye_color | 6 | 1 | 0 | 0 | 1.0 | 0.8571 |
| hair_color | 1 | 0 | 0 | 0 | 1.0 | 1.0 |
| status | 5 | 0 | 0 | 0 | 1.0 | 1.0 |

Recall on 113 candidate sentences (0 unlabelled):

| Facts | Labelled | Found | Recall |
|---|---|---|---|
| all | 38 | 18 | 0.4737 |
| hair_color | 3 | 1 | 0.3333 |
| asserted | 25 | 12 | 0.48 |
| birthplace | 2 | 2 | 1.0 |
| age | 9 | 6 | 0.6667 |
| status | 10 | 3 | 0.3 |
| eye_color | 14 | 6 | 0.4286 |

Contradiction report: 0 findings, 0 real inconsistencies, 0 false alarms, 0 unlabelled.
Errors by cause: modality 5, not_stated 3, inferred 2, intention 1, overstated 1, figurative 1.
