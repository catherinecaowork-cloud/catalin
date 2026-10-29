"""语义指纹定位：候选全失效时按「像不像」找回元素。

这几条用例刻意模拟「没见过的页面改动」：
- 类名全换、表格列顺序变了（vxe 表头与表体分离）；
- 页面上多了一个长得一样的控件；
- 两个元素指纹完全一样时，引擎必须拒绝猜，而不是取第一个。

它们不依赖被测站点，也不需要为每个控件再加一种候选 kind。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, sync_playwright

from autotest_executor.browser.locator import TargetNotFound, resolve_target
from autotest_protocol import Candidate, Fingerprint, Target
from autotest_protocol import dsl as dsl_module
from tests.conftest import require_browser

JS = (
    Path(__file__).resolve().parents[1]
    / "packages"
    / "executor"
    / "autotest_executor"
    / "browser"
    / "locator_candidates.js"
)

SPLIT_HEADER_TABLE = """
<div class="vxe-table">
  <div class="vxe-table--header-wrapper">
    <table><thead><tr>
      <th class="col_100">颜色尺码</th>
      <th class="col_101">155/80A</th>
      <th class="col_102">160/84A</th>
      <th class="col_103">合计</th>
    </tr></thead></table>
  </div>
  <div class="vxe-table--body-wrapper">
    <table><tbody><tr>
      <td class="col_100">1</td>
      <td class="col_101"><input class="vxe-input--inner" data-mark="s155"></td>
      <td class="col_102"><input class="vxe-input--inner" data-mark="s160"></td>
      <td class="col_103">0</td>
    </tr></tbody></table>
  </div>
</div>
"""

# 列顺序整体对调：155 和 160 互换位置，类名也换一轮（模拟框架重新生成）。
SPLIT_HEADER_TABLE_SHUFFLED = """
<div class="vxe-table">
  <div class="vxe-table--header-wrapper">
    <table><thead><tr>
      <th class="col_100">颜色尺码</th>
      <th class="col_102">160/84A</th>
      <th class="col_101">155/80A</th>
      <th class="col_103">合计</th>
    </tr></thead></table>
  </div>
  <div class="vxe-table--body-wrapper">
    <table><tbody><tr>
      <td class="col_100">1</td>
      <td class="col_102"><input class="vxe-input--inner" data-mark="s160"></td>
      <td class="col_101"><input class="vxe-input--inner" data-mark="s155"></td>
      <td class="col_103">0</td>
    </tr></tbody></table>
  </div>
</div>
"""

OINONE_FORM = """
<div class="add-po-info-wrap"><div class="form-container">
  <div class="item">
    <div class="label"><span class="required">*</span>PO单号</div>
    <div class="ctl"><span class="ant-input-affix-wrapper"><input class="ant-input" data-mark="po"></span></div>
  </div>
  <div class="item">
    <div class="label"><span class="required">*</span>国家/地区</div>
    <div class="ctl"><div class="el-select"><div class="el-select__wrapper" data-mark="country">
      <input class="el-select__input" readonly>
    </div></div></div>
  </div>
</div></div>
"""

OINONE_FORM_WITH_LOOKALIKE = """
<div class="add-po-info-wrap"><div class="form-container">
  <div class="item">
    <div class="label"><span class="required">*</span>品牌</div>
    <div class="ctl"><div class="el-select"><div class="el-select__wrapper" data-mark="brand">
      <input class="el-select__input" readonly>
    </div></div></div>
  </div>
  <div class="item">
    <div class="label"><span class="required">*</span>PO单号</div>
    <div class="ctl"><span class="ant-input-affix-wrapper"><input class="ant-input" data-mark="po"></span></div>
  </div>
  <div class="item">
    <div class="label"><span class="required">*</span>国家/地区</div>
    <div class="ctl"><div class="el-select"><div class="el-select__wrapper" data-mark="country">
      <input class="el-select__input" readonly>
    </div></div></div>
  </div>
</div></div>
"""


@pytest.fixture(scope="module")
def browser():
    require_browser()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        yield browser
        browser.close()


def _page(browser, html: str) -> Page:
    page = browser.new_page()
    page.set_content(html)
    page.add_script_tag(path=str(JS))
    return page


def _fingerprint(page: Page, selector: str) -> Fingerprint:
    raw = page.evaluate(
        "([sel]) => window.__atpFingerprint(document.querySelector(sel))", [selector]
    )
    assert raw, f"{selector} 没算出指纹"
    return Fingerprint(**raw)


def _bogus_target(fingerprint: Fingerprint) -> Target:
    # 候选故意写成已经不存在的选择器：逼解析器走指纹退路。
    return Target(
        candidates=[Candidate(kind="css", value=".selector-that-no-longer-exists")],
        fingerprint=fingerprint,
    )


def test_grid_cell_survives_column_swap_and_class_rename(browser) -> None:
    """vxe 表头分离 + 列顺序变化：按列头语义找回 155/80A 那一格。"""
    page = _page(browser, SPLIT_HEADER_TABLE)
    fingerprint = _fingerprint(page, 'input[data-mark="s155"]')
    assert fingerprint.grid_col == "155/80A"
    assert fingerprint.grid_row == "1"

    page.set_content(SPLIT_HEADER_TABLE_SHUFFLED)
    page.add_script_tag(path=str(JS))

    resolution = resolve_target(page, _bogus_target(fingerprint), timeout_ms=800)
    assert resolution.candidate.kind == "fingerprint"
    assert resolution.locator.get_attribute("data-mark") == "s155"

    page.close()


def test_oinone_label_survives_lookalike_control(browser) -> None:
    """同格 .label 锚定：前面多了一个长得一样的下拉，也认准「国家/地区」。"""
    page = _page(browser, OINONE_FORM)
    fingerprint = _fingerprint(page, '[data-mark="country"]')
    assert fingerprint.label == "国家/地区"

    page.set_content(OINONE_FORM_WITH_LOOKALIKE)
    page.add_script_tag(path=str(JS))

    resolution = resolve_target(page, _bogus_target(fingerprint), timeout_ms=800)
    assert resolution.candidate.kind == "fingerprint"
    assert resolution.locator.get_attribute("data-mark") == "country"

    page.close()


def test_label_survives_class_rename(browser) -> None:
    """框架把 label/item/input 的类名整体换掉，标签仍要能从结构里读出来。

    Oinone 的标签是 <div class="label">，按类名找的话一旦改版 label 就没了，
    指纹退化成「第一个 textbox」——这正是不能接受的静默错点。
    """
    page = _page(
        browser,
        """
        <div class="form-container"><div class="item">
          <div class="label">PO单号</div>
          <div class="ctl"><input class="ant-input" data-mark="po"></div>
        </div></div>
        """,
    )
    fingerprint = _fingerprint(page, '[data-mark="po"]')
    assert fingerprint.label == "PO单号"

    page.set_content(
        """
        <div class="form-container"><div class="itm_a71">
          <div class="lb_x9">PO单号</div>
          <div class="ct_z3"><input class="ai_k8" data-mark="po"></div>
        </div></div>
        """
    )
    page.add_script_tag(path=str(JS))

    healed = page.evaluate(
        "() => window.__atpFingerprint(document.querySelector('[data-mark=\"po\"]'))"
    )
    assert healed["label"] == "PO单号"

    resolution = resolve_target(page, _bogus_target(fingerprint), timeout_ms=800)
    assert resolution.candidate.kind == "fingerprint"
    assert resolution.locator.get_attribute("data-mark") == "po"
    page.close()


def test_grid_cell_does_not_borrow_form_label(browser) -> None:
    """表格格子不能被旁边的表单块「借」到标签，只能靠行×列。"""
    page = _page(
        browser,
        """
        <div class="add-po-info-wrap">
          <div class="form-container"><div class="item">
            <div class="label">PO单号</div>
            <div class="ctl"><input class="ant-input" data-mark="po"></div>
          </div></div>
        """
        + SPLIT_HEADER_TABLE
        + "</div>",
    )
    fingerprint = _fingerprint(page, 'input[data-mark="s155"]')
    assert fingerprint.grid_col == "155/80A"
    # 左边一格的「1」、旁边表单块的「PO单号」都不能变成格子的标签。
    assert fingerprint.label is None

    page.set_content(
        "<div class='add-po-info-wrap'>" + SPLIT_HEADER_TABLE_SHUFFLED + "</div>"
    )
    page.add_script_tag(path=str(JS))
    resolution = resolve_target(page, _bogus_target(fingerprint), timeout_ms=800)
    assert resolution.locator.get_attribute("data-mark") == "s155"
    page.close()


def test_structural_label_skips_buttons(browser) -> None:
    """结构找标签只对字段生效：工具栏里前一个按钮的文字不能算标签。"""
    page = _page(
        browser,
        """
        <div class="toolbar">
          <button>新增</button>
          <button data-mark="save">保存</button>
        </div>
        """,
    )
    fingerprint = _fingerprint(page, '[data-mark="save"]')
    assert fingerprint.label is None
    assert fingerprint.name == "保存"
    page.close()


def test_ambiguous_fingerprint_is_refused(browser) -> None:
    """两个元素指纹完全一样：宁可失败，也不能猜一个填进去。"""
    page = _page(
        browser,
        """
        <div>
          <input data-mark="a"><input data-mark="b">
        </div>
        """,
    )
    both = page.evaluate(
        """() => Array.from(document.querySelectorAll('input'))
             .map((el) => window.__atpFingerprint(el))"""
    )
    assert len(both) == 2
    fingerprint = Fingerprint(**both[0])

    with pytest.raises(TargetNotFound) as excinfo:
        resolve_target(page, _bogus_target(fingerprint), timeout_ms=600)
    assert "fingerprint" in str(excinfo.value)

    page.close()


def test_fingerprint_beats_bare_role_candidate(browser) -> None:
    """无名 role=textbox 会命中页面第一个输入框；有指纹时必须走指纹。"""
    page = _page(
        browser,
        """
        <div class="form-container">
          <div class="item"><div class="label">备注</div>
            <div class="ctl"><input class="ant-input" data-mark="memo"></div></div>
          <div class="item"><div class="label">PO单号</div>
            <div class="ctl"><input class="ant-input" data-mark="po"></div></div>
        </div>
        """,
    )
    fingerprint = _fingerprint(page, '[data-mark="po"]')
    target = Target(
        candidates=[
            Candidate(kind="role", value="textbox"),
            Candidate(kind="css", value=".selector-that-no-longer-exists"),
        ],
        fingerprint=fingerprint,
    )

    resolution = resolve_target(page, target, timeout_ms=800)
    assert resolution.locator.get_attribute("data-mark") == "po"
    # 无名 role 被跳过，集中走指纹；不会出现「首个 textbox」的静默错点。
    assert resolution.candidate.kind == "fingerprint"
    page.close()


def test_late_rendered_element_is_healed_and_reported(browser) -> None:
    """元素比指纹首轮等待还晚出现：兜底那一轮找回，并按「自愈」报出来。"""
    page = _page(
        browser,
        """
        <div class="form-container">
          <div class="item"><div class="label">备注</div>
            <div class="ctl"><input class="ant-input" data-mark="memo"></div></div>
        </div>
        """,
    )
    fingerprint = Fingerprint(tag="input", role="textbox", label="PO单号", index=0)
    page.evaluate(
        """() => setTimeout(() => {
             const item = document.createElement('div');
             item.className = 'item';
             item.innerHTML = '<div class="label">PO单号</div>'
               + '<div class="ctl"><input class="ant-input" data-mark="po"></div>';
             document.querySelector('.form-container').appendChild(item);
           }, 1500)"""
    )

    target = _bogus_target(fingerprint)
    resolution = resolve_target(page, target, timeout_ms=6_000)

    assert resolution.locator.get_attribute("data-mark") == "po"
    assert resolution.candidate.kind == "fingerprint"
    # 兜底命中要带顺位与自愈说明，界面上才看得出这步不是按候选走的。
    assert resolution.fallback_index == len(target.candidates)
    assert resolution.drifted
    assert "自愈" in resolution.drift_note
    page.close()


def test_protocol_round_trip_keeps_fingerprint() -> None:
    """指纹要能随流程 JSON 存取，旧流程（无指纹）不受影响。"""
    fingerprint = Fingerprint(label="国家/地区", tag="div", grid_col=None)
    target = Target(
        candidates=[Candidate(kind="css", value=".x")], fingerprint=fingerprint
    )
    dumped = target.model_dump()
    assert dumped["fingerprint"]["label"] == "国家/地区"
    assert Target.model_validate(dumped).fingerprint == fingerprint
    assert not fingerprint.is_empty()
    assert dsl_module.Fingerprint is Fingerprint
