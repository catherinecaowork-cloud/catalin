"""阶段 C：最小对象库 — 登记、步骤引用、改定义修多流程（无浏览器 / 无内网）。"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from autotest_control.deps import Scope
from autotest_control.domain.objects import (
    ObjectNotFound,
    load_site_object_map,
    resolve_steps_objects,
)
from autotest_control.models import Base, Flow, Site, UiObject
from autotest_control.replay_bind import ReplayBindError, bind_flow_steps
from autotest_protocol import Candidate, Step, Target

SCOPE = Scope(tenant_id="default", project_id="default")


@pytest.fixture()
def session() -> Session:
    temp = tempfile.mkdtemp()
    db_path = Path(temp) / "test.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = factory()
    db.add(
        Site(
            id="site-1",
            tenant_id="default",
            project_id="default",
            name="自测站",
            base_url="http://example.test",
            env="test",
            adapter="generic",
            probe_error_url_patterns=[],
        )
    )
    db.commit()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()
        db_path.unlink(missing_ok=True)
        Path(temp).rmdir()


def _target(css: str) -> dict:
    return Target(candidates=[Candidate(kind="css", value=css)]).model_dump(mode="json")


def test_step_accepts_object_id_without_inline_target() -> None:
    step = Step(id="s1", action="click", object_id="obj-1", label="保存")
    assert step.object_id == "obj-1"
    assert step.target is None


def test_resolve_object_id_fills_target(session: Session) -> None:
    session.add(
        UiObject(
            id="obj-save",
            tenant_id="default",
            project_id="default",
            site_id="site-1",
            key="style.save",
            name="保存按钮",
            target=_target("#save"),
        )
    )
    session.commit()
    objects = load_site_object_map(session, SCOPE, "site-1")
    steps = [
        Step(id="click_save", action="click", object_id="obj-save", label="点保存"),
        Step(id="goto_home", action="goto", value="/home"),
    ]
    resolved = resolve_steps_objects(steps, objects)
    assert resolved[0].target is not None
    assert resolved[0].target.candidates[0].value == "#save"
    assert resolved[0].object_id == "obj-save"
    assert resolved[1].target is None


def test_updating_object_repairs_multiple_flows(session: Session) -> None:
    session.add(
        UiObject(
            id="obj-save",
            tenant_id="default",
            project_id="default",
            site_id="site-1",
            key="style.save",
            name="保存按钮",
            target=_target("#old-save"),
        )
    )
    steps = [
        {
            "id": "click_save",
            "action": "click",
            "object_id": "obj-save",
            "label": "点保存",
        }
    ]
    for flow_id, name in (("flow-a", "流程 A"), ("flow-b", "流程 B")):
        session.add(
            Flow(
                id=flow_id,
                tenant_id="default",
                project_id="default",
                site_id="site-1",
                name=name,
                version=1,
                status="draft",
                steps=steps,
                auth_type="none",
            )
        )
    session.commit()
    site = session.get(Site, "site-1")
    assert site is not None

    before_a = bind_flow_steps(session, session.get(Flow, "flow-a"), site)
    before_b = bind_flow_steps(session, session.get(Flow, "flow-b"), site)
    assert before_a[0].target.candidates[0].value == "#old-save"
    assert before_b[0].target.candidates[0].value == "#old-save"

    obj = session.get(UiObject, "obj-save")
    assert obj is not None
    obj.target = _target("#new-save")
    session.commit()

    after_a = bind_flow_steps(session, session.get(Flow, "flow-a"), site)
    after_b = bind_flow_steps(session, session.get(Flow, "flow-b"), site)
    assert after_a[0].target.candidates[0].value == "#new-save"
    assert after_b[0].target.candidates[0].value == "#new-save"


def test_missing_object_ref_fails_bind(session: Session) -> None:
    session.add(
        Flow(
            id="flow-x",
            tenant_id="default",
            project_id="default",
            site_id="site-1",
            name="缺对象",
            version=1,
            status="draft",
            steps=[
                {
                    "id": "click_missing",
                    "action": "click",
                    "object_id": "no-such",
                    "label": "幽灵",
                }
            ],
            auth_type="none",
        )
    )
    session.commit()
    site = session.get(Site, "site-1")
    assert site is not None
    with pytest.raises(ReplayBindError) as caught:
        bind_flow_steps(session, session.get(Flow, "flow-x"), site)
    assert "不存在的对象" in str(caught.value)


def test_resolve_unknown_object_raises() -> None:
    step = Step(id="s1", action="click", object_id="ghost")
    with pytest.raises(ObjectNotFound):
        resolve_steps_objects([step], {})
