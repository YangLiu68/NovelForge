# Benchmark

Every number in this file was produced by a committed command on recorded data. The corpora are
generated deterministically from a seed, so anyone can rebuild them and rerun the commands:

```bash
bench/run_all.sh        # regenerates the corpora and every result below (~30 min on CPU)
```

Raw outputs are in [bench/results/](bench/results). Each section names the commit its numbers
come from (reports from `bc2ddf6` on also record it themselves). All corpora: generator version 4,
seed 7 (version 4 adds the dye sentence to the labels and pronouns to the character sheets; the
chapter text, retrieval questions and planted evidence are byte-identical to version 3, so
the retrieval results in section 1 hold for both). Hardware: Apple M4, 16 GB, macOS 15.3, Python 3.12.10, PostgreSQL 16.2 + pgvector 0.6.2
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
statement and overlaps its sentence. The table compares `rules-v3` (frozen at `e709488`, run from
a worktree) with the current `rules-v6` (`9cc3b88`), both against generator-v4 labels.

| Predicate | v3 precision | v3 recall | v6 precision | v6 recall |
|---|---|---|---|---|
| **all scored** (1,000 ch) | 1.000 | 0.813 | 1.000 | **0.903** |
| all scored (100 ch) | 1.000 | 0.799 | 1.000 | 0.884 |
| location | 1.000 | 1.000 | 1.000 | 1.000 |
| abilities (cannot / learned) | 1.000 | 1.000 | 1.000 | 1.000 |
| death | 1.000 | 1.000 | 1.000 | 1.000 |
| age | 1.000 | 1.000 | 1.000 | 1.000 |
| hair colour | 1.000 | 0.720 | 1.000 | **1.000** |
| birthplace | 1.000 | 0.672 | 1.000 | **1.000** |
| eye colour | 1.000 | 0.586 | 1.000 | 0.759 |
| handedness | 1.000 | 0.307 | 1.000 | 0.307 |

1,000 chapters extract in 4 to 11 s depending on machine load. Every hedged, dialogue and memory
negative the extractor touched was kept out of `asserted` (42 of 42), and location days are right
for all 1,027 journeys. World rules, foreshadowing and causal links: 0% (the rules do not read
them). With pronouns inferred from each chapter instead of read from the character sheets,
rules-v6 recall is 0.844, still at precision 1.000.

**Failure analysis by phrasing** (1,000 chapters):

| Phrasing | Missed by v3 | Missed by v6 | Example |
|---|---|---|---|
| pronoun | 138 | 0 | "Mara looked up, her grey eyes narrowing" |
| indirect birthplace | 88 | 0 | "had grown up in Ashford, where she was born" |
| handedness by implication | 178 | 178 | "Being left-handed, …", "wrote with his left hand" |
| colour by simile | 67 | 67 | "eyes the colour of sea glass" |

**History and caveat.** rules-v3 added four patterns found in the v2 failure analysis ("At fifty,
Cawen …", "dove from the pier and swam", "dyed her hair red", "Three days later …"; recall 0.784
to 0.812 against generator-v3 labels, which did not label the dye sentence). rules-v4 to v6 add
precision-first pronoun and "with"-phrase attribution (`core/coref.py`) and fixes found by reading
real novels (section 6). Every phrasing above comes from this generator's templates, so a recall
of 0.903 here says little about real manuscripts; section 6 measures that, and the answer is a
fifth to a third.

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
statement itself; a negative counts as violated when a false alarm cites it. rules-v6 ran at
`9cc3b88`, rules-v3 at `d7830ba`; rules-v2 ran from a worktree at `2572c56` with the same scoring
code copied in, so every row uses the same scorer.

**1,000 chapters** (125 planted contradictions, 148 negatives), rules-v6:

| System | Recall | Precision | False alarms | Negatives flagged | Claims seen per check | Time |
|---|---|---|---|---|---|---|
| no-memory | 0.280 | 1.000 | 0 | 0 / 148 | 2.8 | 1.7 s |
| vector-only | 0.584 | 1.000 | 0 | 0 / 148 | 15.9 | 277 s |
| hybrid | 0.512 | 0.970 | 2 | 2 / 148 | 18.0 | 289 s |
| **structured** | **0.664** | **1.000** | **0** | **0 / 148** | 2,806 | **0.5 s** |

With rules-v3 the same systems scored 0.224, 0.496, 0.424 (2 false alarms) and 0.576; with
rules-v2, structured recall was 0.520 at precision 0.813 (15 false alarms, 18 negatives flagged).
The gain from v3 to v6 is the pronoun-stated facts the extractor now reads (section 2); no system
gained a false alarm.

**100 chapters** (12 contradictions, 13 negatives), identical for v2, v3 and v6: no-memory 0.250,
vector-only 0.667, hybrid 0.583, structured **0.750**; precision 1.000 and no negative flagged
in every system.

By category at 1,000 chapters (structured, rules-v6): timeline 27/27, location 16/16, abilities
10/10, identity 30/44 (v3: 19/44), world rules 0/28. Citation recall 0.947; citation precision
0.652 (v3: 0.744), counted as the share of cited spans that are labelled evidence. It fell because
findings now also cite more of the consistent statements behind the explanation, which v6 reads
through pronouns and which the ground truth does not list as evidence.

What the ablation shows:
- **Memory decides recall.** Checking a chapter alone finds about a fifth of the contradictions.
  Retrieved memory more than doubles that. The structured claim store finds the most, at a cost of
  well under a second for the whole novel, against minutes for per-claim retrieval.
- **Hybrid is not better than vector here.** For memory, the query is the claim's own sentence; full-text
  matching then favours paragraphs that share the character's name and template words, which
  crowds out the paragraph that actually conflicts. Hybrid wins for questions (section 1) and loses
  for this use. The structured index does not depend on retrieval at all.
- **What stays missed is extraction, not memory.** Of the 14 missed identity contradictions
  (25 with v3), 13 are stated by implication or simile ("Being left-handed, …", "wrote with her
  left hand", "eyes the colour of peat"), which the rules do not read by design. The 14th is
  detected but merged: Jorin is "born in Blackmere" in chapters 527 and 663 against a sheet that
  says Wrengate, the detector reports both as one finding, and the scorer credits each finding to
  one planted contradiction. Every world-rule violation needs the LLM judge. Detection has no
  false alarms on 148 negatives.
- **Failure analysis drove v3.** The v2 false alarms were all deliberate changes ("dyed her hair")
  and journeys within one chapter ("three days later"); recognising those removed every false
  alarm and lifted recall by 5.6 points (section 2 has the caveat).

## 4. Scale and load

Command: `novelforge bench-load bench/corpora/load-1000-s7` (generated with `--filler 25`, about
1,250 words per chapter; commit `9cc3b88`, rules-v6, hash embedder so indexing time measures the
pipeline rather than a model). Everything runs in one process against a fresh database.

| Measure | 100 chapters | 1,000 chapters |
|---|---|---|
| Words / paragraphs / extracted claims | 124,999 / 3,342 / 457 | 1,250,697 / 33,277 / 4,337 |
| Import (split, scenes, extraction, revisions) | 4.0 s | 44.4 s (22.5 chapters/s) |
| Embedding index (hash mock) | 2.5 s | 24.5 s |
| HNSW index build | 1.3 s | 14.4 s |
| Search p50 / p95: keyword | 4.2 / 6.9 ms | 4.9 / 5.8 ms |
| Search p50 / p95: fts | 14.8 / 20.0 ms | 18.7 / 35.1 ms |
| Search p50 / p95: vector, exact | 17.8 / 19.9 ms | 178.3 / 222.2 ms |
| Search p50 / p95: vector, HNSW | 16.5 / 18.3 ms | 137.6 / 151.1 ms |
| Search p50 / p95: hybrid (exact) | 33.4 / 38.4 ms | 172.5 / 193.0 ms |
| HNSW top-10 agreement with exact search | 1.0 | 1.0 |
| Contradiction report refresh p50 | 50 ms | 774 ms |
| Character graph p50 | 145 ms | 2,659 ms |
| Timeline p50 | 43 ms | 630 ms |
| Chapter save p50 / p95 (re-split, re-extract, revision) | 60 / 70 ms | 247 / 569 ms |
| Database size | 36 MB | 258 MB |
| Peak RSS of the benchmark process | 170 MB | 834 MB |

These runs shared the machine with other jobs at a load average near 100 on 10 cores, far busier
than the previous run (rules-v3 at `eb34a16`: 1,000-chapter import 59.7 s, exact vector search
127 ms, save 213 ms, report 524 ms, graph 2,037 ms). Import got faster because rules-v6 matches
its patterns at each name instead of at every character. Search latencies rose with the machine
load (the search code did not change); the report and timeline also handle 5% more claims.

What this says about a 1.25-million-word manuscript on a laptop:
- Saving a chapter stays around a quarter of a second even on a saturated machine, and search
  stays interactive.
- Exact vector search over 33,000 paragraphs costs 130 to 180 ms. HNSW is about a quarter
  faster, and its top 10 matched exact search on every query. Exact remains the default because
  an approximate index filtered by novel can drop matches; HNSW is the switch for larger corpora.
- The character graph is the slowest view (2 to 3 s at 1,000 chapters). It re-scans every
  paragraph for names on each request; caching it per chapter version is the obvious next step.
- These timings are an upper bound for an idle M4.

## 5. LLM extraction with a small local model

Command: `novelforge bench-extraction bench/corpora/syn-40-s7 --extractor ollama:qwen2.5:3b
--max-chapters 15` (commit `51fa460`). No API key was available, and the largest model this
16 GB machine could run beside other jobs was qwen2.5:3b (4-bit, 2.5 GB in Ollama on the M4 GPU).
It ran on the first 15 chapters of a 40-chapter corpus (55 labelled facts) with schema-constrained
JSON and an output cap of 2,048 tokens per call. The scoring is the same as in section 2.

| | Rules (rules-v3 / rules-v6) | qwen2.5:3b, default validation | qwen2.5:3b, value check off |
|---|---|---|---|
| Facts found / false positives | 50 / 0, 53 / 0 | 2 / 1 | 2 / 14 |
| Precision / recall | 1.000 / 0.909, 1.000 / 0.964 | 0.667 / 0.036 | 0.125 / 0.036 |
| Facts rejected by validation | n/a | 53 | 35 |
| Time for 15 chapters | 0.2 s | 711 s uncached (see below) | 0.06 s, replayed |

The model was called once per chapter. The 13 calls that returned used 11,591 input and 6,360
output tokens ($0); the other two ran into the 2,048-token output cap with the model repeating
itself, and their tokens are not counted. Rejections: the quote is not in the chapter (19), the
value does not fit the predicate (16), and the value is not in the quote (18, only when the value
check is on). The first, uncached run took 711 s; the committed report comes from a rerun that
called the model only for the two failed calls (281 s) and reproduced every number.

- **A 3B model is not a usable extractor for this task.** It found 2 of 55 facts, both hair
  colours, against 50 for rules-v3 (53 for v6). It also proposed 6 events, 2 relationships
  and 1 of the 4 world-rule statements, which the rules cannot produce at all, but too little to
  change any number above.
- **The validation layer is what keeps a weak model safe.** Without the value check, 14 of the 16
  accepted facts were wrong: real sentences offered as evidence for an unrelated value ("Jorin
  could not swim." as evidence of a location). The check removed 13 of them and no correct fact.
  The remaining false positive is a scene-setting line ("Day 83, in Wrengate.") that names the
  place but not the character.
- **The last column is a replay.** Every response, including the two failed calls, is
  recorded in `bench/results/llm-cache/`; this column re-scores the same responses with the
  check off and loads no model.
- **Not measured: a capable model.** `--extractor anthropic` runs the same benchmark against
  Claude (`claude-opus-5-5`); it has not been run, so how much of the implication gap in
  section 2, and of the much larger real-prose gap in section 6, an LLM closes is still an open
  question.

## 6. Real prose: four public-domain novels

Command: `novelforge bench-real <book>`; the method, labelling rules and protocol are in
[bench/real/README.md](bench/real/README.md). The synthetic numbers above were earned on the
generator's own phrasings, so this section runs the extractor and the contradiction report on
novels nobody wrote for NovelForge, 489,634 words in all, and judges every claim by hand. Recall
is estimated on sentences that a keyword filter flags as possibly stating an eye colour, hair
colour, age, birthplace, handedness or death (an upper bound: facts stated without those words
are not counted). The labels were made by the AI assistant that wrote the rules, so the protocol
holds books out: each extractor version was frozen before its held-out book was read.

| Book | Words | Role | Version | Claims | Strict precision | Recall, narrator-stated facts |
|---|---|---|---|---|---|---|
| *Little Women* | 185,677 | dev | rules-v3 | 24 | 0.79 | 3 / 30 (0.10) |
| | | | rules-v6 | 33 | 0.97 | 15 / 30 (0.50) |
| *Anne of Green Gables* | 101,964 | **v4 held-out** | rules-v3 | 11 | 0.82 | 3 / 29 (0.10) |
| | | | **rules-v4** | 19 | 0.84 | **10 / 29 (0.34)** |
| *Pride and Prejudice* | 121,681 | **v4 held-out** | rules-v3 | 6 | 0.67 | 0 / 3 |
| | | | **rules-v4** | 8 | 0.63 | **1 / 3** |
| *The Secret Garden* | 80,312 | **v5 held-out** | rules-v3 | 3 | 0.67 | 1 / 25 (0.04) |
| | | | **rules-v5** | 9 | 0.78 | **5 / 25 (0.20)** |

Strict precision counts a claim as correct only when the fact is right and its modality is right
(a narrator assertion marked `asserted`, dialogue or a past state not). Bold rows are the
held-out measurements; later versions on the same books are in `bench/results/real-*.json`
(rules-v6 on all four: 69 claims, strict precision 0.94, no wrong fact).

- **Synthetic recall does not transfer.** The rules find 90% of the generator's facts and a
  fifth to a third of the explicit identity facts in held-out novels. The misses are what real
  prose does that templates do not: the owner given by the paragraph ("the brown eyes" when the
  paragraph is about Brooke), sentences without a subject ("A regular snow maiden, with blue
  eyes"), compounds ("black-eyed", "iron-gray", "bright-blue"), features joined by "and", first
  person ("my red hair") and plain euphemism (Beth's death is never written as "Beth died").
  This is the gap the LLM extractor is for, and it is far larger than the synthetic benchmark
  suggests.
- **Precision transfers better.** Across the held-out books, rules-v4 and v5 made 36 claims, of
  which one had the wrong fact. The other errors were modality: four past states in time clauses
  ("ever since he was twenty", "since Jane was sixteen", "before Anne came to Green Gables"),
  which v5 now marks `recalled`, and "might"/"perhaps" scoped over a different clause.
- **The one wrong attribution** was "He did look funny and delightful, Mary thought, with his
  round blue eyes": an introductory-phrase rule handed Dickon's eyes to Mary. rules-v6 fixes it
  (a sentence that opens with its subject pronoun keeps the phrase); v6 has not been measured on
  an unseen book.
- **No false alarms, but nothing found either.** No version raised a single contradiction on
  any of the four books. With this few facts per character there is little to compare, and none
  of these books has a well-known identity contradiction. *Anne of Green Gables* deliberately
  gives Anne eyes that "looked green in some lights and moods and gray in others"; the rules
  extracted neither colour, so the report stayed silent where an LLM extractor would need the
  author to mark the variation.
- **Pronouns on the sheet matter less on real chapters.** Without sheet pronouns, rules-v6
  infers them per chapter and finds 14 of the 15 *Little Women* facts it finds with them, 5 of 10
  in *Anne* and 5 of 6 in *The Secret Garden*, still with no wrong fact. On the synthetic
  corpus, whose chapters are short, inference recovers a third of the gain (recall 0.844 against
  0.903).

## 7. The three-chapter sample

`novelforge eval-sample` on `samples/lanternfall` (hand-written, five labelled contradictions, four
negatives): 4 found, 0 false positives, 0 of 4 negatives flagged, citation precision 1.0 (rules-v2
to rules-v6 alike). The miss is a hair-colour change written as "Her hair, cropped short since the
year of the fever, had gone the red of rust": a pronoun plus a phrasing the rules do not read.
The sample and the rules were written together, so this is a regression check, not a result.

## 8. Story logic: motives, plot holes and pacing on Chinese samples

The surface checks above compare stated facts. This benchmark measures the story-logic audit
(ARCHITECTURE.md, "Story logic"): does each key action have a reason in the text that fits the
character's background, personality and situation, do villains have reasons, does the plot hold
(knowledge leaks, deus ex machina, dangling setups), and does the pacing sag. It needs an LLM, and
the only one available was local: **qwen2.5:7b** (Q4_K_M, 4.7 GB, Ollama on the M4 GPU; temperature
0, seed 0). Claude has not been run (no API key).

**Samples.** Three original Chinese web-novel samples, eight chapters each, written and labelled by
the assistant that built the audit (no second annotator):

| Sample | Role | Labels |
|---|---|---|
| `samples/xueye-dangpu` 雪夜当铺 (3,062 characters) | development: prompts were changed after seeing its results | 6 problems (a calculating heroine with 37 coins gives 20 to a stranger out of pity; a cousin pushes her into a frozen pond "just because"; a combination lock opened with a code only two other people knew; an imperial envoy who happens to pass by; a dying mother's pendant never mentioned again; a chapter of New Year shopping) and 8 traps (look-alikes with a reason in the text: a bribe that buys information, an uncle with gambling debts, a loan explained five chapters later, knowledge from a past life...) |
| `samples/qingshi-du` 青石渡 (1,989 characters) | **held out**: written before the dev runs were scored, run once with the frozen prompts | 6 problems of the same kinds in a different setting and wording, 4 traps, 2 ambiguous cases |
| `samples/xueye-dangpu-revised` 雪夜当铺（修订版） (3,717 characters) | a revision of the dev sample written from the audit's findings | the 6 fixed places as traps plus the original 8 traps; no planted problems |

**Scoring** (`narrative/score.py`). A problem is found when an issue of an accepted kind is in the
labelled chapter, on the labelled character, with its quote in a labelled paragraph; an issue at
the right place with a different diagnosis is reported separately. A trap is set off by a problem
verdict on it. Issues on no label are listed for a person to judge, not counted as false alarms.

### Prompt history on the development sample

| Prompts | How the model is asked | Problems found | Traps set off | Issues on no label |
|---|---|---|---|---|
| draft (qwen2.5:3b) | verdict per beat, batched | 2 / 6 | 1 / 8 | 5 |
| story-v1 | verdict per beat, batched | 1 / 6 | 0 / 8 | 6 |
| story-v2 | sub-questions per beat, verdict computed in code; rescue check; payoff check per setup | 4 / 6 | 1 / 8 | 7 |
| story-v3 (frozen `1860fc6`) | beats and chapter shape asked separately; setups carry a key word; a per-beat source check for secrets | 5 / 6, **4 / 6** after the fix below | 1 / 8 | 1 |

Asked for a verdict directly (v1), the 7B model called 15 of the 18 judged beats consistent and
cited nothing (it wrote note IDs into the motive text), so the code downgraded them to "not grounded"
and almost nothing was found. Splitting the judgement into questions it can answer (is this a
choice that needs a reason? which note gives the reason? what does it go against?) and computing
the verdict by rule is what moved the numbers; the rule also refuses dislike as a motive, which
is how "she just could not stand her" became villainy without cause. The dev numbers are tuned
on the sample and are not a result.

One of the five v3 hits was an accident. Reviewing the dev output after the held-out run showed
the heroine's gift flagged as going against a note that said she was "kind-hearted", and that
note had been read off the gift itself. Circular citations were already refused as reasons but
not as conflicts; they now are (a code change, prompts untouched), and all three runs were
re-scored from their recordings: the dev sample drops to 4/6, the held-out and revised numbers
do not change. The fix came from the dev sample, so the held-out numbers below stay blind.

### Frozen prompts on the held-out and revised samples (one run each)

| Sample | Problems found | Flagged at the place, other diagnosis | Traps set off | Issues on no label | Calls, tokens, model time |
|---|---|---|---|---|---|
| 青石渡 (held out) | **2 / 6** (the timid heroine stealing the ledger, flagged as against her character, which the label accepts; the flat chapter) | +1 (the classmate's malice called "against the character") | **1 / 4** | 5 | 51 calls, 33,420 in / 8,659 out, 1,066 s |
| 雪夜当铺（修订版） | none planted | | **0 / 14** | 5 | 61 calls, 51,291 in / 11,538 out, 1,484 s |

Commands: `novelforge audit-story qingshi-du --llm ollama:qwen2.5:7b` (and `xueye-dangpu-revised`),
reports in `bench/results/story-*-story-v3.md`, every response in `bench/results/llm-cache/`.
`--replay` re-scores a recording with the current code and loads no model.

- **On unseen text the 7B model finds a third of the problems.** The held-out drop from 5/6 to 2/6
  is the size of the tuning on the dev sample. The misses are reading errors the checks cannot
  repair: for the heroine who slaps a warlord's son despite being written as timid, the model
  invented a motive ("her uncle's threats humiliated her") and cited as its grounds the very notes
  it also named as conflicts (the timid character sheet, her fear of troubling her uncle's
  family), which the code accepted because the notes exist; the rescuer from overseas was attributed to the
  warlord's son, who appears earlier, so the rescue check never ran; the dying father's letter was
  extracted as a setup without a quote and rejected.
- **The fixes are recognised.** On the revised sample none of the 14 traps is set off: the gift
  that now repays a past-life kindness, the cousin with a marriage at stake, the code learned in a
  past life, the envoy the heroine summoned herself, the pendant redeemed at a money shop, the
  shopping chapter with a hook.
- **Most extra issues are noise.** Of the 10 issues on no label across the two frozen runs, two
  are defensible minor notes (two chapters of the revision end quietly). The other eight are
  misreadings: two causality claims that contradict the text, four "against the character"
  verdicts on routine scenes (hearing news, meeting the headmaster), and two "dangling setups"
  that were paid off in other words (the warlord's moved ledger is found as "the blue ledger").
- **The checks do their part.** Over the three frozen runs, 45 model outputs were refused (quotes
  not in the text, setups without a quote, a cause without an effect) and 200 quotes were located
  (174 exactly, 4 after punctuation normalisation, 11 as the real sentence of a stitched quote,
  11 by sentence similarity). The computed verdict differs from the model's raw answers in 14
  places: 6 cited reasons that were missing, circular or not shown (now "not grounded"), 6 beats
  the model called routine while naming a conflicting note (now "against the character"), 1
  dislike refused as a motive, 1 loan explained by a later reveal.
- **Not measured: a capable model.** The prompts and checks are the same for Claude
  (`--llm anthropic`); how far they get with a stronger reader is the open question, and the
  held-out sample has to be replaced by a new one before it is used to judge another model.

## 9. Chinese continuity facts (rules-zh)

The rule extractor reads Chinese chapters with `core/extraction_zh.py` (ARCHITECTURE.md,
"Extraction") and feeds the same contradiction detectors as English. Each sample is labelled
twice: every statement of a checked predicate about a listed character (`facts:`, asserted or
not, scored by `novelforge eval-facts`: claim precision and recall), and planted contradictions
with look-alike negatives (`novelforge eval-sample`: findings).

**Protocol.** The development sample 雾港信札 (3 chapters) was written together with v1. Each
held-out novel (4 chapters, about 7,700 characters, 9 contradictions, 9 negatives, 52 to 61
facts) was written by a separate agent session. The session was told not to read the
extractor, its tests or the other samples, and to report only counts. Its novel was then scored
once with the version frozen before it arrived; the commit is noted in its `novel.yaml`. The
failures on that novel produced the next version, which was scored on the next novel. Each
held-out number is therefore blind for exactly one version, and the later rows on the same
novel are not.

| Sample | Version | Contradictions found | False findings | Negatives flagged | Claim precision (strict) | Claim recall (asserted facts) |
|---|---|---|---|---|---|---|
| 雾港信札 (dev) | v1, v2, v3 | 7 / 7 | 0 | 0 / 6 | 1.0 (1.0) | 0.903 (0.958) |
| 临江镖旗 (镖局, held out for v1) | **v1, blind** | **3 / 9** | **2** | **1 / 9** | 0.833 (0.833) | 0.385 (0.405) |
| | v2 / v3, seen | 6 / 9, 7 / 9 | 0 | 0 / 9 | 1.0 (1.0) | 0.75 (0.838) |
| 雾岭茶事 (茶山, held out for v2) | **v2, blind** | **5 / 9** | **2** | **2 / 9** | 0.947 (0.868) | 0.59 (0.625) |
| | v3, seen | 8 / 9 | 0 | 0 / 9 | 1.0 (0.974) | 0.639 (0.688) |
| 太液秋深 (宫廷, held out for v3) | **v3, blind** | **5 / 9** | **3** | **3 / 9** | 1.0 (0.944) | 0.621 (0.70) |

The v3 blind row counts two canon findings that were scored as false when they arrived. The
scorer reads a label's last evidence item as the conflicting statement, and that writer had put
the agreeing sentence last. Both findings cite the right sentence. Their labels' evidence order
was fixed, with a comment in the file. As first scored the result was 3 / 9 with 5 false
findings; that result is kept in `findings-taiye-qiushen-rules-zh-v3-as-labelled.json`.

- **On unseen text the rules find about half of the planted contradictions** (v2 and v3), up from
  a third (v1), and raise two or three false findings per novel. The extracted facts are almost
  always right (blind precision 0.95 to 1.0); the false findings come from context the rules
  miss around them. v1: 她 given to the wrong woman (这姑娘 stood between), and a lesson missed
  because another name sat in the sentence (照雪跟着苏砚学会了骑马), so her later riding looked
  impossible. v2: the old colour in 把一头黑发染成了银白色 read as current, and an age given to the
  name after 跟着. v3: a skill learned by being taught (裴照教他凫水), hair revealed chapters later
  to have been dyed all along, and a past age with its time word in front (那年他才四岁).
- **Misses** are pronoun chains the resolver declines (two women in the previous sentence),
  roundabout statements (她的第一声啼哭是落在于阗 for a birthplace, 墨一样的眼睛), an action
  between the name and the stage verb (孙嬷嬷撑着一把青绸伞站在她身后), and idioms not in the lists
  (一个字也不认得).
- **Each version fixed its novel and the next novel brought new phrasings.** Blind recall of
  facts went from 0.385 to about 0.6 and then stayed there. That is the long tail rules cannot
  follow, and it is what the LLM extractor is for. The LLM extraction prompt is still English
  and has not been run on Chinese.
- **No false alarms on the story samples.** On 雪夜当铺, 青石渡 and the revision (24 chapters
  not written for this check) v3 makes 6, 3 and 9 claims, mostly characters on stage. All were
  checked by hand, and none raises a finding.
- The held-out labels are the writing sessions' own; no second annotator checked them, and the
  writers were not told the scorer's conventions (hence the evidence-order fix above).

Commands: `novelforge eval-sample linjiang-biaoqi` and `novelforge eval-facts linjiang-biaoqi`
(likewise `wugang-xinzha`, `wuling-chashi`, `taiye-qiushen`). Results are in
`bench/results/findings-*-rules-zh-vN.json` and `facts-*-rules-zh-vN.{json,md}`.

## Reproducing

```bash
make setup                                   # or: cd backend && uv sync --extra localdb --extra embeddings
bench/run_all.sh                             # corpora + every table above (about 30 min on an M4)
cd backend && uv run novelforge bench-consistency ../bench/corpora/syn-100-s7 --embedder fastembed
uv run novelforge bench-real the-secret-garden   # downloads the book once, scores the labels
uv run novelforge bench-real anne-of-green-gables \
    --claims ../bench/results/real-claims/claims-anne-of-green-gables-rules-v4.jsonl  # a frozen version
uv run novelforge audit-story qingshi-du --llm ollama:qwen2.5:7b --replay   # story logic, from the recording
```

- Corpora are byte-identical for the same seed, chapter count, filler and generator version.
- Each JSON in `bench/results/` records the corpus, generator version, embedder, reranker,
  extractor, machine and (from `bc2ddf6` on) the git commit.
- Models: BAAI/bge-small-en-v1.5 and ms-marco-MiniLM-L-6-v2 via fastembed 0.8.1 (ONNX, CPU).
  Retrieval scores are deterministic; latencies vary with machine load.

## Known gaps and next steps

- **Story logic has been measured with a 7B local model only** (section 8): a third of the
  held-out problems found, one trap in four set off, and about five noisy issues per novel. The
  checks keep its output grounded but cannot make it read better. Claude is the obvious next
  run, on a fresh held-out sample. Three v4 rules are suggested by the held-out misses and not yet
  applied (they would be tuned on it): a note cited both as the reason and as a conflict cannot be
  the reason; a reason note must name the beat's target or share words with it, as later
  explanations already must; a setup without a quote could be kept when its key word is in the
  chapter. Checked against the recorded answers, the first would not find H1 on its own (the
  invented motive also cites a second note that restates the conflict) and would add a false
  alarm on the revision, where the model cites the cousin's real motive both as reason and as
  conflict; it is not applied.
- **Chinese continuity checks find about half of what is planted in unseen novels** (section 9),
  with two or three false findings each. The next steps are a skill learned by being taught,
  changes revealed after the fact, and time words before an age. Beyond that the LLM extractor
  needs a Chinese prompt and a run.

- **No hosted-model run.** Claude is wired in (official SDK, structured outputs, fallbacks) and
  tested against a fake client, but no API key was available. `--extractor anthropic` runs every
  benchmark unchanged.
- **Small local model only.** The one LLM run is qwen2.5:3b on 15 chapters (section 5), which
  is far below the rule baseline; it tests the pipeline and its guardrails, not LLM extraction.
  It has not been run on the real-prose books.
- **World rules are undetected without an LLM.** All 28 planted rule violations at 1,000 chapters
  are missed by the rule baseline; the LLM judge is the only path.
- **Rules read a fifth to a third of real prose.** On held-out novels the rules find 20 to 34%
  of explicitly stated identity facts (section 6). Real-prose recall is what an LLM run should be
  judged on: `bench-real` scores any extractor's claims against the same labels.
- **Contradiction detection on real prose is unmeasured.** No version raised a finding on the
  four novels, so there is no real-prose detection recall. Measuring it needs a manuscript with
  known continuity errors (an author's draft, or errors planted in real text).
- **The real-prose labels are not independent.** They were made by the assistant that wrote the
  rules, with the notes field recording each judgement call; a second annotator would show how
  stable they are. The keyword filter also bounds the recall estimate from above.
- **Hedge scope.** "might" and "perhaps" hedge their whole clause, so "so that she might see
  Matthew's kindly brown eyes" marks the colour as hedged. Three of the eight held-out errors.
