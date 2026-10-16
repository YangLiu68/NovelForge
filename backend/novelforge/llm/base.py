"""The LLM interface used by extraction, judging and drafting.

Two calls cover every use in NovelForge:
- `generate_json(system, prompt, schema)`: one structured response, validated as JSON.
- `stream_text(system, prompt, cancel)`: incremental text for drafting, stoppable mid-way.

Every result carries token counts and a cost, so benchmarks report measured spend. Cost is 0 for
local/mock backends and None when a hosted model's price is not in PRICES_PER_MTOK.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol

# USD per million tokens (input, output) for hosted models, as published 2026-10.
# Update here when prices change; unknown models report cost None, never a guess.
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}


class LLMError(Exception):
    """kind: refusal | max_tokens | invalid_json | transport | config | not_recorded (replay)"""

    def __init__(self, kind: str, message: str):
        super().__init__(f"{kind}: {message}")
        self.kind, self.message = kind, message


@dataclass
class LLMResult:
    text: str
    data: Any | None
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    stop_reason: str | None = None
    cost_usd: float | None = 0.0
    request_id: str | None = None


@dataclass
class StreamChunk:
    text: str = ""
    done: bool = False
    cancelled: bool = False
    result: LLMResult | None = None  # set on the final chunk
    meta: dict[str, Any] = field(default_factory=dict)


class LLM(Protocol):
    name: str
    local: bool

    def generate_json(
        self, system: str, prompt: str, schema: dict[str, Any], max_tokens: int = 16000
    ) -> LLMResult: ...

    def stream_text(
        self,
        system: str,
        prompt: str,
        max_tokens: int = 8000,
        cancel: threading.Event | None = None,
    ) -> Iterator[StreamChunk]: ...


def cost(model: str, input_tokens: int, output_tokens: int, local: bool) -> float | None:
    if local:
        return 0.0
    price = PRICES_PER_MTOK.get(model)
    if price is None:
        return None
    return round(input_tokens / 1e6 * price[0] + output_tokens / 1e6 * price[1], 6)
