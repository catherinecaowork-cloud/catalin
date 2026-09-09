"""把一条流程绑到当前要跑的环境上。

脚本属于录制时的站点。要用在别的环境，先在运行页从其他环境导入一份拷贝。
回放时仍会把地址换成当前站点，登录用当前环境的账号。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse, urlunparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from autotest_control.chain import parse_steps
from autotest_control.models import Credential, Flow, Site
from autotest_protocol import AuthRef, Step


class ReplayBindError(ValueError):
    """跨环境绑定时缺登录账号等，控制面转成 409。"""


def rebase_url(value: str, from_base: str, to_base: str) -> str:
    if not value or not from_base or not to_base:
        return value
    source = from_base.rstrip("/")
    target = to_base.rstrip("/")
    if source == target:
        return value
    if value.startswith(source):
        return target + value[len(source) :]
    try:
        src = urlparse(source)
        dst = urlparse(target)
        current = urlparse(value)
    except Exception:
        return value
    if current.scheme and current.netloc and src.netloc and current.netloc == src.netloc:
        return urlunparse(
            (dst.scheme or current.scheme, dst.netloc, current.path, current.params, current.query, current.fragment)
        )
    return value


def rebase_steps(steps: list[Step], from_base: str, to_base: str) -> list[Step]:
    rebound: list[Step] = []
    for step in steps:
        cloned = step.model_copy(deep=True)
        if cloned.value:
            cloned.value = rebase_url(cloned.value, from_base, to_base)
        rebound.append(cloned)
    return rebound


def bind_flow_steps(session: Session, flow: Flow, site: Site) -> list[Step]:
    steps = parse_steps(getattr(flow, "steps", None))
    origin = session.get(Site, flow.site_id)
    if origin is None:
        return steps
    return rebase_steps(steps, origin.base_url, site.base_url)


def _missing_login(session: Session, flow: Flow, site: Site) -> ReplayBindError:
    site_name = getattr(site, "name", None) or "当前环境"
    flow_name = getattr(flow, "name", None) or "该脚本"
    origin = session.get(Site, getattr(flow, "site_id", None))
    hint = ""
    if origin is not None and origin.id != getattr(site, "id", None):
        hint = f"或把顶栏切回「{origin.name}」再跑。"
    return ReplayBindError(
        f"「{flow_name}」需要登录，但「{site_name}」还没有登录账号。"
        f"请先在该环境添加表单登录凭证。{hint}"
    )


def credential_for_site(session: Session, flow: Flow, site: Site) -> AuthRef:
    """登录账号跟环境走：到樱井就用樱井的凭证，不用杰克那份。

    脚本本身不写登录步骤；回放时由当前环境的凭证注入。
    需要登录却找不到账号时必须拒绝，不能默默从业务第一步开始。
    """
    auth_type = getattr(flow, "auth_type", None) or "none"
    credential_id = getattr(flow, "credential_id", None)
    if auth_type == "none":
        return AuthRef(type="none", ref=None)
    if flow.site_id == site.id:
        if credential_id:
            return AuthRef(type=auth_type, ref=credential_id)
        raise _missing_login(session, flow, site)
    origin = session.get(Credential, credential_id) if credential_id else None
    creds = list(session.scalars(select(Credential).where(Credential.site_id == site.id)).all())
    if origin:
        named = next((item for item in creds if item.name == origin.name), None)
        if named:
            return AuthRef(type=named.type, ref=named.id)
        typed = next((item for item in creds if item.type == origin.type), None)
        if typed:
            return AuthRef(type=typed.type, ref=typed.id)
    if creds:
        form = next((item for item in creds if item.type == "form"), creds[0])
        return AuthRef(type=form.type, ref=form.id)
    raise _missing_login(session, flow, site)


def bind_flow_for_site(session: Session, flow: Flow, site: Site) -> Any:
    """给链式拼接一份不写库的副本：步骤已换成当前环境地址。"""
    steps = [step.model_dump(mode="json") for step in bind_flow_steps(session, flow, site)]
    return SimpleNamespace(
        id=flow.id,
        name=flow.name,
        site_id=flow.site_id,
        steps=steps,
        setup_flow_id=getattr(flow, "setup_flow_id", None),
        auth_type=getattr(flow, "auth_type", None) or "none",
        credential_id=getattr(flow, "credential_id", None),
        version=getattr(flow, "version", 1),
    )
