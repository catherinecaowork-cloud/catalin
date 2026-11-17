"""弹窗「保存」等主按钮不能被上一次下拉的 trigger_css 错标成字段名。"""

from __future__ import annotations

from autotest_executor.compiler import compile_events


def test_save_click_keeps_save_label_despite_stale_trigger_css() -> None:
    events = [
        {
            "type": "click",
            "text": "保存",
            "target": {
                "candidates": [
                    {"kind": "text", "value": "保存"},
                    {"kind": "role", "value": "button", "name": "保存"},
                    {
                        "kind": "css",
                        "value": (
                            "div.el-dialog.is-align-center > footer.el-dialog__footer"
                            " > span.dialog-footer > button.el-button.el-button--primary"
                        ),
                    },
                ],
                "scope": {
                    "kind": "modal",
                    "css": "div.el-dialog.is-align-center",
                    "name": "modal",
                },
                "widget": "control",
                "trigger_css": 'div:has(> .label:text-is("国家/地区")) .el-select__wrapper',
                "fingerprint": {"tag": "span", "name": "保存", "text": "保存", "index": 0},
            },
            "context": {
                "scope": {"kind": "modal", "name": "modal"},
                "trigger_css": 'div:has(> .label:text-is("国家/地区")) .el-select__wrapper',
            },
        }
    ]

    steps, notes = compile_events(events, "http://example.test/page")
    assert notes == []
    assert len(steps) == 2
    save = steps[1]
    assert save["action"] == "click"
    assert save["label"] == "在「modal」弹窗：点击「保存」"
    assert save["mutating"] is True
    assert save["target"].get("trigger_css") is None
    assert any(
        c.get("kind") == "text" and c.get("value") == "保存"
        for c in save["target"]["candidates"]
    )


def test_bring_back_action_not_relabeled_by_select_anchor() -> None:
    events = [
        {
            "type": "click",
            "text": "带回",
            "target": {
                "candidates": [
                    {"kind": "text", "value": "带回"},
                    {"kind": "role", "value": "button", "name": "带回"},
                    {"kind": "css", "value": "button.el-button.is-link"},
                ],
                "scope": {"kind": "modal", "name": "款式"},
                "trigger_css": 'div:has(> .label:text-is("款号")) .el-input__wrapper',
            },
        }
    ]
    steps, _ = compile_events(events, "http://example.test/page")
    assert steps[1]["label"] == "在「款式」弹窗：点击「带回」"
