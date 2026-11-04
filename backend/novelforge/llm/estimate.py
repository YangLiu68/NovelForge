"""What an LLM run on a novel will roughly cost, before it is started.

Calibrated on the runs recorded in bench/results/llm-cache/ (2026-11-03, Claude through
OpenRouter and local qwen2.5):

- Extraction is one call per window. Each call carries the system prompt, the JSON schema and the
  cast: about 1,760 input tokens in English (fitted on 100 synthetic chapters, Haiku 5.5) and
  2,400 in Chinese (4 held-out chapters, three models). Text costs about 1.5 tokens per English
  word (1.3 on templated prose, 1.8 on Gutenberg dialogue) and 1.15 per Chinese character.
- The story audit reads every window three times (notes, beats, shape) and then asks about each
  key action: about 3 calls per window plus 4 per chapter and 10 for the whole book (later
  explanations, plot, payoffs, plan), each with about 1,300 tokens of
  prompt besides the text (68 calls / 104k tokens on 青石渡, 46+ on 青崖问剑).
- Output tokens per input token depend on the model, mostly on how much it thinks: Opus 5.5
  0.4-0.56, Sonnet 5.5 0.23, Haiku 5.5 0.3-0.9, qwen2.5 0.22-0.38.

The estimate is a range (half to twice the point estimate): wording, cast size and how many
actions the model lists move it. Prices come from the same table as measured costs
(`base.PRICES_PER_MTOK`); a model with no known price is reported as unknown, never guessed.
"""

from __future__ import annotations

import math
from typing import Any

from novelforge.core.domain import ChapterRef
from novelforge.core.lang import is_chinese
from novelforge.llm.base import PRICES_PER_MTOK

OVERHEAD = {"en": 1760, "zh": 2400}  # input tokens per extraction call besides the text
PER_UNIT = {"en": 1.5, "zh": 1.15}  # tokens per word (en) / character (zh)
STORY_OVERHEAD = 1300  # input tokens per story-audit call besides the text
STORY_WINDOW_CHARS = 2400  # narrative/audit.py max_chars
STORY_WHOLE_BOOK = 10  # later explanations, plot, payoffs, plan
# Output tokens per input token, by model family; "default" for anything else.
OUTPUT_RATIO = {
    "extract": {"opus": 0.5, "sonnet": 0.25, "haiku": 0.6, "default": 0.5},
    "story": {"opus": 0.42, "sonnet": 0.3, "haiku": 0.6, "default": 0.4},
}


def _family(model: str) -> str:
    return next((f for f in ("opus", "sonnet", "haiku") if f in model), "default")


def _price(spec: str) -> tuple[float, float] | None:
    kind, _, model = spec.partition(":")
    if kind == "anthropic":
        return PRICES_PER_MTOK.get(model or "claude-opus-5-5")
    if kind == "openrouter":
        from novelforge.llm.openrouter_backend import price_key

        return PRICES_PER_MTOK.get(price_key(model))
    return None


def estimate(chapters: list[ChapterRef], spec: str, task: str, window_words: int) -> dict[str, Any]:
    """{calls, input_tokens, output_tokens, cost_usd, low_usd, high_usd, free, basis}."""
    if task not in OUTPUT_RATIO:
        raise ValueError(f"unknown task '{task}'")
    text = "\n".join(c.body for c in chapters)
    lang = "zh" if is_chinese(text[:5000]) else "en"
    kind = spec.partition(":")[0]
    free = kind in ("mock", "replay", "ollama")
    calls = text_tokens = 0
    for c in chapters:
        units = len(c.body) // 2 if lang == "zh" else len(c.body.split())
        text_tokens += int(units * (2 if lang == "zh" else 1) * PER_UNIT[lang])
        if task == "extract":
            calls += max(1, math.ceil(units / max(1, window_words)))
        else:
            calls += 3 * max(1, math.ceil(len(c.body) / STORY_WINDOW_CHARS)) + 4
    if task == "story":
        calls += STORY_WHOLE_BOOK
    if task == "extract":
        input_tokens = calls * OVERHEAD[lang] + text_tokens
    else:
        input_tokens = calls * STORY_OVERHEAD + 3 * text_tokens
    model = spec.partition(":")[2]
    output_tokens = int(input_tokens * OUTPUT_RATIO[task][_family(model)])
    price = None if free else _price(spec)
    cost = (
        0.0
        if free
        else None
        if price is None
        else round(input_tokens / 1e6 * price[0] + output_tokens / 1e6 * price[1], 4)
    )
    return {
        "llm": spec,
        "task": task,
        "language": lang,
        "chapters": len(chapters),
        "calls": calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "free": free,
        "cost_usd": cost,
        "low_usd": None if cost is None else round(cost / 2, 4),
        "high_usd": None if cost is None else round(cost * 2, 4),
        "basis": "calibrated on recorded runs (llm/estimate.py); actual cost is reported after "
        "the run",
    }
