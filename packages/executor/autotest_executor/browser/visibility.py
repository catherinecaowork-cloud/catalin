"""浮层可见性语义。

从 locator 巨石里抽出「取第一个可见匹配」与「等可见下拉面板」——
这两块是浮层 flaky 的核心判据，继续堆在 locator.py 只会让评审成本上升。

与 `_try_root`（取**最后一个**可见面板）刻意不同向：面板要最新打开的，
候选匹配要第一个活着的。
"""

from __future__ import annotations

import time

from playwright.sync_api import Locator, Page

from autotest_executor.ui_selectors import DROPDOWN_PANEL

# Ant Design / rc-virtual-list 隐藏副本通常个位数；有界避免病态 DOM 拖成秒级。
_VISIBILITY_PROBE_LIMIT = 20
# Playwright 1.49.1 没有 locator.filter(visible=True)（需 ≥1.51），
# 且给候选 CSS 拼 `:visible` 会破坏 role/text 等非 CSS 候选，所以自己轮询。
_VISIBILITY_POLL_MS = 100


def first_visible(locator: Locator) -> Locator | None:
    """按 DOM 顺序返回第一个可见匹配；全不可见或探测超限时返回 None。

    Ant Design / rc-virtual-list 会在同一层里留一份隐藏副本（量高用）并排在 DOM 前面。
    取 `.first` 会命中它，从而把整个候选误判为不可见——可见的那个从未被检查。
    """
    try:
        total = locator.count()
    except Exception:
        return None
    for index in range(min(total, _VISIBILITY_PROBE_LIMIT)):
        node = locator.nth(index)
        try:
            if node.is_visible():
                return node
        except Exception:
            continue
    return None


def wait_first_visible(locator: Locator, timeout_ms: int) -> Locator | None:
    """轮询到超时，返回第一个可见匹配。

    替代 `locator.first.wait_for(state="visible")`——后者只认第一个匹配，
    正是隐藏副本场景下失效的那条路。
    """
    deadline = time.monotonic() + max(0, timeout_ms) / 1000
    while True:
        found = first_visible(locator)
        if found is not None:
            return found
        if time.monotonic() >= deadline:
            return None
        try:
            locator.page.wait_for_timeout(_VISIBILITY_POLL_MS)
        except Exception:
            return None


def visible_dropdown_panel(page: Page) -> Locator | None:
    """当前可见的下拉面板。已打开就不要再点触发器，Ant 下拉会点一下关一下。"""
    dropdown = page.locator(DROPDOWN_PANEL)
    try:
        if dropdown.count() == 0:
            return None
        return dropdown.last
    except Exception:
        return None


def wait_visible_dropdown_panel(page: Page, timeout_ms: int) -> Locator | None:
    """轮询到出现可见下拉面板为止，超时返回 None。"""
    deadline = time.monotonic() + max(0, timeout_ms) / 1000
    while True:
        panel = visible_dropdown_panel(page)
        if panel is not None:
            return panel
        if time.monotonic() >= deadline:
            return None
        try:
            page.wait_for_timeout(_VISIBILITY_POLL_MS)
        except Exception:
            return None


def wait_any_dropdown_panel(page: Page, timeout_ms: int) -> bool | None:
    """轮询到出现可见下拉面板；单一来源后与 wait_visible_dropdown_panel 同口径。

    保留函数名：actions 的生效确认仍调用它。返回 True / None（超时），
    与历史 selftest 断言兼容。
    """
    panel = wait_visible_dropdown_panel(page, timeout_ms)
    return True if panel is not None else None
