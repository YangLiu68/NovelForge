"""Runtime settings, read from environment variables (see .env.example)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # Later files win: repo-root .env, then a .env in the working directory.
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    # SQLAlchemy URL, e.g. postgresql+psycopg://novelforge:novelforge@localhost:5432/novelforge.
    # Empty means "use the local pgserver instance" (dev machines without Docker).
    database_url: str = ""
    # Where pgserver keeps its data directory when database_url is empty.
    local_pgdata: Path = REPO_ROOT / ".pgdata"
    samples_dir: Path = REPO_ROOT / "samples"
    # Claims below this confidence are kept but left out of the contradiction report.
    report_min_confidence: float = 0.6
    # In chapters an LLM has read, report its claims instead of the rule extractor's (accepted
    # claims always count). Better with Claude on the Chinese samples; unmeasured on English.
    report_prefer_llm: bool = False
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    log_level: str = "INFO"

    # Retrieval. "hash" is a deterministic lexical mock (tests/CI); for real semantic search use
    # "fastembed:BAAI/bge-small-en-v1.5" (needs `uv sync --extra embeddings`).
    embedder: str = "hash"
    reranker: str = "lexical"  # none | lexical | cross-encoder[:model]
    model_cache_dir: Path = Path.home() / ".cache" / "novelforge"
    ollama_url: str = "http://127.0.0.1:11434"
    openai_base_url: str = "https://api.openai.com/v1"
    # Run the job worker inside the API process. Turn off when running `novelforge worker`.
    jobs_in_process: bool = True

    # LLM: "mock" (offline, deterministic), "anthropic[:model]" (Claude; default
    # claude-opus-5-5), "openrouter:<model>" (hosted models through OpenRouter, e.g.
    # openrouter:anthropic/claude-opus-5.5; key in OPENROUTER_API_KEY), "ollama:<model>" (local).
    # LLM extraction runs as a background job after every chapter save when llm_extraction is on.
    llm: str = "mock"
    openrouter_api_key: str = ""
    openrouter_url: str = "https://openrouter.ai/api/v1"
    llm_effort: str = "medium"  # Claude effort: low | medium | high | xhigh | max
    llm_extraction: bool = False
    # Words per LLM extraction window; 0 = the default for the model (6000 hosted, 500 local).
    llm_window_words: int = 0
    # Recorded LLM answers (bench/results/llm-cache/*.jsonl) that "replay:<llm>" answers from:
    # a real model's run on unchanged text can be shown on a machine without that model.
    replay_dir: Path = REPO_ROOT / "bench" / "results" / "llm-cache"
    # Run story audits inside the request (tests); default: a background job.
    story_inline: bool = False
    # Run drafting workflow steps synchronously inside the request (tests); default: background.
    workflow_inline: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
