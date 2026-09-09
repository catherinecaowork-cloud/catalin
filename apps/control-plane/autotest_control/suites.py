"""套件成员校验与失败即停决策。"""

from __future__ import annotations

from typing import Protocol

CONFIRMED_STATUSES = frozenset({"reviewed", "golden", "active"})


class SuiteError(ValueError):
    """成员不合法，控制面转成 409。"""


class FlowLike(Protocol):
    id: str
    name: str
    status: str
    site_id: str


def decide_after_run(run_status: str, remaining_count: int) -> str:
    """前一条结束后批次怎么走：next / passed / failed。"""
    if run_status == "passed":
        return "next" if remaining_count > 0 else "passed"
    return "failed"


def resolve_members(
    site_id: str,
    flow_ids: list[str],
    flows_by_id: dict[str, FlowLike],
) -> list[FlowLike]:
    if not flow_ids:
        raise SuiteError("至少勾选一条已确认用例")
    ordered: list[FlowLike] = []
    seen: set[str] = set()
    for flow_id in flow_ids:
        if flow_id in seen:
            raise SuiteError("同一清单里不要重复勾选同一条用例")
        seen.add(flow_id)
        flow = flows_by_id.get(flow_id)
        if flow is None:
            raise SuiteError("流程不存在或不属于当前项目")
        if flow.status not in CONFIRMED_STATUSES:
            raise SuiteError(f"「{flow.name}」还是草稿，不能入套件或勾选运行")
        ordered.append(flow)
    return ordered
