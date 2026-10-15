"""A local model served by Ollama (native /api/chat, structured outputs via `format`)."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from typing import Any

import httpx

from novelforge.llm.base import LLMError, LLMResult, StreamChunk


class OllamaLLM:
    local = True

    def __init__(self, model: str, url: str, num_ctx: int = 8192, transport=None):
        self.model, self.url, self.num_ctx = model, url.rstrip("/"), num_ctx
        self.name = f"ollama:{model}"
        self._client = httpx.Client(timeout=600, transport=transport)

    def _options(self) -> dict[str, Any]:
        return {"temperature": 0, "seed": 0, "num_ctx": self.num_ctx}

    def generate_json(
        self, system: str, prompt: str, schema: dict[str, Any], max_tokens: int = 16000
    ) -> LLMResult:
        started = time.perf_counter()
        try:
            r = self._client.post(
                f"{self.url}/api/chat",
                json={
                    "model": self.model,
                    "stream": False,
                    "format": {k: v for k, v in schema.items() if k != "title"},
                    "options": {**self._options(), "num_predict": max_tokens},
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                },
            )
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError("transport", f"ollama: {exc}") from exc
        body = r.json()
        text = body.get("message", {}).get("content", "")
        if body.get("done_reason") == "length":
            raise LLMError("max_tokens", f"output hit num_predict={max_tokens}")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError("invalid_json", str(exc)) from exc
        return LLMResult(
            text=text,
            data=data,
            model=self.model,
            input_tokens=int(body.get("prompt_eval_count", 0)),
            output_tokens=int(body.get("eval_count", 0)),
            latency_ms=(time.perf_counter() - started) * 1000,
            stop_reason=body.get("done_reason"),
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
        parts: list[str] = []
        payload = {
            "model": self.model,
            "stream": True,
            "options": {**self._options(), "temperature": 0.7, "num_predict": max_tokens},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        last: dict[str, Any] = {}
        try:
            with self._client.stream("POST", f"{self.url}/api/chat", json=payload) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if cancel is not None and cancel.is_set():
                        yield StreamChunk(
                            done=True,
                            cancelled=True,
                            result=self._result(parts, last, started, "cancelled"),
                        )
                        return
                    if not line:
                        continue
                    event = json.loads(line)
                    piece = event.get("message", {}).get("content", "")
                    if piece:
                        parts.append(piece)
                        yield StreamChunk(text=piece)
                    if event.get("done"):
                        last = event
                        break
        except httpx.HTTPError as exc:
            raise LLMError("transport", f"ollama: {exc}") from exc
        yield StreamChunk(
            done=True, result=self._result(parts, last, started, last.get("done_reason"))
        )

    def _result(self, parts, last, started, stop) -> LLMResult:
        return LLMResult(
            text="".join(parts),
            data=None,
            model=self.model,
            input_tokens=int(last.get("prompt_eval_count", 0)),
            output_tokens=int(last.get("eval_count", 0)),
            latency_ms=(time.perf_counter() - started) * 1000,
            stop_reason=stop,
            cost_usd=0.0,
        )
