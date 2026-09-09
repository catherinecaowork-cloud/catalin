"""P1.2 AI 编译层自测；所有 HTTP 请求均由 MockTransport 接管。"""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx

from autotest_control.ai import (
    AICompiler,
    AIConfigurationError,
    AIContractError,
    AnthropicClient,
    CompileContract,
    apply_contract,
    parse_contract,
)
from autotest_protocol import Step


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"× {message}")
    print(f"√ {message}")


def _raises(error_type: type[Exception], call, message: str) -> None:
    try:
        call()
    except error_type:
        print(f"√ {message}")
        return
    raise SystemExit(f"× {message}")


def _config(**overrides):
    values = {
        "anthropic_base_url": "https://gateway.example/anthropic",
        "anthropic_auth_token": "secret-token",
        "anthropic_model": "claude-compatible",
        "anthropic_timeout_seconds": 3,
        "anthropic_max_tokens": 777,
        "anthropic_vision_enabled": False,
        "anthropic_max_retries": 2,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _steps() -> list[Step]:
    target = {
        "candidates": [
            {"kind": "label", "value": "款式编码"},
            {"kind": "css", "value": "#style-code"},
        ]
    }
    return [
        Step(id="s1", action="goto", value="/styles"),
        Step(id="s2", action="fill", target=target, value="ABC123"),
        Step(id="s3", action="click", target={"candidates": [{"kind": "text", "value": "保存"}]}),
    ]


def _anthropic_response(text: str, *, status: int = 200) -> httpx.Response:
    return httpx.Response(
        status,
        json={
            "content": [{"type": "text", "text": text}],
            "usage": {"input_tokens": 12, "output_tokens": 8},
        },
    )


def main() -> int:
    requests: list[httpx.Request] = []
    legal = {
        "step_edits": [
            {
                "source_id": "s2",
                "label": "填写唯一款式编码",
                "mutating": True,
                "value": "{{unique:style_code}}",
            },
            {"source_id": "s3", "label": "保存款式", "mutating": True},
        ],
        "assertions": [
            {
                "id": "a1",
                "assert_kind": "element_visible",
                "target": "s3",
                "expected": "true",
                "label": "保存按钮仍可见",
            }
        ],
        "notes": ["建议先在测试环境回放"],
    }

    def success_handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _anthropic_response(json.dumps(legal, ensure_ascii=False))

    result = AICompiler(
        AnthropicClient(
            config=_config(),
            transport=httpx.MockTransport(success_handler),
            sleeper=lambda _: None,
        )
    ).compile(_steps(), intent="新增款式")

    _assert(requests[0].url == "https://gateway.example/anthropic/v1/messages", "调用 /v1/messages")
    _assert(requests[0].headers["authorization"] == "Bearer secret-token", "使用 Bearer 鉴权")
    sent = json.loads(requests[0].content)
    _assert(sent["model"] == "claude-compatible" and sent["max_tokens"] == 777, "发送模型和 max tokens 配置")
    _assert([step.id for step in result.steps[:3]] == ["s1", "s2", "s3"], "确定性步骤顺序不变")
    _assert(result.steps[1].action == "fill" and result.steps[1].target == _steps()[1].target, "action/target 不变")
    _assert(result.steps[1].value == "{{unique:style_code}}" and result.steps[1].mutating, "应用合法字段修改")
    _assert([step.id for step in result.steps] == ["s1", "s2", "s3"], "模型追加的断言被忽略")
    _assert(result.usage.total_tokens == 20 and result.attempts == 1, "返回 token usage 和尝试次数")

    fenced = f"```json\n{json.dumps(legal, ensure_ascii=False)}\n```"
    _assert(len(parse_contract(fenced).step_edits) == 2, "可解析 Markdown JSON 围栏")

    _raises(
        AIContractError,
        lambda: parse_contract(
            '{"step_edits":[{"source_id":"s2","action":"click"}],"assertions":[],"notes":[]}'
        ),
        "拒绝越权修改 action",
    )
    dropped = apply_contract(
        _steps(),
        CompileContract.model_validate(
            {
                "step_edits": [],
                "assertions": [
                    {
                        "id": "a2",
                        "assert_kind": "element_visible",
                        "target": "missing",
                        "expected": "true",
                    }
                ],
                "notes": [],
            }
        ),
    )
    _assert([step.id for step in dropped] == ["s1", "s2", "s3"], "模型断言即使引用无效步骤也不写入")
    _raises(
        AIContractError,
        lambda: apply_contract(
            _steps(),
            CompileContract.model_validate(
                {
                    "step_edits": [{"source_id": "s2", "value": "{{pick:category}}"}],
                    "assertions": [],
                    "notes": [],
                }
            ),
        ),
        "拒绝非 unique/now/env 模板",
    )

    missing_client = AnthropicClient(
        config=_config(anthropic_auth_token=""),
        transport=httpx.MockTransport(lambda _: _anthropic_response("{}")),
    )
    _raises(
        AIConfigurationError,
        lambda: missing_client.create_message("test"),
        "缺配置抛出可识别异常",
    )

    attempts = 0

    def retry_handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(503, json={"error": "busy"})
        return _anthropic_response("{}")

    retry_result = AnthropicClient(
        config=_config(),
        transport=httpx.MockTransport(retry_handler),
        sleeper=lambda _: None,
    ).create_message("test")
    _assert(attempts == 3 and retry_result.attempts == 3, "瞬态错误进行有限重试")

    openai_requests: list[httpx.Request] = []

    def openai_handler(request: httpx.Request) -> httpx.Response:
        openai_requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1},
            },
        )

    glm_result = AnthropicClient(
        config=_config(anthropic_model="glm-5.1"),
        transport=httpx.MockTransport(openai_handler),
        sleeper=lambda _: None,
    ).create_message("hi")
    _assert(
        str(openai_requests[0].url).endswith("/v1/chat/completions"),
        "glm-5.1 走 Chat Completions 而不是 /v1/messages",
    )
    _assert(glm_result.text == "ok" and glm_result.usage.total_tokens == 4, "解析 OpenAI 兼容响应")

    print("\nAI 编译层自测通过；未请求真实网关。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
