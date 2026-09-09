"""网关客户端：按模型协议走 Anthropic Messages 或 OpenAI Chat Completions。"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx

from autotest_control.settings import infer_api_format, settings as default_settings, Settings

from .schemas import ImageInput, MessageResult, TokenUsage


class AIConfigurationError(RuntimeError):
    """AI 网关缺少必需配置。"""

    code = "ai_configuration_missing"

    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        super().__init__(
            f"{self.code}: 缺少配置 {', '.join(missing)}。"
            "请在控制台顶栏「AI」填写网关地址、Token 和模型。"
        )


class AIRequestError(RuntimeError):
    """AI 网关请求失败或返回了不兼容响应。"""

    code = "ai_request_failed"


class AnthropicClient:
    def __init__(
        self,
        *,
        config: Any = default_settings,
        transport: httpx.BaseTransport | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self._transport = transport
        self._sleeper = sleeper

    def _required_config(self) -> tuple[str, str, str]:
        names = {
            "ANTHROPIC_BASE_URL": getattr(self.config, "anthropic_base_url", ""),
            "ANTHROPIC_AUTH_TOKEN": getattr(self.config, "anthropic_auth_token", ""),
            "ANTHROPIC_MODEL": getattr(self.config, "anthropic_model", ""),
        }
        missing = [name for name, value in names.items() if not value]
        if missing:
            raise AIConfigurationError(missing)
        return (
            Settings.normalize_base_url(str(names["ANTHROPIC_BASE_URL"])),
            Settings.normalize_auth_token(str(names["ANTHROPIC_AUTH_TOKEN"])),
            str(names["ANTHROPIC_MODEL"]),
        )

    def _api_format(self, model: str) -> str:
        explicit = str(getattr(self.config, "anthropic_api_format", "") or "").strip()
        return infer_api_format(model, explicit)

    def create_message(
        self,
        prompt: str,
        *,
        system: str | None = None,
        images: list[ImageInput] | None = None,
    ) -> MessageResult:
        base_url, token, model = self._required_config()
        api_format = self._api_format(model)
        if api_format == "openai-completions":
            return self._chat_completions(base_url, token, model, prompt, system=system)
        if api_format != "anthropic":
            raise AIRequestError(
                f"{AIRequestError.code}: 模型 {model} 的协议是 {api_format}，"
                "当前只支持 Anthropic Messages 与 OpenAI Chat Completions（如 glm-5.1）。"
                "请改用 glm-5.1 或 Claude 模型。"
            )
        return self._anthropic_messages(
            base_url, token, model, prompt, system=system, images=images
        )

    def _anthropic_messages(
        self,
        base_url: str,
        token: str,
        model: str,
        prompt: str,
        *,
        system: str | None,
        images: list[ImageInput] | None,
    ) -> MessageResult:
        content: str | list[dict[str, Any]] = prompt
        if images and bool(getattr(self.config, "anthropic_vision_enabled", False)):
            content = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": image.media_type,
                        "data": image.data,
                    },
                }
                for image in images
            ]
            content.append({"type": "text", "text": prompt})

        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": int(getattr(self.config, "anthropic_max_tokens", 4096)),
            "messages": [{"role": "user", "content": content}],
        }
        if system:
            payload["system"] = system
        headers = {
            "Authorization": f"Bearer {token}",
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        return self._post_json(
            f"{base_url}/v1/messages",
            headers,
            payload,
            parser="anthropic",
            token_hint=token[-4:] if len(token) >= 4 else "",
        )

    def _chat_completions(
        self,
        base_url: str,
        token: str,
        model: str,
        prompt: str,
        *,
        system: str | None,
    ) -> MessageResult:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": model,
            "max_tokens": int(getattr(self.config, "anthropic_max_tokens", 4096)),
            "messages": messages,
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "content-type": "application/json",
        }
        return self._post_json(
            f"{base_url}/v1/chat/completions",
            headers,
            payload,
            parser="openai",
            token_hint=token[-4:] if len(token) >= 4 else "",
        )

    def _post_json(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        *,
        parser: str,
        token_hint: str = "",
    ) -> MessageResult:
        timeout = float(getattr(self.config, "anthropic_timeout_seconds", 30))
        max_retries = max(0, int(getattr(self.config, "anthropic_max_retries", 2)))
        with httpx.Client(timeout=timeout, transport=self._transport) as client:
            for attempt in range(1, max_retries + 2):
                try:
                    response = client.post(url, headers=headers, json=payload)
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    if attempt > max_retries:
                        raise AIRequestError(
                            f"{AIRequestError.code}: 网络请求失败（已尝试 {attempt} 次）"
                        ) from exc
                    self._backoff(attempt)
                    continue

                if response.status_code in {408, 409, 429} or response.status_code >= 500:
                    if attempt <= max_retries:
                        self._backoff(attempt)
                        continue
                if response.is_error:
                    raise AIRequestError(self._error_text(response, url=url, token_hint=token_hint))
                return self._parse_response(response, attempt, parser)

        raise AssertionError("unreachable")

    def _backoff(self, attempt: int) -> None:
        self._sleeper(min(0.25 * (2 ** (attempt - 1)), 1.0))

    @staticmethod
    def _error_text(response: httpx.Response, url: str = "", token_hint: str = "") -> str:
        snippet = (response.text or "").strip().replace("\n", " ")
        if len(snippet) > 280:
            snippet = snippet[:280] + "…"
        suffix = f"：{snippet}" if snippet else ""
        where = f" {url}" if url else ""
        hint = f" key=…{token_hint}" if token_hint else ""
        return f"{AIRequestError.code}: 网关返回 HTTP {response.status_code}{where}{hint}{suffix}"

    @staticmethod
    def _parse_response(response: httpx.Response, attempts: int, parser: str) -> MessageResult:
        try:
            body = response.json()
            if parser == "openai":
                text, usage = _openai_text_and_usage(body)
            else:
                text, usage = _anthropic_text_and_usage(body)
            if not text:
                raise ValueError("响应不含 text content")
            return MessageResult(
                text=text,
                usage=TokenUsage(
                    input_tokens=usage.get("input_tokens", 0),
                    output_tokens=usage.get("output_tokens", 0),
                ),
                attempts=attempts,
            )
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            raise AIRequestError(
                f"{AIRequestError.code}: 网关响应格式不兼容"
            ) from exc


def _anthropic_text_and_usage(body: dict[str, Any]) -> tuple[str, dict[str, int]]:
    text = "".join(
        item.get("text", "")
        for item in body["content"]
        if item.get("type") == "text"
    )
    usage = body.get("usage") or {}
    return text, {
        "input_tokens": int(usage.get("input_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or 0),
    }


def _openai_text_and_usage(body: dict[str, Any]) -> tuple[str, dict[str, int]]:
    message = body["choices"][0]["message"]
    content = message.get("content")
    if isinstance(content, list):
        text = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    else:
        text = str(content or "")
    if not text.strip():
        text = str(message.get("reasoning_content") or "")
    usage = body.get("usage") or {}
    return text, {
        "input_tokens": int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0),
        "output_tokens": int(usage.get("completion_tokens") or usage.get("output_tokens") or 0),
    }
