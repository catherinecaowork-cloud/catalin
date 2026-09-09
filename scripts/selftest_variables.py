"""P1.2 协议字段与步骤变量运行时自测。"""

from __future__ import annotations

from pydantic import ValidationError

from autotest_executor.variables import VariableResolutionError, resolve_steps
from autotest_protocol import Flow, Job, Step


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"× {message}")
    print(f"√ {message}")


def _rejects(call, message: str) -> None:
    try:
        call()
    except VariableResolutionError:
        print(f"√ {message}")
        return
    raise SystemExit(f"× {message}")


def main() -> int:
    target = {"candidates": [{"kind": "text", "value": "{{unique:target}}"}]}
    flow = Flow(
        name="变量自测",
        steps=[
            Step(
                id="fill",
                action="fill",
                phase="main",
                target=target,
                value="{{unique:code}}-{{env:suffix}}",
            ),
            Step(
                id="assert",
                action="assert",
                phase="verify",
                assert_kind="text_contains",
                expected="{{unique:code}}/{{now:%Y%m%d}}",
            ),
        ],
    )
    resolved = resolve_steps(flow.steps, {"suffix": "blue"})

    unique = resolved[0].value.removesuffix("-blue")
    _assert(unique.startswith("AT_"), "unique 值带 AT_ 前缀")
    _assert(resolved[1].expected.startswith(f"{unique}/"), "同一 run 同 key 保持一致")
    _assert(resolved[0].value.endswith("-blue"), "env 从 Job variables 对应值展开")
    _assert(len(resolved[1].expected.split("/", 1)[1]) == 8, "now 按指定格式展开")
    _assert(resolved[0] is not flow.steps[0], "执行步骤是原步骤的副本")
    _assert(flow.steps[0].value == "{{unique:code}}-{{env:suffix}}", "原步骤值未被修改")
    _assert(
        resolved[0].target is not flow.steps[0].target
        and resolved[0].target.candidates[0].value == "{{unique:target}}",
        "target 被复制但不展开",
    )

    _rejects(
        lambda: resolve_steps([Step(id="x", action="goto", value="{{other:key}}")]),
        "未知变量类型被拒绝",
    )
    _rejects(
        lambda: resolve_steps([Step(id="x", action="goto", value="{{env:{{key}}}}")]),
        "嵌套变量被拒绝",
    )
    _rejects(
        lambda: resolve_steps([Step(id="x", action="goto", value="{{env:missing}}")]),
        "缺失 env 被拒绝",
    )
    _rejects(
        lambda: resolve_steps([Step(id="x", action="goto", value="{{now:%Q}}")]),
        "未知时间格式指令被拒绝",
    )

    job = Job(
        run_id="run-p12",
        site={"id": "site", "base_url": "https://example.test"},
        flow=flow,
        record_intent="新增款式",
        variables={"suffix": "blue"},
    )
    _assert(job.record_intent == "新增款式" and job.variables["suffix"] == "blue", "Job 新字段可用")
    _assert(job.flow.steps[0].phase == "main", "Step phase 可用")
    try:
        Step(id="bad-phase", action="screenshot", phase="cleanup")
    except ValidationError:
        print("√ 非法 phase 被协议拒绝")
    else:
        raise SystemExit("× 非法 phase 被协议拒绝")

    print("\n变量运行时自测通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
