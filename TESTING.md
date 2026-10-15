# Testing

## Suites

| Suite | Command | Needs | Covers |
|---|---|---|---|
| Lint | `cd backend && uv run ruff check .` | — | pyflakes, import order, bugbear, pyupgrade, simplify |
| Backend unit + integration | `cd backend && uv run pytest` | PostgreSQL (embedded or `DATABASE_URL`) | see below |
| Sample evaluation | `cd backend && uv run novelforge eval-sample [--db]` | `--db` needs PostgreSQL | contradiction report vs. labelled ground truth |
| Frontend types | `cd frontend && npm run typecheck` | — | `tsc` strict mode, app + e2e code |
| Frontend unit | `cd frontend && npm test` | Node 22 | code-point ↔ UTF-16 offsets, highlight segmentation, span links |
| Frontend build | `cd frontend && npm run build` | — | production bundle |
| End-to-end | `cd frontend && npm run e2e` | Playwright Chromium (`npx playwright install chromium`), uv | real browser against a real API and database |

### Backend tests (50)

- `test_text.py`: body normalisation, paragraph offsets, number words, dialogue detection, sentence bounds.
- `test_extraction.py`: every rule, alias handling (case, ambiguity, explicit vs. implied first name),
  modality (hedged, reported, hedge confined to its clause), traps ("ten minutes late", "Marabel",
  negation, pronouns), effective time vs. unknown, deterministic version-scoped claim IDs.
- `test_contradictions.py`: static conflicts, majority suggestion, canon conflicts, confidence
  threshold, age vs. elapsed days (time skip, birthday, decrease, unknown time).
- `test_api_crud.py`: CRUD for novels/chapters/characters, 404/409/422, revisions, no-op saves,
  stale saves rejected without changes, cascading deletes.
- `test_concurrency.py`: two sessions both read version 1; the second write gets a conflict.
- `test_import.py`: import → delete → import gives identical IDs, hashes, claims, spans, passages;
  second import is a no-op; every claim's span slices the chapter body to its quote; time fields
  are consistent.
- `test_search.py`: highlight offsets slice the body to the stemmed match, phrase queries, ranking
  order, no-match and stop-word queries, per-novel scoping, edits reflected immediately.
- `test_report.py`: the sample report finds the four seeded contradictions; evidence offsets are
  exact; lowering the threshold surfaces the hedged/dialogue cases; fixing the text clears a
  finding; character-sheet edits re-extract; DB and in-memory evaluations agree.
- `test_migrations.py`: `upgrade head` then `downgrade base` on an empty database.

Database handling: tests use `TEST_DATABASE_URL` or `DATABASE_URL` when set, otherwise the
embedded pgserver. A fresh `novelforge_test` database is created per session and tables are
truncated before each test.

### End-to-end tests (8)

`frontend/e2e/workspace.spec.ts`. Playwright starts `novelforge e2e-server` (drops and recreates a
`novelforge_e2e` database, migrates, serves on port 18765) and a Vite dev server on 15199. Ports can
be changed with `E2E_API_PORT` / `E2E_WEB_PORT`.

1. Import the sample from the home page.
2. Every contradiction citation (all 7) opens its chapter with that exact span highlighted and in view.
3. Hedged and dialogue statements appear only when the checkbox is on.
4. A search result opens its passage highlighted.
5. Edits persist across reload; markdown preview renders; a stale save shows a conflict and does not
   overwrite; "Save mine anyway" saves on top and history shows versions 4, 3, 2, 1.
6. Fixing the text in the editor clears the contradiction.
7. A canon fact added on the character sheet is checked against the text.
8. Create, rename and delete a novel; add and delete a chapter.

## Latest results

Run on 2026-10-14, Apple M4 / 16 GB / macOS 15.3, Python 3.12.10, Node 22.14.0, embedded
PostgreSQL 16.2 (pgserver 0.1.4), Chromium headless shell 140 (Playwright 1.55.1). Timings were
taken while other jobs were running on the same machine.

| Check | Result |
|---|---|
| ruff | All checks passed |
| pytest | 50 passed in 14.70 s |
| eval-sample (in-memory and `--db`) | 4 TP, 0 FP, 1 FN (known miss), 0/4 negatives violated, citation precision 7/7 |
| tsc | no errors |
| Node unit tests | 6/6 passed |
| vite build | succeeded (373 kB JS, 118 kB gzip) |
| npm audit | 0 vulnerabilities |
| Playwright | 8 passed in 23.6 s |

## Not yet executed

- **GitHub Actions** (`.github/workflows/ci.yml`: backend, frontend, e2e, compose jobs). The workflow
  is written and its YAML parses, but it has never run: the repository has not been pushed.
- **Docker Compose.** No container runtime on the development machine, so `docker compose up` has
  not been run. The CI `compose` job only validates the file and builds the images.
