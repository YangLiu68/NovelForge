"""Engine and session management."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from novelforge.config import get_settings
from novelforge.localdb import local_server_url


def resolve_database_url() -> str:
    settings = get_settings()
    if settings.database_url:
        url = make_url(settings.database_url)
        if url.drivername == "postgresql":
            url = url.set(drivername="postgresql+psycopg")
        return url.render_as_string(hide_password=False)
    return local_server_url(settings.local_pgdata, "novelforge")


@lru_cache
def get_engine() -> Engine:
    url = resolve_database_url()
    if not get_settings().database_url:
        ensure_database(url)  # the local pgserver starts with only the "postgres" database
    return create_engine(url, pool_pre_ping=True)


def ensure_database(url: str) -> None:
    """Create the target database if it does not exist (needed for the local pgserver)."""
    parsed = make_url(url)
    admin = create_engine(parsed.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            exists = conn.exec_driver_sql(
                "SELECT 1 FROM pg_database WHERE datname = %s", (parsed.database,)
            ).scalar()
            if not exists:
                conn.exec_driver_sql(f'CREATE DATABASE "{parsed.database}"')
    finally:
        admin.dispose()


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    with get_sessionmaker()() as session:
        yield session
