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

| Corpus | Command | Used for |
|---|---|---|
| `syn-100-s7` | `novelforge gen-corpus --chapters 100 --seed 7` | retrieval, extraction, consistency |
| `syn-1000-s7` | `novelforge gen-corpus --chapters 1000 --seed 7` | retrieval and consistency at scale |
| `syn-40-s7` | `novelforge gen-corpus --chapters 40 --seed 7` | local-LLM extraction slice |
| `load-100-s7`, `load-1000-s7` | `... --filler 25` (about 1,250 words per chapter) | load tests |
