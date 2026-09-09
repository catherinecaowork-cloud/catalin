"""非必填下拉是空的：跳过，不中断整次运行。"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from autotest_executor.browser.actions import ActionRunner
from autotest_executor.browser.session import BrowserSession
from autotest_protocol import Candidate, Flow, Job, RunOptions, SiteRef, Step, Target
from autotest_protocol.job import ProbeConfig

PAGE = """<!doctype html>
<html><body>
<div class="ant-form-item">
  <div class="ant-form-item-label"><label class="ant-form-item-required">品类</label></div>
  <div class="ant-select" id="cat"><span class="ant-select-selection-item"></span></div>
</div>
<div class="ant-form-item">
  <div class="ant-form-item-label"><label>品牌</label></div>
  <div class="ant-select" id="brand"><span class="ant-select-selection-item"></span></div>
</div>
<div class="ant-select-dropdown" style="display:block;position:fixed;top:80px;left:8px;background:#fff">
  <div class="ant-select-item-empty">暂无数据</div>
</div>
</body></html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        body = PAGE.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:
        pass


def _step(step_id: str, css: str, label: str) -> Step:
    return Step(
        id=step_id,
        action="choose",
        value="Gucci",
        label=label,
        target=Target(candidates=[Candidate(kind="css", value=css)]),
        choose_mode="search_or_first",
    )


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"× {message}")
    print(f"√ {message}")


def main() -> int:
    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    job = Job(
        run_id="selftest-optional",
        site=SiteRef(
            id="selftest",
            base_url=f"http://127.0.0.1:{port}",
            probe=ProbeConfig(enabled=False),
        ),
        flow=Flow(name="新建款式", steps=[_step("s1", "#brand", "选择「品牌」为 Gucci")]),
        options=RunOptions(headless=True, video="off", trace="off"),
    )
    with TemporaryDirectory() as tmp:
        session = BrowserSession(job, Path(tmp))
        session.start()
        try:
            session.page.goto(job.site.base_url, wait_until="load")
            runner = ActionRunner(session)
            brand = runner.run(_step("s1", "#brand", "在「新增」弹窗：选择「品牌」为 Gucci"))
            _assert(brand.status == "skipped", f"非必填空品牌应跳过，实际 {brand.status} {brand.message}")
            session.page.goto(job.site.base_url, wait_until="load")
            category = runner.run(_step("s2", "#cat", "在「新增」弹窗：选择「品类」为 T恤"))
            _assert(category.status == "failed", f"必填空品类应失败，实际 {category.status} {category.message}")
        finally:
            session.stop(keep_trace=False)
    server.shutdown()
    print("selftest_optional_skip ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
