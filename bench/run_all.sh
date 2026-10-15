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
uv run novelforge eval-sample --json > "$OUT/sample-lanternfall-rules-v2.json"

# Retrieval: mock embedder, then real local models (bge-small + MiniLM cross-encoder)
uv run novelforge bench-retrieval "$C/syn-100-s7" --embedder hash --reranker lexical --out "$OUT"
uv run novelforge bench-retrieval "$C/syn-100-s7" --embedder fastembed --reranker cross-encoder --out "$OUT"
uv run novelforge bench-retrieval "$C/syn-1000-s7" --embedder fastembed --reranker cross-encoder --out "$OUT"

# Extraction quality of the rule baseline
uv run novelforge bench-extraction "$C/syn-100-s7" --extractor rules --out "$OUT"
uv run novelforge bench-extraction "$C/syn-1000-s7" --extractor rules --out "$OUT"

# Contradiction detection with the memory ablation
uv run novelforge bench-consistency "$C/syn-100-s7" --extractor rules --embedder fastembed --out "$OUT"
uv run novelforge bench-consistency "$C/syn-1000-s7" --extractor rules --embedder fastembed --out "$OUT"

# Load tests
uv run novelforge bench-load "$C/load-100-s7" --out "$OUT"
uv run novelforge bench-load "$C/load-1000-s7" --out "$OUT"
