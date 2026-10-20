"""非必填下拉是空的：跳过，不中断整次运行。

第二个场景是 141 上踩到的那个坑：跳过一个非必填字段时要收下拉，原来用的是
Escape，而 Oinone 的弹窗把 Escape 绑成「关自己」——一跳过，整个「新增」表单就没了，
后面每一步都只剩垃圾结果。跳过可以，连弹窗一起收掉不行。
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from autotest_executor.browser.actions import ActionRunner
from autotest_executor.browser.session import BrowserSession
from autotest_protocol import Candidate, Flow, Job, RunOptions, SiteRef, Step, Target
from autotest_protocol.job import ProbeConfig

PLAIN = """<!doctype html>
<html><head><style>
.ant-select { display:block; width:200px; height:32px; border:1px solid #ccc; }
</style></head><body>
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

# 照抄 141 的两个行为：Escape 关掉整个弹窗；点触发器切换面板开关。
MODAL = """<!doctype html>
<html><head><style>
.ant-select { display:block; width:200px; height:32px; border:1px solid #ccc; }
.ant-select-selector { display:block; width:100%; height:100%; }
.ant-modal-content { width:600px; height:400px; background:#fff; }
</style></head><body>
<div class="ant-modal-wrap" id="wrap">
  <div class="ant-modal-content">
    <div class="ant-form-item">
      <div class="ant-form-item-label"><label>品牌</label></div>
      <div class="ant-select" id="brand">
        <span class="ant-select-selector" id="brand-trigger">
          <span class="ant-select-selection-item"></span>
        </span>
      </div>
    </div>
  </div>
</div>
<div class="ant-select-dropdown" id="brand-panel"
     style="display:block;position:fixed;bottom:0;right:0;background:#fff">
  <div class="ant-select-item-empty">暂无数据</div>
</div>
<script>
document.addEventListener('keydown', function (e) {
  if (e.key === 'Escape') { document.getElementById('wrap').style.display = 'none'; }
});
document.getElementById('brand-trigger').addEventListener('click', function () {
  var p = document.getElementById('brand-panel');
  p.style.display = (p.style.display === 'block') ? 'none' : 'block';
});
</script>
</body></html>
"""

PAGES = {"/": PLAIN, "/modal": MODAL}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        body = PAGES.get(self.path, PLAIN).encode("utf-8")
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


def _modal_step(step_id: str, label: str) -> Step:
    return Step(
        id=step_id,
        action="choose",
        value="Gucci",
        label=label,
        target=Target(
            candidates=[Candidate(kind="css", value="#brand")],
            trigger_css="#brand-trigger",
        ),
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

            # 弹窗里跳过一个非必填项：可以跳过，不能把弹窗一起收掉。
            session.page.goto(job.site.base_url + "/modal", wait_until="load")
            modal = ActionRunner(session).run(
                _modal_step("s3", "在「新增」弹窗：选择「品牌」为 Gucci")
            )
            _assert(
                modal.status == "skipped",
                f"弹窗里非必填空品牌应跳过，实际 {modal.status} {modal.message}",
            )
            _assert(
                session.page.locator("#wrap").is_visible(),
                "跳过非必填项后，「新增」弹窗必须还在",
            )
            _assert(
                not session.page.locator("#brand-panel").is_visible(),
                "跳过后下拉面板应已收起",
            )
        finally:
            session.stop(keep_trace=False)
    server.shutdown()
    print("selftest_optional_skip ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
