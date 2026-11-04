"""Claude through the official Anthropic SDK (`uv sync --extra anthropic`).

Credentials resolve the SDK's usual way (ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, or an
`ant auth login` profile). Requests opt into server-side refusal fallbacks
(`fallbacks="default"`), and a refusal that the fallback chain could not rescue is surfaced as
LLMError("refusal") rather than an empty answer.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from typing import Any

from novelforge.llm.base import LLMError, LLMResult, StreamChunk, cost

FALLBACK_BETA = "server-side-fallback-2026-07-01"


def _price_key(model: str) -> str:
    """Behind a proxy the model may be named "anthropic/claude-haiku-5.5"; prices are keyed
    "claude-haiku-5-5"."""
    return model.rpartition("/")[2].replace(".", "-")


class AnthropicLLM:
    local = False

    def __init__(
        self,
        model: str = "claude-opus-5-5",
        effort: str = "medium",
        client=None,
        fallbacks: bool | None = None,
    ):
        if client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - depends on the install
                raise LLMError("config", "install the extra: uv sync --extra anthropic") from exc
            # ANTHROPIC_BASE_URL / ANTHROPIC_AUTH_TOKEN are read by the SDK itself, so the same
            # backend runs against an Anthropic-compatible endpoint (OpenRouter's, for one).
            client = anthropic.Anthropic()
        self.client = client
        self.model = model
        self.effort = effort
        self.name = f"anthropic:{model}"
        # Server-side refusal fallbacks are an Anthropic API feature; other endpoints that speak
        # the Messages API reject or misread the parameter, so it is off when the client points
        # elsewhere (unless asked for explicitly).
        if fallbacks is None:
            host = str(getattr(client, "base_url", "") or "")
            fallbacks = not host or "anthropic.com" in host
        self.fallbacks = fallbacks

    def _extra(self) -> dict[str, Any]:
        return {"betas": [FALLBACK_BETA], "fallbacks": "default"} if self.fallbacks else {}

    def _errors(self):
        import anthropic

        return anthropic

    def generate_json(
        self, system: str, prompt: str, schema: dict[str, Any], max_tokens: int = 16000
    ) -> LLMResult:
        started = time.perf_counter()
        api_schema = {k: v for k, v in schema.items() if k != "title"}
        try:
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                **self._extra(),
                system=system,
                messages=[{"role": "user", "content": prompt}],
                output_config={
                    "effort": self.effort,
                    "format": {"type": "json_schema", "schema": api_schema},
                },
            )
        except Exception as exc:
            raise self._wrap(exc) from exc
        if response.stop_reason == "refusal":
            category = getattr(getattr(response, "stop_details", None), "category", None)
            raise LLMError("refusal", f"model declined (category: {category})")
        if response.stop_reason == "max_tokens":
            raise LLMError("max_tokens", f"output hit max_tokens={max_tokens}")
        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError("invalid_json", str(exc)) from exc
        usage = response.usage
        return LLMResult(
            text=text,
            data=data,
            model=response.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            latency_ms=(time.perf_counter() - started) * 1000,
            stop_reason=response.stop_reason,
            cost_usd=cost(
                _price_key(self.model), usage.input_tokens, usage.output_tokens, local=False
            ),
            request_id=getattr(response, "_request_id", None),
        )

    def stream_text(
        self,
        system: str,
        prompt: str,
        max_tokens: int = 64000,
        cancel: threading.Event | None = None,
    ) -> Iterator[StreamChunk]:
        started = time.perf_counter()
        parts: list[str] = []
        try:
            with self.client.beta.messages.stream(
                model=self.model,
                max_tokens=max_tokens,
                **self._extra(),
                system=system,
                messages=[{"role": "user", "content": prompt}],
                output_config={"effort": self.effort},
            ) as stream:
                for text in stream.text_stream:
                    if cancel is not None and cancel.is_set():
                        # Leaving the context manager closes the HTTP stream.
                        yield StreamChunk(
                            done=True,
                            cancelled=True,
                            result=LLMResult(
                                text="".join(parts),
                                data=None,
                                model=self.model,
                                input_tokens=0,
                                output_tokens=0,
                                latency_ms=(time.perf_counter() - started) * 1000,
                                stop_reason="cancelled",
                                cost_usd=None,
                            ),
                        )
                        return
                    parts.append(text)
                    yield StreamChunk(text=text)
                final = stream.get_final_message()
        except LLMError:
            raise
        except Exception as exc:
            raise self._wrap(exc) from exc
        if final.stop_reason == "refusal":
            raise LLMError("refusal", "model declined to continue")
        usage = final.usage
        yield StreamChunk(
            done=True,
            result=LLMResult(
                text="".join(parts),
                data=None,
                model=final.model,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                latency_ms=(time.perf_counter() - started) * 1000,
                stop_reason=final.stop_reason,
                cost_usd=cost(
                    _price_key(self.model), usage.input_tokens, usage.output_tokens, local=False
                ),
            ),
        )

    def _wrap(self, exc: Exception) -> LLMError:
        try:
            anthropic = self._errors()
        except ImportError:  # pragma: no cover
            return LLMError("transport", str(exc))
        if isinstance(exc, anthropic.AuthenticationError | anthropic.PermissionDeniedError):
            return LLMError("config", f"credentials rejected: {exc}")
        if isinstance(exc, anthropic.BadRequestError):
            return LLMError("config", f"bad request: {exc}")
        if isinstance(exc, anthropic.RateLimitError):
            return LLMError("transport", f"rate limited: {exc}")
        if isinstance(exc, anthropic.APIStatusError | anthropic.APIConnectionError):
            return LLMError("transport", str(exc))
        return LLMError("transport", f"{type(exc).__name__}: {exc}")
