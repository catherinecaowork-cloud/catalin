"""步骤取值的数据策略（阶段 B）。

与观察者侧 ValueStrategy（choose_any / parameterized 等「怎么填」）不同：
这里描述「运行时这个值从哪来」。失败必须报 data_strategy，不能混进定位失败。

lookup / ensure 的 query 约定（MVP）：

- source=page：用 CSS selector（及可选 text_contains）在当前页或本地 HTML 上查
- source=api：HTTP GET + json_path / match + return_field
- source=store：进程内实体表（契约测试与 ensure 创建演示）
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

DataStrategyKind = Literal["literal", "env", "from_step", "lookup", "ensure"]

DATA_STRATEGY_KINDS: tuple[str, ...] = (
    "literal",
    "env",
    "from_step",
    "lookup",
    "ensure",
)

# ensure 内置创建：把 query.create（或 query.match）写入 store，无需远程拉流程
STORE_UPSERT_FLOW_ID = "__store_upsert__"


class DataStrategy(BaseModel):
    """步骤 value / expected 的解析策略。

    - literal：字面量（兼容旧流程只写 value 字符串）
    - env：从 Environment.data / Job.variables 取值
    - from_step：取前序步骤产出（如 readTable 抽出的字段）
    - lookup：按 query 在页面 / API / store 查已有数据
    - ensure：先 lookup；未命中则跑 create_flow_id / create_steps，再 lookup
    """

    kind: DataStrategyKind
    # literal
    value: str | None = None
    # env
    key: str | None = None
    # from_step
    step_id: str | None = None
    field: str | None = None
    # lookup / ensure
    query: dict[str, Any] = Field(default_factory=dict)
    # ensure：创建子流程引用；可与 create_steps 二选一（或同时，steps 优先执行）
    create_flow_id: str | None = None
    # ensure：内联创建步骤（最小可跑通路径，避免本 PR 依赖控制面拉 Flow）
    create_steps: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_fields(self) -> DataStrategy:
        if self.kind == "literal" and self.value is None:
            raise ValueError("literal 策略需要 value")
        if self.kind == "env" and not (self.key or "").strip():
            raise ValueError("env 策略需要 key")
        if self.kind == "from_step" and not (self.step_id or "").strip():
            raise ValueError("from_step 策略需要 step_id")
        if self.kind in {"lookup", "ensure"} and not self.query:
            raise ValueError(f"{self.kind} 策略需要 query")
        if self.kind == "ensure":
            has_flow = bool((self.create_flow_id or "").strip())
            has_steps = bool(self.create_steps)
            if not has_flow and not has_steps:
                raise ValueError("ensure 策略需要 create_flow_id 或 create_steps")
        return self


class EnvironmentRef(BaseModel):
    """下发给 Worker 的环境快照。Job 自包含，Worker 不连库。"""

    id: str
    name: str
    base_url: str
    # 数据档：供 DataStrategy kind=env 与 {{env:key}} 共用
    data: dict[str, str] = Field(default_factory=dict)
    labels: list[str] = Field(default_factory=list)
    credential_id: str | None = None
