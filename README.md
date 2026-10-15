# NovelForge

A workspace for long-form fiction that keeps a manuscript consistent across hundreds of
chapters. NovelForge extracts facts from the text, points every fact back to the exact words it
came from, and reports contradictions with clickable evidence. The author decides what is canon.

It is not a chatbot wrapper. The portfolio goal is a reproducible, evidence-grounded
narrative-consistency benchmark plus an interactive character/timeline graph (later milestones).

**Status: Milestones 1–2 of 6 complete.** See [PLAN.md](PLAN.md) for scope and
[PROGRESS.md](PROGRESS.md) for what has actually been run.

![Contradiction report with evidence links](docs/images/contradictions.png)

## What works today

- Novels, chapters and characters: create, edit, delete (API and UI).
- Markdown chapter editor with preview, revision history, and optimistic locking: a save based
  on a stale version is refused with a conflict message instead of silently overwriting.
- Deterministic, idempotent import of a three-chapter sample novel with labelled ground truth.
- Hybrid search: PostgreSQL full-text + pgvector embeddings fused with reciprocal rank fusion, an
  optional cross-encoder reranker, and a "why this result" breakdown per hit. Indexing runs in a
  PostgreSQL-backed job queue and only re-embeds paragraphs that changed.
- A seeded synthetic-novel generator with labelled contradictions, look-alike negatives, facts and
  questions, and a retrieval benchmark (recall@k, MRR, nDCG, latency, tokens) on top of it.
- A rule-based fact extractor (`rules-v1`) and a basic contradiction report: conflicting
  statements, text vs. character sheet, and age vs. elapsed story time. Every finding cites
  exact spans; clicking one opens the chapter with that span highlighted.

Not yet: LLM extraction with review, timeline/location/world-rule checks, dismiss/resolve,
drafting workflow, scale tests. Those are Milestones 3–6.

## Quick start (no Docker needed)

Requirements: Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 22.

```bash
# Backend: installs deps plus an embedded PostgreSQL 16 + pgvector (pgserver) for local dev
cd backend
uv sync --extra localdb
uv run novelforge migrate          # creates the schema in ./.pgdata (repo root)
uv run novelforge import-sample    # optional: loads samples/lanternfall
uv run novelforge serve            # API on http://127.0.0.1:8000

# Frontend (second terminal)
cd frontend
npm ci
npm run dev                        # UI on http://localhost:5173, proxies /api to :8000
```

To use your own PostgreSQL instead, set `DATABASE_URL` (see [.env.example](.env.example)).

Semantic search uses a deterministic mock embedder by default. For real local models on CPU
(bge-small embeddings + a MiniLM cross-encoder, ~150 MB downloaded on first use):

```bash
uv sync --extra localdb --extra embeddings
EMBEDDER=fastembed RERANKER=cross-encoder uv run novelforge serve
```
Stop the embedded database with `uv run novelforge local-db --stop`.

### With Docker Compose

```bash
docker compose up --build          # UI http://localhost:8080, API http://localhost:8000
```

This file is written but **has not been run on the development machine**, which has no
container runtime. CI validates and builds it.

## Commands

| Command (from `backend/`) | What it does |
|---|---|
| `uv run novelforge migrate [head\|base]` | Apply or roll back migrations |
| `uv run novelforge import-sample [name]` | Import a sample novel (idempotent) |
| `uv run novelforge eval-sample [--db] [--json]` | Score the contradiction report against the sample's ground truth |
| `uv run novelforge serve [--reload]` | Run the API |
| `uv run novelforge local-db [--stop]` | Start (and print the URL of) or stop the embedded PostgreSQL |
| `uv run novelforge worker [--once]` | Run background jobs (embeddings) outside the API process |
| `uv run novelforge gen-corpus --chapters N --seed S --out DIR` | Generate a synthetic benchmark novel |
| `uv run novelforge import-corpus DIR` | Import a generated corpus (idempotent) |
| `uv run novelforge bench-retrieval DIR [--embedder E --reranker R]` | Retrieval benchmark on a corpus |
| `uv run pytest` | Backend tests |

From `frontend/`: `npm run dev`, `npm run typecheck`, `npm test`, `npm run build`,
`npm run e2e` (Playwright; starts its own API and database).

## Documentation

- [PLAN.md](PLAN.md): milestones, acceptance criteria, non-goals
- [ARCHITECTURE.md](ARCHITECTURE.md): data model, data flow, design decisions
- [TESTING.md](TESTING.md): test suites and the latest real results
- [BENCHMARK.md](BENCHMARK.md): evaluation design and measured numbers (so far: one small smoke check)
- [LICENSE_NOTES.md](LICENSE_NOTES.md): third-party licenses and sample-text provenance
- [docs/demo-walkthrough.md](docs/demo-walkthrough.md): a five-minute demo script
- [PROGRESS.md](PROGRESS.md): progress log
