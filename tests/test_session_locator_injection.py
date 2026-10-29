"""回放页面必须自带指纹脚本。

指纹解析在页面内算分。如果只有录制/踩点注入了 locator_candidates.js，
回放时 window.__atpFindByFingerprint 不存在，指纹退路会静默失效——
表现就是「录得好好的流程，换个环境就找不到元素」。
"""

from __future__ import annotations

from pathlib import Path

from autotest_executor.browser.session import BrowserSession
from autotest_protocol import Job

HTML = "<div class='form-container'><input class='ant-input' value=''></div>"


def _job() -> Job:
    return Job.model_validate(
        {
            "run_id": "injection-check",
            "site": {"id": "local", "base_url": "about:blank", "probe": {"enabled": False}},
            "options": {"headless": True, "screenshot_each_step": False, "trace": "off", "video": "off"},
        }
    )


def test_fingerprint_scripts_available_after_navigation(tmp_path: Path) -> None:
    page_file = tmp_path / "page.html"
    page_file.write_text(HTML, encoding="utf-8")

    session = BrowserSession(_job(), tmp_path / "artifacts")
    session.start()
    try:
        page = session.page
        # 导航到新文档：init script 必须跟着生效，而不是只在首个空白页里有。
        page.goto(page_file.as_uri())

        assert page.evaluate("() => typeof window.__atpFindByFingerprint") == "function"
        assert page.evaluate("() => typeof window.__atpFingerprint") == "function"

        fp = page.evaluate(
            "() => window.__atpFingerprint(document.querySelector('.ant-input'))"
        )
        assert fp is not None and fp.get("tag") == "input"
    finally:
        session.stop(keep_trace=False)
