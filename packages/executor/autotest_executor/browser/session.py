"""浏览器会话。

开窗与无头共用同一份步骤和同一套断言，只切 headless——如果无头是
「只发接口、假装点过」，CI 的结论就不可信了。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from autotest_protocol import Job

_PROBE_JS = (Path(__file__).resolve().parent / "probe.js").read_text(encoding="utf-8")
# 指纹解析在页面内算分。回放时步骤里带着指纹，缺了这份脚本就只剩
# 「候选全失效 → 找不到」，自愈形同虚设，所以在上下文层面无条件注入。
_LOCATOR_JS = (Path(__file__).resolve().parent / "locator_candidates.js").read_text(
    encoding="utf-8"
)


class HeadedNotSupported(RuntimeError):
    """请求开窗但当前环境没有桌面会话。

    这里明确失败，不静默降级为无头：使用者要的是「看得见」，
    悄悄改成看不见等于骗人。
    """


def _has_desktop_session() -> bool:
    if sys.platform.startswith("win") or sys.platform == "darwin":
        return True
    # Linux 容器里通常既无 DISPLAY 也无 WAYLAND_DISPLAY
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


class BrowserSession:
    def __init__(self, job: Job, artifacts_dir: Path) -> None:
        self.job = job
        self.artifacts_dir = artifacts_dir
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._trace_started = False

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("会话尚未启动")
        return self._page

    @property
    def context(self) -> BrowserContext:
        if self._context is None:
            raise RuntimeError("会话尚未启动")
        return self._context

    @property
    def playwright(self):
        if self._playwright is None:
            raise RuntimeError("会话尚未启动")
        return self._playwright

    def start(self, cookies: list[dict[str, Any]] | None = None, extra_headers: dict[str, str] | None = None) -> None:
        options = self.job.options
        if not options.headless and not _has_desktop_session():
            raise HeadedNotSupported("该执行器不支持开窗：当前环境没有桌面会话")

        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()
        if options.headless:
            launch_args: list[str] = []
        else:
            try:
                from autotest_executor.browser.window_dock import compute_record_layout

                # 开窗一律按「带右侧录制面板」的尺寸起窗：登录阶段就是最终尺寸，
                # 等面板打开时窗口不再跳动（141 的登录页在全屏宽下渲染不同，会登录失败）。
                layout = compute_record_layout()
                launch_args = [
                    f"--window-position={layout['left']},{layout['top']}",
                    f"--window-size={layout['main_width']},{layout['height']}",
                ]
            except Exception:
                launch_args = ["--window-position=0,0", "--window-size=1920,1040"]
        self._browser = self._playwright.chromium.launch(
            headless=options.headless,
            args=launch_args,
        )

        context_kwargs: dict[str, Any] = {}
        # 开窗：禁用固定 viewport，页面随 Chromium 窗口实际大小渲染
        if not options.headless:
            context_kwargs["no_viewport"] = True
        else:
            context_kwargs["viewport"] = {
                "width": options.viewport_width,
                "height": options.viewport_height,
            }
        if options.video != "off":
            context_kwargs["record_video_dir"] = str(self.artifacts_dir / "video")
        self._context = self._browser.new_context(**context_kwargs)

        # 定位脚本同样按上下文注入：指纹解析要用，回放整页刷新也不能丢。
        self._context.add_init_script(script=_LOCATOR_JS)

        if extra_headers:
            self._context.set_extra_http_headers(extra_headers)
        if cookies:
            self._context.add_cookies(cookies)  # type: ignore[arg-type]

        # 探针注入在上下文层面：对该上下文的所有页面与后续导航自动生效，
        # 整页刷新也不失效——比「进入应用后注入一次」可靠。
        if self.job.site.probe.enabled:
            config = {"errorUrlPatterns": self.job.site.probe.error_url_patterns}
            self._context.add_init_script(
                script=f"window.__atpProbeConfig = {config!r};".replace("'", '"') + "\n" + _PROBE_JS
            )

        if options.trace != "off":
            self._context.tracing.start(screenshots=True, snapshots=True, sources=False)
            self._trace_started = True

        self._page = self._context.new_page()
        if not options.headless:
            # 后台启动的 python 有时把窗口开在屏幕外，用 CDP 贴齐可用工作区
            try:
                from autotest_executor.browser.window_dock import apply_main_only_layout

                apply_main_only_layout(self._page)
            except Exception:
                pass
            try:
                self._page.bring_to_front()
            except Exception:
                pass

    def read_probe(self) -> dict[str, Any]:
        if not self.job.site.probe.enabled:
            return {"consoleErrors": [], "jsErrors": [], "requestErrors": [], "uiErrors": [], "enabled": False}
        try:
            data = self.page.evaluate("() => window.__atpProbe ? window.__atpProbe.read() : null")
        except Exception:
            data = None
        if not data:
            return {
                "consoleErrors": [],
                "jsErrors": [],
                "requestErrors": [],
                "uiErrors": [],
                "installed": False,
            }
        data["installed"] = True
        data.setdefault("uiErrors", [])
        return data

    def consume_ui_errors(self) -> list[dict[str, Any]]:
        if not self.job.site.probe.enabled:
            return []
        try:
            items = self.page.evaluate(
                "() => window.__atpProbe && window.__atpProbe.consumeUiErrors"
                " ? window.__atpProbe.consumeUiErrors() : []"
            )
        except Exception:
            return []
        return list(items or [])

    def stop(self, keep_trace: bool) -> dict[str, str]:
        """关闭会话并返回产物本地路径。"""
        produced: dict[str, str] = {}
        try:
            if self._context is not None:
                if self._trace_started:
                    trace_path = self.artifacts_dir / "trace.zip"
                    if keep_trace:
                        self._context.tracing.stop(path=str(trace_path))
                        produced["trace"] = str(trace_path)
                    else:
                        self._context.tracing.stop()
                video_path: str | None = None
                if self._page is not None and self._page.video is not None and keep_trace:
                    try:
                        video_path = self._page.video.path()
                    except Exception:
                        video_path = None
                self._context.close()
                if video_path:
                    produced["video"] = video_path
        finally:
            if self._browser is not None:
                self._browser.close()
            if self._playwright is not None:
                self._playwright.stop()
        return produced
