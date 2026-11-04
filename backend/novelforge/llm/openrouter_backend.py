"""Hosted models through OpenRouter (https://openrouter.ai), e.g. Claude without an Anthropic key.

OpenRouter speaks the OpenAI chat-completions format: structured output via
`response_format: json_schema` (strict), reasoning effort via `reasoning.effort`, and the billed
cost in `usage.cost`. `provider.require_parameters` keeps a request off any provider that would
ignore the schema. The key is OPENROUTER_API_KEY; with this backend, manuscript text is sent to
OpenRouter and the model's provider.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from typing import Any

import httpx

from novelforge.llm.base import LLMError, LLMResult, StreamChunk, cost

# OpenRouter's effort levels; NovelForge's xhigh/max have no separate level there.
EFFORT = {"low": "low", "medium": "medium", "high": "high", "xhigh": "high", "max": "high"}


def price_key(model: str) -> str:
    """'anthropic/claude-opus-5.5' -> 'claude-opus-5-5', the key of the local price table."""
    return model.rpartition("/")[2].replace(".", "-")


class OpenRouterLLM:
    local = False

    def __init__(
        self,
        model: str,
        api_key: str,
        url: str = "https://openrouter.ai/api/v1",
        effort: str = "medium",
        transport=None,
        timeout: float = 600,
    ):
        if not api_key:
            raise LLMError("config", "set OPENROUTER_API_KEY (in .env) to use openrouter:<model>")
        self.model, self.url = model, url.rstrip("/")
        self.effort = EFFORT.get(effort, "medium")
        self.name = f"openrouter:{model}"
        self._client = httpx.Client(
            timeout=timeout,
            transport=transport,
            headers={"Authorization": f"Bearer {api_key}", "X-Title": "NovelForge"},
        )

    def _body(self, system: str, prompt: str, max_tokens: int) -> dict[str, Any]:
        return {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "reasoning": {"effort": self.effort},
            "provider": {"require_parameters": True},
            "usage": {"include": True},
        }

    def generate_json(
        self, system: str, prompt: str, schema: dict[str, Any], max_tokens: int = 16000
    ) -> LLMResult:
        started = time.perf_counter()
        body = self._body(system, prompt, max_tokens)
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": schema.get("title", "answer").replace(" ", "_")[:64],
                "strict": True,
                "schema": {k: v for k, v in schema.items() if k != "title"},
            },
        }
        try:
            r = self._client.post(f"{self.url}/chat/completions", json=body)
        except httpx.HTTPError as exc:
            raise LLMError("transport", f"openrouter: {exc}") from exc
        data = self._json(r)
        choice = (data.get("choices") or [{}])[0]
        finish = choice.get("finish_reason")
        if finish == "length":
            raise LLMError("max_tokens", f"output hit max_tokens={max_tokens}")
        if finish in ("content_filter", "refusal") or choice.get("message", {}).get("refusal"):
            raise LLMError("refusal", f"model declined ({choice.get('native_finish_reason')})")
        text = choice.get("message", {}).get("content") or ""
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError("invalid_json", str(exc)) from exc
        return self._result(text, parsed, data, started, finish)

    def stream_text(
        self,
        system: str,
        prompt: str,
        max_tokens: int = 64000,
        cancel: threading.Event | None = None,
    ) -> Iterator[StreamChunk]:
        started = time.perf_counter()
        parts: list[str] = []
        body = {**self._body(system, prompt, max_tokens), "stream": True}
        last: dict[str, Any] = {}
        finish = None
        try:
            with self._client.stream("POST", f"{self.url}/chat/completions", json=body) as r:
                if r.status_code >= 400:
                    r.read()
                    self._json(r)
                for line in r.iter_lines():
                    if cancel is not None and cancel.is_set():
                        yield StreamChunk(
                            done=True,
                            cancelled=True,
                            result=self._result("".join(parts), None, last, started, "cancelled"),
                        )
                        return
                    # SSE: "data: {...}" events, ": keep-alive" comments, "data: [DONE]" at the end.
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    event = json.loads(payload)
                    if "error" in event:
                        raise LLMError("transport", f"openrouter: {event['error']}")
                    for choice in event.get("choices") or []:
                        piece = (choice.get("delta") or {}).get("content") or ""
                        if piece:
                            parts.append(piece)
                            yield StreamChunk(text=piece)
                        finish = choice.get("finish_reason") or finish
                    if event.get("usage"):
                        last = event
        except httpx.HTTPError as exc:
            raise LLMError("transport", f"openrouter: {exc}") from exc
        if finish in ("content_filter", "refusal"):
            raise LLMError("refusal", "model declined to continue")
        yield StreamChunk(
            done=True, result=self._result("".join(parts), None, last, started, finish)
        )

    def _json(self, r: httpx.Response) -> dict[str, Any]:
        try:
            data = r.json()
        except ValueError:
            data = {}
        error = data.get("error") if isinstance(data, dict) else None
        if r.status_code >= 400 or error:
            message = (
                (error or {}).get("message", r.text[:300])
                if isinstance(error, dict)
                else r.text[:300]
            )
            if r.status_code in (401, 402, 403):
                raise LLMError("config", f"openrouter {r.status_code}: {message}")
            if r.status_code == 400:
                raise LLMError("config", f"openrouter bad request: {message}")
            raise LLMError("transport", f"openrouter {r.status_code}: {message}")
        return data

    def _result(self, text, parsed, data, started, stop) -> LLMResult:
        usage = data.get("usage") or {}
        tokens_in, tokens_out = (
            int(usage.get("prompt_tokens", 0)),
            int(usage.get("completion_tokens", 0)),
        )
        billed = usage.get("cost")
        return LLMResult(
            text=text,
            data=parsed,
            model=data.get("model", self.model),
            input_tokens=tokens_in,
            output_tokens=tokens_out,
            latency_ms=(time.perf_counter() - started) * 1000,
            stop_reason=stop,
            cost_usd=float(billed)
            if billed is not None
            else cost(price_key(self.model), tokens_in, tokens_out, local=False),
            request_id=data.get("id"),
        )
