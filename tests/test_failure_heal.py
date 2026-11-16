"""回放失败 → AI/fixture 提案补丁 → 写回流程/对象库（无真实 LLM）。"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from autotest_control.ai.failure_healer import (
    AIFailureHealer,
    FailureHealPatch,
    apply_failure_patches,
    build_failure_context,
    classify_error_class,
    fixture_propose,
    parse_failure_heal_contract,
)
from autotest_control.api_auth import ApiTokenMiddleware
from autotest_control.api.router import router
from autotest_control.deps import Scope
from autotest_control.domain.failure_heal import apply_failure_heal_task, propose_for_run
from autotest_control.models import Base, FailureHealTask, Flow, Run, Site, UiObject
from autotest_protocol import Candidate, DataStrategy, Step, Target


SCOPE = Scope(tenant_id="default", project_id="default")


def test_classify_keeps_locator_and_data_strategy_apart() -> None:
    assert classify_error_class({"failure": "data_strategy", "failure_kind": "missing_env"}) == (
        "data_strategy"
    )
    assert classify_error_class({"failure_kind": "target_changed"}) == "locator"
    assert classify_error_class({"message": "偶发超时"}) == "uncertain"


def test_fixture_locator_proposes_object_rebind() -> None:
    context = build_failure_context(
        run_id="r1",
        flow_id="f1",
        step={
            "id": "s1",
            "action": "click",
            "object_id": "obj-1",
            "label": "保存",
            "target": {"candidates": [{"kind": "css", "value": "#old"}]},
        },
        step_result={
            "step_id": "s1",
            "status": "failed",
            "failure_kind": "target_changed",
            "message": "找不到目标",
            "tried": ["css=#new-save"],
        },
        object_def={
            "id": "obj-1",
            "key": "style.save",
            "name": "保存",
            "target": {"candidates": [{"kind": "css", "value": "#old"}]},
        },
        tried=["css=#new-save"],
    )
    contract = fixture_propose(context)
    assert contract.error_class == "locator"
    assert contract.requires_human_confirm is True
    assert len(contract.patches) == 1
    patch = contract.patches[0]
    assert patch.kind == "object_rebind"
    assert patch.object_id == "obj-1"
    assert patch.candidates[0]["value"] == "#new-save"


def test_fixture_data_strategy_literal_to_env() -> None:
    context = build_failure_context(
        run_id="r1",
        flow_id="f1",
        step={
            "id": "fill_order",
            "action": "fill",
            "value_strategy": {"kind": "literal", "value": "A-100"},
            "target": {"candidates": [{"kind": "label", "value": "单号"}]},
        },
        step_result={
            "step_id": "fill_order",
            "status": "failed",
            "failure": "data_strategy",
            "failure_kind": "not_found",
            "strategy": "lookup",
            "message": "lookup 未命中",
        },
        env_data_keys=["order_no", "username"],
    )
    contract = fixture_propose(context)
    assert contract.error_class == "data_strategy"
    assert contract.patches[0].kind == "data_strategy"
    assert contract.patches[0].strategy == {"kind": "env", "key": "order_no"}


def test_apply_patches_updates_flow_and_object() -> None:
    steps = [
        {
            "id": "s1",
            "action": "click",
            "object_id": "obj-1",
            "target": {"candidates": [{"kind": "css", "value": "#old"}]},
        },
        {
            "id": "s2",
            "action": "fill",
            "value": "A-100",
            "target": {"candidates": [{"kind": "label", "value": "单号"}]},
        },
    ]
    objects = {
        "obj-1": {
            "id": "obj-1",
            "key": "save",
            "target": {"candidates": [{"kind": "css", "value": "#old"}]},
        }
    }
    patches = [
        FailureHealPatch(
            kind="object_rebind",
            step_id="s1",
            object_id="obj-1",
            candidates=[{"kind": "css", "value": "#new"}],
            rationale="对象重绑",
            confidence=0.8,
        ),
        FailureHealPatch(
            kind="data_strategy",
            step_id="s2",
            field="value_strategy",
            strategy={"kind": "env", "key": "order_no"},
            rationale="改 env",
            confidence=0.8,
        ),
    ]
    new_steps, object_updates, audit = apply_failure_patches(steps, patches, objects=objects)
    assert object_updates["obj-1"]["target"]["candidates"][0]["value"] == "#new"
    assert new_steps[1]["value_strategy"]["kind"] == "env"
    assert "value" not in new_steps[1]
    assert [a["status"] for a in audit] == ["applied", "applied"]
    assert audit[0]["proposed"]["kind"] == "object_rebind"
    assert audit[0]["applied"]["candidates"][0]["value"] == "#new"


def test_parse_contract_and_mock_ai_client() -> None:
    legal = {
        "error_class": "locator",
        "requires_human_confirm": True,
        "patches": [
            {
                "kind": "target_candidates",
                "step_id": "s1",
                "candidates": [{"kind": "text", "value": "保存"}],
                "rationale": "改文本候选",
                "confidence": 0.9,
            }
        ],
        "notes": ["mock"],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": json.dumps(legal, ensure_ascii=False)}],
                "usage": {"input_tokens": 3, "output_tokens": 5},
            },
        )

    client = AnthropicLike(
        transport=httpx.MockTransport(handler),
    )
    healer = AIFailureHealer(client=client)  # type: ignore[arg-type]
    result = healer.propose(
        {"error_class": "locator", "step_id": "s1", "step": {"id": "s1"}},
        fixture_mode=False,
    )
    assert result.source == "ai"
    assert result.contract.patches[0].candidates[0]["value"] == "保存"
    parsed = parse_failure_heal_contract("```json\n" + json.dumps(legal) + "\n```")
    assert parsed.patches[0].kind == "target_candidates"


class AnthropicLike:
    """最小可注入 AnthropicClient 表面。"""

    def __init__(self, transport: httpx.BaseTransport) -> None:
        from autotest_control.ai.client import AnthropicClient

        self._inner = AnthropicClient(
            config=SimpleNamespace(
                anthropic_base_url="https://example.test",
                anthropic_auth_token="tok",
                anthropic_model="m",
                anthropic_timeout_seconds=3,
                anthropic_max_tokens=100,
                anthropic_vision_enabled=False,
                anthropic_max_retries=0,
                anthropic_api_format="anthropic",
            ),
            transport=transport,
        )

    def create_message(self, *args, **kwargs):
        return self._inner.create_message(*args, **kwargs)

    def _required_config(self):
        return self._inner._required_config()


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
    db.add(
        UiObject(
            id="obj-1",
            tenant_id="default",
            project_id="default",
            site_id="site-1",
            key="style.save",
            name="保存",
            target=Target(candidates=[Candidate(kind="css", value="#old")]).model_dump(mode="json"),
        )
    )
    steps = [
        Step(id="s1", action="click", object_id="obj-1", label="保存").model_dump(mode="json"),
        Step(
            id="s2",
            action="fill",
            target=Target(candidates=[Candidate(kind="label", value="单号")]),
            value_strategy=DataStrategy(kind="literal", value="A-100"),
            label="填单号",
        ).model_dump(mode="json"),
    ]
    db.add(
        Flow(
            id="flow-1",
            tenant_id="default",
            project_id="default",
            site_id="site-1",
            name="下单",
            status="draft",
            steps=steps,
        )
    )
    db.add(
        Run(
            id="run-1",
            tenant_id="default",
            project_id="default",
            site_id="site-1",
            flow_id="flow-1",
            kind="replay",
            status="failed",
            job={
                "environment": {"data": {"order_no": "B-200"}},
                "variables": {},
            },
            summary={
                "steps": [
                    {
                        "step_id": "s1",
                        "action": "click",
                        "status": "failed",
                        "failure_kind": "target_changed",
                        "message": "找不到目标",
                        "tried": ["css=#new-save"],
                        "screenshot": "/artifacts/r1/01_s1.png",
                    }
                ],
                "failed": 1,
            },
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


def test_propose_and_apply_persists_audit(session: Session) -> None:
    run = session.get(Run, "run-1")
    assert run is not None
    task = propose_for_run(session, run, fixture_mode=True, dry_run=True)
    session.commit()
    assert task.source == "fixture"
    assert task.dry_run is True
    assert task.requires_human_confirm is True
    assert task.error_class == "locator"
    assert task.patches[0]["kind"] == "object_rebind"

    apply_failure_heal_task(session, task, scope=SCOPE)
    session.commit()
    session.refresh(task)
    assert task.status == "applied"
    assert task.dry_run is False
    assert task.applied_log[0]["status"] == "applied"
    assert task.applied_log[0]["proposed"]["kind"] == "object_rebind"
    obj = session.get(UiObject, "obj-1")
    assert obj is not None
    assert obj.target["candidates"][0]["value"] == "#new-save"
    flow = session.get(Flow, "flow-1")
    assert flow is not None
    assert int(flow.version) >= 2


def test_api_propose_fixture_dry_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATP_VAR_DIR", str(tmp_path))
    monkeypatch.setenv("ATP_DATABASE_URL", f"sqlite:///{tmp_path / 'control.db'}")
    monkeypatch.setenv("ATP_API_TOKEN", "test-api-token")
    monkeypatch.setenv("ATP_WORKER_REGISTER_CODE", "test-register-code")
    monkeypatch.setenv("ATP_SECRET_KEY_PATH", str(tmp_path / "secret.key"))

    from autotest_control import db
    from autotest_control.settings import settings

    settings.__init__()
    db.configure_engine()
    db.init_db()

    with db.SessionLocal() as session:
        session.add(
            Site(
                id="site-1",
                tenant_id="default",
                project_id="default",
                name="站",
                base_url="http://example.test",
                env="test",
                adapter="generic",
                probe_error_url_patterns=[],
            )
        )
        session.add(
            Flow(
                id="flow-1",
                tenant_id="default",
                project_id="default",
                site_id="site-1",
                name="流",
                status="draft",
                steps=[
                    {
                        "id": "s2",
                        "action": "fill",
                        "label": "单号",
                        "target": {"candidates": [{"kind": "label", "value": "单号"}]},
                        "value_strategy": {"kind": "literal", "value": "A-100"},
                    }
                ],
            )
        )
        session.add(
            Run(
                id="run-ds",
                tenant_id="default",
                project_id="default",
                site_id="site-1",
                flow_id="flow-1",
                kind="replay",
                status="failed",
                job={"environment": {"data": {"order_no": "X"}}, "variables": {}},
                summary={
                    "steps": [
                        {
                            "step_id": "s2",
                            "status": "failed",
                            "failure": "data_strategy",
                            "failure_kind": "not_found",
                            "message": "lookup 未命中",
                        }
                    ]
                },
            )
        )
        session.commit()

    app = FastAPI()
    app.add_middleware(ApiTokenMiddleware)
    app.include_router(router)
    client = TestClient(app)
    response = client.post(
        "/api/v1/runs/run-ds/failure-heal/propose",
        headers={"X-API-Token": "test-api-token"},
        json={"fixture_mode": True, "dry_run": True},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source"] == "fixture"
    assert body["dry_run"] is True
    assert body["error_class"] == "data_strategy"
    assert body["patches"][0]["kind"] == "data_strategy"
    assert body["requires_human_confirm"] is True

    # dry-run 未写回
    with db.SessionLocal() as session:
        flow = session.get(Flow, "flow-1")
        assert flow is not None
        assert flow.steps[0]["value_strategy"]["kind"] == "literal"

    apply = client.post(
        f"/api/v1/failure-heal-tasks/{body['id']}/apply",
        headers={"X-API-Token": "test-api-token"},
    )
    assert apply.status_code == 200, apply.text
    applied = apply.json()
    assert applied["status"] == "applied"
    assert applied["applied_log"][0]["proposed"]["strategy"]["kind"] == "env"
    assert applied["applied_log"][0]["applied"]["strategy"]["kind"] == "env"

    with db.SessionLocal() as session:
        flow = session.get(Flow, "flow-1")
        assert flow is not None
        assert flow.steps[0]["value_strategy"] == {"kind": "env", "key": "order_no"}
        task = session.get(FailureHealTask, body["id"])
        assert task is not None
        assert task.status == "applied"
