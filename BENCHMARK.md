# Benchmark

Rule for this file: a number appears here only after the command that produced it has run, with
the command, date and configuration next to it.

## Current state (Milestone 1)

There is **no benchmark yet**. There is one small smoke check on the three-chapter sample.

### Smoke check: Lanternfall sample, `rules-v1`

Command: `cd backend && uv run novelforge eval-sample` (in-memory) and `... eval-sample --db`
(through PostgreSQL and the API code path). Both gave identical results.
Run: 2026-10-14, Apple M4 / 16 GB, macOS 15.3, Python 3.12.10, PostgreSQL 16.2 (pgserver).

| Metric | Value |
|---|---|
| Labelled contradictions | 5 (4 detectable by rules, 1 needs pronoun resolution) |
| Labelled negative cases | 4 |
| Findings | 4 |
| True positives / false positives / false negatives | 4 / 0 / 1 |
| Precision | 1.0 |
| Recall (all labelled) | 0.8 |
| Recall (rule-detectable) | 1.0 |
| Negative cases wrongly flagged | 0 / 4 |
| Citation precision (cited spans overlapping labelled evidence) | 1.0 (7/7) |
| Citation recall (labelled spans covered) | 1.0 (7/7) |
| Missed | GT5: Mara's hair colour change, referenced only by "Her hair" |

**How to read this:** the sample text and the extraction rules were written together, so these
numbers show the pipeline is wired correctly end to end. They say nothing about accuracy on
unseen prose. Treat them as a regression check, not a result.

Matching rules (`backend/novelforge/core/evaluation.py`): a finding matches a labelled
contradiction when kind, subject and predicate agree; a cited span is correct when it overlaps a
labelled evidence span in the same chapter; a negative case is violated when any finding has its
subject and predicate.

## Planned benchmark (Milestones 2, 4, 6)

- **Data:** synthetic novels generated from a seeded world model (characters, timeline, places,
  rules), rendered to prose with templates and optionally an LLM paraphrase pass. Contradictions
  are injected at known spans; negative cases (hedges, dialogue, unreliable narrators, legitimate
  time skips, aliases, name collisions) are injected deliberately. Ground truth is written by the
  generator, not by hand, and the seed is recorded.
- **Sizes:** 3 (sample), 100 and 1,000 chapters.
- **Systems compared:** no-memory (current chapter only), vector-only retrieval, and hybrid
  retrieval + structured canon. Rule extractor vs. LLM extractor as an ablation.
- **Metrics:** precision, recall, false positives on negatives, citation precision/recall,
  retrieval recall@k, latency (p50/p95), peak memory, and token cost (0 for mock components,
  never imputed).
- **Reporting:** every table names the hardware, model or mock, seed, commit, and command, and
  lists failure cases next to the metrics.
