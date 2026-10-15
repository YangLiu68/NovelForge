# License notes

## This project

NovelForge is released under the MIT License ([LICENSE](LICENSE)).

## Sample and benchmark text

`samples/lanternfall/` (novel.yaml, three chapters, ground truth) was written originally for this
project. It contains no third-party text. The synthetic benchmark corpora are generator-produced
and not committed (they regenerate from a seed). No copyrighted novel is committed.

The real-prose evaluation (`bench/real/`) uses three novels that are in the public domain in
the United States: *Little Women* (1868–69), *Anne of Green Gables* (1908) and *Pride and
Prejudice* (1813). Their Project Gutenberg files are downloaded at run time into the ignored
`bench/corpora/real/` and are not redistributed, so the Project Gutenberg License and trademark
terms do not attach to this repository. The committed labels (`bench/real/labels/`) quote short
sentences of the public-domain text, without Gutenberg headers. Readers outside the US should
check the status of these works where they are (all three authors died more than 70 years ago).

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
| pgvector (Python) | 0.5.0 | MIT | SQLAlchemy `Vector` type |
| httpx | 0.28.1 | BSD-3-Clause | Ollama and OpenAI-compatible HTTP calls |
| anthropic (optional `anthropic` extra) | 1.11.0 | MIT | Official SDK for Claude |
| fastembed (optional `embeddings` extra) | 0.8.1 | Apache-2.0 | Local ONNX embedding and cross-encoder models |
| onnxruntime (optional `embeddings` extra) | 1.30.0 | MIT | |
| tokenizers, huggingface-hub (via fastembed) | 0.23.3, 1.33.0 | Apache-2.0 | |

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

Nothing in the repository requires a model or an API key: tests, CI and the default
configuration use deterministic mocks. Optional models are downloaded by the user at run time
and are not redistributed here:

| Model | Used for | License | Notes |
|---|---|---|---|
| BAAI/bge-small-en-v1.5 (Qdrant ONNX quantisation, via fastembed) | `EMBEDDER=fastembed` | MIT | ~67 MB, CPU |
| cross-encoder/ms-marco-MiniLM-L-6-v2 (Xenova ONNX export, via fastembed) | `RERANKER=cross-encoder` | Apache-2.0 | ~80 MB, CPU |
| Qwen2.5 3B Instruct (Ollama `qwen2.5:3b`) | Local LLM evaluation runs | Qwen Research License | Non-commercial research terms; used only for local measurement, not shipped |
| Claude (`claude-opus-5-5`) | `LLM=anthropic` | Anthropic commercial terms | Needs the user's own credentials; manuscript text leaves the machine |

Hosted providers' terms apply to whoever supplies the key. The default stays local.
