from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from autotest_control.api.router import router
from autotest_control.api_auth import ApiTokenMiddleware
from autotest_control.compilation_worker import compilation_worker
from autotest_control.db import init_db
from autotest_control.settings import settings

_STATIC_DIR = Path(__file__).resolve().parent / "static"
_CONSOLE_INDEX = _STATIC_DIR / "dist" / "index.html"
def _console_index() -> Path:
    """React build 产物入口。"""
    return _CONSOLE_INDEX


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    compilation_worker.start()
    try:
        yield
    finally:
        compilation_worker.stop()


def create_app() -> FastAPI:
    settings.ensure_access_secrets()
    init_db()
    app = FastAPI(
        title="autotest-platform control plane", version="0.0.1", lifespan=_lifespan
    )
    app.add_middleware(ApiTokenMiddleware)
    app.include_router(router)

    app.mount("/artifacts", StaticFiles(directory=settings.artifacts_dir), name="artifacts")
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
    dist_assets = _STATIC_DIR / "dist" / "assets"
    if dist_assets.is_dir():
        app.mount("/assets", StaticFiles(directory=dist_assets), name="spa-assets")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/")
    def console() -> FileResponse:
        index = _console_index()
        if not index.is_file():
            raise HTTPException(
                status_code=503,
                detail=(
                    "控制台前端未构建。请在 apps/control-plane/web 执行："
                    "npm i && npm run build"
                ),
            )
        return FileResponse(index)

    @app.get("/favicon.ico")
    def favicon() -> FileResponse:
        return FileResponse(_STATIC_DIR / "favicon.ico")

    return app


app = create_app()


def main() -> None:
    uvicorn.run("autotest_control.main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    main()
