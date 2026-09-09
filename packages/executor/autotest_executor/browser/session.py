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

    def start(self, cookies: list[dict[str, Any]] | None = None, extra_headers: dict[str, str] | None = None) -> None:
        options = self.job.options
        if not options.headless and not _has_desktop_session():
            raise HeadedNotSupported("该执行器不支持开窗：当前环境没有桌面会话")

        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=options.headless,
            args=[] if options.headless else ["--window-position=80,80", "--window-size=1440,900"],
        )

        context_kwargs: dict[str, Any] = {
            "viewport": {"width": options.viewport_width, "height": options.viewport_height},
        }
        if options.video != "off":
            context_kwargs["record_video_dir"] = str(self.artifacts_dir / "video")
        self._context = self._browser.new_context(**context_kwargs)

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
            # 后台启动的 python 有时把窗口开在屏幕外，尽量拉到前台
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
