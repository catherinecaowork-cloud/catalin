"""尺码面板：S/M/L 在未激活 tab 里时，不能点 DOM 里第一个隐藏「S」。

录制要点：点字母尺码应记下所在 tab + 可见 sizeTag，不要录成已选 is-closable 芯片。

用法：python scripts/selftest_size_panel.py
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

from autotest_executor.browser.locator import pick_panel_choice

_ROOT = Path(__file__).resolve().parents[1]
_LOCATOR_JS = (
    _ROOT / "packages/executor/autotest_executor/browser/locator_candidates.js"
).read_text(encoding="utf-8")
_RECORDER_JS = (
    _ROOT / "packages/executor/autotest_executor/browser/recorder.js"
).read_text(encoding="utf-8")

PAGE = """<!doctype html>
<html><body>
<div class="el-select-dropdown is-multiple" style="position:fixed;top:8px;left:8px;background:#fff;border:1px solid #ddd;padding:8px">
  <div class="el-tabs">
    <div class="el-tabs__header">
      <div class="el-tabs__item is-active" id="tab-上衣尺码">上衣尺码</div>
      <div class="el-tabs__item" id="tab-S/M/L码">S/M/L码</div>
    </div>
    <div class="el-tabs__content">
      <div id="pane-上衣尺码" class="el-tab-pane" aria-hidden="false">
        <div class="sizeTag">
          <span class="el-tag el-tag--info" data-size="32"><span class="el-tag__content">32</span></span>
        </div>
      </div>
      <div id="pane-S/M/L码" class="el-tab-pane" aria-hidden="true" style="display:none">
        <div class="title-tag">女装上装</div>
        <div class="sizeTag">
          <span class="el-tag el-tag--info" data-size="S"><span class="el-tag__content">S</span></span>
          <span class="el-tag el-tag--info" data-size="M"><span class="el-tag__content">M</span></span>
          <span class="el-tag el-tag--info" data-size="L"><span class="el-tag__content">L</span></span>
        </div>
      </div>
    </div>
  </div>
  <div class="select-options">
    <span class="el-tag is-closable" id="chip-s"><span class="el-tag__content">S</span></span>
  </div>
</div>
<script>
  const tabs = [...document.querySelectorAll('.el-tabs__item')];
  const panes = {
    '上衣尺码': document.getElementById('pane-上衣尺码'),
    'S/M/L码': document.getElementById('pane-S/M/L码'),
  };
  function show(name) {
    tabs.forEach((tab) => tab.classList.toggle('is-active', tab.textContent === name));
    Object.entries(panes).forEach(([key, pane]) => {
      const on = key === name;
      pane.setAttribute('aria-hidden', on ? 'false' : 'true');
      pane.style.display = on ? '' : 'none';
    });
  }
  tabs.forEach((tab) => tab.addEventListener('click', () => show(tab.textContent.trim())));
  document.querySelectorAll('.el-tag').forEach((tag) => {
    tag.addEventListener('click', () => {
      if (tag.closest('.el-tab-pane[aria-hidden="true"]')) return;
      tag.classList.add('is-checked');
      tag.dataset.picked = '1';
    });
  });
</script>
</body></html>
"""


COLOR_PAGE = """<!doctype html>
<html><body>
<div class="el-select-dropdown is-multiple" style="position:fixed;top:8px;left:8px;background:#fff;border:1px solid #ddd;padding:8px">
  <div class="select-body">
    <div class="select-options">
      <span class="el-tag el-tag--info is-closable" id="c-yellow"><span class="el-tag__content"><pre>黄色</pre></span></span>
      <span class="el-tag el-tag--info is-closable" id="c-cyan"><span class="el-tag__content"><pre>青色</pre></span></span>
    </div>
  </div>
</div>
</body></html>
"""


def _assert(cond: bool, message: str) -> None:
    if not cond:
        raise SystemExit(f"× {message}")
    print(f"√ {message}")


def main() -> int:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(PAGE)
        picked = pick_panel_choice(page, "S", kind="tag", timeout_ms=3_000)
        checked = page.locator(".el-tag.is-checked").evaluate_all(
            "els => els.map(el => el.getAttribute('data-size'))"
        )
        hidden_first = page.get_by_text("S", exact=True).first
        _assert(picked == "S", f"应点到 S，实际 {picked}")
        _assert(checked == ["S"], f"激活 tab 里的 S 应被选中，实际 {checked}")
        _assert(
            page.get_by_text("S/M/L码", exact=True).evaluate("el => el.classList.contains('is-active')"),
            "应切到 S/M/L 码 tab",
        )
        _assert(hidden_first.is_visible(), "点中之后 S 才可见")

        page.set_content(PAGE)
        page.evaluate(_LOCATOR_JS)
        retarget = page.evaluate(
            """() => {
              const chip = document.getElementById('chip-s');
              const mapped = window.__atpSelectTag(chip);
              return mapped && mapped.getAttribute('data-size');
            }"""
        )
        _assert(retarget == "S", f"已选芯片应映射回 sizeTag，实际 {retarget}")
        described = page.evaluate("() => window.__atpDescribe(document.getElementById('chip-s'))")
        values = [c.get("value") for c in described["candidates"]]
        _assert("S" in values, f"录制应记下字母尺码文案，实际 {described['candidates']}")
        _assert(
            any("sizeTag" in str(v) and "pane" in str(v) for v in values),
            f"录制应带上所在 pane 的 sizeTag，实际 {described['candidates']}",
        )
        _assert(
            not any("is-closable" in str(v) for v in values),
            f"不应把已选芯片 class 写进定位，实际 {described['candidates']}",
        )

        page.set_content(PAGE)
        page.evaluate(_LOCATOR_JS)
        page.evaluate("() => { window.__atpEvents = []; window.__atpEmit = (e) => window.__atpEvents.push(e); }")
        page.evaluate(_RECORDER_JS)
        page.locator("#chip-s").click()
        events = page.evaluate("() => window.__atpEvents || []")
        texts = [e.get("text") for e in events]
        _assert(
            any(t and "S/M/L" in str(t) for t in texts),
            f"点字母尺码前应录下所在 tab，实际 {texts}",
        )
        _assert("S" in texts, f"应录下点击 S，实际 {texts}")
        _assert(
            not any(t == "女装上装" for t in texts),
            f"尺码步骤名不能用分组名，实际 {texts}",
        )
        size_ev = next((e for e in events if e.get("text") == "S"), None)
        _assert(size_ev is not None, "应发出点击 S 的步骤")
        _assert(size_ev.get("context", {}).get("label") == "S", f"上下文标题应是 S，实际 {size_ev.get('context')}")
        size_vals = [c.get("value") for c in (size_ev.get("target") or {}).get("candidates") or []]
        _assert(
            any("sizeTag" in str(v) for v in size_vals),
            f"重录应定位到 sizeTag，实际 {size_vals}",
        )
        _assert(
            not any(str(v).endswith(".sizeTag .el-tag") for v in size_vals),
            f"不应把整 pane 所有尺码写成首选，实际 {size_vals}",
        )
        _assert(
            not any("is-closable" in str(v) for v in size_vals),
            f"重录不应写成已选芯片，实际 {size_vals}",
        )

        page.set_content(COLOR_PAGE)
        page.evaluate(_LOCATOR_JS)
        color_from_pre = page.evaluate(
            """() => {
              const pre = document.querySelector('#c-yellow pre');
              const mapped = window.__atpSelectTag(pre);
              const described = window.__atpDescribe(pre);
              return {
                mapped: mapped && ((mapped.innerText || '').trim().split('\\n')[0]),
                values: (described.candidates || []).map((c) => c.value),
                first: described.candidates && described.candidates[0],
              };
            }"""
        )
        _assert(color_from_pre["mapped"] == "黄色", f"点色块内部文字应抬到色块，实际 {color_from_pre}")
        _assert(color_from_pre["first"]["kind"] == "text" and color_from_pre["first"]["value"] == "黄色", f"颜色首选应是文案，实际 {color_from_pre['first']}")
        _assert(
            any("el-tag" in str(v) for v in color_from_pre["values"]),
            f"颜色应带 el-tag 以便按色块回放，实际 {color_from_pre['values']}",
        )
        _assert(
            not any(str(v).rstrip().endswith("> pre") for v in color_from_pre["values"]),
            f"颜色不能录内部 pre，实际 {color_from_pre['values']}",
        )
        picked_color = pick_panel_choice(page, "青色", kind="tag", timeout_ms=3_000)
        _assert(picked_color == "青色", f"色板应点中青色，实际 {picked_color}")

        page.set_content(COLOR_PAGE)
        page.evaluate(_LOCATOR_JS)
        page.evaluate(
            """() => {
              window.__atpRecorder = null;
              window.__atpEvents = [];
              window.__atpEmit = (e) => window.__atpEvents.push(e);
            }"""
        )
        page.evaluate(_RECORDER_JS)
        page.evaluate(
            """() => {
              const fire = (el) => {
                if (!el) return;
                const box = el.getBoundingClientRect();
                const opts = {
                  bubbles: true,
                  cancelable: true,
                  view: window,
                  clientX: box.left + Math.max(box.width / 2, 1),
                  clientY: box.top + Math.max(box.height / 2, 1),
                };
                el.dispatchEvent(new MouseEvent('mousedown', opts));
                el.dispatchEvent(new MouseEvent('click', opts));
              };
              fire(document.querySelector('#c-yellow pre'));
              fire(document.getElementById('c-cyan'));
            }"""
        )
        color_texts = page.evaluate("() => (window.__atpEvents || []).map((e) => e.text)")
        _assert(color_texts.count("黄色") >= 1, f"应录下黄色，实际 {color_texts}")
        _assert("青色" in color_texts, f"第二色应录青色，实际 {color_texts}")
        browser.close()
    print("selftest_size_panel ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
