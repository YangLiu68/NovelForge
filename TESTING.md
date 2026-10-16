# Testing

## Suites

| Suite | Command | Needs |
|---|---|---|
| Lint + format | `cd backend && uv run ruff check . && uv run ruff format --check .` | — |
| Backend unit + integration | `cd backend && uv run pytest` | PostgreSQL (embedded `pgserver` or `DATABASE_URL`) |
| Frontend types | `cd frontend && npm run typecheck` | — |
| Frontend unit | `cd frontend && npm test` | Node 22 |
| Frontend build | `cd frontend && npm run build` | — |
| End-to-end | `cd frontend && npm run e2e` | Playwright Chromium, uv |
| Benchmarks | `bench/run_all.sh` | ~30 min on CPU, downloads ~150 MB of models |

Tests never call a hosted model and never need an API key: the LLM is the deterministic mock,
the embedder is the hash mock. Database tests create a fresh `novelforge_test` database per
session and truncate tables before each test.

## Backend tests (164)

| File | Covers |
|---|---|
| `test_text.py` | normalisation, paragraph offsets, number words, dialogue detection, sentence bounds |
| `test_extraction.py` | every rule, aliases (case, ambiguity, implied first names), modality, traps (negation, "ten minutes late", word boundaries), effective time, deterministic IDs, rules-v3 patterns ("At fifty", chained verbs, "dyed her hair", in-chapter day offsets) |
| `test_coref.py` | pronoun and "with"-phrase attribution and every abstention (two candidates, unknown pronouns, person noun, dialogue, plural "they"), nearest-sentence rule, feature lists, ages in apposition, word sense and negation, hedge scope, time clauses, titles, sentence breaks after "Mrs.", pronoun inference, colour families |
| `test_real_text.py` | Gutenberg stripping, unwrapping, chapter split; the real-prose scorer end to end offline (labels, to-do list, precision, recall) |
| `test_contradictions.py` | attribute and canon conflicts, thresholds, ages vs elapsed days, dead characters (flashback, memory, unknown time), travel times, abilities |
| `test_api_crud.py`, `test_concurrency.py` | CRUD, 404/409/422, revisions, stale saves rejected without changes, two concurrent writers |
| `test_import.py` | deterministic and idempotent import; every claim's span slices the text to its quote; a plain-text novel imports with pronoun attribution |
| `test_search.py`, `test_retrieval.py` | highlights, phrases, scoping, edits; hash embedder; every retrieval mode returns grounded hits; OR semantics for questions; stage ranks; HNSW agrees with exact search |
| `test_jobs.py` | idempotent enqueue, success/skip/retry/fail, four concurrent workers run each job once, stale-job recovery, cache-aware embedding, stale versions skipped |
| `test_llm_extraction.py` | quote locator, windows, validation and rejection reasons, day offsets, rule-backed mock, strict schema, cost table, Anthropic request shape (structured output, fallbacks, effort) and stop reasons, Ollama JSON and streaming, cancellation, rejecting values not in their quote, record-and-replay cache (repeatable failures replayed, transport errors not) |
| `test_review.py` | review queue, accept into canon with audit, refusal to overwrite canon, explicit replace, reject, decisions surviving re-extraction, batch accept, idempotent LLM extraction jobs, scenes |
| `test_findings.py` | stored findings, dismiss needs a reason and survives edits, auto-resolve and reopen, manual resolve, uncertain preview not stored, LLM rule judge with verified quotes |
| `test_workflows.py` | plan → approve → draft → apply, critic citing both sides, bounded revisions, refusal to overwrite newer edits, new-chapter runs, discard, cancel mid-stream then retry, SSE replay, retryable failures, LLM allow-list |
| `test_graph.py` | co-occurrence graph with evidence, timeline lanes and findings |
| `test_generate.py` | byte-identical corpora per seed, every labelled span exact, category coverage, import, consistency benchmark end to end |
| `test_review_fixes.py` | regressions for the independent code review: stale LLM claims after edits, shared quotes, chapter-scoped decisions and edited values, concurrent report refreshes, preview thresholds, double accept, re-arming failed jobs, double step start and restart recovery, finalisation failures, non-adjacent ages, one-to-one benchmark matching, nulls in PATCH, case-insensitive places, length-changing lowercase, undated statements ordered by chapter around an attribute change |
| `test_report.py`, `test_migrations.py` | sample report, threshold preview, edits clearing findings, character-sheet changes, CLI evaluation in memory vs database; migrations up and down |

## Frontend unit tests (11)

`src/spans.test.ts` (code points ↔ UTF-16, highlight segments, span links),
`src/layout.test.ts` (force layout is deterministic, stays on canvas, pulls connected nodes
together, centres small graphs with room for labels) and `src/resolved.test.ts` (the review
note that explains a pronoun or sentence-subject attribution). Run with Node's built-in test
runner.

## End-to-end tests (13)

`frontend/e2e/workspace.spec.ts`, real browser, real API, real PostgreSQL, mock LLM:
import; every contradiction citation highlights its exact span; uncertain-statement preview;
exact search; hybrid search with stage ranks; editing with conflicts and history; fixing text
clears a finding; character-sheet canon; novel and chapter CRUD; review (accept, canon conflict,
reject); dismissing a finding with a reason; the draft assistant from plan to applied chapter;
the character graph and timeline with click-through to evidence.

## Latest results

Run on 2026-10-15, Apple M4 / 16 GB / macOS 15.3, Python 3.12.10, Node 22.14, embedded PostgreSQL
16.2 (pgserver), Chromium headless 140 (Playwright 1.55.1), on a machine shared with several other
jobs (timings are not benchmarks).

| Check | Result |
|---|---|
| `eval-sample` (in memory and through the database, rules-v6) | 4 TP, 0 FP, 1 FN (pronoun plus indirect phrasing), 0 / 4 negatives flagged, citation precision 1.0 |
| ruff check / ruff format --check | clean / 98 files formatted |
| pytest | 164 passed in 84.8 s (machine under load) |
| tsc | no errors |
| Node unit tests | 11 / 11 passed |
| vite build | succeeded (407 kB JS, 128 kB gzip) |
| npm audit | 0 vulnerabilities |
| Playwright | 13 passed in 37.1 s |

## Not executed

- **GitHub Actions**: the workflow (backend, frontend, e2e, compose jobs) parses but has not run,
  because the repository has not been pushed.
- **Docker Compose**: no container runtime on the development machine; CI validates and builds it.
- **Claude**: the Anthropic backend is tested against a fake client (request shape, structured
  output, fallbacks, stop reasons, cost) but has not called the real API (no key was available).
