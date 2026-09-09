"""Oinone / Ant Design 导航特例。"""

from __future__ import annotations

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from autotest_adapters.oinone.selectors import SIDEBAR_MENU_ITEM, SIDEBAR_SUBMENU_TITLE


def click_sidebar_menu(page: Page, name: str, timeout_ms: int) -> bool:
    """侧栏：父级是 submenu-title，真正开页的是隐藏的 menuitem。

    父级「款式」和子项「款式」同名。text='款式' 会点到父级，子 ul 仍是 display:none，
    首页页签不会出现。这里先展开再点 li.ant-menu-item[title=名称]。

    纯分组项（如「生产」）只有 submenu-title、没有同名叶子项：只展开，不能
    再 fall through 用 text 点一次 title（会折叠）。下一步再点子项「生产单」。
    """
    item = page.locator(SIDEBAR_MENU_ITEM.format(name=name))
    title = page.locator(SIDEBAR_SUBMENU_TITLE).filter(
        has=page.locator(f'span[title="{name}"]')
    )
    has_item = item.count() > 0
    has_title = title.count() > 0
    if not has_item and not has_title:
        return False

    try:
        if has_item and item.first.is_visible():
            item.first.click(timeout=timeout_ms)
            return True
    except Exception:
        pass

    if has_title:
        header = title.first
        try:
            expanded = header.get_attribute("aria-expanded")
            if expanded != "true":
                header.click(timeout=timeout_ms)
                page.wait_for_timeout(150)
            if not has_item:
                return True
            item.first.wait_for(state="visible", timeout=timeout_ms)
            item.first.click(timeout=timeout_ms)
            return True
        except PlaywrightTimeout:
            return False
        except Exception:
            return False

    if has_item:
        try:
            item.first.click(timeout=timeout_ms)
            return True
        except Exception:
            return False
    return False
