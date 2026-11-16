"""动作原语。

一条流程只能由这些动作构成。将来 AI 探索也只能输出这些动作，
所以探索产物天生可回放，编译环节只需补断言与固化定位，不需要翻译。
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

from autotest_adapters.oinone.selectors import (
    COMBOBOX_ANCESTOR_JS,
    CLICKABLE_ANCESTOR_XPATH,
    DROPDOWN_SCROLL_HOLDER,
    CLICKABLE_VISIBLE,
    MODAL_WRAP_VISIBLE,
    JS_FIELD_REQUIRED,
    JS_FIELD_REQUIRED_BY_NAME,
    JS_INSPECT_PANEL,
    JS_SELECTED_CHOICE,
    MENU_ITEM_ANCESTOR_JS,
    MODAL_TITLE_VISIBLE,
    MODAL_VISIBLE,
    OVERLAY_WAIT_VISIBLE,
    DATE_PICKER_WIDGETS,
    looks_like_picker_date,
)
from autotest_executor.browser.locator import (
    ENVIRONMENTAL_KINDS,
    FailureKind,
    IframeNotSupported,
    LocatorMemory,
    LocatorResolution,
    TargetNotFound,
    TargetStillVisible,
    click_ant_sidebar_menu,
    pick_dropdown_option,
    pick_first_dropdown_option,
    locator_is_readonly_picker,
    parse_picker_value,
    pick_ant_picker_value,
    pick_any_panel_choice,
    pick_panel_choice,
    resolve_target,
    visible_dropdown_panel,
    wait_any_dropdown_panel,
    wait_target_hidden,
    wait_visible_dropdown_panel,
)
from autotest_executor.ui_selectors import (
    DROPDOWN_MIXED_VISIBLE,
    DROPDOWN_WIDGETS,
    is_select_trigger_css,
    looks_like_dropdown_option,
    panel_visible_selectors,
)
from autotest_executor.browser.readiness import wait_for_app_ready, wait_for_route_idle
from autotest_executor.browser.session import BrowserSession
from autotest_executor.uploads import resolve_upload_file
from autotest_protocol import Step
from autotest_protocol.dsl import candidate_key


def _remaining_ms(deadline: float) -> int:
    """离总预算还剩多少毫秒。给 0 表示已经用完，调用方必须收手。"""
    return max(0, int((deadline - time.monotonic()) * 1000))


# 给后续候选留的点击底。首选被遮挡时空等会把总预算耗光，回退就没机会跑。
# 1000ms 对「元素正常、只是页面慢」远远够用，只有真点不动时才会用满。
_CLICK_RESERVE_MS = 1_000

# 点击后等下拉展开的确认预算。沿用原来 `_wait_dropdown` 的 1500ms——
# 这是「动画 + 数据拉取」的常见量级，不是新拍的数。
_DROPDOWN_CONFIRM_MS = 1_500


def _click_slice_ms(remaining: int, candidates_left: int) -> int:
    """当前候选能用的点击预算。

    首选拿大头——它是正常情况下该命中的那个，不能因为要多试几个候选就缩短它的
    正常等待。但要给剩下的候选留一份底，否则首选被遮挡时空等会把总预算耗光，
    回退根本没机会跑（这正是第 3 节要修的那条路）。
    """
    if candidates_left <= 1:
        return remaining
    reserve = min(remaining // 2, _CLICK_RESERVE_MS * (candidates_left - 1))
    return max(1, remaining - reserve)


# 失败分类：运行结论里必须能区分这三类。混成一句「偶发失败」等于没报——
# 运维分不清该去改脚本，还是该去看环境。
# 「没找到」在下面 _do_* 解析失败处用；另两类由点击回退与生效确认补齐。
FAILURE_NOT_FOUND = "not_found"
FAILURE_NOT_ACTIONABLE = "not_actionable"
FAILURE_NO_EFFECT = "no_effect"

class ClickNotActionable(Exception):
    """候选都找到了，但一个都点不动。

    与「没找到」是两类失败：前者要去看遮挡/动画/权限，后者才要去看脚本里的候选。
    混成同一句，运维会去改本来没问题的候选。
    """

    def __init__(self, tried: list[str], cause: Exception) -> None:
        # Playwright 的 click 报错带整段 call log（几十行）。只取首行——
        # 那段日志会经 step_results 进运行结论，灌进去没人看得完。详情留在 cause 里。
        first_line = next((line for line in str(cause).splitlines() if line.strip()), "")
        detail = first_line.strip() or type(cause).__name__
        super().__init__(f"找到但点不到（{detail}）")
        self.tried = tried
        self.cause = cause

# Vue / React 这类框架监听的是 input 事件，直接改 value 不生效。
# Playwright 的 fill 已经派发 input，这里补 change 与 blur，覆盖依赖失焦提交的表单。
_JS_COMMIT_INPUT = """
(el) => {
  el.dispatchEvent(new Event('change', { bubbles: true }));
  el.dispatchEvent(new Event('blur', { bubbles: true }));
}
"""

_JS_READ_TABLE = """
() => {
  const table = document.querySelector('table');
  if (!table) return { found: false, headers: [], rows: [] };
  const headerCells = table.querySelectorAll('thead th, thead td');
  const headers = Array.from(headerCells).map((c) => (c.innerText || '').trim());
  const bodyRows = table.querySelectorAll('tbody tr');
  const rows = Array.from(bodyRows).slice(0, 50).map((tr) =>
    Array.from(tr.querySelectorAll('td, th')).map((td) => (td.innerText || '').trim())
  );
  return { found: true, headers, rows, totalRows: bodyRows.length };
}
"""

_NUMERIC_KEEP = re.compile(r"[^\d,.\-]")


def _to_number(value: str) -> float | None:
    """把页面格式化后的数字还原成 float。

    支持 RM 前缀、空格、千分位，以及逗号当小数点（99,00）。
    """
    raw = _NUMERIC_KEEP.sub("", (value or "").strip())
    if not raw or raw in {".", ",", "-", "-.", "-,"}:
        return None
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        parts = raw.split(",")
        if len(parts[-1]) <= 2:
            raw = raw.replace(",", ".")
        else:
            raw = raw.replace(",", "")
    try:
        return float(raw)
    except ValueError:
        return None


def _loose_value_match(expected: str, actual: str) -> bool:
    """数字输入框会被前端格式化，不能按字符串全等判断。

    99 对 99,00 / 99.00 / RM 99 都算填对。
    """
    if (expected or "").strip() == (actual or "").strip():
        return True
    exp_num = _to_number(expected)
    act_num = _to_number(actual)
    if exp_num is None or act_num is None:
        return False
    return exp_num == act_num


_EDIT_HINT = re.compile(r"编辑|修改|更新")
_CREATE_HINT = re.compile(r"新建|新增")
_COMMIT_LABEL = re.compile(r"保存|提交|确定|确认|登录")
_QUOTED = re.compile(r"[「「]([^」」]+)[」」]")
_NOT_FIELD = {
    "新增",
    "新建",
    "保存",
    "提交",
    "确定",
    "确认",
    "取消",
    "关闭",
    "删除",
    "编辑",
    "登录",
    "款式",
}


def field_name_from_label(label: str | None) -> str | None:
    if not label:
        return None
    parts = _QUOTED.findall(label)
    if not parts:
        return None
    name = parts[-1].strip()
    if not name or name in _NOT_FIELD:
        return None
    return name


_DROPDOWN_SCROLL_MARKERS = (
    "el-select-dropdown",
    "select-options",
    "select-body",
    "el-scrollbar__view",
    "el-scrollbar__wrap",
)


_DATE_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _picker_date_value(step: Step) -> str | None:
    target = step.target
    if target is not None:
        for cand in target.ordered():
            value = (cand.value or "").strip()
            if cand.kind == "text" and _DATE_ISO.fullmatch(value):
                return value
            if cand.kind == "css" and "title=" in value:
                match = re.search(r'title="(\d{4}-\d{2}-\d{2})"', value)
                if match:
                    return match.group(1)
    label = step.label or ""
    match = re.search(r"「(\d{4}-\d{2}-\d{2})」", label)
    return match.group(1) if match else None


def _looks_like_picker_date_click(step: Step) -> bool:
    target = step.target
    if target is None:
        return False
    if target.widget in DATE_PICKER_WIDGETS:
        return True
    if (target.panel or "").startswith("picker-overlay"):
        return True
    blob = " ".join(f"{c.kind}={c.value}" for c in target.candidates).lower()
    if looks_like_picker_date(blob):
        return True
    return bool(_picker_date_value(step) and "picker" in blob)


def _picker_trigger_meta(step: Step) -> tuple[str | None, str | None]:
    target = step.target
    if target is None:
        return None, None
    field = next((c.value for c in target.candidates if c.kind == "field" and c.value), None)
    trigger = target.trigger_css
    return trigger, field


def _is_dropdown_internal_scroll(step: Step) -> bool:
    """录制时在下拉浮层里滚轮浏览选项产生的 scroll。"""
    target = step.target
    if target is None:
        return False
    if target.scope is not None and target.scope.kind == "dropdown":
        return True
    blob = " ".join(
        f"{c.kind}={c.value}" for c in target.candidates
    ).lower()
    return any(marker in blob for marker in _DROPDOWN_SCROLL_MARKERS)


def should_skip_optional_miss(
    *,
    action: str,
    optional: bool | None,
    required: bool | None,
    mutating: bool = False,
    label: str | None = None,
    empty_choice: bool = False,
) -> bool:
    """非必填项选不到就跳过，必填项和保存/登录仍要失败。"""
    if action in {"goto", "waitFor", "assert", "pageHealth", "screenshot", "scroll"}:
        return False
    if action == "click" and mutating and _COMMIT_LABEL.search(label or ""):
        return False
    if optional is True:
        return True
    if required is False:
        return True
    if required is True:
        return False
    if empty_choice and action == "choose":
        return True
    if (
        empty_choice
        and action == "click"
        and "弹窗" in (label or "")
        and not _COMMIT_LABEL.search(label or "")
    ):
        return True
    return False


def panel_choice_kind(step: Step) -> str | None:
    """这次点击是下拉里的 tab、尺码标签，还是普通选项。"""
    target = step.target
    if target is None:
        return None
    css = " ".join(c.value or "" for c in target.candidates if c.kind == "css")
    roles = [c.value or "" for c in target.candidates if c.kind == "role"]
    if "tab-" in css or "el-tabs__item" in css or "tab" in roles:
        return "tab"
    if "sizeTag" in css or "el-tag" in css or "pane-" in css:
        return "tag"
    if (target.scope and target.scope.kind == "dropdown") or target.panel:
        return "any"
    if "弹窗" in (step.label or "") and not _COMMIT_LABEL.search(step.label or ""):
        return "any"
    return None


def is_edit_context(flow_name: str | None, step_label: str | None) -> bool:
    """编辑类流程才换已选项。链式步骤看前缀「编辑款式：」，不看整条套件名。"""
    label = (step_label or "").strip()
    name = (flow_name or "").strip()
    if "：" in label:
        head = label.split("：", 1)[0]
        if _CREATE_HINT.search(head):
            return False
        if _EDIT_HINT.search(head):
            return True
    if _CREATE_HINT.search(name) and _EDIT_HINT.search(name):
        return False
    if _EDIT_HINT.search(name) and not _CREATE_HINT.search(name):
        return True
    if _EDIT_HINT.search(label) and not _CREATE_HINT.search(label):
        return True
    return False


def decide_inline_create(panel: dict[str, Any]) -> str:
    """看打开的下拉面板长什么样，决定能不能在这一层新建。

    local：面板自己就是标签/色板/可添加输入，新建不会跳出当前层。
    lookup：只是主数据选项列表，新增会另开表单或点到外层保存，当前页不能建。
    """
    if panel.get("has_tags") or panel.get("has_color"):
        return "local"
    if panel.get("has_options") and not panel.get("has_tags"):
        return "lookup"
    if panel.get("has_add") and panel.get("has_input") and not panel.get("has_options"):
        return "local"
    return "lookup"


@dataclass
class StepOutcome:
    step_id: str
    action: str
    # passed / failed / skipped
    status: str
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    drift: str | None = None


class ActionRunner:
    def __init__(self, session: BrowserSession) -> None:
        self.session = session
        self.job = session.job
        self.locator_memory = LocatorMemory()
        self._last_trigger_css: str | None = None
        self._fallback_picked: set[str] = set()

    def _resolve(
        self,
        step: Step,
        *,
        fill_value: str | None = None,
        timeout_ms: int | None = None,
        skip: dict[str, str] | None = None,
    ) -> LocatorResolution:
        assert step.target is not None
        return resolve_target(
            self.session.page,
            step.target,
            step.timeout_ms if timeout_ms is None else timeout_ms,
            memory=self.locator_memory,
            step_id=step.id,
            fill_value=fill_value,
            skip=skip,
        )

    def _try_pick_date(self, step: Step) -> StepOutcome | None:
        date_val = _picker_date_value(step)
        if not date_val or not _looks_like_picker_date_click(step):
            return None
        trigger, field = _picker_trigger_meta(step)
        if pick_ant_picker_value(
            self.session.page,
            date_val,
            trigger_css=trigger,
            field=field,
            timeout_ms=step.timeout_ms,
        ):
            return StepOutcome(
                step.id,
                step.action,
                "passed",
                data={"value": date_val, "mode": "date_picker"},
            )
        return StepOutcome(
            step.id,
            step.action,
            "failed",
            f"日期面板里选不中 {date_val}",
        )

    def run(self, step: Step) -> StepOutcome:
        if self.job.options.dry_run and step.mutating:
            return StepOutcome(step.id, step.action, "skipped", "dry-run：跳过写操作步骤")

        handler = getattr(self, f"_do_{step.action}", None)
        if handler is None:
            # DSL 已在保存与执行前校验过，这里是兜底
            return StepOutcome(step.id, step.action, "failed", f"不支持的动作：{step.action}")
        try:
            return handler(step)
        except ClickNotActionable as exc:
            if self._should_skip_optional(step):
                return self._skip_optional(step, str(exc))
            return StepOutcome(
                step.id,
                step.action,
                "failed",
                str(exc),
                data={
                    "tried": exc.tried,
                    "failure": FAILURE_NOT_ACTIONABLE,
                    "failure_kind": FailureKind.COVERED,
                    "environmental": True,
                },
            )
        except IframeNotSupported as exc:
            return StepOutcome(
                step.id,
                step.action,
                "failed",
                str(exc),
                data={
                    "failure": FAILURE_NOT_FOUND,
                    "failure_kind": FailureKind.TARGET_CHANGED,
                    "unsupported": "iframe",
                },
            )
        except TargetNotFound as exc:
            fallback = self._click_available_choice(step)
            if fallback:
                wanted = field_name_from_label(step.label) or ""
                msg = f"没有「{wanted}」，已改选「{fallback}」" if wanted else f"已改选「{fallback}」"
                return StepOutcome(step.id, step.action, "passed", msg, data={"value": fallback, "mode": "select_any"})
            if self._should_skip_optional(step):
                return self._skip_optional(step, str(exc))
            return StepOutcome(
                step.id,
                step.action,
                "failed",
                str(exc),
                data={
                    "tried": exc.tried,
                    "failure": FAILURE_NOT_FOUND,
                    # 浮层没出现是环境原因，与「脚本里的候选真失效了」必须分开报：
                    # 前者不该让人去改脚本，也不该生成修补任务
                    "failure_kind": exc.kind,
                    "environmental": exc.kind in ENVIRONMENTAL_KINDS,
                },
            )
        except Exception as exc:  # noqa: BLE001 - 步骤级失败要变成结果，不能掀掉整次运行
            return StepOutcome(step.id, step.action, "failed", f"{type(exc).__name__}: {exc}")

    # ------------------------------------------------------------ 动作实现

    def _do_goto(self, step: Step) -> StepOutcome:
        target_url = step.value or "/"
        if not target_url.startswith(("http://", "https://")):
            base = self.job.site.base_url
            if self.job.environment is not None and self.job.environment.base_url:
                base = self.job.environment.base_url
            target_url = urljoin(base.rstrip("/") + "/", target_url.lstrip("/"))
        self.session.page.goto(target_url, timeout=step.timeout_ms, wait_until="domcontentloaded")
        # 单页应用在 DOM 就绪后还要渲染一段时间，不等会间歇性找不到元素
        ready = wait_for_app_ready(self.session.page, timeout_ms=step.timeout_ms)
        wait_for_route_idle(self.session.page, timeout_ms=min(8_000, step.timeout_ms))
        return StepOutcome(
            step.id,
            step.action,
            "passed",
            data={"url": self.session.page.url, "app_ready": ready},
        )

    def _do_click(self, step: Step) -> StepOutcome:
        assert step.target is not None
        date_outcome = self._try_pick_date(step)
        if date_outcome is not None:
            return date_outcome
        self._ensure_panel_open(step)
        panel_kind = panel_choice_kind(step)
        panel_name = self._panel_choice_name(step)
        if panel_kind in {"tag", "tab"} and panel_name:
            picked = pick_panel_choice(
                self.session.page,
                panel_name,
                kind=panel_kind,
                timeout_ms=min(5_000, step.timeout_ms),
            )
            if picked:
                return StepOutcome(
                    step.id,
                    step.action,
                    "passed",
                    data={"matched": f"panel-{panel_kind}[{picked}]", "mode": "panel_choice"},
                )
            # 录到的值不在了、面板里还有别的值：按既定口径「能选中就可以」改选一项，
            # 而不是直接跳过——跳过会让必填字段空着，保存时才失败，报错还指向上一步。
            # tab 也一样：人肉测试遇到没有的分组会换一个点，继续往下走。
            # 已激活的 tab 不算（再点一次什么都不会发生，不能报通过）。
            fallback = pick_any_panel_choice(
                self.session.page,
                kind=panel_kind,
                skip=[panel_name],
                timeout_ms=min(3_000, step.timeout_ms),
            )
            if fallback:
                return StepOutcome(
                    step.id,
                    step.action,
                    "passed",
                    f"没有「{panel_name}」，已改选「{fallback}」",
                    data={
                        "matched": f"panel-{panel_kind}[{fallback}]",
                        "mode": "panel_any",
                        "wanted": panel_name,
                    },
                )
            miss = f"面板里找不到「{panel_name}」"
            # 走到这里说明面板里没有可用的项（兜底也点不到），按「空面板」处理。
            if self._should_skip_optional(step, empty_choice=True):
                return self._skip_optional(step, miss)
            return StepOutcome(step.id, step.action, "failed", miss)
        option_name = self._dropdown_option_name(step)
        if option_name:
            picked = pick_dropdown_option(self.session.page, option_name, step.timeout_ms)
            if picked:
                return StepOutcome(
                    step.id,
                    step.action,
                    "passed",
                    data={"matched": f'select-option[{option_name}]', "mode": "filter_or_scroll"},
                )
            miss = f"下拉里找不到「{option_name}」（已尝试搜索过滤和滚动虚拟列表）"
            first = pick_first_dropdown_option(self.session.page, skip=[option_name])
            if first:
                return StepOutcome(
                    step.id,
                    step.action,
                    "passed",
                    f"没有「{option_name}」，已改选「{first}」",
                    data={"matched": f"select-option[{first}]", "mode": "select_any", "wanted": option_name},
                )
            if self._should_skip_optional(step, empty_choice=True):
                return self._skip_optional(step, miss)
            return StepOutcome(
                step.id,
                step.action,
                "failed",
                miss,
            )
        scoped = step.target.scope is not None and step.target.scope.kind != "page"
        if not scoped:
            names = [c.value for c in step.target.ordered() if c.kind == "text" and c.value]
            for name in names:
                if click_ant_sidebar_menu(self.session.page, name, step.timeout_ms):
                    self._settle_after_navigation()
                    return StepOutcome(
                        step.id,
                        step.action,
                        "passed",
                        data={"matched": f'menuitem[title="{name}"]', "menu": "sidebar"},
                    )
        # 点之前先看下拉是不是已经开着。已经开着时点触发器本来就会把它收起来，
        # 「点完没有下拉」说明不了没生效——这道护栏也顺带挡住 _ensure_panel_open
        # 刚把面板点开、紧接着又被 _click_candidate 点关的乱局。
        dropdown_was_open = visible_dropdown_panel(self.session.page) is not None
        resolution = self._click_candidate(step)
        self._remember_trigger(step)
        label = step.label or ""
        opens_overlay = scoped or any(word in label for word in ("新增", "新建", "添加"))
        no_effect: str | None = None
        if self._click_opens_dropdown(step):
            no_effect = self._confirm_dropdown_opened(step, already_open=dropdown_was_open)
        elif opens_overlay:
            self._wait_overlay()
        else:
            self._settle_after_navigation()
        if no_effect is not None:
            return StepOutcome(
                step.id,
                step.action,
                "failed",
                no_effect,
                data={
                    "matched": resolution.candidate.describe(),
                    "failure": FAILURE_NO_EFFECT,
                    "failure_kind": FailureKind.TIMEOUT,
                    "environmental": True,
                },
            )
        return self._with_drift(step, resolution, data={"matched": resolution.candidate.describe()})

    def _confirm_dropdown_opened(self, step: Step, *, already_open: bool) -> str | None:
        """点击「下拉触发器」后确认下拉真的展开了。返回 None 表示确认通过。

        只在步骤**自己声明了后果**时才判失败：目标是 select / combobox 触发器，
        点它的唯一目的就是展开下拉。没有这一条，「点了没生效」只能靠下游步骤
        莫名其妙地失败来暴露——而那时的报错指向的是下游，排查方向是错的。

        **不做**通用的「什么都没变就判失败」。点输入框取焦点、点表格行做选中、
        点按钮弹一个我们不追踪的 toast，都是合法的不改 URL 不改可见性的点击。
        凭空判失败会把好用例弄红，而没人会看天天红的报告——那比漏报更糟。
        只有「步骤明确声明了该有什么后果」才够格当判据。
        """
        if already_open:
            return None
        if wait_any_dropdown_panel(self.session.page, min(_DROPDOWN_CONFIRM_MS, step.timeout_ms)):
            return None
        return (
            "点了没生效：点击下拉触发器后没有出现下拉面板"
            "（目标可能被遮挡、已禁用，或点击落到了别的元素上）"
        )

    def _panel_choice_name(self, step: Step) -> str | None:
        target = step.target
        if target is not None:
            for cand in target.ordered():
                if cand.kind == "text" and cand.value:
                    return cand.value
                if cand.kind == "role" and cand.name:
                    return cand.name
        label = step.label or ""
        marker = "点击「"
        if marker in label:
            return label.split(marker, 1)[1].split("」", 1)[0]
        return None

    def _dropdown_option_name(self, step: Step) -> str | None:
        target = step.target
        if target is None:
            return None
        looks_option = any(
            looks_like_dropdown_option(c.value or "") for c in target.candidates
        )
        # 自定义色板/面板也常落在 dropdown scope，但不能走标准下拉搜索
        if not looks_option:
            return None
        for cand in target.ordered():
            if cand.kind == "text" and cand.value:
                return cand.value
            if cand.kind == "role" and cand.name:
                return cand.name
            if cand.kind == "css" and "title=" in cand.value:
                start = cand.value.find('title="')
                if start >= 0:
                    rest = cand.value[start + 7 :]
                    return rest.split('"', 1)[0]
        return None

    def _click_candidate(self, step: Step) -> LocatorResolution:
        """按候选顺序点到成功为止，总预算受 `step.timeout_ms` 约束。

        只点一次就判失败是缺陷的一半：候选 A 点不到不代表候选 B 也不行。
        但跳过的候选按环境原因（COVERED）记——点不到多半是遮挡或动画，不是 A 失效；
        判成失效会在下一次把好候选从脚本里删掉（见 `LocatorMemory.remember`）。

        预算是**总共一份**，不是每个候选一份：候选多的时候，逐个给满预算会把一次
        点击拖成候选数 × timeout。但也不是平均分——见 `_click_slice_ms`。
        """
        assert step.target is not None
        deadline = time.monotonic() + max(0, step.timeout_ms) / 1000
        total = max(1, len(step.target.candidates))
        skipped: dict[str, str] = {}
        tried: list[str] = []
        last_error: Exception | None = None
        while True:
            try:
                resolution = self._resolve(step, timeout_ms=_remaining_ms(deadline), skip=skipped)
            except TargetNotFound as exc:
                if last_error is None:
                    raise
                # 候选都试过了：不是没找到，是找到了点不到
                raise ClickNotActionable(exc.tried or tried, last_error) from exc
            tried.append(resolution.candidate.describe())
            try:
                # 至少给 1ms：Playwright 的 timeout=0 表示「不限时」，会挂死
                budget = _click_slice_ms(_remaining_ms(deadline), total - len(skipped))
                self._click_locator(resolution.locator, budget)
                return resolution
            except Exception as exc:  # noqa: BLE001 - 换下一个候选，不能掀掉整次运行
                last_error = exc
                skipped[candidate_key(resolution.candidate)] = FailureKind.COVERED
                if _remaining_ms(deadline) <= 0:
                    raise ClickNotActionable(tried, last_error) from last_error

    def _click_locator(self, locator, timeout_ms: int) -> None:
        """图标内部的 <use> 能被定位，但点击会被上层 svg 挡住。改点可点的祖先。

        点不动就抛。这里**不再**用 `force=True` 兜底——绕过遮挡检查的强制点击会
        静默点到别的东西上还报通过，比失败更糟。逃生口留给步骤显式声明。
        """
        try:
            in_select = locator.evaluate(COMBOBOX_ANCESTOR_JS)
        except Exception:
            in_select = False
        if in_select:
            target = locator
        else:
            leaf = locator.locator(MENU_ITEM_ANCESTOR_JS)
            if leaf.count():
                target = leaf
            else:
                clickable = locator.locator(CLICKABLE_ANCESTOR_XPATH)
                target = clickable if clickable.count() else locator
        target.click(timeout=timeout_ms)

    def _do_fill(self, step: Step) -> StepOutcome:
        assert step.target is not None and step.value is not None
        if "fakepath" in (step.value or "").lower():
            return self._do_upload(step)
        target = step.target
        resolution = self._resolve(step, fill_value=step.value)
        box = resolution.locator
        try:
            tag = box.evaluate("(el) => el && el.tagName ? el.tagName.toLowerCase() : ''")
        except Exception:
            tag = ""
        if tag not in {"input", "textarea"} and not box.get_attribute("contenteditable"):
            inner = box.locator(
                "input:not([type=hidden]):not([type=file]):not(.is-hidden), textarea, [contenteditable=true]"
            )
            if inner.count():
                box = inner.first
        try:
            input_type = (box.get_attribute("type") or "").lower()
        except Exception:
            input_type = ""
        if input_type == "file" or "fakepath" in (step.value or "").lower():
            return self._do_upload(step)
        blob = " ".join(f"{c.kind}={c.value}" for c in target.candidates)
        is_picker = (
            target.widget in DATE_PICKER_WIDGETS
            or locator_is_readonly_picker(box)
            or looks_like_picker_date(blob)
        )
        if is_picker:
            trigger, field = _picker_trigger_meta(step)
            if parse_picker_value(step.value):
                if pick_ant_picker_value(
                    self.session.page,
                    step.value,
                    trigger_css=trigger,
                    field=field,
                    input_locator=box,
                    timeout_ms=step.timeout_ms,
                ):
                    return StepOutcome(
                        step.id,
                        step.action,
                        "passed",
                        data={"value": step.value, "mode": "date_picker"},
                    )
            return StepOutcome(
                step.id,
                step.action,
                "failed",
                f"日期控件是只读的，不能 fill；需要 YYYY-MM-DD 或 YYYY-MM-DD HH:mm:ss，"
                f"实际为 {step.value!r}",
            )
        box.fill(step.value, timeout=step.timeout_ms)
        box.evaluate(_JS_COMMIT_INPUT)
        actual = box.input_value(timeout=step.timeout_ms)
        if actual != step.value:
            if _loose_value_match(step.value, actual):
                return self._with_drift(
                    step,
                    resolution,
                    data={"value": actual, "expected": step.value, "note": "前端对值做了格式化"},
                )
            return StepOutcome(
                step.id,
                step.action,
                "failed",
                f"填值后取回的值与期望不一致：期望 {step.value!r}，实际 {actual!r}（可能被前端格式化或未生效）",
                data={
                    "expected": step.value,
                    "actual": actual,
                    # 值取回来是别的：不是没找到、也不是点不到，是填了没生效
                    "failure": FAILURE_NO_EFFECT,
                },
            )
        return self._with_drift(step, resolution, data={"value": actual})

    def _do_upload(self, step: Step) -> StepOutcome:
        """回放固定项目图片，不打开系统文件框。"""
        assert step.target is not None
        path = resolve_upload_file(step.value)
        if not path.is_file():
            return StepOutcome(
                step.id,
                step.action,
                "failed",
                f"回放用的图片不存在：{path}",
            )
        loc = self._file_input_locator(step)
        loc.set_input_files(str(path), timeout=step.timeout_ms)
        return StepOutcome(
            step.id,
            step.action,
            "passed",
            data={"file": str(path), "name": path.name},
        )

    def _file_input_locator(self, step: Step):
        page = self.session.page
        field = None
        if step.target is not None:
            for cand in step.target.candidates:
                if cand.kind == "field" and cand.value:
                    field = cand.value
                    break
        selectors = ["input[type=file]", ".el-upload__input"]
        if field:
            selectors = [
                f'[data-name="{field}"] input[type=file]',
                f'[data-name="{field}"] .el-upload__input',
                *selectors,
            ]
        modal = page.locator(MODAL_VISIBLE)
        root = modal.last if modal.count() else page
        for sel in selectors:
            loc = root.locator(sel)
            try:
                if loc.count():
                    return loc.last
            except Exception:
                continue
        resolution = self._resolve(step)
        inner = resolution.locator.locator("input[type=file], .el-upload__input")
        try:
            if inner.count():
                return inner.last
        except Exception:
            pass
        return resolution.locator

    def _do_choose(self, step: Step) -> StepOutcome:
        """新建：能搜就搜，没有就用第一条。编辑：跳过已选项，换一条。"""
        assert step.target is not None and step.value is not None
        page = self.session.page
        self._ensure_panel_open(step)
        resolution = self._resolve(step)
        current = self._read_selected_choice(resolution)
        # 上一步「点击品类」往往已经打开下拉。再点一次触发器会被 Ant 关掉。
        if visible_dropdown_panel(page) is None:
            resolution.locator.click(timeout=step.timeout_ms)
            self._remember_trigger(step)
            # 轮询到面板出现即可。原来是 wait_for_timeout(250) + wait_for(visible)：
            # 那 250ms 是纯硬等，动画快时白等、慢时又不够。
            wait_visible_dropdown_panel(page, min(3_000, step.timeout_ms))
        else:
            self._remember_trigger(step)
        mode = step.choose_mode
        if mode == "other" or (mode is None and self._is_edit_choose(step)):
            return self._choose_for_edit(step, resolution, current)
        return self._choose_for_create(step, resolution)

    def _is_edit_choose(self, step: Step) -> bool:
        flow_name = self.job.flow.name if self.job.flow else ""
        if is_edit_context(flow_name, step.label):
            return True
        if "：" in (step.label or "") and not is_edit_context(flow_name, step.label):
            return False
        return self._dialog_looks_edit()

    def _dialog_looks_edit(self) -> bool:
        loc = self.session.page.locator(MODAL_TITLE_VISIBLE)
        try:
            if not loc.count():
                return False
            title = (loc.last.inner_text(timeout=500) or "").strip()
        except Exception:
            return False
        if _CREATE_HINT.search(title):
            return False
        return bool(_EDIT_HINT.search(title))

    def _should_skip_optional(self, step: Step, locator=None, *, empty_choice: bool = False) -> bool:
        required = self._probe_required(step, locator)
        return should_skip_optional_miss(
            action=step.action,
            optional=step.optional,
            required=required,
            mutating=step.mutating,
            label=step.label,
            empty_choice=empty_choice,
        )

    def _skip_optional(self, step: Step, reason: str) -> StepOutcome:
        dialogs_before = self._visible_dialog_count()
        self._dismiss_dropdown()
        field = field_name_from_label(step.label) or step.value or ""
        prefix = f"非必填「{field}」未选到，已跳过" if field else "非必填项未选到，已跳过"
        if dialogs_before and not self._visible_dialog_count():
            # 跳过本身无害，但收下拉把外层弹窗一起收掉了。后面每一步都只剩垃圾结果，
            # 失败会被推迟几十步、还报成「浮层不存在」指错方向。就地判红。
            return StepOutcome(
                step.id,
                step.action,
                "failed",
                f"{prefix}：收下拉时把外层弹窗一起关掉了（{reason}）",
                data={
                    "failure": FAILURE_NOT_FOUND,
                    "failure_kind": FailureKind.OVERLAY_ABSENT,
                    "environmental": True,
                },
            )
        return StepOutcome(step.id, step.action, "skipped", f"{prefix}：{reason}")

    def _dismiss_dropdown(self) -> None:
        """收起可能开着的下拉面板。

        **没开着的面板不要按 Escape**：Escape 会一路冒泡到弹窗上，把整个表单关掉。
        141 的 Oinone 就是这么挂的——跳过一个非必填字段，后面 20 步全落空。

        弹窗里开着面板时更不能按 Escape，同一个原因。改点触发器把面板收回去：
        点一个开着的触发器本来就是收起，这是 Ant/Element 的常规行为（`_do_click`
        里 `dropdown_was_open` 那段已经依赖这个行为）。触发器 css 没记住时宁可留一个
        开着的面板——下一步点别的触发器会把它顶掉，而弹窗关了就再也回不来。
        """
        page = self.session.page
        if visible_dropdown_panel(page) is None:
            return
        if self._visible_dialog_count() > 0:
            self._toggle_panel_closed()
            return
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(150)
        except Exception:
            pass

    def _toggle_panel_closed(self) -> None:
        """点开着的触发器把下拉收回去。没有记住触发器就什么都不做。"""
        css = self._last_trigger_css
        if not css:
            return
        try:
            trigger = self.session.page.locator(css)
            if trigger.count() == 0:
                return
            self._click_locator(trigger.last, 1_500)
            self.session.page.wait_for_timeout(150)
        except Exception:
            pass

    def _probe_required(self, step: Step, locator=None) -> bool | None:
        seen: list[Any] = []
        if locator is not None:
            seen.append(locator)
        if self._last_trigger_css:
            try:
                trigger = self.session.page.locator(self._last_trigger_css)
                if trigger.count():
                    seen.append(trigger.last)
            except Exception:
                pass
        for item in seen:
            try:
                value = item.evaluate(JS_FIELD_REQUIRED)
            except Exception:
                value = None
            if isinstance(value, bool):
                return value
        name = field_name_from_label(step.label)
        if not name:
            return None
        try:
            value = self.session.page.evaluate(JS_FIELD_REQUIRED_BY_NAME, name)
        except Exception:
            return None
        return value if isinstance(value, bool) else None

    def _fallback_key(self, step: Step, kind: str) -> str:
        css = ""
        if step.target and step.target.trigger_css:
            css = step.target.trigger_css
        elif self._last_trigger_css:
            css = self._last_trigger_css
        return f"{css}|{kind}"

    def _click_available_choice(self, step: Step) -> str | None:
        """录到的项没有时，在当前面板里有啥选啥，同类只补一项。"""
        if step.action != "click":
            return None
        if step.mutating and _COMMIT_LABEL.search(step.label or ""):
            return None
        kind = panel_choice_kind(step)
        if kind is None:
            return None
        key = self._fallback_key(step, "tag" if kind == "any" else kind)
        if kind != "tab" and key in self._fallback_picked:
            return None
        self._ensure_panel_open(step)
        wanted = field_name_from_label(step.label)
        picked = pick_any_panel_choice(
            self.session.page,
            kind=kind,
            skip=[wanted] if wanted else None,
        )
        if picked and kind != "tab":
            self._fallback_picked.add(key)
        return picked

    def _read_selected_choice(self, resolution) -> str:
        try:
            text = resolution.locator.evaluate(JS_SELECTED_CHOICE)
            return (text or "").strip().split("\n")[0].strip()
        except Exception:
            return ""

    def _choose_for_edit(self, step: Step, resolution, current: str) -> StepOutcome:
        skip = [item for item in (current, step.value) if item]
        picked = pick_first_dropdown_option(
            self.session.page, skip=skip, skip_selected=True, timeout_ms=min(5_000, step.timeout_ms)
        )
        if picked:
            return self._choose_existing(
                step,
                resolution,
                picked,
                mode="select_other",
                message=f"编辑已换选项：原「{current or step.value}」→「{picked}」",
            )
        if self._open_dropdown_root() is None:
            miss = f"编辑要换掉已选的「{current or step.value}」，但下拉没有打开"
            if self._should_skip_optional(step, resolution.locator):
                return self._skip_optional(step, miss)
            return StepOutcome(step.id, step.action, "failed", miss)
        miss = (
            f"编辑要换掉已选的「{current or step.value}」，"
            "但下拉里没扫到其它项（可能被搜索框里的已选文案滤成一项）"
        )
        if self._should_skip_optional(step, resolution.locator, empty_choice=True):
            return self._skip_optional(step, miss)
        return StepOutcome(step.id, step.action, "failed", miss)

    def _choose_for_create(self, step: Step, resolution) -> StepOutcome:
        page = self.session.page
        picked = pick_dropdown_option(page, step.value, min(5_000, step.timeout_ms))
        if picked:
            return self._choose_existing(step, resolution, picked)
        panel = self._open_dropdown_root()
        if panel is not None:
            try:
                option = panel.get_by_text(step.value, exact=True)
                if option.count() and option.last.is_visible():
                    option.last.click(timeout=min(3_000, step.timeout_ms))
                    return self._choose_existing(step, resolution, step.value)
            except Exception:
                pass
        mode = decide_inline_create(self._inspect_dropdown(panel))
        if mode == "local":
            return self._choose_create_local(step, resolution)
        first = pick_first_dropdown_option(page)
        if first:
            return self._choose_existing(
                step,
                resolution,
                first,
                mode="select_first",
                message=f"下拉里没有「{step.value}」，已用第一条「{first}」兜底",
            )
        miss = f"下拉里没有「{step.value}」，也没有可兜底的选项"
        if self._should_skip_optional(step, resolution.locator, empty_choice=True):
            return self._skip_optional(step, miss)
        return StepOutcome(step.id, step.action, "failed", miss)

    def _choose_create_local(self, step: Step, resolution) -> StepOutcome:
        if self.job.options.dry_run:
            return StepOutcome(
                step.id,
                step.action,
                "skipped",
                f"没有「{step.value}」，演练不在面板里新建",
            )
        created = self._create_in_dropdown(step.value)
        if not created:
            miss = f"面板支持新建，但没能在下拉里加上「{step.value}」（不会去点表单保存）"
            if self._should_skip_optional(step, resolution.locator):
                return self._skip_optional(step, miss)
            return StepOutcome(step.id, step.action, "failed", miss)
        pick_dropdown_option(self.session.page, step.value, min(3_000, step.timeout_ms))
        outcome = self._with_drift(
            step,
            resolution,
            data={"value": step.value, "mode": "create"},
        )
        outcome.message = f"已在下拉面板中新建 {step.value}"
        return outcome

    def _choose_existing(
        self,
        step: Step,
        resolution,
        value: str,
        *,
        mode: str = "select_existing",
        message: str | None = None,
    ) -> StepOutcome:
        outcome = self._with_drift(
            step,
            resolution,
            data={"value": value, "wanted": step.value, "mode": mode},
        )
        outcome.message = message or f"已选择已有项 {value}"
        return outcome

    def _open_dropdown_root(self):
        return visible_dropdown_panel(self.session.page)

    def _inspect_dropdown(self, panel) -> dict[str, Any]:
        empty = {
            "has_tags": False,
            "has_color": False,
            "has_options": False,
            "has_add": False,
            "has_input": False,
        }
        if panel is None:
            return empty
        try:
            info = panel.evaluate(JS_INSPECT_PANEL)
            if isinstance(info, dict):
                return {**empty, **info}
        except Exception:
            pass
        return empty

    def _visible_dialog_count(self) -> int:
        loc = self.session.page.locator(MODAL_WRAP_VISIBLE)
        try:
            return loc.count()
        except Exception:
            return 0

    def _create_in_dropdown(self, value: str) -> bool:
        """只在当前下拉面板里填值和添加。新增若弹出另一层表单就取消，不点外层保存。"""
        panel = self._open_dropdown_root()
        if panel is None:
            return False
        dialogs_before = self._visible_dialog_count()
        filled = self._fill_in(panel, value)
        added = self._click_exact_text(panel, ("新增", "添加", "新建"), 1_500)
        if self._visible_dialog_count() > dialogs_before:
            self._dismiss_extra_dialog(dialogs_before)
            return False
        if filled:
            try:
                box = panel.locator("input:visible:not([type=hidden])").last
                if box.count():
                    box.press("Enter")
                    added = True
            except Exception:
                pass
        if self._visible_dialog_count() > dialogs_before:
            self._dismiss_extra_dialog(dialogs_before)
            return False
        confirmed = self._click_panel_confirm(panel)
        return bool(filled or added or confirmed)

    def _dismiss_extra_dialog(self, dialogs_before: int) -> None:
        """关掉刚弹出来的那层嵌套表单，别碰外层弹窗。

        先在最上层弹窗里找「取消/关闭」——这是有目标的点击。找不到再按 Escape，
        且只在嵌套层确实还在时才按：Escape 关的是最上面那层，层数一旦判断有误，
        带走的就是外层弹窗。
        """
        page = self.session.page
        top = page.locator(MODAL_WRAP_VISIBLE).last
        for label in ("取消", "关闭"):
            try:
                btn = top.get_by_text(label, exact=True)
                if btn.count() and btn.last.is_visible():
                    btn.last.click(timeout=800)
                    return
            except Exception:
                continue
        if self._visible_dialog_count() <= dialogs_before:
            return
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(150)
        except Exception:
            pass

    def _click_exact_text(self, root, labels: tuple[str, ...], timeout_ms: int) -> bool:
        for label in labels:
            option = root.get_by_text(label, exact=True)
            try:
                if option.count() and option.last.is_visible():
                    option.last.click(timeout=timeout_ms)
                    return True
            except Exception:
                continue
        return False

    def _fill_in(self, root, value: str) -> bool:
        for locator in (
            root.locator("input:visible:not([type=hidden])"),
            root.get_by_placeholder("请输入"),
            root.locator("[contenteditable=true]:visible"),
        ):
            try:
                if locator.count() and locator.last.is_visible():
                    target = locator.last
                    target.fill(value, timeout=2_000)
                    target.evaluate(_JS_COMMIT_INPUT)
                    return True
            except Exception:
                continue
        return False

    def _click_panel_confirm(self, root) -> bool:
        buttons = root.locator(CLICKABLE_VISIBLE)
        try:
            total = buttons.count()
        except Exception:
            total = 0
        for label in ("确定", "确认"):
            for index in range(total):
                btn = buttons.nth(index)
                try:
                    text = (btn.inner_text(timeout=500) or "").strip().split("\n")[0]
                    if text != label:
                        continue
                    action = btn.evaluate(
                        """el => {
                          const host = el.closest('[data-action-name]') || el;
                          return (host.getAttribute('data-action-name') || '').toLowerCase();
                        }"""
                    )
                    if action == "update":
                        continue
                    btn.click(timeout=1_200)
                    return True
                except Exception:
                    continue
        return False

    def _do_select(self, step: Step) -> StepOutcome:
        assert step.target is not None and step.value is not None
        resolution = self._resolve(step)
        resolution.locator.select_option(step.value, timeout=step.timeout_ms)
        return self._with_drift(step, resolution, data={"value": step.value})

    def _do_scroll(self, step: Step) -> StepOutcome:
        assert step.target is not None
        self._ensure_panel_open(step)
        try:
            top = int(float(step.value or 0))
        except (TypeError, ValueError):
            top = 0
        # 下拉已打开时，录到的 css 往往是浮层内部路径，对不上就滚不动。
        # 改滚当前可见下拉的滚动容器（与 pick_dropdown_option 一致）。
        if _is_dropdown_internal_scroll(step):
            page = self.session.page
            panel = visible_dropdown_panel(page)
            if panel is None:
                return StepOutcome(
                    step.id,
                    step.action,
                    "failed",
                    "下拉滚动步骤：面板未打开或不可见",
                )
            holder = panel.locator(DROPDOWN_SCROLL_HOLDER)
            try:
                scroll_target = holder.last if holder.count() else panel
                scroll_target.evaluate(
                    """(el, y) => {
                      el.scrollTop = y;
                      el.dispatchEvent(new Event('scroll', { bubbles: true }));
                    }""",
                    top,
                )
                page.wait_for_timeout(120)
                return StepOutcome(
                    step.id,
                    step.action,
                    "passed",
                    data={"scrollTop": top, "mode": "dropdown_panel"},
                )
            except Exception as exc:
                return StepOutcome(step.id, step.action, "failed", str(exc))
        resolution = self._resolve(step)
        resolution.locator.evaluate(
            """(el, y) => {
              el.scrollTop = y;
              el.dispatchEvent(new Event('scroll', { bubbles: true }));
            }""",
            top,
        )
        self.session.page.wait_for_timeout(120)
        return self._with_drift(step, resolution, data={"scrollTop": top})

    def _do_waitFor(self, step: Step) -> StepOutcome:  # noqa: N802 - 与 DSL 动作名保持一致
        condition = step.condition
        page = self.session.page
        if condition == "load":
            page.wait_for_load_state("load", timeout=step.timeout_ms)
        elif condition == "network_idle":
            page.wait_for_load_state("networkidle", timeout=step.timeout_ms)
        elif condition == "probe_ready":
            page.wait_for_function(
                "() => !!window.__atpProbe", timeout=step.timeout_ms
            )
        elif condition == "visible":
            assert step.target is not None
            resolution = self._resolve(step)
            return self._with_drift(step, resolution)
        elif condition == "hidden":
            assert step.target is not None
            try:
                matched = wait_target_hidden(page, step.target, step.timeout_ms)
            except TargetStillVisible as exc:
                return StepOutcome(
                    step.id,
                    step.action,
                    "failed",
                    "元素始终没有消失",
                    data={"tried": exc.tried},
                )
            return StepOutcome(step.id, step.action, "passed", data={"hidden": matched})
        return StepOutcome(step.id, step.action, "passed", data={"condition": condition})

    def _do_readTable(self, step: Step) -> StepOutcome:  # noqa: N802
        table = self.session.page.evaluate(_JS_READ_TABLE)
        status = "passed" if table.get("found") else "failed"
        message = "" if table.get("found") else "页面上没有找到表格"
        return StepOutcome(step.id, step.action, status, message, data=table)

    def _do_pageHealth(self, step: Step) -> StepOutcome:  # noqa: N802
        """页面体检：纯确定性 JS，零模型调用，可在全量回归里逐页跑。"""
        probe = self.session.read_probe()
        counts = {
            "consoleErrors": len(probe.get("consoleErrors", [])),
            "jsErrors": len(probe.get("jsErrors", [])),
            "requestErrors": len(probe.get("requestErrors", [])),
            "uiErrors": len(probe.get("uiErrors", [])),
        }
        healthy = sum(counts.values()) == 0
        data = {
            "counts": counts,
            "jsErrors": probe.get("jsErrors", [])[:5],
            "requestErrors": probe.get("requestErrors", [])[:5],
            "consoleErrors": probe.get("consoleErrors", [])[:5],
            "uiErrors": probe.get("uiErrors", [])[:5],
            "url": self.session.page.url,
            "title": self.session.page.title(),
        }
        if healthy:
            return StepOutcome(step.id, step.action, "passed", "未发现前端错误", data=data)
        toasts = [str(e.get("message") or "") for e in probe.get("uiErrors", []) if e.get("message")]
        if toasts:
            message = "页面报错：" + "；".join(toasts[:3])
        else:
            message = "探针捕获到异常：页面可能视觉正常但底层请求或脚本失败"
        return StepOutcome(
            step.id,
            step.action,
            "failed",
            message,
            data=data,
        )

    def _do_screenshot(self, step: Step) -> StepOutcome:
        # 截图由执行器统一在每步之后处理，这里只标记一个命名点
        return StepOutcome(step.id, step.action, "passed", data={"name": step.value or step.id})

    def _settle_after_navigation(self) -> None:
        """点菜单后 SPA 还要渲染列表，立刻找「新增」会扑空。

        只等盖住内容的遮罩（最多 8 秒）。角落里一直转的小 spinner 不等。
        """
        wait_for_route_idle(self.session.page, timeout_ms=8_000)
        wait_for_app_ready(self.session.page, timeout_ms=1_500)

    def _remember_trigger(self, step: Step) -> None:
        target = step.target
        if target is None:
            return
        if target.trigger_css:
            self._last_trigger_css = target.trigger_css
        elif self._click_opens_dropdown(step):
            for cand in target.candidates:
                if cand.kind == "css" and is_select_trigger_css(cand.value or ""):
                    self._last_trigger_css = cand.value
                    break

    def _panel_visible(self, step: Step) -> bool:
        page = self.session.page
        panel = (step.target.panel if step.target else None) or ""
        selectors = panel_visible_selectors(panel)
        loc = page.locator(", ".join(selectors))
        try:
            if loc.count() > 0 and loc.last.is_visible():
                return True
        except Exception:
            pass
        return visible_dropdown_panel(page) is not None

    def _ensure_panel_open(self, step: Step) -> None:
        target = step.target
        if target is None:
            return
        needs = (
            (target.scope is not None and target.scope.kind == "dropdown")
            or bool(target.panel)
        )
        if not needs:
            return
        if self._panel_visible(step):
            return
        css = target.trigger_css or self._last_trigger_css
        if not css:
            return
        loc = self.session.page.locator(css)
        try:
            if loc.count():
                self._click_locator(loc.last, min(3_000, step.timeout_ms))
                self._wait_dropdown()
        except Exception:
            pass

    def _click_opens_dropdown(self, step: Step) -> bool:
        """这一击是不是「展开下拉」。

        判据只看**目标是不是 select 触发器**。候选里的 `field` 不算数：它是定位器
        种类（`CANDIDATE_STABILITY` 里排第 1），不是「这是个下拉」的声明。把它算进来，
        任何带 field 候选的目标都得「点完出现下拉面板」才算过——点输入框、点数字框、
        点文本域全都会被判成没生效，而 `_confirm_dropdown_opened` 的失败路径不走
        `_should_skip_optional`，非必填也照样判红。
        """
        target = step.target
        if target is None:
            return False
        widget = target.widget or ""
        if widget in DROPDOWN_WIDGETS:
            return True
        for cand in target.candidates:
            value = cand.value or ""
            if cand.kind == "role" and value == "combobox":
                return True
            if cand.kind == "css" and is_select_trigger_css(value):
                return True
        return False

    def _wait_dropdown(self) -> None:
        page = self.session.page
        dropdown = page.locator(DROPDOWN_MIXED_VISIBLE)
        try:
            dropdown.first.wait_for(state="visible", timeout=1_500)
        except Exception:
            pass

    def _wait_overlay(self) -> None:
        page = self.session.page
        overlay = page.locator(OVERLAY_WAIT_VISIBLE)
        try:
            if overlay.count():
                return
            overlay.last.wait_for(state="visible", timeout=800)
        except Exception:
            pass

    def _do_assert(self, step: Step) -> StepOutcome:
        kind = step.assert_kind
        page = self.session.page
        if kind == "text_contains":
            body = page.inner_text("body", timeout=step.timeout_ms)
            if step.expected and step.expected in body:
                return StepOutcome(step.id, step.action, "passed", data={"expected": step.expected})
            return StepOutcome(
                step.id,
                step.action,
                "failed",
                "页面文本不包含期望内容",
                data={"expected": step.expected, "actual_excerpt": body[:300]},
            )
        if kind == "element_visible":
            assert step.target is not None
            resolution = self._resolve(step)
            return self._with_drift(step, resolution, data={"matched": resolution.candidate.describe()})
        if kind == "element_count":
            assert step.target is not None and step.expected is not None
            resolution = self._resolve(step)
            actual = resolution.locator.count()
            expected = int(step.expected)
            if actual == expected:
                return self._with_drift(step, resolution, data={"count": actual})
            return StepOutcome(
                step.id,
                step.action,
                "failed",
                "元素数量与期望不一致",
                data={"expected": expected, "actual": actual},
            )
        if kind == "table_row_count_min":
            assert step.expected is not None
            table = page.evaluate(_JS_READ_TABLE)
            actual = int(table.get("totalRows") or 0)
            expected = int(step.expected)
            if actual >= expected:
                return StepOutcome(step.id, step.action, "passed", data={"rows": actual})
            return StepOutcome(
                step.id,
                step.action,
                "failed",
                "表格行数少于期望",
                data={"expected_min": expected, "actual": actual},
            )
        if kind == "no_page_error":
            return self._do_pageHealth(step)
        return StepOutcome(step.id, step.action, "failed", f"不支持的断言：{kind}")

    # ------------------------------------------------------------ 辅助

    def _with_drift(self, step: Step, resolution: Any, data: dict[str, Any] | None = None) -> StepOutcome:
        outcome = StepOutcome(step.id, step.action, "passed", data=data or {})
        if resolution.drifted:
            # 措辞由 LocatorResolution 自己给：环境原因（浮层没出现 / 点不动）下的命中
            # 只是退到兜底撞上的，说成「首选失效」会让人去改本来没问题的候选。
            if resolution.candidate.kind == "fingerprint":
                outcome.drift = f"{resolution.drift_note}：{resolution.candidate.value}"
            else:
                outcome.drift = (
                    f"{resolution.drift_note}，命中第 {resolution.fallback_index + 1} 顺位 "
                    f"{resolution.candidate.describe()}"
                )
        outcome.data["locator"] = resolution.candidate.describe()
        return outcome
