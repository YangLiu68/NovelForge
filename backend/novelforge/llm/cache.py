"""Record-and-replay cache for LLM calls (benchmarks).

Responses are stored in a JSONL file keyed by (model, system, prompt, schema). A benchmark run
with a cache calls the model only for prompts it has not seen, so validation or scoring changes
can be re-measured offline, and a paid model is paid for once. Replayed results keep the
original token counts and cost (what producing them cost), flagged with `cached`. Failures that
would repeat on the same input (output cap, refusal, invalid JSON) are recorded and replayed too;
transport and configuration errors are not.
"""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any

from novelforge.llm.base import LLM, LLMError, LLMResult

REPLAYABLE_ERRORS = {"max_tokens", "refusal", "invalid_json"}


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
            if "error_kind" in entry:
                raise LLMError(entry["error_kind"], entry["error_message"])
            return LLMResult(**{k: entry[k] for k in LLMResult.__dataclass_fields__ if k in entry})
        self.misses += 1
        try:
            result = self.inner.generate_json(system, prompt, schema, max_tokens)
        except LLMError as exc:
            if exc.kind in REPLAYABLE_ERRORS:
                self._store({"key": key, "error_kind": exc.kind, "error_message": exc.message})
            raise
        self._store({"key": key, **result.__dict__})
        return result

    def _store(self, entry: dict[str, Any]) -> None:
        with self._lock:
            self._entries[entry["key"]] = entry
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")

    def stream_text(self, *args, **kwargs):
        return self.inner.stream_text(*args, **kwargs)


class ReplayLLM:
    """Answers only from recordings of another LLM (`replay:<llm spec>`); never calls a model.

    Keys are computed exactly as CachingLLM records them, so a recorded run replays when the
    prompts are byte-identical (same text, cast and prompt version). A prompt with no recording
    raises `not_recorded`, which says so; nothing is made up.
    """

    local = True

    def __init__(self, recorded: str, directory: Path):
        self.recorded = recorded
        self.name = f"replay:{recorded}"
        self._entries: dict[str, dict[str, Any]] = {}
        for path in sorted(directory.glob("*.jsonl")) if directory.exists() else []:
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    entry = json.loads(line)
                    self._entries.setdefault(entry["key"], entry)

    def generate_json(
        self, system: str, prompt: str, schema: dict[str, Any], max_tokens: int = 16000
    ) -> LLMResult:
        blob = json.dumps([self.recorded, system, prompt, schema], sort_keys=True)
        entry = self._entries.get(hashlib.sha256(blob.encode()).hexdigest())
        if entry is None:
            raise LLMError(
                "not_recorded",
                f"no recorded answer from {self.recorded} for this prompt; the text, cast or "
                "prompt version differ from the recorded run, so run it with a live model",
            )
        if "error_kind" in entry:
            raise LLMError(entry["error_kind"], entry["error_message"])
        result = LLMResult(**{k: entry[k] for k in LLMResult.__dataclass_fields__ if k in entry})
        result.cost_usd = 0.0  # replaying costs nothing; the recording keeps what it cost
        return result

    def stream_text(self, *args, **kwargs):
        raise LLMError("config", "replay answers structured calls only")
