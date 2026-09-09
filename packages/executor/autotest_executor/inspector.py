"""踩点任务：打开一个页面，识别登录表单。

单独一种任务类型，因为控制面不装浏览器——「打开页面看看长什么样」
这件事只能由执行器做。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from autotest_executor.browser.readiness import wait_for_app_ready
from autotest_executor.browser.session import BrowserSession
from autotest_executor.client import ControlPlaneClient
from autotest_executor.onboarding import detect_login_form
from autotest_protocol import Job, new_event


class InspectExecutor:
    def __init__(self, client: ControlPlaneClient, job: Job, workspace: Path) -> None:
        self.client = client
        self.job = job
        self.artifacts_dir = workspace / job.run_id
        self.session = BrowserSession(job, self.artifacts_dir)

    def execute(self) -> str:
        started = time.monotonic()
        url = self.job.inspect_url or ""
        self._emit("run.start", run_id=self.job.run_id, kind="inspect", url=url)

        status = "passed"
        summary: dict[str, Any] = {}
        try:
            # 踩点一律无头：这一步没有「要看得见」的诉求，
            # 也就不该占用可开窗的执行器。
            self.session.start()
            summary = self._inspect(url)
            if not summary.get("detection", {}).get("found"):
                status = "failed"
        except Exception as exc:  # noqa: BLE001
            self._emit("log", level="error", message=f"{type(exc).__name__}: {exc}")
            status = "error"
            summary = {"error": f"{type(exc).__name__}: {exc}"}

        try:
            self.session.stop(keep_trace=False)
        except Exception:
            pass

        self._emit("run.end", status=status)
        self.client.complete(self.job.run_id, status, summary, time.monotonic() - started)
        return status

    def _inspect(self, url: str) -> dict[str, Any]:
        page = self.session.page

        self._emit("step.start", step_id="open", label="打开页面", index=1, total=2)
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        # 单页应用在 networkidle 之后还要渲染一段时间，不等会扑空
        ready = wait_for_app_ready(page, timeout_ms=30_000)
        page.wait_for_timeout(500)
        self._emit(
            "step.end",
            step_id="open",
            label="打开页面",
            status="passed" if ready else "failed",
            message="" if ready else "等了 30 秒页面上仍然没有可交互元素",
            data={"url": page.url, "title": page.title()},
        )

        self._emit("step.start", step_id="detect", label="识别登录表单", index=2, total=2)
        detection = detect_login_form(page)

        screenshot_url = None
        shot = self.artifacts_dir / "login.png"
        try:
            page.screenshot(path=str(shot), full_page=False)
            screenshot_url = self.client.upload_artifact(self.job.run_id, "login.png", shot)
        except Exception:
            pass

        self._emit(
            "step.end",
            step_id="detect",
            label="识别登录表单",
            status="passed" if detection.get("found") else "failed",
            message="" if detection.get("found") else detection.get("reason", "识别失败"),
            screenshot=screenshot_url,
        )

        parsed = urlparse(url)
        return {
            "detection": detection,
            "title": page.title(),
            "final_url": page.url,
            "base_url": urlunparse((parsed.scheme, parsed.netloc, "", "", "", "")),
            "login_path": parsed.path + (f"?{parsed.query}" if parsed.query else ""),
            "screenshot": screenshot_url,
        }

    def _emit(self, type_: str, **data: Any) -> None:
        self.client.post_events(self.job.run_id, [new_event(type_, **data)])  # type: ignore[arg-type]
