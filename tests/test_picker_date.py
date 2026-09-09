from autotest_adapters.oinone.selectors import sanitize_css_selector
from autotest_executor.browser.actions import (
    _looks_like_picker_date_click,
    _picker_date_value,
)
from autotest_protocol import Candidate, Step, Target, TargetScope


def test_sanitize_css_removes_focus_state() -> None:
    raw = "div.el-select > div.el-select__wrapper.is-focused"
    assert sanitize_css_selector(raw) == "div.el-select > div.el-select__wrapper"


def test_picker_date_value_from_click_step() -> None:
    step = Step(
        id="s1",
        action="click",
        target=Target(
            candidates=[
                Candidate(kind="text", value="2026-09-30"),
                Candidate(
                    kind="css",
                    value="tbody > tr > td.ant-picker-cell > div.ant-picker-cell-inner",
                ),
            ],
            scope=TargetScope(kind="modal", name="新增"),
        ),
        label="在「新增」弹窗：点击「2026-09-30」",
    )
    assert _picker_date_value(step) == "2026-09-30"
    assert _looks_like_picker_date_click(step)

