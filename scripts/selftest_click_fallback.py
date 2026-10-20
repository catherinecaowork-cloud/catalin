"""点击回退候选：首选点不到时换下一个候选，而不是直接判步骤失败。

用 `<button>` 作候选（`CLICKABLE_ANCESTOR_XPATH` 会解析到它自己），在它上面盖一层
遮罩，让 Playwright 的 actionability 检查一直不过。第二候选没有任何遮挡。
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from autotest_executor.browser.actions import (
    FAILURE_NOT_ACTIONABLE,
    ActionRunner,
)
from autotest_executor.browser.session import BrowserSession
from autotest_protocol import Candidate, Job, RunOptions, SiteRef, Step, Target, TargetScope
from autotest_protocol.job import ProbeConfig

PAGE = """<!doctype html>
<html><head><style>
  body { margin: 0; }
  button { position: absolute; left: 8px; width: 200px; height: 40px; }
  #covered { top: 8px; }
  #free { top: 80px; }
  #blocker { position: absolute; left: 0; top: 0; width: 216px; height: 56px; z-index: 10; }
</style></head><body>
<div id="blocker"></div>
<button id="covered">被遮挡的按钮</button>
<button id="free" onclick="document.title = 'clicked-free'">能点的按钮</button>
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


def _step(step_id: str, candidates: list[Candidate], timeout_ms: int) -> Step:
    return Step(
        id=step_id,
        action="click",
        target=Target(candidates=candidates, scope=TargetScope(kind="page")),
        label="点击「能点的按钮」",
        timeout_ms=timeout_ms,
    )


COVERED = Candidate(kind="css", value="#covered")
FREE = Candidate(kind="css", value="#free")


def main() -> int:
    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    job = Job(
        run_id="selftest-click-fallback",
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
            runner = ActionRunner(session)

            # 首选被遮挡、次选能点：应当回退并成功
            page.goto(job.site.base_url, wait_until="load")
            fell_back = runner.run(_step("s1", [COVERED, FREE], 1_200))
            clicked_free = page.title() == "clicked-free"

            # 只有被遮挡的候选：找不到可点的，必须报失败而不是静默点上去
            page.goto(job.site.base_url, wait_until="load")
            stuck = runner.run(_step("s2", [COVERED], 800))
            title_after_stuck = page.title()
        finally:
            session.stop(keep_trace=False)

    checks = {
        "首选点不到时回退到下一候选并通过": fell_back.status == "passed",
        "命中的是第二候选": fell_back.data.get("matched") == FREE.describe(),
        "回退确实点到了第二候选": clicked_free,
        "回退按环境原因报，不报成定位漂移": "环境原因回退" in (fell_back.drift or ""),
        "只有点不到的候选时报失败": stuck.status == "failed",
        "失败分类是「找到但点不到」": stuck.data.get("failure") == FAILURE_NOT_ACTIONABLE,
        "失败时没有偷偷点上去": title_after_stuck != "clicked-free",
        "点不到的候选不进 bad（下次还试它）": runner.locator_memory.bad == set(),
        "点不到的候选不写回候选更新": runner.locator_memory.updates == [],
    }
    for name, ok in checks.items():
        print(f"{'√' if ok else '×'} {name}")
    if not all(checks.values()):
        print(
            {
                "fell_back": fell_back,
                "drift": fell_back.drift,
                "stuck": stuck,
                "title_after_stuck": title_after_stuck,
                "bad": runner.locator_memory.bad,
                "updates": runner.locator_memory.updates,
            }
        )
        return 1
    print("selftest_click_fallback ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
