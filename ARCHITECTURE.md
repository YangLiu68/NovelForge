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
                                       narrative/   story logic: character files, beats,
                                                    motives, plot holes, pacing, revision plan
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
| `story_audit` | Story-logic audits: the whole result (JSONB) plus the chapter versions it read, so evidence in a chapter edited since is shown as stale. |
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

- `rules-v6` (`core/extraction.py`): regular expressions anchored on character names and aliases
  for attributes, age, location, death/alive, abilities (cannot / learned / used) and explicit
  changes ("dyed her hair red"). A time phrase earlier in the sentence ("Three days later", "The
  next morning") shifts the claim's story day. Each match gets a modality: `asserted`, `hedged`
  (perception governing the fact, rumour, a condition), `reported` (inside dialogue) or
  `recalled` (memory, habit, a state in a time clause such as "ever since he was twenty").
  Deterministic, about 2 s for a 186,000-word novel.
- Attribution without a name (`core/coref.py`): "her grey eyes", "She had ... gray eyes"
  and "Brooke was a silent young man, with brown eyes" are attributed when exactly one
  character fits. Pronouns come from the character sheet (`pronouns: she/her`) or are inferred
  per chapter from the pronouns that follow a name; the nearest sentence that names a possible
  referent decides, and two candidates of the same gender, a candidate of unknown gender, a
  person noun in between ("the girl") or dialogue make it abstain. The claim records the pronoun and the
  antecedent (`details.resolved`) and is 0.1 less confident. Similes and implications ("eyes the
  colour of sea glass", "Being left-handed, ...") are left to the LLM.
- LLM (`extraction/`): a strict JSON schema (16 kinds, including world rules, events,
  foreshadowing, causal links and relationships, plus `day_offset` for "three days later").
  Long chapters are split into paragraph windows. Every returned fact is validated: unknown
  kind, unknown character, malformed value, a quote that cannot be found in the text
  (exact match, then a normalised match mapped back to exact offsets), or a literal value
  (colour, place, age, hand) that the quote does not contain gets the fact rejected with a
  reason. The last check was added after a small local model paired real sentences with
  unrelated values; it also rejects values inferred from similes, trading that recall for
  precision. Jobs are idempotent per (chapter version, model, prompt version).

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
| identity | `attribute_conflict` (two statements disagree), `canon_conflict` (text vs character sheet); an explicit change starts a new period, so "dyed her hair red" is not an inconsistency; words for one colour agree ("golden", "yellow", "blond") |
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

## Story logic: motives, plot holes, pacing

The contradiction detectors compare stated facts. `narrative/audit.py` checks the reasons behind
actions, which needs an LLM, and wraps every LLM step in checks the code applies itself:

```
per chapter   notes    what the text establishes about each character: background (incl. a
                       past life), personality, goals, wounds, situation (money, status),
                       relationships, knowledge and its source; plus the author's sheet
              beats    key actions (who, what, quote, hostile?, cost, resolves a crisis?),
                       setups, a summary, tension 1-5, reader emotions, the ending hook
per beat      motives  sub-questions, not a verdict: is it a choice that needs a reason? what
                       reason does the text give (note IDs)? does it go against the character
                       or their situation (note IDs)? The verdict is computed in code (below)
per problem   later    does a later chapter explain it? then it is a planted reveal (delayed)
whole story   plot     knowledge leaks and broken causality, tied to beat / note IDs
per crisis    rescue   a beat that resolves a crisis by someone never named in an earlier
                       chapter: the model confirms or not -> deus ex machina
per setup     payoff   does any later beat pay it off? if none -> dangling setup
whole story   pacing   from the tension curve and hooks (no LLM): flat stretches, no hook
top problems  plan     revisions (plant a setup, rewrite the motive, a setback that opens an
                       opportunity, reversal, past-life memory, special advantage, cliffhanger,
                       cost and payoff), each tied to the problems it fixes
```

The motive verdict is a rule over the model's answers, in this order: not a choice → `routine`;
a reason grounded in a cited note → `consistent`; going against the character with no grounded
reason → `contradicts`; a reason stated but not grounded → `unverified` (not counted); harming
someone with no reason → `malice_without_cause`; otherwise `unmotivated`. "Dislikes her",
"found it amusing" and the like are never a reason (a lexicon check on the reason and on the
notes cited for it), which is what "no villainy for its own sake" means in practice. The first
prompt version asked the model for the verdict directly; a 7B model then called nearly every
beat consistent and cited nothing (BENCHMARK.md section 8).

| Check (code, not model) | What happens to the model's answer |
|---|---|
| Quote must be in the chapter: exact, normalised (curly/full-width punctuation, spacing), the longest real sentence of a stitched quote, or one sentence with ≥ 0.8 character overlap | otherwise dropped; the stored span is always the author's text |
| Character must resolve to the cast (name or alias) | note dropped; a beat by an unlisted person is kept but not motive-checked |
| A cited note must exist, be shown for that beat, and not quote the beat itself | citation dropped (a note read off the act cannot be its motive) |
| A reason that is dislike or whim, or a note saying so | not a reason |
| An empty or failed answer for a beat | recorded as "no judgement", never guessed |
| A later explanation must be a later note of the same character that names the beat's target or shares words with it | ignored otherwise; if accepted, the verdict becomes `delayed` |
| A knowledge leak needs a valid beat ID | dropped; the chapter and character come from the beat, not the model |
| A rescuer named in any earlier chapter (any alias, honorifics stripped) | no deus ex machina check at all |
| A setup planted in the last chapter | not checked for a payoff (an open ending) |
| A hook must be in the last 30% of the chapter | otherwise the chapter has no hook |
| Plan targets must be known problem IDs | dropped |

Prompts are in the novel's language (Chinese or English). Runs are `story_audit` jobs, idempotent
per (novel text, model, prompt version). `replay:<llm>` answers from recorded responses
(`bench/results/llm-cache/`) and refuses any prompt it has no recording for, so a real model's
run can be shown on a machine without that model, and a changed text is never answered with an
old response. The cast is sorted by name so the same novel gives byte-identical prompts from
files and from the database. `narrative/score.py` scores a run against labelled problems, traps
and ambiguous cases (`samples/*/narrative_truth.yaml`); the author's suggestions link to the
draft assistant, so a revision still goes through plan approval and a checked draft.

## Chinese text

- Sentences end at 。！？ (a closing quote stays with them; an ellipsis inside dialogue does not
  end one); dialogue is tracked for “”, 「」 and 『』 (`core/text.py`).
- Plain-text import recognises 第一章 / 第12回 headings and treats each line as a paragraph
  (`core/plaintext.py`); chapter lengths are counted in characters.
- Tokens for the hash embedder and the lexical reranker are character bigrams.
- Full-text search indexes Chinese as bigrams encoded as ASCII tokens (`passage.search_text`,
  migration 0008): PostgreSQL's parser under the C locale (pgserver) treats Chinese characters as
  spaces, so plain bigrams would index nothing. Queries get the same encoding, so a quoted
  phrase matches adjacent bigrams; highlights are computed in Python.
- The rule extractor and the contradiction detectors are English-only; for a Chinese novel the
  story-logic audit (LLM) is the analysis.

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
`extract_chapter`, `judge_rules`, `story_audit`.

## Observability and privacy

Every response carries `X-Request-ID`; one JSON log line per request (method, path, status,
duration) and per job (kind, status, attempt, duration). Query strings, bodies and manuscript text
are never logged. Credentials come only from the environment. The default LLM and embedder are
local; sending text to a hosted model is an explicit configuration choice.

## Plain-text import and the real-prose benchmark

`core/plaintext.py` turns a typed or Project Gutenberg `.txt` into chapters (licence header and
footer stripped, table of contents skipped, hard-wrapped paragraphs joined);
`novelforge import-text` imports the result with an optional cast list. `bench/real_text.py`
uses the same path on four public-domain novels and scores claims against hand labels keyed by
content, so labels survive extractor versions; `--claims` scores a frozen version's claims.

## Local database without Docker

The development machine has no container runtime, so `pgserver` (PostgreSQL 16.2 + pgvector
0.6.2 as a pip package) runs a private server in `./.pgdata` on a Unix socket. It is used when
`DATABASE_URL` is empty; CI and Docker Compose use the `pgvector/pgvector:pg16` image.
