"""FastAPI application."""

import json
import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from novelforge.api import analysis, chapters, characters, novels, samples
from novelforge.config import get_settings
from novelforge.db import get_engine
from novelforge.services.errors import Conflict, NotFound

log = logging.getLogger("novelforge.http")


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level, format="%(message)s")
    app = FastAPI(title="NovelForge", version="0.1.0")
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"],
        allow_headers=["*"], expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_log(request: Request, call_next):
        # Logs method, path and timing only. Query strings and bodies can contain manuscript
        # text (search queries, chapter edits), so they are never logged.
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        log.info(json.dumps({
            "request_id": request_id, "method": request.method, "path": request.url.path,
            "status": response.status_code,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        }))
        return response

    @app.exception_handler(NotFound)
    async def not_found(_: Request, exc: NotFound):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(Conflict)
    async def conflict(_: Request, exc: Conflict):
        return JSONResponse(
            status_code=409,
            content={"detail": str(exc), "current_version": exc.current_version},
        )

    @app.get("/api/health")
    def health():
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}

    for module in (novels, chapters, characters, analysis, samples):
        app.include_router(module.router)
    return app


app = create_app()
