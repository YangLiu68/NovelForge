# Build context: repository root (the image also needs ../samples).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:0.9.2 /uv /usr/local/bin/uv

WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ ./
COPY samples/ /app/samples/
RUN uv sync --frozen --no-dev

RUN useradd --create-home --uid 10001 novelforge
USER novelforge

ENV PATH="/app/backend/.venv/bin:$PATH" \
    SAMPLES_DIR=/app/samples
EXPOSE 8000
CMD ["sh", "-c", "novelforge migrate && novelforge serve --host 0.0.0.0 --port 8000"]
