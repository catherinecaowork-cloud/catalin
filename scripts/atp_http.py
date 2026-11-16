"""脚本共用的控制面 HTTP 小工具：自动带上 API Token。"""

from __future__ import annotations

import os
from pathlib import Path

import httpx

_REPO_ROOT = Path(__file__).resolve().parents[1]


def resolve_api_token() -> str:
    env = (os.getenv("ATP_API_TOKEN") or "").strip()
    if env:
        return env
    for candidate in (
        Path(os.getenv("ATP_API_TOKEN_PATH", "")) if os.getenv("ATP_API_TOKEN_PATH") else None,
        _REPO_ROOT / "var" / "api.token",
        Path.cwd() / "var" / "api.token",
    ):
        if candidate is None:
            continue
        if candidate.is_file():
            value = candidate.read_text(encoding="utf-8").strip()
            if value:
                return value
    return ""


def api_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    token = resolve_api_token()
    if token:
        headers["X-API-Token"] = token
    if extra:
        headers.update(extra)
    return headers


def control_client(server: str, timeout: float = 30.0) -> httpx.Client:
    return httpx.Client(base_url=server.rstrip("/"), timeout=timeout, headers=api_headers())
