# Contributing

## Setup

```bash
make setup        # backend deps + embedded PostgreSQL, migrations, frontend deps
make api          # terminal 1
make web          # terminal 2
```

Python 3.12 with `uv`, Node 22. No Docker or API keys needed; see README for real models.

## Before opening a pull request

```bash
make check        # ruff, format check, tsc, pytest, node unit tests, Playwright
```

- New behaviour needs a test. Database tests use the `client`, `session` and `run_jobs`
  fixtures in `backend/tests/conftest.py`.
- Schema changes need an Alembic migration (`uv run alembic revision --autogenerate`), reviewed
  by hand: add server defaults for new non-null columns.
- Detector, extractor or generator changes change benchmark numbers. Re-run the affected
  benchmark, commit the new `bench/results/*`, and update BENCHMARK.md in the same change. Never
  edit a number by hand.
- Generated corpora are deterministic. If you change the generator's output for a given seed,
  bump `version` in `novelforge/bench/generate.py`.
- Manuscript text must never be logged.
