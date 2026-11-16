"""本地 Ant Design 浮层回归：不依赖福瑞丝内网。

覆盖：隐藏副本在前的下拉点选、ant-dropdown 菜单、弹窗内按钮、
浮层未出现的环境失败、iframe 明确不支持。同一 fixture 连续跑多轮。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from autotest_executor.browser.actions import (
    FAILURE_NOT_FOUND,
    FAILURE_NO_EFFECT,
    ActionRunner,
)
from autotest_executor.browser.locator import (
    FailureKind,
    IframeNotSupported,
    TargetNotFound,
    resolve_target,
)
from autotest_executor.browser.session import BrowserSession
from autotest_executor.ui_selectors import DROPDOWN_OPTION, DROPDOWN_PANEL
from autotest_protocol import Candidate, Job, RunOptions, SiteRef, Step, Target, TargetScope
from autotest_protocol.job import ProbeConfig
from tests.conftest import require_browser

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "ant_overlay.html"


def _job(url: str) -> Job:
    return Job(
        run_id="ant-overlay-fixture",
        site=SiteRef(id="local", base_url=url, probe=ProbeConfig(enabled=False)),
        options=RunOptions(headless=True, video="off", trace="off"),
    )


@pytest.fixture(scope="module")
def fixture_url(tmp_path_factory) -> str:
    require_browser()
    return FIXTURE.resolve().as_uri()


def test_dropdown_panel_includes_ant_dropdown() -> None:
    """选择器单一来源后，菜单型 .ant-dropdown 必须在面板口径里。"""
    assert ".ant-dropdown:visible" in DROPDOWN_PANEL
    assert "ant-select-item-option-disabled" in DROPDOWN_OPTION
    assert "[role=option]" in DROPDOWN_OPTION


def test_open_select_choose_with_hidden_copy(fixture_url: str, tmp_path: Path) -> None:
    """隐藏副本在前时，点开下拉并选中可见「品牌A」。"""
    session = BrowserSession(_job(fixture_url), tmp_path / "artifacts")
    session.start()
    try:
        page = session.page
        page.goto(fixture_url, wait_until="load")
        runner = ActionRunner(session)

        open_step = Step(
            id="open",
            action="click",
            target=Target(
                candidates=[Candidate(kind="css", value="#brand-trigger")],
                scope=TargetScope(kind="page"),
                widget="ant-select",
            ),
            label="点击「品牌」",
            timeout_ms=3_000,
        )
        opened = runner.run(open_step)
        assert opened.status == "passed", opened.message
        assert page.locator("#brand-dropdown").is_visible()

        choose = Step(
            id="choose",
            action="click",
            target=Target(
                candidates=[Candidate(kind="css", value=".ant-select-item-option")],
                scope=TargetScope(kind="dropdown"),
            ),
            label="选择「品牌A」",
            timeout_ms=3_000,
        )
        picked = runner.run(choose)
        assert picked.status == "passed", picked.message
        assert page.inner_text("#brand-value") == "品牌A"
        assert page.inner_text("#log") == "brand=品牌A"
    finally:
        session.stop(keep_trace=False)


def test_ant_dropdown_menu_item(fixture_url: str, tmp_path: Path) -> None:
    """菜单型 ant-dropdown：点「更多」→ 点「导出」。"""
    session = BrowserSession(_job(fixture_url), tmp_path / "artifacts")
    session.start()
    try:
        page = session.page
        page.goto(fixture_url, wait_until="load")
        runner = ActionRunner(session)

        runner.run(
            Step(
                id="open-menu",
                action="click",
                target=Target(
                    candidates=[Candidate(kind="css", value="#more-btn")],
                    scope=TargetScope(kind="page"),
                ),
                label="点击「更多」",
                timeout_ms=2_000,
            )
        )
        assert page.locator("#more-menu").is_visible()

        picked = runner.run(
            Step(
                id="export",
                action="click",
                target=Target(
                    candidates=[
                        Candidate(kind="css", value=".ant-dropdown-menu-item"),
                        Candidate(kind="text", value="导出"),
                    ],
                    scope=TargetScope(kind="dropdown"),
                ),
                label="点击「导出」",
                timeout_ms=2_000,
            )
        )
        assert picked.status == "passed", picked.message
        assert page.inner_text("#log") == "menu=导出"
    finally:
        session.stop(keep_trace=False)


def test_modal_save_button(fixture_url: str, tmp_path: Path) -> None:
    """弹窗内按钮：打开 → 点保存。"""
    session = BrowserSession(_job(fixture_url), tmp_path / "artifacts")
    session.start()
    try:
        page = session.page
        page.goto(fixture_url, wait_until="load")
        runner = ActionRunner(session)

        runner.run(
            Step(
                id="open-modal",
                action="click",
                target=Target(
                    candidates=[Candidate(kind="css", value="#open-modal")],
                    scope=TargetScope(kind="page"),
                ),
                label="点击「新增」",
                timeout_ms=2_000,
            )
        )
        assert "open" in (page.locator("#modal").get_attribute("class") or "")

        saved = runner.run(
            Step(
                id="save",
                action="click",
                target=Target(
                    candidates=[Candidate(kind="css", value="#modal-save")],
                    scope=TargetScope(kind="modal", name="新增款式"),
                ),
                label="在「新增款式」弹窗：点击「保存」",
                timeout_ms=2_000,
            )
        )
        assert saved.status == "passed", saved.message
        assert page.inner_text("#log") == "modal-saved"
    finally:
        session.stop(keep_trace=False)


def test_overlay_absent_is_environmental(fixture_url: str, tmp_path: Path) -> None:
    """下拉未打开时，dropdown scope 目标报浮层未出现，不写成候选失效。"""
    require_browser()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(fixture_url, wait_until="load")
            target = Target(
                candidates=[Candidate(kind="css", value=".ant-select-item-option")],
                scope=TargetScope(kind="dropdown"),
            )
            with pytest.raises(TargetNotFound) as excinfo:
                resolve_target(page, target, timeout_ms=400)
            assert excinfo.value.kind == FailureKind.OVERLAY_ABSENT
        finally:
            browser.close()


def test_click_select_no_effect(fixture_url: str, tmp_path: Path) -> None:
    """声明为 ant-select 的触发器点了却不展开 → 点了没生效。"""
    session = BrowserSession(_job(fixture_url), tmp_path / "artifacts")
    session.start()
    try:
        page = session.page
        page.goto(fixture_url, wait_until="load")
        # 把 onclick 摘掉，模拟「点了没反应」
        page.evaluate("document.getElementById('brand-trigger').onclick = null")
        runner = ActionRunner(session)
        outcome = runner.run(
            Step(
                id="dead-trigger",
                action="click",
                target=Target(
                    candidates=[Candidate(kind="css", value="#brand-trigger")],
                    scope=TargetScope(kind="page"),
                    widget="ant-select",
                ),
                label="点击「品牌」",
                timeout_ms=2_000,
            )
        )
        assert outcome.status == "failed"
        assert outcome.data.get("failure") == FAILURE_NO_EFFECT
    finally:
        session.stop(keep_trace=False)


def test_iframe_target_reports_unsupported(tmp_path: Path) -> None:
    """目标只在 iframe 里时，明确报不支持，而不是偶发找不到。"""
    require_browser()
    host = tmp_path / "iframe_host.html"
    inner = tmp_path / "iframe_inner.html"
    inner.write_text(
        '<!doctype html><button id="inside">iframe内按钮</button>',
        encoding="utf-8",
    )
    host.write_text(
        f'<!doctype html><iframe src="{inner.resolve().as_uri()}" '
        f'id="frame" style="width:300px;height:120px"></iframe>',
        encoding="utf-8",
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(host.resolve().as_uri(), wait_until="load")
            page.wait_for_selector("iframe")
            target = Target(
                candidates=[Candidate(kind="css", value="#inside")],
                scope=TargetScope(kind="page"),
            )
            with pytest.raises(IframeNotSupported):
                resolve_target(page, target, timeout_ms=800)
        finally:
            browser.close()


@pytest.mark.parametrize("round_id", range(3))
def test_overlay_flow_stable_across_rounds(fixture_url: str, tmp_path: Path, round_id: int) -> None:
    """同一套浮层路径连续多轮全绿——本地替代真站 5 次闸。"""
    artifacts = tmp_path / f"round-{round_id}"
    session = BrowserSession(_job(fixture_url), artifacts)
    session.start()
    try:
        page = session.page
        page.goto(fixture_url, wait_until="load")
        runner = ActionRunner(session)

        assert (
            runner.run(
                Step(
                    id="o",
                    action="click",
                    target=Target(
                        candidates=[Candidate(kind="css", value="#brand-trigger")],
                        widget="ant-select",
                    ),
                    timeout_ms=2_000,
                )
            ).status
            == "passed"
        )
        assert (
            runner.run(
                Step(
                    id="c",
                    action="click",
                    target=Target(
                        candidates=[Candidate(kind="css", value=".ant-select-item-option")],
                        scope=TargetScope(kind="dropdown"),
                    ),
                    timeout_ms=2_000,
                )
            ).status
            == "passed"
        )
        assert page.inner_text("#brand-value") == "品牌A"

        assert (
            runner.run(
                Step(
                    id="m",
                    action="click",
                    target=Target(candidates=[Candidate(kind="css", value="#open-modal")]),
                    timeout_ms=2_000,
                )
            ).status
            == "passed"
        )
        assert (
            runner.run(
                Step(
                    id="s",
                    action="click",
                    target=Target(
                        candidates=[Candidate(kind="css", value="#modal-save")],
                        scope=TargetScope(kind="modal"),
                    ),
                    timeout_ms=2_000,
                )
            ).status
            == "passed"
        )
        assert page.inner_text("#log") == "modal-saved"
    finally:
        session.stop(keep_trace=False)


def test_iframe_failure_surfaces_via_action_runner(tmp_path: Path) -> None:
    """ActionRunner 路径也要把 iframe 不支持报到步骤结果里。"""
    require_browser()
    inner = tmp_path / "inner.html"
    host = tmp_path / "host.html"
    inner.write_text('<!doctype html><button id="inside">内</button>', encoding="utf-8")
    host.write_text(
        f'<!doctype html><iframe src="{inner.resolve().as_uri()}"></iframe>',
        encoding="utf-8",
    )
    url = host.resolve().as_uri()
    session = BrowserSession(_job(url), tmp_path / "artifacts")
    session.start()
    try:
        session.page.goto(url, wait_until="load")
        session.page.wait_for_selector("iframe")
        outcome = ActionRunner(session).run(
            Step(
                id="iframe-click",
                action="click",
                target=Target(candidates=[Candidate(kind="css", value="#inside")]),
                timeout_ms=1_200,
            )
        )
        assert outcome.status == "failed"
        assert outcome.data.get("unsupported") == "iframe"
        assert outcome.data.get("failure") == FAILURE_NOT_FOUND
    finally:
        session.stop(keep_trace=False)
