"""准入相关只读接口：本机控制台可取到 API Token，远程不回显。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from autotest_control.settings import settings

router = APIRouter()


def _is_loopback(request: Request) -> bool:
    host = (request.client.host if request.client else "") or ""
    return host in {"127.0.0.1", "::1", "localhost", "testclient"}


@router.get("/auth/bootstrap")
def auth_bootstrap(request: Request) -> dict[str, Any]:
    """控制台启动时探测鉴权。

    仅 loopback / TestClient 回显 api_token，方便同机开控制台；
    远程部署请用环境变量配置，不要依赖本接口取密钥。
    """
    settings.ensure_access_secrets()
    loopback = _is_loopback(request)
    payload: dict[str, Any] = {
        "required": True,
        "loopback": loopback,
        "header": "X-API-Token",
    }
    if loopback:
        payload["api_token"] = settings.api_token
    return payload
