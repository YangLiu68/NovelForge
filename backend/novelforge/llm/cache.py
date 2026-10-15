"""Record-and-replay cache for LLM calls (benchmarks).

Responses are stored in a JSONL file keyed by (model, system, prompt, schema). A benchmark run
with a cache calls the model only for prompts it has not seen, so validation or scoring changes
can be re-measured offline, and a paid model is paid for once. Replayed results keep the
original token counts and cost (what producing them cost), flagged with `cached`.
"""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any

from novelforge.llm.base import LLM, LLMResult


class CachingLLM:
    def __init__(self, inner: LLM, path: Path):
        self.inner, self.path = inner, path
        self.name, self.local = inner.name, inner.local
        self.hits = self.misses = 0
        self._lock = threading.Lock()
        self._entries: dict[str, dict[str, Any]] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    entry = json.loads(line)
                    self._entries[entry["key"]] = entry

    def _key(self, system: str, prompt: str, schema: dict[str, Any]) -> str:
        blob = json.dumps([self.inner.name, system, prompt, schema], sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()

    def generate_json(
        self, system: str, prompt: str, schema: dict[str, Any], max_tokens: int = 16000
    ) -> LLMResult:
        key = self._key(system, prompt, schema)
        entry = self._entries.get(key)
        if entry is not None:
            self.hits += 1
            return LLMResult(**{k: entry[k] for k in LLMResult.__dataclass_fields__ if k in entry})
        self.misses += 1
        result = self.inner.generate_json(system, prompt, schema, max_tokens)
        entry = {"key": key, **result.__dict__}
        with self._lock:
            self._entries[key] = entry
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        return result

    def stream_text(self, *args, **kwargs):
        return self.inner.stream_text(*args, **kwargs)
