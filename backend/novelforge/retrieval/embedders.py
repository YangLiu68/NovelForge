"""Text embedders behind one interface.

- `hash`: deterministic feature hashing of stemmed words and bigrams. No model, no network,
  identical on every machine. It is a LEXICAL mock used for tests and CI; it does not
  understand meaning, and benchmark tables label it as such.
- `fastembed:<model>`: local ONNX models on CPU (default BAAI/bge-small-en-v1.5, 384 dims).
- `ollama:<model>`: a local Ollama server (`/api/embed`).
- `openai:<model>`: any OpenAI-compatible `/v1/embeddings` endpoint.

Every call returns vectors plus a token count; `tokens_exact` says whether the count came from
the provider or is an estimate.
"""

from __future__ import annotations

import hashlib
import math
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

import httpx

from novelforge.core.text import tokens


@dataclass
class EmbedResult:
    vectors: list[list[float]]
    tokens: int
    tokens_exact: bool


class Embedder(Protocol):
    name: str
    dim: int
    local: bool

    def embed_documents(self, texts: list[str]) -> EmbedResult: ...

    def embed_query(self, text: str) -> EmbedResult: ...


def _estimate_tokens(texts: list[str]) -> int:
    # ~1.3 tokens per English word for WordPiece/BPE tokenizers; flagged as an estimate.
    return int(sum(len(t.split()) for t in texts) * 1.3)


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


class HashEmbedder:
    local = True

    def __init__(self, dim: int = 384):
        self.dim = dim
        self.name = f"hash:{dim}"

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        toks = tokens(text)
        feats = [(t, 1.0) for t in toks] + [
            (f"{a}_{b}", 0.5) for a, b in zip(toks, toks[1:], strict=False)
        ]
        for feat, weight in feats:
            h = int.from_bytes(hashlib.blake2b(feat.encode(), digest_size=8).digest(), "big")
            vec[h % self.dim] += weight if (h >> 63) & 1 else -weight
        return _normalize(vec)

    def embed_documents(self, texts: list[str]) -> EmbedResult:
        return EmbedResult([self._vector(t) for t in texts], _estimate_tokens(texts), False)

    def embed_query(self, text: str) -> EmbedResult:
        return self.embed_documents([text])


class FastEmbedEmbedder:
    local = True

    def __init__(self, model: str, cache_dir: str):
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model, cache_dir=cache_dir)
        self.name = f"fastembed:{model}"
        self.dim = len(next(iter(self._model.embed(["probe"]))))

    def _count(self, texts: list[str]) -> int:
        tokenizer = getattr(getattr(self._model, "model", None), "tokenizer", None)
        if tokenizer is None:
            return -1
        return sum(len(e.ids) for e in tokenizer.encode_batch(texts))

    def embed_documents(self, texts: list[str]) -> EmbedResult:
        vectors = [v.tolist() for v in self._model.embed(texts, batch_size=64)]
        count = self._count(texts)
        return EmbedResult(vectors, count if count >= 0 else _estimate_tokens(texts), count >= 0)

    def embed_query(self, text: str) -> EmbedResult:
        vectors = [v.tolist() for v in self._model.query_embed([text])]
        count = self._count([text])
        return EmbedResult(vectors, count if count >= 0 else _estimate_tokens([text]), count >= 0)


class OllamaEmbedder:
    local = True

    def __init__(self, model: str, url: str):
        self.model, self.url = model, url.rstrip("/")
        self.name = f"ollama:{model}"
        self.dim = len(self.embed_documents(["probe"]).vectors[0])

    def embed_documents(self, texts: list[str]) -> EmbedResult:
        r = httpx.post(
            f"{self.url}/api/embed", json={"model": self.model, "input": texts}, timeout=120
        )
        r.raise_for_status()
        data = r.json()
        count = data.get("prompt_eval_count")
        return EmbedResult(
            [_normalize(v) for v in data["embeddings"]],
            int(count) if count is not None else _estimate_tokens(texts),
            count is not None,
        )

    def embed_query(self, text: str) -> EmbedResult:
        return self.embed_documents([text])


class OpenAICompatibleEmbedder:
    local = False

    def __init__(self, model: str, base_url: str, api_key: str):
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for openai:* embedders")
        self.model, self.base_url, self._key = model, base_url.rstrip("/"), api_key
        self.name = f"openai:{model}"
        self.dim = len(self.embed_documents(["probe"]).vectors[0])

    def embed_documents(self, texts: list[str]) -> EmbedResult:
        r = httpx.post(
            f"{self.base_url}/embeddings",
            headers={"Authorization": f"Bearer {self._key}"},
            json={"model": self.model, "input": texts},
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()
        vectors = [d["embedding"] for d in sorted(data["data"], key=lambda d: d["index"])]
        usage = data.get("usage", {}).get("prompt_tokens")
        return EmbedResult(
            vectors, int(usage) if usage is not None else _estimate_tokens(texts), usage is not None
        )

    def embed_query(self, text: str) -> EmbedResult:
        return self.embed_documents([text])


DEFAULT_ARGS = {
    "hash": "384",
    "fastembed": "BAAI/bge-small-en-v1.5",
    "ollama": "nomic-embed-text",
    "openai": "text-embedding-3-small",
}


def canonical(spec: str) -> str:
    """'hash' -> 'hash:384', 'fastembed' -> 'fastembed:BAAI/bge-small-en-v1.5', ...

    The canonical spec is also the embedder's `name`, which is what passages store in
    `embedding_model`, so it can be computed without loading a model.
    """
    kind, _, arg = spec.partition(":")
    if kind not in DEFAULT_ARGS:
        raise ValueError(f"unknown embedder '{spec}'")
    return f"{kind}:{arg or DEFAULT_ARGS[kind]}"


def get_embedder(spec: str) -> Embedder:
    return _build_embedder(canonical(spec))


@lru_cache(maxsize=8)
def _build_embedder(spec: str) -> Embedder:
    """Build an embedder from a spec: 'hash', 'hash:256', 'fastembed:BAAI/bge-small-en-v1.5'."""
    from novelforge.config import get_settings

    settings = get_settings()
    kind, _, arg = spec.partition(":")
    if kind == "hash":
        return HashEmbedder(int(arg) if arg else 384)
    if kind == "fastembed":
        return FastEmbedEmbedder(
            arg or "BAAI/bge-small-en-v1.5", str(settings.model_cache_dir / "fastembed")
        )
    if kind == "ollama":
        return OllamaEmbedder(arg or "nomic-embed-text", settings.ollama_url)
    if kind == "openai":
        return OpenAICompatibleEmbedder(
            arg or "text-embedding-3-small",
            settings.openai_base_url,
            os.environ.get("OPENAI_API_KEY", ""),
        )
    raise ValueError(f"unknown embedder '{spec}'")


def release_models() -> None:
    """Drop loaded ONNX models before interpreter shutdown.

    ONNX Runtime sessions destroyed during Python's own teardown can abort the process on macOS
    ("recursive_mutex lock failed"); releasing them while the runtime is alive avoids that.
    """
    import gc

    from novelforge.retrieval.rerankers import get_reranker

    _build_embedder.cache_clear()
    get_reranker.cache_clear()
    gc.collect()
