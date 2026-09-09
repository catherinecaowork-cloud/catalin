"""AI 观察者编写契约。"""

from __future__ import annotations

from pydantic import Field

from autotest_protocol import PageWidgetEntry, Step

from .schemas import StrictModel, TokenUsage


class ObserverContract(StrictModel):
    """观察者一次编写产物：完整 DSL + 页面模型条目。"""

    steps: list[Step] = Field(min_length=1)
    page_widget_entries: list[PageWidgetEntry] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ObserverResult(StrictModel):
    steps: list[Step]
    page_widget_entries: list[PageWidgetEntry]
    notes: list[str]
    usage: TokenUsage
    attempts: int = Field(ge=1)
