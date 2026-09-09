"""前置脚本展开、剔登录、套件拼成一次运行。"""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from autotest_control.api import _enqueue_chain, _queue_replay
from autotest_control.chain import (
    ChainError,
    compose_chain,
    expand_members,
    expand_setup_chain,
    is_login_step,
    strip_leading_login,
)
from autotest_control.models import Base, Flow, Site
from autotest_protocol import Step


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"× {message}")
    print(f"√ {message}")


def _flow(**kwargs) -> SimpleNamespace:
    defaults = {
        "version": 1,
        "auth_type": "none",
        "credential_id": None,
        "setup_flow_id": None,
        "site_id": "site-a",
        "steps": [],
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _click(step_id: str, label: str, text: str | None = None) -> dict:
    return {
        "id": step_id,
        "action": "click",
        "label": label,
        "target": {"candidates": [{"kind": "text", "value": text or label}]},
    }


def _fill(step_id: str, label: str, value: str, placeholder: str) -> dict:
    return {
        "id": step_id,
        "action": "fill",
        "label": label,
        "value": value,
        "target": {"candidates": [{"kind": "placeholder", "value": placeholder}]},
    }


_LOGIN_STEPS = [
    {"id": "g1", "action": "goto", "label": "打开登录页", "value": "https://example.test/login"},
    _fill("u1", "填写用户名", "admin", "请输入您的账号"),
    _fill("p1", "填写密码", "secret", "请输入密码"),
    _click("c1", "点击「登录」", "登录"),
    {"id": "w1", "action": "waitFor", "label": "等待工作台", "condition": "network_idle"},
]

_CREATE_MAIN = [
    _fill("n1", "填写款名", "{{unique:style_name}}", "款式名称"),
    _click("s1", "点击「保存」", "保存"),
]

_DELETE_MAIN = [
    _click("d1", "点击「删除」", "删除"),
]


def main() -> int:
    create = _flow(id="create", name="新建款式", steps=_LOGIN_STEPS + _CREATE_MAIN)
    delete = _flow(
        id="delete",
        name="删除款式",
        setup_flow_id="create",
        steps=_LOGIN_STEPS + _DELETE_MAIN,
        auth_type="form",
        credential_id="cred-1",
    )
    by_id = {"create": create, "delete": delete}

    chain = expand_setup_chain(delete, by_id)
    _assert([item.id for item in chain] == ["create", "delete"], "删除展开为 新建 → 删除")
    _assert(expand_setup_chain(create, by_id)[0].id == "create", "没有前置则只含本条")

    members = expand_members([delete], by_id)
    _assert([item.id for item in members] == ["create", "delete"], "套件只勾删除也会带上前置")

    both = expand_members([create, delete], by_id)
    _assert([item.id for item in both] == ["create", "delete"], "套件已含前置时不重复")

    reversed_members = expand_members([delete, create], by_id)
    _assert(
        [item.id for item in reversed_members] == ["create", "delete"],
        "勾选顺序乱了也按前置排到前面",
    )

    loop_a = _flow(id="a", name="A", setup_flow_id="b", steps=_CREATE_MAIN)
    loop_b = _flow(id="b", name="B", setup_flow_id="a", steps=_CREATE_MAIN)
    try:
        expand_setup_chain(loop_a, {"a": loop_a, "b": loop_b})
        raise SystemExit("× 循环应当被拒绝")
    except ChainError as exc:
        _assert("循环" in str(exc), "前置循环报错")

    self_ref = _flow(id="self", name="自己", setup_flow_id="self", steps=_CREATE_MAIN)
    try:
        expand_setup_chain(self_ref, {"self": self_ref})
        raise SystemExit("× 自指应当被拒绝")
    except ChainError as exc:
        _assert("自己" in str(exc), "不能把自己当成前置")

    missing = _flow(id="x", name="删", setup_flow_id="gone", steps=_DELETE_MAIN)
    try:
        expand_setup_chain(missing, {"x": missing})
        raise SystemExit("× 缺失前置应当被拒绝")
    except ChainError as exc:
        _assert("不存在" in str(exc), "前置不存在时报错")

    other_site = _flow(id="y", name="外站新建", site_id="site-b", steps=_CREATE_MAIN)
    host = _flow(id="z", name="本站删除", setup_flow_id="y", steps=_DELETE_MAIN)
    crossed = expand_setup_chain(host, {"z": host, "y": other_site})
    _assert([item.id for item in crossed] == ["y", "z"], "前置可以来自同项目其他环境")

    login_steps = [Step.model_validate(item) for item in _LOGIN_STEPS]
    _assert(all(is_login_step(step) for step in login_steps[:4]), "登录步被识别")
    _assert(
        not is_login_step(Step.model_validate(_CREATE_MAIN[0])),
        "填款名不是登录",
    )
    stripped = strip_leading_login(login_steps + [Step.model_validate(_DELETE_MAIN[0])])
    _assert(
        [step.id for step in stripped] == ["d1"],
        "后续流程开头的登录和等待被剥掉",
    )
    kept = strip_leading_login([Step.model_validate(_DELETE_MAIN[0])])
    _assert([step.id for step in kept] == ["d1"], "没有登录则整段保留")

    name, steps, auth = compose_chain([create, delete])
    _assert(name == "新建款式 → 删除款式", "拼接后的流程名")
    _assert(auth.type == "none" and auth.ref is None, "第一条靠录制登录时不注入后面的凭证")
    _assert(steps[0].id.startswith("c1_"), "第一条步骤加前缀")
    _assert(any(step.id.startswith("c1_") and "登录" in (step.label or "") for step in steps), "第一条保留登录")
    second = [step for step in steps if step.id.startswith("c2_")]
    _assert(len(second) == 1 and second[0].id == "c2_d1", "第二条只留下删除")
    _assert(second[0].label.startswith("删除款式："), "步骤标签带流程名")
    _assert(
        any(step.value == "{{unique:style_name}}" for step in steps),
        "新建填的唯一值模板原样保留，同一次运行才展开",
    )

    create_only_cred = _flow(
        id="create",
        name="新建款式",
        steps=_LOGIN_STEPS + _CREATE_MAIN,
        auth_type="form",
        credential_id="cred-create",
    )
    delete_also_cred = _flow(
        id="delete",
        name="删除款式",
        steps=_LOGIN_STEPS + _DELETE_MAIN,
        auth_type="form",
        credential_id="cred-delete",
    )
    _, _, auth_first = compose_chain([create_only_cred, delete_also_cred])
    _assert(auth_first.ref == "cred-create", "两条都有凭证时只用第一条，避免登两次")

    try:
        compose_chain([
            create,
            _flow(id="login-only", name="只登录", steps=_LOGIN_STEPS),
        ])
        raise SystemExit("× 去掉登录后为空应当被拒绝")
    except ChainError as exc:
        _assert("没有可执行步骤" in str(exc), "后续只剩登录则报错")

    with tempfile.TemporaryDirectory() as temp:
        engine = create_engine(f"sqlite:///{(Path(temp) / 'chain.db').as_posix()}")
        Base.metadata.create_all(engine)
        try:
            with Session(engine) as session:
                site = Site(
                    id="site-a",
                    tenant_id="default",
                    project_id="default",
                    name="测站",
                    base_url="https://example.test",
                )
                first = Flow(
                    id="flow-create",
                    tenant_id="default",
                    project_id="default",
                    site_id=site.id,
                    name="新建款式",
                    status="reviewed",
                    steps=_LOGIN_STEPS + _CREATE_MAIN,
                    auth_type="form",
                    credential_id="cred-1",
                )
                second = Flow(
                    id="flow-delete",
                    tenant_id="default",
                    project_id="default",
                    site_id=site.id,
                    name="删除款式",
                    status="reviewed",
                    steps=_LOGIN_STEPS + _DELETE_MAIN,
                    setup_flow_id="flow-create",
                    auth_type="form",
                    credential_id="cred-2",
                )
                session.add_all([site, first, second])
                session.flush()

                single = _queue_replay(session, first, site, headless=True, dry_run=False)
                _assert(
                    single.job["flow"]["steps"][0]["id"] == "g1",
                    "单独跑前置时不改步骤 id，定位修复还能对上",
                )

                chained = _queue_replay(session, second, site, headless=True, dry_run=False)
                _assert(chained.flow_id == "flow-delete", "运行归属用户点的那条")
                _assert(chained.job["flow"]["name"] == "新建款式 → 删除款式", "入队任务已拼接")
                step_ids = [item["id"] for item in chained.job["flow"]["steps"]]
                _assert(step_ids[0].startswith("c1_") and "c2_d1" in step_ids, "拼接后带前缀")
                _assert(
                    chained.job["auth"]["ref"] == "cred-1",
                    "链式运行只用第一条的凭证",
                )

                suite_run = _enqueue_chain(
                    session,
                    [first, second],
                    site,
                    headless=True,
                    dry_run=False,
                )
                labels = [item["label"] for item in suite_run.job["flow"]["steps"]]
                _assert(
                    any(label.startswith("新建款式：") for label in labels)
                    and any(label.startswith("删除款式：") for label in labels),
                    "套件成员拼进同一次运行",
                )
                _assert(
                    sum("登录" in (label or "") for label in labels) >= 1
                    and not any(label.startswith("删除款式：") and "登录" in label for label in labels),
                    "套件只保留第一段登录",
                )
        finally:
            engine.dispose()

    print("selftest_chain ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
