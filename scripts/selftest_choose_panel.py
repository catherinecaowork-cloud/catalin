"""下拉新建：按面板形态判断，不写死字段名。编辑才换已选项。"""

from __future__ import annotations

from autotest_executor.browser.actions import (
    decide_inline_create,
    field_name_from_label,
    is_edit_context,
    panel_choice_kind,
    should_skip_optional_miss,
)
from autotest_protocol import Candidate, Step, Target


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"× {message}")
    print(f"√ {message}")


def main() -> int:
    category = {
        "has_tags": False,
        "has_color": False,
        "has_options": True,
        "has_add": True,
        "has_input": True,
    }
    _assert(decide_inline_create(category) == "lookup", "有选项列表的面板当主数据，不在当前页新建")

    brand = {
        "has_tags": False,
        "has_color": False,
        "has_options": True,
        "has_add": False,
        "has_input": False,
    }
    _assert(decide_inline_create(brand) == "lookup", "纯选项下拉也不能在当前页新建")

    size = {
        "has_tags": True,
        "has_color": False,
        "has_options": False,
        "has_add": True,
        "has_input": True,
    }
    _assert(decide_inline_create(size) == "local", "标签面板可以在当前下拉里新建")

    color = {
        "has_tags": False,
        "has_color": True,
        "has_options": False,
        "has_add": False,
        "has_input": True,
    }
    _assert(decide_inline_create(color) == "local", "色板可以在当前下拉里新建")

    add_only = {
        "has_tags": False,
        "has_color": False,
        "has_options": False,
        "has_add": True,
        "has_input": True,
    }
    _assert(decide_inline_create(add_only) == "local", "面板里自带输入和新增、没有选项列表，也算就地新建")

    _assert(is_edit_context("编辑款式", "选择品类为夹克外套"), "单条编辑流程按流程名识别")
    _assert(not is_edit_context("新建款式", "选择品类为夹克外套"), "新建不走换已选项")
    _assert(is_edit_context("新建款式 → 编辑款式", "编辑款式：选择品类为夹克外套"), "套件里只看当前步骤前缀")
    _assert(not is_edit_context("新建款式 → 编辑款式", "新建款式：选择品类为夹克外套"), "套件里新建步骤仍当新建")
    _assert(not is_edit_context("新建款式 → 编辑款式", "选择品类为夹克外套"), "套件名同时含新建和编辑时，无前缀不当编辑")

    _assert(field_name_from_label("在「新增」弹窗：选择「品牌」为 Gucci") == "品牌", "从步骤文案取出字段名")
    _assert(field_name_from_label("点击「款式」") is None, "菜单点击不当成表单字段")
    _assert(
        should_skip_optional_miss(action="choose", optional=None, required=False, empty_choice=True),
        "表单上没有必填星号的空下拉要跳过",
    )
    _assert(
        not should_skip_optional_miss(action="choose", optional=None, required=True, empty_choice=True),
        "必填空下拉仍要失败",
    )
    _assert(
        should_skip_optional_miss(action="choose", optional=None, required=None, empty_choice=True),
        "下拉是空的、又看不出星号时跳过，不中断保存",
    )
    _assert(
        should_skip_optional_miss(
            action="click",
            optional=None,
            required=None,
            empty_choice=True,
            label="在「新增」弹窗：点击「SAD BLUE」",
        ),
        "弹窗里非必填选项点不到也跳过",
    )
    _assert(
        not should_skip_optional_miss(
            action="click", optional=None, required=None, mutating=True, label="在「新增」弹窗：点击「保存」"
        ),
        "保存失败不能跳过",
    )

    tab = Step(
        id="t1",
        action="click",
        label="在「新增」弹窗：点击「女装」",
        target=Target(
            candidates=[
                Candidate(kind="css", value="#tab-女装"),
                Candidate(kind="role", value="tab", name="女装"),
            ]
        ),
    )
    size = Step(
        id="t2",
        action="click",
        label="在「新增」弹窗：点击「155」",
        target=Target(
            candidates=[
                Candidate(kind="text", value="155"),
                Candidate(kind="css", value="div#pane-女装 > div > div.sizeTag > span.el-tag"),
            ]
        ),
    )
    _assert(panel_choice_kind(tab) == "tab", "女装是尺码面板的 tab")
    _assert(panel_choice_kind(size) == "tag", "155 是尺码标签")

    print("selftest_choose_panel ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
