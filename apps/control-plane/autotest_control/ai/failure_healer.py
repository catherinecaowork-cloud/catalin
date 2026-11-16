"""回放失败 → AI 提出结构化补丁（定位候选 / 对象重绑 / 数据策略）。

日常回归零模型调用；本模块只在失败后、人工或 API 显式触发时介入。
不确定时必须 ``requires_human_confirm=true``，禁止静默改生产脚本。
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from autotest_protocol import DataStrategy, Target

from .client import AIConfigurationError, AnthropicClient
from .compiler import AIContractError
from .schemas import ImageInput, TokenUsage

_FENCE_RE = re.compile(
    r"^\s*```(?:json)?\s*(?P<body>.*?)\s*```\s*$",
    flags=re.IGNORECASE | re.DOTALL,
)

ErrorClass = Literal["locator", "data_strategy", "uncertain"]
PatchKind = Literal["target_candidates", "object_rebind", "data_strategy"]
StrategyField = Literal["value_strategy", "expected_strategy"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FailureHealPatch(StrictModel):
    """一条可审计的补丁提案。"""

    kind: PatchKind
    step_id: str = Field(min_length=1)
    object_id: str | None = None
    candidates: list[dict[str, Any]] | None = None
    field: StrategyField | None = None
    strategy: dict[str, Any] | None = None
    rationale: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _shape(self) -> FailureHealPatch:
        if self.kind in {"target_candidates", "object_rebind"}:
            if not self.candidates:
                raise ValueError(f"{self.kind} 需要非空 candidates")
            Target.model_validate({"candidates": self.candidates})
            if self.kind == "object_rebind" and not (self.object_id or "").strip():
                raise ValueError("object_rebind 需要 object_id")
        if self.kind == "data_strategy":
            if self.field not in {"value_strategy", "expected_strategy"}:
                raise ValueError("data_strategy 补丁需要 field=value_strategy|expected_strategy")
            if not isinstance(self.strategy, dict):
                raise ValueError("data_strategy 补丁需要 strategy 对象")
            DataStrategy.model_validate(self.strategy)
        return self


class FailureHealContract(StrictModel):
    error_class: ErrorClass
    requires_human_confirm: bool = True
    patches: list[FailureHealPatch] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _uncertain_needs_confirm(self) -> FailureHealContract:
        low = any(p.confidence < 0.6 for p in self.patches)
        if self.error_class == "uncertain" or low or not self.patches:
            self.requires_human_confirm = True
        return self


class FailureHealResult(StrictModel):
    contract: FailureHealContract
    usage: TokenUsage
    attempts: int = Field(ge=1)
    source: Literal["ai", "fixture"] = "ai"


def classify_error_class(step_result: dict[str, Any] | None) -> ErrorClass:
    """把执行器失败字段收敛成 locator | data_strategy | uncertain。"""
    if not isinstance(step_result, dict):
        return "uncertain"
    failure = str(step_result.get("failure") or "").strip()
    if failure == "data_strategy":
        return "data_strategy"
    if failure in {"not_found", "no_effect", "covered", "locator", "target_not_found"}:
        return "locator"
    kind = str(step_result.get("failure_kind") or "").strip()
    if kind in {"target_changed", "overlay_absent", "covered", "timeout"}:
        # 环境原因仍归 locator 大类（定位交互），与 data_strategy 分开
        return "locator"
    if step_result.get("strategy") and failure:
        return "data_strategy"
    message = str(step_result.get("message") or "").lower()
    if "data_strategy" in message or "缺少环境" in message or "lookup" in message:
        return "data_strategy"
    if "找不到" in message or "target" in message or "locator" in message:
        return "locator"
    return "uncertain"


def build_failure_context(
    *,
    run_id: str,
    flow_id: str,
    step: dict[str, Any],
    step_result: dict[str, Any],
    object_def: dict[str, Any] | None = None,
    screenshot: str | None = None,
    env_data_keys: list[str] | None = None,
    tried: list[str] | None = None,
) -> dict[str, Any]:
    """压缩失败上下文，避免把整页 DOM / 密钥塞进提示词。"""
    error_class = classify_error_class(step_result)
    compact_step = {
        "id": step.get("id"),
        "action": step.get("action"),
        "label": step.get("label"),
        "object_id": step.get("object_id"),
        "target": _compact_target(step.get("target")),
        "value": step.get("value"),
        "value_strategy": step.get("value_strategy"),
        "expected": step.get("expected"),
        "expected_strategy": step.get("expected_strategy"),
    }
    return {
        "run_id": run_id,
        "flow_id": flow_id,
        "step_id": str(step.get("id") or step_result.get("step_id") or ""),
        "step": compact_step,
        "object_id": step.get("object_id"),
        "object_def": _compact_object(object_def),
        "error_class": error_class,
        "failure": step_result.get("failure"),
        "failure_kind": step_result.get("failure_kind"),
        "strategy": step_result.get("strategy"),
        "message": str(step_result.get("message") or "")[:500],
        "screenshot": screenshot,
        "tried_candidates": list(tried or [])[:12],
        "env_data_keys": list(env_data_keys or [])[:40],
    }


def _compact_target(target: Any) -> dict[str, Any] | None:
    if not isinstance(target, dict):
        return None
    candidates = target.get("candidates")
    if not isinstance(candidates, list):
        return {"candidates": []}
    return {
        "candidates": [
            {k: c.get(k) for k in ("kind", "value", "name") if isinstance(c, dict) and c.get(k) is not None}
            for c in candidates[:8]
        ],
        "widget": target.get("widget"),
        "panel": target.get("panel"),
    }


def _compact_object(obj: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(obj, dict):
        return None
    return {
        "id": obj.get("id"),
        "key": obj.get("key"),
        "name": obj.get("name"),
        "target": _compact_target(obj.get("target")),
    }


def parse_failure_heal_contract(text: str) -> FailureHealContract:
    match = _FENCE_RE.match(text)
    raw = match.group("body") if match else text.strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AIContractError(f"模型输出不是合法 JSON：{exc.msg}") from exc
    try:
        return FailureHealContract.model_validate(data)
    except ValidationError as exc:
        raise AIContractError(f"模型输出不符合失败修复契约：{exc}") from exc


def fixture_propose(context: dict[str, Any]) -> FailureHealContract:
    """无 API Key / 显式 fixture 模式：确定性提案，便于本地单测。"""
    error_class = context.get("error_class") or "uncertain"
    step = context.get("step") if isinstance(context.get("step"), dict) else {}
    step_id = str(context.get("step_id") or step.get("id") or "")
    notes: list[str] = ["fixture 模式：未调用真实模型"]
    patches: list[FailureHealPatch] = []

    if error_class == "data_strategy":
        patches.append(_fixture_data_strategy_patch(step_id, step, context))
        notes.append("建议把字面量/脆弱策略改成 env 或 lookup")
    elif error_class == "locator":
        patch = _fixture_locator_patch(step_id, step, context)
        if patch is not None:
            patches.append(patch)
        notes.append("建议调整定位候选或对象库定义")
    else:
        notes.append("失败类别不确定，仅生成待人工确认的空提案，禁止自动写回")

    return FailureHealContract(
        error_class=error_class if error_class in {"locator", "data_strategy", "uncertain"} else "uncertain",
        requires_human_confirm=True,
        patches=patches,
        notes=notes,
    )


def _fixture_data_strategy_patch(
    step_id: str, step: dict[str, Any], context: dict[str, Any]
) -> FailureHealPatch:
    keys = context.get("env_data_keys") if isinstance(context.get("env_data_keys"), list) else []
    preferred = str(keys[0]) if keys else "order_no"
    current = step.get("value_strategy")
    if isinstance(current, dict) and current.get("kind") == "literal":
        rationale = "字面量在跨环境会失效，改为 env"
    else:
        rationale = "数据策略失败：改为从环境数据档取值"
    return FailureHealPatch(
        kind="data_strategy",
        step_id=step_id,
        field="value_strategy",
        strategy={"kind": "env", "key": preferred},
        rationale=rationale,
        confidence=0.72,
    )


def _fixture_locator_patch(
    step_id: str, step: dict[str, Any], context: dict[str, Any]
) -> FailureHealPatch | None:
    object_id = step.get("object_id") or context.get("object_id")
    object_def = context.get("object_def") if isinstance(context.get("object_def"), dict) else None
    target = None
    if object_def and isinstance(object_def.get("target"), dict):
        target = object_def["target"]
    elif isinstance(step.get("target"), dict):
        target = step["target"]
    candidates = list((target or {}).get("candidates") or [])
    tried = context.get("tried_candidates") if isinstance(context.get("tried_candidates"), list) else []

    new_candidates: list[dict[str, Any]] = []
    if tried:
        # 把 tried 里看起来像 css/testid 的线索提到前面（fixture 启发式）
        for item in tried:
            text = str(item)
            if text.startswith("#") or text.startswith(".") or text.startswith("["):
                new_candidates.append({"kind": "css", "value": text})
            elif "=" in text and text.split("=", 1)[0] in {"css", "testid", "role", "label", "text", "placeholder"}:
                kind, value = text.split("=", 1)
                new_candidates.append({"kind": kind, "value": value.strip("'\"")})
    for c in candidates:
        if isinstance(c, dict) and c not in new_candidates:
            new_candidates.append(c)
    if not new_candidates:
        new_candidates = [{"kind": "css", "value": "[data-testid='healed']"}]

    # 校验
    Target.model_validate({"candidates": new_candidates})
    if object_id:
        return FailureHealPatch(
            kind="object_rebind",
            step_id=step_id,
            object_id=str(object_id),
            candidates=new_candidates,
            rationale="定位失败且步骤引用对象库：更新对象定义候选",
            confidence=0.68,
        )
    return FailureHealPatch(
        kind="target_candidates",
        step_id=step_id,
        candidates=new_candidates,
        rationale="定位失败：重排/补充步骤 target 候选",
        confidence=0.65,
    )


def apply_failure_patches(
    flow_steps: list[Any],
    patches: list[FailureHealPatch] | list[dict[str, Any]],
    *,
    objects: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """把提案应用到流程步骤与对象库副本。

    返回 ``(new_steps, object_updates, audit_log)``。
    ``audit_log`` 每条含 proposed / applied / status，便于对照。
    """
    parsed: list[FailureHealPatch] = []
    for raw in patches or []:
        if isinstance(raw, FailureHealPatch):
            parsed.append(raw)
        else:
            parsed.append(FailureHealPatch.model_validate(raw))

    steps = [dict(s) if isinstance(s, dict) else s for s in (flow_steps or [])]
    by_id = {
        str(s.get("id")): (i, s)
        for i, s in enumerate(steps)
        if isinstance(s, dict) and s.get("id")
    }
    object_updates: dict[str, dict[str, Any]] = {}
    objects = dict(objects or {})
    audit: list[dict[str, Any]] = []

    for patch in parsed:
        proposed = patch.model_dump(mode="json")
        if patch.kind == "object_rebind":
            oid = str(patch.object_id)
            current = objects.get(oid) or object_updates.get(oid)
            if current is None and oid not in objects:
                audit.append(
                    {
                        "status": "skipped",
                        "proposed": proposed,
                        "applied": None,
                        "reason": f"对象 {oid} 不在当前站点对象库",
                    }
                )
                continue
            base = dict(current or objects.get(oid) or {})
            new_target = dict(base.get("target") or {})
            new_target["candidates"] = patch.candidates
            updated = {**base, "id": oid, "target": new_target}
            object_updates[oid] = updated
            objects[oid] = updated
            audit.append(
                {
                    "status": "applied",
                    "proposed": proposed,
                    "applied": {
                        "kind": "object_rebind",
                        "object_id": oid,
                        "candidates": patch.candidates,
                    },
                    "reason": patch.rationale or "已更新对象定义",
                }
            )
            continue

        entry = by_id.get(patch.step_id)
        if entry is None:
            audit.append(
                {
                    "status": "skipped",
                    "proposed": proposed,
                    "applied": None,
                    "reason": f"流程中找不到步骤 {patch.step_id}",
                }
            )
            continue
        index, step = entry
        new_step = dict(step)
        if patch.kind == "target_candidates":
            target = dict(step.get("target") or {})
            target["candidates"] = patch.candidates
            new_step["target"] = target
            applied = {"kind": "target_candidates", "step_id": patch.step_id, "candidates": patch.candidates}
        else:
            assert patch.field is not None and patch.strategy is not None
            new_step[patch.field] = patch.strategy
            # 换策略后清掉冲突的裸 value，避免解析优先顺序歧义
            if patch.field == "value_strategy" and "value" in new_step:
                new_step.pop("value", None)
            if patch.field == "expected_strategy" and "expected" in new_step:
                new_step.pop("expected", None)
            applied = {
                "kind": "data_strategy",
                "step_id": patch.step_id,
                "field": patch.field,
                "strategy": patch.strategy,
            }
        steps[index] = new_step
        by_id[patch.step_id] = (index, new_step)
        audit.append(
            {
                "status": "applied",
                "proposed": proposed,
                "applied": applied,
                "reason": patch.rationale or "已写回流程步骤",
            }
        )
    return steps, object_updates, audit


class AIFailureHealer:
    """失败修复编译器：复用 AnthropicClient；可 fixture 短路。"""

    def __init__(self, client: AnthropicClient | None = None) -> None:
        self.client = client or AnthropicClient()

    def propose(
        self,
        context: dict[str, Any],
        *,
        fixture_mode: bool | None = None,
        images: list[ImageInput] | None = None,
    ) -> FailureHealResult:
        use_fixture = fixture_mode
        if use_fixture is None:
            use_fixture = not self._ai_ready()
        if use_fixture:
            contract = fixture_propose(context)
            return FailureHealResult(
                contract=contract,
                usage=TokenUsage(),
                attempts=1,
                source="fixture",
            )
        message = self.client.create_message(
            self._prompt(context),
            system=self._system_prompt(),
            images=images,
        )
        contract = parse_failure_heal_contract(message.text)
        return FailureHealResult(
            contract=contract,
            usage=message.usage,
            attempts=message.attempts,
            source="ai",
        )

    def _ai_ready(self) -> bool:
        try:
            self.client._required_config()  # noqa: SLF001 — 与 AICompiler 同网关
            return True
        except AIConfigurationError:
            return False

    @staticmethod
    def _system_prompt() -> str:
        schema = json.dumps(
            FailureHealContract.model_json_schema(), ensure_ascii=False, separators=(",", ":")
        )
        return (
            "你是自动化测试失败修复编译器（healer），不是远程点击机器人。"
            "只在失败后提出结构化补丁，禁止输出逐步点击剧本。"
            "必须保持失败分类：locator 与 data_strategy 不得混淆。"
            "可提案：target_candidates（改步骤候选）、object_rebind（改对象库 target）、"
            "data_strategy（literal→env/lookup/ensure）。"
            "不确定时 error_class=uncertain，patches 可空，requires_human_confirm 必须为 true。"
            "confidence<0.6 的补丁视为需人工确认。只返回符合 JSON Schema 的对象："
            f"{schema}"
        )

    @staticmethod
    def _prompt(context: dict[str, Any]) -> str:
        return json.dumps({"failure_context": context}, ensure_ascii=False, separators=(",", ":"))

