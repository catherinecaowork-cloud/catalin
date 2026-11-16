"""定位候选解析。

一个目标保存多个候选并按稳定性排序，回放时依次尝试。命中低稳定性候选
说明首选已经失效——用例还没坏，但已经在坏的路上，这个信号要报出来，
而不是等它彻底失败。

录制时会把点击所在层写进 target.scope。回放先在当前页活着的同类层里找
（下次页面 DOM 变了也不用旧 css），找不到再退回录到的 css，最后才全页搜。
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime

from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeout

from autotest_protocol import Candidate, Target, learn_candidates
from autotest_protocol.dsl import candidate_key

# 本模块不使用，转出给 browser.actions——它是浏览器层对适配器的唯一入口
from autotest_adapters.oinone.navigation import (  # noqa: F401
    click_sidebar_menu as click_ant_sidebar_menu,
)
from autotest_adapters.oinone.selectors import (
    FIELD_INPUT,
    LIVE_MODAL,
    MODAL_VISIBLE,
    PANEL_TAB,
    PANEL_TAG,
    SELECTED_OPTION_TOKENS,
    SKIP_OPTION_LABELS,
    sanitize_css_selector,
)
from autotest_executor.ui_selectors import (
    DROPDOWN_OPTION,
    DROPDOWN_OPTION_ACTIVE,
    DROPDOWN_PANEL,
    DROPDOWN_SEARCH,
    DROPDOWN_SCROLL_HOLDER,
    DROPDOWN_VIRTUAL_HOLDER,
    LIVE_DROPDOWN,
    OPTION_BY_TITLE,
    PICKER_PANEL_VISIBLE,
)
from autotest_executor.browser.visibility import (
    _VISIBILITY_PROBE_LIMIT,  # noqa: F401 - 测试与对外兼容再导出
    first_visible as _first_visible,
    wait_any_dropdown_panel,  # noqa: F401 - actions / selftest 从本模块导入
    wait_first_visible as _wait_first_visible,
    wait_visible_dropdown_panel,  # noqa: F401
    visible_dropdown_panel,
)

_visible_dropdown_panel = visible_dropdown_panel


class IframeNotSupported(RuntimeError):
    """目标位于 iframe 内。

    平台明确不支持跨 frame 定位；发现目标只在子 frame 里时立刻报不支持，
    而不是空等到超时再伪装成偶发 TargetNotFound。
    """


class FailureKind:
    """一个候选没被选中的原因。只有 TARGET_CHANGED 能证明候选本身失效。"""

    # 容器在，候选就是没命中——目标确实变了
    TARGET_CHANGED = "target_changed"
    # 目标录在浮层里，但这次那个浮层压根没出现。容器不在，证伪不了候选
    OVERLAY_ABSENT = "overlay_absent"
    # 找到了，但动作做不下去（被遮挡 / 不可点）
    COVERED = "covered"
    # 等超时
    TIMEOUT = "timeout"


# 环境原因：候选本身没被证伪。一旦进了 LocatorMemory.bad，下一次就会把好候选
# 从脚本里删掉——缺陷会随时间反向污染已录资产，这比当次失败严重得多。
ENVIRONMENTAL_KINDS = frozenset(
    {FailureKind.OVERLAY_ABSENT, FailureKind.COVERED, FailureKind.TIMEOUT}
)

_ENVIRONMENTAL_NOTES = {
    FailureKind.OVERLAY_ABSENT: "目标所在浮层未出现",
    FailureKind.COVERED: "目标被遮挡或点不动",
    FailureKind.TIMEOUT: "等待超时",
}


@dataclass(frozen=True)
class CandidateFailure:
    """一次候选失败，带上原因。判定失效与报失败都读它。"""

    candidate: Candidate
    kind: str = FailureKind.TARGET_CHANGED

    @property
    def environmental(self) -> bool:
        return self.kind in ENVIRONMENTAL_KINDS


@dataclass
class LocatorResolution:
    locator: Locator
    candidate: Candidate
    # 命中的候选在优先级序列里的位置，>0 表示退到了后顺位
    fallback_index: int
    tried: list[str]
    # 本轮失败的候选与原因（含被 skip 的）。报漂移、报失败都读它——
    # 只看 fallback_index 会把「首选点不到」与「首选真失效」说成同一件事。
    failed: list[CandidateFailure] = field(default_factory=list)

    @property
    def drifted(self) -> bool:
        return self.fallback_index > 0

    @property
    def environmental(self) -> bool:
        """本轮失败是否**全**为环境原因（浮层没出现 / 被遮挡 / 超时）。

        为真时 drifted 的命中只是退到兜底撞上的，报「首选失效」就是假警报。
        failed 为空（靠 memory 记住的好候选直接命中）不算环境原因——那是真漂移。
        """
        return bool(self.failed) and all(item.environmental for item in self.failed)

    @property
    def drift_note(self) -> str:
        """回退命中的说明。环境原因时点明是哪一种，否则按定位漂移报。"""
        if self.candidate.kind == "fingerprint":
            return "定位自愈：候选全部失效，按语义指纹找回"
        if not self.environmental:
            return "定位漂移：首选候选失效"
        kinds = list(dict.fromkeys(item.kind for item in self.failed))
        notes = "；".join(_ENVIRONMENTAL_NOTES.get(kind, kind) for kind in kinds)
        return f"环境原因回退（{notes}，未判首选失效）"


class TargetNotFound(Exception):
    def __init__(self, tried: list[str], kind: str = FailureKind.TARGET_CHANGED) -> None:
        self.tried = tried
        self.kind = kind
        # 环境原因与「脚本坏了」在报告里必须分开。混成同一句，运维会去改本来没问题的候选。
        head = (
            "目标所在浮层这次没有出现，未在其中找到元素"
            if kind in ENVIRONMENTAL_KINDS
            else "所有候选定位方式都未命中"
        )
        super().__init__(head + "：" + "; ".join(tried))


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
        self,
        target: Target,
        winner: Candidate,
        failed: list[CandidateFailure],
        step_id: str | None,
    ) -> None:
        self.good[candidate_key(winner)] = winner
        # 只有「目标确实变化」才判候选失效。浮层没打开 / 被遮挡 / 超时都说明不了候选
        # 本身有问题，写进 bad 就会在下面被当成 stale 删掉，并写回控制面生成修补任务。
        judged = [item for item in failed if not item.environmental]
        for item in judged:
            self.bad.add(candidate_key(item.candidate))
        if failed and not judged:
            # 这一轮失败全是环境原因：既不能判失效，也不能据此改写首选。
            # 环境原因下的命中往往只是退到 page 兜底撞上的，把它升为首选等于用一次
            # 环境抖动改写脚本——比不修更糟。
            return
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


_OVERLAY_SCOPES = frozenset({"dropdown", "modal", "drawer"})


def _overlay_absent(target: Target, roots: list[Page | Locator]) -> bool:
    """目标录在浮层里，但这次回放那个浮层根本没出现。

    `_roots_for` 找不到浮层时只留一个 page 兜底，所以 roots 只剩一项就是「层没找到」。
    此时候选没命中证明不了它失效——它要待的容器压根不在，属环境原因。

    刻意偏向「误判成环境原因」：浮层动画未完成时 `_try_root` 可能快照不到，那也只是
    这一轮不判候选失效，下一轮照常；反过来误判成漂移则会真的删掉好候选。
    """
    kind = (target.scope.kind if target.scope else None) or "page"
    return kind in _OVERLAY_SCOPES and len(roots) <= 1


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


# 指纹命中阈值：相似度够高、且明显领先第二名，才算认准。
# 宁可失败报出来，也不把值填到「长得像」的别的控件里。
FINGERPRINT_MIN_SCORE = 0.62
FINGERPRINT_MIN_MARGIN = 0.12


def _fingerprint_summary(element: dict | None) -> str:
    element = element or {}
    parts = [str(element.get("tag") or "element")]
    for key, label in (("label", "标签"), ("text", "文本"), ("grid", "坐标")):
        value = element.get(key)
        if value:
            parts.append(f"{label}={value}")
    return " ".join(parts)


def resolve_by_fingerprint(
    page: Page,
    target: Target,
    timeout_ms: int = 1_500,
    *,
    fallback_index: int = 0,
) -> tuple[LocatorResolution | None, list[str]]:
    """候选全失效时的通用退路：在实时 DOM 里按语义指纹找最像的元素。

    不依赖任何站点框架，也不需要为新控件加候选类型。返回命中结果与诊断说明；
    诊断说明无论成败都写进 tried，失败时能看出「最像的是谁、差多少」。
    """
    fingerprint = target.fingerprint
    notes: list[str] = []
    if fingerprint is None or fingerprint.is_empty():
        return None, notes
    payload = fingerprint.model_dump()
    deadline = time.monotonic() + max(0.2, timeout_ms / 1000)
    best_report: dict | None = None
    while True:
        try:
            result = page.evaluate(
                "([fp]) => (window.__atpFindByFingerprint"
                " ? window.__atpFindByFingerprint(fp) : {ok: false, reason: 'no fn'})",
                [payload],
            )
        except Exception as exc:  # noqa: BLE001
            notes.append(f"fingerprint 评估失败：{type(exc).__name__}")
            return None, notes
        if isinstance(result, dict) and result.get("reason") == "no fn":
            # 注入丢了：这时说「不够像」会把人带偏，直接点明缺脚本。
            notes.append("页面未注入 locator_candidates.js，指纹解析不可用")
            return None, notes
        if isinstance(result, dict) and result.get("ok"):
            score = float(result.get("score") or 0)
            second = float(result.get("second") or 0)
            if score >= FINGERPRINT_MIN_SCORE and (score - second) >= FINGERPRINT_MIN_MARGIN:
                try:
                    locator = page.locator(str(result.get("path") or "")).first
                    if (
                        locator.count()
                        and locator.get_attribute("data-atp-hit") == str(result.get("token") or "")
                    ):
                        summary = _fingerprint_summary(result.get("element"))
                        # 路径不依赖临时属性，认证完就清掉，避免污染页面 DOM。
                        locator.evaluate("(el) => el.removeAttribute('data-atp-hit')")
                        return (
                            LocatorResolution(
                                locator=locator,
                                candidate=Candidate(
                                    kind="fingerprint",
                                    value=f"{summary}（相似度 {score:.2f}，次高 {second:.2f}）",
                                ),
                                fallback_index=fallback_index,
                                tried=[],
                                failed=[],
                            ),
                            notes,
                        )
                    notes.append("fingerprint 命中后核对失败：元素已被重绘")
                except Exception as exc:  # noqa: BLE001
                    notes.append(f"fingerprint 命中后定位失败：{type(exc).__name__}")
            else:
                best_report = result
        elif isinstance(result, dict):
            best_report = result if result.get("matches") else best_report
        if time.monotonic() >= deadline:
            break
        page.wait_for_timeout(150)
    if best_report:
        matches = best_report.get("matches") or []
        head = "；".join(
            f"{item.get('label') or item.get('text') or item.get('tag')} {item.get('score')}"
            for item in matches[:3]
        )
        notes.append(
            f"fingerprint 未达阈值（{FINGERPRINT_MIN_SCORE}），最像的：{head or '无'}"
        )
    else:
        notes.append("fingerprint 未找到足够相似的元素")
    return None, notes


def resolve_target(
    page: Page,
    target: Target,
    timeout_ms: int = 5_000,
    memory: LocatorMemory | None = None,
    step_id: str | None = None,
    *,
    fill_value: str | None = None,
    skip: dict[str, str] | None = None,
) -> LocatorResolution:
    original = target.ordered()
    ordered = memory.order(target) if memory is not None else original
    tried: list[str] = []
    failed: list[CandidateFailure] = []
    seen_failed: set[str] = set()
    # 解析之外已经失败的候选（点不到）与原因。它们不能被返回，但要按原因记账——
    # 调用方知道得比这里多，所以以调用方给的为准。
    skipped = skip or {}
    roots = _roots_for(page, target)
    # 浮层没出现时，这一轮的失败一律按环境原因记：容器不在，证伪不了任何候选。
    failure_kind = (
        FailureKind.OVERLAY_ABSENT if _overlay_absent(target, roots) else FailureKind.TARGET_CHANGED
    )
    has_preferred = bool(memory and ordered and candidate_key(ordered[0]) in memory.good)

    def _failed(candidate: Candidate) -> CandidateFailure:
        return CandidateFailure(candidate, skipped.get(candidate_key(candidate), failure_kind))

    def _record(candidate: Candidate) -> None:
        """一个候选只记一次，且以最先给出的原因为准。"""
        key = candidate_key(candidate)
        if key in seen_failed:
            return
        seen_failed.add(key)
        failed.append(_failed(candidate))

    def _hit(candidate: Candidate, locator: Locator, fallback_index: int) -> LocatorResolution:
        if memory is not None:
            memory.remember(target, candidate, failed, step_id)
        return LocatorResolution(
            locator=locator,
            candidate=candidate,
            fallback_index=fallback_index,
            tried=tried,
            failed=list(failed),
        )

    # 无名 role 候选（role=textbox 但不知道是哪个）会命中的是「页面上第一个同类元素」。
    # 有指纹的流程不需要它：留着它只会抢在指纹之前把值填到别的控件里，还报通过。
    untrusted_role = bool(target.fingerprint)

    # 指纹优先：它是语义匹配 + 双阈值，比录制时那条结构/类名路径更抗改版。
    # 命中不到（指纹不够像）再走候选，候选顺序与旧流程完全一致。
    fp_notes: list[str] = []
    if target.fingerprint is not None:
        fingerprint_hit, fp_notes = resolve_by_fingerprint(
            page, target, timeout_ms=min(1_000, timeout_ms), fallback_index=0
        )
        if fingerprint_hit is not None:
            fingerprint_hit.tried = list(fp_notes)
            return fingerprint_hit

    # 已经在页面上的元素立刻点，不要让失效的首选空等数秒。
    for index, candidate in enumerate(ordered):
        description = candidate.describe()
        if untrusted_role and candidate.kind == "role" and not candidate.name:
            tried.append(description + " (无名 role 不可信，有指纹时跳过)")
            _record(candidate)
            continue
        if candidate_key(candidate) in skipped:
            tried.append(description + " (已试过，点不动)")
            _record(candidate)
            continue
        for root in roots:
            locator = _first_visible(_build(root, candidate))
            if locator is None:
                continue
            if not _locator_accepts_fill(locator, fill_value):
                tried.append(description + " (只读日期框，跳过)")
                _record(candidate)
                continue
            tried.append(description)
            original_index = next(
                (i for i, item in enumerate(original) if candidate_key(item) == candidate_key(candidate)),
                index,
            )
            if index > 0:
                # 前面的候选按同一原因记；进不进 bad 由 remember 按 environmental 判
                for item in ordered[:index]:
                    _record(item)
            return _hit(candidate, locator, original_index)

    for index, candidate in enumerate(ordered):
        description = candidate.describe()
        if untrusted_role and candidate.kind == "role" and not candidate.name:
            tried.append(description + " (无名 role 不可信，有指纹时跳过)")
            _record(candidate)
            continue
        if candidate_key(candidate) in skipped:
            tried.append(description + " (已试过，点不动)")
            _record(candidate)
            continue
        tried.append(description)
        wait_ms = _candidate_timeout(index, timeout_ms, len(ordered), has_preferred)
        matched = None
        for root_idx, root in enumerate(roots):
            root_wait = _root_wait_ms(root_idx, len(roots), wait_ms)
            matched = _wait_first_visible(_build(root, candidate), root_wait)
            if matched is None:
                continue
            if not _locator_accepts_fill(matched, fill_value):
                continue
            break
        if matched is None:
            # 全部候选都没命中时 remember 不会被调用，这里得自己落一次；
            # 但同样只认「目标确实变化」，环境原因不写。
            if memory is not None and not _failed(candidate).environmental:
                memory.bad.add(candidate_key(candidate))
            _record(candidate)
            continue
        original_index = next(
            (i for i, item in enumerate(original) if candidate_key(item) == candidate_key(candidate)),
            index,
        )
        return _hit(candidate, matched, original_index)

    # 候选全失效：再用指纹找一次（可能页面在这一轮里才渲染出来）。
    # 这次是兜底命中，按「自愈」报，不写回候选。
    healed, notes = resolve_by_fingerprint(
        page,
        target,
        timeout_ms=max(800, min(1_500, timeout_ms)),
        fallback_index=len(target.candidates),
    )
    tried.extend(fp_notes)
    tried.extend(notes)
    if healed is not None:
        healed.tried = tried
        healed.failed = list(failed)
        return healed

    _raise_if_only_in_iframe(page, target)
    raise TargetNotFound(tried, failure_kind)


def _raise_if_only_in_iframe(page: Page, target: Target) -> None:
    """主文档没命中时，若子 frame 能看见目标，明确报不支持。"""
    frames = getattr(page, "frames", None) or []
    if len(frames) <= 1:
        return
    main = page.main_frame
    for frame in frames:
        if frame == main:
            continue
        for candidate in target.ordered():
            if candidate.kind != "css" or not candidate.value:
                continue
            try:
                loc = frame.locator(sanitize_css_selector(candidate.value))
                total = min(loc.count(), 5)
            except Exception:
                continue
            for index in range(total):
                try:
                    if loc.nth(index).is_visible():
                        raise IframeNotSupported(
                            "目标位于 iframe 内，平台明确不支持跨 frame 定位与操作"
                            f"（候选 {candidate.describe()}）"
                        )
                except IframeNotSupported:
                    raise
                except Exception:
                    continue


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

# visible_dropdown_panel / wait_*_dropdown_panel 从 visibility 转入并在此再导出，
# 供 actions 与既有 selftest 的 import 路径不变。


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


_JS_PANEL_TAG_SELECTED = """(el) => {
  const chip = (el.closest && el.closest('.el-tag')) || el;
  const cls = String((chip && chip.className) || '');
  if (/(^|\\s)(is-selected|selected|is-checked)(\\s|$)/.test(cls)) return true;
  if (chip.getAttribute && chip.getAttribute('aria-selected') === 'true') return true;
  // Oinone 的色板/尺码面板：未选是 el-tag--info，选中换成 el-tag--primary。
  return /(^|\\s)el-tag--primary(\\s|$)/.test(cls) && !/(^|\\s)el-tag--info(\\s|$)/.test(cls);
}"""


def _is_selected_panel_tag(item) -> bool:
    """面板里的色板/尺码 tag 是不是已经选中。

    选中态挂在外层 `.el-tag` 上（`--info` 变 `--primary`），而 `_PANEL_TAG`
    定位到的是里面的 `.el-tag__content`，所以要往上找最近一层 `.el-tag`。
    多选面板里再点一次已选项会把它**取消**——141 上连续四次「改选」把尺码全点没了。
    """
    try:
        return bool(item.evaluate(_JS_PANEL_TAG_SELECTED))
    except Exception:
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


_PANEL_SIZE_TAG = (
    ".el-tab-pane[aria-hidden='false'] .sizeTag .el-tag, "
    ".el-tab-pane:visible .sizeTag .el-tag, "
    ".sizeTag .el-tag"
)
_PANEL_OPTION_TAG = (
    ".select-body .select-options .el-tag, "
    ".select-options .el-tag"
)
_PANEL_TAB_HOST = ".el-tabs__item, [role=tab]"

_JS_PANEL_CLICK = """(root, opts) => {
  const name = opts.name;
  const kind = opts.kind;
  const shown = (el) => {
    if (!el) return false;
    const pane = el.closest('.el-tab-pane');
    if (pane && pane.getAttribute('aria-hidden') === 'true') return false;
    const st = window.getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden' || Number(st.opacity) === 0) return false;
    const box = el.getBoundingClientRect();
    return box.width > 0 && box.height > 0;
  };
  const labelOf = (el) => {
    const inner = el.querySelector && el.querySelector('.el-tag__content, pre');
    const raw = ((inner && (inner.innerText || '')) || el.innerText || '').trim();
    return (raw.split('\\n')[0] || '').trim();
  };
  const tabs = Array.from(root.querySelectorAll('.el-tabs__item, [role=tab]'));
  if (kind === 'tab') {
    const tab = tabs.find((el) => shown(el) && labelOf(el) === name);
    if (!tab) return false;
    tab.click();
    return true;
  }
  const sizeTags = Array.from(root.querySelectorAll('.sizeTag .el-tag'));
  const sizeNames = new Set(sizeTags.map(labelOf).filter(Boolean));
  const isSelected = (el) => {
    const chip = (el.closest && el.closest('.el-tag')) || el;
    const cls = String((chip && chip.className) || '');
    if (/(^|\\s)(is-selected|selected|is-checked)(\\s|$)/.test(cls)) return true;
    if (chip.getAttribute && chip.getAttribute('aria-selected') === 'true') return true;
    return /(^|\\s)el-tag--primary(\\s|$)/.test(cls) && !/(^|\\s)el-tag--info(\\s|$)/.test(cls);
  };
  const clickNamed = (nodes) => {
    for (const el of nodes) {
      if (!shown(el) || labelOf(el) !== name) continue;
      const chip = el.classList.contains('is-closable') && !el.closest('.sizeTag');
      if (chip && sizeNames.has(name)) continue;
      // 多选面板里再点一次已选项会取消选择：已经是目标状态，不用点。
      if (isSelected(el)) return true;
      el.scrollIntoView({ block: 'nearest', inline: 'nearest' });
      el.click();
      return true;
    }
    return false;
  };
  if (clickNamed(sizeTags)) return true;
  const options = Array.from(root.querySelectorAll(
    '.select-body .select-options .el-tag, .select-options .el-tag'
  ));
  return clickNamed(options);
}"""


def _js_panel_click(panel, name: str, kind: str) -> bool:
    try:
        return bool(panel.evaluate(_JS_PANEL_CLICK, {"name": name, "kind": kind}))
    except Exception:
        return False


def _node_label(item) -> str:
    try:
        content = item.locator(".el-tag__content, pre").first
        if content.count():
            text = (content.inner_text(timeout=80) or "").strip()
            if text:
                return text.split("\n")[0].strip()
    except Exception:
        pass
    try:
        return ((item.inner_text(timeout=80) or "").strip().split("\n") or [""])[0].strip()
    except Exception:
        return ""


def _is_size_duplicate_chip(item, panel, name: str) -> bool:
    """已选芯片和隐藏 sizeTag 同文案时，不能点芯片。颜色没有 sizeTag，芯片就是选项。"""
    try:
        cls = (item.get_attribute("class") or "").split()
    except Exception:
        return False
    if "is-closable" not in cls:
        return False
    try:
        if item.evaluate("el => !!el.closest('.sizeTag')"):
            return False
    except Exception:
        pass
    loc = panel.locator(".sizeTag .el-tag")
    try:
        total = loc.count()
    except Exception:
        return False
    for index in range(total):
        if _node_label(loc.nth(index)) == name:
            return True
    return False


def _click_visible_named(
    loc, name: str, timeout_ms: int, *, panel=None, deadline: float | None = None
) -> bool:
    try:
        total = loc.count()
    except Exception:
        return False
    for index in range(total):
        # 面板可能有几十个尺码/颜色；每次点击都可能吃满 timeout，逐个给一遍会
        # 把「一次选择」拖成项数 × timeout。deadline 是调用方的总预算。
        if deadline is not None and time.monotonic() >= deadline:
            return False
        item = loc.nth(index)
        try:
            if not item.is_visible():
                continue
            if _node_label(item) != name:
                continue
            if panel is not None and _is_size_duplicate_chip(item, panel, name):
                continue
            # 已经是选中态：再点一次会把选择取消，按「已是目标状态」算命中。
            if _is_selected_panel_tag(item):
                return True
            click_ms = min(2_000, timeout_ms)
            if click_ms <= 0:
                return False
            item.scroll_into_view_if_needed(timeout=min(800, click_ms))
            item.click(timeout=click_ms)
            return True
        except Exception:
            continue
    return False


def pick_panel_choice(page: Page, name: str, *, kind: str = "tag", timeout_ms: int = 5_000) -> str | None:
    """尺码/色板/Tab 面板：只点当前看得见的项。当前 tab 没有就切过去再点。

    不能用 get_by_text().first：隐藏 pane 里的「S」排在 DOM 前面时，
    回放会点到未激活的标签，步骤显示通过，字段却仍是空的。

    **`timeout_ms` 是整次选择的总预算，不是每次尝试的预算。** 141 上当前 tab 找不到
    就挨个切 tab 全量重扫，每切一个 tab 还要发请求拉该 tab 的尺码表；按每次尝试给满
    预算，一次选择会被 tab 数乘成几百秒（实测单步 305s/361s/243s）。
    """
    if not name:
        return None
    deadline = time.monotonic() + max(0, timeout_ms) / 1000

    def left() -> int:
        return max(0, int((deadline - time.monotonic()) * 1000))

    def settle() -> None:
        wait_ms = min(200, left())
        if wait_ms <= 0:
            return
        try:
            page.wait_for_timeout(wait_ms)
        except Exception:
            pass

    panel = _visible_dropdown_panel(page)
    if panel is None:
        return None
    tabs = panel.locator(_PANEL_TAB_HOST)
    if kind == "tab":
        if _js_panel_click(panel, name, "tab") or _click_visible_named(
            tabs, name, left(), deadline=deadline
        ):
            settle()
            return name
        return None
    if _js_panel_click(panel, name, "tag"):
        return name
    if _click_visible_named(panel.locator(_PANEL_SIZE_TAG), name, left(), deadline=deadline):
        return name
    if _click_visible_named(
        panel.locator(_PANEL_OPTION_TAG), name, left(), panel=panel, deadline=deadline
    ):
        return name
    if _js_panel_click(panel, name, "tab") or _click_visible_named(
        tabs, name, left(), deadline=deadline
    ):
        settle()
        return name
    try:
        tab_count = tabs.count()
    except Exception:
        tab_count = 0
    for index in range(tab_count):
        # 预算用完就收手：剩下的 tab 不可能再给出「这项在选择里」的证据。
        if left() <= 0:
            break
        tab = tabs.nth(index)
        try:
            if not tab.is_visible():
                continue
            cls = (tab.get_attribute("class") or "").split()
            if "is-active" in cls:
                continue
            click_ms = min(2_000, left())
            if click_ms <= 0:
                break
            tab.click(timeout=click_ms)
            settle()
        except Exception:
            continue
        if _js_panel_click(panel, name, "tag"):
            return name
        if _click_visible_named(
            panel.locator(_PANEL_SIZE_TAG), name, left(), deadline=deadline
        ):
            return name
        if _click_visible_named(
            panel.locator(_PANEL_OPTION_TAG), name, left(), panel=panel, deadline=deadline
        ):
            return name
    return None


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


def _click_first_match(
    loc,
    skip_norm: set[str],
    timeout_ms: int,
    *,
    skip_active: bool = False,
    skip_selected: bool = False,
) -> str | None:
    try:
        total = loc.count()
    except Exception:
        return None
    for index in range(total):
        item = loc.nth(index)
        try:
            if not item.is_visible():
                continue
            cls = (item.get_attribute("class") or "").split()
            if "is-disabled" in cls or "disabled" in cls:
                continue
            # 已激活的 tab 再点一次什么都不会发生，不能把它当成「换了一屏」报通过。
            if skip_active and "is-active" in cls:
                continue
            # 已选中的色板/尺码再点一次会取消选择，不能拿它来「补一项」。
            if skip_selected and _is_selected_panel_tag(item):
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


def _first_matching_label(loc, skip_norm: set[str]) -> str | None:
    """只看不点：返回第一个可用项的文案。

    兜底时如果面板里的项**全部**已是选中态，字段本来就有值，再点只会取消，
    这时用它确认「已有一项被选中」而不是判失败。
    """
    try:
        total = loc.count()
    except Exception:
        return None
    for index in range(total):
        item = loc.nth(index)
        try:
            if not item.is_visible():
                continue
            cls = (item.get_attribute("class") or "").split()
            if "is-disabled" in cls or "disabled" in cls:
                continue
            label = (item.inner_text(timeout=400) or "").strip().split("\n")[0].strip()
            if not label or label in _SKIP_OPTION_LABELS or label in skip_norm:
                continue
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
        picked = _click_first_match(
            panel.locator(_PANEL_TAB), skip_norm, timeout_ms, skip_active=True
        )
        if picked:
            try:
                page.wait_for_timeout(200)
            except Exception:
                pass
        return picked
    if kind in {"tag", "any"}:
        tag_loc = panel.locator(_PANEL_TAG)
        picked = _click_first_match(tag_loc, skip_norm, timeout_ms, skip_selected=True)
        if picked:
            return picked
        # 项都已经是选中态：字段里有值，再点只会取消，确认即可。
        already = _first_matching_label(tag_loc, skip_norm)
        if already:
            return already
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
