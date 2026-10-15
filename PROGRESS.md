# Progress log

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
