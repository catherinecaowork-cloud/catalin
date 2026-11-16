"""颜色×尺码矩阵自测。

vxe-table 单元格包装 id 是随机 uuid，回放时必然失效。
应改用 matrix 候选：行颜色 + 列尺码。

用法：python scripts/selftest_matrix_grid.py
"""

from __future__ import annotations

from playwright.sync_api import sync_playwright

from autotest_executor.browser.locator import resolve_target
from autotest_executor.browser.locator_script import locator_init_script
from autotest_executor.compiler import compile_events
from autotest_protocol import Target

_LOCATOR_JS = locator_init_script()

PAGE = """
<!doctype html><html><body>
<div role="dialog" class="el-dialog"><div class="el-dialog__title">新增</div>
<table class="vxe-table">
  <thead><tr>
    <th>颜色尺码</th><th>155</th><th>160</th><th>165</th><th>170</th><th>合计</th>
  </tr></thead>
  <tbody>
    <tr>
      <td>SAD BLUE</td>
      <td><div id="15ac707-e508-4e63-810d-01f6c53d1df1-0-0"><input class="vxe-input--inner" id="c155"></div></td>
      <td><div id="15ac707-e508-4e63-810d-01f6c53d1df1-0-1"><input class="vxe-input--inner" id="c160"></div></td>
      <td><div id="15ac707-e508-4e63-810d-01f6c53d1df1-0-2"><input class="vxe-input--inner" id="c165"></div></td>
      <td><div id="15ac707-e508-4e63-810d-01f6c53d1df1-0-3"><input class="vxe-input--inner" id="c170"></div></td>
      <td>0</td>
    </tr>
    <tr><td>合计</td><td>0</td><td>0</td><td>0</td><td>0</td><td>0</td></tr>
  </tbody>
</table>
<table class="vxe-table">
  <thead><tr><th>颜色尺码</th><th>155</th><th>160</th></tr></thead>
  <tbody><tr>
    <td>OTHER</td>
    <td><div id="other-uuid-0-0"><input class="vxe-input--inner" id="other155"></div></td>
    <td><div id="other-uuid-0-1"><input class="vxe-input--inner" id="other160"></div></td>
  </tr></tbody>
</table>
</div></body></html>
"""


def _assert(cond: bool, message: str) -> None:
    if not cond:
        raise SystemExit(f"× {message}")
    print(f"√ {message}")


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(PAGE)
        page.evaluate(_LOCATOR_JS)

        described = page.eval_on_selector("#c160", "(el) => window.__atpDescribe(el)")
        _assert(described["candidates"][0]["kind"] == "matrix", f"首选应是 matrix，实际 {described['candidates'][0]}")
        _assert(
            described["candidates"][0]["value"] == "SAD BLUE|160",
            f"matrix 值应是行×列，实际 {described['candidates'][0]['value']}",
        )

        css_ids = [
            c["value"]
            for c in described["candidates"]
            if c["kind"] == "css" and "15ac707" in c["value"]
        ]
        _assert(not css_ids, f"不应再产出 vxe uuid css 候选，实际 {css_ids}")

        steps, _ = compile_events(
            [
                {
                    "type": "fill",
                    "target": described,
                    "value": "1",
                    "context": page.eval_on_selector("#c160", "(el) => window.__atpContext(el)"),
                }
            ],
            "http://example.test/app",
        )
        step = steps[-1]
        _assert(
            "SAD BLUE×160" in step["label"],
            f"步骤名应含颜色×尺码，实际 {step['label']!r}",
        )

        resolution = resolve_target(page, Target.model_validate(step["target"]), 3_000)
        hit = resolution.locator.get_attribute("id")
        _assert(hit == "c160", f"回放应命中 SAD BLUE 的 160 列，实际 id={hit!r}")
        _assert(resolution.fallback_index == 0, "matrix 首选应直接命中")

        resolution.locator.fill("2")
        _assert(page.input_value("#c160") == "2", "应能填入矩阵单元格")

        browser.close()

    print("\n颜色×尺码矩阵自测通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
