"""脚本绑到当前环境：换地址、换当前环境的账号。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from autotest_control.models import Base, Credential, Flow, Site
from autotest_control.replay_bind import ReplayBindError, credential_for_site, rebase_steps, rebase_url
from autotest_protocol import Step


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"× {message}")
    print(f"√ {message}")


def _site(sid: str, name: str, url: str) -> Site:
    return Site(
        id=sid,
        tenant_id="default",
        project_id="default",
        name=name,
        base_url=url,
    )


def _cred(cid: str, site_id: str, name: str = "admin（表单登录）") -> Credential:
    return Credential(
        id=cid,
        tenant_id="default",
        project_id="default",
        site_id=site_id,
        name=name,
        type="form",
        payload_encrypted="x",
    )


def _flow(fid: str, site_id: str, cred_id: str | None, auth: str = "form") -> Flow:
    return Flow(
        id=fid,
        tenant_id="default",
        project_id="default",
        site_id=site_id,
        name="新建款式",
        status="reviewed",
        steps=[],
        auth_type=auth,
        credential_id=cred_id,
    )


def main() -> int:
    jack = "http://192.168.1.10:9000"
    sakura = "http://192.168.1.20:9000"
    _assert(
        rebase_url(jack + "/login", jack, sakura) == sakura + "/login",
        "绝对地址从杰克换到樱井",
    )
    _assert(rebase_url("/styles", jack, sakura) == "/styles", "相对路径保持不变")
    _assert(rebase_url(sakura + "/a", jack, sakura) == sakura + "/a", "已经是目标环境则不改")

    step = Step(id="s1", action="goto", value=jack + "/app/style")
    rebound = rebase_steps([step], jack, sakura)
    _assert(rebound[0].value == sakura + "/app/style", "打开页跟着当前环境走")
    _assert(step.value.endswith("/app/style") and "1.10" in step.value, "不改库里原来的步骤")

    with tempfile.TemporaryDirectory() as temp:
        engine = create_engine(f"sqlite:///{(Path(temp) / 'bind.db').as_posix()}")
        Base.metadata.create_all(engine)
        try:
            with Session(engine) as session:
                jack_site = _site("jack", "杰克MES", jack)
                sakura_site = _site("sakura", "樱井MES", sakura)
                jack_cred = _cred("cred-jack", "jack")
                flow = _flow("flow-1", "jack", "cred-jack")
                session.add_all([jack_site, sakura_site, jack_cred, flow])
                session.flush()

                same = credential_for_site(session, flow, jack_site)
                _assert(same.type == "form" and same.ref == "cred-jack", "本环境沿用录制时的凭证")

                try:
                    credential_for_site(session, flow, sakura_site)
                    raise SystemExit("× 异站没有账号应当拒绝")
                except ReplayBindError as exc:
                    _assert("樱井MES" in str(exc) and "登录账号" in str(exc), "异站无凭证时说清楚缺的是登录")

                sakura_cred = _cred("cred-sakura", "sakura")
                session.add(sakura_cred)
                session.flush()
                rebound_auth = credential_for_site(session, flow, sakura_site)
                _assert(rebound_auth.ref == "cred-sakura", "异站有同名凭证则换过去")

                open_flow = _flow("flow-open", "jack", None, auth="none")
                session.add(open_flow)
                session.flush()
                _assert(
                    credential_for_site(session, open_flow, sakura_site).type == "none",
                    "不需要登录的脚本不强制要凭证",
                )
        finally:
            engine.dispose()

    print("selftest_replay_bind ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
