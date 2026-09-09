"""页面就绪判定。

`networkidle` 对单页应用不可靠：请求早就停了，框架还没把界面渲染出来。
实测某 Vue + Apollo 应用在 networkidle 之后 2 秒才出现登录表单——
在那之前找元素必然扑空，而且是间歇性的，比稳定失败更难查。

这里用「页面上出现了可交互元素」作为就绪信号。对静态页面它立刻返回，
不会拖慢；对单页应用它把那段空窗期等掉。
"""

from __future__ import annotations

from playwright.sync_api import Page

_JS_HAS_INTERACTIVE = """
() => document.querySelectorAll(
  'input, textarea, select, button, a[href], [role=button]'
).length > 0
"""


def wait_for_app_ready(page: Page, timeout_ms: int = 15_000) -> bool:
    """等到页面出现可交互元素。

    返回是否等到。等不到不代表出错——有些页面确实只有文本——
    所以由调用方决定要不要当成失败。
    """
    try:
        page.wait_for_function(_JS_HAS_INTERACTIVE, timeout=timeout_ms)
        return True
    except Exception:
        return False
