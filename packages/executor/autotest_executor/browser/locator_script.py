"""定位脚本装配：选择器前言 + locator_candidates.js。

录制 / 回放 / 踩点 / 自测都必须经此入口注入，避免 JS 里再抄一份选择器。
"""

from __future__ import annotations

from pathlib import Path

from autotest_executor.ui_selectors import js_preamble

_BROWSER_DIR = Path(__file__).resolve().parent
_CANDIDATES_JS = (_BROWSER_DIR / "locator_candidates.js").read_text(encoding="utf-8")


def locator_init_script() -> str:
    """给 add_init_script / page.evaluate 用的完整定位脚本。"""
    return js_preamble() + _CANDIDATES_JS
