# Benchmark

Every number in this file was produced by a committed command on recorded data. The corpora are
generated deterministically from a seed, so anyone can rebuild them and rerun the commands:

```bash
bench/run_all.sh        # regenerates the corpora and every result below (~30 min on CPU)
```

Raw outputs are in [bench/results/](bench/results). Each section names the commit its numbers
come from (reports from `bc2ddf6` on also record it themselves). All corpora: generator version 3,
seed 7. Hardware: Apple M4, 16 GB, macOS 15.3, Python 3.12.10, PostgreSQL 16.2 + pgvector 0.6.2
(embedded `pgserver`). The machine was shared with other jobs, so latencies are indicative, not
tuned peaks.

## The benchmark corpus

`novelforge gen-corpus` simulates a small world (characters with attributes and abilities,
places with travel times, deaths, skills learned, world rules, foreshadowing, causal links) and
renders it to prose from varied templates. It then plants contradictions and look-alike negatives
at known spans and writes the ground truth next to the text.

| | 100 chapters (`syn-100-s7`) | 1,000 chapters (`syn-1000-s7`) |
|---|---|---|
| Labelled facts | 283 | 2,502 |
| Planted contradictions | 12 | 125 |
| Negative cases (look like contradictions, are not) | 13 | 148 |
| Retrieval questions (half paraphrased) | 352 | 800 |
| Foreshadowing set-ups / causal links / world-rule statements | 14 / 8 / 4 | 128 / 117 / 4 |

Contradictions cover five categories: identity (attribute conflicts, conflicts with the character
sheet), timeline (ages that do not fit elapsed days; dead characters who reappear), location
(journeys faster than the travel time), abilities (skills used before they are learned) and
world rules. Negatives include hedged perception ("seemed almost black"), a character's wrong words
in dialogue, memories of the dead, flashbacks set before a death, skills used after learning them,
journeys that fit the travel time, failed attempts at a forbidden act, and dyed hair.

Templates are deliberately varied: some state a fact next to the character's name, others only
through a pronoun or an indirect phrasing ("Being left-handed, …", "had grown up in Ashford").
Every mention records its template, so failures can be broken down by phrasing.

**Limits of a synthetic benchmark.** The prose is templated and the world is small. The corpus
measures whether the pipeline finds labelled facts and errors at known spans, and what each design
choice contributes. It does not measure literary understanding, and absolute numbers will be
lower on real manuscripts. Rule-based numbers in particular benefit from the corpus using a finite
set of phrasings.

## 1. Retrieval

Command: `novelforge bench-retrieval bench/corpora/syn-100-s7 --embedder fastembed --reranker cross-encoder`
(commit `2572c56`). Embedder: BAAI/bge-small-en-v1.5 (local ONNX, CPU). Reranker: ms-marco-MiniLM-L-6-v2 cross-encoder
over the top 30. A passage is relevant when it overlaps a labelled evidence span for the question.

| Mode | R@1 | R@3 | R@10 | MRR@10 | nDCG@10 | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|
| keyword (all words required) | 0.230 | 0.236 | 0.250 | 0.235 | 0.208 | 1.0 | 2.3 |
| fts (any word, ranked) | 0.591 | 0.835 | 0.972 | 0.726 | 0.753 | 4.9 | 8.0 |
| vector | 0.631 | 0.858 | 0.977 | 0.758 | 0.790 | 13.6 | 23.1 |
| hybrid (RRF) | 0.761 | 0.943 | **1.000** | 0.853 | 0.871 | 19.0 | 32.2 |
| hybrid + cross-encoder | **0.903** | **0.980** | **1.000** | **0.943** | **0.952** | 179.6 | 238.4 |

Paraphrased questions only (176): fts R@1 0.557, vector 0.602, hybrid 0.733, hybrid + rerank 0.875.
Indexing 835 paragraphs took 14.7 s (44,658 tokens counted by the model's tokenizer); cost $0, all
local. Reranking is 158 ms of the 180 ms median.

- Hybrid beats both of its parts on every metric: fusing word and meaning matches lifts R@1 by
  13–17 points over either alone.
- The cross-encoder adds 14 more points at the top for about 160 ms per question; hybrid without
  it already finds the answer in the top 10 for every question.
- "keyword" (all words required) is what a naive search box does with questions: it fails on
  any paraphrase.

**At 1,000 chapters** (8,277 paragraphs, 800 questions; same models):

| Mode | R@1 | R@10 | MRR@10 | p50 ms | p95 ms |
|---|---|---|---|---|---|
| fts | 0.584 | 0.938 | 0.706 | 9.1 | 16.3 |
| vector | 0.614 | 0.965 | 0.741 | 37.0 | 49.8 |
| hybrid | 0.774 | 0.985 | 0.851 | 39.2 | 50.0 |
| hybrid + cross-encoder | **0.909** | **0.999** | **0.946** | 353.9 | 520.5 |

The ranking quality holds at ten times the size (hybrid + rerank R@1 0.903 → 0.909; paraphrases
0.955), while the lexical baselines lose top-10 recall as more paragraphs mention the same names
(fts R@10 0.972 → 0.938). Indexing 7,710 unique paragraphs took 126 s on CPU (425,736 tokens).

**Mock components, for contrast** (`--embedder hash --reranker lexical`, the defaults in tests and
CI): hybrid R@1 0.676, but the lexical mock reranker drops paraphrased questions to R@1 0.278. The
mocks keep tests deterministic; they are not semantic, and these rows show why the real models matter.

## 2. Extraction (rule baseline)

Command: `novelforge bench-extraction bench/corpora/syn-1000-s7 --extractor rules`. A fact is
found when an `asserted` claim has the same chapter, character, predicate and value as a labelled
statement and overlaps its sentence. Two versions of the rule extractor are compared: `rules-v2`
(commit `2572c56`) and `rules-v3` (run at `eb34a16` and again at `d7830ba` with identical
results), which adds four patterns found by the failure analysis below.

| Predicate | v2 precision | v2 recall | v3 precision | v3 recall |
|---|---|---|---|---|
| **all scored** (1,000 ch) | 1.000 | 0.784 | 0.992* | **0.812** |
| all scored (100 ch) | 1.000 | 0.777 | 0.996* | 0.799 |
| location | 1.000 | 1.000 | 1.000 | 1.000 |
| abilities (cannot / learned) | 1.000 | 1.000 | 1.000 | 1.000 |
| death | 1.000 | 1.000 | 1.000 | 1.000 |
| age | 1.000 | 0.749 | 1.000 | **1.000** |
| hair colour | 1.000 | 0.705 | 0.931* | 0.705 |
| birthplace | 1.000 | 0.672 | 1.000 | 0.672 |
| eye colour | 1.000 | 0.586 | 1.000 | 0.586 |
| handedness | 1.000 | 0.307 | 1.000 | 0.307 |

\* All 16 v3 "false positives" are sentences like "Damo dyed her hair red": correct statements of
the new colour that the generator does not label as facts (it labels the following "her hair was
red now"). This is a gap in the ground truth, not an extraction error (see Known gaps).

1,000 chapters extract in about 5 s. Every hedged, dialogue and memory negative the extractor
touched was kept out of `asserted` (42 of 42). Location day accuracy rose from 1,013 to 1,027 of
1,027: v3 reads in-chapter offsets ("Three days later Tomas was in Varrow"). World rules,
foreshadowing and causal links: 0% (the rules do not read them).

**Failure analysis by phrasing** (1,000 chapters, rules-v3): the rules find 100% of statements
anchored on a name and 0% of these, which is the gap the LLM extractor exists to close:

| Phrasing | Missed | Example |
|---|---|---|
| pronoun | 138 | "Mara looked up, her grey eyes narrowing" |
| handedness by implication | 178 | "Being left-handed, …", "wrote with his left hand" |
| indirect birthplace | 88 | "had grown up in Ashford, where she was born" |
| colour by simile | 67 | "eyes the colour of sea glass" |

**What v3 changed, and the caveat.** The 1,000-chapter run of v2 showed four phrasings the rules
missed or misread: "At fifty, Cawen …" (69 ages), "dove from the pier and swam" (missed ability
use), "dyed her hair red" (a deliberate change reported as a contradiction) and "Three days later …"
(14 journeys put on the wrong day). v3 handles all four with generic English patterns. They were
found on this generator's own templates, so the size of the improvement on real manuscripts is
unknown; the same caution applies to every rule-based number here.

## 3. Contradiction detection and the memory ablation

Command: `novelforge bench-consistency bench/corpora/syn-1000-s7 --embedder fastembed`. The task:
check each chapter against the rest of the novel. Every system uses the same extracted claims and
the same detectors; they differ only in what the checker can see when it checks chapter *c*:

- **no-memory**: chapter *c*'s own claims (plus character sheets and travel times)
- **vector-only**: plus the claims in the top 5 earlier paragraphs retrieved by embedding
  similarity, one query per claim
- **hybrid**: the same with hybrid retrieval (full-text + vector, RRF)
- **structured**: every claim in the novel, indexed by character and predicate (NovelForge)

A finding counts only if it names the right category and character and cites the planted
statement itself; a negative counts as violated when a false alarm cites it. rules-v3 ran at
commit `d7830ba`; rules-v2 ran from a worktree at `2572c56` with the same scoring code copied in,
so both rows use the same scorer.

**1,000 chapters** (125 planted contradictions, 148 negatives), rules-v3:

| System | Recall | Precision | False alarms | Negatives flagged | Claims seen per check | Time |
|---|---|---|---|---|---|---|
| no-memory | 0.224 | 1.000 | 0 | 0 / 148 | 2.6 | 5 s |
| vector-only | 0.496 | 1.000 | 0 | 0 / 148 | 14.0 | 288 s |
| hybrid | 0.424 | 0.964 | 2 | 2 / 148 | 15.7 | 299 s |
| **structured** | **0.576** | **1.000** | **0** | **0 / 148** | 2,580 | **0.8 s** |

Same run with rules-v2: structured recall 0.520, precision 0.813, 15 false alarms, 18 negatives
flagged; no-memory 0.208 / 0.813; vector-only 0.440 / 0.688; hybrid 0.384 / 0.640.

**100 chapters** (12 contradictions, 13 negatives), identical for v2 and v3: no-memory 0.250,
vector-only 0.667, hybrid 0.583, structured **0.750**; precision 1.000 and no negative flagged
in every system.

By category at 1,000 chapters (structured, rules-v3): timeline 27/27, location 16/16, abilities
10/10, identity 19/44, world rules 0/28. Citation precision 0.744 (cited spans that are labelled
evidence; findings also cite consistent statements that support the explanation), citation recall
0.926.

What the ablation shows:
- **Memory decides recall.** Checking a chapter alone finds about a fifth of the contradictions.
  Retrieved memory more than doubles that. The structured claim store finds the most, at a cost of
  well under a second for the whole novel, against minutes for per-claim retrieval.
- **Hybrid is not better than vector here.** For memory, the query is the claim's own sentence; full-text
  matching then favours paragraphs that share the character's name and template words, which
  crowds out the paragraph that actually conflicts. Hybrid wins for questions (section 1) and loses
  for this use. The structured index does not depend on retrieval at all.
- **What stays missed is extraction, not memory.** Of the 25 missed identity contradictions, 24
  are stated through a pronoun or by implication ("Being left-handed, …", "eyes the colour of
  peat"), which the rules cannot read. The 25th is detected but merged: Jorin is "born in
  Blackmere" in chapters 527 and 663 against a sheet that says Wrengate, the detector reports both
  as one finding, and the scorer credits each finding to one planted contradiction. Every
  world-rule violation needs the LLM judge. Detection has no false alarms on 148 negatives.
- **Failure analysis drove v3.** The v2 false alarms were all deliberate changes ("dyed her hair")
  and journeys within one chapter ("three days later"); recognising those removed every false
  alarm and lifted recall by 5.6 points (section 2 has the caveat).

## 4. Scale and load

Command: `novelforge bench-load bench/corpora/load-1000-s7` (generated with `--filler 25`, about
1,250 words per chapter; commit `eb34a16`, hash embedder so indexing time measures the pipeline
rather than a model). Everything runs in one process against a fresh database.

| Measure | 100 chapters | 1,000 chapters |
|---|---|---|
| Words / paragraphs / extracted claims | 125,000 / 3,342 / 433 | 1,250,697 / 33,277 / 4,111 |
| Import (split, scenes, extraction, revisions) | 4.4 s | 59.7 s (16.7 chapters/s) |
| Embedding index (hash mock) | 1.8 s | 17.9 s |
| HNSW index build | 0.9 s | 10.1 s |
| Search p50 / p95: keyword | 1.8 / 3.6 ms | 3.8 / 4.9 ms |
| Search p50 / p95: fts | 5.3 / 7.0 ms | 13.6 / 30.1 ms |
| Search p50 / p95: vector, exact | 12.5 / 16.5 ms | 126.7 / 143.4 ms |
| Search p50 / p95: vector, HNSW | 12.0 / 15.7 ms | 100.9 / 123.3 ms |
| Search p50 / p95: hybrid (exact) | 17.3 / 23.1 ms | 135.6 / 159.1 ms |
| HNSW top-10 agreement with exact search | 1.0 | 1.0 |
| Contradiction report refresh p50 | 37 ms | 524 ms |
| Character graph p50 | 102 ms | 2,037 ms |
| Timeline p50 | 37 ms | 449 ms |
| Chapter save p50 / p95 (re-split, re-extract, revision) | 53 / 70 ms | 213 / 328 ms |
| Database size | 35 MB | 257 MB |
| Peak RSS of the benchmark process | 168 MB | 837 MB |

What this says about a 1.25-million-word manuscript on a laptop:
- Saving a chapter stays around a fifth of a second, and search stays interactive.
- Exact vector search over 33,000 paragraphs costs about 127 ms. With HNSW it is about 101 ms,
  and its top 10 matched exact search on every query. Exact remains the default because an
  approximate index filtered by novel can drop matches; HNSW is the switch for larger corpora.
- The character graph is the slowest view (2 s at 1,000 chapters). It re-scans every paragraph for
  names on each request; caching it per chapter version is the obvious next step.
- These timings come from a machine running other jobs, so they are an upper bound for an
  idle M4.

## 5. LLM extraction with a small local model

Command: `novelforge bench-extraction bench/corpora/syn-40-s7 --extractor ollama:qwen2.5:3b
--max-chapters 15` (commit `51fa460`). No API key was available, and the largest model this
16 GB machine could run beside other jobs was qwen2.5:3b (4-bit, 2.5 GB in Ollama on the M4 GPU).
It ran on the first 15 chapters of a 40-chapter corpus (55 labelled facts) with schema-constrained
JSON and an output cap of 2,048 tokens per call. The scoring is the same as in section 2.

| | Rules (rules-v3) | qwen2.5:3b, default validation | qwen2.5:3b, value check off |
|---|---|---|---|
| Facts found / false positives | 50 / 0 | 2 / 1 | 2 / 14 |
| Precision / recall | 1.000 / 0.909 | 0.667 / 0.036 | 0.125 / 0.036 |
| Facts rejected by validation | n/a | 53 | 35 |
| Time for 15 chapters | 0.2 s | 711 s uncached (see below) | 0.06 s, replayed |

The model was called once per chapter. The 13 calls that returned used 11,591 input and 6,360
output tokens ($0); the other two ran into the 2,048-token output cap with the model repeating
itself, and their tokens are not counted. Rejections: the quote is not in the chapter (19), the
value does not fit the predicate (16), and the value is not in the quote (18, only when the value
check is on). The first, uncached run took 711 s; the committed report comes from a rerun that
called the model only for the two failed calls (281 s) and reproduced every number.

- **A 3B model is not a usable extractor for this task.** It found 2 of 55 facts, both hair
  colours, against 50 for the rules. It also proposed 6 events, 2 relationships and 1 of the 4
  world-rule statements, which the rules cannot produce at all, but too little to change any
  number above.
- **The validation layer is what keeps a weak model safe.** Without the value check, 14 of the 16
  accepted facts were wrong: real sentences offered as evidence for an unrelated value ("Jorin
  could not swim." as evidence of a location). The check removed 13 of them and no correct fact.
  The remaining false positive is a scene-setting line ("Day 83, in Wrengate.") that names the
  place but not the character.
- **The last column is a replay.** Every response, including the two failed calls, is
  recorded in `bench/results/llm-cache/`; this column re-scores the same responses with the
  check off and loads no model.
- **Not measured: a capable model.** `--extractor anthropic` runs the same benchmark against
  Claude (`claude-opus-5-5`); it has not been run, so how much of the pronoun and implication gap
  in section 2 an LLM closes is still an open question.

## 6. The three-chapter sample

`novelforge eval-sample` on `samples/lanternfall` (hand-written, five labelled contradictions, four
negatives): 4 found, 0 false positives, 0 of 4 negatives flagged, citation precision 1.0 (rules-v2
and rules-v3 alike). The miss is a hair-colour change referred to only by "Her hair", which needs
pronoun resolution. The sample and the rules were written together, so this is a regression check,
not a result.

## Reproducing

```bash
make setup                                   # or: cd backend && uv sync --extra localdb --extra embeddings
bench/run_all.sh                             # corpora + every table above (about 30 min on an M4)
cd backend && uv run novelforge bench-consistency ../bench/corpora/syn-100-s7 --embedder fastembed
```

- Corpora are byte-identical for the same seed, chapter count, filler and generator version.
- Each JSON in `bench/results/` records the corpus, generator version, embedder, reranker,
  extractor, machine and (from `bc2ddf6` on) the git commit.
- Models: BAAI/bge-small-en-v1.5 and ms-marco-MiniLM-L-6-v2 via fastembed 0.8.1 (ONNX, CPU).
  Retrieval scores are deterministic; latencies vary with machine load.

## Known gaps and next steps

- **No hosted-model run.** Claude is wired in (official SDK, structured outputs, fallbacks) and
  tested against a fake client, but no API key was available. `--extractor anthropic` runs every
  benchmark unchanged.
- **Small local model only.** The one LLM run is qwen2.5:3b on 15 chapters (section 5), which
  is far below the rule baseline; it tests the pipeline and its guardrails, not LLM extraction.
- **World rules are undetected without an LLM.** All 28 planted rule violations at 1,000 chapters
  are missed by the rule baseline; the LLM judge is the only path.
- **Ground-truth gap.** The generator does not label "X dyed her hair Y" as a hair-colour fact.
  Fixing it changes the ground truth (and every result above), so it is left for the next full
  benchmark run under a new generator version.
- **Synthetic prose.** Templates and a small world: good for controlled measurement, not a
  substitute for real manuscripts.
