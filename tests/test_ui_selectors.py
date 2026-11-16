"""浮层选择器单一来源：Python 与注入前言字段一致。"""

from __future__ import annotations

from autotest_executor.browser.locator_script import locator_init_script
from autotest_executor.ui_selectors import (
    DROPDOWN_MIXED_VISIBLE,
    DROPDOWN_OPTION,
    DROPDOWN_PANEL,
    js_selector_payload,
)


def test_dropdown_panel_is_union_with_ant_dropdown() -> None:
    assert DROPDOWN_PANEL == DROPDOWN_MIXED_VISIBLE
    assert ".ant-dropdown:visible" in DROPDOWN_PANEL
    assert ".ant-cascader-dropdown:visible" in DROPDOWN_PANEL
    assert ".el-popper:visible" in DROPDOWN_PANEL


def test_dropdown_option_keeps_disabled_filter_and_role() -> None:
    assert ":not(.ant-select-item-option-disabled)" in DROPDOWN_OPTION
    assert ":not(.is-disabled)" in DROPDOWN_OPTION
    assert "[role=option]" in DROPDOWN_OPTION
    assert "ant-dropdown-menu-item" in DROPDOWN_OPTION


def test_js_preamble_keys_match_candidates_contract() -> None:
    payload = js_selector_payload()
    assert set(payload) == {"PORTAL_SEL", "STD_OPTION_SEL", "STD_DROPDOWN_SEL"}
    assert "ant-select-dropdown" in payload["PORTAL_SEL"]
    assert "ant-select-item-option-disabled" in payload["STD_OPTION_SEL"]
    script = locator_init_script()
    assert "window.__atpUiSelectors" in script
    assert "locator_candidates.js 需要先注入" in script or "__atpDescribe" in script
