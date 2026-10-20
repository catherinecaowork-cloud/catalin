"""浮层内可见性收敛：同一层里隐藏副本在前时，不能把整个候选判死。

Ant Design / rc-virtual-list 会在下拉里留一份隐藏副本（量高用）并排在 DOM 前面。
改动前 `_immediately_visible` 只看 `.first`，命中隐藏副本就跳过整个候选，
可见的那个从未被检查，最终报 TargetNotFound。
"""

from __future__ import annotations

import pytest
from playwright.sync_api import sync_playwright

from autotest_executor.browser.locator import (
    _VISIBILITY_PROBE_LIMIT,
    TargetNotFound,
    resolve_target,
)
from autotest_protocol import Candidate, Target, TargetScope
from tests.conftest import require_browser

OPTION = ".ant-select-item-option"
TARGET = Target(candidates=[Candidate(kind="css", value=OPTION)], scope=TargetScope(kind="dropdown"))


def _page_html(options: list[tuple[str, bool]]) -> str:
    """options: [(文本, 是否可见)]，按给定顺序写入 DOM。"""
    rows = "".join(
        f'<div class="ant-select-item-option{" hidden-copy" if not visible else ""}">{text}</div>'
        for text, visible in options
    )
    return f"""<!doctype html><meta charset="utf-8">
<style>
  .ant-select-dropdown {{ position: absolute; top: 40px; left: 20px; width: 200px;
                          border: 1px solid #d9d9d9; background: #fff; }}
  .ant-select-item-option {{ padding: 6px 12px; }}
  .hidden-copy {{ display: none; }}
</style>
<div class="ant-select-dropdown"><div class="rc-virtual-list">{rows}</div></div>
"""


def _resolve_text(html: str, timeout_ms: int = 400) -> str:
    """返回解析到的元素文本。locator 不能带出 with 块（浏览器已关闭），故在此取值。"""
    require_browser()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(html)
            resolution = resolve_target(page, TARGET, timeout_ms=timeout_ms)
            assert resolution.locator.is_visible()
            return resolution.locator.inner_text()
        finally:
            browser.close()


def test_hidden_copy_before_visible_one_still_resolves() -> None:
    """隐藏副本在前、可见元素在后——正是 Ant Design 下拉的形态。"""
    assert _resolve_text(_page_html([("品牌A", False), ("品牌A", True)])) == "品牌A"


def test_returns_first_visible_when_several_visible() -> None:
    """多个可见匹配时取 DOM 顺序上第一个（与 _try_root 的「取最后一个」刻意不同向）。"""
    assert _resolve_text(_page_html([("甲", True), ("乙", True)])) == "甲"


def test_all_matches_hidden_raises_target_not_found() -> None:
    """全部不可见时仍然要报失败，不能因为放宽了探测就假装命中。"""
    with pytest.raises(TargetNotFound):
        _resolve_text(_page_html([("品牌A", False), ("品牌B", False)]))


def test_probe_is_bounded() -> None:
    """可见匹配排在上限之外时放弃探测——有界是刻意的，改上限要让这条测试先失败。"""
    options = [("副本", False)] * _VISIBILITY_PROBE_LIMIT + [("品牌A", True)]
    with pytest.raises(TargetNotFound):
        _resolve_text(_page_html(options))
