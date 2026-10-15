"""Deterministic offline LLM for tests, CI and demos. Clearly labelled `mock` in every report.

- `generate_json` returns the next scripted response if one was queued, otherwise asks the
  registered responder for this schema (e.g. the rule-backed extraction responder), otherwise
  returns an empty object.
- `stream_text` streams a scripted (or templated) text in small chunks with a short delay, so
  streaming, cancellation and retry can be tested end to end.
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from collections.abc import Callable, Iterator
from typing import Any

from novelforge.llm.base import LLMResult, StreamChunk

Responder = Callable[[str, str, dict[str, Any]], Any]


class MockLLM:
    local = True

    def __init__(self, name: str = "mock", chunk_delay: float = 0.01):
        self.name = name
        self.chunk_delay = chunk_delay
        self.json_queue: deque[Any] = deque()
        self.text_queue: deque[str] = deque()
        self.responders: dict[str, Responder] = {}
        self.calls: list[dict[str, Any]] = []

    def queue_json(self, *responses: Any) -> None:
        self.json_queue.extend(responses)

    def queue_text(self, *texts: str) -> None:
        self.text_queue.extend(texts)

    def on_schema(self, title: str, responder: Responder) -> None:
        """Answer requests whose schema has this `title`."""
        self.responders[title] = responder

    def generate_json(
        self, system: str, prompt: str, schema: dict[str, Any], max_tokens: int = 16000
    ) -> LLMResult:
        started = time.perf_counter()
        self.calls.append({"kind": "json", "system": system, "prompt": prompt, "schema": schema})
        if self.json_queue:
            data = self.json_queue.popleft()
        elif schema.get("title") in self.responders:
            data = self.responders[schema["title"]](system, prompt, schema)
        else:
            data = {}
        text = data if isinstance(data, str) else json.dumps(data)
        parsed = None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        return LLMResult(
            text=text,
            data=parsed,
            model=self.name,
            input_tokens=_count(system) + _count(prompt),
            output_tokens=_count(text),
            latency_ms=(time.perf_counter() - started) * 1000,
            stop_reason="end_turn",
            cost_usd=0.0,
        )

    def stream_text(
        self,
        system: str,
        prompt: str,
        max_tokens: int = 8000,
        cancel: threading.Event | None = None,
    ) -> Iterator[StreamChunk]:
        started = time.perf_counter()
        self.calls.append({"kind": "stream", "system": system, "prompt": prompt})
        text = self.text_queue.popleft() if self.text_queue else _template_draft(prompt)
        words = text.split(" ")
        out: list[str] = []
        for i in range(0, len(words), 3):
            if cancel is not None and cancel.is_set():
                yield StreamChunk(
                    cancelled=True, done=True, result=self._result(out, system, prompt, started)
                )
                return
            piece = " ".join(words[i : i + 3]) + (" " if i + 3 < len(words) else "")
            out.append(piece)
            yield StreamChunk(text=piece)
            if self.chunk_delay:
                time.sleep(self.chunk_delay)
        yield StreamChunk(done=True, result=self._result(out, system, prompt, started))

    def _result(self, out: list[str], system: str, prompt: str, started: float) -> LLMResult:
        text = "".join(out)
        return LLMResult(
            text=text,
            data=None,
            model=self.name,
            input_tokens=_count(system) + _count(prompt),
            output_tokens=_count(text),
            latency_ms=(time.perf_counter() - started) * 1000,
            stop_reason="end_turn",
            cost_usd=0.0,
        )


def _count(text: str) -> int:
    return int(len(text.split()) * 1.3)


def _template_draft(prompt: str) -> str:
    return (
        "The fog came in early that evening, and the harbour lamps were lit before the bell. "
        "Nobody spoke of the survey, though everyone was thinking of it. "
        "[mock draft: replace with a real model for actual prose]"
    )
