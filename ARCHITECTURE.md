# Architecture

## Components

```
React + TypeScript (Vite)  ──/api──▶  FastAPI (sync SQLAlchemy 2)  ──▶  PostgreSQL 16 + pgvector
 novels, chapter editor, search,       api/         HTTP routes, SSE
 contradictions, review, canon,        services/    DB operations: workspace, review, findings,
 draft assistant, graph & timeline                  rule judge, graph, extraction jobs
                                       retrieval/   embedders, rerankers, hybrid search, indexing
                                       extraction/  LLM prompt, schema, quote verification
                                       drafting/    plan → draft → critique workflow
                                       llm/         mock | Anthropic SDK | Ollama behind one interface
                                       jobs.py      PostgreSQL job queue + worker thread
                                       core/        pure logic: text, rules extractor, detectors,
                                                    evaluation (no DB, no web)
                                       bench/       corpus generator and four benchmarks
```

`core/` has no database or web dependencies: extraction, contradiction detection and
evaluation are plain functions over small dataclasses, so the same code runs in the API, in the
benchmarks (in memory) and in unit tests.

## Data model

| Table | Role |
|---|---|
| `novel`, `chapter`, `revision` | The manuscript. Chapters are markdown with `story_day` (days since day 0, null = unknown) and `version`; every save writes a revision. |
| `scene`, `passage` | Derived from chapter text: scenes (between `* * *` breaks) and paragraphs (the search unit, with `tsv` and an optional `embedding`). |
| `character`, `location` | Canon entities. Character sheets hold canon attributes; locations hold travel times to other places. |
| `claim`, `evidence_span` | Extracted facts (proposals) and the exact text they came from. |
| `world_rule`, `timeline_event`, `plot_thread`, `relationship` | Canon created only by accepting claims in review. |
| `canon_change` | Audit log of every canon change (old value, new value, source claim). |
| `review_decision` | Accept/reject decisions keyed by claim fingerprint, re-applied after re-extraction. |
| `finding` | Contradiction findings with a lifecycle (open, dismissed, resolved). |
| `workflow_run`, `workflow_step` | Drafting runs and their LLM steps. |
| `embedding_cache`, `job` | Infrastructure: content-addressed embeddings, background jobs. |

Invariants (enforced by tests and check constraints):
- `chapter.body[start:end] == evidence_span.quote` for every span of the current version.
- Every claim has an `effective_day`, or `time_certainty = 'unknown'` and no day.
- Offsets are Unicode code points; the frontend converts them to UTF-16 (`frontend/src/spans.ts`).
- Nothing becomes canon without a review action; drafts change nothing until applied.

## Write path: saving a chapter

1. `PATCH /api/chapters/{id}` carries the version the client saw; a mismatch returns 409.
2. The UPDATE runs as `... WHERE id = :id AND version = :seen` (SQLAlchemy `version_id_col`), so
   two writers that both saw version 1 cannot both succeed (`tests/test_concurrency.py`).
3. In the same transaction: a revision, rebuilt passages and scenes, re-extracted rule-based
   claims (with earlier review decisions re-applied), an `embed_chapter` job, and, when
   `LLM_EXTRACTION=true`, an `extract_chapter` job.

## Extraction

Two extractors produce the same `Claim` shape.

- `rules-v3` (`core/extraction.py`): regular expressions anchored on character names and aliases
  for attributes, age, location, death/alive, abilities (cannot / learned / used) and explicit
  changes ("dyed her hair red"). A time phrase earlier in the sentence ("Three days later", "The
  next morning") shifts the claim's story day. Each match gets a modality: `asserted`, `hedged`
  (perception, rumour), `reported` (inside dialogue) or `recalled` (memory, habit).
  Deterministic and fast; misses pronouns and indirect phrasings by design.
- LLM (`extraction/`): a strict JSON schema (16 kinds, including world rules, events,
  foreshadowing, causal links and relationships, plus `day_offset` for "three days later").
  Long chapters are split into paragraph windows. Every returned fact is validated: unknown
  kind, unknown character, malformed value, or a quote that cannot be found in the text
  (exact match, then a normalised match mapped back to exact offsets) gets the fact rejected
  with a reason. Jobs are idempotent per (chapter version, model, prompt version).

Backends (`llm/`): `mock` (deterministic; for extraction it is backed by the rule extractor so
the whole LLM path runs offline), `anthropic` (official SDK, `claude-opus-5-5`, JSON-schema
structured outputs, `fallbacks="default"` for refusals, cost from a price table), and `ollama`
(native API with schema-constrained output and a hard output cap). Every call reports tokens and
cost; unknown prices are reported as unknown, never guessed.

## Review and canon

Claims start as `proposed`. Accepting one applies it to canon: character sheets for
attributes, a location and a travel event for locations, timeline events for deaths and
abilities, world rules, plot threads, relationships. If canon already holds a different value,
the accept is refused (409) unless the reviewer explicitly replaces it. Every change is written
to `canon_change`. Decisions are stored by fingerprint (subject, predicate, value, normalised
quote) so that editing a chapter, which re-extracts its claims with new IDs, keeps earlier
decisions.

## Contradiction detection

Pure functions over claims (`core/contradictions.py`), by default only narrator assertions above
a confidence threshold, with facts from several extractors de-duplicated:

| Category | Check |
|---|---|
| identity | `attribute_conflict` (two statements disagree), `canon_conflict` (text vs character sheet); an explicit change starts a new period, so "dyed her hair red" is not an inconsistency |
| timeline | `age_timeline` (ages vs elapsed story days), `dead_character_active` (present after death) |
| location | `location_conflict` (two places closer in time than the travel time between them) |
| abilities | `ability_conflict` (a skill used after "cannot" without learning it) |
| world rules | `world_rule_violation`: hybrid retrieval of candidate passages per rule, then an LLM judge with verified quotes (`services/rule_judge.py`) |

Claims with unknown story time are never used for time-based checks; flashbacks set before a
death, memories, failed attempts at a forbidden act and dialogue are not contradictions.

Findings are stored (`finding`) with a fingerprint over kind, subject and evidence text (not
offsets). Each refresh reconciles: new findings open, dismissed ones stay dismissed (a reason is
required), open ones that are no longer detected resolve automatically, and an auto-resolved
finding that comes back reopens.

## Retrieval

Five modes over the same passages (`retrieval/search.py`): `keyword` (web-search syntax, all
words), `fts` (OR of stemmed lexemes ranked with `ts_rank_cd`), `vector` (cosine on
`passage.embedding`), `hybrid` (reciprocal rank fusion of fts and vector, k = 60) and
`hybrid_rerank` (cross-encoder over the top 30). Every hit reports its rank in each stage
("why this result"), and every call reports per-stage latency. Embeddings are named by a
canonical spec (`hash:384`, `fastembed:BAAI/bge-small-en-v1.5`, ...), cached by text hash, and
searched exactly per novel by default; a per-model partial HNSW index is available and its
agreement with exact search is measured in the load test.

## Drafting workflow

```
planning → awaiting_plan_approval →(approve)→ drafting → critiquing → awaiting_decision
                                                   ▲                          │
                                                   └──(revise, ≤ max_iterations ≤ 3)
awaiting_decision →(apply)→ applied   (optimistic-locked save; 409 if the chapter changed)
                  →(discard)→ discarded
any LLM step → <step>_cancelled / <step>_failed →(retry)→ new attempt of the same step
```

Steps stream over server-sent events from an in-process stream; partial output is also saved, so
a reconnecting client sees what was produced. Cancelling closes the model stream and never
promotes partial output. The critic extracts facts from the draft and runs the same detectors
against every other chapter, the character sheets and travel times, and returns each issue with
the draft quote and the evidence it contradicts; a revision prompt carries those issues.

## Graph and timeline

`services/graph.py`: characters co-occurring in the same paragraph (weighted, with example
paragraphs) plus accepted relationships; and per-character lanes of dated, asserted,
non-rejected claims with open findings linking their evidence. The frontend lays the graph out
with a deterministic force-directed algorithm (`frontend/src/layout.ts`) and draws the timeline
by chapter order or by story day.

## Jobs

`jobs.py`: unique key per job (enqueueing twice is a no-op), claims with `FOR UPDATE SKIP
LOCKED`, retries with exponential backoff, `failed` with the error after `max_attempts`,
`skipped` when the job no longer applies, re-queueing of jobs left `running` by a dead worker.
Jobs are enqueued in the transaction that needs them. Kinds: `embed_chapter`,
`extract_chapter`, `judge_rules`.

## Observability and privacy

Every response carries `X-Request-ID`; one JSON log line per request (method, path, status,
duration) and per job (kind, status, attempt, duration). Query strings, bodies and manuscript text
are never logged. Credentials come only from the environment. The default LLM and embedder are
local; sending text to a hosted model is an explicit configuration choice.

## Local database without Docker

The development machine has no container runtime, so `pgserver` (PostgreSQL 16.2 + pgvector
0.6.2 as a pip package) runs a private server in `./.pgdata` on a Unix socket. It is used when
`DATABASE_URL` is empty; CI and Docker Compose use the `pgvector/pgvector:pg16` image.
