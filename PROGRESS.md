# Progress log

## 2026-10-15 (later): benchmarks, failure analysis, rules-v3

All benchmarks were run for real on this machine (BENCHMARK.md, raw output in `bench/results/`).
What the runs changed:

- **Generator fix.** At 1,000 chapters the multi-year time skips made ages implausible; skips now
  scale with novel length (generator version 3, `2572c56`).
- **rules-v3** (`42317f2`). The 1,000-chapter failure analysis found four phrasings the rules
  missed or misread ("At fifty, …", "dove from the pier and swam", "dyed her hair red",
  "Three days later …"). Fixing them removed every false alarm in the contradiction benchmark
  (15 → 0) and raised rule recall from 0.784 to 0.812. The phrasings came from this generator's
  templates, so BENCHMARK.md flags the gain as corpus-specific.
- **Stricter scoring** (`6fbc369`, `38f62fd`). A finding now counts only if it cites the planted
  statement itself, matching is one-to-one, and negatives are violated only by false alarms. This
  lowered every system's recall; the tables use the strict scorer for both extractor versions.
- **Local LLM run** (qwen2.5:3b through Ollama). Its first run produced facts whose quotes were
  real but unrelated to the value ("Jorin could not swim." as evidence of a location), which
  quote verification alone accepted. Extraction now also rejects a fact whose value is not in its
  quote (`d7830ba`), and LLM benchmarks record and replay responses so validation changes can be
  re-scored without the model.
- **Provenance.** Reports record the git commit (`bc2ddf6`); results name the extractor version
  that produced them (`eb34a16`).

## 2026-10-15: Milestones 2–6

The user asked for the whole plan to be carried through autonomously, to a high standard, with
self-review. Each milestone was implemented, tested, reviewed and committed separately
(`git log`). Heavy runs (tests, browsers, benchmarks, local LLM) went through this machine's
shared resource manager.

**M2 Retrieval.** pgvector embeddings with a content-addressed cache; PostgreSQL job queue;
embedders (hash mock, fastembed bge-small, Ollama, OpenAI-compatible) and rerankers (lexical mock,
MiniLM cross-encoder); five retrieval modes with per-stage ranks and timings; the seeded
synthetic-novel generator; the retrieval benchmark.

**M3 Extraction and review.** LLM interface (mock, Anthropic SDK, Ollama); schema-validated
extraction with quote verification and windows; idempotent extraction jobs; rules-v2; review
queue with canon tables, audit log and decision memory; extraction benchmark.

**M4 Contradictions.** Dead-character, travel-time and ability detectors; the LLM world-rule
judge over retrieved passages; persisted findings with dismiss/resolve and automatic
resolution; evaluation by category, subject and evidence overlap; the consistency benchmark with
a memory ablation.

**M5 Drafting.** Plan → approve → draft → evidence-grounded check → apply/revise/discard, bounded
to at most three drafts, streamed over SSE with cancel and retry; applying is an
optimistic-locked save.

**M6 Scale and polish.** Character graph and timeline; load tests up to 1,000 chapters; one
script that regenerates every benchmark; docs and demo video script.

**Independent code review.** A fresh-eyes review of the backend found nine defects and four
minor ones (stale LLM claims after edits, facts dropped when two characters share a quote,
review decisions leaking across chapters and losing edited values, a findings-refresh race,
duplicate canon on double submit, drafting runs that could get stuck, job-queue gaps, an age
check that only compared neighbours, greedy benchmark matching). All were fixed with 16
regression tests before the benchmarks were run.

**Bugs found by tests and review along the way** (all fixed, with tests):
- switching search mode cleared the query being typed;
- a slow earlier response could overwrite a newer one on the Contradictions and Search pages;
- the quote locator stripped a leading quotation mark from unwrapped quotes;
- the generator picked a random value inside a search loop, so it could fail to find a rule;
- the API let a client choose any LLM spec (now limited to the configured model or the mock);
- a live SSE stream held a database connection for its whole duration;
- a small local model could loop until the HTTP timeout (output is now capped per call).

## 2026-10-14: Milestone 1 complete

**Environment** (details in PLAN.md): Apple M4, 16 GB, no Docker, no API keys, Python 3.12 + uv,
Node 22. PostgreSQL 16 + pgvector runs locally through the `pgserver` pip package; CI uses the
`pgvector/pgvector:pg16` container.

**Implemented**
- Backend (`backend/novelforge`): SQLAlchemy models + Alembic migration `0001`; CRUD API for
  novels, chapters, characters with optimistic locking and chapter revisions; deterministic sample
  import; passage-level PostgreSQL full-text search with exact highlight offsets; `rules-v1` fact
  extractor with modality and effective time; contradiction report (canon, attribute, age vs.
  timeline) with explanations, severities, suggestions and evidence spans; evaluator against
  labelled ground truth; CLI; request-id logging without manuscript text.
- Frontend (`frontend/src`): novel list, workspace with chapter sidebar, markdown editor (write /
  preview / source with highlighted span), revision history, conflict handling, character sheets
  with canon facts, search, contradictions, extracted facts table. Light/dark and phone widths.
- Sample (`samples/lanternfall`): three original chapters, three characters, five labelled
  contradictions (one deliberately undetectable by rules), four labelled negative cases.
- Infra: `.env.example`, `.gitignore`, Dockerfiles, `docker-compose.yml`, GitHub Actions workflow.
- Docs: README, PLAN, ARCHITECTURE, TESTING, BENCHMARK, LICENSE_NOTES, demo walkthrough.

**Acceptance criteria** (PLAN.md, M1)

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Migrations up/down on empty PostgreSQL 16 | Met | `test_migrations.py` |
| 2 | CRUD with 404/409/422 and cascades | Met | `test_api_crud.py`, e2e test 8 |
| 3 | Stale writes → 409, no change; revisions | Met | `test_api_crud.py`, `test_concurrency.py`, e2e test 5 |
| 4 | Deterministic, idempotent import | Met | `test_import.py` |
| 5 | Every claim grounded and timed | Met | `test_import.py`, check constraints |
| 6 | Search with exact highlight offsets | Met | `test_search.py`, e2e test 4 |
| 7 | 4/4 detectable seeded contradictions, 0/4 negatives flagged, known miss documented | Met | `test_report.py`, `eval-sample` |
| 8 | Playwright flows | Met | 8/8 passed |
| 9 | Local checks pass; CI defined | Met locally; **CI not yet run** (not pushed) | TESTING.md |

**Test results:** see TESTING.md (50 backend tests, 6 frontend unit tests, 8 e2e tests, all passing).

**Deviations from the original brief**
- Frontend unit tests use Node's built-in runner instead of Vitest (security advisory; see LICENSE_NOTES.md).
- Docker Compose is written but unverified locally (no container runtime).
- Only the M1 entities exist; the remaining domain tables come with M3, when something fills them.

**Remaining risks**
- The sample numbers are a smoke check on text written alongside the rules, not evidence of accuracy.
- `rules-v1` misses pronoun references, paraphrase, and any predicate outside its five.
- Character edits re-extract the whole novel synchronously. Fine at 3 chapters; at 1,000 chapters
  this must become a background job (planned with M3's job system, measured in M6).
- Citation links carry offsets and a version. After an edit, an old link may point at shifted
  text; the UI warns but does not re-anchor.
- CI and Docker Compose have not run yet.

**Next step:** Milestone 2: add `passage.embedding` (pgvector), a deterministic mock embedder plus
optional real ones, hybrid FTS + vector retrieval with reranking, and a labelled query set to
measure recall@k, citation precision, latency and cost against FTS-only and vector-only baselines.
