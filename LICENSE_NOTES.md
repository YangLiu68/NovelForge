# License notes

## This project

NovelForge is released under the MIT License ([LICENSE](LICENSE)).

## Sample and benchmark text

`samples/lanternfall/` (novel.yaml, three chapters, ground truth) was written originally for this
project. It contains no third-party text. Future benchmark corpora will be synthetic
(generator-produced) for the same reason; no copyrighted novels will be committed.

## Runtime dependencies

Versions are the ones installed and tested on 2026-10-14. Licenses were read from installed
package metadata (`pgserver` from its bundled LICENSE file).

### Backend (Python)

| Package | Version | License | Notes |
|---|---|---|---|
| fastapi | 0.143.1 | MIT | |
| starlette | 1.8.0 | BSD-3-Clause | via FastAPI |
| uvicorn | 0.54.0 | BSD-3-Clause | |
| SQLAlchemy | 2.1.4 | MIT | |
| alembic | 1.20.0 | MIT | |
| psycopg / psycopg-binary | 3.3.6 | LGPL-3.0-only | Used as an unmodified, dynamically imported library, which LGPL permits in closed or permissive projects. Keep it replaceable (it is a normal pip dependency). |
| pydantic | 2.14.1 | MIT | |
| pydantic-settings | 2.16.0 | MIT | |
| PyYAML | 6.0.3 | MIT | |
| pgserver (optional `localdb` extra) | 0.1.4 | Apache-2.0 | Bundles PostgreSQL 16.2 (PostgreSQL License) and pgvector 0.6.2 (PostgreSQL License). Development only. |

Dev: pytest 9.1.1 (MIT), httpx 0.28.1 (BSD-3-Clause), ruff 0.17.0 (MIT).

### Frontend (npm)

| Package | Version | License |
|---|---|---|
| react, react-dom | 19.1.10 | MIT |
| react-router-dom / react-router | 7.18.4 | MIT |
| react-markdown | 9.1.0 | MIT |
| vite | 6.4.4 | MIT |
| @vitejs/plugin-react | 4.7.0 | MIT |
| typescript | 5.9.3 | Apache-2.0 |
| @playwright/test, playwright | 1.55.1 | Apache-2.0 |
| @types/react, @types/node | 19.1.10, 22.15.3 | MIT |

`npm audit` reported 0 vulnerabilities on 2026-10-14. Vitest was tried and removed: the release
that fixes its current critical advisory (tinypool) was two days old, so the frontend unit tests use
Node's built-in test runner instead.

### Container images (Docker Compose / CI)

| Image | License |
|---|---|
| pgvector/pgvector:pg16 | PostgreSQL License (PostgreSQL and pgvector) |
| python:3.12-slim | PSF License (Python) + Debian package licenses |
| node:22-alpine (build stage only) | MIT (Node.js) + Alpine package licenses |
| nginx:1.27-alpine | BSD-2-Clause (nginx) + Alpine package licenses |

## Models and APIs

Milestone 1 calls no model or external API. Later milestones will add optional providers
(Anthropic, OpenAI-compatible, Ollama). Their terms of service apply to whoever supplies the key,
and manuscript text sent to a hosted provider leaves the machine; the default stays a local mock.
