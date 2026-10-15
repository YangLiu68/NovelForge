"""Second-stage rerankers over a short candidate list.

- `none`: keep the first-stage order.
- `lexical`: deterministic query-term overlap with IDF weights computed over the candidates
  (a mock with no model; used in tests and CI).
- `cross-encoder:<model>`: a local ONNX cross-encoder via fastembed
  (default Xenova/ms-marco-MiniLM-L-6-v2).
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Protocol

from novelforge.core.text import tokens


class Reranker(Protocol):
    name: str

    def score(self, query: str, passages: list[str]) -> list[float]: ...


class NoReranker:
    name = "none"

    def score(self, query: str, passages: list[str]) -> list[float]:
        return [float(-i) for i in range(len(passages))]


class LexicalReranker:
    name = "lexical"

    def score(self, query: str, passages: list[str]) -> list[float]:
        q = set(tokens(query))
        docs = [tokens(p) for p in passages]
        n = len(docs) or 1
        df = {t: sum(1 for d in docs if t in d) for t in q}
        out = []
        for d in docs:
            dset = set(d)
            matched = sum(math.log(1 + n / df[t]) for t in q if t in dset)
            out.append(matched / math.sqrt(1 + len(d) / 40))  # mild length normalisation
        return out


class CrossEncoderReranker:
    def __init__(self, model: str, cache_dir: str):
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        self._model = TextCrossEncoder(model, cache_dir=cache_dir)
        self.name = f"cross-encoder:{model}"

    def score(self, query: str, passages: list[str]) -> list[float]:
        return [float(s) for s in self._model.rerank(query, passages, batch_size=32)]


@lru_cache(maxsize=4)
def get_reranker(spec: str) -> Reranker:
    from novelforge.config import get_settings

    kind, _, arg = spec.partition(":")
    if kind == "none":
        return NoReranker()
    if kind == "lexical":
        return LexicalReranker()
    if kind == "cross-encoder":
        return CrossEncoderReranker(
            arg or "Xenova/ms-marco-MiniLM-L-6-v2",
            str(get_settings().model_cache_dir / "fastembed"),
        )
    raise ValueError(f"unknown reranker '{spec}'")
