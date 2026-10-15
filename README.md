# NovelForge

**An evidence-grounded workspace for long fiction.** NovelForge reads a manuscript, extracts
the facts it states (who has which eye colour, who is where on which day, who has died, who can
swim, what the rules of the world are), and finds the places where the story contradicts
itself. Every fact and every finding points at the exact words it came from, and nothing becomes
canon until the author says so.

It is not a chatbot wrapper. The core is a reproducible consistency benchmark: a seeded novel
generator with planted contradictions and look-alike negatives, used to measure retrieval,
extraction and contradiction detection, including how much each kind of memory helps.

![Contradiction report with evidence links](docs/images/contradictions.png)

## What it does

- **Write**: markdown chapters with preview, revision history and optimistic locking (a save
  based on a stale version is refused, never silently merged).
- **Extract**: a deterministic rule extractor runs on every save; an LLM extractor (Claude,
  a local Ollama model, or an offline mock) runs as an idempotent background job with a strict
  JSON schema. Every quote is verified against the text, and every literal value against its
  quote; facts that fail are rejected with a reason.
- **Review**: extracted facts are proposals. Accepting one updates canon (character sheets,
  locations, world rules, timeline, plot threads, relationships) with an audit log; accepting a
  fact that contradicts canon requires explicit confirmation. Decisions survive later edits.
- **Check**: contradictions in identity (attributes, character sheet), timeline (ages, the dead
  reappearing), location (journeys faster than the travel time), abilities (skills used before
  they are learned) and world rules (LLM judge over retrieved passages). Each finding has an
  explanation, evidence, severity and a suggested fix, and can be dismissed (with a reason) or
  resolved; fixed text resolves it automatically.
- **Search**: hybrid retrieval, PostgreSQL full-text plus pgvector embeddings fused with
  reciprocal rank fusion, optional cross-encoder reranking, and per-result "why this ranked".
- **Draft**: a bounded plan → draft → check → revise workflow with human approval at each
  checkpoint, streamed over SSE with cancel and retry. The checker runs the contradiction
  detectors on the draft against the rest of the book and cites both sides.
- **See**: an interactive character co-occurrence graph and a per-character timeline with
  contradictions drawn between the facts that clash.

## Screens

| | |
|---|---|
| ![Clicking a citation opens the chapter with the exact span highlighted](docs/images/cited-span.png) | ![Hybrid search with the rank from each stage](docs/images/search.png) |
| Every citation opens the chapter at the exact quoted span. | Hybrid search shows each hit's rank by words, meaning, fusion and reranking. |
| ![Review queue of extracted facts](docs/images/review.png) | ![Character co-occurrence graph](docs/images/graph.png) |
| Extracted facts wait for review before they become canon. | Who appears with whom, with the paragraphs behind each link. |
| ![Per-character timeline by story day](docs/images/timeline.png) | ![Draft assistant at the decision checkpoint](docs/images/draft.png) |
| Facts by story day; red rings are facts in an open contradiction. | Plan, draft, check, then apply, revise or discard (mock model shown). |

## Quick start (no Docker needed)

Requirements: Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 22.

```bash
# Backend (an embedded PostgreSQL 16 + pgvector is installed as a Python package)
cd backend
uv sync --extra localdb
uv run novelforge migrate
uv run novelforge import-sample          # optional: the three-chapter sample
uv run novelforge serve                  # http://127.0.0.1:8000

# Frontend (second terminal)
cd frontend
npm ci
npm run dev                              # http://localhost:5173
```

### Optional: real models

```bash
uv sync --extra localdb --extra embeddings --extra anthropic
EMBEDDER=fastembed RERANKER=cross-encoder uv run novelforge serve   # local CPU models (~150 MB)
LLM=anthropic LLM_EXTRACTION=true uv run novelforge serve           # Claude (claude-opus-5-5)
LLM=ollama:qwen2.5:7b LLM_EXTRACTION=true uv run novelforge serve   # a local Ollama model
```

Claude uses the Anthropic SDK's usual credentials (`ANTHROPIC_API_KEY` or `ant auth login`).
With `LLM=anthropic`, manuscript text is sent to Anthropic; the default (`mock`) sends nothing
anywhere. All settings are in [.env.example](.env.example).

### Docker Compose

```bash
docker compose up --build               # UI http://localhost:8080, API http://localhost:8000
```

Written and validated in CI; not run on the development machine (no container runtime there).

## Benchmarks

Everything is reproducible from seeds: `bench/run_all.sh` regenerates the corpora and every
number. Details, failure cases and caveats are in [BENCHMARK.md](BENCHMARK.md). Headline results
on a generated 1,000-chapter novel (125 planted contradictions, 148 look-alike negatives), all
local on an M4 laptop:

| What | Result |
|---|---|
| Retrieval, 800 questions (half paraphrased) | hybrid + cross-encoder R@1 **0.909**, R@10 0.999; full-text alone 0.584, vectors alone 0.614 |
| Contradiction recall by memory type (same claims, same detectors) | chapter alone 0.224 · vector memory 0.496 · hybrid memory 0.424 · **structured claim store 0.576** |
| False alarms (structured) | **0** findings wrong, 0 of 148 negatives flagged; whole-novel check in 0.8 s |
| Rule extractor | precision 0.992, recall 0.812; 0% on facts stated through pronouns or implication |
| Local LLM extractor (qwen2.5:3b, 15 chapters) | precision 0.667, recall 0.036: too weak to help; validation cut its false positives from 14 to 1. Claude is wired in but has not been run (no API key) |
| Scale, 1.25 M words / 33,277 paragraphs | chapter save p50 213 ms, hybrid search p50 136 ms, report refresh 524 ms, 257 MB database |

The corpus is synthetic and templated, so these numbers measure the pipeline against known
answers, not literary understanding. The recall figures use the rule extractor only, so they
count all 28 world-rule violations (which need the LLM judge) and every pronoun-stated fact as
misses.

## Commands

`make help` lists the common tasks (`make setup`, `make api`, `make web`, `make check`,
`make bench`). The API's OpenAPI docs are at http://127.0.0.1:8000/docs.

| Command (from `backend/`) | What it does |
|---|---|
| `uv run novelforge migrate [head\|base]` | Apply or roll back migrations |
| `uv run novelforge serve [--reload]` | Run the API (with an in-process job worker) |
| `uv run novelforge worker [--once]` | Run background jobs in a separate process |
| `uv run novelforge import-sample` / `import-corpus DIR` | Import the sample or a generated corpus |
| `uv run novelforge gen-corpus --chapters N --seed S [--filler F] --out DIR` | Generate a benchmark novel |
| `uv run novelforge eval-sample` | Score the sample's contradiction report |
| `uv run novelforge bench-retrieval DIR` | Retrieval: recall@k, MRR, nDCG, latency, tokens |
| `uv run novelforge bench-extraction DIR --extractor rules\|mock\|ollama:M\|anthropic` | Extraction precision/recall per fact type |
| `uv run novelforge bench-consistency DIR` | Contradiction detection with a memory ablation |
| `uv run novelforge bench-load DIR` | Throughput, latency, memory, storage |
| `uv run pytest` | Backend tests |

From `frontend/`: `npm run dev`, `npm run typecheck`, `npm test`, `npm run build`, `npm run e2e`.

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md): components, data model, pipelines, design decisions
- [BENCHMARK.md](BENCHMARK.md): evaluation design, results, ablations, failure cases
- [TESTING.md](TESTING.md): test suites and the latest real results
- [PLAN.md](PLAN.md) and [PROGRESS.md](PROGRESS.md): milestones, acceptance criteria, log
- [LICENSE_NOTES.md](LICENSE_NOTES.md): dependency and model licenses
- [CONTRIBUTING.md](CONTRIBUTING.md): setup, checks, and rules for changes that move numbers
- [docs/demo-walkthrough.md](docs/demo-walkthrough.md) and
  [docs/demo-video-script.md](docs/demo-video-script.md)

MIT licensed ([LICENSE](LICENSE)).
