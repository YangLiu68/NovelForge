"""FastAPI application."""

import json
import logging
import threading
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from novelforge.api import analysis, chapters, characters, jobs, novels, review, samples
from novelforge.config import get_settings
from novelforge.db import get_engine, get_sessionmaker
from novelforge.jobs import Worker, load_handlers
from novelforge.services.errors import Conflict, NotFound

log = logging.getLogger("novelforge.http")


def _warm_models(settings) -> None:
    from novelforge.retrieval.embedders import get_embedder
    from novelforge.retrieval.rerankers import get_reranker

    try:
        get_embedder(settings.embedder)
        get_reranker(settings.reranker)
    except Exception:  # noqa: BLE001 - surfaced again (with context) on first use
        log.exception("model warm-up failed")


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level, format="%(message)s")
    load_handlers()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        worker = Worker(get_sessionmaker()) if settings.jobs_in_process else None
        if worker:
            worker.start()
        # Load real models in the background so the first search does not pay the load time.
        threading.Thread(target=_warm_models, args=(settings,), daemon=True).start()
        yield
        if worker:
            worker.stop()

    app = FastAPI(title="NovelForge", version="0.2.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_log(request: Request, call_next):
        # Logs method, path and timing only. Query strings and bodies can contain manuscript
        # text (search queries, chapter edits), so they are never logged.
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        log.info(
            json.dumps(
                {
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                }
            )
        )
        return response

    @app.exception_handler(NotFound)
    async def not_found(_: Request, exc: NotFound):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(Conflict)
    async def conflict(_: Request, exc: Conflict):
        return JSONResponse(
            status_code=409,
            content={
                "detail": str(exc),
                "current_version": exc.current_version,
                "canon_value": getattr(exc, "canon_value", None),
            },
        )

    @app.get("/api/health")
    def health():
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}

    for module in (novels, chapters, characters, analysis, samples, jobs, review):
        app.include_router(module.router)
    return app


app = create_app()
