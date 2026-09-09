"""从其他环境导入脚本：拷贝、换地址、同名跳过、前置映射。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from autotest_control.flow_import import FlowImportError, import_flows_to_site
from autotest_control.models import Base, Credential, Flow, Site


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


def _cred(cid: str, site_id: str) -> Credential:
    return Credential(
        id=cid,
        tenant_id="default",
        project_id="default",
        site_id=site_id,
        name="admin（表单登录）",
        type="form",
        payload_encrypted="x",
    )


def _flow(
    fid: str,
    site_id: str,
    name: str,
    *,
    cred_id: str | None = None,
    setup_id: str | None = None,
    steps: list[dict] | None = None,
    status: str = "reviewed",
) -> Flow:
    return Flow(
        id=fid,
        tenant_id="default",
        project_id="default",
        site_id=site_id,
        name=name,
        status=status,
        steps=steps or [],
        auth_type="form" if cred_id else "none",
        credential_id=cred_id,
        setup_flow_id=setup_id,
    )


def main() -> int:
    jack = "http://192.168.1.10:9000"
    sakura = "http://192.168.1.20:9000"
    goto = {"id": "s1", "action": "goto", "value": jack + "/app/style"}

    with tempfile.TemporaryDirectory() as temp:
        engine = create_engine(f"sqlite:///{(Path(temp) / 'import.db').as_posix()}")
        Base.metadata.create_all(engine)
        try:
            with Session(engine) as session:
                jack_site = _site("jack", "杰克MES", jack)
                sakura_site = _site("sakura", "樱井MES", sakura)
                create = _flow("f-create", "jack", "新建款式", cred_id="cred-jack", steps=[goto])
                delete = _flow(
                    "f-delete",
                    "jack",
                    "删除款式",
                    cred_id="cred-jack",
                    setup_id="f-create",
                    steps=[{"id": "s1", "action": "screenshot"}],
                )
                session.add_all(
                    [
                        jack_site,
                        sakura_site,
                        _cred("cred-jack", "jack"),
                        _cred("cred-sakura", "sakura"),
                        create,
                        delete,
                    ]
                )
                session.flush()
                by_id = {row.id: row for row in session.scalars(select(Flow)).all()}

                try:
                    import_flows_to_site(session, jack_site, [create], by_id)
                    raise SystemExit("× 从当前环境导入到自己应当拒绝")
                except FlowImportError as exc:
                    _assert("当前环境" in str(exc), "不能从当前环境导入到自己")

                imported, skipped = import_flows_to_site(session, sakura_site, [delete], by_id)
                session.flush()
                _assert(set(imported) == {"新建款式", "删除款式"}, "勾选删除会带上前置新建")
                _assert(not skipped, "目标环境为空则不跳过")

                copies = list(session.scalars(select(Flow).where(Flow.site_id == "sakura")).all())
                by_name = {item.name: item for item in copies}
                _assert(len(copies) == 2, "樱井得到两份拷贝")
                _assert(by_name["新建款式"].imported_from == "杰克MES", "记下源环境名")
                _assert(by_name["新建款式"].status == "draft", "导入后是草稿")
                _assert(by_name["新建款式"].credential_id == "cred-sakura", "登录换成当前环境账号")
                _assert(
                    by_name["新建款式"].steps[0]["value"] == sakura + "/app/style",
                    "打开页地址换成樱井",
                )
                _assert(by_name["删除款式"].setup_flow_id == by_name["新建款式"].id, "前置指向导入后的新建")
                _assert(create.steps[0]["value"].startswith(jack), "不改源环境脚本")

                again_imported, again_skipped = import_flows_to_site(session, sakura_site, [delete], by_id)
                _assert(not again_imported, "第二次导入没有新脚本")
                _assert(len(again_skipped) == 2, "同名全部跳过")

                extra = _site("extra", "示例站点", "http://example.test")
                session.add(extra)
                session.add(_flow("f-dup-create", "extra", "新建款式", steps=[goto]))
                child = _flow(
                    "f-edit",
                    "extra",
                    "编辑款式",
                    setup_id="f-dup-create",
                    steps=[{"id": "s1", "action": "screenshot"}],
                )
                session.add(child)
                session.flush()
                by_id = {row.id: row for row in session.scalars(select(Flow)).all()}
                mapped_imported, mapped_skipped = import_flows_to_site(session, sakura_site, [child], by_id)
                session.flush()
                _assert(mapped_imported == ["编辑款式"], "只拷还没有的编辑")
                _assert(any("新建款式" in msg for msg in mapped_skipped), "已有同名新建则跳过")
                edit = session.scalars(select(Flow).where(Flow.site_id == "sakura", Flow.name == "编辑款式")).one()
                _assert(edit.setup_flow_id == by_name["新建款式"].id, "前置接到当前环境已有的新建")
        finally:
            engine.dispose()

    print("selftest_flow_import ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
