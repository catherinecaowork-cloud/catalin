"""运行事件。

成败结论由执行器在事件里直接给出，平台不从日志文本里用正则猜——
那条路会随每个新接入的站点而破。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

EventType = Literal[
    "run.start",
    "step.start",
    "step.end",
    "request",
    "probe.alert",
    "assert",
    "artifact",
    "log",
    "record.progress",
    "observe.snapshot",
    "run.end",
]


class Event(BaseModel):
    type: EventType
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # 由控制面接收时赋值，用于断线重连后补齐
    seq: int | None = None
    data: dict[str, Any] = {}


def new_event(type_: EventType, **data: Any) -> Event:
    return Event(type=type_, data=data)


def new_observe_snapshot_event(**data: Any) -> Event:
    """Worker 上报脱敏页面观察快照（字段库存，不是 HTML）。"""
    return new_event("observe.snapshot", **data)
