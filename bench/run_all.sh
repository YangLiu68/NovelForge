#!/usr/bin/env bash
# Regenerate every corpus and every number in BENCHMARK.md (except the LLM rows, which need a
# model; see BENCHMARK.md). Corpora are deterministic: same seed and generator version, same files.
# Usage: bench/run_all.sh            (from the repository root; needs `uv sync --extra embeddings`)
set -euo pipefail
cd "$(dirname "$0")/../backend"
OUT=../bench/results
C=../bench/corpora
mkdir -p "$OUT" "$C"

uv run novelforge gen-corpus --chapters 100 --seed 7 --out "$C/syn-100-s7"
uv run novelforge gen-corpus --chapters 1000 --seed 7 --out "$C/syn-1000-s7"
uv run novelforge gen-corpus --chapters 100 --seed 7 --filler 25 --out "$C/load-100-s7"
uv run novelforge gen-corpus --chapters 1000 --seed 7 --filler 25 --out "$C/load-1000-s7"

# Sample smoke check (three hand-written chapters)
uv run novelforge eval-sample --json > "$OUT/sample-lanternfall-rules-v6.json"

# Chinese continuity facts: the dev sample and three held-out novels (rules-zh)
for sample in wugang-xinzha linjiang-biaoqi wuling-chashi taiye-qiushen; do
  uv run novelforge eval-sample "$sample" --json > "$OUT/findings-$sample-rules-zh-v3.json"
  uv run novelforge eval-facts "$sample" --out "$OUT" > /dev/null
done

# Retrieval: mock embedder, then real local models (bge-small + MiniLM cross-encoder)
uv run novelforge bench-retrieval "$C/syn-100-s7" --embedder hash --reranker lexical --out "$OUT"
uv run novelforge bench-retrieval "$C/syn-100-s7" --embedder fastembed --reranker cross-encoder --out "$OUT"
uv run novelforge bench-retrieval "$C/syn-1000-s7" --embedder fastembed --reranker cross-encoder --out "$OUT"

# Extraction quality of the rule baseline (and the pronoun ablation)
uv run novelforge bench-extraction "$C/syn-100-s7" --extractor rules --out "$OUT"
uv run novelforge bench-extraction "$C/syn-1000-s7" --extractor rules --out "$OUT"
uv run novelforge bench-extraction "$C/syn-1000-s7" --extractor rules --no-sheet-pronouns --out "$OUT"

# Real prose: four public-domain novels (downloaded once), scored against bench/real/labels
for book in little-women anne-of-green-gables pride-and-prejudice the-secret-garden; do
  uv run novelforge bench-real "$book" --out "$OUT"
  uv run novelforge bench-real "$book" --no-sheet-pronouns --out "$OUT"
  for v in v3 v4 v5; do
    uv run novelforge bench-real "$book" --claims "$OUT/real-claims/claims-$book-rules-$v.jsonl" --out "$OUT"
  done
done

# Story logic on the Chinese samples: re-scored from the recorded qwen2.5:7b answers (no model
# needed). With Ollama running, drop --replay to call the model for anything not recorded.
for sample in xueye-dangpu qingshi-du xueye-dangpu-revised; do
  uv run novelforge audit-story "$sample" --llm ollama:qwen2.5:7b --replay --out "$OUT"
done

# Contradiction detection with the memory ablation
uv run novelforge bench-consistency "$C/syn-100-s7" --extractor rules --embedder fastembed --out "$OUT"
uv run novelforge bench-consistency "$C/syn-1000-s7" --extractor rules --embedder fastembed --out "$OUT"

# Load tests
uv run novelforge bench-load "$C/load-100-s7" --out "$OUT"
uv run novelforge bench-load "$C/load-1000-s7" --out "$OUT"
