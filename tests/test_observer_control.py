"""控制面页面认识：合并、保存、站点复用。"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from autotest_control.deps import Scope
from autotest_control.domain.observer import (
    apply_snapshot_to_run,
    attach_model_to_flow,
    load_site_widget_models,
    seed_run_observation,
)
from autotest_control.models import Base, Flow, Run, Site
from autotest_protocol import LayerRef, PageWidgetEntry, PageWidgetModel

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


def _snapshot_payload(**overrides: object) -> dict:
    base = {
        "trigger": "form_visible",
        "url": "http://example.test/style/new",
        "layer": {"kind": "modal", "name": "新增款式"},
        "fields": [
            {
                "label": "品牌",
                "widget_kind": "searchable_dropdown",
                "required": True,
                "sample_options": ["Gucci", "Prada"],
            },
            {
                "label": "155",
                "widget_kind": "tab",
                "sample_options": [],
            },
        ],
    }
    base.update(overrides)
    return base


def test_apply_snapshot_merges_without_transient_option_identity(session: Session) -> None:
    run = Run(
        id="run-1",
        tenant_id="default",
        project_id="default",
        site_id="site-1",
        kind="record",
        status="running",
        job={},
    )
    session.add(run)
    session.commit()

    updated = apply_snapshot_to_run(run, _snapshot_payload())
    assert updated is not None
    names = {entry.display_name for entry in updated.entries}
    assert "品牌" in names
    assert "155" not in names
    brand = next(entry for entry in updated.entries if entry.display_name == "品牌")
    assert brand.value_strategy == "choose_any"


def test_save_flow_carries_page_widget_model(session: Session) -> None:
    run = Run(
        id="run-2",
        tenant_id="default",
        project_id="default",
        site_id="site-1",
        kind="record",
        status="passed",
        job={},
        observation_model=PageWidgetModel(
            site_id="site-1",
            recording_run_id="run-2",
            entries=[
                PageWidgetEntry(
                    id="code",
                    layer=LayerRef(kind="modal", name="新增款式"),
                    display_name="款式编码",
                    widget_kind="text",
                    operation="fill",
                    value_strategy="parameterized",
                )
            ],
        ).model_dump(mode="json"),
    )
    flow = Flow(
        id="flow-1",
        tenant_id="default",
        project_id="default",
        site_id="site-1",
        name="新建款式",
        steps=[{"id": "s1", "action": "click", "label": "保存"}],
    )
    session.add(run)
    session.add(flow)
    session.commit()

    attach_model_to_flow(flow, run)
    session.commit()

    saved = session.get(Flow, "flow-1")
    assert saved is not None
    assert saved.page_widget_model is not None
    entries = saved.page_widget_model.get("entries") or []
    assert any(item.get("display_name") == "款式编码" for item in entries)
    assert saved.page_widget_model.get("flow_id") == "flow-1"
    assert all(item.get("display_name") != "155" for item in entries)


def test_new_recording_seeds_site_existing_models(session: Session) -> None:
    session.add(
        Flow(
            id="flow-old",
            tenant_id="default",
            project_id="default",
            site_id="site-1",
            name="已有流程",
            page_widget_model=PageWidgetModel(
                site_id="site-1",
                flow_id="flow-old",
                entries=[
                    PageWidgetEntry(
                        id="brand",
                        layer=LayerRef(kind="modal", name="新增款式"),
                        display_name="品牌",
                        widget_kind="searchable_dropdown",
                        operation="choose",
                        value_strategy="choose_any",
                    )
                ],
            ).model_dump(mode="json"),
        )
    )
    run = Run(
        id="run-3",
        tenant_id="default",
        project_id="default",
        site_id="site-1",
        kind="record",
        status="queued",
        job={},
    )
    session.add(run)
    session.commit()

    seed_run_observation(session, SCOPE, run)
    session.commit()

    seeded = session.get(Run, "run-3")
    assert seeded is not None
    entries = (seeded.observation_model or {}).get("entries") or []
    assert any(item.get("display_name") == "品牌" for item in entries)

    site_model = load_site_widget_models(session, SCOPE, "site-1")
    assert any(entry.display_name == "品牌" for entry in site_model.entries)
