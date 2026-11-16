"""浮层 / 下拉通用选择器——录制与回放的单一来源。

Ant Design / Element UI 的通用件放这里；厂商特例（`oio-` 等）留在
`autotest_adapters.oinone`。JS 侧通过 `js_preamble()` 注入，不再在
`locator_candidates.js` 里抄一份常量。
"""

from __future__ import annotations

import json

# —— 活着的层（回放找 scope 用；不含 :visible，由 _try_root 自己判可见）——

LIVE_MODAL = (
    ".ant-modal-wrap[role=dialog], "
    ".ant-modal-content, "
    "[role=dialog], "
    "dialog[open], "
    ".ant-drawer-content, "
    ".el-dialog"
)

LIVE_DROPDOWN = (
    ".ant-select-dropdown, .ant-dropdown, "
    ".ant-picker-dropdown, .ant-cascader-dropdown, "
    ".ant-cascader-menus, "
    ".ant-popover, "
    ".el-select-dropdown, "
    ".el-color-dropdown, "
    ".el-popper.el-select__popper, "
    ".el-select__popper, "
    ".el-popper, "
    "[role=listbox]"
)

# —— 可见面板（Playwright :visible；判定「下拉开着」的正规口径）——
# 合并自旧 DROPDOWN_PANEL / DROPDOWN_MIXED_VISIBLE / PANEL_VISIBLE_DEFAULT：
# 补上曾缺失的 `.ant-dropdown`，保留 cascader / el-popper / listbox。

DROPDOWN_PANEL = (
    ".ant-select-dropdown:visible, "
    ".ant-dropdown:visible, "
    ".el-select-dropdown:visible, "
    ".ant-cascader-dropdown:visible, "
    ".ant-cascader-menus:visible, "
    ".el-popper.el-select__popper:visible, "
    ".el-select__popper:visible, "
    ".el-popper:visible, "
    "[role=listbox]:visible"
)

# 历史别名：曾经与 DROPDOWN_PANEL 互有差集；单一来源后二者同义。
DROPDOWN_MIXED_VISIBLE = DROPDOWN_PANEL

DROPDOWN_SEARCH = (
    ".ant-select-open .ant-select-selection-search-input, "
    ".ant-select-dropdown:visible input, "
    ".el-select__popper:visible input, "
    ".el-select-dropdown:visible input, "
    "[role=listbox]:visible input"
)

# 下拉选项：保留 disabled 过滤（取更严的一份），并含 [role=option] / 菜单项。
DROPDOWN_OPTION = (
    ".ant-select-item-option:not(.ant-select-item-option-disabled), "
    ".ant-select-item:not(.ant-select-item-group)"
    ":not(.ant-select-item-empty):not(.ant-select-item-option-disabled), "
    ".el-select-dropdown__item:not(.is-disabled), "
    "[role=option], "
    ".ant-select-dropdown .ant-table-row, "
    ".ant-dropdown-menu-item:not(.ant-dropdown-menu-item-disabled)"
)

DROPDOWN_OPTION_ACTIVE = (
    ".ant-select-item-option-active:visible, "
    ".el-select-dropdown__item.hover:visible, "
    ".el-select-dropdown__item.is-hovering:visible, "
    "[role=option][aria-selected=true]:visible"
)

DROPDOWN_VIRTUAL_HOLDER = (
    ".rc-virtual-list-holder, .rc-virtual-list, .el-scrollbar__wrap, "
    ".el-select-dropdown__wrap, .ant-table-body"
)

DROPDOWN_SCROLL_HOLDER = (
    ".rc-virtual-list-holder, .rc-virtual-list, .el-scrollbar__wrap, "
    ".el-select-dropdown__wrap"
)

OPTION_BY_TITLE = (
    '.ant-select-item-option[title="{name}"], '
    '.el-select-dropdown__item[title="{name}"], '
    '[role=option][title="{name}"]'
)

PANEL_VISIBLE_DEFAULT = DROPDOWN_PANEL

PANEL_VISIBLE_EL_SELECT = (
    ".el-select-dropdown:visible, .el-select__popper:visible, "
    ".el-popper.el-select__popper:visible"
)

DROPDOWN_ONLY_VISIBLE = ".ant-select-dropdown:visible"

PICKER_PANEL_VISIBLE = ".ant-picker-dropdown:visible, .el-picker-panel:visible"

# —— JS 注入用（无 :visible；隐藏态用框架自己的 -hidden class）——

PORTAL_SEL = ",".join(
    [
        ".ant-select-dropdown:not(.ant-select-dropdown-hidden)",
        ".ant-dropdown:not(.ant-dropdown-hidden)",
        ".ant-picker-dropdown",
        ".ant-cascader-dropdown",
        ".ant-cascader-menus",
        ".ant-mentions-dropdown",
        ".ant-popover:not(.ant-popover-hidden)",
        ".el-select-dropdown",
        ".el-popper.el-select__popper",
        ".el-select__popper",
        ".el-color-dropdown",
        ".el-popper.is-pure.el-select__popper",
        ".el-popper:not(.is-pure)",
        '[class*="color-picker"]',
        '[class*="color-panel"]',
    ]
)

# 与 DROPDOWN_OPTION 对齐（disabled 过滤 + role=option + 菜单项），供录制 climb 用。
STD_OPTION_SEL = (
    ".ant-select-item-option:not(.ant-select-item-option-disabled), "
    ".el-select-dropdown__item:not(.is-disabled), "
    "[role=option], "
    ".ant-dropdown-menu-item:not(.ant-dropdown-menu-item-disabled)"
)

STD_DROPDOWN_SEL = ",".join(
    [
        ".ant-select-dropdown",
        ".ant-dropdown",
        ".el-select-dropdown",
        ".el-popper.el-select__popper",
        ".el-select__popper",
        ".ant-cascader-dropdown",
        ".ant-cascader-menus",
        "[role=listbox]",
    ]
)

DROPDOWN_OPTION_MARKERS = ("ant-select-item-option", "el-select-dropdown__item")
SELECT_TRIGGER_MARKERS = ("el-select__wrapper", "ant-select-selector")
DROPDOWN_WIDGETS = frozenset({"el-select", "ant-select", "combobox"})


def looks_like_dropdown_option(value: str) -> bool:
    return any(marker in value for marker in DROPDOWN_OPTION_MARKERS)


def is_select_trigger_css(value: str) -> bool:
    return any(marker in value for marker in SELECT_TRIGGER_MARKERS) or (
        value.endswith(".el-select") and "dropdown" not in value
    )


def panel_visible_selectors(panel: str) -> list[str]:
    if "ant-select" in panel:
        return [DROPDOWN_ONLY_VISIBLE]
    if "el-select" in panel:
        return list(PANEL_VISIBLE_EL_SELECT.split(", "))
    if "listbox" in panel:
        return ["[role=listbox]:visible"]
    return list(PANEL_VISIBLE_DEFAULT.split(", "))


def js_selector_payload() -> dict[str, str]:
    """注入到页面的选择器字典。字段名与 locator_candidates.js 读取的键一致。"""
    return {
        "PORTAL_SEL": PORTAL_SEL,
        "STD_OPTION_SEL": STD_OPTION_SEL,
        "STD_DROPDOWN_SEL": STD_DROPDOWN_SEL,
    }


def js_preamble() -> str:
    """在 locator_candidates.js 之前注入，建立 window.__atpUiSelectors。"""
    payload = json.dumps(js_selector_payload(), ensure_ascii=False)
    return f"window.__atpUiSelectors = {payload};\n"
