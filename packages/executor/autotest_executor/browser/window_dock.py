"""将 Web 录制面板停靠在被测 Chromium 窗口右侧（Katalon 风格）。"""

from __future__ import annotations

import shutil
import sys
import tempfile
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext, Page, Playwright

PANEL_WIDTH = 460
FALLBACK_WIDTH = 1920
FALLBACK_HEIGHT = 1040


def get_work_area() -> dict[str, int]:
    """可用桌面区域（排除任务栏）。Windows 用 SPI_GETWORKAREA。"""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            rect = wintypes.RECT()
            # SPI_GETWORKAREA = 0x0030
            if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
                return {
                    "left": int(rect.left),
                    "top": int(rect.top),
                    "width": int(rect.right - rect.left),
                    "height": int(rect.bottom - rect.top),
                }
        except Exception:
            pass
    return {"left": 0, "top": 0, "width": FALLBACK_WIDTH, "height": FALLBACK_HEIGHT}


def compute_record_layout() -> dict[str, int]:
    """主浏览器 + 右侧面板铺满可用屏幕宽度。"""
    work = get_work_area()
    panel_width = min(PANEL_WIDTH, max(360, work["width"] // 4))
    main_width = max(640, work["width"] - panel_width)
    return {
        "left": work["left"],
        "top": work["top"],
        "height": work["height"],
        "main_width": main_width,
        "panel_width": panel_width,
        "panel_left": work["left"] + main_width,
    }


def build_dock_url(server: str, run_id: str, start_url: str, intent: str = "") -> str:
    base = server.rstrip("/")
    query = (
        f"run_id={quote(run_id)}"
        f"&url={quote(start_url)}"
        f"&intent={quote(intent or '')}"
    )
    return f"{base}/static/recorder-dock.html?{query}"


def _cdp(page: Page) -> Any:
    return page.context.new_cdp_session(page)


def _window_id(page: Page) -> int | None:
    try:
        info = _cdp(page).send("Browser.getWindowForTarget")
        window_id = info.get("windowId")
        return int(window_id) if window_id is not None else None
    except Exception:
        return None


def get_bounds(page: Page) -> dict[str, int] | None:
    try:
        window_id = _window_id(page)
        if window_id is None:
            return None
        payload = _cdp(page).send("Browser.getWindowBounds", {"windowId": window_id})
        bounds = payload.get("bounds") or {}
        return {
            "left": int(bounds.get("left", 0)),
            "top": int(bounds.get("top", 0)),
            "width": int(bounds.get("width", FALLBACK_WIDTH)),
            "height": int(bounds.get("height", FALLBACK_HEIGHT)),
        }
    except Exception:
        return None


def set_bounds(page: Page, left: int, top: int, width: int, height: int) -> None:
    try:
        window_id = _window_id(page)
        if window_id is None:
            return
        _cdp(page).send(
            "Browser.setWindowBounds",
            {
                "windowId": window_id,
                "bounds": {
                    "left": left,
                    "top": top,
                    "width": width,
                    "height": height,
                    "windowState": "normal",
                },
            },
        )
    except Exception:
        return


def apply_main_only_layout(main_page: Page) -> dict[str, int]:
    """右侧面板尚未打开时，主浏览器先按「带面板」的最终尺寸就位。

    不再铺满整个工作区：登录阶段就用带面板的尺寸，等录制面板打开时
    窗口不再跳动（141 的登录页在全屏宽下渲染不同，会登录失败）。"""
    layout = compute_record_layout()
    set_bounds(main_page, layout["left"], layout["top"], layout["main_width"], layout["height"])
    main_page.wait_for_timeout(80)
    return {
        "left": layout["left"],
        "top": layout["top"],
        "height": layout["height"],
        "main_width": layout["main_width"],
        "panel_width": 0,
        "panel_left": layout["left"] + layout["main_width"],
    }


def apply_record_layout(main_page: Page, panel_page: Page | None = None) -> dict[str, int]:
    layout = compute_record_layout()
    set_bounds(
        main_page,
        layout["left"],
        layout["top"],
        layout["main_width"],
        layout["height"],
    )
    if panel_page is not None and not panel_page.is_closed():
        set_bounds(
            panel_page,
            layout["panel_left"],
            layout["top"],
            layout["panel_width"],
            layout["height"],
        )
    main_page.wait_for_timeout(100)
    return layout


@dataclass
class RecorderDock:
    context: BrowserContext
    page: Page
    user_data_dir: str

    def reposition_beside(self, main_page: Page) -> None:
        apply_record_layout(main_page, self.page)
        try:
            main_page.bring_to_front()
        except Exception:
            pass

    def close(self) -> None:
        try:
            self.context.close()
        except Exception:
            pass
        try:
            shutil.rmtree(self.user_data_dir, ignore_errors=True)
        except Exception:
            pass


def hide_inpage_recorder_badge(main_page: Page) -> None:
    try:
        main_page.evaluate(
            """() => {
              window.__atpDockPanelActive = true;
              const badge = document.getElementById('__atp_recorder_badge');
              if (badge) badge.remove();
            }"""
        )
    except Exception:
        pass


def open_recorder_dock(
    playwright: Playwright,
    main_page: Page,
    server: str,
    run_id: str,
    start_url: str,
    intent: str = "",
) -> RecorderDock | None:
    """单独开一个 app 模式 Chromium 窗口作为录制面板，并贴到主浏览器右侧。"""
    dock_url = build_dock_url(server, run_id, start_url, intent)
    layout = apply_record_layout(main_page)
    user_data_dir = tempfile.mkdtemp(prefix="atp-recorder-dock-")
    try:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            args=[
                f"--app={dock_url}",
                f"--window-position={layout['panel_left']},{layout['top']}",
                f"--window-size={layout['panel_width']},{layout['height']}",
                "--disable-session-crashed-bubble",
                "--disable-features=TranslateUI",
            ],
            no_viewport=True,
        )
        page = context.pages[0] if context.pages else context.new_page()
        if "recorder-dock" not in page.url:
            page.goto(dock_url, wait_until="domcontentloaded", timeout=20_000)
        dock = RecorderDock(context=context, page=page, user_data_dir=user_data_dir)
        apply_record_layout(main_page, page)
        hide_inpage_recorder_badge(main_page)
        return dock
    except Exception:
        shutil.rmtree(user_data_dir, ignore_errors=True)
        return None
