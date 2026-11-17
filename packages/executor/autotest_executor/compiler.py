"""把录制的原始事件编译成步骤。

人点过的每一下都要留下。清洗只去掉真正的重复空操作，例如同一控件连点
打开、关掉、再打开，以及框架把一次点击派发成两条事件。

清洗规则：
1. 打开同一下拉的连续空点只留最后一次；面板里点的不同项都留下
2. 同一输入框连续填写，只留最后一次
3. 下拉里的过滤字不是业务填值：后面若选中了选项，丢掉过滤 fill
4. 不支持的操作（拖拽、canvas）不产出步骤；文件上传编成 upload，回放固定项目里的图片
5. 点到弹窗壳、表单行、下拉搜索框不算操作
6. 下拉编成 choose。新建记下点到的值（回放可搜索，没有则第一条）；编辑编成换一项，不把已选值当目标
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import re

from autotest_adapters.oinone.selectors import field_label, sanitize_css_selector
from autotest_executor.uploads import DEFAULT_UPLOAD

# 点了这些字样的按钮多半会往被测环境写数据，dry-run 时要跳过。
# 是启发式，所以在确认界面上可以改。
_MUTATING_WORDS = (
    "保存",
    "提交",
    "确定",
    "确认",
    "新增",
    "新建",
    "添加",
    "删除",
    "移除",
    "启用",
    "禁用",
    "发布",
    "归档",
    "导入",
    "生成",
    "创建",
    "save",
    "submit",
    "create",
    "delete",
    "confirm",
)

_MAX_CANDIDATES = 6

_NOISE_CLICK_TEXT = {"请选择", "下拉", "搜索", "添加", "元素", "输入框", "—", "-", "–", "一"}

_EDIT_HINT = re.compile(r"编辑|修改|更新")
_CREATE_HINT = re.compile(r"新建|新增")


def infer_form_kind(
    context: dict[str, Any] | None,
    *,
    intent: str = "",
    form_kind: str | None = None,
) -> str | None:
    """看弹窗标题 / 录制意图，判断这次下拉是新建还是编辑。"""
    if form_kind in {"edit", "create"}:
        return form_kind
    ctx = context or {}
    dialog = str(ctx.get("dialog") or "")
    scope_name = ""
    scope = ctx.get("scope")
    if isinstance(scope, dict):
        scope_name = str(scope.get("name") or "")
    if _CREATE_HINT.search(dialog) or _CREATE_HINT.search(scope_name):
        return "create"
    if _EDIT_HINT.search(dialog) or _EDIT_HINT.search(scope_name):
        return "edit"
    text = intent or ""
    if _CREATE_HINT.search(text) and not _EDIT_HINT.search(text):
        return "create"
    if _EDIT_HINT.search(text) and not _CREATE_HINT.search(text):
        return "edit"
    return None


def _choose_step_fields(
    event: dict[str, Any],
    *,
    where: str,
    field: str,
    value: str,
    intent: str,
) -> dict[str, Any]:
    context = event.get("context") or {}
    kind = infer_form_kind(
        context,
        intent=intent,
        form_kind=event.get("form_kind") or context.get("form_kind"),
    )
    if kind == "edit":
        skip = str(event.get("already_selected") or value or "").strip()
        return {
            "value": skip or value or "__other__",
            "choose_mode": "other",
            "label": f"{where}选择「{field}」换一项",
            **_optional_fields(event),
        }
    return {
        "value": value,
        "choose_mode": "search_or_first",
        "label": f"{where}选择「{field}」为 {value}",
        **_optional_fields(event),
    }


def _optional_fields(event: dict[str, Any]) -> dict[str, Any]:
    ctx = event.get("context") or {}
    required = ctx.get("required")
    if required is False:
        return {"optional": True}
    if required is True:
        return {"optional": False}
    return {}


def _clean_candidates(target: dict[str, Any] | None) -> dict[str, Any] | None:
    """去重并截断候选。留太多没意义，前几个稳定的才有用。"""
    if not target or not target.get("candidates"):
        return None
    seen: set[tuple[str, str]] = set()
    kept: list[dict[str, Any]] = []
    for candidate in target["candidates"]:
        key = (candidate["kind"], candidate["value"])
        if key in seen:
            continue
        seen.add(key)
        item = {k: v for k, v in candidate.items() if v is not None}
        if item.get("kind") == "css" and item.get("value"):
            item["value"] = sanitize_css_selector(str(item["value"]))
        kept.append(item)
        if len(kept) >= _MAX_CANDIDATES:
            break
    if not kept:
        return None
    cleaned: dict[str, Any] = {"candidates": kept}
    scope = target.get("scope")
    if isinstance(scope, dict) and scope.get("kind"):
        cleaned["scope"] = {k: v for k, v in scope.items() if v not in (None, "", [])}
    for key in ("widget", "panel", "trigger_css"):
        value = target.get(key)
        if value:
            cleaned[key] = value
    fingerprint = target.get("fingerprint")
    if isinstance(fingerprint, dict) and fingerprint:
        cleaned["fingerprint"] = {k: v for k, v in fingerprint.items() if v not in (None, "", {})}
    return cleaned


_ANCHOR_LABEL_RE = re.compile(r':(?:text-is|has-text)\("([^"]+)"\)')
_VXE_EPHEMERAL_CSS_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}-\d+-\d+",
    re.I,
)


def _is_anchored_css(candidate: dict[str, Any]) -> bool:
    """同格标签锚定的选择器，如 div:has(> .label:text-is("交货日期")) …"""
    return candidate.get("kind") == "css" and ":has(" in str(candidate.get("value") or "")


def _matrix_label(candidate: dict[str, Any]) -> str | None:
    if candidate.get("kind") != "matrix" or "|" not in str(candidate.get("value") or ""):
        return None
    row, col = str(candidate["value"]).split("|", 1)
    title = str(candidate.get("name") or "颜色尺码").strip()
    return f"{title} {row}×{col}"


def _is_ephemeral_css(candidate: dict[str, Any]) -> bool:
    if candidate.get("kind") != "css":
        return False
    value = str(candidate.get("value") or "")
    return bool(_VXE_EPHEMERAL_CSS_RE.search(value))


def _anchored_field_labels(candidates: list[dict[str, Any]]) -> set[str]:
    labels: set[str] = set()
    for candidate in candidates:
        if not _is_anchored_css(candidate):
            continue
        match = _ANCHOR_LABEL_RE.search(str(candidate.get("value") or ""))
        if match:
            labels.add(match.group(1))
    return labels


def _prune_redundant_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """删掉已知会空等的候选，避免回放从失效首选开始等 20s+。"""
    if not candidates:
        return candidates
    has_matrix = any(item.get("kind") == "matrix" for item in candidates)
    anchor_labels = _anchored_field_labels(candidates)
    matrix_titles = {
        str(item.get("name") or "颜色尺码").strip()
        for item in candidates
        if item.get("kind") == "matrix"
    }
    kept: list[dict[str, Any]] = []
    for candidate in candidates:
        kind = candidate.get("kind")
        value = str(candidate.get("value") or "")
        if has_matrix:
            if kind == "label" and value in matrix_titles:
                continue
            if _is_ephemeral_css(candidate):
                continue
        if anchor_labels:
            if kind == "label" and value in anchor_labels:
                continue
            if kind == "css" and not _is_anchored_css(candidate):
                if "ant-picker" in value and ":has(" not in value:
                    continue
        kept.append(candidate)
    return kept or list(candidates)


def _fill_candidate_rank(candidate: dict[str, Any]) -> int:
    kind = candidate.get("kind")
    if kind == "field":
        return 0
    if kind == "matrix":
        return 0
    if _is_anchored_css(candidate):
        return 1
    if kind == "testid":
        return 2
    if kind == "label":
        return 3
    if kind == "placeholder":
        return 4
    if kind == "role":
        name = str(candidate.get("name") or "")
        if name.isdigit() or len(name) <= 3:
            return 9
        return 5
    if kind == "css":
        return 6
    if kind == "text":
        return 7
    return 8


def _prioritize_fill_candidates(target: dict[str, Any] | None) -> dict[str, Any] | None:
    if not target or not target.get("candidates"):
        return target
    kept = []
    for candidate in target["candidates"]:
        if candidate.get("kind") == "role":
            name = str(candidate.get("name") or "")
            if name.isdigit() or len(name) <= 3:
                continue
        kept.append(candidate)
    if not kept:
        kept = list(target["candidates"])
    kept = _prune_redundant_candidates(kept)
    ranked = sorted(kept, key=_fill_candidate_rank)
    out = dict(target)
    out["candidates"] = ranked[:_MAX_CANDIDATES]
    return out


def _prioritize_click_candidates(
    target: dict[str, Any] | None, event: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """按钮优先用可见文字。打开下拉时优先字段，避免点到标签文字打不开面板。"""
    if not target or not target.get("candidates"):
        return target
    prefer_field = bool(event and _is_combobox(event) and event.get("type") == "click")
    pruned = _prune_redundant_candidates(list(target["candidates"]))
    ranked = sorted(
        pruned,
        key=lambda item: _click_candidate_rank(item, prefer_field=prefer_field),
    )
    out = dict(target)
    out["candidates"] = ranked
    return out


def _click_candidate_rank(candidate: dict[str, Any], *, prefer_field: bool = False) -> int:
    kind = candidate.get("kind")
    value = str(candidate.get("value") or "")
    if kind == "matrix":
        return 0
    if kind == "testid":
        return 0
    if kind == "css" and (
        "el-select__wrapper" in value
        or "ant-select-selector" in value
        or (".el-select" in value and "dropdown" not in value and "popper" not in value)
    ):
        return 1
    if kind == "css" and value.startswith("[data-action-name"):
        return 2
    if kind == "css" and (value.startswith("#tab-") or "#tab-" in value):
        return 2
    if _is_anchored_css(candidate):
        return 3
    if prefer_field and kind == "field":
        return 3
    if kind == "text":
        return 4
    if kind == "label":
        return 5
    if kind == "field":
        return 6
    if kind == "role":
        return 7
    return 8


def _with_scope(target: dict[str, Any] | None, context: dict[str, Any] | None) -> dict[str, Any] | None:
    if not target:
        return None
    if target.get("scope"):
        return target
    scope = (context or {}).get("scope")
    if isinstance(scope, dict) and scope.get("kind"):
        target = dict(target)
        target["scope"] = {k: v for k, v in scope.items() if v not in (None, "", [])}
    return target


def _stamp_widget_meta(target: dict[str, Any] | None, context: dict[str, Any] | None) -> dict[str, Any] | None:
    if not target:
        return None
    ctx = context or {}
    out = dict(target)
    for key in ("widget", "panel", "trigger_css"):
        value = target.get(key) or ctx.get(key)
        if value:
            out[key] = value
    if not out.get("fingerprint") and isinstance(ctx.get("fingerprint"), dict):
        out["fingerprint"] = ctx["fingerprint"]
    return out


def _same_element(a: dict[str, Any] | None, b: dict[str, Any] | None) -> bool:
    if not a or not b:
        return False
    first_a = a["candidates"][0]
    first_b = b["candidates"][0]
    if first_a.get("kind") != first_b.get("kind"):
        return False
    if first_a.get("kind") == "role":
        # 两个 button 首候选都是 role=button，必须比 name（带回 vs 新增PO）
        return first_a.get("value") == first_b.get("value") and first_a.get("name") == first_b.get("name")
    return first_a.get("value") == first_b.get("value")


def _field_key(target: dict[str, Any] | None) -> tuple[str, str] | None:
    if not target:
        return None
    for candidate in target.get("candidates", []):
        if candidate.get("kind") == "field" and candidate.get("value"):
            return ("field", str(candidate["value"]))
    return None


def _same_open_control(a: dict[str, Any] | None, b: dict[str, Any] | None) -> bool:
    """两次都是点开同一个下拉，不是面板里点不同项。"""
    if not a or not b:
        return False
    scope_a = a.get("scope") or {}
    scope_b = b.get("scope") or {}
    if scope_a.get("kind") == "dropdown" or scope_b.get("kind") == "dropdown":
        return False
    name_a = str(scope_a.get("name") or "").strip()
    name_b = str(scope_b.get("name") or "").strip()
    if name_a and name_b and name_a != name_b:
        return False
    css_a = a.get("trigger_css")
    css_b = b.get("trigger_css")
    if css_a and css_a == css_b:
        return True
    return _same_element(a, b) or (
        _field_key(a) is not None and _field_key(a) == _field_key(b)
    )


def _same_control(a: dict[str, Any] | None, b: dict[str, Any] | None) -> bool:
    if _same_element(a, b):
        return True
    key_a = _field_key(a)
    return bool(key_a) and key_a == _field_key(b)


_ACTION_CLICK_WORDS = {
    "保存",
    "提交",
    "确定",
    "确认",
    "取消",
    "带回",
    "选择",
    "save",
    "submit",
    "ok",
}


def _is_action_control(
    candidates: list[dict[str, Any]], values: str, text: str
) -> bool:
    """保存/确定这类按钮经常套在 DialogWidget 里，不能当弹窗壳丢掉。"""
    if any(
        c.get("kind") == "role" and c.get("value") in {"button", "menuitem", "link"}
        for c in candidates
    ):
        return True
    if (
        "[data-action-name" in values
        or "oio-action" in values
        or "ant-btn" in values
        or "el-button" in values
    ):
        return True
    names = {str(text or "").strip().lower()}
    names.update(
        str(c.get("value") or "").strip().lower()
        for c in candidates
        if c.get("kind") in {"text", "label"}
    )
    names.update(
        str(c.get("name") or "").strip().lower()
        for c in candidates
        if c.get("kind") == "role"
    )
    return any(word in names for word in _ACTION_CLICK_WORDS)


def _is_chrome_click(event: dict[str, Any]) -> bool:
    """点到弹窗壳、整表单行、下拉搜索框，不是业务操作。"""
    if event.get("type") != "click":
        return False
    target = event.get("target") or {}
    candidates = target.get("candidates") or []
    scope_kind = (target.get("scope") or {}).get("kind")
    kinds = {c.get("kind") for c in candidates}
    values = " ".join(str(c.get("value") or "") for c in candidates)
    text = str(event.get("text") or "")
    if _is_action_control(candidates, values, text):
        return False
    if any(c.get("kind") == "role" and c.get("value") == "dialog" for c in candidates):
        return True
    if "DialogWidget-" in values and "field" not in kinds:
        return True
    if "ant-row" in values and "oio-row" in values:
        return True
    if "ant-spin-container" in values and "field" not in kinds:
        return True
    if scope_kind == "dropdown" and any(
        c.get("kind") == "role" and c.get("value") in {"textbox", "searchbox", "combobox"}
        for c in candidates
    ):
        return True
    return False


_DATE_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PICKER_DATE_MARKERS = ("ant-picker-cell", "ant-picker-dropdown", "el-date-table")


def _picker_date_from_event(event: dict[str, Any]) -> str | None:
    for candidate in (event.get("target") or {}).get("candidates") or []:
        value = str(candidate.get("value") or "").strip()
        if _DATE_ISO.fullmatch(value):
            return value
        if "title=" in value:
            match = re.search(r'title="(\d{4}-\d{2}-\d{2})"', value)
            if match:
                return match.group(1)
    text = str(event.get("text") or event.get("value") or "").strip()
    if _DATE_ISO.fullmatch(text):
        return text
    return None


def _is_picker_date_event(event: dict[str, Any]) -> bool:
    if event.get("type") != "click":
        return False
    blob = " ".join(
        str(c.get("value") or "")
        for c in (event.get("target") or {}).get("candidates") or []
    ).lower()
    return any(marker in blob for marker in _PICKER_DATE_MARKERS)


def _picker_field_target(event: dict[str, Any]) -> dict[str, Any]:
    target = dict(event.get("target") or {})
    ctx = event.get("context") or {}
    candidates: list[dict[str, Any]] = []
    for candidate in target.get("candidates") or []:
        if candidate.get("kind") == "field" and candidate.get("value"):
            candidates.append({"kind": "field", "value": candidate["value"]})
    for candidate in target.get("candidates") or []:
        if candidate.get("kind") == "matrix" and candidate.get("value"):
            candidates.append(
                {
                    "kind": "matrix",
                    "value": candidate["value"],
                    "name": candidate.get("name"),
                }
            )
    for candidate in target.get("candidates") or []:
        if _is_anchored_css(candidate):
            candidates.append({"kind": "css", "value": candidate["value"]})
    trigger = target.get("trigger_css") or ctx.get("trigger_css")
    if trigger and not any(c.get("value") == trigger for c in candidates):
        candidates.append({"kind": "css", "value": trigger})
    if not candidates:
        candidates = list(target.get("candidates") or [])
    out = {
        "candidates": candidates,
        "scope": target.get("scope"),
        "widget": target.get("widget") or ctx.get("widget") or "ant-date-picker",
    }
    if trigger:
        out["trigger_css"] = trigger
    return out


_DROPDOWN_SCROLL_MARKERS = (
    "el-select-dropdown",
    "select-options",
    "select-body",
    "ant-select-dropdown",
    "el-scrollbar__view",
    "el-scrollbar__wrap",
)


def _is_ephemeral_scroll(event: dict[str, Any]) -> bool:
    """下拉/面板内滚动只为找选项，不应落成回放步骤。"""
    if event.get("type") != "scroll":
        return False
    target = event.get("target") or {}
    scope_kind = (target.get("scope") or {}).get("kind")
    if scope_kind == "dropdown":
        return True
    blob = " ".join(str(c.get("value") or "") for c in target.get("candidates") or []).lower()
    if any(marker in blob for marker in _DROPDOWN_SCROLL_MARKERS):
        return True
    context = event.get("context") or {}
    if context.get("widget") in _COMBO_WIDGETS:
        return True
    return False


def _is_filter_fill(event: dict[str, Any]) -> bool:
    """下拉里写着「搜索」的过滤框不是业务填值。"""
    if event.get("type") != "fill":
        return False
    name = _field_name(event)
    if "搜索" in name:
        return True
    target = event.get("target") or {}
    for candidate in target.get("candidates", []):
        value = str(candidate.get("value") or "")
        if candidate.get("kind") == "placeholder" and "搜索" in value:
            return True
    return False


def _is_file_upload_fill(event: dict[str, Any]) -> bool:
    """文件选择框的 value 只能是 C:\\fakepath\\...，不能当普通填值回放。"""
    if event.get("type") != "fill":
        return False
    value = str(event.get("value") or "")
    if "fakepath" in value.lower():
        return True
    target = event.get("target") or {}
    blob = " ".join(str(c.get("value") or "") for c in target.get("candidates") or [])
    return "el-upload__input" in blob or 'type="file"' in blob or "[type=file]" in blob


_COMBO_WIDGETS = {"combobox", "el-select", "ant-select", "native-select"}


def _is_combobox(event: dict[str, Any]) -> bool:
    context = event.get("context") or {}
    widget = context.get("widget") or (event.get("target") or {}).get("widget")
    if widget in _COMBO_WIDGETS:
        return True
    target = event.get("target") or {}
    for candidate in target.get("candidates", []):
        kind = candidate.get("kind")
        value = str(candidate.get("value") or "")
        if kind == "role" and value in {"combobox", "listbox"}:
            return True
        if "ant-select" in value or "el-select" in value:
            return True
    return False


def _describe_where(context: dict[str, Any], target: dict[str, Any] | None = None) -> str:
    scope = ((target or {}).get("scope") or (context or {}).get("scope") or {})
    kind = scope.get("kind")
    name = scope.get("name") or (context or {}).get("dialog")
    dialog = (context or {}).get("dialog")
    # 下拉浮层挂到 body 上，标题常借到外面的弹窗名。那是弹窗，不是「新增选项」。
    if kind == "dropdown":
        host = dialog if dialog and dialog not in {"下拉", "dropdown"} else name
        if host and host not in {"下拉", "dropdown"}:
            return f"在「{host}」弹窗："
        return "在下拉中："
    if kind in {"modal", "drawer"}:
        layer = "抽屉" if kind == "drawer" else "弹窗"
        return f"在「{name or layer}」{layer}："
    return f"在「{dialog}」弹窗：" if dialog else ""


def _label_from_scope(event: dict[str, Any]) -> str | None:
    target = event.get("target") or {}
    context = event.get("context") or {}
    scope = target.get("scope") or context.get("scope") or {}
    path = str(scope.get("path") or "")
    if "字段「" not in path:
        return None
    start = path.find("字段「") + 3
    end = path.find("」", start)
    if end <= start:
        return None
    label = path[start:end].strip()
    return label if label and label not in _NOISE_CLICK_TEXT else None


def _scope_path_chain(event: dict[str, Any]) -> str:
    target = event.get("target") or {}
    context = event.get("context") or {}
    scope = target.get("scope") or context.get("scope") or {}
    path = str(scope.get("path") or "")
    return path.rsplit(" / ", 1)[-1] if path else ""


def _modal_scope_name(event: dict[str, Any]) -> str:
    target = event.get("target") or {}
    context = event.get("context") or {}
    scope = target.get("scope") or context.get("scope") or {}
    return str(scope.get("name") or "").strip()


def _is_empty_placeholder_click(event: dict[str, Any]) -> bool:
    target = event.get("target") or {}
    candidates = target.get("candidates") or []
    values = " ".join(str(c.get("value") or "") for c in candidates)
    path = _scope_path_chain(event)
    blob = f"{values} {path}"
    return "empty-placeholder" in blob or (
        "info-wrap" in blob and ("form-section" in blob or "section:" in blob)
    )


def _label_from_section_path(event: dict[str, Any]) -> str | None:
    """Oinone 空态加号区：section:1.选择款式信息>...>div.empty-placeholder。"""
    chain = _scope_path_chain(event)
    if not chain:
        return None
    for part in chain.split(">"):
        if not part.startswith("section:"):
            continue
        raw = part.split(":", 1)[1].strip()
        title = re.sub(r"^\d+\.\s*", "", raw).strip()
        title = re.sub(r"信息$", "", title).strip()
        if not title:
            continue
        if "加号" in title:
            return title
        return f"{title}加号"
    return None


def _placeholder_click_label(event: dict[str, Any]) -> str | None:
    if event.get("type") != "click":
        return None
    section = _label_from_section_path(event)
    if section:
        return section
    if _is_empty_placeholder_click(event):
        return "加号"
    text = str(event.get("text") or "").strip().lower()
    if text == "plus":
        return "加号"
    return None


def _label_from_path_chain(event: dict[str, Any]) -> str | None:
    """Oinone form-container 把「*交货日期」写进 DOM 链路径，如 div:*交货日期>div>input。"""
    target = event.get("target") or {}
    context = event.get("context") or {}
    scope = target.get("scope") or context.get("scope") or {}
    path = str(scope.get("path") or "")
    if not path:
        return None
    chain = path.rsplit(" / ", 1)[-1]
    for part in reversed(chain.split(">")):
        if ":" not in part:
            continue
        text = part.split(":", 1)[1].strip().lstrip("*").strip()
        if not text or text in _NOISE_CLICK_TEXT:
            continue
        if len(text) == 1 and not text.isdigit():
            continue
        if re.match(r"^[\u4e00-\u9fffA-Za-z0-9/（）()-]{2,16}$", text):
            return text
    return None


def _known_field_label(event: dict[str, Any]) -> str | None:
    """Oinone 已知 data-name → 中文名；未知字段名不算「认识」。"""
    target = event.get("target") or {}
    context = event.get("context") or {}
    for candidate in target.get("candidates") or []:
        if candidate.get("kind") == "field" and candidate.get("value"):
            dn = str(candidate["value"])
            mapped = field_label(dn)
            if mapped != dn:
                return mapped
    trigger = str(target.get("trigger_css") or context.get("trigger_css") or "")
    match = re.search(r'data-name="([^"]+)"', trigger)
    if match:
        dn = match.group(1)
        mapped = field_label(dn)
        if mapped != dn:
            return mapped
    return None


def _anchor_label(event: dict[str, Any]) -> str | None:
    """从锚定选择器里读回字段名，它就是录制时同格标签的原文。"""
    target = event.get("target") or {}
    context = event.get("context") or {}
    blobs = [str(c.get("value") or "") for c in target.get("candidates") or []]
    blobs.append(str(target.get("trigger_css") or context.get("trigger_css") or ""))
    for blob in blobs:
        if ":has(" not in blob:
            continue
        match = _ANCHOR_LABEL_RE.search(blob)
        if match:
            name = match.group(1).strip()
            if name and name not in _NOISE_CLICK_TEXT:
                return name
    return None


def _field_name(event: dict[str, Any]) -> str:
    target = event.get("target") or {}
    for candidate in target.get("candidates") or []:
        labeled = _matrix_label(candidate)
        if labeled:
            return labeled
    known = _known_field_label(event)
    if known:
        return known
    anchored = _anchor_label(event)
    if anchored:
        return anchored
    chain_label = _label_from_path_chain(event)
    if chain_label:
        return chain_label
    scope_label = _label_from_scope(event)
    if scope_label:
        return scope_label
    context = event.get("context") or {}
    label = str(context.get("label") or "").strip()
    if label and label not in _NOISE_CLICK_TEXT:
        return label
    target = event.get("target") or {}
    for candidate in target.get("candidates", []):
        if candidate["kind"] == "field" and candidate.get("value"):
            return field_label(str(candidate["value"]))
        if candidate["kind"] in {"placeholder", "label"}:
            value = str(candidate.get("value") or "").strip()
            if value and value not in _NOISE_CLICK_TEXT and not re.match(
                r"^(请输入|请选择|请填写)$", value
            ):
                return value
    return "输入框"


_ICON_CLICK_NAMES = {
    "pushpin",
    "pin",
    "menu",
    "ellipsis",
    "more",
    "caret",
}


def _click_in_panel(event: dict[str, Any]) -> bool:
    context = event.get("context") or {}
    target = event.get("target") or {}
    scope = target.get("scope") or context.get("scope") or {}
    return scope.get("kind") == "dropdown" or bool(target.get("panel"))


def _panel_option_text(event: dict[str, Any]) -> str | None:
    """下拉里点的是选项值，不能用旁边的分组名/字段名当步骤标题。"""
    if not _click_in_panel(event):
        return None
    text = str(event.get("text") or "").strip()
    if text and text.lower() not in _ICON_CLICK_NAMES and text not in _NOISE_CLICK_TEXT:
        if text.lower() == "plus":
            return "加号"
        modal = _modal_scope_name(event)
        if not (modal and text == modal):
            return text
    for candidate in (event.get("target") or {}).get("candidates") or []:
        if candidate.get("kind") != "text":
            continue
        value = str(candidate.get("value") or "").strip()
        if value and value.lower() not in _ICON_CLICK_NAMES and value not in _NOISE_CLICK_TEXT:
            return "加号" if value.lower() == "plus" else value
    return None


def _action_click_name(event: dict[str, Any]) -> str | None:
    """保存/确定等动作按钮优先用自身文案，不被残留 trigger_css 字段名盖住。"""
    target = event.get("target") or {}
    candidates = target.get("candidates") or []
    text = str(event.get("text") or "").strip()
    values = " ".join(str(c.get("value") or "") for c in candidates)
    if not _is_action_control(candidates, values, text):
        return None

    names: list[str] = []
    if text:
        names.append(text)
    fingerprint = target.get("fingerprint")
    if isinstance(fingerprint, dict):
        for key in ("text", "name"):
            value = str(fingerprint.get(key) or "").strip()
            if value:
                names.append(value)
    for candidate in candidates:
        kind = candidate.get("kind")
        if kind in {"text", "label"}:
            value = str(candidate.get("value") or "").strip()
            if value:
                names.append(value)
        elif kind == "role" and candidate.get("name"):
            names.append(str(candidate["name"]).strip())

    modal = _modal_scope_name(event)
    for name in names:
        if not name or name in _NOISE_CLICK_TEXT:
            continue
        if name.lower() in _ICON_CLICK_NAMES:
            continue
        if modal and name == modal:
            continue
        return "加号" if name.lower() == "plus" else name
    return None


def _click_name(event: dict[str, Any]) -> str:
    placeholder = _placeholder_click_label(event)
    if placeholder:
        return placeholder
    action_name = _action_click_name(event)
    if action_name:
        return action_name
    modal = _modal_scope_name(event)
    target = event.get("target") or {}
    candidates = target.get("candidates") or []
    for candidate in candidates:
        labeled = _matrix_label(candidate)
        if labeled:
            return labeled
    panel_name = _panel_option_text(event)
    if panel_name:
        return panel_name
    values = " ".join(str(c.get("value") or "") for c in candidates)
    text = str(event.get("text") or "").strip()

    def _reject_modal_echo(name: str) -> bool:
        return bool(modal and name == modal and not _is_action_control(candidates, values, text))

    if not _click_in_panel(event):
        known = _known_field_label(event)
        if known:
            return known
        anchored = _anchor_label(event)
        if anchored:
            return anchored
        chain_label = _label_from_path_chain(event)
        if chain_label:
            return chain_label
    scope_label = _label_from_scope(event)
    if scope_label and not _reject_modal_echo(scope_label):
        return scope_label
    if text and text.lower() not in _ICON_CLICK_NAMES and text not in _NOISE_CLICK_TEXT:
        if text.lower() == "plus":
            return "加号"
        if not _reject_modal_echo(text):
            return text
    context = event.get("context") or {}
    label = str(context.get("label") or "").strip()
    if label and label not in _NOISE_CLICK_TEXT and not _reject_modal_echo(label):
        return label
    for candidate in candidates:
        if candidate["kind"] == "field" and candidate.get("value"):
            return field_label(str(candidate["value"]))
        if candidate["kind"] in {"text", "label", "placeholder"}:
            value = str(candidate.get("value") or "").strip()
            if value and value.lower() not in _ICON_CLICK_NAMES and value not in _NOISE_CLICK_TEXT:
                if value.lower() == "plus":
                    return "加号"
                if not _reject_modal_echo(value):
                    return value
        if candidate["kind"] == "role" and candidate.get("name"):
            if candidate.get("value") == "dialog":
                continue
            name = str(candidate["name"])
            if _reject_modal_echo(name):
                continue
            return name
    return "元素"


def _strip_stale_combo_meta(event: dict[str, Any]) -> dict[str, Any]:
    """动作按钮上的 trigger_css 多半是上一次下拉残留，会污染标签与回放。"""
    target = event.get("target")
    if not isinstance(target, dict) or not target.get("trigger_css"):
        return event
    candidates = target.get("candidates") or []
    text = str(event.get("text") or "").strip()
    values = " ".join(str(c.get("value") or "") for c in candidates)
    if not _is_action_control(candidates, values, text):
        return event
    cleaned = dict(event)
    next_target = dict(target)
    next_target.pop("trigger_css", None)
    cleaned["target"] = next_target
    context = cleaned.get("context")
    if isinstance(context, dict) and context.get("trigger_css"):
        next_context = dict(context)
        next_context.pop("trigger_css", None)
        cleaned["context"] = next_context
    return cleaned


def _click_is_mutating(event: dict[str, Any], name: str) -> bool:
    if _is_mutating(name):
        return True
    if _is_mutating(str(event.get("text") or "")):
        return True
    target = event.get("target") or {}
    for candidate in target.get("candidates") or []:
        if candidate.get("kind") in {"text", "label"} and _is_mutating(
            str(candidate.get("value") or "")
        ):
            return True
        if candidate.get("kind") == "role" and _is_mutating(str(candidate.get("name") or "")):
            return True
    fingerprint = target.get("fingerprint")
    if isinstance(fingerprint, dict):
        if _is_mutating(str(fingerprint.get("text") or "")) or _is_mutating(
            str(fingerprint.get("name") or "")
        ):
            return True
    return False


def _is_mutating(name: str) -> bool:
    lowered = name.lower()
    return any(word.lower() in lowered for word in _MUTATING_WORDS)


def _prefilter(events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    notes: list[str] = []
    kept: list[dict[str, Any]] = []

    for event in events:
        kind = event.get("type")
        if kind == "stop":
            continue
        if kind == "unsupported":
            reason = event.get("reason", "未知操作")
            note = f"{reason}没有被录上，回放时需要手工补一步"
            if note not in notes:
                notes.append(note)
            continue
        if not event.get("target"):
            continue
        event = dict(event)
        event["target"] = _with_scope(
            _stamp_widget_meta(_clean_candidates(event["target"]), event.get("context")),
            event.get("context"),
        )
        if not event["target"]:
            continue
        if _is_filter_fill(event):
            continue
        if _is_file_upload_fill(event) or event.get("type") == "upload":
            event = dict(event)
            event["type"] = "upload"
            if not event.get("value") or "fakepath" in str(event.get("value") or "").lower():
                event["value"] = DEFAULT_UPLOAD
        if _is_chrome_click(event):
            continue
        if _is_ephemeral_scroll(event):
            continue
        if event.get("type") == "click":
            event = _strip_stale_combo_meta(event)
        kept.append(event)

    filtered: list[dict[str, Any]] = []
    for index, event in enumerate(kept):
        # 同一下拉连点打开/关掉，只留最后一次。面板里点的不同项都留下。
        if (
            event["type"] == "click"
            and filtered
            and filtered[-1]["type"] == "click"
            and _same_open_control(filtered[-1]["target"], event["target"])
        ):
            filtered[-1] = event
            continue
        # 同一框连续输入或同一容器连续滚动，留最后一次
        if (
            event["type"] in {"fill", "scroll"}
            and filtered
            and filtered[-1]["type"] == event["type"]
            and _same_control(filtered[-1]["target"], event["target"])
        ):
            filtered[-1] = event
            continue
        # 同一选项连发两条 choose 才合并；多选下拉的不同值都留下
        if (
            event["type"] == "choose"
            and filtered
            and filtered[-1]["type"] == "choose"
            and _same_control(filtered[-1]["target"], event["target"])
            and filtered[-1].get("value") == event.get("value")
        ):
            filtered[-1] = event
            continue
        # 下拉搜索框里敲的过滤字不是填值；点开下拉的那一下要留着
        if event["type"] == "fill" and (
            index + 1 < len(kept)
            and kept[index + 1].get("type") == "choose"
            and _same_control(kept[index + 1].get("target"), event["target"])
        ):
            continue
        if event["type"] == "fill" and _is_combobox(event):
            event = dict(event)
            event["type"] = "choose"
        filtered.append(event)

    return filtered, notes


def compile_events(
    events: list[dict[str, Any]], start_url: str, *, intent: str = ""
) -> tuple[list[dict[str, Any]], list[str]]:
    """原始事件 → 步骤草稿 + 需要人工留意的提示。"""
    filtered, notes = _prefilter(events)

    steps: list[dict[str, Any]] = [
        {"id": "s1", "action": "goto", "value": start_url, "label": "打开起始页"}
    ]

    for event in filtered:
        index = len(steps) + 1
        step_id = f"s{index}"
        context = event.get("context") or {}
        where = _describe_where(context, event.get("target"))
        kind = event["type"]

        if kind == "click":
            date_val = _picker_date_from_event(event)
            if date_val and _is_picker_date_event(event):
                field = _field_name(event)
                steps.append(
                    {
                        "id": step_id,
                        "action": "fill",
                        "target": _picker_field_target(event),
                        "value": date_val,
                        "label": f"{where}填写「{field}」",
                        "mutating": True,
                        **_optional_fields(event),
                    }
                )
                continue
            name = _click_name(event)
            steps.append(
                {
                    "id": step_id,
                    "action": "click",
                    "target": _prioritize_click_candidates(event["target"], event),
                    "label": f"{where}点击「{name}」",
                    "mutating": _click_is_mutating(event, name),
                    **_optional_fields(event),
                }
            )
        elif kind in {"fill", "choose"}:
            field = _field_name(event)
            value = event.get("value") or event.get("text") or ""
            as_choose = kind == "choose" or _is_combobox(event)
            if as_choose:
                chosen = _choose_step_fields(
                    event, where=where, field=field, value=value, intent=intent
                )
                steps.append(
                    {
                        "id": step_id,
                        "action": "choose",
                        "target": _prioritize_fill_candidates(event["target"]),
                        "mutating": False,
                        **chosen,
                    }
                )
            else:
                steps.append(
                    {
                        "id": step_id,
                        "action": "fill",
                        "target": _prioritize_fill_candidates(event["target"]),
                        "value": value,
                        "label": f"{where}填写「{field}」",
                        "mutating": True,
                        **_optional_fields(event),
                    }
                )
        elif kind == "select":
            field = _field_name(event)
            shown = event.get("text") or event.get("value") or ""
            steps.append(
                {
                    "id": step_id,
                    "action": "select",
                    "target": event["target"],
                    "value": event.get("value") or "",
                    "label": f"{where}选择「{field}」为 {shown}",
                    "mutating": True,
                    **_optional_fields(event),
                }
            )
        elif kind == "scroll":
            shown = event.get("value") or "0"
            steps.append(
                {
                    "id": step_id,
                    "action": "scroll",
                    "target": event["target"],
                    "value": str(shown),
                    "label": f"{where}滚动容器到 {shown}",
                    "mutating": False,
                }
            )
        elif kind == "upload":
            field = _field_name(event)
            value = event.get("value") or DEFAULT_UPLOAD
            steps.append(
                {
                    "id": step_id,
                    "action": "upload",
                    "target": event["target"],
                    "value": value,
                    "label": f"{where}上传「{field}」为 {Path(value).name}",
                    "mutating": True,
                    **_optional_fields(event),
                }
            )
        elif kind == "press":
            # DSL 里没有独立的按键动作，回车通常等价于提交
            steps.append(
                {
                    "id": step_id,
                    "action": "click",
                    "target": event["target"],
                    "label": f"{where}回车提交",
                    "mutating": True,
                }
            )

    if len(steps) == 1:
        notes.append("除了打开页面之外没录到任何操作")

    return steps, notes
