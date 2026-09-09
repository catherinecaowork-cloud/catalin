from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from autotest_control.api import router
from autotest_control.compilation_worker import compilation_worker
from autotest_control.db import init_db
from autotest_control.settings import settings

_STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    compilation_worker.start()
    try:
        yield
    finally:
        compilation_worker.stop()


def create_app() -> FastAPI:
    init_db()
    app = FastAPI(
        title="autotest-platform control plane", version="0.0.1", lifespan=_lifespan
    )
    app.include_router(router)

    app.mount("/artifacts", StaticFiles(directory=settings.artifacts_dir), name="artifacts")
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/")
    def console() -> FileResponse:
        return FileResponse(_STATIC_DIR / "index.html")

    @app.get("/favicon.ico")
    def favicon() -> FileResponse:
        return FileResponse(_STATIC_DIR / "favicon.ico")

    return app


app = create_app()


def main() -> None:
    uvicorn.run("autotest_control.main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    main()
