"""阶段 B：Environment 持久化、Job 合并与 API 契约（无内网）。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from autotest_control.api.environments import router as env_router
from autotest_control.api.sites import router as sites_router
from autotest_control.db import get_session
from autotest_control.deps import Scope, get_scope
from autotest_control.domain.environments import (
    merge_run_variables,
    seed_environment_for_site,
    site_ref_for_run,
)
from autotest_control.domain.jobs import build_job
from autotest_control.models import Base, Environment, Flow, Site
from autotest_protocol import DataStrategy, RunOptions, Step


@pytest.fixture()
def session(tmp_path: Path) -> Session:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'phase_b.db'}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = factory()
    try:
        yield db
    finally:
        db.close()


def _site(session: Session, *, name: str = "福瑞丝", base: str = "https://a.example") -> Site:
    site = Site(
        id="site-1",
        tenant_id="default",
        project_id="default",
        name=name,
        base_url=base,
        env="test",
        adapter="generic",
        probe_error_url_patterns=[],
    )
    session.add(site)
    seed_environment_for_site(session, site)
    session.commit()
    return site


def test_seed_default_environment(session: Session) -> None:
    site = _site(session)
    envs = session.query(Environment).filter_by(site_id=site.id).all()
    assert len(envs) == 1
    assert envs[0].base_url == "https://a.example"
    assert envs[0].name == "test"


def test_job_uses_environment_base_url_and_data(session: Session) -> None:
    site = _site(session)
    env_b = Environment(
        id="env-b",
        tenant_id="default",
        project_id="default",
        site_id=site.id,
        name="预发",
        base_url="https://b.example",
        credential_id=None,
        labels=["staging"],
        data={"username": "user-b", "order_no": "B-9"},
    )
    session.add(env_b)
    flow = Flow(
        id="flow-1",
        tenant_id="default",
        project_id="default",
        site_id=site.id,
        name="填单号",
        version=1,
        status="draft",
        steps=[
            Step(
                id="fill",
                action="fill",
                target={"candidates": [{"kind": "label", "value": "单号"}]},
                value_strategy=DataStrategy(kind="env", key="order_no"),
            ).model_dump(mode="json")
        ],
        auth_type="none",
    )
    session.add(flow)
    session.commit()

    job = build_job(
        session,
        "run-1",
        site,
        flow,
        RunOptions(headless=True),
        variables={"extra": "1"},
        environment=env_b,
    )
    assert job.site.base_url == "https://b.example"
    assert job.site.env == "预发"
    assert job.environment is not None
    assert job.environment.id == "env-b"
    assert job.variables["order_no"] == "B-9"
    assert job.variables["username"] == "user-b"
    assert job.variables["extra"] == "1"
    # 同一流程步骤仍是策略引用，不是死值
    assert job.flow is not None
    assert job.flow.steps[0].value_strategy is not None
    assert job.flow.steps[0].value_strategy.kind == "env"


def test_same_flow_env_a_vs_env_b_variables(session: Session) -> None:
    site = _site(session, base="https://system.example")
    env_a = Environment(
        id="env-a",
        tenant_id="default",
        project_id="default",
        site_id=site.id,
        name="测试",
        base_url="https://a.example",
        data={"order_no": "A-1"},
        labels=["a"],
    )
    env_b = Environment(
        id="env-b2",
        tenant_id="default",
        project_id="default",
        site_id=site.id,
        name="预发",
        base_url="https://b.example",
        data={"order_no": "B-2"},
        labels=["b"],
    )
    session.add_all([env_a, env_b])
    session.commit()

    ref_a = site_ref_for_run(site, env_a)
    ref_b = site_ref_for_run(site, env_b)
    assert ref_a.base_url == "https://a.example"
    assert ref_b.base_url == "https://b.example"
    assert merge_run_variables(env_a, {})["order_no"] == "A-1"
    assert merge_run_variables(env_b, {"order_no": "override"})["order_no"] == "override"


@pytest.fixture()
def api_client(tmp_path: Path) -> TestClient:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'api.db'}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    app = FastAPI()
    app.include_router(sites_router, prefix="/api/v1")
    app.include_router(env_router, prefix="/api/v1")

    def _session():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_scope] = lambda: Scope("default", "default")
    return TestClient(app)


def test_environments_api_crud(api_client: TestClient) -> None:
    created = api_client.post(
        "/api/v1/sites",
        json={"name": "系统", "base_url": "https://sys.example", "env": "default"},
    )
    assert created.status_code == 200, created.text
    site_id = created.json()["id"]

    listed = api_client.get(f"/api/v1/sites/{site_id}/environments")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["base_url"] == "https://sys.example"

    env_b = api_client.post(
        f"/api/v1/sites/{site_id}/environments",
        json={
            "name": "预发",
            "base_url": "https://b.example",
            "labels": ["staging"],
            "data": {"order_no": "B-100", "username": "u-b"},
        },
    )
    assert env_b.status_code == 200, env_b.text
    body = env_b.json()
    assert body["name"] == "预发"
    assert body["data"]["order_no"] == "B-100"

    patched = api_client.patch(
        f"/api/v1/sites/{site_id}/environments/{body['id']}",
        json={"data": {"order_no": "B-200"}},
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["order_no"] == "B-200"

    # 不能删光
    default_id = listed.json()[0]["id"]
    api_client.delete(f"/api/v1/sites/{site_id}/environments/{body['id']}")
    blocked = api_client.delete(f"/api/v1/sites/{site_id}/environments/{default_id}")
    assert blocked.status_code == 409
