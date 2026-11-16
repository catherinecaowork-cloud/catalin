"""执行器观察快照采集自测。"""

from __future__ import annotations

from pathlib import Path

import pytest

from autotest_executor.browser.locator_script import locator_init_script
from autotest_executor.observer_collect import sanitize_observation_payload
from tests.conftest import require_browser

_BROWSER_DIR = Path(__file__).resolve().parents[1] / "packages" / "executor" / "autotest_executor" / "browser"
_LOCATOR_JS = locator_init_script()
_OBSERVER_JS = (_BROWSER_DIR / "observer_snapshot.js").read_text(encoding="utf-8")

_FORM_HTML = """
<!doctype html>
<html>
  <body>
    <div class="el-dialog" role="dialog" style="display:block">
      <div class="el-dialog__title">新增款式</div>
      <form class="el-form">
        <div class="el-form-item" data-name="name">
          <label class="el-form-item__label">名称</label>
          <input type="text" placeholder="请输入名称" />
        </div>
        <div class="el-form-item" data-name="brand">
          <label class="el-form-item__label">品牌</label>
          <div class="el-select" style="display:inline-block;width:180px;height:32px">
            <div class="el-select__wrapper" style="width:180px;height:32px"></div>
          </div>
        </div>
        <div class="el-form-item">
          <label class="el-form-item__label">款式编码</label>
          <input type="text" value="ST-001" />
        </div>
        <div class="el-form-item">
          <label class="el-form-item__label">密码</label>
          <input type="password" value="SuperSecret!" />
        </div>
        <div class="el-form-item">
          <span class="el-form-item__label">155</span>
          <button type="button">155</button>
        </div>
      </form>
    </div>
  </body>
</html>
"""


def test_sanitize_drops_password_options_and_transient_labels() -> None:
    snapshot = sanitize_observation_payload(
        {
            "trigger": "form_visible",
            "url": "https://example.test/style/new",
            "layer": {"kind": "modal", "name": "新增款式"},
            "fields": [
                {
                    "label": "密码",
                    "widget_kind": "password",
                    "required": True,
                    "sample_options": ["SuperSecret!"],
                },
                {"label": "155", "widget_kind": "tab", "sample_options": []},
                {"label": "品牌", "widget_kind": "searchable_dropdown", "sample_options": ["Gucci"]},
            ],
        }
    )
    assert snapshot is not None
    labels = {field.label for field in snapshot.fields}
    assert "品牌" in labels
    assert "密码" in labels
    assert "155" not in labels
    password = next(field for field in snapshot.fields if field.label == "密码")
    assert password.sample_options == []


@pytest.mark.browser
def test_dom_snapshot_lists_fields_without_password_plaintext() -> None:
    require_browser()
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(_FORM_HTML)
        page.evaluate(_LOCATOR_JS)
        page.evaluate(_OBSERVER_JS)
        raw = page.evaluate("() => window.__atpCollectObservation('form_visible')")
        browser.close()

    snapshot = sanitize_observation_payload(raw)
    assert snapshot is not None
    labels = {field.label for field in snapshot.fields}
    assert "名称" in labels
    assert "品牌" in labels
    assert "款式编码" in labels
    assert "155" not in labels
    assert snapshot.layer.kind == "modal"
    assert snapshot.layer.name == "新增款式"
    serialized = snapshot.model_dump_json()
    assert "SuperSecret!" not in serialized
