"""AI 观察者：根据页面认识与样例轨迹编写可回放 DSL。"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from autotest_protocol import Step, is_transient_component_identity

from .client import AnthropicClient
from .compiler import AIContractError, _FENCE_RE, validate_template_value
from .observer_schemas import ObserverContract, ObserverResult
from .schemas import ImageInput

_CODE_LABEL = re.compile(r"编码|code|sku|单号|编号|款式号", re.I)
_ALLOWED_CHOOSE_MODES = {"search_or_first", "other"}


def parse_observer_contract(text: str) -> ObserverContract:
    match = _FENCE_RE.match(text)
    raw = match.group("body") if match else text.strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AIContractError(f"模型输出不是合法 JSON：{exc.msg}") from exc
    try:
        return ObserverContract.model_validate(data)
    except ValidationError as exc:
        raise AIContractError(f"观察者输出不符合契约：{exc}") from exc


def _sample_choose_values(sample_steps: list[Step]) -> set[str]:
    values: set[str] = set()
    for step in sample_steps:
        if step.action == "choose" and step.value:
            values.add(step.value.strip())
        if step.action == "click" and step.value:
            text = str(step.label or step.value).strip()
            if text:
                values.add(text)
    return values


def _requires_unique_value(step: Step) -> bool:
    label = step.label or ""
    if _CODE_LABEL.search(label):
        return True
    if step.action == "fill" and step.value and not step.value.startswith("{{"):
        if _CODE_LABEL.search(label) or "编码" in label:
            return True
    return False


def validate_observer_steps(
    steps: list[Step],
    *,
    sample_steps: list[Step] | None = None,
    intent: str = "",
) -> list[Step]:
    """观察者路径允许改骨架，但仍须遵守 DSL 与任选/参数化策略。"""
    del intent  # 预留：意图明确要求固定主数据时可放宽
    if not steps:
        raise AIContractError("观察者必须输出至少一步")
    sample_values = _sample_choose_values(sample_steps or [])
    validated: list[Step] = []
    seen_ids: set[str] = set()
    for step in steps:
        if step.id in seen_ids:
            raise AIContractError(f"步骤 id 重复：{step.id}")
        seen_ids.add(step.id)
        if step.action == "choose":
            mode = step.choose_mode
            if mode == "exact":
                raise AIContractError(f"步骤 {step.id} 不得使用 choose_mode=exact")
            if mode not in _ALLOWED_CHOOSE_MODES:
                raise AIContractError(
                    f"步骤 {step.id} 的选择类步骤须使用 search_or_first 或 other"
                )
            value = (step.value or "").strip()
            if value and is_transient_component_identity(value):
                if mode != "search_or_first" and mode != "other":
                    raise AIContractError(
                        f"步骤 {step.id} 不能把样例选项 {value!r} 当作唯一合法值"
                    )
            elif value and value in sample_values and mode not in _ALLOWED_CHOOSE_MODES:
                raise AIContractError(
                    f"步骤 {step.id} 样例选项 {value!r} 须配合任选策略，不得写死回归值"
                )
        if step.action in {"fill", "choose", "select"} and step.value is not None:
            validate_template_value(step.value, step.id)
        if step.action == "fill" and _requires_unique_value(step):
            if not step.value or "{{unique:" not in step.value:
                raise AIContractError(f"步骤 {step.id} 的编码类填值须使用 {{{{unique:key}}}}")
        validated.append(step)
    return validated


class AIObserver:
    def __init__(self, client: AnthropicClient | None = None) -> None:
        self.client = client or AnthropicClient()

    def write(
        self,
        sample_steps: list[Step],
        *,
        intent: str = "",
        page_model: dict[str, Any] | None = None,
        snapshots: list[dict[str, Any]] | None = None,
        site_page_model: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        images: list[ImageInput] | None = None,
    ) -> ObserverResult:
        message = self.client.create_message(
            self._prompt(
                sample_steps,
                intent=intent,
                page_model=page_model or {},
                snapshots=snapshots or [],
                site_page_model=site_page_model or {},
                context=context or {},
            ),
            system=self._system_prompt(),
            images=images,
        )
        contract = parse_observer_contract(message.text)
        steps = validate_observer_steps(
            contract.steps,
            sample_steps=sample_steps,
            intent=intent,
        )
        return ObserverResult(
            steps=steps,
            page_widget_entries=list(contract.page_widget_entries),
            notes=contract.notes,
            usage=message.usage,
            attempts=message.attempts,
        )

    @staticmethod
    def _system_prompt() -> str:
        schema = json.dumps(
            ObserverContract.model_json_schema(), ensure_ascii=False, separators=(",", ":")
        )
        return (
            "你是自动化测试 AI 观察者。根据录制意图、页面认识、观察快照与样例轨迹，"
            "编写可日常回归的 Playwright DSL 步骤与页面模型条目。"
            "只返回一个符合 JSON Schema 的 JSON 对象，不要解释。"
            "你可以改写 action、target、步骤顺序与数量；但只能使用平台已有动作原语。"
            "样例轨迹里的具体选项文案（如尺码 155、品牌 Gucci）不是回归契约："
            "选择类步骤必须用 choose，并设 choose_mode 为 search_or_first 或 other，"
            "禁止 choose_mode=exact。"
            "可搜索下拉用 search_or_first；Tab/尺码/面板用 other。"
            "编码、单号等唯一性输入须用 {{unique:英文语义键}}，不得抄样例固定字符串。"
            "page_widget_entries 登记字段/组件用法，不得把动态选项文案登记为 display_name。"
            "不要输出 assert 步骤；notes 可写编写说明。JSON Schema："
            f"{schema}"
        )

    @staticmethod
    def _prompt(
        sample_steps: list[Step],
        *,
        intent: str,
        page_model: dict[str, Any],
        snapshots: list[dict[str, Any]],
        site_page_model: dict[str, Any],
        context: dict[str, Any],
    ) -> str:
        payload = {
            "intent": intent,
            "sample_steps": [step.model_dump(mode="json", exclude_none=True) for step in sample_steps],
            "page_model": page_model,
            "site_page_model": site_page_model,
            "snapshots": snapshots[-20:],
            "context": context,
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
