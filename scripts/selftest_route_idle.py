"""路由空闲：盖住内容的转圈要等，角落装饰转圈不能空等。"""

from __future__ import annotations

import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from autotest_executor.browser.readiness import wait_for_route_idle
from autotest_executor.browser.session import BrowserSession
from autotest_protocol import Job, RunOptions, SiteRef
from autotest_protocol.job import ProbeConfig

PAGE = """<!doctype html>
<html><body>
<button>ok</button>
<div class="ant-spin ant-spin-spinning" style="width:16px;height:16px;background:#f00"></div>
<div id="mask" class="el-loading-mask" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.2)"></div>
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


def main() -> int:
    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    job = Job(
        run_id="selftest-route-idle",
        site=SiteRef(
            id="selftest",
            base_url=f"http://127.0.0.1:{port}",
            probe=ProbeConfig(enabled=False),
        ),
        options=RunOptions(headless=True, video="off", trace="off"),
    )

    with TemporaryDirectory() as tmp:
        session = BrowserSession(job, Path(tmp))
        session.start()
        try:
            page = session.page
            page.goto(job.site.base_url, wait_until="load")
            started = time.perf_counter()
            idle_tiny = wait_for_route_idle(page, timeout_ms=3_000, appear_ms=0)
            tiny_ms = int((time.perf_counter() - started) * 1000)

            page.evaluate(
                """() => {
                  const mask = document.getElementById('mask');
                  mask.style.display = 'none';
                  setTimeout(() => { mask.style.display = 'block'; }, 30);
                  setTimeout(() => { mask.style.display = 'none'; }, 220);
                }"""
            )
            started = time.perf_counter()
            idle_mask = wait_for_route_idle(page, timeout_ms=3_000, appear_ms=180)
            mask_ms = int((time.perf_counter() - started) * 1000)
            mask_gone = page.evaluate(
                "() => getComputedStyle(document.getElementById('mask')).display === 'none'"
            )
        finally:
            session.stop(keep_trace=False)

    checks = {
        "角落小转圈立刻空闲": idle_tiny and tiny_ms < 250,
        "全屏遮罩等到消失": idle_mask and mask_gone and 80 <= mask_ms < 800,
    }
    for name, ok in checks.items():
        print(f"{'√' if ok else '×'} {name}")
    if not all(checks.values()):
        print({"tiny_ms": tiny_ms, "mask_ms": mask_ms, "mask_gone": mask_gone})
        return 1
    print("selftest_route_idle ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
