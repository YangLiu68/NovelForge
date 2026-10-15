# NovelForge: Plan

NovelForge is a workspace for long-form fiction. It helps an author plan, draft, revise,
and keep hundreds of chapters consistent. It is not a chatbot wrapper. Every fact the
system extracts points back to an exact span of an exact chapter version, and the author
decides what becomes canon.

The portfolio differentiator is a reproducible, evidence-grounded narrative-consistency
benchmark plus an interactive character/timeline graph, not generated prose.

## Environment inspected (2026-10-14)

| Item | Finding | Consequence |
|---|---|---|
| Hardware | Apple M4, 10 cores, 16 GB RAM, ~26 GB free disk | Fine for Postgres, synthetic corpora up to 1,000 chapters, and a 7B local model. No GPU work planned |
| Python | 3.12.10 (miniforge), `uv` 0.9.2 | Backend targets Python 3.12 and is managed with `uv` |
| Node | Node 22.14, npm 10.9 | Frontend: Vite + React + TypeScript |
| Container runtime | **None** (no docker/podman/colima) | `docker-compose.yml` is written but **cannot be run locally**. Local dev/tests use `pgserver` (pip-installable PostgreSQL 16.2 + pgvector 0.6.2, verified working on this machine). CI uses the `pgvector/pgvector:pg16` service container |
| PostgreSQL | Not installed system-wide | See above |
| LLM credentials | No `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / other keys in the environment | Tests and CI use deterministic mock backends. Real providers are optional and configured by env vars |
| Local LLM | Ollama installed, `qwen2.5` model present, server not running | Optional offline real-model runs from M3 on, clearly labelled |
| Git | `$HOME` is itself a git repo | NovelForge has its own `git init` so it is not swallowed by the home repo |
| `gh` CLI | Not installed | CI workflows are written but have not run until the user pushes to GitHub |

## Global non-goals

- No chatbot UI as the product. LLM output is always parsed into structured, reviewable data.
- No silent canon overwrites. Extracted facts are proposals until a human accepts them (M3+).
- No model training or fine-tuning.
- No multi-tenant auth, billing, or public deployment. Single-author local app.
- No copyrighted third-party novels in the repo. Sample and benchmark text is original or synthetic.
- No reported benchmark numbers that were not produced by a command in this repo.

## Milestones

### M1: Workspace core, sample import, search, basic contradiction report (done 2026-10-14)

Scope
- PostgreSQL schema via Alembic: `Novel`, `Chapter`, `Character`, `Claim`, `EvidenceSpan`,
  `Revision`, plus `Passage` (paragraph-level search unit; M2 adds embeddings to it).
- REST CRUD for novels, chapters, characters. Optimistic locking (`version`) on chapter and
  character updates. Every chapter save writes a `Revision`.
- React/TypeScript UI: novel list, chapter list, markdown chapter editor with preview and a
  conflict message on stale saves, character editor, search panel, contradiction panel.
- Deterministic import of three original sample chapters (`samples/lanternfall`) with
  front-matter metadata and labelled ground truth.
- Basic search: Postgres full-text search over passages, with exact highlight offsets.
- Deterministic, rule-based fact extractor (`rules-v1`) for a small set of character attributes
  (eye colour, hair colour, age, handedness, birthplace). Hedged statements and dialogue are
  extracted with low confidence and excluded from the report by default.
- Basic contradiction report: static-attribute conflicts, age vs elapsed story time, and
  text vs character-sheet canon. Each finding has an explanation, severity, and clickable
  evidence spans that open the chapter with the span highlighted.
- Request logging with request id and latency (no chapter text in logs).

Acceptance criteria
1. `alembic upgrade head` creates the schema on an empty PostgreSQL 16 database, and
   `alembic downgrade base` removes it.
2. CRUD for novels, chapters, characters works through the API, with 404/409/422 handling
   and cascading deletes.
3. A chapter or character update with a stale `version` returns 409 and changes nothing.
   Every successful chapter save stores a `Revision`.
4. Importing the Lanternfall sample twice yields identical IDs, text hashes, claims, and spans,
   with no duplicates (deterministic and idempotent).
5. Every stored claim has at least one evidence span with `chapter.body[start:end] == quote`,
   and either an `effective_day` or `time_certainty = "unknown"`.
6. Search returns ranked passages whose highlight offsets slice the chapter body to the matched
   words.
7. The contradiction report on the sample finds all 4 seeded contradictions that the rules can
   detect and raises nothing on the 4 labelled negative cases. The fifth seeded contradiction
   (pronoun-only) is a documented known miss for M1. `novelforge eval-sample` prints the real counts.
8. Playwright e2e passes: import sample → open a contradiction → click evidence → the chapter
   view shows a highlighted span whose text equals the quote; search → click result → highlight;
   edit + save a chapter and see it persist; a stale save shows a conflict.
9. `ruff check`, `pytest`, `tsc`, frontend unit tests (Node test runner), `vite build`, and
   Playwright pass locally.
   A GitHub Actions workflow runs the same checks without secrets.

Non-goals for M1: any LLM call, embeddings, Scene/Relationship/Location/WorldRule/TimelineEvent/
PlotThread tables, background jobs, pronoun/coreference resolution, dismiss/resolve of findings,
WYSIWYG editing, multi-user editing, running Docker Compose locally (no runtime on this machine).

### M2: Hybrid retrieval and retrieval evaluation ← next

Scope: `Passage.embedding` (pgvector) with a deterministic mock embedder (hashing) for tests and
optional real embedders (Ollama, OpenAI-compatible, Voyage) by env var. Hybrid retrieval: Postgres
FTS (BM25-style ranking) + vector search fused with reciprocal rank fusion, then a reranker (mock
lexical reranker by default; optional cross-encoder/LLM reranker). Retrieval eval harness over
labelled query→span sets: recall@k, citation precision, latency p50/p95, token cost.

Acceptance criteria: the three retrieval modes (FTS-only, vector-only, hybrid) run through one
interface; the eval harness reports all metrics from real runs on the synthetic set, with the
embedder named in every report; latency is measured, not estimated; token cost is reported as 0
for mock components rather than imputed.

Non-goals: training embedders, approximate-index tuning beyond HNSW defaults.

### M3: Structured extraction pipeline with human review

Scope: LLM backend interface (mock scripted backend for tests; Anthropic/OpenAI-compatible/Ollama by
env var). Extraction of character facts, events, causal dependencies, and unresolved foreshadowing
into JSON-schema-validated output. Each fact carries evidence spans that are verified against the
source text (rejected if the quote is not found), confidence, and explicit `unknown` states.
Idempotent extraction jobs keyed by (chapter, chapter version, extractor version, prompt hash).
A review queue: proposals never overwrite canon until accepted. Adds TimelineEvent, PlotThread,
Location, Relationship, WorldRule, Scene tables.

Acceptance criteria: rerunning a job on an unchanged chapter is a no-op; malformed LLM output is
rejected and logged, not stored; accepted proposals become canon with an audit trail; extraction
quality is measured against labelled ground truth (precision/recall per fact type).

### M4: Contradiction detection

Scope: detectors for timeline, identity, location, abilities, and world rules over canon +
proposals. Each finding: explanation, evidence spans, severity, suggested correction. Findings are
persisted; dismiss/resolve with a reason; dismissed findings stay dismissed across re-runs unless the
evidence changes.

Acceptance criteria: measured precision/recall/false positives on the seeded benchmark per category;
citation accuracy (cited spans are among the labelled evidence); dismiss/resolve round-trips.

### M5: Bounded planning/drafting/critic workflow

Scope: plan → draft → critic loop with a hard iteration cap and explicit checkpoints where the author
approves or edits. Drafts are new chapter versions, never silent overwrites. Server-sent-event
streaming with cancel and retry. Canon and chapter version history are browsable.

Acceptance criteria: iteration cap enforced in tests; cancel stops generation and leaves no partial
canon writes; retry is idempotent; every applied draft has a Revision and an approval record.

### M6: Scale, evaluation, CI, documentation

Scope: synthetic 100- and 1,000-chapter corpora with seeded contradictions and negative cases; load
tests (import, extraction with mock LLM, retrieval, contradiction report) measuring latency, memory,
and cost; the full benchmark comparing no-memory, vector-only, and hybrid+structured approaches;
interactive character/timeline graph; CI hardening; demo video script.

Acceptance criteria: every number in BENCHMARK.md is produced by a committed command with a recorded
seed, hardware, and configuration; failure cases are documented next to the metrics.

## Evaluation design (shared by M1–M6)

- Ground truth lives next to the data (`samples/*/ground_truth.yaml`, later generated benchmark
  folders) and lists seeded contradictions, negative cases (things that look like contradictions but
  are not), and known misses.
- Metrics: precision, recall, false positives on negatives, citation accuracy, retrieval recall@k,
  latency, token cost.
- Systems compared (from M4/M6): no-memory (current chapter only), vector-only retrieval, and
  hybrid retrieval + structured canon.
- A result is written into BENCHMARK.md only after the command that produced it has run.

## Progress

See [PROGRESS.md](PROGRESS.md).
