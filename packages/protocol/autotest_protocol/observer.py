"""P1.2 观察者：页面认识与观察快照。

观察快照是字段库存（不是 HTML）；页面模型描述控件怎么用、取值用任选还是参数化。
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from autotest_protocol.dsl import CandidateKind, ChooseMode

LayerKind = Literal["page", "modal", "drawer", "dropdown"]

SnapshotTrigger = Literal[
    "navigation",
    "layer_open",
    "layer_close",
    "form_visible",
    "manual",
    "record_end",
]

WidgetKind = Literal[
    "text",
    "textarea",
    "number",
    "password",
    "searchable_dropdown",
    "dropdown",
    "radio",
    "checkbox",
    "switch",
    "date",
    "upload",
    "button",
    "link",
    "table",
    "tab",
    "panel",
    "unknown",
]

OperationMethod = Literal[
    "click",
    "fill",
    "choose",
    "select",
    "upload",
    "toggle",
    "open_panel",
]

ValueStrategy = Literal[
    # 任选合法项（下拉、尺码、Tab 等）
    "choose_any",
    # 需唯一或按意图参数化（编码、单号等）
    "parameterized",
    # 意图明确要求固定主数据时才用
    "literal",
    # 非必填且面板空时可跳过
    "skip_if_empty",
]

# 动态列表项 / 样例选项文案，不得登记为永久组件身份
_TRANSIENT_OPTION = re.compile(r"^\d{1,4}$|^[A-Z0-9_-]{1,12}$", re.I)
_CODE_LABEL = re.compile(r"编码|code|sku|单号|编号|款式号", re.I)

# 与 executor 侧观察封顶一致
MAX_SNAPSHOT_FIELDS = 80
MAX_SAMPLE_OPTIONS = 20
MAX_PAGE_MODEL_ENTRIES = 200


class LayerRef(BaseModel):
    kind: LayerKind = "page"
    name: str | None = None
    path: str | None = None


class LocatorSummary(BaseModel):
    kind: CandidateKind
    value: str
    name: str | None = None


class ObservedField(BaseModel):
    label: str
    widget_kind: WidgetKind = "unknown"
    required: bool = False
    locator: LocatorSummary | None = None
    operation: OperationMethod | None = None
    value_strategy: ValueStrategy | None = None
    # 快照里看到的选项样例，不是组件身份
    sample_options: list[str] = Field(default_factory=list, max_length=MAX_SAMPLE_OPTIONS)

    @field_validator("sample_options")
    @classmethod
    def trim_options(cls, value: list[str]) -> list[str]:
        out: list[str] = []
        for item in value:
            text = str(item).strip()
            if text and text not in out:
                out.append(text[:80])
            if len(out) >= MAX_SAMPLE_OPTIONS:
                break
        return out


class ObservationSnapshot(BaseModel):
    trigger: SnapshotTrigger
    url: str
    title: str | None = None
    layer: LayerRef = Field(default_factory=LayerRef)
    fields: list[ObservedField] = Field(default_factory=list, max_length=MAX_SNAPSHOT_FIELDS)
    open_panel_kind: str | None = None
    seq: int | None = None
    captured_at: datetime | None = None


class PageWidgetEntry(BaseModel):
    """随流程保存的页面认识条目。"""

    id: str
    layer: LayerRef
    display_name: str
    widget_kind: WidgetKind
    operation: OperationMethod
    value_strategy: ValueStrategy
    locator: LocatorSummary | None = None
    choose_mode: ChooseMode | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def reject_transient_identity(self) -> PageWidgetEntry:
        if is_transient_component_identity(self.display_name):
            raise ValueError(
                f"display_name {self.display_name!r} 是动态选项文案，不能登记为组件身份"
            )
        return self


class PageWidgetModel(BaseModel):
    site_id: str | None = None
    flow_id: str | None = None
    recording_run_id: str | None = None
    entries: list[PageWidgetEntry] = Field(default_factory=list, max_length=MAX_PAGE_MODEL_ENTRIES)
    snapshots_seen: int = 0


class RecordingSummary(BaseModel):
    """录制完成 summary：样例轨迹与观察者脚本分栏。"""

    sample_steps: list[dict[str, Any]] = Field(default_factory=list)
    observer_steps: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    error: str | None = None
    start_url: str | None = None
    site_id: str | None = None
    credential_id: str | None = None
    screenshot: str | None = None
    compiler_context: dict[str, Any] | None = None
    page_widget_model: PageWidgetModel | None = None
    raw_event_count: int | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_steps(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        legacy = out.get("steps")
        if legacy and not out.get("sample_steps"):
            out["sample_steps"] = legacy
        return out

    def to_summary_dict(self) -> dict[str, Any]:
        """写入 Run.summary；保留 steps 别名供旧路径读取。"""
        payload = self.model_dump(mode="json", exclude_none=True)
        if self.sample_steps:
            payload["steps"] = self.sample_steps
        return payload

    @classmethod
    def from_summary_dict(cls, data: dict[str, Any] | None) -> RecordingSummary:
        return cls.model_validate(data or {})


def is_transient_component_identity(text: str) -> bool:
    """样例轨迹里的具体选项（如尺码 155）不是永久组件身份。"""
    raw = (text or "").strip()
    if not raw:
        return True
    if _TRANSIENT_OPTION.match(raw):
        return True
    if len(raw) <= 3 and raw.isdigit():
        return True
    return False


def infer_value_strategy(*, label: str, widget_kind: WidgetKind) -> ValueStrategy:
    """根据字段标签与控件种类推断取值策略。"""
    if widget_kind in {"searchable_dropdown", "dropdown", "radio", "tab", "panel"}:
        return "choose_any"
    if widget_kind in {"password"}:
        return "parameterized"
    if _CODE_LABEL.search(label or ""):
        return "parameterized"
    if widget_kind in {"text", "textarea", "number"}:
        return "parameterized"
    return "choose_any"


def infer_operation(widget_kind: WidgetKind) -> OperationMethod:
    if widget_kind in {"searchable_dropdown", "dropdown", "radio", "tab", "panel"}:
        return "choose"
    if widget_kind in {"checkbox", "switch"}:
        return "toggle"
    if widget_kind == "upload":
        return "upload"
    if widget_kind in {"text", "textarea", "number", "password"}:
        return "fill"
    if widget_kind in {"button", "link"}:
        return "click"
    return "click"


def default_choose_mode(widget_kind: WidgetKind) -> ChooseMode | None:
    if widget_kind == "searchable_dropdown":
        return "search_or_first"
    if widget_kind in {"dropdown", "radio", "tab", "panel"}:
        return "other"
    return None


def observation_snapshot_from_event_data(data: dict[str, Any]) -> ObservationSnapshot:
    return ObservationSnapshot.model_validate(data)


def merge_snapshot_into_model(
    model: PageWidgetModel,
    snapshot: ObservationSnapshot,
    *,
    site_id: str | None = None,
    recording_run_id: str | None = None,
) -> PageWidgetModel:
    """把一次观察快照合并进页面模型（确定性、不含动态选项身份）。"""
    entries = list(model.entries)
    index = {entry.display_name: entry for entry in entries}
    for field in snapshot.fields:
        label = (field.label or "").strip()
        if not label or is_transient_component_identity(label):
            continue
        strategy = field.value_strategy or infer_value_strategy(
            label=label, widget_kind=field.widget_kind
        )
        operation = field.operation or infer_operation(field.widget_kind)
        choose_mode = default_choose_mode(field.widget_kind)
        entry_id = label
        index[label] = PageWidgetEntry(
            id=entry_id,
            layer=snapshot.layer,
            display_name=label,
            widget_kind=field.widget_kind,
            operation=operation,
            value_strategy=strategy,
            locator=field.locator,
            choose_mode=choose_mode,
        )
    return PageWidgetModel(
        site_id=site_id or model.site_id,
        flow_id=model.flow_id,
        recording_run_id=recording_run_id or model.recording_run_id,
        entries=list(index.values())[:MAX_PAGE_MODEL_ENTRIES],
        snapshots_seen=model.snapshots_seen + 1,
    )
