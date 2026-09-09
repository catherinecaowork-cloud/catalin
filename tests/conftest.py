"""pytest 配置与共享 fixture。"""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "browser: 需要本机已安装 Playwright Chromium")


def require_browser() -> None:
    """Chromium 未安装时跳过浏览器自测。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        pytest.skip(f"playwright 未安装: {exc}")
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            browser.close()
    except Exception as exc:
        pytest.skip(f"playwright chromium 不可用（可先运行 playwright install chromium）: {exc}")
