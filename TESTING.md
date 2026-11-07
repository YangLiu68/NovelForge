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

## Backend tests (291)

| File | Covers |
|---|---|
| `test_text.py` | normalisation, paragraph offsets, number words, dialogue detection, sentence bounds; Chinese sentences, 「」 dialogue, bigram tokens, language detection, 第一章 headings |
| `test_extraction.py` | every rule, aliases (case, ambiguity, implied first names), modality, traps (negation, "ten minutes late", word boundaries), effective time, deterministic IDs, rules-v3 patterns ("At fifty", chained verbs, "dyed her hair", in-chapter day offsets) |
| `test_extraction_zh.py` | Chinese numerals (ranges refused); every predicate next to a name; one subject across clauses; look-alikes (another person's eyes or hair, 七八岁, a birthday, 红了眼睛, 差点冻死, 死了丈夫, 她过世的母亲, intention, generic places); modality (dialogue, perception and rumour scope, conditions, dreams, 那年, an age as a time adverbial, 像从前一样); pronouns only when unambiguous (gender, previous sentence across a paragraph, chains, a person noun in between); dyeing as a change; presence; Chinese finding wording; the v2 and v3 phrasings; the dev sample's scores |
| `test_coref.py` | pronoun and "with"-phrase attribution and every abstention (two candidates, unknown pronouns, person noun, dialogue, plural "they"), nearest-sentence rule, feature lists, ages in apposition, word sense and negation, hedge scope, time clauses, titles, sentence breaks after "Mrs.", pronoun inference, colour families |
| `test_real_text.py` | Gutenberg stripping, unwrapping, chapter split; the real-prose scorer end to end offline (labels, to-do list, precision, recall) |
| `test_contradictions.py` | attribute and canon conflicts, thresholds, ages vs elapsed days, dead characters (flashback, memory, unknown time), travel times, abilities; a more detailed birthplace agreeing with the sheet; a remembered lesson clearing (never creating) an ability conflict; practice in the lesson chapter |
| `test_api_crud.py`, `test_concurrency.py` | CRUD, 404/409/422, revisions, stale saves rejected without changes, two concurrent writers |
| `test_import.py` | deterministic and idempotent import; every claim's span slices the text to its quote; a plain-text novel imports with pronoun attribution |
| `test_search.py`, `test_retrieval.py` | highlights, phrases, scoping, edits; Chinese words, phrases and OR queries with highlights; hash embedder; every retrieval mode returns grounded hits; OR semantics for questions; stage ranks; HNSW agrees with exact search |
| `test_jobs.py` | idempotent enqueue, success/skip/retry/fail, four concurrent workers run each job once, stale-job recovery, cache-aware embedding, stale versions skipped |
| `test_llm_extraction.py` | quote locator, windows, validation and rejection reasons, day offsets, rule-backed mock, strict schema, cost table, Anthropic request shape (structured output, fallbacks, effort) and stop reasons, Ollama JSON and streaming, OpenRouter request shape (strict schema, effort, provider routing), SSE streaming, billed or table cost and error mapping, cancellation, rejecting values not in their quote, record-and-replay cache (repeatable failures replayed, transport errors not); the Chinese prompt and schema, colour words and numerals normalised and grounded in the quote, `presence` only for Chinese, the mock reading the Chinese prompt, character windows, an explained hair change marked |
| `test_review.py` | review queue, accept into canon with audit, refusal to overwrite canon, explicit replace, reject, decisions surviving re-extraction, batch accept, idempotent LLM extraction jobs, scenes |
| `test_findings.py` | a failed attempt is not a world-rule violation, stored findings, dismiss needs a reason and survives edits, auto-resolve and reopen, manual resolve, uncertain preview not stored, LLM rule judge with verified quotes |
| `test_workflows.py` | plan → approve → draft → apply, critic citing both sides, bounded revisions, refusal to overwrite newer edits, new-chapter runs, discard, cancel mid-stream then retry, SSE replay, retryable failures, LLM allow-list |
| `test_graph.py` | co-occurrence graph with evidence, timeline lanes and findings |
| `test_generate.py` | byte-identical corpora per seed, every labelled span exact, category coverage, import, consistency benchmark end to end |
| `test_review_fixes.py` | regressions for the independent code review: stale LLM claims after edits, shared quotes, chapter-scoped decisions and edited values, concurrent report refreshes, preview thresholds, double accept, re-arming failed jobs, double step start and restart recovery, finalisation failures, non-adjacent ages, one-to-one benchmark matching, nulls in PATCH, case-insensitive places, length-changing lowercase, undated statements ordered by chapter around an attribute change |
| `test_story_audit.py` | story-logic audit on a scripted model: one finding per scene and per beat (merges), reveals not judged as acts, payoff in other words, quiet endings as cliffhanger suggestions, later notes naming a third person, long files keeping the notes about the beat, harm with no reason as villainy, every story sample's labels quoting their chapters; quotes located (exact, normalised, stitched, sentence), cast resolution, circular motives dropped, verdict downgrades (unverified, unmotivated), skipped beats asked again, later reveals (and unrelated ones refused), plot references, hooks at the chapter end, pacing, plan targets, failures recorded, the scorer, the Chinese samples' labels |
| `test_story_api.py` | the cost estimate before a run (free models, unknown prices, windows, the allow-list), audits as jobs, reuse for unchanged text, stale chapters after an edit, the LLM allow-list, a recorded run replayed through the API with the same prompts as from files, replay refusing changed text |
| `test_report.py`, `test_migrations.py` | sample report, threshold preview, edits clearing findings, character-sheet changes, CLI evaluation in memory vs database, preferring the LLM's claims in chapters it read; migrations up and down |

## Frontend unit tests (17)

`src/spans.test.ts` (code points ↔ UTF-16, highlight segments, span links),
`src/layout.test.ts` (force layout is deterministic, stays on canvas, pulls connected nodes
together, centres small graphs with room for labels), `src/resolved.test.ts` (the review
note that explains a pronoun or sentence-subject attribution) and `src/story.test.ts` (language
detection, labels, the tension curve, beats per character, a revision suggestion turned into a
draft-assistant goal). Run with Node's built-in test
runner.

## End-to-end tests (14)

`frontend/e2e/workspace.spec.ts`, real browser, real API, real PostgreSQL, mock LLM:
import; every contradiction citation highlights its exact span; uncertain-statement preview;
exact search; hybrid search with stage ranks; editing with conflicts and history; fixing text
clears a finding; character-sheet canon; novel and chapter CRUD; review (accept, canon conflict,
reject); dismissing a finding with a reason; the draft assistant from plan to applied chapter;
the character graph and timeline with click-through to evidence; the story-logic page replaying
the recorded qwen2.5:7b audit of 雪夜当铺 (issue count, evidence opening its exact span, motives
and pacing tabs, a suggestion opening the draft assistant with its goal).

## Latest results

Run on 2026-11-03, Apple M4 / 16 GB / macOS 15.3, Python 3.12.10, Node 22.14, embedded PostgreSQL
16.2 (pgserver), Chromium headless 140 (Playwright 1.55.1), on a machine shared with several other
jobs (timings are not benchmarks).

| Check | Result |
|---|---|
| `audit-story --replay` on the three Chinese samples (qwen2.5:7b) | dev 4/6 problems, 1/8 traps; held-out 2/6, 1/4; revised 0/14 traps |
| `audit-story qingshi-du --llm openrouter:anthropic/claude-opus-5.5` (live, once) | 3/6 problems, 0/4 traps, 11 issues on no label; 68 calls, $1.24 |
| `eval-sample` / `eval-facts` on the Chinese samples (rules-zh-v3) | dev 7/7, 0 false; held out (blind, one version each) v1 3/9, v2 5/9, v3 5/9, 7/9 with 2, 2, 3, 1 false findings; claim precision 0.92 to 1.0 |
| the same with `--llm openrouter:anthropic/claude-opus-5.5` (live, then `--replay`) | 驼铃过碛 blind: 9/9, 1 false; claims P 0.98, R 0.857 ($0.25). After the lesson fix, all five samples 0 false findings (seen) |
| OpenRouter smoke test (Claude Haiku 5.5, live) | structured JSON, streaming and billed cost returned |
| `audit-story qingya-wenjian` (held-out, live, once per model) | Opus 5.5 4/6, 1/6 traps (0/6 by hand), $1.49; Haiku 5.5 3/6, 0/6, $0.049; checks-v5 re-score 5/6 and 4/6 |
| `bench-extraction syn-100-s7 --extractor openrouter:anthropic/claude-haiku-5.5` | P 0.982, R 0.961, $0.079 |
| `bench-consistency syn-100-s7 ... --with-rules` (Haiku) | 12/12, 0 false findings (Haiku alone 10/12, rules 9/12) |
| `bench-real the-secret-garden` / `anne-of-green-gables --llm openrouter:anthropic/claude-haiku-5.5` | recall 0.316 / 0.426 (rules 0.184 / 0.213), fact precision 0.79 / 0.93, every claim hand-labelled; 1500-word windows 0.474 / 0.340 |
| `eval-sample` (in memory and through the database, rules-v6) | 4 TP, 0 FP, 1 FN (pronoun plus indirect phrasing), 0 / 4 negatives flagged, citation precision 1.0 |
| ruff check / ruff format --check | clean / 116 files formatted |
| pytest | 291 passed |
| tsc | no errors |
| Node unit tests | 17 / 17 passed |
| vite build | succeeded (425 kB JS, 134 kB gzip) |
| npm audit | 0 vulnerabilities |
| Playwright | 14 passed in 21.5 s (after the story-page estimate and Claude replay option) |

## Continuous integration and deployment

- **GitHub Actions** (`.github/workflows/ci.yml`, public repository
  [YangLiu68/NovelForge](https://github.com/YangLiu68/NovelForge)): backend (ruff, pytest against
  PostgreSQL 16 + pgvector, sample evaluation in memory and through the database, a retrieval
  smoke test), frontend (typecheck, unit tests, build), Playwright end to end, and Docker
  Compose. First green run 2026-11-04 (`7d302e2`): all four jobs passed, Playwright 14 passed in
  24.5 s. The first run failed only in the e2e job: `ubuntu-latest` had become Ubuntu 26.04,
  for which Playwright 1.55 has no browsers, so the runners are pinned to `ubuntu-24.04`.
- **Docker Compose**: the CI job builds both images, starts the stack and runs
  `scripts/compose-smoke.sh` (API health, migrations, the English sample's 4 and the Chinese
  sample's 7 planted findings with Chinese explanations, the frontend and its `/api` proxy). The
  same script passed on the development Mac (Colima 2 CPU / 2 GiB VM, Docker Compose 5.7.0,
  2026-11-04): images built, three containers healthy, every check passed.

## Not executed

- **Anthropic's own API**: the Anthropic backend has run for real only against an
  Anthropic-compatible endpoint (OpenRouter's Messages API, through `ANTHROPIC_BASE_URL`):
  structured output, effort, streaming and an extraction run (P 0.90, R 0.871 on 雾港信札). Its
  server-side refusal fallbacks, which only Anthropic's API offers, are sent only when the
  client points there and have not been exercised (no Anthropic key).
- **LLM runs at full scale**: the 1,000-chapter corpus and two of the four real books have not
  been run with an LLM (cost).
