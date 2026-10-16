#!/usr/bin/env bash
# Same steps as run_all.sh, each under its own short lease from this machine's resource
# manager (~/.resmgr/rq), so they can be backfilled between other sessions' jobs.
set -euo pipefail
cd "$(dirname "$0")/../backend"
OUT=../bench/results
C=../bench/corpora
RQ=~/.resmgr/rq
mkdir -p "$OUT" "$C"
nf() { uv run novelforge "$@"; }

nf gen-corpus --chapters 100 --seed 7 --out "$C/syn-100-s7"
nf gen-corpus --chapters 1000 --seed 7 --out "$C/syn-1000-s7"
nf gen-corpus --chapters 100 --seed 7 --filler 25 --out "$C/load-100-s7"
nf gen-corpus --chapters 1000 --seed 7 --filler 25 --out "$C/load-1000-s7"
nf eval-sample --json > "$OUT/sample-lanternfall-rules-v6.json"
for s in wugang-xinzha linjiang-biaoqi wuling-chashi taiye-qiushen; do  # Chinese facts, rules-zh
  nf eval-sample "$s" --json > "$OUT/findings-$s-rules-zh-v3.json"; nf eval-facts "$s" --out "$OUT" > /dev/null
done

$RQ run -c 1 -m 1 -t 2 -w "novelforge bench: retrieval 100 hash" -- \
  uv run novelforge bench-retrieval "$C/syn-100-s7" --embedder hash --reranker lexical --out "$OUT"
$RQ run -c 2 -m 2 -t 4 -w "novelforge bench: retrieval 100 bge+minilm" -- \
  uv run novelforge bench-retrieval "$C/syn-100-s7" --embedder fastembed --reranker cross-encoder --out "$OUT"
$RQ run -c 1 -m 1 -t 2 -w "novelforge bench: extraction rules 100+1000" -- \
  bash -c "uv run novelforge bench-extraction $C/syn-100-s7 --out $OUT && uv run novelforge bench-extraction $C/syn-1000-s7 --out $OUT && uv run novelforge bench-extraction $C/syn-1000-s7 --no-sheet-pronouns --out $OUT"
$RQ run -c 1 -m 1 -t 4 -w "novelforge bench: real prose (4 books)" -- bash -c '
  for book in little-women anne-of-green-gables pride-and-prejudice the-secret-garden; do
    uv run novelforge bench-real "$book" --out "$1" && uv run novelforge bench-real "$book" --no-sheet-pronouns --out "$1"
  done' x "$OUT"
# Story logic: replayed from the recorded qwen2.5:7b answers, so no model and little memory.
nf_story() { for s in xueye-dangpu qingshi-du xueye-dangpu-revised; do
  uv run novelforge audit-story "$s" --llm ollama:qwen2.5:7b --replay --out "$OUT" || return 1; done; }
nf_story
$RQ run -c 2 -m 2 -t 4 -w "novelforge bench: consistency 100" -- \
  uv run novelforge bench-consistency "$C/syn-100-s7" --embedder fastembed --out "$OUT"
$RQ run -c 1 -m 1 -t 3 -w "novelforge bench: load 100" -- \
  uv run novelforge bench-load "$C/load-100-s7" --out "$OUT"
$RQ run -c 2 -m 2 -t 10 -w "novelforge bench: retrieval 1000 bge+minilm" -- \
  uv run novelforge bench-retrieval "$C/syn-1000-s7" --embedder fastembed --reranker cross-encoder --out "$OUT"
$RQ run -c 2 -m 2 -t 10 -w "novelforge bench: consistency 1000" -- \
  uv run novelforge bench-consistency "$C/syn-1000-s7" --embedder fastembed --out "$OUT"
$RQ run -c 2 -m 2 -t 8 -w "novelforge bench: load 1000" -- \
  uv run novelforge bench-load "$C/load-1000-s7" --out "$OUT"
