"""主数据下拉：搜索、第一条兜底、编辑跳过已选项。"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from autotest_executor.browser.locator import pick_dropdown_option, pick_first_dropdown_option
from autotest_executor.browser.session import BrowserSession
from autotest_protocol import Job, RunOptions, SiteRef
from autotest_protocol.job import ProbeConfig

PAGE = """<!doctype html>
<html><body>
<div class="ant-select ant-select-open" style="width:240px">
  <span class="ant-select-selection-item" title="外套">外套</span>
  <input class="ant-select-selection-search-input" value="外套" style="opacity:0;width:4px" />
</div>
<div class="ant-select-dropdown" style="position:fixed;top:40px;left:8px;background:#fff;border:1px solid #ddd">
  <div class="ant-select-item ant-select-item-option ant-select-item-option-selected" title="外套" role="option">外套</div>
  <div class="ant-select-item ant-select-item-option" title="衬衫" role="option">衬衫</div>
  <div class="ant-select-item ant-select-item-option" title="T恤" role="option">T恤</div>
</div>
<script>
function applyFilter() {
  const q = (document.querySelector('.ant-select-selection-search-input').value || '').trim();
  document.querySelectorAll('.ant-select-item-option').forEach((el) => {
    const show = !q || (el.getAttribute('title') || '').includes(q);
    el.style.display = show ? '' : 'none';
  });
}
document.querySelector('.ant-select-selection-search-input').addEventListener('input', applyFilter);
applyFilter();
</script>
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
        run_id="selftest-choose",
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
            found = pick_dropdown_option(page, "衬衫", 2_000)
            page.goto(job.site.base_url, wait_until="load")
            missing = pick_dropdown_option(page, "不存在的品类", 800)
            first = pick_first_dropdown_option(page)
            page.goto(job.site.base_url, wait_until="load")
            other = pick_first_dropdown_option(page, skip=["外套"], skip_selected=True)
            page.goto(job.site.base_url, wait_until="load")
            filtered = pick_first_dropdown_option(page, skip=["外套"], skip_selected=True)
        finally:
            session.stop(keep_trace=False)

    checks = {
        "能搜到现成项": found == "衬衫",
        "搜不到不误点": missing is None,
        "新建兜底用第一条": first == "外套",
        "编辑跳过已选换下一项": other == "衬衫",
        "搜索框残留已选文案时仍能换项": filtered == "衬衫",
    }
    for name, ok in checks.items():
        print(f"{'√' if ok else '×'} {name}")
    if not all(checks.values()):
        print({"found": found, "missing": missing, "first": first, "other": other, "filtered": filtered})
        return 1
    print("selftest_choose_fallback ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
