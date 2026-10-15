"""Local PostgreSQL 16 + pgvector via `pgserver`, for machines without Docker.

This is a development fallback. CI and Docker Compose use a real `pgvector/pgvector:pg16`
server and set DATABASE_URL instead.
"""

from pathlib import Path


def local_server_url(pgdata: Path, database: str = "postgres") -> str:
    try:
        import pgserver
    except ImportError as exc:  # pragma: no cover - depends on the install
        raise RuntimeError(
            "DATABASE_URL is not set and the optional 'pgserver' package is not installed. "
            "Either set DATABASE_URL or run `uv sync --extra localdb`."
        ) from exc
    pgdata.mkdir(parents=True, exist_ok=True)
    # cleanup_mode=None keeps the server running after this process exits, so the API server,
    # tests and CLI can share one instance.
    server = pgserver.get_server(pgdata, cleanup_mode=None)
    uri = server.get_uri(database)  # postgresql://postgres:@/<db>?host=<socket dir>
    return uri.replace("postgresql://", "postgresql+psycopg://", 1)


def stop_local_server(pgdata: Path) -> bool:
    """Stop the server if it is running. Returns True if a server was stopped."""
    import subprocess

    import pgserver

    if not (pgdata / "postmaster.pid").exists():
        return False
    pg_ctl = Path(pgserver.__file__).parent / "pginstall" / "bin" / "pg_ctl"
    subprocess.run([str(pg_ctl), "-D", str(pgdata), "stop", "-m", "fast"], check=True,
                   capture_output=True)
    return True
