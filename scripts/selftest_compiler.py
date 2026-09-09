"""编译器自测。

清洗规则是后面所有东西的地基，必须能单独验证：
同一控件连点被合并、人点过的点击要留下、不支持的操作变成提示、mutating 标记正确。
"""

from __future__ import annotations

from autotest_executor.compiler import compile_events

TARGET_INPUT = {
    "candidates": [
        {"kind": "placeholder", "value": "请输入您的账号", "name": None},
        {"kind": "css", "value": "#form_item_login"},
        {"kind": "css", "value": "input#form_item_login"},
    ]
}
TARGET_SAVE = {
    "candidates": [
        {"kind": "role", "value": "button", "name": "保存"},
        {"kind": "text", "value": "保存"},
        {"kind": "css", "value": "button.ant-btn"},
    ]
}
TARGET_MENU = {
    "candidates": [
        {"kind": "text", "value": "款式"},
        {"kind": "css", "value": "a.menu-item"},
    ]
}


def _assert(cond: bool, message: str) -> None:
    if not cond:
        raise SystemExit(f"× {message}")
    print(f"√ {message}")


def main() -> int:
    events = [
        {
            "type": "click",
            "ts": 1000,
            "target": TARGET_MENU,
            "text": "款式",
            "context": {},
        },
        # 规则 1：150ms 内同一元素重复点击
        {
            "type": "click",
            "ts": 1080,
            "target": TARGET_MENU,
            "text": "款式",
            "context": {},
        },
        # 超过 150ms 的连续重复点击也应合并
        {
            "type": "click",
            "ts": 1800,
            "target": TARGET_MENU,
            "text": "款式",
            "context": {},
        },
        # 点进输入框也要留下
        {
            "type": "click",
            "ts": 2000,
            "target": TARGET_INPUT,
            "text": "",
            "context": {"label": "账号", "dialog": "新增款式"},
        },
        {
            "type": "fill",
            "ts": 2600,
            "target": TARGET_INPUT,
            "value": "款式A",
            "context": {
                "label": "账号",
                "dialog": "新增款式",
                "scope": {
                    "kind": "modal",
                    "css": ".ant-modal-content",
                    "name": "新增款式",
                    "path": "modal「新增款式」",
                },
            },
        },
        {
            "type": "fill",
            "ts": 6100,
            "target": {
                "candidates": [
                    {"kind": "label", "value": "颜色", "name": None},
                    {"kind": "css", "value": "#color"},
                ]
            },
            "value": "随便新建一个蓝",
            "context": {"label": "颜色", "dialog": "新增款式"},
        },
        {
            "type": "click",
            "ts": 7000,
            "target": TARGET_SAVE,
            "text": "保存",
            "context": {"dialog": "新增款式"},
        },
        {
            "type": "unsupported",
            "ts": 4100,
            "reason": "拖拽操作",
            "context": {},
        },
    ]

    steps, notes = compile_events(events, "http://example.test/app")

    _assert(steps[0]["action"] == "goto" and steps[0]["value"] == "http://example.test/app", "第一步是打开起始页")
    actions = [s["action"] for s in steps[1:]]
    _assert(actions == ["click", "click", "fill", "fill", "click"], f"清洗后动作应为 click/click/fill/fill/click，实际 {actions}")
    _assert(sum(1 for s in steps if s.get("label") == "点击「款式」") == 1, "连续点击款式只留一次")
    _assert(any("账号" in s.get("label", "") and s["action"] == "click" for s in steps), "点进输入框的点击也保留")
    fill = next(s for s in steps if s["action"] == "fill" and s.get("value") == "款式A")
    _assert(fill["value"] == "款式A", "普通 fill 保留录到的值")
    _assert(fill["mutating"] is True, "fill 标为 mutating")
    _assert("新增款式" in fill["label"], "fill 带弹窗前缀")
    color = next(s for s in steps if "颜色" in s.get("label", ""))
    _assert(color["action"] == "fill" and color["value"] == "随便新建一个蓝", "颜色保留录到的值，不改成固定主数据")
    _assert(not any("SAD BLUE" in n for n in notes), "不再写主数据替换提示")
    save = next(s for s in steps if "保存" in s.get("label", ""))
    _assert(save["mutating"] is True, "『保存』点击标为 mutating")
    menu = next(s for s in steps if "款式" in s.get("label", "") and s["action"] == "click")
    _assert(menu.get("mutating") is False, "普通菜单点击不标 mutating")
    _assert(any("拖拽" in n for n in notes), "不支持的操作变成提示，不产出步骤")
    _assert(len(fill["target"]["candidates"]) <= 6, "候选截断到 6 个")
    _assert("name" not in fill["target"]["candidates"][0], "丢掉值为 None 的字段")
    _assert(fill["target"].get("scope", {}).get("kind") == "modal", "弹窗内操作带上当场爬到的 scope")
    _assert(fill["target"]["scope"].get("css") == ".ant-modal-content", "scope.css 来自这次录到的 DOM")

    again, _ = compile_events(
        [
            {
                "type": "fill",
                "target": {
                    "candidates": [{"kind": "placeholder", "value": "编码"}],
                    "scope": {"kind": "modal", "css": ".oio-dialog", "name": "下次的弹窗", "path": "modal「下次的弹窗」"},
                },
                "value": "B",
                "context": {"dialog": "下次的弹窗"},
            }
        ],
        "http://example.test/app",
    )
    next_fill = next(s for s in again if s["action"] == "fill")
    _assert(next_fill["target"]["scope"]["css"] == ".oio-dialog", "下一次录制用当时的 DOM，不沿用上一次的 css")

    combo_target = {
        "candidates": [{"kind": "field", "value": "basicProductType"}],
        "scope": {"kind": "modal", "css": ".oio-modal-wrapper", "name": "新增"},
    }
    combo_steps, _ = compile_events(
        [
            {
                "type": "click",
                "target": combo_target,
                "text": "请选择",
                "context": {"widget": "combobox", "label": "货品类型", "dialog": "新增"},
            },
            {
                "type": "fill",
                "target": combo_target,
                "value": "T",
                "context": {"widget": "combobox", "label": "货品类型", "dialog": "新增"},
            },
            {
                "type": "choose",
                "target": combo_target,
                "value": "T恤",
                "text": "T恤",
                "context": {"widget": "combobox", "label": "货品类型", "dialog": "新增"},
            },
        ],
        "http://example.test/app",
    )
    combo_actions = [s["action"] for s in combo_steps[1:]]
    _assert(combo_actions == ["click", "choose"], f"点开下拉要留下，实际 {combo_actions}")
    _assert(combo_steps[1]["action"] == "click", "点开下拉应是 click")
    combo = combo_steps[2]
    _assert(combo["value"] == "T恤", "下拉保留选中项，丢掉搜索框里的过滤字")
    _assert(combo["action"] == "choose", "Ant Design 下拉不能编成 fill")
    _assert(combo.get("choose_mode") == "search_or_first", "新建弹窗的 choose 应记下可搜索、没有则第一条")
    _assert("为 T恤" in combo["label"], "新建仍写出点到的值")

    optional_steps, _ = compile_events(
        [
            {
                "type": "choose",
                "target": combo_target,
                "value": "Gucci",
                "context": {
                    "widget": "combobox",
                    "label": "品牌",
                    "dialog": "新增",
                    "required": False,
                },
            }
        ],
        "http://example.test/app",
        intent="新建款式",
    )
    optional = next(s for s in optional_steps if s["action"] == "choose")
    _assert(optional.get("optional") is True, "录到非必填下拉时步骤要标 optional")

    required_steps, _ = compile_events(
        [
            {
                "type": "choose",
                "target": combo_target,
                "value": "T恤",
                "context": {
                    "widget": "combobox",
                    "label": "品类",
                    "dialog": "新增",
                    "required": True,
                },
            }
        ],
        "http://example.test/app",
        intent="新建款式",
    )
    required = next(s for s in required_steps if s["action"] == "choose")
    _assert(required.get("optional") is False, "录到必填下拉时不能标成可跳过")

    leaked_fill, _ = compile_events(
        [
            {
                "type": "fill",
                "target": combo_target,
                "value": "T",
                "context": {"widget": "combobox", "label": "货品类型", "dialog": "新增"},
            }
        ],
        "http://example.test/app",
    )
    leaked = next(s for s in leaked_fill if s["action"] in {"fill", "choose"})
    _assert(leaked["action"] == "choose", "即便录成 fill，带 combobox 标记也改成 choose")

    filter_steps, _ = compile_events(
        [
            {
                "type": "fill",
                "target": {
                    "candidates": [
                        {"kind": "placeholder", "value": "搜索/添加"},
                        {"kind": "css", "value": "#el-id-3540-393"},
                    ],
                    "scope": {"kind": "dropdown", "name": "新增"},
                },
                "value": "S",
                "context": {"label": "搜索/添加", "dialog": "新增"},
            },
            {
                "type": "choose",
                "target": combo_target,
                "value": "T恤",
                "context": {"label": "品类", "dialog": "新增"},
            },
        ],
        "http://example.test/app",
    )
    filter_actions = [s["action"] for s in filter_steps[1:]]
    _assert(filter_actions == ["choose"], f"搜索/添加过滤框不能编成 fill，实际 {filter_actions}")
    _assert(filter_steps[1]["value"] == "T恤", "品类应留下选中项而不是过滤字")

    tab_steps, _ = compile_events(
        [
            {
                "type": "click",
                "target": {
                    "candidates": [{"kind": "text", "value": "女装"}],
                    "scope": {"kind": "dropdown", "name": "新增"},
                },
                "text": "女装",
                "context": {"dialog": "新增", "label": "尺码"},
            }
        ],
        "http://example.test/app",
    )
    tab = next(s for s in tab_steps if s["action"] == "click")
    _assert("弹窗" in tab["label"] and "选项" not in tab["label"], f"下拉里的点击应写弹窗不是选项，实际 {tab['label']}")
    _assert("新增" in tab["label"] and "女装" in tab["label"], f"应带弹窗名和点击对象，实际 {tab['label']}")

    size_open = {
        "candidates": [
            {"kind": "text", "value": "尺码"},
            {"kind": "field", "value": "productSizes"},
            {"kind": "css", "value": '[data-name="productSizes"] .el-select__wrapper'},
        ],
        "widget": "el-select",
        "trigger_css": '[data-name="productSizes"] .el-select__wrapper',
        "scope": {"kind": "modal", "css": ".oio-modal-wrapper", "name": "新增"},
    }
    size_steps, _ = compile_events(
        [
            {
                "type": "click",
                "target": size_open,
                "text": "尺码",
                "context": {"widget": "el-select", "label": "尺码", "dialog": "新增", "trigger_css": size_open["trigger_css"]},
            },
            {
                "type": "click",
                "target": {
                    "candidates": [
                        {"kind": "text", "value": "女装"},
                        {"kind": "css", "value": "#tab-女装"},
                    ],
                    "scope": {"kind": "dropdown", "name": "新增"},
                    "panel": "el-select-dropdown:teleport",
                    "widget": "el-select",
                    "trigger_css": '[data-name="productSizes"] .el-select__wrapper',
                },
                "text": "女装",
                "context": {
                    "dialog": "新增",
                    "label": "女装",
                    "panel": "el-select-dropdown:teleport",
                    "widget": "el-select",
                    "trigger_css": '[data-name="productSizes"] .el-select__wrapper',
                },
            },
        ],
        "http://example.test/app",
    )
    size_clicks = [s for s in size_steps if s["action"] == "click"]
    _assert(len(size_clicks) == 2, f"点开尺码后再点女装应保留两步，实际 {[s['label'] for s in size_clicks]}")
    _assert("尺码" in size_clicks[0]["label"], f"第一步应是点开尺码，实际 {size_clicks[0]['label']}")
    _assert("女装" in size_clicks[1]["label"], f"第二步应是点女装，实际 {size_clicks[1]['label']}")
    _assert(
        size_clicks[0]["target"].get("widget") == "el-select",
        f"打开下拉应记下控件类型，实际 {size_clicks[0]['target']}",
    )
    _assert(
        size_clicks[0]["target"].get("trigger_css") == '[data-name="productSizes"] .el-select__wrapper',
        f"打开下拉应记下触发器，实际 {size_clicks[0]['target']}",
    )
    _assert(
        size_clicks[0]["target"]["candidates"][0]["value"] == '[data-name="productSizes"] .el-select__wrapper',
        f"打开下拉应优先点 wrapper，实际 {size_clicks[0]['target']['candidates']}",
    )
    _assert(
        size_clicks[1]["target"]["candidates"][0]["value"] == "#tab-女装",
        f"下拉 tab 应优先用 id，实际 {size_clicks[1]['target']['candidates']}",
    )
    _assert(
        size_clicks[1]["target"].get("trigger_css") == '[data-name="productSizes"] .el-select__wrapper',
        f"面板内点击应带上打开它的触发器，实际 {size_clicks[1]['target']}",
    )
    _assert(
        size_clicks[1]["target"].get("panel") == "el-select-dropdown:teleport",
        f"面板内点击应记下面板类型，实际 {size_clicks[1]['target']}",
    )

    scroll_steps, _ = compile_events(
        [
            {
                "type": "scroll",
                "target": {
                    "candidates": [{"kind": "css", "value": ".el-dialog__body"}],
                    "scope": {"kind": "modal", "name": "新增"},
                },
                "value": "240",
                "context": {"dialog": "新增"},
            },
            {
                "type": "scroll",
                "target": {
                    "candidates": [{"kind": "css", "value": ".el-dialog__body"}],
                    "scope": {"kind": "modal", "name": "新增"},
                },
                "value": "480",
                "context": {"dialog": "新增"},
            },
        ],
        "http://example.test/app",
    )
    scrolls = [s for s in scroll_steps if s["action"] == "scroll"]
    _assert(len(scrolls) == 1, f"同一容器连续滚动只留最后一次，实际 {scrolls}")
    _assert(scrolls[0]["value"] == "480", f"滚动应记下最终位置，实际 {scrolls[0]}")

    idle_open, _ = compile_events(
        [
            {
                "type": "click",
                "target": size_open,
                "text": "尺码",
                "context": {"widget": "combobox", "label": "尺码", "dialog": "新增"},
            },
            {
                "type": "click",
                "target": size_open,
                "text": "尺码",
                "context": {"widget": "combobox", "label": "尺码", "dialog": "新增"},
            },
            {
                "type": "click",
                "target": size_open,
                "text": "尺码",
                "context": {"widget": "combobox", "label": "尺码", "dialog": "新增"},
            },
            {
                "type": "click",
                "target": {
                    "candidates": [{"kind": "css", "value": "#tab-女装"}],
                    "scope": {"kind": "dropdown", "name": "新增"},
                },
                "text": "女装",
                "context": {"dialog": "新增"},
            },
        ],
        "http://example.test/app",
    )
    idle_clicks = [s for s in idle_open if s["action"] == "click"]
    _assert(len(idle_clicks) == 2, f"空开空关同一下拉应并成一次再点女装，实际 {[s['label'] for s in idle_clicks]}")
    _assert("尺码" in idle_clicks[0]["label"] and "女装" in idle_clicks[1]["label"], "空开空关之后仍要留下点女装")

    brand_steps, _ = compile_events(
        [
            {
                "type": "click",
                "target": {
                    "candidates": [
                        {"kind": "field", "value": "brand"},
                        {"kind": "css", "value": '[data-name="brand"] .ant-select-selector'},
                    ],
                    "widget": "ant-select",
                    "trigger_css": '[data-name="brand"] .ant-select-selector',
                    "scope": {"kind": "modal", "name": "新增"},
                },
                "text": "下拉",
                "context": {"widget": "ant-select", "dialog": "新增"},
            },
            {
                "type": "choose",
                "target": {
                    "candidates": [{"kind": "field", "value": "brand"}],
                    "widget": "ant-select",
                    "trigger_css": '[data-name="brand"] .ant-select-selector',
                    "scope": {"kind": "modal", "name": "新增"},
                },
                "value": "杰克",
                "text": "杰克",
                "context": {"widget": "ant-select", "dialog": "新增"},
            },
        ],
        "http://example.test/app",
    )
    brand_choose = next(s for s in brand_steps if s["action"] == "choose")
    _assert(brand_choose["value"] == "杰克", f"品牌应保留点到的值，实际 {brand_choose}")
    _assert("品牌" in brand_choose["label"], f"品牌步骤应写出字段名，实际 {brand_choose['label']}")
    _assert("Gucci" not in brand_choose["label"] and brand_choose["value"] != "Gucci", "品牌不能被改成 Gucci")
    brand_open = next(s for s in brand_steps if s["action"] == "click")
    _assert("品牌" in brand_open["label"], f"点开品牌不能写成下拉，实际 {brand_open['label']}")

    size_pick, _ = compile_events(
        [
            {
                "type": "click",
                "target": {
                    "candidates": [{"kind": "text", "value": "155"}],
                    "scope": {"kind": "dropdown", "name": "新增"},
                    "widget": "el-select",
                    "panel": "el-select-dropdown:teleport",
                    "trigger_css": '[data-name="productSizes"] .el-select__wrapper',
                },
                "text": "155",
                "context": {"dialog": "新增"},
            },
            {
                "type": "click",
                "target": {
                    "candidates": [{"kind": "text", "value": "170"}],
                    "scope": {"kind": "dropdown", "name": "新增"},
                    "widget": "el-select",
                    "panel": "el-select-dropdown:teleport",
                    "trigger_css": '[data-name="productSizes"] .el-select__wrapper',
                },
                "text": "170",
                "context": {"dialog": "新增"},
            },
        ],
        "http://example.test/app",
    )
    size_values = [s["label"] for s in size_pick if s["action"] == "click"]
    _assert(len(size_values) == 2, f"尺码多选应留下每一次点击，实际 {size_values}")

    chrome, _ = compile_events(
        [
            {
                "type": "click",
                "target": {
                    "candidates": [
                        {"kind": "text", "value": "新增"},
                        {"kind": "role", "value": "dialog", "name": "新增"},
                        {"kind": "css", "value": "#DialogWidget-430"},
                    ],
                    "scope": {"kind": "modal", "name": "新增"},
                },
                "text": "新增",
                "context": {"dialog": "新增"},
            }
        ],
        "http://example.test/app",
    )
    _assert(all(s["action"] != "click" for s in chrome[1:]), f"点弹窗壳不能编成步骤，实际 {chrome}")

    save_in_dialog, _ = compile_events(
        [
            {
                "type": "click",
                "target": {
                    "candidates": [
                        {"kind": "role", "value": "button", "name": "保存"},
                        {"kind": "text", "value": "保存"},
                        {
                            "kind": "css",
                            "value": "div#DialogWidget-430 > div.ant-modal-footer > button.ant-btn",
                        },
                    ],
                    "scope": {"kind": "modal", "name": "新增"},
                },
                "text": "保存",
                "context": {"dialog": "新增"},
            }
        ],
        "http://example.test/app",
    )
    save_labels = [s.get("label", "") for s in save_in_dialog]
    _assert(
        any(s["action"] == "click" and "保存" in s.get("label", "") for s in save_in_dialog),
        f"弹窗里的保存按钮不能当弹窗壳丢掉，实际 {save_labels}",
    )

    upload_steps, _ = compile_events(
        [
            {
                "type": "fill",
                "target": {
                    "candidates": [{"kind": "field", "value": "imageUrls"}],
                    "scope": {"kind": "modal", "name": "新增"},
                },
                "value": r"C:\fakepath\ScreenShot.png",
                "context": {"label": "图片列表", "dialog": "新增"},
            }
        ],
        "http://example.test/app",
    )
    _assert(all(s["action"] != "fill" for s in upload_steps[1:]), f"文件上传不能编成 fill，实际 {upload_steps}")
    upload = next(s for s in upload_steps if s["action"] == "upload")
    _assert(upload["value"].endswith("ScreenShot_2026-04-16_084203_890.png"), f"回放应固定项目图片，实际 {upload}")
    _assert("图片列表" in upload["label"], f"上传步骤应带字段名，实际 {upload['label']}")

    edit_steps, _ = compile_events(
        [
            {
                "type": "choose",
                "target": {
                    "candidates": [{"kind": "field", "value": "basicProductType"}],
                    "scope": {"kind": "modal", "css": ".oio-modal-wrapper", "name": "编辑"},
                },
                "value": "外套",
                "already_selected": "外套",
                "form_kind": "edit",
                "context": {"widget": "combobox", "label": "品类", "dialog": "编辑"},
            }
        ],
        "http://example.test/app",
        intent="编辑款式",
    )
    edit_choose = next(s for s in edit_steps if s["action"] == "choose")
    _assert(edit_choose.get("choose_mode") == "other", "编辑弹窗的 choose 应编成换一项")
    _assert("换一项" in edit_choose["label"], "编辑步骤文案是换一项，不是选已选值")
    _assert("为 外套" not in edit_choose["label"], "编辑不要把已选的外套写成目标")

    empty_steps, empty_notes = compile_events([], "http://example.test/")
    _assert(len(empty_steps) == 1, "没有任何操作时只剩 goto")
    _assert(any("没录到任何操作" in n for n in empty_notes), "空录制有提示")

    print("\n编译器自测通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
