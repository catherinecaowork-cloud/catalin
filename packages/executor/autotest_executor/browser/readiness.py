"""页面就绪判定。

`networkidle` 对单页应用不可靠：请求早就停了，框架还没把界面渲染出来。
实测某 Vue + Apollo 应用在 networkidle 之后 2 秒才出现登录表单——
在那之前找元素必然扑空，而且是间歇性的，比稳定失败更难查。

这里用「页面上出现了可交互元素」作为就绪信号。对静态页面它立刻返回，
不会拖慢；对单页应用它把那段空窗期等掉。
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from playwright.sync_api import Page

_JS_HAS_INTERACTIVE = """
() => document.querySelectorAll(
  'input, textarea, select, button, a[href], [role=button]'
).length > 0
"""

# 只认盖住内容的转圈：角落里 20px 的装饰 spinner 不能空等 8 秒。
_JS_COVERING_SPINNER = """
() => {
  const nodes = document.querySelectorAll(
    '.ant-spin-spinning, .el-loading-mask, .oio-spin'
  );
  for (const el of nodes) {
    const st = getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden' || Number(st.opacity) === 0) {
      continue;
    }
    const r = el.getBoundingClientRect();
    if (r.width < 8 || r.height < 8) continue;
    if (r.bottom < 0 || r.right < 0 || r.top > innerHeight || r.left > innerWidth) {
      continue;
    }
    const mask = el.classList.contains('el-loading-mask') && r.width >= 80 && r.height >= 80;
    const overlay = st.position === 'fixed' || st.position === 'absolute';
    const covers =
      (r.width >= innerWidth * 0.35 && r.height >= innerHeight * 0.25)
      || (overlay && r.width >= 80 && r.height >= 80);
    if (mask || covers) return true;
  }
  return false;
}
"""

_JS_NO_COVERING_SPINNER = f"() => !(({_JS_COVERING_SPINNER})())"


def same_navigation_url(current: str, target: str) -> bool:
    """登录后常已经落到起始页，再 goto 会整页重载，空耗数秒。"""
    return _norm_navigation_url(current) == _norm_navigation_url(target)


def _norm_navigation_url(url: str) -> str:
    parts = urlsplit((url or "").strip())
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, parts.fragment))


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


def wait_for_route_idle(
    page: Page,
    timeout_ms: int = 3_000,
    appear_ms: int = 180,
) -> bool:
    """等路由切换的遮罩转圈消失。

    没有盖住内容的 spinner 就立刻返回，不要对装饰性转圈空等。
    返回是否在超时前确认空闲。
    """
    try:
        busy = bool(page.evaluate(_JS_COVERING_SPINNER))
    except Exception:
        busy = False
    if not busy and appear_ms > 0:
        try:
            page.wait_for_function(_JS_COVERING_SPINNER, timeout=appear_ms)
            busy = True
        except Exception:
            return True
    if not busy:
        return True
    try:
        page.wait_for_function(_JS_NO_COVERING_SPINNER, timeout=max(0, timeout_ms))
        return True
    except Exception:
        return False
