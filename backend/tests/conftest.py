"""Test database setup.

Uses TEST_DATABASE_URL or DATABASE_URL when set (CI: the pgvector service container).
Otherwise starts the local pgserver PostgreSQL. Each session gets a freshly created database;
each test starts from empty tables.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_DB = "novelforge_test"
# Tests drive the job queue explicitly (run_pending) and use the deterministic mock embedder.
os.environ["JOBS_IN_PROCESS"] = "false"
os.environ["EMBEDDER"] = "hash"
os.environ["RERANKER"] = "lexical"


def server_url() -> URL:
    raw = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not raw:
        from novelforge.localdb import local_server_url

        raw = local_server_url(REPO_ROOT / ".pgdata", "postgres")
    url = make_url(raw)
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    return url


def recreate_database(name: str) -> URL:
    base = server_url()
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        conn.exec_driver_sql(f'CREATE DATABASE "{name}"')
    admin.dispose()
    return base.set(database=name)


def drop_database(name: str) -> None:
    admin = create_engine(server_url().set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    admin.dispose()


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    url = recreate_database(TEST_DB).render_as_string(hide_password=False)
    os.environ["DATABASE_URL"] = url
    from novelforge import db
    from novelforge.cli import cmd_migrate
    from novelforge.config import get_settings

    get_settings.cache_clear()
    db.get_engine.cache_clear()
    db.get_sessionmaker.cache_clear()
    import argparse

    cmd_migrate(argparse.Namespace(revision="head"))
    yield url
    db.get_engine().dispose()
    drop_database(TEST_DB)


@pytest.fixture(autouse=True)
def clean_tables(request):
    if (
        "database_url" not in request.fixturenames
        and "client" not in request.fixturenames
        and "session" not in request.fixturenames
    ):
        yield
        return
    request.getfixturevalue("database_url")
    from novelforge.db import get_engine

    with get_engine().begin() as conn:
        conn.execute(text("TRUNCATE novel, job, embedding_cache CASCADE"))
    yield


@pytest.fixture
def session(database_url):
    from novelforge.db import get_sessionmaker

    with get_sessionmaker()() as s:
        yield s


@pytest.fixture
def client(database_url):
    from fastapi.testclient import TestClient

    from novelforge.main import create_app

    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def sample_novel_id(client) -> str:
    r = client.post("/api/samples/lanternfall/import")
    assert r.status_code == 200, r.text
    return r.json()["novel_id"]


@pytest.fixture
def run_jobs(database_url):
    """Drain the job queue synchronously; returns the number of jobs run."""
    from novelforge.db import get_sessionmaker
    from novelforge.jobs import load_handlers, run_pending

    load_handlers()
    return lambda: run_pending(get_sessionmaker())
