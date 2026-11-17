"""Phase D：控制面写接口鉴权与 Worker 注册码 / 凭证收紧。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def auth_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ATP_VAR_DIR", str(tmp_path))
    monkeypatch.setenv("ATP_DATABASE_URL", f"sqlite:///{tmp_path / 'control.db'}")
    monkeypatch.setenv("ATP_API_TOKEN", "test-api-token")
    monkeypatch.setenv("ATP_WORKER_REGISTER_CODE", "test-register-code")
    monkeypatch.setenv("ATP_SECRET_KEY_PATH", str(tmp_path / "secret.key"))

    from autotest_control import db
    from autotest_control.settings import settings

    settings.__init__()
    db.configure_engine()
    # 避免 lifespan 拉起编译后台线程干扰单测
    from autotest_control.api_auth import ApiTokenMiddleware
    from autotest_control.api.router import router
    from fastapi import FastAPI

    db.init_db()
    app = FastAPI(title="auth-test")
    app.add_middleware(ApiTokenMiddleware)
    app.include_router(router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    with TestClient(app) as client:
        yield client, settings


def _auth_headers(token: str = "test-api-token") -> dict[str, str]:
    return {"X-API-Token": token}


def test_write_without_token_denied(auth_env) -> None:
    client, _ = auth_env
    response = client.post(
        "/api/v1/sites",
        json={
            "name": "x",
            "base_url": "https://example.com",
            "env": "test",
            "adapter": "generic",
        },
    )
    assert response.status_code == 401
    assert "API Token" in response.json()["detail"]


def test_write_with_wrong_token_denied(auth_env) -> None:
    client, _ = auth_env
    response = client.post(
        "/api/v1/sites",
        headers=_auth_headers("wrong"),
        json={
            "name": "x",
            "base_url": "https://example.com",
            "env": "test",
            "adapter": "generic",
        },
    )
    assert response.status_code == 401


def test_write_with_token_ok(auth_env) -> None:
    client, _ = auth_env
    response = client.post(
        "/api/v1/sites",
        headers=_auth_headers(),
        json={
            "name": "示例",
            "base_url": "https://example.com",
            "env": "test",
            "adapter": "generic",
            "probe_error_url_patterns": [],
        },
    )
    assert response.status_code == 200
    assert response.json()["name"] == "示例"


def test_healthz_and_get_without_token(auth_env) -> None:
    client, _ = auth_env
    assert client.get("/healthz").status_code == 200
    assert client.get("/api/v1/sites").status_code == 200


def test_bootstrap_loopback_returns_token(auth_env) -> None:
    client, settings = auth_env
    response = client.get("/api/v1/auth/bootstrap")
    assert response.status_code == 200
    body = response.json()
    assert body["required"] is True
    assert body["api_token"] == settings.api_token


def test_recording_stop_requires_api_token(auth_env) -> None:
    """录制旁路面板也必须带 Token；匿名 stop 会 401，旧 dock 会卡在「停止中…」。"""
    client, _ = auth_env
    from autotest_control.db import session_scope
    from autotest_control.deps import new_id, now
    from autotest_control.models import Run, Site

    with session_scope() as session:
        site = Site(
            id=new_id(),
            tenant_id="default",
            project_id="default",
            name="s",
            base_url="https://example.com",
            env="test",
            adapter="generic",
        )
        session.add(site)
        run = Run(
            id=new_id(),
            tenant_id="default",
            project_id="default",
            site_id=site.id,
            kind="record",
            status="running",
            job={"record_intent": "demo"},
            created_at=now(),
        )
        session.add(run)
        session.commit()
        run_id = run.id

    denied = client.post(f"/api/v1/recordings/{run_id}/stop")
    assert denied.status_code == 401

    ok = client.post(f"/api/v1/recordings/{run_id}/stop", headers=_auth_headers())
    assert ok.status_code == 200
    assert ok.json()["ok"] is True


def test_worker_register_without_code_denied(auth_env) -> None:
    client, _ = auth_env
    response = client.post(
        "/api/v1/workers/register",
        json={"name": "w1", "labels": [], "platform": "test"},
    )
    assert response.status_code == 401


def test_worker_register_with_code_ok(auth_env) -> None:
    client, _ = auth_env
    response = client.post(
        "/api/v1/workers/register",
        json={
            "name": "w1",
            "labels": ["os:linux"],
            "platform": "test",
            "register_code": "test-register-code",
        },
    )
    assert response.status_code == 200
    assert response.json()["token"]


def test_credential_material_only_for_current_job(auth_env) -> None:
    client, _ = auth_env
    from autotest_control import crypto
    from autotest_control.db import session_scope
    from autotest_control.deps import new_id, now
    from autotest_control.models import Credential, Run, Site, Worker

    with session_scope() as session:
        site = Site(
            id=new_id(),
            tenant_id="default",
            project_id="default",
            name="s",
            base_url="https://example.com",
            env="test",
            adapter="generic",
        )
        session.add(site)
        cred_job = Credential(
            id=new_id(),
            tenant_id="default",
            project_id="default",
            site_id=site.id,
            name="job-cred",
            type="form",
            payload_encrypted=crypto.encrypt(json.dumps({"username": "a", "password": "b"})),
        )
        cred_other = Credential(
            id=new_id(),
            tenant_id="default",
            project_id="default",
            site_id=site.id,
            name="other-cred",
            type="form",
            payload_encrypted=crypto.encrypt(json.dumps({"username": "x", "password": "y"})),
        )
        session.add_all([cred_job, cred_other])
        worker = Worker(
            id=new_id(),
            project_id="default",
            name="w",
            token="worker-token",
            labels=[],
            platform="test",
            last_heartbeat_at=now(),
            registered_at=now(),
        )
        session.add(worker)
        run = Run(
            id=new_id(),
            tenant_id="default",
            project_id="default",
            site_id=site.id,
            flow_id=new_id(),
            status="leased",
            worker_id=worker.id,
            job={"auth": {"type": "form", "ref": cred_job.id}, "run_id": "r"},
        )
        session.add(run)
        session.commit()
        worker_id = worker.id
        job_cred_id = cred_job.id
        other_cred_id = cred_other.id

    denied = client.get(
        f"/api/v1/credentials/{other_cred_id}/material",
        params={"worker_id": worker_id, "token": "worker-token"},
    )
    assert denied.status_code == 403

    allowed = client.get(
        f"/api/v1/credentials/{job_cred_id}/material",
        params={"worker_id": worker_id, "token": "worker-token"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["payload"]["username"] == "a"
