"""动作生效确认：点击下拉触发器后下拉没展开，要报「点了没生效」而不是通过。

三类页面：触发器真的展开下拉 / 触发器什么都没做 / 下拉本来就开着（点它反而收起）。
第三类是护栏——「点完没有下拉」在那种情况下说明不了没生效。
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from autotest_executor.browser.actions import FAILURE_NO_EFFECT, ActionRunner
from autotest_executor.browser.session import BrowserSession
from autotest_protocol import Candidate, Job, RunOptions, SiteRef, Step, Target, TargetScope
from autotest_protocol.job import ProbeConfig

_STYLE = """
<style>
  body { margin: 0; }
  #trigger { position: absolute; top: 8px; left: 8px; width: 200px; height: 40px;
             background: #eee; }
  .ant-select-dropdown { position: absolute; top: 60px; left: 8px; width: 200px;
                         height: 120px; border: 1px solid #d9d9d9; background: #fff; }
</style>
"""

# 触发器真的展开下拉
OPENS = f"""<!doctype html><html><head>{_STYLE}</head><body>
<div id="trigger" onclick="document.body.insertAdjacentHTML('beforeend',
  '<div class=&quot;ant-select-dropdown&quot;>选项一</div>')">品类</div>
</body></html>
"""

# 触发器什么都没做——点下去页面毫无变化
INERT = f"""<!doctype html><html><head>{_STYLE}</head><body>
<div id="trigger">品类</div>
</body></html>
"""

# 下拉本来就开着，点触发器会把它收起（Ant 的开关行为）
ALREADY_OPEN = f"""<!doctype html><html><head>{_STYLE}</head><body>
<div id="trigger" onclick="document.querySelector('.ant-select-dropdown').remove()">品类</div>
<div class="ant-select-dropdown">选项一</div>
</body></html>
"""

PAGES = {"opens": OPENS, "inert": INERT, "already_open": ALREADY_OPEN}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        body = PAGES.get(self.path.strip("/"), INERT).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:
        pass


def _step(step_id: str, timeout_ms: int) -> Step:
    """widget=ant-select 就是「这是个下拉触发器」的声明，生效确认据此判定后果。"""
    return Step(
        id=step_id,
        action="click",
        target=Target(
            candidates=[Candidate(kind="css", value="#trigger")],
            scope=TargetScope(kind="page"),
            widget="ant-select",
        ),
        label="点击「品类」",
        timeout_ms=timeout_ms,
    )


def main() -> int:
    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"

    job = Job(
        run_id="selftest-click-effect",
        site=SiteRef(id="selftest", base_url=base, probe=ProbeConfig(enabled=False)),
        options=RunOptions(headless=True, video="off", trace="off"),
    )

    with TemporaryDirectory() as tmp:
        session = BrowserSession(job, Path(tmp))
        session.start()
        try:
            page = session.page
            runner = ActionRunner(session)

            page.goto(f"{base}/opens", wait_until="load")
            opened = runner.run(_step("s1", 1_200))

            page.goto(f"{base}/inert", wait_until="load")
            inert = runner.run(_step("s2", 700))

            page.goto(f"{base}/already_open", wait_until="load")
            toggled = runner.run(_step("s3", 700))
            still_closed = page.locator(".ant-select-dropdown").count() == 0
        finally:
            session.stop(keep_trace=False)

    checks = {
        "下拉真的展开时照常通过": opened.status == "passed",
        "下拉没展开时报失败": inert.status == "failed",
        "失败分类是「点了没生效」": inert.data.get("failure") == FAILURE_NO_EFFECT,
        "失败说明指出点了没生效": "点了没生效" in (inert.message or ""),
        "本来就开着时不判失败（点它是收起）": toggled.status == "passed",
        "护栏这一轮确实把下拉点关了": still_closed,
    }
    for name, ok in checks.items():
        print(f"{'√' if ok else '×'} {name}")
    if not all(checks.values()):
        print(
            {
                "opened": opened,
                "inert": inert,
                "toggled": toggled,
                "still_closed": still_closed,
            }
        )
        return 1
    print("selftest_click_effect ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
