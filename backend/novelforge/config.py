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
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
