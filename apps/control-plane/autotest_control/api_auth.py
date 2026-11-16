"""控制面 API 最小准入。

写接口需要共享 API Token（``Authorization: Bearer …`` 或 ``X-API-Token``）。
Worker 协议路径仍走各自的 worker token / 注册码，不要求再带 API Token。
"""

from __future__ import annotations

import re
import secrets
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from autotest_control.settings import settings

_WORKER_PROTOCOL = re.compile(
    r"^/api/v1/(?:workers/register|workers/heartbeat|jobs/lease|"
    r"runs/[^/]+/(?:events|complete|artifacts|control)|"
    r"credentials/[^/]+/material)/?$"
)


def extract_api_token(request: Request) -> str:
    header = request.headers.get("x-api-token") or ""
    if header.strip():
        return header.strip()
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def tokens_match(provided: str, expected: str) -> bool:
    if not provided or not expected:
        return False
    if len(provided) != len(expected):
        # compare_digest 要求等长；故意错长度也当失败
        return False
    return secrets.compare_digest(provided, expected)


def is_worker_protocol_path(path: str) -> bool:
    return bool(_WORKER_PROTOCOL.match(path))


class ApiTokenMiddleware(BaseHTTPMiddleware):
    """阻断匿名写：未带正确 API Token 的 mutating /api/v1 请求直接 401。"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method in {"GET", "HEAD", "OPTIONS"}:
            return await call_next(request)
        path = request.url.path
        if not path.startswith("/api/v1/"):
            return await call_next(request)
        if is_worker_protocol_path(path):
            return await call_next(request)
        expected = settings.api_token
        if not expected:
            return JSONResponse(
                {"detail": "控制面未配置 ATP_API_TOKEN，拒绝写操作"},
                status_code=503,
            )
        provided = extract_api_token(request)
        if not tokens_match(provided, expected):
            return JSONResponse(
                {"detail": "未授权：需要 API Token（Authorization: Bearer 或 X-API-Token）"},
                status_code=401,
            )
        return await call_next(request)
