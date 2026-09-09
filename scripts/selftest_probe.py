"""探针自测。

用一个刻意做坏的本地页面验证：接口返回 HTTP 200 但响应体里带 errors、
脚本抛未捕获异常、Promise 被拒绝、右上角失败弹出——页面看着可能正常，
探针必须都能抓到。成功提示必须忽略。

用法：python scripts/selftest_probe.py
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from autotest_executor.browser.session import BrowserSession
from autotest_protocol import Job, RunOptions, SiteRef
from autotest_protocol.job import ProbeConfig

PAGE = """<!doctype html>
<html><body>
<h1>看起来一切正常</h1>
<div class="ant-message-notice ant-message-success"
     style="position:fixed;top:16px;left:16px;background:#f6ffed;padding:8px 12px">保存成功</div>
<div class="ant-message-notice" role="alert"
     style="position:fixed;top:16px;right:16px;background:#fff1f0;padding:8px 12px">
  <div class="ant-message-custom-content ant-message-error">保存失败：款号已存在</div>
</div>
<script>
  // 1) 状态码 200，错误藏在响应体里
  fetch('/api/data').then(r => r.json()).then(() => {});
  // 2) 未捕获的运行时错误
  setTimeout(() => { null.foo; }, 50);
  // 3) 未处理的 Promise 拒绝
  Promise.reject(new Error('后台任务失败'));
</script>
</body></html>
"""

BROKEN_JSON = b'{"data": null, "errors": [{"message": "\\u6743\\u9650\\u4e0d\\u8db3"}]}'


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/api/data"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(BROKEN_JSON)))
            self.end_headers()
            self.wfile.write(BROKEN_JSON)
            return
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
        run_id="selftest",
        site=SiteRef(
            id="selftest",
            base_url=f"http://127.0.0.1:{port}",
            probe=ProbeConfig(enabled=True, error_url_patterns=[]),
        ),
        options=RunOptions(headless=True, video="off", trace="off"),
    )

    with TemporaryDirectory() as tmp:
        session = BrowserSession(job, Path(tmp))
        session.start()
        try:
            session.page.goto(job.site.base_url, wait_until="load")
            session.page.wait_for_timeout(1200)
            probe = session.read_probe()
        finally:
            session.stop(keep_trace=False)

    checks = {
        "探针已注入": probe.get("installed") is True,
        "抓到响应体里的 errors": any(
            e.get("kind") == "body_errors" for e in probe.get("requestErrors", [])
        ),
        "抓到未捕获异常": any(e.get("kind") == "error" for e in probe.get("jsErrors", [])),
        "抓到未处理的 Promise 拒绝": any(
            e.get("kind") == "unhandledrejection" for e in probe.get("jsErrors", [])
        ),
        "抓到右上角失败弹出": any(
            "款号已存在" in (e.get("message") or "") for e in probe.get("uiErrors", [])
        ),
        "忽略保存成功提示": not any(
            "保存成功" in (e.get("message") or "") for e in probe.get("uiErrors", [])
        ),
    }

    for name, ok in checks.items():
        print(f"{'√' if ok else '×'} {name}")

    if not all(checks.values()):
        print("\n探针实际读到的内容：")
        print(probe)
        return 1
    print("\n探针自测通过：底层错误和右上角失败弹出都能抓到。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
