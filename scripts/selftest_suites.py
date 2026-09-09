"""套件成员校验与失败即停自测。"""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from autotest_control.api import _advance_batch, _queue_replay
from autotest_control.models import Base, Batch, Flow, Run, Site
from autotest_control.suites import SuiteError, decide_after_run, resolve_members

_STEP = {
    "id": "s1",
    "action": "click",
    "label": "下一步",
    "target": {"candidates": [{"kind": "text", "value": "下一步"}]},
}


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"× {message}")
    print(f"√ {message}")


def _flow(fid: str, status: str = "reviewed", site_id: str = "site-a", name: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(id=fid, status=status, site_id=site_id, name=name or fid)


def _seed(session: Session) -> tuple[Site, Flow, Flow]:
    site = Site(
        id="site-a",
        tenant_id="default",
        project_id="default",
        name="测站",
        base_url="http://example.test",
    )
    first = Flow(
        id="flow-a",
        tenant_id="default",
        project_id="default",
        site_id=site.id,
        name="建款",
        status="reviewed",
        steps=[_STEP],
    )
    second = Flow(
        id="flow-b",
        tenant_id="default",
        project_id="default",
        site_id=site.id,
        name="补 SKU",
        status="reviewed",
        steps=[_STEP],
    )
    session.add_all([site, first, second])
    session.flush()
    return site, first, second


def _open_batch(session: Session, site: Site, first: Flow, second: Flow) -> tuple[Batch, Run]:
    run = _queue_replay(
        session,
        first,
        site,
        headless=True,
        dry_run=False,
        variables={},
        batch_id="batch-1",
        batch_index=0,
    )
    batch = Batch(
        id="batch-1",
        tenant_id="default",
        project_id="default",
        site_id=site.id,
        name="造完整款式",
        flow_ids=[first.id, second.id],
        items=[
            {"flow_id": first.id, "run_id": run.id, "status": "queued"},
            {"flow_id": second.id, "run_id": None, "status": "pending"},
        ],
        current_index=0,
        current_run_id=run.id,
        status="running",
        headless=True,
        dry_run=False,
        variables={},
    )
    session.add(batch)
    session.flush()
    return batch, run


def main() -> int:
    flows = {
        "a": _flow("a", "reviewed"),
        "b": _flow("b", "golden"),
        "c": _flow("c", "active"),
        "d": _flow("d", "draft"),
        "x": _flow("x", "reviewed", site_id="site-b"),
    }

    members = resolve_members("site-a", ["b", "a", "c"], flows)
    _assert([item.id for item in members] == ["b", "a", "c"], "按提交顺序保留成员")

    try:
        resolve_members("site-a", ["a", "d"], flows)
        raise SystemExit("× 草稿应当被拒绝")
    except SuiteError as exc:
        _assert("草稿" in str(exc), "草稿不能入套件或勾选运行")

    members = resolve_members("site-a", ["a", "x"], flows)
    _assert([item.id for item in members] == ["a", "x"], "同项目脚本可在任一环境勾选运行")

    try:
        resolve_members("site-a", [], flows)
        raise SystemExit("× 空清单应当被拒绝")
    except SuiteError:
        _assert(True, "空清单拒绝")

    try:
        resolve_members("site-a", ["a", "a"], flows)
        raise SystemExit("× 重复成员应当被拒绝")
    except SuiteError:
        _assert(True, "同一清单不能重复勾选")

    _assert(decide_after_run("passed", 2) == "next", "通过且还有后续则入队下一条")
    _assert(decide_after_run("passed", 0) == "passed", "最后一条通过则批次通过")
    _assert(decide_after_run("failed", 3) == "failed", "失败即停")
    _assert(decide_after_run("error", 1) == "failed", "异常也停止")

    with tempfile.TemporaryDirectory() as temp:
        engine = create_engine(f"sqlite:///{(Path(temp) / 'fail.db').as_posix()}")
        Base.metadata.create_all(engine)
        try:
            with Session(engine) as session:
                site, first, second = _seed(session)
                batch, run = _open_batch(session, site, first, second)
                run.status = "failed"
                nxt = _advance_batch(session, run)
                session.flush()
                _assert(nxt is None, "失败不入队下一条")
                _assert(batch.status == "failed", "失败即停标记批次失败")
                _assert(batch.items[1]["status"] == "skipped", "后续条目标为跳过")
        finally:
            engine.dispose()

    with tempfile.TemporaryDirectory() as temp:
        engine = create_engine(f"sqlite:///{(Path(temp) / 'pass.db').as_posix()}")
        Base.metadata.create_all(engine)
        try:
            with Session(engine) as session:
                site, first, second = _seed(session)
                batch, run = _open_batch(session, site, first, second)
                run.status = "passed"
                nxt = _advance_batch(session, run)
                session.flush()
                _assert(nxt is not None and nxt.flow_id == second.id, "通过后入队下一条")
                _assert(batch.status == "running", "批次仍在进行")
                _assert(session.scalar(select(Run).where(Run.flow_id == second.id)) is not None, "第二条已落成 queued")
                nxt.status = "passed"
                done = _advance_batch(session, nxt)
                session.flush()
                _assert(done is None and batch.status == "passed", "全部通过则批次通过")
        finally:
            engine.dispose()

    print("selftest_suites ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
