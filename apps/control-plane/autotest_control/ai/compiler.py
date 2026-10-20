"""将受约束的模型建议安全应用到确定性步骤。"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from autotest_protocol import Step

from .client import AnthropicClient
from .schemas import CompileContract, CompileResult, ImageInput

_FENCE_RE = re.compile(
    r"^\s*```(?:json)?\s*(?P<body>.*?)\s*```\s*$",
    flags=re.IGNORECASE | re.DOTALL,
)
_TEMPLATE_RE = re.compile(r"\{\{(?P<kind>[a-zA-Z_]+):(?P<arg>[^{}]+)\}\}")
_ALLOWED_TEMPLATE_KINDS = {"unique", "now", "env"}
_KEY_RE = re.compile(r"^[a-zA-Z0-9._-]+$")
_TIME_DIRECTIVES = set("aAwdbBmyYHIMSpfzZjUWcxX%GVu")


class AIContractError(ValueError):
    """模型输出违反编译器边界。"""

    code = "ai_contract_invalid"

    def __init__(self, message: str) -> None:
        super().__init__(f"{self.code}: {message}")


def parse_contract(text: str) -> CompileContract:
    """解析纯 JSON 或单个 Markdown JSON 围栏。"""

    match = _FENCE_RE.match(text)
    raw = match.group("body") if match else text.strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AIContractError(f"模型输出不是合法 JSON：{exc.msg}") from exc
    try:
        return CompileContract.model_validate(data)
    except ValidationError as exc:
        raise AIContractError(f"模型输出不符合契约：{exc}") from exc


def _validate_value_templates(value: str, source_id: str) -> None:
    matches = list(_TEMPLATE_RE.finditer(value))
    for match in matches:
        if match.group("kind") not in _ALLOWED_TEMPLATE_KINDS:
            raise AIContractError(
                f"步骤 {source_id} 使用了不允许的模板 {match.group(0)}"
            )
        if not match.group("arg").strip():
            raise AIContractError(f"步骤 {source_id} 的模板参数不能为空")
        kind = match.group("kind")
        argument = match.group("arg")
        if kind in {"unique", "env"} and not _KEY_RE.fullmatch(argument):
            raise AIContractError(f"步骤 {source_id} 的 {kind} 模板键名无效")
        if kind == "now":
            _validate_time_format(argument, source_id)
    remainder = _TEMPLATE_RE.sub("", value)
    if "{{" in remainder or "}}" in remainder:
        raise AIContractError(f"步骤 {source_id} 含格式错误的 value 模板")


def _validate_time_format(value: str, source_id: str) -> None:
    index = 0
    while index < len(value):
        if value[index] != "%":
            index += 1
            continue
        index += 1
        if index >= len(value) or value[index] not in _TIME_DIRECTIVES:
            raise AIContractError(f"步骤 {source_id} 的 now 时间格式无效")
        index += 1


def validate_template_value(value: str | None, source_id: str) -> None:
    """给保存接口复用的模板语法门禁；不解析运行时 env 值。"""
    if value is not None:
        _validate_value_templates(value, source_id)


def _validated_step(data: dict[str, Any], description: str) -> Step:
    try:
        return Step.model_validate(data)
    except ValidationError as exc:
        raise AIContractError(f"{description} 未通过 Step 校验：{exc}") from exc


def apply_contract(steps: list[Step], contract: CompileContract) -> list[Step]:
    """应用白名单字段，并保证原步骤 action/target/顺序不变。"""

    source_by_id = {step.id: step for step in steps}
    if len(source_by_id) != len(steps):
        raise AIContractError("确定性步骤 id 必须唯一")

    edits_by_id = {}
    for edit in contract.step_edits:
        if edit.source_id not in source_by_id:
            raise AIContractError(f"step_edits 引用了不存在的步骤 {edit.source_id}")
        if edit.source_id in edits_by_id:
            raise AIContractError(f"步骤 {edit.source_id} 出现了重复 edit")
        edits_by_id[edit.source_id] = edit

    result: list[Step] = []
    for original in steps:
        data = original.model_dump()
        edit = edits_by_id.get(original.id)
        if edit is not None:
            changes = edit.model_dump(exclude={"source_id"}, exclude_unset=True)
            if changes.get("mutating", False) is None:
                raise AIContractError(f"步骤 {original.id} 的 mutating 不能为 null")
            if "value" in changes and changes["value"] is not None:
                _validate_value_templates(changes["value"], original.id)
            if "phase" in changes and "phase" not in Step.model_fields:
                raise AIContractError("当前 Step DSL 尚未提供 phase 字段")
            data.update(changes)
        checked = _validated_step(data, f"步骤 {original.id}")
        if checked.action != original.action or checked.target != original.target:
            raise AIContractError(f"步骤 {original.id} 的 action/target 不得更改")
        result.append(checked)

    # 模型提议的断言一律不进步骤；需要校验时在确认页手工添加。

    # 最后逐条重新校验，避免 model_copy 或未来 DSL 变更绕过字段约束。
    return [
        _validated_step(step.model_dump(), f"结果步骤 {step.id}") for step in result
    ]


class AICompiler:
    def __init__(self, client: AnthropicClient | None = None) -> None:
        self.client = client or AnthropicClient()

    def compile(
        self,
        steps: list[Step],
        *,
        intent: str = "",
        context: dict[str, Any] | None = None,
        images: list[ImageInput] | None = None,
    ) -> CompileResult:
        message = self.client.create_message(
            self._prompt(steps, intent=intent, context=context or {}),
            system=self._system_prompt(),
            images=images,
        )
        contract = parse_contract(message.text)
        compiled = apply_contract(steps, contract)
        return CompileResult(
            steps=compiled,
            notes=contract.notes,
            usage=message.usage,
            attempts=message.attempts,
        )

    @staticmethod
    def _system_prompt() -> str:
        schema = json.dumps(
            CompileContract.model_json_schema(), ensure_ascii=False, separators=(",", ":")
        )
        return (
            "你是自动化测试步骤编译器。只返回一个符合给定 JSON Schema 的 JSON 对象，"
            "不要返回解释。只能按 source_id 修改 label、phase、mutating、value；"
            "不能输出或修改 action、target、步骤顺序。不要生成断言步骤。"
            "请把每步 label 改成业务可读中文，并分到 setup、main、verify；"
            "准确标记会写数据的 mutating。编码、编号、名称等可能唯一的录入值应改成"
            "{{unique:英文语义键}}，日期可用 {{now:%Y%m%d}}，不要生成 pick 模板。"
            "不要追加断言，assertions 必须是空数组；录制没有的校验不要编造。"
            "value 模板仅可使用 unique、now、env。"
            "如果提供 previous_failure，必须针对失败原因修正可修改字段。JSON Schema："
            f"{schema}"
        )

    @staticmethod
    def _prompt(
        steps: list[Step], *, intent: str, context: dict[str, Any]
    ) -> str:
        payload = {
            "intent": intent,
            "steps": [step.model_dump(mode="json") for step in steps],
            "context": context,
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
