"""Oinone / Ant Design 导航特例。"""

from __future__ import annotations

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from autotest_adapters.oinone.selectors import SIDEBAR_MENU_ITEM, SIDEBAR_SUBMENU_TITLE


def click_sidebar_menu(page: Page, name: str, timeout_ms: int) -> bool:
    """侧栏：父级是 submenu-title，真正开页的是隐藏的 menuitem。

    父级「款式」和子项「款式」同名。text='款式' 会点到父级，子 ul 仍是 display:none，
    首页页签不会出现。这里先展开再点 li.ant-menu-item[title=名称]。
    """
    item = page.locator(SIDEBAR_MENU_ITEM.format(name=name))
    title = page.locator(SIDEBAR_SUBMENU_TITLE).filter(
        has=page.locator(f'span[title="{name}"]')
    )
    if item.count() == 0 and title.count() == 0:
        return False

    try:
        if item.count() and item.first.is_visible():
            item.first.click(timeout=timeout_ms)
            return True
    except Exception:
        pass

    if title.count() == 0:
        return False

    header = title.first
    try:
        expanded = header.get_attribute("aria-expanded")
        if expanded != "true":
            header.click(timeout=timeout_ms)
        item.first.wait_for(state="visible", timeout=timeout_ms)
        item.first.click(timeout=timeout_ms)
        return True
    except PlaywrightTimeout:
        return False
    except Exception:
        return False
