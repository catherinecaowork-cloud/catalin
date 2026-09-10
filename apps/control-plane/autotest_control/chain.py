"""前置脚本展开与套件拼接。

删除款式不能对着空库乱删：先跑新建，再删刚建的那条。
链式 / 套件回放共用一个浏览器、同一套 {{unique}} / {{now}}。
后续流程里录到的登录步会剥掉，只留第一条的登录。
"""

from __future__ import annotations

import re
from typing import Any, Protocol, Sequence

from autotest_protocol import AuthRef, Step

_LOGIN_TEXT_RE = re.compile(
    r"登录|登陆|登\s*录|填写用户名|填写密码|打开登录页|提交登录|"
    r"请输入您的账号|请输入账号|请输入密码|请输入用户名"
)
_LOGIN_FIELD_RE = re.compile(r"密码|password|username|用户名|账号", re.I)
_LOGIN_URL_RE = re.compile(r"(login|signin|sign-in|/auth)(/|$|\?|#)", re.I)
_LOGIN_CLICK_RE = re.compile(r"^(点击[「「]?)?(登录|登陆|登\s*录)[」」]?$")


class ChainError(ValueError):
    """前置链不合法，控制面转成 409。"""


class FlowLike(Protocol):
    id: str
    name: str
    site_id: str
    steps: list[Any]
    setup_flow_id: str | None
    setup_flow_ids: list[str] | None


def _direct_setup_ids(flow: FlowLike) -> list[str]:
    setup_ids = list(getattr(flow, "setup_flow_ids", None) or [])
    if setup_ids:
        return setup_ids
    setup_id = getattr(flow, "setup_flow_id", None) or None
    return [setup_id] if setup_id else []


def _depends_on(flow: FlowLike, target_id: str, by_id: dict[str, FlowLike], visiting: set[str]) -> bool:
    if flow.id in visiting:
        return False
    visiting.add(flow.id)
    for setup_id in _direct_setup_ids(flow):
        if setup_id == target_id:
            return True
        setup = by_id.get(setup_id)
        if setup is not None and _depends_on(setup, target_id, by_id, visiting):
            return True
    return False


def expand_setup_chain(
    flow: FlowLike,
    by_id: dict[str, FlowLike],
    *,
    _stack: tuple[str, ...] = (),
) -> list[FlowLike]:
    """从叶子往根展开：先前置，再本条。"""
    if flow.id in _stack:
        names = [by_id[i].name if i in by_id else i for i in (*_stack, flow.id)]
        raise ChainError("前置脚本互相指向，形成循环：" + " → ".join(names))
    setup_ids = list(getattr(flow, "setup_flow_ids", None) or [])
    if setup_ids:
        if flow.id in setup_ids:
            raise ChainError(f"「{flow.name}」不能把自己放进前置列表")
        chain: list[FlowLike] = []
        for setup_id in setup_ids:
            if setup_id in _stack:
                names = [by_id[i].name if i in by_id else i for i in (*_stack, flow.id)]
                raise ChainError("前置脚本互相指向，形成循环：" + " → ".join(names))
            if setup_id == flow.id:
                raise ChainError(f"「{flow.name}」不能把自己当成前置")
            setup = by_id.get(setup_id)
            if setup is None:
                raise ChainError(f"「{flow.name}」的前置脚本已不存在，请重新选择")
            if _depends_on(setup, flow.id, by_id, set()):
                raise ChainError(f"「{setup.name}」已依赖「{flow.name}」，不能互为前置")
            chain.append(setup)
        chain.append(flow)
        return chain

    chain: list[FlowLike] = []
    setup_id = getattr(flow, "setup_flow_id", None) or None
    if setup_id:
        if setup_id == flow.id:
            raise ChainError(f"「{flow.name}」不能把自己当成前置")
        setup = by_id.get(setup_id)
        if setup is None:
            raise ChainError(f"「{flow.name}」的前置脚本已不存在，请重新选择")
        chain.extend(expand_setup_chain(setup, by_id, _stack=(*_stack, flow.id)))
    chain.append(flow)
    return chain


def expand_members(members: Sequence[FlowLike], by_id: dict[str, FlowLike]) -> list[FlowLike]:
    """套件 / 勾选：每人先展开前置，再按出现顺序去重。"""
    ordered: list[FlowLike] = []
    seen: set[str] = set()
    for member in members:
        for flow in expand_setup_chain(member, by_id):
            if flow.id in seen:
                continue
            ordered.append(flow)
            seen.add(flow.id)
    return ordered


def parse_steps(raw: Sequence[Any] | None) -> list[Step]:
    steps: list[Step] = []
    for item in raw or []:
        if isinstance(item, Step):
            steps.append(item)
        else:
            steps.append(Step.model_validate(item))
    return steps


def _haystack(step: Step) -> str:
    parts = [step.id or "", step.label or "", step.value or ""]
    if step.target is not None:
        for candidate in step.target.candidates:
            parts.append(candidate.value or "")
            if candidate.name:
                parts.append(candidate.name)
    return " ".join(parts)


def is_login_step(step: Step) -> bool:
    if (step.id or "").startswith("login."):
        return True
    text = _haystack(step)
    if _LOGIN_TEXT_RE.search(text):
        return True
    if step.action == "goto" and step.value and _LOGIN_URL_RE.search(step.value):
        return True
    if step.action == "fill" and _LOGIN_FIELD_RE.search(text):
        return True
    label = (step.label or "").strip()
    if step.action == "click" and _LOGIN_CLICK_RE.match(label):
        return True
    return False


def strip_leading_login(steps: Sequence[Step]) -> list[Step]:
    """从第二条流程起，去掉开头录到的登录（含夹在中间的等待/截图）。"""
    items = list(steps)
    if not items:
        return items
    index = 0
    last_login = -1
    while index < len(items):
        if is_login_step(items[index]):
            last_login = index
            index += 1
            continue
        if last_login >= 0 and items[index].action in {"waitFor", "screenshot"}:
            index += 1
            continue
        break
    return items[index:]


def auth_ref_for_chain(flows: Sequence[FlowLike]) -> AuthRef:
    """凭证只跟第一条走：后续流程的登录会剥掉，不能再注入一份 form_login。"""
    first = flows[0]
    return AuthRef(
        type=getattr(first, "auth_type", None) or "none",
        ref=getattr(first, "credential_id", None),
    )


def compose_chain(flows: Sequence[FlowLike]) -> tuple[str, list[Step], AuthRef]:
    """把多条流程拼成一份 Job 步骤。单条时调用方不要走这里，以免改步骤 id。"""
    if not flows:
        raise ChainError("没有可执行的流程")
    composed: list[Step] = []
    for index, flow in enumerate(flows):
        steps = parse_steps(getattr(flow, "steps", None))
        if index > 0:
            steps = strip_leading_login(steps)
        if not steps:
            raise ChainError(f"「{flow.name}」去掉登录后没有可执行步骤")
        prefix = f"c{index + 1}_"
        for step in steps:
            cloned = step.model_copy(deep=True)
            cloned.id = prefix + step.id
            cloned.label = f"{flow.name}：{step.display()}"
            composed.append(cloned)
    name = " → ".join(flow.name for flow in flows)
    return name, composed, auth_ref_for_chain(flows)
