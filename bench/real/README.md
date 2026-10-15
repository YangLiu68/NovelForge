# Real-prose evaluation

The synthetic benchmarks know every answer, but their prose comes from the generator's
templates, and the rule extractor was improved against those templates. This evaluation runs
the extractor and the contradiction report on four public-domain novels that nobody wrote for
NovelForge:

| Book | Role | Gutenberg file |
|---|---|---|
| *Little Women* (Alcott) | **dev**: failure analysis and rule changes were allowed to look at it | [#514](https://www.gutenberg.org/ebooks/514) |
| *Anne of Green Gables* (Montgomery) | **v4 held-out**: scored only after rules-v4 was frozen; its errors then shaped v5 | [#45](https://www.gutenberg.org/ebooks/45) |
| *Pride and Prejudice* (Austen) | **v4 held-out**, as above | [#42671](https://www.gutenberg.org/ebooks/42671) |
| *The Secret Garden* (Burnett) | **v5 held-out**: added after rules-v5 was frozen, scored once | [#113](https://www.gutenberg.org/ebooks/113) |

```bash
cd backend
uv run novelforge bench-real little-women            # downloads the text once, scores the labels
uv run novelforge bench-real little-women --no-sheet-pronouns   # ablation: pronouns inferred
```

The text is downloaded into `bench/corpora/real/` (not committed) and checked against the
SHA-256 in [books.yaml](books.yaml); Gutenberg revises files, so a mismatch is reported. The
cast lists in `books.yaml` (names, aliases, pronouns) were written by hand from the books, the
way an author would fill in character sheets. They contain no attributes, so the report can
only find text-against-text contradictions.

## What is measured

There is no complete ground truth for a novel, so the evaluation has two parts:

- **Precision.** Every claim the extractor makes, and every finding the report raises, is
  judged. A claim label says whether the fact is right (the quote states this value for this
  character) and whether the narrator asserts it there; a claim is *correct* when the fact is
  right and its modality agrees, *modality* when only the modality is wrong, and *wrong*
  otherwise (with a cause: figurative, word sense, negation, wrong character, ...).
- **Recall, estimated.** A keyword filter (`CANDIDATE` in `novelforge/bench/real_text.py`)
  selects every sentence that might state an eye colour, hair colour, age, birthplace,
  handedness or death. Each candidate sentence is labelled with the facts it states about
  listed characters, including facts whose owner is clear only from the paragraph ("the brown
  eyes" when the paragraph is about Brooke) and facts in dialogue. Facts stated without those
  keywords (Beth's death in *Little Women* is never written as "Beth died") are outside the
  estimate, so it overstates true recall.

Labels live in `labels/<book>.jsonl`, keyed by content (chapter, character, predicate, value,
quote, occurrence; or chapter and sentence), never by extractor version or offsets. A rerun
scores what is labelled and writes the rest to a to-do file, so a new extractor version only
needs its new claims judged.

**Who labelled.** The labels were made by the AI coding assistant that built NovelForge, by
reading each quote in its paragraph (the notes field records the judgement calls). They are
not independent human annotations, and the person who wrote the rules also judged them. The
held-out protocol below limits, but does not remove, that bias.

## Protocol

1. rules-v3 (the version benchmarked on synthetic text) was run on the dev book; every claim
   and candidate sentence was labelled.
2. The dev failures drove rules-v4 (pronoun and "with"-phrase attribution, ages in apposition,
   word-sense and negation guards, hedge scope, title handling). Each change was checked
   against the synthetic benchmarks as well.
3. rules-v4 was frozen (commit `ef1f062`) before either held-out book was run.
4. Both versions were then run on the two held-out books, and all their claims, findings and
   candidate sentences were labelled.
5. Four of the six held-out errors were one kind, a past state in a time clause ("ever since
   he was twenty"); rules-v5 handles it, so those two books stopped being unseen for v5. The
   other two ("might" hedging a different part of the sentence) are left as they are.
6. rules-v5 was frozen (commit `f29b4d3`), a fourth book was added, and it was run and
   labelled once. The cast list was written before its text was read.

Results and their discussion are in [BENCHMARK.md](../../BENCHMARK.md#6-real-prose);
raw reports are `bench/results/real-*.json`.
