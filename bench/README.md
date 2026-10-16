# Benchmark data

- `run_all.sh` regenerates the corpora below and every number in `../BENCHMARK.md`
  (except the local-LLM rows, whose command is listed there). `run_all_leased.sh` runs the same
  steps, each under a lease from the development machine's shared resource manager; elsewhere use
  `run_all.sh`.
- `results/llm-cache/` records every local-LLM response (keyed by model, prompt and schema),
  so an LLM benchmark can be replayed and re-scored without the model.
- `corpora/` (git-ignored) holds generated novels. They are deterministic: the same seed,
  chapter count, filler and generator version produce byte-identical files.
- `results/` holds the JSON and markdown output of each benchmark run, with the git commit,
  machine and settings recorded inside the JSON.
- `real/` is the real-prose benchmark: four public-domain novels (downloaded into
  `corpora/real/` at run time), their cast lists and the hand labels; see
  [real/README.md](real/README.md). `results/real-claims/` keeps the claims of each frozen
  extractor version so old versions can be rescored without checking them out.
- Story logic (BENCHMARK.md section 8) runs on the Chinese samples in `../samples/`
  (`xueye-dangpu` dev, `qingshi-du` held out, `xueye-dangpu-revised`), labelled in each
  sample's `narrative_truth.yaml`. `results/story-*-story-vN.*` are the reports per prompt
  version; `novelforge audit-story SAMPLE --llm ollama:qwen2.5:7b --replay` re-scores the recorded
  responses with the current code.

- Chinese continuity facts (BENCHMARK.md section 9) run on `../samples/wugang-xinzha` (dev) and
  the held-out `linjiang-biaoqi`, `wuling-chashi`, `taiye-qiushen`, labelled in each sample's
  `ground_truth.yaml` (`contradictions`, `negatives`, `facts`). `results/findings-*-rules-zh-vN`
  and `results/facts-*-rules-zh-vN` are the scores per extractor version.

| Corpus | Command | Used for |
|---|---|---|
| `syn-100-s7` | `novelforge gen-corpus --chapters 100 --seed 7` | retrieval, extraction, consistency |
| `syn-1000-s7` | `novelforge gen-corpus --chapters 1000 --seed 7` | retrieval and consistency at scale |
| `syn-40-s7` | `novelforge gen-corpus --chapters 40 --seed 7` | local-LLM extraction slice |
| `load-100-s7`, `load-1000-s7` | `... --filler 25` (about 1,250 words per chapter) | load tests |
| `corpora/real/*.txt` | downloaded by `novelforge bench-real BOOK` | real-prose precision and recall |
