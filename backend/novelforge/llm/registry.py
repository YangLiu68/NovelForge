"""Build an LLM from a spec: 'mock', 'anthropic[:model]', 'ollama:<model>', 'replay:<spec>'."""

from __future__ import annotations

from functools import lru_cache

from novelforge.llm.base import LLM, LLMError


def allowed_llm(requested: str | None) -> str:
    """The LLM a request may use: the configured one or the offline mock, nothing else.

    API callers must not be able to point the server at a paid hosted model or an arbitrary local
    one, so a request can only choose between what the operator configured and `mock`.
    """
    from novelforge.config import get_settings

    configured = get_settings().llm
    if requested is None or requested == configured:
        return configured
    if requested == "mock" or requested.startswith("replay:"):
        return requested  # offline and free
    raise LLMError("config", f"LLM '{requested}' is not enabled; this server uses '{configured}'")


@lru_cache(maxsize=8)
def get_llm(spec: str) -> LLM:
    from novelforge.config import get_settings

    settings = get_settings()
    kind, _, arg = spec.partition(":")
    if kind == "replay":
        from novelforge.llm.cache import ReplayLLM

        if not arg:
            raise LLMError("config", "replay needs the recorded LLM, e.g. replay:ollama:qwen2.5:7b")
        return ReplayLLM(arg, settings.replay_dir)
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
