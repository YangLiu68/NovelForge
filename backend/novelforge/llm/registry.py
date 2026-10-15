"""Build an LLM from a spec: 'mock', 'anthropic[:model]', 'ollama:<model>'."""

from __future__ import annotations

from functools import lru_cache

from novelforge.llm.base import LLM, LLMError


@lru_cache(maxsize=8)
def get_llm(spec: str) -> LLM:
    from novelforge.config import get_settings

    settings = get_settings()
    kind, _, arg = spec.partition(":")
    if kind == "mock":
        from novelforge.extraction.mock_responder import rules_backed_mock

        return rules_backed_mock()
    if kind == "anthropic":
        from novelforge.llm.anthropic_backend import AnthropicLLM

        return AnthropicLLM(model=arg or "claude-opus-5-5", effort=settings.llm_effort)
    if kind == "ollama":
        from novelforge.llm.ollama_backend import OllamaLLM

        if not arg:
            raise LLMError("config", "ollama needs a model, e.g. ollama:qwen2.5:7b")
        return OllamaLLM(model=arg, url=settings.ollama_url)
    raise LLMError("config", f"unknown LLM spec '{spec}'")
