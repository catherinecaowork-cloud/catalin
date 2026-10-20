"""定位学习：失败过的候选要删掉，下次从命中的那个开始——但环境原因除外。"""

from __future__ import annotations

from autotest_executor.browser.locator import (
    CandidateFailure,
    FailureKind,
    LocatorMemory,
)
from autotest_protocol import Candidate, Target, TargetScope, learn_candidates
from autotest_protocol.dsl import candidate_key


def _assert(cond: bool, message: str) -> None:
    if not cond:
        raise SystemExit(f"× {message}")
    print(f"√ {message}")


def main() -> int:
    role = Candidate(kind="role", value="button", name="新增")
    text = Candidate(kind="text", value="新增")
    css = Candidate(kind="css", value="button.ant-btn")
    learned = learn_candidates([role, text, css], winner=text, failed=[role])
    _assert(learned[0].kind == "text", "命中的候选排第一")
    _assert(all(item.kind != "role" for item in learned), "已空等失败的候选被删掉")
    _assert(any(item.kind == "css" for item in learned), "没试过的候选留着当退路")

    only = learn_candidates([role, text], winner=text, failed=[role])
    _assert(len(only) == 1 and only[0].kind == "text", "没有退路时只保留命中项")

    # 环境原因不得删候选。浮层没打开 / 被遮挡 / 超时都说明不了候选本身有问题，
    # 判成失效会在下一次回放里把好候选删掉，并写回控制面生成修补任务。
    for kind in (FailureKind.OVERLAY_ABSENT, FailureKind.COVERED, FailureKind.TIMEOUT):
        memory = LocatorMemory()
        target = Target(candidates=[role, text, css], scope=TargetScope(kind="dropdown"))
        memory.remember(target, winner=text, failed=[CandidateFailure(role, kind)], step_id="s1")
        _assert(memory.bad == set(), f"{kind}：不进 bad")
        _assert(memory.updates == [], f"{kind}：不写回候选更新（监督者据此不生成修补任务）")
        _assert(len(target.candidates) == 3, f"{kind}：不删候选、也不改首选")

    # 目标确实变化才是漂移：该判、该删、该写回
    memory = LocatorMemory()
    target = Target(candidates=[role, text, css], scope=TargetScope(kind="dropdown"))
    memory.remember(
        target,
        winner=text,
        failed=[CandidateFailure(role, FailureKind.TARGET_CHANGED)],
        step_id="s1",
    )
    _assert(candidate_key(role) in memory.bad, "目标确实变化：进 bad")
    _assert(len(memory.updates) == 1, "目标确实变化：写回候选更新")
    _assert([item.kind for item in target.candidates] == ["text", "css"], "目标确实变化：删掉失效候选")

    print("\n定位学习自测通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
