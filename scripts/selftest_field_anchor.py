"""同格标签锚定自测。

Oinone 的 form-container 不给 data-name，标签是控件的亲兄弟：

    <div style="width:25%">
      <div class="label"><span class="required">*</span>交货日期</div>
      <div class="ant-picker"><div class="ant-picker-input"><input readonly></div></div>
    </div>

一个弹窗里有好几个一模一样的 ant-picker。如果定位不锚回这一格的标签，
录的是「交货日期」，回放却会命中排在前面的「下单日期」——这正是要防的。

用法：python scripts/selftest_field_anchor.py
"""

from __future__ import annotations

from playwright.sync_api import sync_playwright

from autotest_executor.browser.locator import resolve_target
from autotest_executor.browser.locator_script import locator_init_script
from autotest_executor.compiler import compile_events
from autotest_protocol import Target

_LOCATOR_JS = locator_init_script()


def _cell(label: str, control: str, required: bool = True) -> str:
    star = '<span class="required">*</span>' if required else ""
    return (
        f'<div style="width:25%;display:inline-block">'
        f'<div class="label">{star}{label}</div>{control}</div>'
    )


_PICKER = (
    '<div class="ant-picker oio-date-time-picker"><div class="ant-picker-input">'
    '<input id="{id}" readonly placeholder="请选择日期" value="{value}"></div></div>'
)
_SELECT = '<div class="el-select"><div class="el-select__wrapper" id="{id}">请选择</div></div>'

PAGE = f"""<!doctype html><html><body>
<div role="dialog" class="el-dialog" style="width:900px">
  <div class="el-dialog__title">新增</div>
  <section class="form-section"><div class="section-title">2.输入生产单信息</div>
    <div class="form-container">
      {_cell("生产单号", '<span class="ant-input-affix-wrapper oio-input"><input id="prodNo"></span>')}
      {_cell("客户单号", '<span class="ant-input-affix-wrapper oio-input"><input id="custNo"></span>', False)}
      {_cell("下单日期", _PICKER.format(id="order", value="2026-09-09 15:33:19"))}
    </div>
  </section>
  <section class="form-section"><div class="section-title">3.输入PO信息</div>
    <div class="form-container">
      {_cell("PO单号", '<span class="ant-input-affix-wrapper oio-input"><input id="poNo"></span>')}
      {_cell("交货日期", _PICKER.format(id="delivery", value=""))}
      {_cell("国家/地区", _SELECT.format(id="country"))}
    </div>
  </section>
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

        context = page.eval_on_selector("#delivery", "(el) => window.__atpContext(el)")
        _assert(
            context.get("label") == "交货日期",
            f"日期框要认出同格标签，实际 {context.get('label')!r}",
        )
        _assert(
            "交货日期" in str(context.get("trigger_css") or ""),
            f"触发器要锚回交货日期，实际 {context.get('trigger_css')!r}",
        )

        described = page.eval_on_selector("#delivery", "(el) => window.__atpDescribe(el)")
        kinds = [c["kind"] for c in described["candidates"]]
        _assert(
            ":has(" in str(described["candidates"][0]["value"]),
            f"首选候选应是标签锚定选择器，实际 {described['candidates'][0]}",
        )
        _assert(
            all(c.get("value") != "交货日期" or c["kind"] != "label" for c in described["candidates"]),
            f"div.label 不是真 label，不能当 label 候选，实际 {kinds}",
        )

        # 锚定选择器必须唯一命中交货日期，不能捞到下单日期
        for candidate in described["candidates"]:
            if candidate["kind"] != "css" or ":has(" not in candidate["value"]:
                continue
            loc = page.locator(candidate["value"])
            ids = [loc.nth(i).get_attribute("id") for i in range(loc.count())]
            _assert(ids == ["delivery"], f"锚定选择器应只命中交货日期，实际 {ids} <- {candidate['value']}")

        country = page.eval_on_selector("#country", "(el) => window.__atpContext(el)")
        _assert(
            country.get("label") == "国家/地区",
            f"下拉也要认出同格标签，实际 {country.get('label')!r}",
        )

        # 录制 → 编译 → 回放：编译出的步骤必须仍然指向交货日期
        steps, _ = compile_events(
            [
                {
                    "type": "click",
                    "target": described,
                    "text": "",
                    "context": context,
                }
            ],
            "http://example.test/app",
            intent="新增生产单",
        )
        step = steps[-1]
        _assert(
            step["label"] == "在「新增」弹窗：点击「交货日期」",
            f"步骤名应是交货日期，实际 {step['label']!r}",
        )

        resolution = resolve_target(page, Target.model_validate(step["target"]), 3_000)
        hit = resolution.locator.get_attribute("id")
        _assert(hit == "delivery", f"回放应命中交货日期输入框，实际 id={hit!r}")
        _assert(
            resolution.fallback_index == 0,
            f"首选候选就该命中，不应漂移到第 {resolution.fallback_index + 1} 顺位",
        )

        # 日期填值靠 trigger_css 开面板：点它必须打开交货日期，而不是下单日期
        page.locator(context["trigger_css"]).last.click()
        focused = page.evaluate("() => (document.activeElement || {}).id || ''")
        _assert(focused == "delivery", f"点触发器应打开交货日期，实际聚焦 {focused!r}")

        browser.close()

    print("\n同格标签锚定自测通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
