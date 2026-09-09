"""观察者编写契约与润色路径隔离。"""

from __future__ import annotations

import json

import httpx
import pytest

from autotest_control.ai import (
    AIContractError,
    AIObserver,
    AnthropicClient,
    apply_contract,
    parse_observer_contract,
    validate_observer_steps,
)
from autotest_control.ai.schemas import CompileContract, StepEdit
from autotest_protocol import Step, Target, Candidate


def _choose_step(value: str, *, mode: str = "search_or_first") -> Step:
    return Step(
        id="s-size",
        action="choose",
        label="选择尺码",
        value=value,
        choose_mode=mode,  # type: ignore[arg-type]
        target=Target(candidates=[Candidate(kind="label", value="尺码")]),
    )


def test_observer_rejects_exact_size_sample() -> None:
    with pytest.raises(AIContractError, match="exact"):
        validate_observer_steps([_choose_step("155", mode="exact")])


def test_observer_allows_search_or_first_size_hint() -> None:
    steps = validate_observer_steps(
        [_choose_step("155", mode="search_or_first")],
        sample_steps=[_choose_step("155", mode="search_or_first")],
    )
    assert steps[0].choose_mode == "search_or_first"


def test_observer_requires_unique_for_code_field() -> None:
    step = Step(
        id="s-code",
        action="fill",
        label="填写款式编码",
        value="ST-001",
        target=Target(candidates=[Candidate(kind="label", value="款式编码")]),
    )
    with pytest.raises(AIContractError, match="unique"):
        validate_observer_steps([step])


def test_polish_path_only_changes_safe_fields() -> None:
    original = Step(
        id="s1",
        action="click",
        target=Target(candidates=[Candidate(kind="text", value="保存")]),
    )
    contract = CompileContract(
        step_edits=[StepEdit(source_id="s1", label="保存款式", mutating=True)]
    )
    result = apply_contract([original], contract)
    assert result[0].label == "保存款式"
    assert result[0].action == "click"
    assert result[0].target == original.target


def test_observer_allows_skeleton_rewrite() -> None:
    sample = Step(
        id="s1",
        action="click",
        target=Target(candidates=[Candidate(kind="text", value="155")]),
    )
    rewritten = Step(
        id="s1",
        action="choose",
        label="选择尺码",
        value="155",
        choose_mode="other",
        target=Target(candidates=[Candidate(kind="label", value="尺码")]),
    )
    validated = validate_observer_steps([rewritten], sample_steps=[sample])
    assert validated[0].action == "choose"


def test_parse_observer_contract_rejects_bad_widget_identity() -> None:
    payload = {
        "steps": [
            {
                "id": "s1",
                "action": "goto",
                "value": "/",
            }
        ],
        "page_widget_entries": [
            {
                "id": "bad",
                "layer": {"kind": "modal", "name": "新增"},
                "display_name": "155",
                "widget_kind": "tab",
                "operation": "choose",
                "value_strategy": "choose_any",
            }
        ],
        "notes": [],
    }
    with pytest.raises(AIContractError):
        parse_observer_contract(json.dumps(payload, ensure_ascii=False))


def test_ai_observer_mock_write() -> None:
    contract = {
        "steps": [
            {
                "id": "s1",
                "action": "choose",
                "label": "选择尺码",
                "value": "155",
                "choose_mode": "other",
                "target": {
                    "candidates": [{"kind": "label", "value": "尺码"}],
                },
            }
        ],
        "page_widget_entries": [
            {
                "id": "size",
                "layer": {"kind": "modal", "name": "新增款式"},
                "display_name": "尺码",
                "widget_kind": "tab",
                "operation": "choose",
                "value_strategy": "choose_any",
                "choose_mode": "other",
            }
        ],
        "notes": ["任选尺码"],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": json.dumps(contract, ensure_ascii=False)}],
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    sample = [
        Step(id="sample", action="click", target=Target(candidates=[Candidate(kind="text", value="155")])),
    ]
    client = AnthropicClient(
        config=type(
            "Cfg",
            (),
            {
                "anthropic_base_url": "https://example.test",
                "anthropic_auth_token": "t",
                "anthropic_model": "m",
                "anthropic_timeout_seconds": 3,
                "anthropic_max_tokens": 100,
                "anthropic_vision_enabled": False,
                "anthropic_max_retries": 1,
            },
        )(),
        transport=httpx.MockTransport(handler),
        sleeper=lambda _: None,
    )
    result = AIObserver(client).write(sample, intent="新增款式", page_model={"entries": []})
    assert result.steps[0].choose_mode == "other"
    assert result.page_widget_entries[0].display_name == "尺码"
