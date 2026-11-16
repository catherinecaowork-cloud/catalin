"""运行时数据策略解析。

失败一律归为 data_strategy，不得冒充 locator / TargetNotFound。
lookup / ensure 在 MVP 只占位并给出可读错误。
"""

from __future__ import annotations

from typing import Any, Mapping

from autotest_executor.variables import VariableResolutionError, VariableResolver
from autotest_protocol import DataStrategy, Step


class DataStrategyError(Exception):
    """数据策略失败（缺 key、前序无产出、lookup/ensure 未实现等）。"""

    def __init__(
        self,
        message: str,
        *,
        kind: str,
        strategy: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.kind = kind  # missing_env | missing_step | not_implemented | invalid
        self.strategy = strategy
        self.detail = detail or {}

    def as_failure_data(self) -> dict[str, Any]:
        return {
            "failure": "data_strategy",
            "failure_kind": self.kind,
            "strategy": self.strategy,
            "environmental": True,
            **self.detail,
        }


class DataStrategyResolver:
    """持有一次 run 的 env 变量与前序步骤产出。"""

    def __init__(self, variables: Mapping[str, str] | None = None) -> None:
        self._variables = dict(variables or {})
        self._step_outputs: dict[str, dict[str, Any]] = {}
        self._templates = VariableResolver(self._variables)

    @property
    def variables(self) -> dict[str, str]:
        return dict(self._variables)

    def record_step_output(self, step_id: str, data: Mapping[str, Any] | None) -> None:
        payload = dict(data or {})
        self._step_outputs[step_id] = payload
        # 约定：步骤也可通过 data["exports"] 显式导出键值，供 from_step 使用
        exports = payload.get("exports")
        if isinstance(exports, dict):
            for key, value in exports.items():
                if value is None:
                    continue
                self._variables[str(key)] = str(value)
                self._templates = VariableResolver(self._variables)

    def resolve_strategy(self, strategy: DataStrategy) -> str:
        kind = strategy.kind
        if kind == "literal":
            return strategy.value if strategy.value is not None else ""
        if kind == "env":
            key = (strategy.key or "").strip()
            if key not in self._variables:
                raise DataStrategyError(
                    f"环境数据档缺少键：{key}",
                    kind="missing_env",
                    strategy="env",
                    detail={"key": key},
                )
            return self._variables[key]
        if kind == "from_step":
            step_id = (strategy.step_id or "").strip()
            if step_id not in self._step_outputs:
                raise DataStrategyError(
                    f"前序步骤尚无产出：{step_id}",
                    kind="missing_step",
                    strategy="from_step",
                    detail={"step_id": step_id, "field": strategy.field},
                )
            output = self._step_outputs[step_id]
            field = (strategy.field or "").strip()
            if not field:
                # 无 field：优先 text / value / 第一个非空标量
                for candidate in ("text", "value", "result"):
                    if candidate in output and output[candidate] is not None:
                        return str(output[candidate])
                exports = output.get("exports")
                if isinstance(exports, dict) and exports:
                    first = next(iter(exports.values()))
                    return str(first)
                raise DataStrategyError(
                    f"步骤 {step_id} 没有可用的默认产出字段",
                    kind="missing_step",
                    strategy="from_step",
                    detail={"step_id": step_id},
                )
            if field in output and output[field] is not None:
                return str(output[field])
            exports = output.get("exports")
            if isinstance(exports, dict) and field in exports and exports[field] is not None:
                return str(exports[field])
            raise DataStrategyError(
                f"步骤 {step_id} 产出中没有字段：{field}",
                kind="missing_step",
                strategy="from_step",
                detail={"step_id": step_id, "field": field},
            )
        if kind == "lookup":
            raise DataStrategyError(
                "lookup 策略尚未实现：需要页面/接口查询已有数据",
                kind="not_implemented",
                strategy="lookup",
                detail={"query": dict(strategy.query or {})},
            )
        if kind == "ensure":
            raise DataStrategyError(
                "ensure 策略尚未实现：查不到时需跑创建子流程",
                kind="not_implemented",
                strategy="ensure",
                detail={
                    "query": dict(strategy.query or {}),
                    "create_flow_id": strategy.create_flow_id,
                },
            )
        raise DataStrategyError(
            f"未知数据策略：{kind}",
            kind="invalid",
            strategy=str(kind),
        )

    def resolve_step_fields(self, step: Step) -> Step:
        """深拷贝并解析 value / expected（策略优先，其次 {{}} 模板）。"""
        copied = step.model_copy(deep=True)
        try:
            if copied.value_strategy is not None:
                copied.value = self.resolve_strategy(copied.value_strategy)
            else:
                copied.value = self._templates.resolve(copied.value)
            if copied.expected_strategy is not None:
                copied.expected = self.resolve_strategy(copied.expected_strategy)
            else:
                copied.expected = self._templates.resolve(copied.expected)
        except VariableResolutionError as exc:
            raise DataStrategyError(
                str(exc),
                kind="missing_env" if "缺少环境变量" in str(exc) else "invalid",
                strategy="template",
            ) from exc
        return copied
