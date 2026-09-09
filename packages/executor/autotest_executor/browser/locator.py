"""定位候选解析。

一个目标保存多个候选并按稳定性排序，回放时依次尝试。命中低稳定性候选
说明首选已经失效——用例还没坏，但已经在坏的路上，这个信号要报出来，
而不是等它彻底失败。

录制时会把点击所在层写进 target.scope。回放先在当前页活着的同类层里找
（下次页面 DOM 变了也不用旧 css），找不到再退回录到的 css，最后才全页搜。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeout

from autotest_protocol import Candidate, Target, learn_candidates
from autotest_protocol.dsl import candidate_key

from autotest_adapters.oinone.navigation import click_sidebar_menu as click_ant_sidebar_menu
from autotest_adapters.oinone.selectors import (
    DROPDOWN_OPTION,
    DROPDOWN_OPTION_ACTIVE,
    DROPDOWN_PANEL,
    DROPDOWN_SEARCH,
    DROPDOWN_SCROLL_HOLDER,
    DROPDOWN_VIRTUAL_HOLDER,
    FIELD_INPUT,
    LIVE_DROPDOWN,
    LIVE_MODAL,
    MODAL_VISIBLE,
    OPTION_BY_TITLE,
    PICKER_PANEL_VISIBLE,
    PANEL_TAB,
    PANEL_TAG,
    SELECTED_OPTION_TOKENS,
    SKIP_OPTION_LABELS,
    sanitize_css_selector,
)


@dataclass
class LocatorResolution:
    locator: Locator
    candidate: Candidate
    # 命中的候选在优先级序列里的位置，>0 表示首选已失效
    fallback_index: int
    tried: list[str]

    @property
    def drifted(self) -> bool:
        return self.fallback_index > 0


class TargetNotFound(Exception):
    def __init__(self, tried: list[str]) -> None:
        super().__init__("所有候选定位方式都未命中：" + "; ".join(tried))
        self.tried = tried


class LocatorMemory:
    """一次运行内记住哪些定位好用、哪些已经空等失败。

    流程 JSON 里仍按稳定性排序；第一次命中后把失效候选从步骤里删掉，
    并在 complete 时写回控制面，下次不会再从第一个废选择器空等 16 秒。
    """

    def __init__(self) -> None:
        self.good: dict[str, Candidate] = {}
        self.bad: set[str] = set()
        self.updates: list[dict] = []

    def order(self, target: Target) -> list[Candidate]:
        original = target.ordered()
        preferred: list[Candidate] = []
        unknown: list[Candidate] = []
        seen: set[str] = set()
        for candidate in original:
            key = candidate_key(candidate)
            if key in seen or key in self.bad:
                continue
            seen.add(key)
            if key in self.good:
                preferred.append(self.good[key])
            else:
                unknown.append(candidate)
        return preferred + unknown or original

    def remember(
        self, target: Target, winner: Candidate, failed: list[Candidate], step_id: str | None
    ) -> None:
        self.good[candidate_key(winner)] = winner
        for item in failed:
            self.bad.add(candidate_key(item))
        stale = [item for item in target.candidates if candidate_key(item) in self.bad]
        already_first = bool(
            target.candidates and candidate_key(target.candidates[0]) == candidate_key(winner)
        )
        if not stale and already_first:
            return
        learned = learn_candidates(target.candidates, winner, stale)
        target.candidates = learned
        if step_id:
            self.updates.append(
                {
                    "step_id": step_id,
                    "candidates": [item.model_dump() for item in learned],
                }
            )


def _role_name_exact(name: str | None) -> bool:
    if not name:
        return False
    stripped = name.strip()
    return stripped.isdigit() or len(stripped) <= 3


def _clean_header(text: str) -> str:
    return text.strip().split("\n")[0].replace("*", "").strip()


def _build_matrix(root: Page | Locator, candidate: Candidate) -> Locator:
    """颜色×尺码矩阵：按「表格标题 + 行颜色 + 列尺码」找输入框，不依赖 vxe 随机 id。"""
    if "|" not in candidate.value:
        raise TargetNotFound([f"matrix={candidate.value!r}"])
    row_label, col_label = candidate.value.split("|", 1)
    table_title = (candidate.name or "颜色尺码").strip()

    tables = root.locator("table, .vxe-table--body table, .el-table__body table")
    try:
        table_count = tables.count()
    except Exception:
        table_count = 0

    chosen = None
    for index in range(table_count):
        table = tables.nth(index)
        try:
            corner = _clean_header(table.locator("tr").first.locator("th, td").first.inner_text(timeout=500))
        except Exception:
            continue
        if table_title in corner or "颜色" in corner or "尺码" in corner:
            chosen = table
            break
    if chosen is None and table_count:
        chosen = tables.last

    if chosen is None:
        raise TargetNotFound([f"matrix={candidate.value!r}"])

    header_row = chosen.locator("thead tr, tr").first
    header_cells = header_row.locator("th, td")
    col_idx = None
    try:
        header_count = header_cells.count()
    except Exception:
        header_count = 0
    for index in range(header_count):
        try:
            text = _clean_header(header_cells.nth(index).inner_text(timeout=500))
        except Exception:
            continue
        if text == col_label:
            col_idx = index
            break
    if col_idx is None:
        raise TargetNotFound([f"matrix={candidate.value!r} col={col_label!r}"])

    body_rows = chosen.locator("tbody tr, tr")
    try:
        row_count = body_rows.count()
    except Exception:
        row_count = 0
    for index in range(row_count):
        row = body_rows.nth(index)
        try:
            row_text = _clean_header(row.locator("td, th").first.inner_text(timeout=500))
        except Exception:
            continue
        if row_text != row_label or row_text in {table_title, "合计"}:
            continue
        cell = row.locator("td, th").nth(col_idx)
        input_loc = cell.locator("input.vxe-input--inner, input:not([type=hidden]), textarea")
        try:
            if input_loc.count():
                return input_loc.first
        except Exception:
            continue
    raise TargetNotFound([f"matrix={candidate.value!r} row={row_label!r}"])


def _build(root: Page | Locator, candidate: Candidate) -> Locator:
    kind = candidate.kind
    if kind == "testid":
        return root.get_by_test_id(candidate.value)
    if kind == "matrix":
        return _build_matrix(root, candidate)
    if kind == "field":
        host = root.locator(f'[data-name="{candidate.value}"]')
        return host.locator(FIELD_INPUT)
    if kind == "role":
        if candidate.name:
            return root.get_by_role(
                candidate.value,
                name=candidate.name,
                exact=_role_name_exact(candidate.name),
            )  # type: ignore[arg-type]
        return root.get_by_role(candidate.value)  # type: ignore[arg-type]
    if kind == "label":
        return root.get_by_label(candidate.value)
    if kind == "placeholder":
        return root.get_by_placeholder(candidate.value)
    if kind == "text":
        return root.get_by_text(candidate.value, exact=True)
    if kind == "css":
        return root.locator(sanitize_css_selector(candidate.value))
    return root.locator(candidate.value)


def _try_root(page: Page, css: str) -> Locator | None:
    loc = page.locator(css)
    try:
        total = loc.count()
    except Exception:
        return None
    for index in range(total - 1, -1, -1):
        node = loc.nth(index)
        try:
            if node.is_visible():
                return node
        except Exception:
            continue
    return None


def _roots_for(page: Page, target: Target) -> list[Page | Locator]:
    """按步骤自己的层找。页面按钮不要先去下拉/弹窗里空等。"""
    kind = (target.scope.kind if target.scope else None) or "page"
    roots: list[Page | Locator] = []
    if kind == "dropdown":
        dropdown = _try_root(page, LIVE_DROPDOWN)
        if dropdown is not None:
            roots.append(dropdown)
        modal = _try_root(page, LIVE_MODAL)
        if modal is not None:
            roots.append(modal)
        roots.append(page)
        return roots
    if kind in {"modal", "drawer"}:
        modal = _try_root(page, LIVE_MODAL)
        if target.scope and target.scope.name:
            named = page.locator(LIVE_MODAL).filter(has_text=target.scope.name)
            picked = _try_root_locator(named)
            if picked is not None:
                roots.append(picked)
        if modal is not None:
            roots.append(modal)
        if target.scope and target.scope.css:
            recorded = _try_root(page, target.scope.css)
            if recorded is not None:
                roots.append(recorded)
        roots.append(page)
        return roots
    roots.append(page)
    return roots


def _try_root_locator(loc: Locator) -> Locator | None:
    try:
        total = loc.count()
    except Exception:
        return None
    for index in range(total - 1, -1, -1):
        node = loc.nth(index)
        try:
            if node.is_visible():
                return node
        except Exception:
            continue
    return None


def _immediately_visible(locator: Locator) -> bool:
    try:
        return locator.count() > 0 and locator.first.is_visible()
    except Exception:
        return False


def _locator_accepts_fill(locator: Locator, fill_value: str | None) -> bool:
    """fill 步骤不能落到无关的只读日期框上。"""
    if not fill_value:
        return True
    try:
        if not locator_is_readonly_picker(locator):
            return True
    except Exception:
        return True
    return parse_picker_value(fill_value) is not None


def resolve_target(
    page: Page,
    target: Target,
    timeout_ms: int = 5_000,
    memory: LocatorMemory | None = None,
    step_id: str | None = None,
    *,
    fill_value: str | None = None,
) -> LocatorResolution:
    original = target.ordered()
    ordered = memory.order(target) if memory is not None else original
    tried: list[str] = []
    failed: list[Candidate] = []
    roots = _roots_for(page, target)
    has_preferred = bool(memory and ordered and candidate_key(ordered[0]) in memory.good)

    def _hit(candidate: Candidate, locator: Locator, fallback_index: int) -> LocatorResolution:
        if memory is not None:
            memory.remember(target, candidate, failed, step_id)
        return LocatorResolution(
            locator=locator, candidate=candidate, fallback_index=fallback_index, tried=tried
        )

    # 已经在页面上的元素立刻点，不要让失效的首选空等数秒。
    for index, candidate in enumerate(ordered):
        description = candidate.describe()
        for root in roots:
            locator = _build(root, candidate).first
            if not _immediately_visible(locator):
                continue
            if not _locator_accepts_fill(locator, fill_value):
                tried.append(description + " (只读日期框，跳过)")
                failed.append(candidate)
                continue
            tried.append(description)
            original_index = next(
                (i for i, item in enumerate(original) if candidate_key(item) == candidate_key(candidate)),
                index,
            )
            if index > 0:
                failed.extend(ordered[:index])
                if memory is not None:
                    for item in failed:
                        memory.bad.add(candidate_key(item))
            return _hit(candidate, locator, original_index)

    for index, candidate in enumerate(ordered):
        description = candidate.describe()
        tried.append(description)
        wait_ms = _candidate_timeout(index, timeout_ms, len(ordered), has_preferred)
        matched = None
        for root_idx, root in enumerate(roots):
            try:
                locator = _build(root, candidate).first
                root_wait = _root_wait_ms(root_idx, len(roots), wait_ms)
                locator.wait_for(state="visible", timeout=root_wait)
            except Exception:
                continue
            if not _locator_accepts_fill(locator, fill_value):
                continue
            matched = locator
            break
        if matched is None:
            failed.append(candidate)
            if memory is not None:
                memory.bad.add(candidate_key(candidate))
            continue
        original_index = next(
            (i for i, item in enumerate(original) if candidate_key(item) == candidate_key(candidate)),
            index,
        )
        return _hit(candidate, matched, original_index)

    raise TargetNotFound(tried)


def _candidate_timeout(index: int, timeout_ms: int, count: int, has_preferred: bool) -> int:
    if has_preferred and index == 0:
        return timeout_ms
    if has_preferred:
        return max(250, min(500, timeout_ms))
    if index == 0:
        return min(timeout_ms, max(1_200, int(timeout_ms / max(1, count))))
    return max(250, min(600, int(timeout_ms / max(1, count))))


def _root_wait_ms(root_index: int, root_count: int, wait_ms: int) -> int:
    """弹窗步骤会在「命名弹窗 → 通用弹窗 → 录制 css → 整页」里依次试。

    若每个 root 都等满 wait_ms，一次失效候选就会空等 4× 预算（常见 20s+）。
    只在首选 root 上等足，其余 root 做短探测。
    """
    if root_count <= 1:
        return wait_ms
    tail = min(400, max(200, wait_ms // max(2, root_count)))
    if root_index == 0:
        return max(400, wait_ms - tail * (root_count - 1))
    return tail


_DROPDOWN_PANEL = DROPDOWN_PANEL
_DROPDOWN_SEARCH = DROPDOWN_SEARCH
_DROPDOWN_OPTION = DROPDOWN_OPTION
_SKIP_OPTION_LABELS = SKIP_OPTION_LABELS
_PANEL_TAB = PANEL_TAB
_PANEL_TAG = PANEL_TAG


def _visible_dropdown_panel(page: Page):
    dropdown = page.locator(_DROPDOWN_PANEL)
    try:
        if dropdown.count() == 0:
            return None
        return dropdown.last
    except Exception:
        return None


def visible_dropdown_panel(page: Page):
    """当前可见的下拉面板。已打开就不要再点触发器，Ant 下拉会点一下关一下。"""
    return _visible_dropdown_panel(page)


def _dropdown_search_box(page: Page):
    search = page.locator(_DROPDOWN_SEARCH)
    try:
        total = search.count()
    except Exception:
        return None
    if total == 0:
        return None
    for index in range(total):
        box = search.nth(index)
        try:
            if box.is_visible():
                return box
        except Exception:
            continue
    # 已打开的 Ant 下拉搜索框经常宽为 0，is_visible 为假，但里面还留着已选文案，会把列表滤成一项
    try:
        return search.last
    except Exception:
        return None


def _panel_has_options(panel) -> bool:
    try:
        return panel.locator(_DROPDOWN_OPTION).count() > 0
    except Exception:
        return False


def _fill_dropdown_search(page: Page, panel, name: str, timeout_ms: int) -> None:
    """主数据下拉能搜就输入过滤。标签面板里的「请输入」是新建框，不能当搜索。"""
    has_size_tags = False
    try:
        has_size_tags = panel.locator(".sizeTag .el-tag:visible").count() > 0
    except Exception:
        has_size_tags = False
    if has_size_tags:
        return
    box = _dropdown_search_box(page)
    if box is None:
        return
    try:
        placeholder = box.get_attribute("placeholder") or ""
        looks_create = "请输入" in placeholder and not _panel_has_options(panel)
        if looks_create:
            return
        box.fill(name, timeout=min(2_000, timeout_ms))
        page.wait_for_timeout(200)
    except Exception:
        pass


def clear_dropdown_search(page: Page) -> None:
    """打开后搜索框常带着已选值，远程/本地过滤会只剩这一条。必须清掉再等列表回来。"""
    loc = page.locator(_DROPDOWN_SEARCH)
    try:
        total = loc.count()
    except Exception:
        total = 0
    for index in range(total):
        box = loc.nth(index)
        try:
            box.fill("", force=True, timeout=800)
        except Exception:
            try:
                box.press("Control+A")
                box.press("Backspace")
            except Exception:
                continue
    try:
        page.wait_for_timeout(350)
        page.locator(_DROPDOWN_OPTION).first.wait_for(state="attached", timeout=2_000)
    except Exception:
        pass


def _option_label(item) -> str:
    try:
        title = (item.get_attribute("title") or "").strip()
    except Exception:
        title = ""
    try:
        text = ((item.inner_text(timeout=400) or "").strip().split("\n") or [""])[0].strip()
    except Exception:
        text = ""
    return title or text


def _is_selected_option(item) -> bool:
    try:
        cls = item.get_attribute("class") or ""
        tokens = cls.split()
        if any(token in tokens for token in SELECTED_OPTION_TOKENS):
            return True
        if (item.get_attribute("aria-selected") or "").lower() == "true":
            return True
    except Exception:
        return False
    return False


_DATE_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME_VALUE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})(?:[ T](?P<time>\d{1,2}:\d{2}(?::\d{2})?))?$"
)

_JS_IS_READONLY_PICKER = """
(el) => {
  if (!el) return false;
  const input = el.matches('input') ? el : el.querySelector('input');
  if (!input) return false;
  if (!input.readOnly && !input.hasAttribute('readonly')) return false;
  return !!(input.closest('.ant-picker, .el-date-editor'));
}
"""

_JS_ANT_PICKER_YM = """
(panel) => {
  const yearBtn = panel.querySelector('.ant-picker-year-btn');
  const monthBtn = panel.querySelector('.ant-picker-month-btn');
  if (!yearBtn || !monthBtn) return null;
  const year = parseInt((yearBtn.textContent || '').replace(/\\D/g, ''), 10);
  const month = parseInt((monthBtn.textContent || '').replace(/\\D/g, ''), 10);
  if (!year || !month) return null;
  return { year, month };
}
"""


def parse_picker_value(value: str) -> tuple[str, str | None] | None:
    """解析日期/日期时间字符串，供 Ant DatePicker 回放。"""
    raw = (value or "").strip()
    if _DATE_ISO.fullmatch(raw):
        return raw, None
    match = _DATETIME_VALUE.fullmatch(raw)
    if match:
        time_part = match.group("time")
        if time_part and len(time_part.split(":")) == 2:
            time_part = f"{time_part}:00"
        return match.group("date"), time_part
    return None


def locator_is_readonly_picker(locator: Locator) -> bool:
    try:
        return bool(locator.evaluate(_JS_IS_READONLY_PICKER))
    except Exception:
        return False


def _open_ant_picker(
    page: Page,
    *,
    trigger_css: str | None,
    field: str | None,
    input_locator: Locator | None = None,
    timeout_ms: int,
) -> None:
    if input_locator is not None:
        input_locator.click(timeout=timeout_ms)
        return
    if trigger_css:
        page.locator(trigger_css).last.click(timeout=timeout_ms)
        return
    if field:
        for sel in (
            f'[data-name="{field}"] .ant-picker-input input',
            f'[data-name="{field}"] .ant-picker',
        ):
            loc = page.locator(sel)
            try:
                if loc.count():
                    loc.last.click(timeout=timeout_ms)
                    return
            except Exception:
                continue
    modal = page.locator(MODAL_VISIBLE)
    root = modal.last if modal.count() else page
    for sel in (
        ".ant-picker-focused .ant-picker-input input",
        ".ant-picker .ant-picker-input input",
    ):
        loc = root.locator(sel)
        try:
            if loc.count():
                loc.last.click(timeout=timeout_ms)
                return
        except Exception:
            continue


def _pick_date_on_panel(
    panel: Locator,
    page: Page,
    date_str: str,
    *,
    timeout_ms: int,
) -> bool:
    target = datetime.strptime(date_str, "%Y-%m-%d").date()
    for _ in range(40):
        cell = panel.locator(
            f'td.ant-picker-cell[title="{date_str}"]:not(.ant-picker-cell-disabled)'
        )
        try:
            if cell.count() and cell.first.is_visible():
                cell.first.click(timeout=min(2_000, timeout_ms))
                page.wait_for_timeout(120)
                return True
        except Exception:
            pass
        ym = panel.evaluate(_JS_ANT_PICKER_YM)
        if not ym:
            break
        current = (int(ym["year"]), int(ym["month"]))
        goal = (target.year, target.month)
        if current == goal:
            break
        btn = (
            ".ant-picker-header-next-btn"
            if current < goal
            else ".ant-picker-header-prev-btn"
        )
        try:
            panel.locator(btn).click(timeout=min(1_500, timeout_ms))
            page.wait_for_timeout(80)
        except Exception:
            break
    return False


def _set_ant_picker_time(
    panel: Locator,
    page: Page,
    time_str: str,
    *,
    timeout_ms: int,
) -> None:
    parts = time_str.split(":")
    tokens = [
        parts[0].zfill(2),
        parts[1].zfill(2) if len(parts) > 1 else "00",
        parts[2].zfill(2) if len(parts) > 2 else "00",
    ]
    for idx, val in enumerate(tokens):
        col = panel.locator(".ant-picker-time-panel-column").nth(idx)
        try:
            if not col.count():
                continue
            cell = col.locator(f'.ant-picker-time-panel-cell-inner:text-is("{val}")')
            if cell.count():
                cell.first.click(timeout=min(1_000, timeout_ms))
        except Exception:
            continue
    page.wait_for_timeout(80)


def _confirm_ant_picker(panel: Locator, page: Page, *, timeout_ms: int) -> None:
    ok = panel.locator(".ant-picker-ok")
    try:
        if ok.count() and ok.first.is_visible():
            ok.first.click(timeout=min(2_000, timeout_ms))
            page.wait_for_timeout(120)
    except Exception:
        pass


def pick_ant_picker_value(
    page: Page,
    value: str,
    *,
    trigger_css: str | None = None,
    field: str | None = None,
    input_locator: Locator | None = None,
    timeout_ms: int = 8_000,
) -> bool:
    """Ant Design 日期/日期时间控件：readonly 输入框不能 fill，走面板选值。"""
    parsed = parse_picker_value(value)
    if not parsed:
        return False
    date_str, time_str = parsed
    panel_loc = page.locator(PICKER_PANEL_VISIBLE)
    if panel_loc.count() == 0:
        _open_ant_picker(
            page,
            trigger_css=trigger_css,
            field=field,
            input_locator=input_locator,
            timeout_ms=timeout_ms,
        )
        panel_loc = page.locator(PICKER_PANEL_VISIBLE)
        try:
            panel_loc.last.wait_for(state="visible", timeout=min(3_000, timeout_ms))
        except PlaywrightTimeout:
            return False
    panel = panel_loc.last
    if not _pick_date_on_panel(panel, page, date_str, timeout_ms=timeout_ms):
        return False
    has_time_panel = panel.locator(".ant-picker-time-panel").count() > 0
    if time_str or has_time_panel:
        if time_str:
            _set_ant_picker_time(panel, page, time_str, timeout_ms=timeout_ms)
        _confirm_ant_picker(panel, page, timeout_ms=timeout_ms)
    return True


def pick_ant_date(
    page: Page,
    date_str: str,
    *,
    trigger_css: str | None = None,
    field: str | None = None,
    timeout_ms: int = 8_000,
) -> bool:
    """在 Ant Design 日期面板里选中指定日期（YYYY-MM-DD）。"""
    return pick_ant_picker_value(
        page,
        date_str,
        trigger_css=trigger_css,
        field=field,
        timeout_ms=timeout_ms,
    )


def pick_dropdown_option(page: Page, name: str, timeout_ms: int = 8_000) -> str | None:
    """在已打开的 Ant / Element 下拉里选出一项。

    虚拟列表不会一次渲染全部选项，录制时的滚轮不能回放。
    能搜就输入过滤，否则在列表里滚动直到该项出现。
    """
    if not name:
        return None
    panel = _visible_dropdown_panel(page)
    if panel is None:
        return None

    _fill_dropdown_search(page, panel, name, timeout_ms)

    option = panel.locator(
        OPTION_BY_TITLE.format(name=name) + f', .el-select-dropdown__item:text-is("{name}")'
    )
    size_tag = panel.locator(
        ".el-tab-pane[aria-hidden='false'] .sizeTag .el-tag .el-tag__content, "
        ".el-tab-pane:visible .sizeTag .el-tag .el-tag__content"
    ).get_by_text(name, exact=True)
    tag = panel.locator(".select-options .el-tag pre, .select-options .el-tag .el-tag__content").get_by_text(
        name, exact=True
    )
    by_text = panel.get_by_text(name, exact=True)
    holder = panel.locator(DROPDOWN_SCROLL_HOLDER)

    deadline = timeout_ms
    steps = max(8, int(deadline / 150))
    for _ in range(steps):
        for loc in (size_tag, tag, option, by_text):
            try:
                if loc.count() and loc.first.is_visible():
                    loc.first.scroll_into_view_if_needed(timeout=800)
                    loc.first.click(timeout=min(2_000, timeout_ms))
                    return name
            except Exception:
                continue
        try:
            if holder.count():
                holder.last.evaluate("(el) => { el.scrollTop += Math.max(80, el.clientHeight - 20); }")
            else:
                panel.evaluate("(el) => { el.scrollTop += 80; }")
        except Exception:
            break
        page.wait_for_timeout(80)
    return None


def _scan_dropdown_options(panel, skip_norm: set[str], skip_selected: bool, timeout_ms: int) -> str | None:
    loc = panel.locator(_DROPDOWN_OPTION)
    try:
        total = loc.count()
    except Exception:
        return None
    for index in range(total):
        item = loc.nth(index)
        try:
            if not item.is_visible():
                continue
            if skip_selected and _is_selected_option(item):
                continue
            label = _option_label(item)
            if not label or label in _SKIP_OPTION_LABELS or label in skip_norm:
                continue
            item.scroll_into_view_if_needed(timeout=800)
            item.click(timeout=min(2_000, timeout_ms))
            return label
        except Exception:
            continue
    return None


def _pick_next_by_keyboard(page: Page, skip_norm: set[str]) -> str | None:
    """虚拟列表扫不到时，从当前高亮往下翻一条。"""
    try:
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(120)
    except Exception:
        return None
    active = page.locator(DROPDOWN_OPTION_ACTIVE)
    label = ""
    try:
        if active.count():
            label = _option_label(active.last)
    except Exception:
        label = ""
    if label in skip_norm or label in _SKIP_OPTION_LABELS:
        try:
            page.keyboard.press("ArrowDown")
            page.wait_for_timeout(120)
            if active.count():
                label = _option_label(active.last)
        except Exception:
            pass
    if not label or label in skip_norm or label in _SKIP_OPTION_LABELS:
        return None
    try:
        page.keyboard.press("Enter")
    except Exception:
        return None
    return label


def _click_first_match(loc, skip_norm: set[str], timeout_ms: int) -> str | None:
    try:
        total = loc.count()
    except Exception:
        return None
    for index in range(total):
        item = loc.nth(index)
        try:
            if not item.is_visible():
                continue
            cls = item.get_attribute("class") or ""
            if "is-disabled" in cls.split() or "disabled" in cls.split():
                continue
            label = (item.inner_text(timeout=400) or "").strip().split("\n")[0].strip()
            if not label or label in _SKIP_OPTION_LABELS or label in skip_norm:
                continue
            item.scroll_into_view_if_needed(timeout=800)
            item.click(timeout=min(2_000, timeout_ms))
            return label
        except Exception:
            continue
    return None


def pick_any_panel_choice(
    page: Page,
    *,
    kind: str = "any",
    skip: list[str] | tuple[str, ...] | set[str] | None = None,
    timeout_ms: int = 3_000,
) -> str | None:
    """当前下拉/尺码面板里随便点一项：tab、尺码标签或普通选项。"""
    panel = _visible_dropdown_panel(page)
    if panel is None:
        return None
    skip_norm = {str(item).strip() for item in (skip or []) if item and str(item).strip()}
    if kind == "tab":
        picked = _click_first_match(panel.locator(_PANEL_TAB), skip_norm, timeout_ms)
        if picked:
            try:
                page.wait_for_timeout(200)
            except Exception:
                pass
        return picked
    if kind in {"tag", "any"}:
        picked = _click_first_match(panel.locator(_PANEL_TAG), skip_norm, timeout_ms)
        if picked:
            return picked
    if kind in {"any", "option"}:
        picked = pick_first_dropdown_option(page, skip=skip_norm, timeout_ms=timeout_ms)
        if picked:
            return picked
    if kind == "any":
        picked = _click_first_match(panel.locator(_PANEL_TAB), skip_norm, timeout_ms)
        if picked:
            try:
                page.wait_for_timeout(200)
            except Exception:
                pass
            return picked
    return None


def pick_first_dropdown_option(
    page: Page,
    *,
    skip: list[str] | tuple[str, ...] | set[str] | None = None,
    skip_selected: bool = False,
    timeout_ms: int = 3_000,
) -> str | None:
    """清掉搜索过滤后，点第一条可用选项。编辑时跳过已选项，必要时滚虚拟列表。"""
    panel = _visible_dropdown_panel(page)
    if panel is None:
        return None
    clear_dropdown_search(page)
    panel = _visible_dropdown_panel(page) or panel
    skip_norm = {str(item).strip() for item in (skip or []) if item and str(item).strip()}
    holder = panel.locator(DROPDOWN_VIRTUAL_HOLDER)
    steps = max(6, int(timeout_ms / 150))
    for _ in range(steps):
        picked = _scan_dropdown_options(panel, skip_norm, skip_selected, timeout_ms)
        if picked:
            return picked
        try:
            if holder.count():
                holder.last.evaluate("(el) => { el.scrollTop += Math.max(80, el.clientHeight - 20); }")
            else:
                panel.evaluate("(el) => { el.scrollTop += 80; }")
        except Exception:
            break
        page.wait_for_timeout(80)
    if skip_selected:
        return _pick_next_by_keyboard(page, skip_norm)
    return _click_first_match(panel.locator(_PANEL_TAG), skip_norm, timeout_ms)


class TargetStillVisible(Exception):
    def __init__(self, tried: list[str]) -> None:
        super().__init__("元素在超时前始终没有消失：" + "; ".join(tried))
        self.tried = tried


def wait_target_hidden(page: Page, target: Target, timeout_ms: int = 10_000) -> str:
    """等待元素消失。

    「消失」是很多流程的真实成功信号：登录表单不见了、加载遮罩退了。
    比等某个新元素出现更可靠——新页面长什么样往往因权限和数据而异。
    """
    ordered = target.ordered()
    tried: list[str] = []
    per_candidate_timeout = max(500, int(timeout_ms / max(1, len(ordered))))

    for candidate in ordered:
        tried.append(candidate.describe())
        locator = _build(page, candidate).first
        try:
            locator.wait_for(state="hidden", timeout=per_candidate_timeout)
        except Exception:
            continue
        return candidate.describe()

    raise TargetStillVisible(tried)
