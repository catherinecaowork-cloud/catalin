from __future__ import annotations

import asyncio
import json
import re
import secrets
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse, urlunparse

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from autotest_control import crypto
from autotest_control.ai import (
    AIConfigurationError,
    AIContractError,
    AIRequestError,
    AnthropicClient,
    validate_template_value,
)
from autotest_control.db import get_session, session_scope
from autotest_control.heal import apply_locator_patches, build_locator_patches, supervisor_instruction
from autotest_control.hub import hub
from autotest_control.models import (
    Batch,
    Credential,
    Flow,
    HealTask,
    RecordingCompilation,
    Run,
    RunEvent,
    Site,
    Suite,
    Worker,
)
from autotest_control.schemas import (
    AIConfigIn,
    AIConfigOut,
    BatchCreate,
    BatchOut,
    CompilationOut,
    CompilationRetry,
    CompleteIn,
    CredentialCreate,
    CredentialOut,
    EventsIn,
    FlowCreate,
    FlowImportIn,
    FlowImportOut,
    FlowOut,
    FlowSetupUpdate,
    FlowStatusUpdate,
    HealTaskOut,
    HeartbeatIn,
    InspectIn,
    OnboardCommitIn,
    RecordingCreate,
    RecordingSave,
    RunCreate,
    RunOut,
    RunPurgeIn,
    SiteCreate,
    SiteFormCredentialIn,
    SiteOut,
    SuiteCreate,
    SuiteOut,
    SuiteUpdate,
    WorkerOut,
    WorkerRegister,
)
from autotest_control.local_worker import (
    local_stop_requested,
    start_local_worker,
    stop_local_worker,
)
from autotest_control.settings import infer_api_format, settings
from autotest_control.storage import prune_retained_runs
from autotest_control.chain import ChainError, compose_chain, expand_members, expand_setup_chain
from autotest_control.flow_import import FlowImportError, import_flows_to_site
from autotest_control.replay_bind import (
    ReplayBindError,
    bind_flow_for_site,
    bind_flow_steps,
    credential_for_site,
)
from autotest_control.suites import CONFIRMED_STATUSES, SuiteError, decide_after_run, resolve_members
from autotest_protocol import (
    CANDIDATE_STABILITY,
    AuthRef,
    Flow as FlowDSL,
    Job,
    RunOptions,
    SiteRef,
    Step,
)
from autotest_protocol.job import ProbeConfig

router = APIRouter(prefix="/api/v1")

# 同一进程内防止两个 Worker 领到同一任务。
# 多副本部署时换成 Postgres 的 SELECT ... FOR UPDATE SKIP LOCKED。
_lease_lock = asyncio.Lock()

_SENSITIVE_HEADER = re.compile(
    r"^(authorization|cookie|set-cookie|x-api-key|password|passwd|token|secret|api[_-]?key)$",
    re.I,
)
_MAX_COMPILE_ATTEMPTS = 3


class Scope:
    """租户与项目边界。

    P0 单租户，但字段现在就带上：隔离规则后补的话早期数据要迁移。
    查询一律经过 scope 过滤，不依赖调用方自觉传参。
    """

    def __init__(self, tenant_id: str, project_id: str) -> None:
        self.tenant_id = tenant_id
        self.project_id = project_id


def get_scope(
    x_tenant_id: str = Header(default="default"),
    x_project_id: str = Header(default="default"),
) -> Scope:
    return Scope(x_tenant_id, x_project_id)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


def _auth_worker(session: Session, worker_id: str, token: str) -> Worker:
    worker = session.get(Worker, worker_id)
    if worker is None or not secrets.compare_digest(worker.token, token):
        raise HTTPException(status_code=401, detail="worker 认证失败")
    return worker


def _redact(value: Any) -> Any:
    """事件与产物脱敏：凭证值不进日志、不进报告。"""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and _SENSITIVE_HEADER.match(key):
                out[key] = "***"
            else:
                out[key] = _redact(item)
        return out
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _heal_out(task: HealTask) -> HealTaskOut:
    return HealTaskOut(
        id=task.id,
        flow_id=task.flow_id,
        run_id=task.run_id,
        status=task.status,
        instruction=task.instruction,
        patches=task.patches or [],
        applied_log=task.applied_log or [],
    )


def _pending_heal_for_run(session: Session, run_id: str) -> HealTask | None:
    return session.scalar(
        select(HealTask).where(HealTask.run_id == run_id).order_by(HealTask.created_at.desc())
    )


def _ai_config_out() -> AIConfigOut:
    return AIConfigOut(
        configured=settings.ai_configured(),
        base_url=settings.anthropic_base_url,
        model=settings.anthropic_model,
        vision_enabled=settings.anthropic_vision_enabled,
        has_token=bool(settings.anthropic_auth_token),
        env_overrides=settings.ai_env_overrides(),
        api_format=infer_api_format(
            settings.anthropic_model, getattr(settings, "anthropic_api_format", "")
        ),
        token_hint=settings.token_hint(),
    )


def _collect_heal_task(session: Session, run: Run, updates: Any) -> HealTask | None:
    """监督者：把本轮定位漂移整理成一个脚本修补任务，不自动写回。"""
    if not run.flow_id or not isinstance(updates, list) or not updates:
        return None
    flow = session.get(Flow, run.flow_id)
    if flow is None:
        return None
    patches = build_locator_patches(flow.steps or [], updates)
    if not patches:
        return None
    existing = session.scalar(select(HealTask).where(HealTask.run_id == run.id))
    if existing is not None:
        return existing
    task = HealTask(
        id=_new_id(),
        flow_id=flow.id,
        run_id=run.id,
        status="pending",
        instruction=supervisor_instruction(patches),
        patches=patches,
        applied_log=[],
    )
    session.add(task)
    return task


# ---------------------------------------------------------------- 站点与凭证


@router.post("/sites", response_model=SiteOut)
def create_site(payload: SiteCreate, scope: Scope = Depends(get_scope), session: Session = Depends(get_session)) -> SiteOut:
    site = Site(
        id=_new_id(),
        tenant_id=scope.tenant_id,
        project_id=scope.project_id,
        name=payload.name,
        base_url=payload.base_url.rstrip("/"),
        env=payload.env,
        adapter=payload.adapter,
        probe_error_url_patterns=payload.probe_error_url_patterns,
    )
    session.add(site)
    session.commit()
    return SiteOut(
        id=site.id,
        name=site.name,
        base_url=site.base_url,
        env=site.env,
        adapter=site.adapter,
        probe_error_url_patterns=site.probe_error_url_patterns,
    )


@router.get("/sites", response_model=list[SiteOut])
def list_sites(scope: Scope = Depends(get_scope), session: Session = Depends(get_session)) -> list[SiteOut]:
    rows = session.scalars(
        select(Site).where(Site.tenant_id == scope.tenant_id, Site.project_id == scope.project_id)
    ).all()
    return [
        SiteOut(
            id=row.id,
            name=row.name,
            base_url=row.base_url,
            env=row.env,
            adapter=row.adapter,
            probe_error_url_patterns=row.probe_error_url_patterns,
        )
        for row in rows
    ]


@router.get("/ai/config", response_model=AIConfigOut)
def get_ai_config() -> AIConfigOut:
    return _ai_config_out()


@router.put("/ai/config", response_model=AIConfigOut)
def put_ai_config(payload: AIConfigIn) -> AIConfigOut:
    base_url = settings.normalize_base_url(payload.base_url)
    model = (payload.model or "").strip()
    if not base_url or not model:
        raise HTTPException(status_code=400, detail="请填写网关地址和模型名")
    token = (payload.auth_token or "").strip() or None
    if not token and not settings.anthropic_auth_token:
        raise HTTPException(status_code=400, detail="请填写 Token")
    settings.save_ai_config(
        base_url=base_url,
        auth_token=token,
        model=model,
        vision_enabled=payload.vision_enabled,
    )
    if not settings.ai_configured():
        raise HTTPException(status_code=400, detail="保存后仍缺少配置，请检查环境变量是否覆盖了空值")
    return _ai_config_out()


@router.post("/ai/config/test")
def test_ai_config() -> dict[str, Any]:
    settings.reload_ai(prefer_file=True)
    if not settings.ai_configured():
        raise HTTPException(status_code=400, detail="请先在顶栏「AI」保存网关地址、Token 和模型")
    try:
        result = AnthropicClient().create_message("Reply with the single word ok.")
    except AIConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AIRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "ok": True,
        "model": settings.anthropic_model,
        "base_url": settings.anthropic_base_url,
        "token_hint": settings.token_hint(),
        "api_format": settings.anthropic_api_format,
        "attempts": result.attempts,
        "preview": (result.text or "")[:120],
    }


@router.delete("/sites/{site_id}")
def delete_site(site_id: str, scope: Scope = Depends(get_scope), session: Session = Depends(get_session)) -> dict[str, Any]:
    site = _get_site(session, scope, site_id)
    creds = session.scalars(select(Credential).where(Credential.site_id == site.id)).all()
    flows = session.scalars(select(Flow).where(Flow.site_id == site.id)).all()
    for row in creds:
        session.delete(row)
    for row in flows:
        session.delete(row)
    session.delete(site)
    session.commit()
    return {"ok": True}


def _get_site(session: Session, scope: Scope, site_id: str) -> Site:
    site = session.get(Site, site_id)
    # 越权与不存在返回同样的错误，不泄露资源是否存在
    if site is None or site.tenant_id != scope.tenant_id or site.project_id != scope.project_id:
        raise HTTPException(status_code=404, detail="站点不存在")
    return site


@router.post("/sites/{site_id}/credentials", response_model=CredentialOut)
def create_credential(
    site_id: str,
    payload: CredentialCreate,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> CredentialOut:
    site = _get_site(session, scope, site_id)
    credential = Credential(
        id=_new_id(),
        tenant_id=scope.tenant_id,
        project_id=scope.project_id,
        site_id=site.id,
        name=payload.name,
        type=payload.type,
        payload_encrypted=crypto.encrypt(json.dumps(payload.payload, ensure_ascii=False)),
        updated_at=_now(),
    )
    session.add(credential)
    session.commit()
    return CredentialOut(
        id=credential.id, name=credential.name, type=credential.type, updated_at=credential.updated_at
    )


@router.get("/sites/{site_id}/credentials", response_model=list[CredentialOut])
def list_credentials(
    site_id: str, scope: Scope = Depends(get_scope), session: Session = Depends(get_session)
) -> list[CredentialOut]:
    _get_site(session, scope, site_id)
    rows = session.scalars(
        select(Credential).where(
            Credential.site_id == site_id,
            Credential.tenant_id == scope.tenant_id,
            Credential.project_id == scope.project_id,
        )
    ).all()
    return [CredentialOut(id=r.id, name=r.name, type=r.type, updated_at=r.updated_at) for r in rows]


_FORM_LOCATOR_KEYS = ("username_target", "password_target", "submit_target")


def _form_login_locators(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    if not all(key in data for key in _FORM_LOCATOR_KEYS):
        return None
    return {key: data[key] for key in _FORM_LOCATOR_KEYS}


def _locators_from_inspect(session: Session, scope: Scope, inspect_run_id: str | None) -> tuple[dict[str, Any] | None, str | None]:
    if not inspect_run_id:
        return None, None
    run = session.get(Run, inspect_run_id)
    if run is None or run.tenant_id != scope.tenant_id or run.project_id != scope.project_id:
        raise HTTPException(status_code=404, detail="踩点任务不存在")
    if run.status != "passed":
        return None, None
    summary = run.summary or {}
    detection = summary.get("detection") or {}
    locators = _form_login_locators(detection)
    login_path = summary.get("login_path")
    return locators, str(login_path) if login_path else None


def _copy_project_form_locators(session: Session, scope: Scope) -> tuple[dict[str, Any] | None, str | None]:
    rows = session.scalars(
        select(Credential).where(
            Credential.tenant_id == scope.tenant_id,
            Credential.project_id == scope.project_id,
            Credential.type == "form",
        )
    ).all()
    for cred in rows:
        try:
            data = json.loads(crypto.decrypt(cred.payload_encrypted))
        except Exception:
            continue
        locators = _form_login_locators(data)
        if locators:
            path = data.get("login_path")
            return locators, str(path) if path else None
    return None, None


@router.post("/sites/{site_id}/credentials/form", response_model=CredentialOut)
def create_form_credential(
    site_id: str,
    payload: SiteFormCredentialIn,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> CredentialOut:
    """给已经建好的环境补登录账号，不再另建一个站点。"""
    site = _get_site(session, scope, site_id)
    username = payload.username.strip()
    if not username or not payload.password:
        raise HTTPException(status_code=400, detail="账号和密码都要填")
    login_path = (payload.login_path or "/").strip() or "/"
    locators, inspected_path = _locators_from_inspect(session, scope, payload.inspect_run_id)
    copied_path = None
    if locators is None:
        locators, copied_path = _copy_project_form_locators(session, scope)
    if inspected_path:
        login_path = inspected_path
    elif (payload.login_path or "").strip() in {"", "/"} and copied_path:
        login_path = copied_path
    if locators is None:
        raise HTTPException(
            status_code=409,
            detail="没有识别到登录表单，同项目也没有可复用的登录定位。请确认登录页能打开，并且右上角执行器已点「开始」。",
        )
    material: dict[str, Any] = {
        "login_path": login_path,
        "username": username,
        "password": payload.password,
        **locators,
    }
    if payload.success_text:
        material["success_text"] = payload.success_text.strip()
    credential = Credential(
        id=_new_id(),
        tenant_id=scope.tenant_id,
        project_id=scope.project_id,
        site_id=site.id,
        name=f"{username}（表单登录）",
        type="form",
        payload_encrypted=crypto.encrypt(json.dumps(material, ensure_ascii=False)),
        updated_at=_now(),
    )
    session.add(credential)
    session.commit()
    return CredentialOut(
        id=credential.id, name=credential.name, type=credential.type, updated_at=credential.updated_at
    )


@router.delete("/sites/{site_id}/credentials/{credential_id}")
def delete_credential(
    site_id: str,
    credential_id: str,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    _get_site(session, scope, site_id)
    credential = session.get(Credential, credential_id)
    if (
        credential is None
        or credential.site_id != site_id
        or credential.tenant_id != scope.tenant_id
        or credential.project_id != scope.project_id
    ):
        raise HTTPException(status_code=404, detail="凭证不存在")
    for flow in session.scalars(select(Flow).where(Flow.credential_id == credential.id)).all():
        flow.credential_id = None
        flow.auth_type = "none"
    session.delete(credential)
    session.commit()
    return {"ok": True}


# ---------------------------------------------------------------- 流程


@router.post("/flows", response_model=FlowOut)
def create_flow(payload: FlowCreate, scope: Scope = Depends(get_scope), session: Session = Depends(get_session)) -> FlowOut:
    _get_site(session, scope, payload.site_id)
    flow = Flow(
        id=_new_id(),
        tenant_id=scope.tenant_id,
        project_id=scope.project_id,
        site_id=payload.site_id,
        name=payload.name,
        status="draft",
        steps=[step.model_dump(mode="json", exclude_none=True) for step in payload.steps],
        auth_type=payload.auth_type,
        credential_id=payload.credential_id,
    )
    session.add(flow)
    session.commit()
    return _flow_out(flow)


def _flow_out(flow: Flow) -> FlowOut:
    return FlowOut(
        id=flow.id,
        site_id=flow.site_id,
        name=flow.name,
        version=flow.version,
        status=flow.status,
        steps=flow.steps,
        auth_type=flow.auth_type,
        has_baseline=flow.baseline is not None,
        setup_flow_id=flow.setup_flow_id,
        imported_from=getattr(flow, "imported_from", None),
    )


@router.get("/flows", response_model=list[FlowOut])
def list_flows(
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
    site_id: str | None = Query(default=None),
) -> list[FlowOut]:
    stmt = select(Flow).where(Flow.tenant_id == scope.tenant_id, Flow.project_id == scope.project_id)
    if site_id:
        _get_site(session, scope, site_id)
        stmt = stmt.where(Flow.site_id == site_id)
    rows = session.scalars(stmt).all()
    return [_flow_out(row) for row in rows]


@router.post("/sites/{site_id}/flows/import", response_model=FlowImportOut)
def import_flows(
    site_id: str,
    payload: FlowImportIn,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> FlowImportOut:
    target = _get_site(session, scope, site_id)
    ids = list(dict.fromkeys(payload.flow_ids or []))
    if not ids:
        raise HTTPException(status_code=400, detail="请勾选要导入的脚本")
    selected = [_get_flow(session, scope, item) for item in ids]
    sample = selected[0]
    by_id = _project_flow_map(session, sample)
    try:
        imported, skipped = import_flows_to_site(session, target, selected, by_id)
    except FlowImportError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ChainError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    return FlowImportOut(imported=imported, skipped=skipped)


def _get_flow(session: Session, scope: Scope, flow_id: str) -> Flow:
    flow = session.get(Flow, flow_id)
    if flow is None or flow.tenant_id != scope.tenant_id or flow.project_id != scope.project_id:
        raise HTTPException(status_code=404, detail="流程不存在")
    return flow


@router.delete("/flows/{flow_id}")
def delete_flow(flow_id: str, scope: Scope = Depends(get_scope), session: Session = Depends(get_session)) -> dict[str, Any]:
    flow = _get_flow(session, scope, flow_id)
    if flow.status != "draft":
        raise HTTPException(status_code=409, detail="用例不能删除，请先退回草稿")
    for other in session.scalars(select(Flow).where(Flow.setup_flow_id == flow.id)).all():
        other.setup_flow_id = None
    session.delete(flow)
    session.commit()
    return {"ok": True}


_ALLOWED_TRANSITIONS = {
    ("draft", "reviewed"),
    ("reviewed", "golden"),
    ("golden", "active"),
    # 被测系统变更后回退重走确认
    ("reviewed", "draft"),
    ("golden", "draft"),
    ("active", "draft"),
}


@router.post("/flows/{flow_id}/status", response_model=FlowOut)
def update_flow_status(
    flow_id: str,
    payload: FlowStatusUpdate,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> FlowOut:
    """状态只能按序推进，且执行成功不会自动推进——确认是一次显式动作。"""
    flow = _get_flow(session, scope, flow_id)
    if (flow.status, payload.status) not in _ALLOWED_TRANSITIONS:
        raise HTTPException(
            status_code=409, detail=f"不允许的状态流转：{flow.status} → {payload.status}"
        )

    if payload.status == "golden":
        if not payload.baseline_run_id:
            raise HTTPException(status_code=400, detail="进入 golden 需要指定作为基线的运行")
        run = session.get(Run, payload.baseline_run_id)
        if run is None or run.flow_id != flow.id:
            raise HTTPException(status_code=400, detail="基线运行不属于该流程")
        if run.status != "passed":
            raise HTTPException(status_code=409, detail="只能采纳通过的运行作为基线")
        flow.baseline = {
            "run_id": run.id,
            "adopted_at": _now().isoformat(),
            "summary": run.summary or {},
        }

    if payload.status == "active" and flow.baseline is None:
        raise HTTPException(status_code=409, detail="未固化基线的流程不能进入回归")

    if payload.status == "draft":
        flow.baseline = None

    flow.status = payload.status
    session.commit()
    return _flow_out(flow)


@router.post("/flows/{flow_id}/setup", response_model=FlowOut)
def update_flow_setup(
    flow_id: str,
    payload: FlowSetupUpdate,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> FlowOut:
    flow = _get_flow(session, scope, flow_id)
    setup_id = payload.setup_flow_id or None
    previous = flow.setup_flow_id
    if setup_id:
        setup = _get_flow(session, scope, setup_id)
        if setup.id == flow.id:
            raise HTTPException(status_code=409, detail="不能把自己当成前置")
    flow.setup_flow_id = setup_id
    by_id = _project_flow_map(session, flow)
    by_id[flow.id] = flow
    try:
        expand_setup_chain(flow, by_id)
    except ChainError as exc:
        flow.setup_flow_id = previous
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    return _flow_out(flow)


# ---------------------------------------------------------------- 套件


def _suite_out(suite: Suite) -> SuiteOut:
    return SuiteOut(
        id=suite.id,
        site_id=suite.site_id,
        name=suite.name,
        flow_ids=list(suite.flow_ids or []),
        created_at=suite.created_at,
    )


def _load_member_flows(session: Session, scope: Scope, flow_ids: list[str]) -> dict[str, Flow]:
    if not flow_ids:
        return {}
    rows = session.scalars(
        select(Flow).where(
            Flow.tenant_id == scope.tenant_id,
            Flow.project_id == scope.project_id,
            Flow.id.in_(flow_ids),
        )
    ).all()
    return {row.id: row for row in rows}


def _validated_members(session: Session, scope: Scope, site_id: str, flow_ids: list[str]) -> list[Flow]:
    _get_site(session, scope, site_id)
    try:
        return list(resolve_members(site_id, flow_ids, _load_member_flows(session, scope, flow_ids)))
    except SuiteError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _get_suite(session: Session, scope: Scope, suite_id: str) -> Suite:
    suite = session.get(Suite, suite_id)
    if suite is None or suite.tenant_id != scope.tenant_id or suite.project_id != scope.project_id:
        raise HTTPException(status_code=404, detail="套件不存在")
    return suite


@router.post("/suites", response_model=SuiteOut)
def create_suite(
    payload: SuiteCreate, scope: Scope = Depends(get_scope), session: Session = Depends(get_session)
) -> SuiteOut:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="请填写套件名称")
    _validated_members(session, scope, payload.site_id, payload.flow_ids)
    suite = Suite(
        id=_new_id(),
        tenant_id=scope.tenant_id,
        project_id=scope.project_id,
        site_id=payload.site_id,
        name=name,
        flow_ids=list(payload.flow_ids),
    )
    session.add(suite)
    session.commit()
    return _suite_out(suite)


@router.get("/suites", response_model=list[SuiteOut])
def list_suites(
    site_id: str | None = Query(default=None),
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> list[SuiteOut]:
    stmt = select(Suite).where(Suite.tenant_id == scope.tenant_id, Suite.project_id == scope.project_id)
    if site_id:
        stmt = stmt.where(Suite.site_id == site_id)
    rows = session.scalars(stmt.order_by(Suite.created_at.desc())).all()
    return [_suite_out(row) for row in rows]


@router.put("/suites/{suite_id}", response_model=SuiteOut)
def update_suite(
    suite_id: str,
    payload: SuiteUpdate,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> SuiteOut:
    suite = _get_suite(session, scope, suite_id)
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="请填写套件名称")
        suite.name = name
    if payload.flow_ids is not None:
        _validated_members(session, scope, suite.site_id, payload.flow_ids)
        suite.flow_ids = list(payload.flow_ids)
        flag_modified(suite, "flow_ids")
    session.commit()
    return _suite_out(suite)


@router.delete("/suites/{suite_id}")
def delete_suite(
    suite_id: str, scope: Scope = Depends(get_scope), session: Session = Depends(get_session)
) -> dict[str, Any]:
    suite = _get_suite(session, scope, suite_id)
    session.delete(suite)
    session.commit()
    return {"ok": True}


# ---------------------------------------------------------------- 运行


def _site_ref(site: Site) -> SiteRef:
    return SiteRef(
        id=site.id,
        base_url=site.base_url,
        env=site.env,
        adapter=site.adapter,
        probe=ProbeConfig(error_url_patterns=site.probe_error_url_patterns),
    )


def _project_flow_map(session: Session, flow: Flow) -> dict[str, Flow]:
    rows = session.scalars(
        select(Flow).where(
            Flow.tenant_id == flow.tenant_id,
            Flow.project_id == flow.project_id,
        )
    ).all()
    return {row.id: row for row in rows}


def _build_job(
    session: Session,
    run_id: str,
    site: Site,
    flow: Flow,
    options: RunOptions,
    variables: dict[str, str] | None = None,
) -> Job:
    return Job(
        run_id=run_id,
        kind="replay",
        site=_site_ref(site),
        auth=credential_for_site(session, flow, site),
        flow=FlowDSL(name=flow.name, version=flow.version, steps=bind_flow_steps(session, flow, site)),
        variables=variables or {},
        options=options,
    )


def _build_chain_job(
    session: Session,
    run_id: str,
    site: Site,
    chain: list[Flow],
    options: RunOptions,
    variables: dict[str, str] | None = None,
) -> Job:
    bound = [bind_flow_for_site(session, item, site) for item in chain]
    name, steps, _ignored = compose_chain(bound)
    return Job(
        run_id=run_id,
        kind="replay",
        site=_site_ref(site),
        auth=credential_for_site(session, chain[0], site),
        flow=FlowDSL(name=name, version=chain[-1].version, steps=steps),
        variables=variables or {},
        options=options,
    )


def _enqueue_chain(
    session: Session,
    chain: list[Flow],
    site: Site,
    *,
    headless: bool,
    dry_run: bool,
    variables: dict[str, str] | None = None,
    batch_id: str | None = None,
    batch_index: int | None = None,
) -> Run:
    target = chain[-1]
    run_id = _new_id()
    options = RunOptions(headless=headless, dry_run=dry_run)
    if len(chain) == 1:
        job = _build_job(session, run_id, site, chain[0], options, variables)
    else:
        job = _build_chain_job(session, run_id, site, chain, options, variables)
    run = Run(
        id=run_id,
        tenant_id=target.tenant_id,
        project_id=target.project_id,
        site_id=site.id,
        flow_id=target.id,
        flow_version=target.version,
        kind="replay",
        status="queued",
        job=job.model_dump(mode="json"),
        required_labels=[] if headless else ["headed"],
        batch_id=batch_id,
        batch_index=batch_index,
    )
    session.add(run)
    return run


def _queue_replay(
    session: Session,
    flow: Flow,
    site: Site,
    *,
    headless: bool,
    dry_run: bool,
    variables: dict[str, str] | None = None,
    batch_id: str | None = None,
    batch_index: int | None = None,
) -> Run:
    chain = expand_setup_chain(flow, _project_flow_map(session, flow))
    return _enqueue_chain(
        session,
        chain,
        site,
        headless=headless,
        dry_run=dry_run,
        variables=variables,
        batch_id=batch_id,
        batch_index=batch_index,
    )


def _batch_out(batch: Batch) -> BatchOut:
    return BatchOut(
        id=batch.id,
        site_id=batch.site_id,
        suite_id=batch.suite_id,
        name=batch.name,
        status=batch.status,
        flow_ids=list(batch.flow_ids or []),
        current_index=batch.current_index,
        current_run_id=batch.current_run_id,
        items=list(batch.items or []),
        created_at=batch.created_at,
        finished_at=batch.finished_at,
    )


def _finish_batch(batch: Batch, status: str, items: list[dict[str, Any]]) -> None:
    batch.items = items
    flag_modified(batch, "items")
    batch.status = status
    batch.finished_at = _now()


def _advance_batch(session: Session, run: Run) -> Run | None:
    if not run.batch_id:
        return None
    batch = session.get(Batch, run.batch_id)
    if batch is None or batch.status not in {"queued", "running"}:
        return None
    items = [dict(item) for item in (batch.items or [])]
    index = run.batch_index if run.batch_index is not None else batch.current_index
    if 0 <= index < len(items):
        items[index]["run_id"] = run.id
        items[index]["status"] = run.status
    remaining = list(batch.flow_ids or [])[index + 1 :]
    decision = decide_after_run(run.status, len(remaining))
    if decision == "failed":
        for item in items[index + 1 :]:
            item["status"] = "skipped"
        _finish_batch(batch, "failed", items)
        return None
    if decision == "passed":
        _finish_batch(batch, "passed", items)
        return None
    next_index = index + 1
    next_flow = session.get(Flow, batch.flow_ids[next_index])
    site = session.get(Site, batch.site_id)
    if (
        next_flow is None
        or site is None
        or next_flow.status not in CONFIRMED_STATUSES
    ):
        items[next_index]["status"] = "skipped"
        for item in items[next_index + 1 :]:
            item["status"] = "skipped"
        _finish_batch(batch, "failed", items)
        return None
    next_run = None
    try:
        next_run = _queue_replay(
            session,
            next_flow,
            site,
            headless=batch.headless,
            dry_run=batch.dry_run,
            variables=batch.variables or {},
            batch_id=batch.id,
            batch_index=next_index,
        )
    except (ChainError, ReplayBindError):
        items[next_index]["status"] = "skipped"
        for item in items[next_index + 1 :]:
            item["status"] = "skipped"
        _finish_batch(batch, "failed", items)
        return None
    items[next_index]["run_id"] = next_run.id
    items[next_index]["status"] = "queued"
    batch.items = items
    flag_modified(batch, "items")
    batch.current_index = next_index
    batch.current_run_id = next_run.id
    batch.status = "running"
    return next_run


@router.post("/runs", response_model=RunOut)
def create_run(payload: RunCreate, scope: Scope = Depends(get_scope), session: Session = Depends(get_session)) -> RunOut:
    flow = _get_flow(session, scope, payload.flow_id)
    site = _get_site(session, scope, payload.site_id or flow.site_id)
    try:
        run = _queue_replay(
            session,
            flow,
            site,
            headless=payload.headless,
            dry_run=payload.dry_run,
            variables=payload.variables,
        )
    except (ChainError, ReplayBindError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    hub.notify_new_job()
    return _run_out(run)


@router.post("/batches", response_model=BatchOut)
def create_batch(
    payload: BatchCreate, scope: Scope = Depends(get_scope), session: Session = Depends(get_session)
) -> BatchOut:
    suite = None
    if payload.suite_id:
        suite = _get_suite(session, scope, payload.suite_id)
    flow_ids = list(payload.flow_ids or (suite.flow_ids if suite is not None else []))
    members = _validated_members(session, scope, payload.site_id, flow_ids)
    site = _get_site(session, scope, payload.site_id)
    name = (payload.name or (suite.name if suite is not None else "") or "勾选运行").strip()
    by_id = _project_flow_map(session, members[0])
    try:
        chain = expand_members(members, by_id)
    except ChainError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    batch_id = _new_id()
    try:
        run = _enqueue_chain(
            session,
            chain,
            site,
            headless=payload.headless,
            dry_run=payload.dry_run,
            variables=payload.variables,
            batch_id=batch_id,
            batch_index=0,
        )
    except ReplayBindError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    items = [{"flow_id": chain[-1].id, "run_id": run.id, "status": "queued"}]
    batch = Batch(
        id=batch_id,
        tenant_id=scope.tenant_id,
        project_id=scope.project_id,
        site_id=payload.site_id,
        suite_id=suite.id if suite is not None else None,
        name=name,
        flow_ids=[chain[-1].id],
        items=items,
        current_index=0,
        current_run_id=run.id,
        status="running",
        headless=payload.headless,
        dry_run=payload.dry_run,
        variables=payload.variables or {},
    )
    session.add(batch)
    session.commit()
    hub.notify_new_job()
    return _batch_out(batch)


@router.get("/batches/{batch_id}", response_model=BatchOut)
def get_batch(
    batch_id: str, scope: Scope = Depends(get_scope), session: Session = Depends(get_session)
) -> BatchOut:
    batch = session.get(Batch, batch_id)
    if batch is None or batch.tenant_id != scope.tenant_id or batch.project_id != scope.project_id:
        raise HTTPException(status_code=404, detail="批次不存在")
    return _batch_out(batch)


def _run_out(run: Run) -> RunOut:
    return RunOut(
        id=run.id,
        site_id=run.site_id,
        flow_id=run.flow_id,
        flow_version=run.flow_version,
        kind=run.kind,
        status=run.status,
        worker_id=run.worker_id,
        summary=run.summary,
        duration_seconds=run.duration_seconds,
        created_at=run.created_at,
        finished_at=run.finished_at,
    )


@router.get("/runs", response_model=list[RunOut])
def list_runs(
    limit: int = Query(default=30, le=200),
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> list[RunOut]:
    rows = session.scalars(
        select(Run)
        .where(Run.tenant_id == scope.tenant_id, Run.project_id == scope.project_id)
        .order_by(Run.created_at.desc())
        .limit(limit)
    ).all()
    return [_run_out(row) for row in rows]


_ACTIVE_RUN_STATUS = {"queued", "leased", "running"}


def _purge_run_files(run_id: str) -> None:
    shutil.rmtree(settings.artifacts_dir / run_id, ignore_errors=True)


def _delete_run_row(session: Session, run: Run) -> None:
    session.execute(delete(RunEvent).where(RunEvent.run_id == run.id))
    session.execute(
        delete(RecordingCompilation).where(RecordingCompilation.recording_run_id == run.id)
    )
    for row in session.scalars(
        select(RecordingCompilation).where(RecordingCompilation.validation_run_id == run.id)
    ).all():
        row.validation_run_id = None
    session.delete(run)


@router.post("/history/purge")
def purge_runs(
    payload: RunPurgeIn, scope: Scope = Depends(get_scope), session: Session = Depends(get_session)
) -> dict[str, Any]:
    """按用户勾选删除历史运行。进行中的任务跳过。"""
    ids = list(dict.fromkeys(item.strip() for item in payload.ids if item and item.strip()))
    if not ids:
        raise HTTPException(status_code=400, detail="请先勾选要删除的记录")
    deleted: list[str] = []
    skipped: list[dict[str, str]] = []
    for run_id in ids:
        run = session.get(Run, run_id)
        if run is None or run.tenant_id != scope.tenant_id or run.project_id != scope.project_id:
            skipped.append({"id": run_id, "reason": "不存在"})
            continue
        if run.status in _ACTIVE_RUN_STATUS:
            skipped.append({"id": run_id, "reason": "进行中"})
            continue
        _delete_run_row(session, run)
        deleted.append(run_id)
    session.commit()
    for run_id in deleted:
        _purge_run_files(run_id)
    prune_retained_runs()
    return {"deleted": deleted, "skipped": skipped}


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(run_id: str, scope: Scope = Depends(get_scope), session: Session = Depends(get_session)) -> RunOut:
    run = session.get(Run, run_id)
    if run is None or run.tenant_id != scope.tenant_id or run.project_id != scope.project_id:
        raise HTTPException(status_code=404, detail="运行不存在")
    return _run_out(run)


def _snapshot(session: Session, run_id: str) -> dict[str, Any]:
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="运行不存在")
    events = session.scalars(
        select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.seq)
    ).all()
    heal = _pending_heal_for_run(session, run_id)
    return {
        "run": {
            "id": run.id,
            "status": run.status,
            "worker_id": run.worker_id,
            "flow_id": run.flow_id,
            "flow_version": run.flow_version,
            "site_id": run.site_id,
            "summary": run.summary,
            "duration_seconds": run.duration_seconds,
        },
        "events": [
            {"seq": e.seq, "type": e.type, "ts": e.ts.isoformat(), "data": e.data} for e in events
        ],
        "heal_task": _heal_out(heal).model_dump() if heal is not None else None,
    }


@router.get("/runs/{run_id}/snapshot")
def get_snapshot(run_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    return _snapshot(session, run_id)


@router.get("/runs/{run_id}/stream")
async def stream_run(run_id: str) -> StreamingResponse:
    """SSE 直播：首包全量快照 + 增量 + 心跳。

    断线后前端重连，重新拿快照补齐，不会因为断连丢掉结论。
    """
    queue = hub.subscribe(run_id)

    async def gen():
        try:
            snapshot = await run_in_threadpool(_snapshot_safe, run_id)
            yield _sse("snapshot", snapshot)
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=20)
                except asyncio.TimeoutError:
                    # 心跳，防中间层掐断空闲连接
                    yield ": ping\n\n"
                    continue
                yield _sse(payload.get("event", "message"), payload.get("data", {}))
        finally:
            hub.unsubscribe(run_id, queue)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _snapshot_safe(run_id: str) -> dict[str, Any]:
    with session_scope() as session:
        return _snapshot(session, run_id)


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


# ---------------------------------------------------------------- 站点接入

# 踩点任务用的占位站点。踩点时还没有站点记录——这正是它要解决的问题。
_INSPECT_PLACEHOLDER = "-"


@router.post("/onboarding/inspect")
def start_inspect(
    payload: InspectIn, scope: Scope = Depends(get_scope), session: Session = Depends(get_session)
) -> dict[str, Any]:
    """派一个踩点任务：打开登录页，认出账号框、密码框、提交按钮。

    控制面不装浏览器，所以这活必须交给执行器。
    """
    parsed = urlparse(payload.login_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="请填写完整的登录页地址（http:// 或 https:// 开头）")

    run_id = _new_id()
    base_url = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
    job = Job(
        run_id=run_id,
        kind="inspect",
        # 踩点不查页面错误，只看结构，探针关掉省事
        site=SiteRef(id=_INSPECT_PLACEHOLDER, base_url=base_url, probe=ProbeConfig(enabled=False)),
        inspect_url=payload.login_url,
        options=RunOptions(headless=True, screenshot_each_step=False, video="off", trace="off"),
    )
    run = Run(
        id=run_id,
        tenant_id=scope.tenant_id,
        project_id=scope.project_id,
        site_id=_INSPECT_PLACEHOLDER,
        kind="inspect",
        status="queued",
        job=job.model_dump(mode="json"),
        required_labels=[],
    )
    session.add(run)
    session.commit()
    hub.notify_new_job()
    return {"run_id": run_id}


@router.get("/onboarding/inspect/{run_id}")
def get_inspect(
    run_id: str, scope: Scope = Depends(get_scope), session: Session = Depends(get_session)
) -> dict[str, Any]:
    run = session.get(Run, run_id)
    if run is None or run.tenant_id != scope.tenant_id or run.project_id != scope.project_id:
        raise HTTPException(status_code=404, detail="踩点任务不存在")
    return {"status": run.status, "summary": run.summary or {}}


@router.post("/onboarding/commit")
def commit_onboarding(
    payload: OnboardCommitIn,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """确认踩点结果，建站点 + 凭证 + 冒烟流程。"""
    run = session.get(Run, payload.inspect_run_id)
    if run is None or run.tenant_id != scope.tenant_id or run.project_id != scope.project_id:
        raise HTTPException(status_code=404, detail="踩点任务不存在")
    if run.status != "passed":
        raise HTTPException(status_code=409, detail="踩点还没成功，不能保存")

    summary = run.summary or {}
    detection = summary.get("detection") or {}
    if not detection.get("found"):
        raise HTTPException(status_code=409, detail="没有识别到登录表单")

    site = Site(
        id=_new_id(),
        tenant_id=scope.tenant_id,
        project_id=scope.project_id,
        name=payload.site_name,
        base_url=summary["base_url"].rstrip("/"),
        env="test",
        adapter="generic",
        probe_error_url_patterns=[],
    )
    session.add(site)
    session.flush()

    material: dict[str, Any] = {
        "login_path": summary["login_path"],
        "username": payload.username,
        "password": payload.password,
        "username_target": detection["username_target"],
        "password_target": detection["password_target"],
        "submit_target": detection["submit_target"],
    }
    if payload.success_text:
        material["success_text"] = payload.success_text

    credential = Credential(
        id=_new_id(),
        tenant_id=scope.tenant_id,
        project_id=scope.project_id,
        site_id=site.id,
        name=f"{payload.username}（表单登录）",
        type="form",
        payload_encrypted=crypto.encrypt(json.dumps(material, ensure_ascii=False)),
        updated_at=_now(),
    )
    session.add(credential)
    session.flush()

    # 登录步骤由凭证在执行时展开，这里只写登录之后要干什么
    flow = Flow(
        id=_new_id(),
        tenant_id=scope.tenant_id,
        project_id=scope.project_id,
        site_id=site.id,
        name=f"{payload.site_name} · 登录冒烟",
        status="draft",
        steps=[
            {
                "id": "settle",
                "action": "waitFor",
                "condition": "network_idle",
                "label": "等待首页加载完成",
                "timeout_ms": 20000,
            },
            {"id": "health", "action": "pageHealth", "label": "首页体检（探针）"},
        ],
        auth_type="form",
        credential_id=credential.id,
    )
    session.add(flow)
    session.commit()

    return {"site_id": site.id, "flow_id": flow.id, "flow_name": flow.name}


# ---------------------------------------------------------------- 录制


@router.post("/recordings")
def start_recording(
    payload: RecordingCreate, scope: Scope = Depends(get_scope), session: Session = Depends(get_session)
) -> dict[str, Any]:
    """派一个开窗录制任务。必须 headed：人要看见并操作。"""
    intent = payload.intent.strip()
    if not intent:
        raise HTTPException(status_code=400, detail="请说明本次录制要完成什么")
    prune_retained_runs()
    site = _get_site(session, scope, payload.site_id)
    auth = AuthRef()
    if payload.credential_id:
        credential = session.get(Credential, payload.credential_id)
        if (
            credential is None
            or credential.site_id != site.id
            or credential.tenant_id != scope.tenant_id
            or credential.project_id != scope.project_id
        ):
            raise HTTPException(status_code=404, detail="凭证不存在")
        auth = AuthRef(type=credential.type, ref=credential.id)  # type: ignore[arg-type]

    run_id = _new_id()
    job = Job(
        run_id=run_id,
        kind="record",
        site=SiteRef(
            id=site.id,
            base_url=site.base_url,
            env=site.env,
            adapter=site.adapter,
            probe=ProbeConfig(enabled=False, error_url_patterns=site.probe_error_url_patterns),
        ),
        auth=auth,
        record_start_path=payload.start_path or None,
        record_intent=intent,
        options=RunOptions(headless=False, screenshot_each_step=False, video="off", trace="off"),
    )
    run = Run(
        id=run_id,
        tenant_id=scope.tenant_id,
        project_id=scope.project_id,
        site_id=site.id,
        kind="record",
        status="queued",
        job=job.model_dump(mode="json"),
        required_labels=["headed"],
        stop_requested=False,
    )
    session.add(run)
    session.commit()
    hub.notify_new_job()
    return {"run_id": run_id}


@router.get("/recordings/{run_id}")
def get_recording(
    run_id: str, scope: Scope = Depends(get_scope), session: Session = Depends(get_session)
) -> dict[str, Any]:
    run = session.get(Run, run_id)
    if run is None or run.tenant_id != scope.tenant_id or run.project_id != scope.project_id:
        raise HTTPException(status_code=404, detail="录制任务不存在")
    last = session.scalars(
        select(RunEvent)
        .where(RunEvent.run_id == run_id, RunEvent.type == "record.progress")
        .order_by(RunEvent.seq.desc())
        .limit(1)
    ).first()
    event_count = (last.data or {}).get("event_count", 0) if last else 0
    return {"status": run.status, "summary": run.summary or {}, "event_count": event_count}


def _get_compilation(
    session: Session, scope: Scope, run_id: str
) -> RecordingCompilation:
    row = session.scalar(
        select(RecordingCompilation).where(
            RecordingCompilation.recording_run_id == run_id,
            RecordingCompilation.tenant_id == scope.tenant_id,
            RecordingCompilation.project_id == scope.project_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="AI 编译任务不存在")
    return row


def _compilation_out(row: RecordingCompilation) -> CompilationOut:
    steps = row.compiled_steps or row.deterministic_steps or []
    return CompilationOut(
        id=row.id,
        recording_run_id=row.recording_run_id,
        status=row.status,
        attempt=row.attempt,
        max_attempts=_MAX_COMPILE_ATTEMPTS,
        steps=steps,
        notes=row.compile_notes or [],
        validation_run_id=row.validation_run_id,
        usage=row.usage or {},
        error=row.error,
        verified=row.status == "passed",
    )


@router.post("/recordings/{run_id}/compile", response_model=CompilationOut)
def start_recording_compile(
    run_id: str,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> CompilationOut:
    run = session.get(Run, run_id)
    if run is None or run.tenant_id != scope.tenant_id or run.project_id != scope.project_id:
        raise HTTPException(status_code=404, detail="录制任务不存在")
    if run.kind != "record" or run.status != "passed":
        raise HTTPException(status_code=409, detail="录制成功后才能进行 AI 编译")
    existing = session.scalar(
        select(RecordingCompilation).where(RecordingCompilation.recording_run_id == run_id)
    )
    if existing is not None:
        return _compilation_out(existing)
    summary = run.summary or {}
    steps = summary.get("steps") or []
    if not isinstance(steps, list) or not steps:
        raise HTTPException(status_code=409, detail="录制没有生成可编译步骤")
    intent = str((run.job or {}).get("record_intent") or "").strip()
    if not intent:
        raise HTTPException(status_code=409, detail="录制任务缺少意图")
    row = RecordingCompilation(
        id=_new_id(),
        tenant_id=scope.tenant_id,
        project_id=scope.project_id,
        recording_run_id=run.id,
        status="queued",
        intent=intent,
        deterministic_steps=steps,
        compile_notes=list(summary.get("notes") or []),
    )
    session.add(row)
    session.commit()
    return _compilation_out(row)


@router.get("/recordings/{run_id}/compilation", response_model=CompilationOut)
def get_recording_compile(
    run_id: str,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> CompilationOut:
    return _compilation_out(_get_compilation(session, scope, run_id))


@router.post("/recordings/{run_id}/compilation/retry", response_model=CompilationOut)
def retry_recording_compile(
    run_id: str,
    payload: CompilationRetry,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> CompilationOut:
    row = _get_compilation(session, scope, run_id)
    if row.status not in {"fallback", "error", "passed", "manual_validation"}:
        raise HTTPException(status_code=409, detail="当前编译仍在进行")
    if payload.intent is not None and payload.intent.strip():
        row.intent = payload.intent.strip()
    row.status = "queued"
    row.attempt = 0
    row.validation_run_id = None
    row.failure_context = None
    row.compiled_steps = None
    row.error = None
    session.commit()
    return _compilation_out(row)


@router.post("/recordings/{run_id}/compilation/use-fallback", response_model=CompilationOut)
def use_recording_fallback(
    run_id: str,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> CompilationOut:
    row = _get_compilation(session, scope, run_id)
    row.status = "fallback"
    row.compiled_steps = row.deterministic_steps
    row.validation_run_id = None
    row.error = row.error or "已采用确定性步骤，尚未通过自动回放验证"
    session.commit()
    return _compilation_out(row)


@router.post("/recordings/{run_id}/stop")
def stop_recording(
    run_id: str, scope: Scope = Depends(get_scope), session: Session = Depends(get_session)
) -> dict[str, Any]:
    run = session.get(Run, run_id)
    if run is None or run.tenant_id != scope.tenant_id or run.project_id != scope.project_id:
        raise HTTPException(status_code=404, detail="录制任务不存在")
    run.stop_requested = True
    session.commit()
    return {"ok": True}


@router.get("/runs/{run_id}/control")
def run_control(
    run_id: str, worker_id: str, token: str, session: Session = Depends(get_session)
) -> dict[str, Any]:
    worker = _auth_worker(session, worker_id, token)
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="运行不存在")
    if run.worker_id != worker.id:
        raise HTTPException(status_code=403, detail="该运行不属于此 worker")
    return {"stop": bool(run.stop_requested)}


def _prepare_recorded_step(raw: dict[str, Any]) -> dict[str, Any]:
    """保存前把录制步骤收成 DSL 能认的形状，避免一种新定位方式让整段保存静默失败。"""
    data = dict(raw or {})
    target = data.get("target")
    if not isinstance(target, dict):
        return data
    kept: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for cand in target.get("candidates") or []:
        if not isinstance(cand, dict):
            continue
        kind = cand.get("kind")
        value = cand.get("value")
        if not kind or value is None:
            continue
        pieces = [{"kind": kind, "value": str(value)}]
        if cand.get("name"):
            pieces[0]["name"] = cand["name"]
        for item in pieces:
            if item["kind"] not in CANDIDATE_STABILITY:
                continue
            key = (item["kind"], item["value"])
            if key in seen:
                continue
            seen.add(key)
            kept.append(item)
    if not kept:
        return data
    cleaned: dict[str, Any] = {"candidates": kept}
    scope = target.get("scope")
    if isinstance(scope, dict) and scope.get("kind") in {"page", "modal", "drawer", "dropdown"}:
        cleaned["scope"] = {k: v for k, v in scope.items() if v not in (None, "")}
    for key in ("widget", "panel", "trigger_css"):
        value = target.get(key)
        if value:
            cleaned[key] = value
    data["target"] = cleaned
    return data


@router.post("/recordings/{run_id}/save")
def save_recording(
    run_id: str,
    payload: RecordingSave,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    run = session.get(Run, run_id)
    if run is None or run.tenant_id != scope.tenant_id or run.project_id != scope.project_id:
        raise HTTPException(status_code=404, detail="录制任务不存在")
    if run.kind != "record":
        raise HTTPException(status_code=409, detail="这不是一次录制")
    if run.status != "passed":
        raise HTTPException(status_code=409, detail="录制还没成功，不能保存")
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="流程名称不能为空")

    validated: list[dict[str, Any]] = []
    for index, raw in enumerate(payload.steps, start=1):
        prepared = _prepare_recorded_step(raw)
        try:
            step = Step.model_validate(prepared)
            validate_template_value(step.value, step.id)
            validate_template_value(step.expected, step.id)
        except (ValidationError, AIContractError) as exc:
            if isinstance(exc, ValidationError):
                first = exc.errors()[0]
                message = first.get("msg")
                loc = ".".join(str(x) for x in first.get("loc", ()))
            else:
                message = str(exc)
                loc = "value/expected"
            raise HTTPException(
                status_code=400, detail=f"第 {index} 步无效：{message}（{loc}）"
            ) from exc
        validated.append(step.model_dump(mode="json", exclude_none=True))

    compilation = session.scalar(
        select(RecordingCompilation).where(
            RecordingCompilation.recording_run_id == run_id
        )
    )
    verified_steps: list[dict[str, Any]] = []
    if compilation is not None and compilation.status == "passed":
        for raw in compilation.compiled_steps or []:
            try:
                verified_steps.append(
                    Step.model_validate(_prepare_recorded_step(raw)).model_dump(
                        mode="json", exclude_none=True
                    )
                )
            except ValidationError:
                verified_steps = []
                break
    is_verified_version = bool(verified_steps) and validated == verified_steps
    if not is_verified_version and not payload.allow_unverified:
        raise HTTPException(
            status_code=409,
            detail="当前步骤未通过自动回放验证；确认以 draft 保存时请显式允许未验证版本",
        )

    job = run.job or {}
    auth = job.get("auth") or {}
    flow = Flow(
        id=_new_id(),
        tenant_id=scope.tenant_id,
        project_id=scope.project_id,
        site_id=run.site_id,
        name=payload.name.strip(),
        status="draft",
        steps=validated,
        auth_type=auth.get("type") or "none",
        credential_id=auth.get("ref"),
    )
    session.add(flow)
    session.commit()
    return {"flow_id": flow.id, "flow_name": flow.name}


# ---------------------------------------------------------------- Worker


@router.post("/workers/register", response_model=WorkerOut)
def register_worker(payload: WorkerRegister, session: Session = Depends(get_session)) -> WorkerOut:
    worker = Worker(
        id=_new_id(),
        project_id=payload.project_id,
        name=payload.name,
        token=secrets.token_urlsafe(32),
        labels=payload.labels,
        platform=payload.platform,
        last_heartbeat_at=_now(),
        registered_at=_now(),
    )
    session.add(worker)
    session.commit()
    return _worker_out(worker)


def _worker_out(worker: Worker) -> WorkerOut:
    heartbeat = worker.last_heartbeat_at
    if heartbeat.tzinfo is None:
        heartbeat = heartbeat.replace(tzinfo=timezone.utc)
    online = (_now() - heartbeat).total_seconds() < settings.heartbeat_offline_seconds
    return WorkerOut(
        id=worker.id,
        name=worker.name,
        token=worker.token,
        labels=worker.labels,
        platform=worker.platform,
        online=online,
        last_heartbeat_at=worker.last_heartbeat_at,
    )


@router.post("/workers/heartbeat")
def heartbeat(payload: HeartbeatIn, session: Session = Depends(get_session)) -> dict[str, Any]:
    worker = _auth_worker(session, payload.worker_id, payload.token)
    worker.last_heartbeat_at = _now()
    if payload.labels is not None:
        worker.labels = payload.labels
    session.commit()
    return {"ok": True}


@router.get("/workers", response_model=list[WorkerOut])
def list_workers(session: Session = Depends(get_session)) -> list[WorkerOut]:
    rows = session.scalars(select(Worker)).all()
    return [_worker_out(row) for row in rows]


@router.post("/workers/local/start")
def start_local() -> dict[str, Any]:
    result = start_local_worker()
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error") or "执行器启动失败")
    return result


@router.post("/workers/local/stop")
def stop_local(session: Session = Depends(get_session)) -> dict[str, Any]:
    result = stop_local_worker()
    leftover = result.get("leftover") or []
    # 进程确实没了才标离线。进程还在就改心跳，只是让界面假装停掉。
    if not leftover:
        cutoff = _now() - timedelta(seconds=settings.heartbeat_offline_seconds + 5)
        for row in session.scalars(select(Worker)).all():
            row.last_heartbeat_at = cutoff
        session.commit()
    return result


def _reclaim_expired(session: Session) -> None:
    """回收失联 Worker 手里的任务，让它能被重新领取。"""
    now = _now()
    rows = session.scalars(select(Run).where(Run.status.in_(["leased", "running"]))).all()
    for run in rows:
        expires = run.lease_expires_at
        if expires is None:
            continue
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < now:
            run.status = "queued"
            run.worker_id = None
            run.lease_expires_at = None


def _try_claim(worker_id: str, token: str) -> dict[str, Any] | None:
    with session_scope() as session:
        worker = _auth_worker(session, worker_id, token)
        worker.last_heartbeat_at = _now()
        _reclaim_expired(session)

        labels = set(worker.labels or [])
        candidates = session.scalars(
            select(Run).where(Run.status == "queued").order_by(Run.created_at)
        ).all()
        for run in candidates:
            if not set(run.required_labels or []).issubset(labels):
                continue
            run.status = "leased"
            run.worker_id = worker.id
            run.lease_expires_at = _now() + timedelta(seconds=settings.lease_ttl_seconds)
            job = dict(run.job)
            job["lease_expires_at"] = run.lease_expires_at.isoformat()
            return job
        return None


@router.get("/jobs/lease")
async def lease_job(worker_id: str, token: str) -> dict[str, Any]:
    """长轮询领任务。

    平台不反向连接 Worker：被测系统多在内网、值班机常在 NAT 后，
    只要 Worker 能单向出网就能工作。
    """
    deadline = asyncio.get_event_loop().time() + settings.lease_wait_seconds
    while True:
        if local_stop_requested():
            return {"job": None, "shutdown": True}
        async with _lease_lock:
            job = await run_in_threadpool(_try_claim, worker_id, token)
        if job is not None:
            return {"job": job}
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            return {"job": None}
        await hub.wait_for_job(timeout=min(remaining, 1.0))


@router.post("/runs/{run_id}/events")
def ingest_events(run_id: str, payload: EventsIn, session: Session = Depends(get_session)) -> dict[str, Any]:
    """接收执行器上报的结构化事件。

    成败结论由执行器给出，平台不解析日志文本——那种做法一换站点就破。
    """
    worker = _auth_worker(session, payload.worker_id, payload.token)
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="运行不存在")
    if run.worker_id != worker.id:
        raise HTTPException(status_code=403, detail="该运行不属于此 worker")

    last = session.scalars(
        select(RunEvent.seq).where(RunEvent.run_id == run_id).order_by(RunEvent.seq.desc()).limit(1)
    ).first()
    seq = (last or 0) + 1

    stored: list[dict[str, Any]] = []
    for event in payload.events:
        data = _redact(event.data)
        row = RunEvent(
            run_id=run_id,
            seq=seq,
            type=event.type,
            ts=event.ts or _now(),
            data=data,
        )
        session.add(row)
        stored.append({"seq": seq, "type": event.type, "ts": row.ts.isoformat(), "data": data})
        if event.type == "run.start":
            run.status = "running"
        # 续租：执行中的长流程不该被回收
        run.lease_expires_at = _now() + timedelta(seconds=settings.lease_ttl_seconds)
        seq += 1

    session.commit()
    for item in stored:
        hub.publish(run_id, {"event": "event", "data": item})
    return {"accepted": len(stored)}


@router.post("/runs/{run_id}/complete", response_model=RunOut)
def complete_run(run_id: str, payload: CompleteIn, session: Session = Depends(get_session)) -> RunOut:
    worker = _auth_worker(session, payload.worker_id, payload.token)
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="运行不存在")
    if run.worker_id != worker.id:
        raise HTTPException(status_code=403, detail="该运行不属于此 worker")

    run.status = payload.status
    run.summary = _redact(payload.summary)
    run.duration_seconds = payload.duration_seconds
    run.finished_at = _now()
    run.lease_expires_at = None
    updates = (payload.summary or {}).get("locator_updates") or []
    heal = _collect_heal_task(session, run, updates)
    next_run = _advance_batch(session, run)
    batch = session.get(Batch, run.batch_id) if run.batch_id else None
    session.commit()
    if heal is not None:
        session.refresh(heal)

    hub.publish(
        run_id,
        {
            "event": "run_end",
            "data": {
                "status": run.status,
                "summary": run.summary,
                "duration_seconds": run.duration_seconds,
                "heal_task": _heal_out(heal).model_dump() if heal is not None else None,
                "batch": _batch_out(batch).model_dump(mode="json") if batch is not None else None,
            },
        },
    )
    if next_run is not None:
        hub.notify_new_job()
    prune_retained_runs()
    return _run_out(run)


@router.get("/heal-tasks/{task_id}", response_model=HealTaskOut)
def get_heal_task(task_id: str, session: Session = Depends(get_session)) -> HealTaskOut:
    task = session.get(HealTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="修补任务不存在")
    return _heal_out(task)


@router.post("/heal-tasks/{task_id}/apply", response_model=HealTaskOut)
def apply_heal_task(task_id: str, session: Session = Depends(get_session)) -> HealTaskOut:
    """执行者：用户确认后，只改监督者列出的那几步定位。"""
    task = session.get(HealTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="修补任务不存在")
    if task.status != "pending":
        return _heal_out(task)
    flow = session.get(Flow, task.flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="流程不存在")
    new_steps, logs = apply_locator_patches(flow.steps or [], task.patches or [])
    flow.steps = new_steps
    flag_modified(flow, "steps")
    if any(not line.startswith("跳过") for line in logs):
        flow.version = int(flow.version or 1) + 1
    task.status = "applied"
    task.applied_log = logs
    flag_modified(task, "applied_log")
    session.commit()
    return _heal_out(task)


@router.post("/heal-tasks/{task_id}/reject", response_model=HealTaskOut)
def reject_heal_task(task_id: str, session: Session = Depends(get_session)) -> HealTaskOut:
    task = session.get(HealTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="修补任务不存在")
    if task.status == "pending":
        task.status = "rejected"
        session.commit()
    return _heal_out(task)


@router.post("/runs/{run_id}/artifacts")
async def upload_artifact(
    run_id: str,
    worker_id: str = Form(...),
    token: str = Form(...),
    name: str = Form(...),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """产物上传。

    P0 落本地磁盘；换 MinIO 时改成预签名直传，接口形状不变。
    """

    def _check() -> None:
        with session_scope() as session:
            worker = _auth_worker(session, worker_id, token)
            run = session.get(Run, run_id)
            if run is None:
                raise HTTPException(status_code=404, detail="运行不存在")
            if run.worker_id != worker.id:
                raise HTTPException(status_code=403, detail="该运行不属于此 worker")

    await run_in_threadpool(_check)

    safe_name = re.sub(r"[^A-Za-z0-9_.\-]", "_", name)
    target_dir = settings.artifacts_dir / run_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / safe_name
    content = await file.read()
    await run_in_threadpool(target.write_bytes, content)
    return {"url": f"/artifacts/{run_id}/{safe_name}", "bytes": len(content)}


@router.get("/credentials/{credential_id}/material")
def get_credential_material(
    credential_id: str, worker_id: str, token: str, session: Session = Depends(get_session)
) -> dict[str, Any]:
    """Worker 按引用换取凭证明文。

    只有持有效令牌的 Worker 能调，且明文只在 Worker 内存中使用。
    面向使用者的读接口永远不返回它。
    """
    _auth_worker(session, worker_id, token)
    credential = session.get(Credential, credential_id)
    if credential is None:
        raise HTTPException(status_code=404, detail="凭证不存在")
    return {"type": credential.type, "payload": json.loads(crypto.decrypt(credential.payload_encrypted))}
