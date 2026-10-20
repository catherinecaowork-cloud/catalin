from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from autotest_control.ai import (
    AIConfigurationError,
    AIRequestError,
    AnthropicClient,
)
from autotest_control.domain.mappers import (
    ai_config_out,
)
from autotest_control.schemas import (
    AIConfigIn,
    AIConfigOut,
)
from autotest_control.settings import settings

router = APIRouter()

@router.get("/ai/config", response_model=AIConfigOut)
def get_ai_config() -> AIConfigOut:
    return ai_config_out()


@router.put("/ai/config", response_model=AIConfigOut)
def put_ai_config(payload: AIConfigIn) -> AIConfigOut:
    base_url = settings.normalize_base_url(payload.base_url)
    model = (payload.model or "").strip()
    if not base_url or not model:
        raise HTTPException(status_code=400, detail="请填写网关地址和模型名")
    token = (payload.auth_token or "").strip() or None
    if not token and not settings.anthropic_auth_token:
        raise HTTPException(status_code=400, detail="请填写 Token")
    settings.save_ai_config(
        base_url=base_url,
        auth_token=token,
        model=model,
        vision_enabled=payload.vision_enabled,
    )
    if not settings.ai_configured():
        raise HTTPException(status_code=400, detail="保存后仍缺少配置，请检查环境变量是否覆盖了空值")
    return ai_config_out()


@router.post("/ai/config/test")
def test_ai_config() -> dict[str, Any]:
    settings.reload_ai(prefer_file=True)
    if not settings.ai_configured():
        raise HTTPException(status_code=400, detail="请先在顶栏「AI」保存网关地址、Token 和模型")
    try:
        result = AnthropicClient().create_message("Reply with the single word ok.")
    except AIConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AIRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "ok": True,
        "model": settings.anthropic_model,
        "base_url": settings.anthropic_base_url,
        "token_hint": settings.token_hint(),
        "api_format": settings.anthropic_api_format,
        "attempts": result.attempts,
        "preview": (result.text or "")[:120],
    }
