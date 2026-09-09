"""踩点：打开一个页面，列出可交互元素和它们的候选定位方式。

接入新站点时用它替代手工扒 DOM。输出按稳定性排序，直接能抄进流程配置。
候选计算与录制共用 locator_candidates.js。

用法：python scripts/inspect_page.py <url> [--headed] [--shot 输出.png]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from autotest_executor.browser.readiness import wait_for_app_ready

_LOCATOR_JS = (
    Path(__file__).resolve().parents[1]
    / "packages"
    / "executor"
    / "autotest_executor"
    / "browser"
    / "locator_candidates.js"
).read_text(encoding="utf-8")

JS_COLLECT = """
() => {
  const visible = (el) => {
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return false;
    const style = getComputedStyle(el);
    return style.visibility !== 'hidden' && style.display !== 'none';
  };
  const selector = 'input, textarea, select, button, a[href], [role=button], [onclick]';
  return Array.from(document.querySelectorAll(selector))
    .filter(visible)
    .slice(0, 60)
    .map((el) => {
      const described = window.__atpDescribe(el);
      const text = (el.innerText || '').trim();
      return {
        tag: el.tagName.toLowerCase(),
        type: el.getAttribute('type'),
        name: el.getAttribute('name'),
        placeholder: el.placeholder || null,
        text: text.slice(0, 40),
        candidates: described ? described.candidates : [],
      };
    });
}
"""

STABILITY = {"testid": 0, "role": 1, "label": 2, "placeholder": 3, "text": 4, "css": 5}


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 1
    url = args[0]
    headed = "--headed" in sys.argv
    shot = None
    if "--shot" in sys.argv:
        shot = sys.argv[sys.argv.index("--shot") + 1]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        except Exception as exc:
            print(f"打不开页面：{type(exc).__name__}: {exc}")
            browser.close()
            return 1
        if not wait_for_app_ready(page, timeout_ms=30_000):
            print("警告：等了 30 秒页面上仍然没有可交互元素。")
        page.wait_for_timeout(500)
        page.evaluate(_LOCATOR_JS)

        print(f"标题：{page.title()}")
        print(f"实际地址：{page.url}")
        if shot:
            page.screenshot(path=shot, full_page=True)
            print(f"截图：{shot}")

        elements = page.evaluate(JS_COLLECT)
        browser.close()

    print(f"\n可交互元素 {len(elements)} 个：\n")
    for index, el in enumerate(elements, start=1):
        desc = f"{el['tag']}"
        if el["type"]:
            desc += f"[type={el['type']}]"
        if el["name"]:
            desc += f" name={el['name']}"
        if el["placeholder"]:
            desc += f" placeholder={el['placeholder']!r}"
        if el["text"]:
            desc += f" 文本={el['text']!r}"
        print(f"{index:>2}. {desc}")
        ordered = sorted(el["candidates"], key=lambda c: STABILITY.get(c["kind"], 9))
        for candidate in ordered[:3]:
            extra = f" name={candidate['name']!r}" if candidate.get("name") else ""
            print(f"      {candidate['kind']}={candidate['value']!r}{extra}")
        print()

    print("提示：优先用 testid / role / label，css 只作兜底。")
    print(json.dumps({"url": url, "count": len(elements)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
