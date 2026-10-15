# Architecture

Status: Milestones 1–2. Sections marked *(planned)* describe later milestones.

## Components

```
React + TypeScript (Vite)  ──/api──▶  FastAPI (sync SQLAlchemy 2)  ──▶  PostgreSQL 16 + pgvector
  pages: novels, chapter editor,        api/        HTTP routes            tables: novel, chapter, revision, passage
  search, contradictions, facts,        services/   DB operations            (+ embedding), character, claim,
  characters                            retrieval/  embedders, rerankers,     evidence_span, embedding_cache, job
                                                    hybrid search, indexing
                                        jobs.py     Postgres job queue + worker thread (or `novelforge worker`)
                                        core/       pure logic (no DB): text, extraction, contradictions, evaluation
                                        bench/      corpus generator, retrieval benchmark
```

`backend/novelforge/core` has no database or web dependencies. Extraction, contradiction
detection and evaluation are plain functions over small dataclasses, so the same code runs in the
API, in the CLI evaluator (`eval-sample`, in-memory), and in unit tests. `services/` loads and
stores those dataclasses; `api/` is a thin HTTP layer.

## Data model

| Table | Purpose | Key fields |
|---|---|---|
| `novel` | A manuscript | `slug` (set for imported samples), `version` |
| `chapter` | Markdown source of one chapter | `number` (unique per novel), `body`, `story_day` (days since story day 0, nullable = unknown), `story_time_label`, `content_hash`, `version` |
| `revision` | Snapshot after every save | `(chapter_id, version)` unique, `body`, `content_hash` |
| `passage` | Paragraph-sized slice of a chapter; the search unit | `start`, `end`, `text`, generated `tsv` + GIN index, `text_hash`, `embedding`, `embedding_model` |
| `embedding_cache` | Content-addressed embeddings | `(model, text_hash)` primary key |
| `job` | Background work | unique `key`, `status`, `attempts`, `error`, `result` |
| `character` | Character sheet | `name`, `aliases` (JSONB), `attributes` (JSONB canon, e.g. `{"eye_color": "grey"}`), `version` |
| `claim` | An extracted fact (a proposal, never canon) | `subject_character_id`, `predicate`, `value`, `raw_value`, `modality`, `confidence`, `effective_day` / `time_certainty`, `extractor`, `chapter_version` |
| `evidence_span` | Where a claim came from | `chapter_id`, `chapter_version`, `start`, `end`, `quote` |

Invariants (enforced by tests, and partly by check constraints):
- `chapter.body[start:end] == evidence_span.quote` for every span of the current version.
- Every claim has `effective_day` set, or `time_certainty = 'unknown'` and no day
  (`claim_time_consistent` constraint).
- Offsets are Unicode code points (Python string indices). The frontend converts them to UTF-16
  indices (`frontend/src/spans.ts`), so emoji and other astral characters do not shift highlights.

Scene, Relationship, Location, WorldRule, TimelineEvent and PlotThread are deliberately absent
until the extraction pipeline that fills them exists (M3).

## Write path: saving a chapter

1. Client sends `PATCH /api/chapters/{id}` with the `version` it last saw.
2. Version mismatch → `409` with `current_version`; nothing is written.
3. Body is normalised (LF newlines, no trailing spaces, no leading/trailing blank lines) and hashed.
4. The UPDATE runs as `... WHERE id = :id AND version = :seen` (SQLAlchemy `version_id_col`), so a
   concurrent writer that passed step 2 at the same time also gets a `409`
   (`tests/test_concurrency.py`).
5. In the same transaction: a `revision` row, rebuilt `passage` rows, re-extracted claims for that
   chapter, and an `embed_chapter` job for the new version.

Character edits re-run extraction for every chapter of the novel, because names and aliases decide
attribution. This is cheap with the rule extractor; with an LLM extractor (M3) it becomes a queued,
idempotent job.

## Determinism and idempotency

- Sample import derives novel, chapter and character IDs with `uuid5(slug/kind/key)`. Importing an
  existing sample is a no-op (`created: false`); delete and re-import gives identical rows.
- Claim IDs are `uuid5(chapter_id | chapter_version | extractor | predicate | start | end)`; span
  and passage IDs are derived the same way. Re-running extraction on the same input replaces rows
  with identical ones.

## Extraction: `rules-v1`

Regular expressions over the chapter body, anchored on a character's name, alias, or an implied
first name (only when no other character shares it). Predicates: `eye_color`, `hair_color`,
`age`, `handedness`, `birthplace`. Each match gets a modality:

- `reported`: inside dialogue quotes (a character speaking) → confidence 0.5
- `hedged`: perception or rumour in the same clause ("seemed", "almost", "some said") → 0.4
- `asserted`: otherwise → 0.9

Effective time is the chapter's `story_day`; without one, `time_certainty = 'unknown'`.

Known limits: no pronoun resolution, no paraphrase, English only, a fixed predicate list. It is a
transparent baseline that the M3 LLM extractor will be measured against.

## Contradiction report

Computed on request from claims with confidence ≥ 0.6 (configurable per request):

- `canon_conflict`: a claim disagrees with the character sheet. Cites only the disagreeing text.
- `attribute_conflict`: claims disagree on a static attribute and the sheet says nothing. The
  suggestion picks the most frequent value (ties: the earliest).
- `age_timeline`: consecutive ages (ordered by story day) must differ by ⌊elapsed years⌋ or one
  more. Claims with unknown time are never judged.

Each finding has an explanation, severity, suggested correction, and evidence spans. Findings are
not stored yet; dismiss/resolve with persistence arrives in M4.

## Search

`websearch_to_tsquery('english', q)` over `passage.tsv`, ranked by `ts_rank_cd`. Highlights come
from `ts_headline(..., HighlightAll=true)` with private-use marker characters, so the highlighted
words are exactly what PostgreSQL matched after stemming; the markers are parsed back into offsets,
and if the text does not round-trip exactly, no highlights are returned rather than wrong ones.

## Retrieval (M2)

Five modes over the same passages, one code path (`retrieval/search.py`):

| Mode | First stage | Notes |
|---|---|---|
| `keyword` | `websearch_to_tsquery` (all words, phrases, `-exclude`) | Interactive "Exact" search. Questions rarely match: every word must appear. |
| `fts` | OR of the query's English-stemmed lexemes, `ts_rank_cd` | Lexical baseline (PostgreSQL has no BM25; cover density ranking is the stand-in). |
| `vector` | cosine distance on `passage.embedding` | Semantic baseline. |
| `hybrid` | top 50 of `fts` + top 50 of `vector`, reciprocal rank fusion (k = 60) | Default in the UI. |
| `hybrid_rerank` | hybrid top 30 re-scored by a reranker | Cross-encoder in production, lexical mock in CI. |

Each hit carries its rank in every stage (`ranks: {fts: 3, vector: 2, rrf: 1}`), shown in the UI as
"why this result", and each call reports per-stage latency.

**Embeddings.** `passage.embedding` is a dimension-less `vector` plus `embedding_model`, so several
embedders can coexist. Embedders are named by a canonical spec (`hash:384`,
`fastembed:BAAI/bge-small-en-v1.5`, `ollama:<model>`, `openai:<model>`), which is also what passages
store. `embedding_cache(model, text_hash)` makes indexing content-addressed: editing one paragraph
re-embeds one paragraph.

**Exact vs. HNSW.** Vector search defaults to an exact scan of the novel's passages (a materialised CTE
keeps the planner off the global index). A single novel is tens of thousands of passages at most, and
an approximate index filtered after the fact can silently return fewer than k matches from the
novel. A per-model partial HNSW index (`(embedding::vector(dim)) vector_cosine_ops WHERE
embedding_model = …`) is available for cross-novel scale and is compared in the load tests (M6).

**The mock embedder.** `hash` is feature hashing of stemmed words and bigrams: deterministic,
dependency-free, lexical. It keeps tests and CI reproducible and is labelled as a mock in every
benchmark table; it is not a semantic model.

## Background jobs

`jobs.py` is a small queue on PostgreSQL: unique `key` per job (enqueueing twice is a no-op),
claims with `FOR UPDATE SKIP LOCKED` (several workers never run one job twice, see
`tests/test_jobs.py`), retries with exponential backoff, `failed` after `max_attempts` with the
error kept, `skipped` when a job no longer applies (the chapter moved to a newer version), and
re-queueing of jobs left `running` by a dead worker. Jobs are enqueued in the same transaction as the
edit that needs them. The API runs one worker thread by default (`JOBS_IN_PROCESS`); `novelforge
worker` runs a separate process.

## Observability and privacy

- Every response carries `X-Request-ID`; one JSON log line per request with method, path, status
  and duration.
- Query strings and bodies are never logged, because search queries and edits contain manuscript text.
- Credentials come only from environment variables; `.env` is git-ignored; no API keys are needed in M1.

## Local database without Docker

The development machine has no container runtime, so `pgserver` (a pip package bundling
PostgreSQL 16.2 and pgvector 0.6.2) runs a private server in `./.pgdata` on a Unix socket only
(no TCP port). It is used when `DATABASE_URL` is empty. CI and Docker Compose use the
`pgvector/pgvector:pg16` image instead, so the same migrations run against a standard server.
