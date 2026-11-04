# Progress log

## 2026-11-03 (later): fixing what the Claude runs showed

The user asked to fix every remaining problem. Spent on OpenRouter this round: $2.38 recorded
($5.89 recorded in all; the account showed $0.61 of its $10 left afterwards, the difference
being calls that failed before an answer was recorded).

- **Story logic, code side** (`checks-v4`, then `checks-v5`, prompts unchanged): one finding per
  scene and per beat, reveals not judged as acts, setups paid off in other words found by the
  model's payoff question, quiet chapter endings as cliffhanger suggestions rather than
  problems; then later explanations that name a third person, long character files that keep
  the notes about the beat, harm with no reason as villainy without cause. On 青石渡 Claude's
  unlabelled issues went from 11 to 3 with no find lost.
- **A second story held-out**, 青崖问剑, written by a separate agent and scored once (frozen
  `caf042d`): Opus 5.5 4/6 problems, 0/6 traps by hand, $1.49; Haiku 5.5 3/6, 0/6, $0.049.
  checks-v5 came from its misses (seen): 5/6 and 4/6.
- **English with Claude Haiku 5.5**: synthetic extraction P 0.982 R 0.961 (rules 1.0 / 0.884);
  contradictions 10/12 alone, **12/12 with the rules, 0 false findings**, including the
  world-rule violation (the judge now drops quotes that describe a failed attempt); on *The
  Secret Garden* (blind for the LLM) recall 0.316 against the rules' 0.184, every claim
  hand-labelled; on *Anne of Green Gables* 0.426 against 0.213, fact precision 0.93. Smaller
  windows (`LLM_WINDOW_WORDS=1500`) raised recall on the first book (0.474) and lowered it on
  the second (0.340): not a lever, the default stays a whole chapter.
- **Models compared** on the Chinese held-out: Haiku 9/9 for $0.011, Sonnet 7/9 for $0.084,
  Opus 9/9 for $0.255.
- **Product**: a cost estimate before every run (`/api/novels/{id}/llm-estimate`, calibrated on
  the recorded runs, shown on the story page), the recorded Claude audit as a replay option,
  colour values that must be colour words (similes stay refused), `bench-real --llm`,
  `bench-consistency --with-rules`, `LLM_WINDOW_WORDS`.
- 291 backend tests, 17 frontend unit tests.
- **Still open**: the labels are all the assistant's (no second annotator); the story audit is
  measured on two held-out novels of six problems each; the direct Anthropic SDK backend has
  never called the API; nothing is pushed, so CI and Docker have not run.

## 2026-11-03: Claude through OpenRouter

The user supplied an OpenRouter key (saved to `.env` through a hidden-input dialog; it never
passed through the conversation or the repository). Everything below ran live once, with every
answer recorded so it re-scores offline; total billed $3.51.

- **Backend** `openrouter:<model>` (`llm/openrouter_backend.py`): strict JSON-schema output,
  reasoning effort, provider routing that refuses to drop the schema, billed cost per call.
- **Story logic on Claude** (frozen story-v3 prompts, held-out 青石渡): 3/6 problems, 0/4 traps,
  11 issues on no label, 7 of them wrong or weak by hand (qwen2.5:7b: 2/6, 1/4). $1.24.
- **Chinese LLM extraction**: a Chinese prompt (`extract-zh-v2`), developed on the four earlier
  samples, plus three detector fixes found there (a dyed or explained hair change, a more
  detailed birthplace, a remembered lesson). Frozen in `fbf67ff`; a fourth novel 驼铃过碛, written
  by a separate agent, scored once: **Claude 9/9 contradictions with 1 false finding, claims P
  0.98 R 0.857; rules-zh-v3 7/9 with 1, P 0.923 R 0.643**. The false finding (riding practice
  shown before the sentence that says she learned) was then fixed in the detector; re-scored,
  Claude makes no false finding on any of the five Chinese samples (seen).
- **Rules plus Claude is worse than Claude alone** on Chinese (it keeps the rules' false
  findings), so `REPORT_PREFER_LLM` reports the model's claims in chapters it has read; off by
  default until English is measured.
- Also: `eval-facts` / `eval-sample --llm SPEC [--with-rules] [--replay]`, replays cut the same
  windows as the recorded run, scored predicates are exactly the labelled ones, `.env.example`
  lists the real model settings. Backend 277 tests, Playwright 14/14.
- **Not done**: English benchmarks and real prose with Claude; a fresh held-out story-logic
  sample; the direct Anthropic SDK backend has still not called the real API.

## 2026-10-16 (later): Chinese continuity facts (rules-zh)

The contradiction checks (eye and hair colour, age against elapsed time, the dead reappearing,
skills used before they are learned, the character sheet) only read English. They now read
Chinese as well.

- **Extractor** (`core/extraction_zh.py`): rules anchored on names and aliases with checks on
  the words between the name and the fact; Chinese numerals; Chinese modality; 她/他 resolved
  only when unambiguous; dyeing as a change; `presence` (on stage) for the dead-character check.
  Findings on a Chinese novel are worded in Chinese (`core/findings_zh.py`), and the draft
  critic counts Chinese characters and reports the right extractor.
- **Evaluation.** `novelforge eval-facts` scores claims against a sample's hand-labelled `facts`.
  Dev sample 雾港信札 (written with v1): 7/7 contradictions, 0 false, claim precision 1.0,
  recall 0.90. Three held-out novels, each written by a separate agent session that did not see
  the extractor and scored once with the version frozen before it: v1 3/9 (2 false findings),
  v2 5/9 (2), v3 5/9 (3). For v3, two correct findings were first scored as false: the labels put
  the agreeing sentence last. The label order was fixed and the as-labelled score kept. Blind
  claim precision 0.83 to 1.0, recall 0.39 to 0.62. The remaining misses and false findings are
  phrasings outside the rules (being taught a skill, a dye revealed later, roundabout births);
  BENCHMARK.md section 9.
- **Not done.** The motive and plot rules proposed after the story-logic held-out run were
  checked against the recorded answers and not applied. The simplest one (a note cited as both
  reason and conflict cannot be the reason) would not have found H1 on 青石渡 by itself, since a
  second cited note restates the conflict. It would also have added a false alarm on the
  revision, where the model cites the cousin's real motive both ways. The LLM extraction prompt
  is still English-only.

## 2026-10-16: story logic and Chinese

The user asked for more than surface contradictions: check whether each character's actions
have a motive that fits their background, personality and situation (a calculating heroine with
no money should not give it away out of pity unless the story has prepared it), whether villains
have reasons instead of being bad for its own sake, whether the plot holds, and where the story
could be made more gripping (a setback that opens an opportunity, rebirth, a special advantage,
suspense), for Chinese web novels.

- **Chinese text.** Sentences, dialogue (“”「」『』), 第X章 headings and line-per-paragraph
  plain text, character counts, bigram tokens, and full-text search that indexes Chinese bigrams
  as ASCII tokens (PostgreSQL's parser drops Chinese characters under the C locale; migration
  0008). (The rule extractor became bilingual later the same day, see above.)
- **Story-logic audit** (`backend/novelforge/narrative/`): character notes, beats and chapter
  shape per chapter; per beat, grounded sub-questions with the verdict computed by rule; later
  reveals; knowledge-source checks for secrets set down earlier; a rescue check for helpers never
  seen before; setups paid off by their key word; pacing from the tension curve; a revision plan.
  Every quote is located in the text and every cited ID checked; 45 outputs were refused in the
  three frozen runs. Runs are background jobs stored with the chapter versions they read
  (`story_audit`, migration 0007); `replay:<llm>` shows a recorded run without the model.
- **UI.** "Story logic · 人物与故事线": problems with evidence and fixes, a revision plan whose
  items open the draft assistant with the goal filled in, motives per character, a tension chart
  with setups, character files and the record of what the checks changed.
- **Samples.** Three original Chinese samples with labelled problems, traps and ambiguous cases:
  雪夜当铺 (dev), 青石渡 (held out) and a revision of 雪夜当铺 written from the audit's findings.
- **Results with qwen2.5:7b** (the largest model that fits beside other jobs; Claude not run, no
  key). Dev: v1 prompts 1/6 problems, v2 4/6, v3 5/6 with 1/8 traps, 4/6 after a fix found while
  reviewing the dev output (a "conflict" cited a note read off the act itself; such citations are
  now refused, as they already were for reasons). Frozen v3 (`1860fc6`) on
  the held-out novel: 2/6 found (+1 with another diagnosis), 1/4 traps, about 5 noisy issues. On
  the revision: 0/14 fixed places flagged again. The held-out misses are reading errors (an
  invented motive citing the conflicting notes, a misattributed rescuer, a setup without a quote);
  three v4 rules are proposed in BENCHMARK.md and not applied, since they come from the held-out
  sample.
- **Process.** The first held-out run was stopped after 20 seconds, before any response was
  recorded, when the dev run showed the v1 prompts did not work; the held-out sample was run
  once, after v3 was frozen and committed.

## 2026-10-15 (evening): real prose, rules-v4 to v6

The user asked for the project to keep being improved. The biggest open caveat was that every
quality number came from the generator's own templates, so this round measured the extractor on
real novels and improved it under a held-out protocol (BENCHMARK.md section 6,
`bench/real/README.md`).

- **Real-prose benchmark.** `bench-real` runs on four public-domain novels (490,000 words),
  downloaded at run time. Every claim and every keyword-candidate sentence was judged; labels are
  keyed by content, so they survive extractor versions. The labeller was the assistant that wrote
  the rules, which the docs state.
- **What it showed.** rules-v3 (P 0.99 / R 0.81 on synthetic text) found 3 of 30 explicit
  identity facts in *Little Women*. Pronouns, "with" phrases and ages in apposition were the
  main gaps; "sailed away", "wrote no more" and hedge scope the main errors.
- **rules-v4** (frozen `ef1f062`): precision-first pronoun and "with"-phrase attribution
  (`core/coref.py`) that abstains on any ambiguity, plus the dev-book fixes. On its held-out
  books (*Anne of Green Gables*, *Pride and Prejudice*) recall went from 3/32 to 11/32 with no
  wrong fact.
- **rules-v5** (frozen `f29b4d3`): past states in time clauses ("ever since he was twenty") are
  `recalled`. On a fresh held-out book (*The Secret Garden*, cast written before reading it)
  recall went from 1/25 to 5/25, with one wrong attribution.
- **rules-v6** (`9cc3b88`): that attribution fixed; measured only on books it has seen.
- **Synthetic side effects.** Generator v4 labels the dye sentence and puts pronouns on the
  sheets, text byte-identical to v3; extraction recall 0.813 -> 0.903 at precision 1.0.
- **Also:** `novelforge import-text` for any `.txt` novel; pronouns on the character sheet in the
  UI; "golden"/"yellow"/"blond" no longer contradict each other; sentence splitting no longer
  breaks after "Mrs."; extraction of a 186,000-word novel takes about 2 s (was 20 s).

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
