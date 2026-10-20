"""失败原因分类：只有「目标确实变化」才允许判候选失效。

浮层没打开 / 被遮挡 / 超时都是环境原因，候选本身没被证伪。把它们写进
`LocatorMemory.bad` 会在下一次回放里把好候选从脚本里删掉，并写回控制面生成
修补任务——缺陷随时间反向污染已录资产，比当次失败严重得多。
"""

from __future__ import annotations

import pytest
from playwright.sync_api import sync_playwright

from autotest_executor.browser.locator import (
    CandidateFailure,
    FailureKind,
    LocatorMemory,
    TargetNotFound,
    resolve_target,
)
from autotest_protocol import Candidate, Target, TargetScope
from autotest_protocol.dsl import candidate_key
from tests.conftest import require_browser

# 首选录在浮层里，次选是页面上真实存在的文字——浮层没出现时会退到它
IN_DROPDOWN = Candidate(kind="css", value=".ant-select-item-option")
ON_PAGE = Candidate(kind="text", value="品牌A")

_STYLE = """
<style>
  .ant-select-dropdown { position: absolute; top: 40px; left: 20px; width: 200px;
                         border: 1px solid #d9d9d9; background: #fff; }
  .ant-select-item-option, .page-option { padding: 6px 12px; }
</style>
"""

# 浮层没出现：页面只有次选能命中的文字
NO_OVERLAY = f"""<!doctype html><meta charset="utf-8">{_STYLE}
<div class="page-option">品牌A</div>
"""

# 浮层在，但首选要的那个节点真的没了（下拉是空态）
OVERLAY_WITHOUT_OPTION = f"""<!doctype html><meta charset="utf-8">{_STYLE}
<div class="page-option">品牌A</div>
<div class="ant-select-dropdown"><div class="ant-select-empty">暂无数据</div></div>
"""

# 浮层在，两个候选都能解析——是「点不到」把首选排除掉的，不是它不存在
OVERLAY_WITH_BOTH = f"""<!doctype html><meta charset="utf-8">{_STYLE}
<div class="page-option">品牌A</div>
<div class="ant-select-dropdown"><div class="rc-virtual-list">
  <div class="ant-select-item-option">品牌A</div>
</div></div>
"""


def _target() -> Target:
    """每次新建：remember 会改写 target.candidates，模块级常量会被串味。"""
    return Target(candidates=[IN_DROPDOWN, ON_PAGE], scope=TargetScope(kind="dropdown"))


def _resolve(
    html: str,
    memory: LocatorMemory,
    target: Target,
    timeout_ms: int = 400,
    skip: dict[str, str] | None = None,
):
    """解析一次并返回结果。locator 不能带出 with 块，这里只读纯数据字段。"""
    require_browser()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(html)
            return resolve_target(
                page, target, timeout_ms=timeout_ms, memory=memory, step_id="s1", skip=skip
            )
        finally:
            browser.close()


def _resolve_error(html: str, memory: LocatorMemory, target: Target, timeout_ms: int = 400):
    try:
        _resolve(html, memory, target, timeout_ms)
    except TargetNotFound as exc:
        return exc
    raise AssertionError("应当报 TargetNotFound")


def test_overlay_absent_does_not_judge_candidates_stale() -> None:
    """浮层没出现，退到页面兜底命中——这一轮失败说明不了首选失效。"""
    memory = LocatorMemory()
    target = _target()
    resolution = _resolve(NO_OVERLAY, memory, target)

    assert resolution.candidate.describe() == ON_PAGE.describe()
    assert resolution.fallback_index == 1
    assert resolution.environmental is True
    assert memory.bad == set(), "环境原因不得进 bad"
    assert memory.updates == [], "环境原因不得写回候选更新（否则会生成修补任务）"
    assert [c.describe() for c in target.candidates] == [
        IN_DROPDOWN.describe(),
        ON_PAGE.describe(),
    ], "环境原因不得删候选、也不得改首选"


def test_overlay_present_with_missing_target_judges_candidate_stale() -> None:
    """浮层在，首选要的节点确实没了——这才是漂移，该判该改。"""
    memory = LocatorMemory()
    target = _target()
    resolution = _resolve(OVERLAY_WITHOUT_OPTION, memory, target)

    assert resolution.candidate.describe() == ON_PAGE.describe()
    assert resolution.fallback_index == 1
    assert resolution.environmental is False
    assert candidate_key(IN_DROPDOWN) in memory.bad, "目标确实变化要进 bad"
    assert len(memory.updates) == 1, "目标确实变化要写回候选更新"
    assert [c.describe() for c in target.candidates] == [ON_PAGE.describe()], "失效候选被删掉"


def test_all_candidates_missed_without_overlay_reports_environment() -> None:
    """全都没命中、且浮层没出现时，报的是环境原因，不是「脚本里的候选全坏了」。"""
    memory = LocatorMemory()
    target = Target(
        candidates=[Candidate(kind="css", value=".ant-select-item-option")],
        scope=TargetScope(kind="dropdown"),
    )
    exc = _resolve_error(NO_OVERLAY, memory, target)

    assert exc.kind == FailureKind.OVERLAY_ABSENT
    assert "浮层" in str(exc)
    assert memory.bad == set(), "环境原因不得进 bad"
    assert memory.updates == []


def test_remember_gate_is_per_failure_not_per_call() -> None:
    """同一次调用里混着两类失败时，只把「目标确实变化」那个判死。"""
    memory = LocatorMemory()
    target = _target()
    memory.remember(
        target,
        winner=ON_PAGE,
        failed=[
            CandidateFailure(IN_DROPDOWN, FailureKind.OVERLAY_ABSENT),
            CandidateFailure(Candidate(kind="label", value="品牌"), FailureKind.TARGET_CHANGED),
        ],
        step_id="s1",
    )

    assert candidate_key(IN_DROPDOWN) not in memory.bad
    assert "label='品牌'" in memory.bad


def test_remember_with_only_environmental_failures_leaves_script_alone() -> None:
    """纯环境原因：连首选都不许改——退到兜底撞上的命中不该升为首选。"""
    memory = LocatorMemory()
    target = _target()
    memory.remember(
        target,
        winner=ON_PAGE,
        failed=[CandidateFailure(IN_DROPDOWN, FailureKind.OVERLAY_ABSENT)],
        step_id="s1",
    )

    assert memory.updates == []
    assert [c.describe() for c in target.candidates] == [
        IN_DROPDOWN.describe(),
        ON_PAGE.describe(),
    ]
    assert memory.good[candidate_key(ON_PAGE)].describe() == ON_PAGE.describe(), "命中仍要记住"


@pytest.mark.parametrize(
    "kind", [FailureKind.OVERLAY_ABSENT, FailureKind.COVERED, FailureKind.TIMEOUT]
)
def test_environmental_kinds_are_all_gated(kind: str) -> None:
    """三类环境原因一个都不能漏——漏一类就是一条删好候选的路径。"""
    memory = LocatorMemory()
    target = _target()
    memory.remember(
        target, winner=ON_PAGE, failed=[CandidateFailure(IN_DROPDOWN, kind)], step_id="s1"
    )
    assert memory.bad == set()
    assert memory.updates == []


def test_skipped_candidate_falls_through_without_being_judged_stale() -> None:
    """点不到的候选要能被跳过（第 3 节），但按环境原因记，不判失效（第 5 节）。

    两个候选都能解析，是 `skip` 把首选排除掉的——这正是点击回退的形态。
    """
    memory = LocatorMemory()
    target = _target()
    resolution = _resolve(
        OVERLAY_WITH_BOTH,
        memory,
        target,
        skip={candidate_key(IN_DROPDOWN): FailureKind.COVERED},
    )

    assert resolution.candidate.describe() == ON_PAGE.describe()
    assert resolution.fallback_index == 1
    assert resolution.environmental is True
    assert "点不动" in resolution.drift_note
    assert "定位漂移" not in resolution.drift_note
    assert memory.bad == set(), "点不到不是候选失效"
    assert memory.updates == []
    assert [c.describe() for c in target.candidates] == [
        IN_DROPDOWN.describe(),
        ON_PAGE.describe(),
    ], "跳过首选不得改写脚本"


def test_without_skip_the_same_page_still_hits_the_first_candidate() -> None:
    """对照组：不跳过时首选照常命中，说明上一条的变化确实来自 skip。"""
    memory = LocatorMemory()
    resolution = _resolve(OVERLAY_WITH_BOTH, memory, _target())

    assert resolution.candidate.describe() == IN_DROPDOWN.describe()
    assert resolution.fallback_index == 0
    assert resolution.drifted is False
    assert memory.updates == []
