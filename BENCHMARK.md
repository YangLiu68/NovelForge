# Benchmark

Every number in this file was produced by a committed command on recorded data. The corpora are
generated deterministically from a seed, so anyone can rebuild them and rerun the commands:

```bash
bench/run_all.sh        # regenerates the corpora and every result below (~30 min on CPU)
```

Raw outputs, including the git commit and machine for each run, are in [bench/results/](bench/results).
The main results were run at commit `2572c56`, generator version 3, seed 7. Hardware: Apple M4,
16 GB, macOS 15.3, Python 3.12.10, PostgreSQL 16.2 + pgvector 0.6.2 (embedded `pgserver`). The
machine was shared with other jobs, so latencies are indicative, not tuned peaks.

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

Command: `novelforge bench-retrieval bench/corpora/syn-100-s7 --embedder fastembed --reranker cross-encoder`.
Embedder: BAAI/bge-small-en-v1.5 (local ONNX, CPU). Reranker: ms-marco-MiniLM-L-6-v2 cross-encoder
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
statement and overlaps its sentence.

| Predicate | Precision | Recall (100 ch) | Recall (1,000 ch) |
|---|---|---|---|
| all scored | 1.000 | 0.777 | 0.784 |
| location | 1.000 | 1.000 | 1.000 |
| abilities (cannot / learned) | 1.000 | 1.000 | 1.000 |
| death | 1.000 | 1.000 | 1.000 |
| age | 1.000 | 0.813 | 0.749 |
| hair colour | 1.000 | 0.739 | 0.705 |
| birthplace | 1.000 | 0.519 | 0.672 |
| eye colour | 1.000 | 0.581 | 0.586 |
| handedness | 1.000 | 0.242 | 0.307 |

1,000 chapters extracted in 5.0 s. Every hedged, dialogue and memory negative the extractor touched
was kept out of `asserted` (42 of 42). World rules, foreshadowing and causal links: 0% (the rules do
not read them).

**Failure analysis by phrasing** (1,000 chapters): the rules find 100% of statements anchored on a
name ("Mara's eyes were grey", "Tomas was born in Varrow", "The thirty-six-year-old Mara") and 0% of
these:

| Phrasing | Missed | Example |
|---|---|---|
| pronoun | 138 | "Mara looked up, her grey eyes narrowing" |
| indirect birthplace | 88 | "had grown up in Ashford, where she was born" |
| handedness by implication | 178 | "Being left-handed, …", "wrote with his left hand" |
| age by preposition | 69 | "At thirty-one, Mara had stopped expecting letters" |
| colour by simile | 67 | "eyes the colour of sea glass" |

Location day accuracy is 1,013 of 1,027: the 14 misses are journeys stated with an in-chapter
offset ("Three days later Tomas was in Varrow"), which only the LLM schema's `day_offset` captures.
This is the gap the LLM extractor exists to close; see section 5.
