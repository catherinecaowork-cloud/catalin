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

# 色板里录到的颜色没了、但还有别的颜色：按「能选中就可以」改选一项，不能跳过。
# 跳过会让必填的「颜色」空着，直到保存才报错，报错还指向上一步。
COLOR = """<!doctype html>
<html><head><style>
.el-select-dropdown { position: fixed; top: 8px; left: 8px; background: #fff;
  border: 1px solid #ddd; padding: 8px; }
.el-tag { display: inline-block; padding: 4px 8px; border: 1px solid #ccc; }
</style></head><body>
<div class="el-select-dropdown is-multiple">
  <div class="select-body">
    <div class="select-options">
      <span class="el-tag el-tag--info" id="c-yellow">
        <span class="el-tag__content"><pre>黄色</pre></span>
      </span>
      <span class="el-tag el-tag--info" id="c-cyan">
        <span class="el-tag__content"><pre>青色</pre></span>
      </span>
    </div>
  </div>
</div>
<script>
document.querySelectorAll('.el-tag').forEach(function (tag) {
  tag.addEventListener('click', function () {
    // 照抄 141 的多选色板：未选是 --info，点中换成 --primary，再点一次取消。
    const on = tag.classList.toggle('el-tag--primary');
    tag.classList.toggle('el-tag--info', !on);
    tag.dataset.picked = on ? '1' : '';
  });
});
</script>
</body></html>
"""

PAGES["/color"] = COLOR

# 录到的 tab 没了：换一个没激活的 tab 继续，和人工冒烟测试一样。
TABS = """<!doctype html>
<html><head><style>
.el-select-dropdown { position: fixed; top: 8px; left: 8px; background: #fff;
  border: 1px solid #ddd; padding: 8px; }
.el-tabs__item { display: inline-block; padding: 4px 8px; border: 1px solid #ccc; }
</style></head><body>
<div class="el-select-dropdown">
  <div class="el-tabs__item is-active" id="tab-shirt">上衣</div>
  <div class="el-tabs__item" id="tab-pants">裤装</div>
</div>
<script>
document.querySelectorAll('.el-tabs__item').forEach(function (tab) {
  tab.addEventListener('click', function () { tab.dataset.picked = '1'; });
});
</script>
</body></html>
"""

PAGES["/tabs"] = TABS


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


def _panel_click_step(step_id: str, wanted: str, label: str) -> Step:
    return Step(
        id=step_id,
        action="click",
        label=label,
        target=Target(
            candidates=[
                Candidate(kind="text", value=wanted),
                Candidate(kind="css", value=".select-options .el-tag"),
            ]
        ),
        timeout_ms=5_000,
    )


def _tab_click_step(step_id: str, wanted: str, label: str) -> Step:
    return Step(
        id=step_id,
        action="click",
        label=label,
        target=Target(
            candidates=[
                Candidate(kind="text", value=wanted),
                Candidate(kind="css", value=f"#tab-{wanted}"),
            ]
        ),
        timeout_ms=5_000,
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

            # 色板里录到的值没了、还有别的值：改选一项，不跳过、不判红。
            session.page.goto(job.site.base_url + "/color", wait_until="load")
            color = ActionRunner(session).run(
                _panel_click_step("s4", "SAD BLUE", "在「新增」弹窗：点击「SAD BLUE」")
            )
            _assert(
                color.status == "passed",
                f"面板里有别的颜色应改选而不是跳过，实际 {color.status} {color.message}",
            )
            _assert(
                "已改选" in (color.message or ""),
                f"步骤说明应写明改选了哪一项，实际 {color.message}",
            )
            picked = session.page.evaluate(
                """() => {
                  const el = document.querySelector('.el-tag[data-picked]');
                  return el ? el.innerText.trim().split('\\n')[0] : '';
                }"""
            )
            _assert(picked in {"黄色", "青色"}, f"应真的点中一个备选颜色，实际 {picked!r}")

            # 第二次兜底不能再点已经选中的「黄色」：多选面板里那会把它取消掉。
            # 141 上就是连续四次兜底都点中同一个尺码，四次之后尺码全空，保存报「尺码 必填」。
            again = ActionRunner(session).run(
                _panel_click_step("s6", "SAD BLUE 2", "在「新增」弹窗：点击「SAD BLUE 2」")
            )
            _assert(
                again.status == "passed",
                f"第二次兜底应成功，实际 {again.status} {again.message}",
            )
            _assert(
                session.page.locator("#c-yellow").get_attribute("data-picked") == "1",
                "第二次兜底不能把已经选中的「黄色」再点一遍（会取消选择）",
            )
            _assert(
                session.page.locator("#c-cyan").get_attribute("data-picked") == "1",
                "第二次兜底应改选还没选中的「青色」",
            )

            # 录到的名字恰好就是已选项：不点，也算目标状态已达成。
            same = ActionRunner(session).run(
                _panel_click_step("s7", "黄色", "在「新增」弹窗：点击「黄色」")
            )
            _assert(
                same.status == "passed",
                f"点已选中的项应直接通过，实际 {same.status} {same.message}",
            )
            _assert(
                session.page.locator("#c-yellow").get_attribute("data-picked") == "1",
                "已选中的项再点一次不能把选择取消",
            )

            # 录到的 tab 没了：换一个未激活的 tab，不能点当前已激活的那个充数。
            session.page.goto(job.site.base_url + "/tabs", wait_until="load")
            tab = ActionRunner(session).run(
                _tab_click_step("s5", "裙装", "在「新增」弹窗：点击「裙装」")
            )
            _assert(
                tab.status == "passed",
                f"没有「裙装」时应换一个 tab 继续，实际 {tab.status} {tab.message}",
            )
            _assert(
                session.page.locator("#tab-pants").get_attribute("data-picked") == "1",
                "应真的点了另一个未激活的 tab",
            )
            _assert(
                session.page.locator("#tab-shirt").get_attribute("data-picked") is None,
                "不能把已激活的 tab 再点一遍当通过",
            )
        finally:
            session.stop(keep_trace=False)
    server.shutdown()
    print("selftest_optional_skip ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
