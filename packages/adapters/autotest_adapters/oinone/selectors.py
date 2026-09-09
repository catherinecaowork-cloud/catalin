"""Oinone / Ant Design 选择器常量（从执行器内核搬出）。"""

from __future__ import annotations

import re

LIVE_MODAL = (
    ".ant-modal-wrap.oio-modal-wrapper, "
    ".oio-modal-wrapper, "
    ".ant-modal-wrap[role=dialog], "
    ".ant-modal-content, "
    "[role=dialog], "
    "dialog[open], "
    ".ant-drawer-content, "
    ".el-dialog, "
    ".oio-modal"
)

LIVE_DROPDOWN = (
    ".ant-select-dropdown:visible, .ant-dropdown:visible, "
    ".ant-picker-dropdown:visible, .ant-cascader-dropdown:visible, "
    ".ant-cascader-menus:visible, "
    ".ant-popover:visible, "
    ".el-select-dropdown:visible, "
    ".el-color-dropdown:visible, "
    ".el-popper.el-select__popper:visible, "
    ".el-select__popper:visible, "
    ".el-popper:visible, "
    "[role=listbox]:visible"
)

DROPDOWN_PANEL = (
    ".ant-select-dropdown:visible, .el-select-dropdown:visible, "
    ".ant-cascader-dropdown:visible, .ant-cascader-menus:visible, "
    ".el-popper.el-select__popper:visible, .el-select__popper:visible, "
    "[role=listbox]:visible"
)

DROPDOWN_SEARCH = (
    ".ant-select-open .ant-select-selection-search-input, "
    ".ant-select-dropdown:visible input, "
    ".el-select__popper:visible input, "
    ".el-select-dropdown:visible input, "
    "[role=listbox]:visible input"
)

DROPDOWN_OPTION = (
    ".ant-select-item-option:not(.ant-select-item-option-disabled), "
    ".ant-select-item:not(.ant-select-item-group):not(.ant-select-item-empty):not(.ant-select-item-option-disabled), "
    ".el-select-dropdown__item:not(.is-disabled), "
    "[role=option], "
    ".ant-select-dropdown .ant-table-row, "
    ".ant-dropdown-menu-item:not(.ant-dropdown-menu-item-disabled)"
)

FIELD_INPUT = (
    "input:not([type=hidden]):not([type=file]):not(.is-hidden):not(.ant-select-selection-search-input), "
    "textarea, "
    ".ant-select-selector, "
    ".el-select__wrapper, "
    ".el-select, "
    "[contenteditable=true]"
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

SIDEBAR_MENU_ITEM = 'li.ant-menu-item[role="menuitem"][title="{name}"]'
SIDEBAR_SUBMENU_TITLE = "div.ant-menu-submenu-title"

# actions.py 用到的可见层选择器
MODAL_VISIBLE = (
    ".ant-modal-content:visible, .oio-modal-wrapper:visible, "
    ".ant-modal-wrap:visible, [role=dialog]:visible"
)

MODAL_WRAP_VISIBLE = (
    ".ant-modal-wrap:visible, .oio-modal-wrapper:visible, "
    ".ant-modal-content:visible, .el-dialog:visible, [role=dialog]:visible"
)

MODAL_TITLE_VISIBLE = (
    ".ant-modal-title:visible, .el-dialog__title:visible, "
    "[role=dialog]:visible .oio-dialog-title, [role=dialog]:visible h1, "
    "[role=dialog]:visible h2"
)

DROPDOWN_POPPER_VISIBLE = (
    ".ant-select-dropdown:visible, [role=listbox]:visible, .el-select__popper:visible"
)

DROPDOWN_MIXED_VISIBLE = (
    ".ant-select-dropdown:visible, .el-select-dropdown:visible, "
    ".el-popper.el-select__popper:visible, .el-select__popper:visible, "
    ".el-popper:visible, [role=listbox]:visible, .ant-dropdown:visible"
)

OVERLAY_VISIBLE = (
    ".ant-modal-wrap:visible, .ant-modal-content:visible, "
    ".oio-modal-wrapper:visible, [role=dialog]:visible, "
    ".ant-drawer-content:visible, .el-drawer:visible"
)

CLICKABLE_VISIBLE = (
    "button:visible, [role=button]:visible, .oio-action-item:visible, .ant-btn:visible"
)

SPINNER_VISIBLE = ".ant-spin-spinning:visible, .el-loading-mask:visible, .oio-spin:visible"

DROPDOWN_ONLY_VISIBLE = ".ant-select-dropdown:visible"

DROPDOWN_ALT_VISIBLE = (
    ".ant-dropdown:visible, "
    ".el-popper:visible"
)

REQUIRED_FIELD_JS = """
(el) => {
  const item = el.closest('.ant-form-item, .el-form-item, .oio-form-item, [class*="form-item"], [data-name]');
  if (!item) return false;
  if (item.querySelector('[aria-required="true"], [required], .ant-form-item-required, .el-form-item-required, .is-required')) return true;
  const label = item.querySelector(
    'label, .ant-form-item-label, .el-form-item__label, .oio-form-item-label, [class*="form-item-label"]'
  );
  if (label) {
    const cls = label.className || '';
    if (/\\b(ant-form-item-required|el-form-item-required|is-required)\\b/.test(cls)) return true;
    if ((label.textContent || '').includes('*')) return true;
  }
  return false;
}
"""

REQUIRED_FIELDS_JS = """
() => {
  const items = document.querySelectorAll(
    '.ant-form-item, .el-form-item, .oio-form-item, [class*="form-item"], [data-name]'
  );
  const out = [];
  for (const item of items) {
    if (!item.offsetParent) continue;
    let required = false;
    if (item.querySelector('[aria-required="true"], [required], .ant-form-item-required, .el-form-item-required, .is-required')) required = true;
    if (!required) {
      const label = item.querySelector(
        'label, .ant-form-item-label, .el-form-item__label, .oio-form-item-label, [class*="form-item-label"]'
      );
      if (label) {
        const cls = label.className || '';
        if (/\\b(ant-form-item-required|el-form-item-required|is-required)\\b/.test(cls)) required = true;
        if ((label.textContent || '').includes('*')) required = true;
      }
    }
    if (!required) continue;
    const named = item.getAttribute && item.getAttribute('data-name');
    if (named) out.push(named);
    else {
      const label = item.querySelector(
        'label, .ant-form-item-label, .el-form-item__label, .oio-form-item-label, [class*="form-item-label"]'
      );
      const text = label ? (label.textContent || '').replace(/\\*/g, '').trim() : '';
      if (text) out.push(text);
    }
  }
  return out;
}
"""

SELECT_VALUE_JS = """
(el) => {
  const root = el.closest('.ant-select, .el-select, [role=combobox]') || el;
  const placeholder = root.querySelector(
    '.ant-select-selection-placeholder, .el-select__placeholder, .ant-select-selection-item-remove'
  );
  const item = root.querySelector('.ant-select-selection-item, .el-select__selected-item');
  if (item && (item.textContent || '').trim()) return (item.textContent || '').trim();
  if (placeholder) return '';
  return (root.textContent || '').trim();
}
"""

SELECT_HAS_OPTIONS_JS = """
(root) => !!root.querySelector('.ant-select-item-option, .el-select-dropdown__item, [role=option]')
"""

COMBOBOX_ANCESTOR_JS = """
(el) => el && el.closest && el.closest('.ant-select, .el-select, [role=combobox]')
"""

MENU_ITEM_ANCESTOR_JS = "xpath=ancestor-or-self::li[contains(@class,'ant-menu-item')][1]"

CLICKABLE_ANCESTOR_XPATH = (
    "xpath=ancestor-or-self::*[self::button or self::a "
    "or contains(@class,'oio-action-item') "
    "or @role='button' or @role='menuitem'][1]"
)

SKIP_OPTION_LABELS = frozenset({"新增", "添加", "新建", "无数据", "暂无数据", "无匹配结果", "无匹配数据"})
PANEL_TAB = ".el-tabs__item:visible, [role=tab]:visible"
PANEL_TAG = (
    ".el-tab-pane[aria-hidden='false'] .sizeTag .el-tag .el-tag__content:visible, "
    ".el-tab-pane:visible .sizeTag .el-tag .el-tag__content:visible, "
    ".sizeTag .el-tag .el-tag__content:visible, "
    ".select-options .el-tag pre:visible, "
    ".select-options .el-tag .el-tag__content:visible"
)

SELECTED_OPTION_TOKENS = frozenset({"ant-select-item-option-selected", "selected", "is-selected"})

JS_FIELD_REQUIRED = """
(el) => {
  if (!el || !el.closest) return null;
  const item = el.closest('.ant-form-item, .el-form-item, .oio-form-item, [class*="form-item"], [data-name]');
  if (!item) return null;
  if (item.querySelector('[aria-required="true"], [required], .ant-form-item-required, .el-form-item-required, .is-required')) return true;
  const label = item.querySelector(
    'label, .ant-form-item-label, .el-form-item__label, .oio-form-item-label, [class*="form-item-label"]'
  );
  for (const node of [item, label]) {
    if (!node) continue;
    const cls = String(node.className || '');
    if (/\\b(ant-form-item-required|el-form-item-required|is-required)\\b/.test(cls)) return true;
  }
  if (label) {
    try {
      const star = (getComputedStyle(label, '::before').content || '')
        + (getComputedStyle(label, '::after').content || '');
      if (star.includes('*')) return true;
    } catch (err) {}
    if (/\\*/.test(label.innerText || '')) return true;
  }
  return false;
}
"""

JS_FIELD_REQUIRED_BY_NAME = """
(name) => {
  if (!name) return null;
  const items = document.querySelectorAll(
    '.ant-form-item, .el-form-item, .oio-form-item, [class*="form-item"], [data-name]'
  );
  const aliases = {
    brand: '品牌', basicProductType: '品类', productColors: '颜色',
    productSizes: '尺码', productSpecials: '特殊工艺', productCost: '成本', name: '名称',
  };
  const check = (item) => {
    if (item.querySelector('[aria-required="true"], [required], .ant-form-item-required, .el-form-item-required, .is-required')) return true;
    const label = item.querySelector(
      'label, .ant-form-item-label, .el-form-item__label, .oio-form-item-label, [class*="form-item-label"]'
    );
    for (const node of [item, label]) {
      if (!node) continue;
      const cls = String(node.className || '');
      if (/\\b(ant-form-item-required|el-form-item-required|is-required)\\b/.test(cls)) return true;
    }
    if (label) {
      try {
        const star = (getComputedStyle(label, '::before').content || '')
          + (getComputedStyle(label, '::after').content || '');
        if (star.includes('*')) return true;
      } catch (err) {}
      if (/\\*/.test(label.innerText || '')) return true;
    }
    return false;
  };
  for (const item of items) {
    const label = item.querySelector(
      'label, .ant-form-item-label, .el-form-item__label, .oio-form-item-label, [class*="form-item-label"]'
    );
    const named = item.getAttribute && item.getAttribute('data-name');
    const text = ((label && label.innerText) || aliases[named] || named || '')
      .replace(/\\*/g, '').trim().split('\\n')[0];
    if (text === name || text.startsWith(name)) return check(item);
  }
  return null;
}
"""

JS_SELECTED_CHOICE = """
(el) => {
  if (!el) return '';
  const root = el.closest('.ant-select, .el-select, [role=combobox]') || el;
  const placeholder = root.querySelector(
    '.ant-select-selection-placeholder, .el-select__placeholder, .ant-select-selection-item-remove'
  );
  const item = root.querySelector('.ant-select-selection-item, .el-select__selected-item');
  if (item && item !== placeholder) {
    const title = (item.getAttribute('title') || '').trim();
    const text = (item.innerText || '').trim().split('\\n')[0];
    if (title || text) return title || text;
  }
  return '';
}
"""

JS_INSPECT_PANEL = """
(el) => {
  if (!el) return { has_tags: false, has_color: false, has_options: false, has_add: false, has_input: false };
  const q = (sel) => !!el.querySelector(sel);
  const text = (el.innerText || '').slice(0, 800);
  return {
    has_tags: q('.sizeTag, .select-options .el-tag, .el-tag--plain, .el-tag--info'),
    has_color: q('.el-color-dropdown, .el-color-picker, .el-color-predefine, [class*="color-picker"]'),
    has_options: q('.ant-select-item-option, .el-select-dropdown__item, [role=option]'),
    has_add: /(?:^|\\n)\\s*(新增|添加|新建)\\s*(?:\\n|$)/.test(text) || q('[class*="add"], [class*="plus"]'),
    has_input: q('input:not([type=hidden]):not([type=checkbox]):not([type=radio])'),
  };
}
"""

PANEL_VISIBLE_DEFAULT = (
    ".ant-select-dropdown:visible, .el-select-dropdown:visible, .el-select__popper:visible, "
    ".el-popper.el-select__popper:visible, .ant-dropdown:visible, [role=listbox]:visible"
)

PANEL_VISIBLE_EL_SELECT = (
    ".el-select-dropdown:visible, .el-select__popper:visible, .el-popper.el-select__popper:visible"
)

OVERLAY_WAIT_VISIBLE = (
    ".ant-modal-wrap:visible, .ant-modal-content:visible, "
    ".oio-modal-wrapper:visible, [role=dialog]:visible, "
    ".el-dialog:visible, .el-overlay-dialog:visible, "
    ".ant-drawer-content:visible, .el-drawer:visible"
)

DROPDOWN_OPTION_MARKERS = ("ant-select-item-option", "el-select-dropdown__item")
SELECT_TRIGGER_MARKERS = ("el-select__wrapper", "ant-select-selector")
_EPHEMERAL_CSS_STATE = (
    "is-focused",
    "is-focus",
    "is-active",
    "is-hover",
    "is-selected",
    "is-disabled",
    "is-checked",
    "ant-select-open",
    "ant-select-focused",
    "ant-picker-focused",
)


def sanitize_css_selector(value: str) -> str:
    """去掉录制瞬间的状态 class（如 is-focused），避免回放时对不上。"""
    out = value
    for cls in _EPHEMERAL_CSS_STATE:
        out = out.replace(f".{cls}", "")
    out = re.sub(r"\.(?=[\s,>|]|$)", "", out)
    return out
DATE_PICKER_MARKERS = ("ant-picker-cell", "ant-picker-dropdown", "el-date-table", "el-date-editor")
PICKER_PANEL_VISIBLE = ".ant-picker-dropdown:visible, .el-picker-panel:visible"
DATE_PICKER_WIDGETS = frozenset({"ant-date-picker", "el-date-picker"})
DROPDOWN_WIDGETS = frozenset({"el-select", "ant-select", "combobox"})

# Oinone data-name → 界面中文名。录制/编译/观察者共用。
FIELD_LABELS: dict[str, str] = {
    "brand": "品牌",
    "basicProductType": "品类",
    "productColors": "颜色",
    "productSizes": "尺码",
    "productSpecials": "特殊工艺",
    "productCost": "成本",
    "name": "名称",
    "poNo": "PO号",
    "poNumber": "PO号",
    "customerOrderNo": "客户单号",
    "orderDate": "下单日期",
    "deliveryDate": "交货日期",
    "productionOrderNo": "生产单号",
    "launchDate": "上市日期",
    "factoryId": "生产工厂",
    "sewingLineId": "缝制线组",
    "customerId": "客户",
}


def field_label(name: str) -> str:
    return FIELD_LABELS.get(name, name)


def looks_like_dropdown_option(value: str) -> bool:
    return any(marker in value for marker in DROPDOWN_OPTION_MARKERS)


def looks_like_picker_date(value: str) -> bool:
    return any(marker in value for marker in DATE_PICKER_MARKERS)


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

