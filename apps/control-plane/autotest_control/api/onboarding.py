from __future__ import annotations

import asyncio
import json
import re
import secrets
import shutil
from datetime import timedelta, timezone
from typing import Any
from urllib.parse import urlparse, urlunparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
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
from autotest_control.chain import ChainError, compose_chain, expand_members, expand_setup_chain
from autotest_control.db import get_session
from autotest_control.deps import (
    Scope,
    auth_worker,
    get_flow,
    get_scope,
    get_site,
    get_suite,
    lease_lock,
    new_id,
    now,
)
from autotest_control.domain.credentials import (
    copy_project_form_locators,
    form_login_locators,
    locators_from_inspect,
)
from autotest_control.domain.heal import collect_heal_task, pending_heal_for_run
from autotest_control.domain.jobs import project_flow_map
from autotest_control.domain.mappers import (
    ai_config_out,
    batch_out,
    compilation_out,
    flow_out,
    heal_out,
    run_out,
    suite_out,
    worker_out,
)
from autotest_control.domain.queue import advance_batch, enqueue_chain, queue_replay
from autotest_control.domain.recordings import get_compilation, prepare_recorded_step
from autotest_control.domain.redact import redact
from autotest_control.domain.runs import (
    ACTIVE_RUN_STATUS,
    delete_run_row,
    purge_run_files,
    reclaim_expired,
    try_claim,
)
from autotest_control.domain.snapshots import snapshot, snapshot_safe, sse
from autotest_control.domain.suites import validated_members
from autotest_control.flow_import import FlowImportError, import_flows_to_site
from autotest_control.heal import apply_locator_patches
from autotest_control.hub import hub
from autotest_control.local_worker import local_stop_requested, start_local_worker, stop_local_worker
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
from autotest_control.replay_bind import ReplayBindError, bind_flow_steps, credential_for_site
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
from autotest_control.settings import settings
from autotest_control.storage import prune_retained_runs
from autotest_control.suites import CONFIRMED_STATUSES
from autotest_protocol import AuthRef, CANDIDATE_STABILITY, Job, RunOptions, SiteRef, Step
from autotest_protocol.job import ProbeConfig

router = APIRouter()

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

    run_id = new_id()
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
        id=new_id(),
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
        id=new_id(),
        tenant_id=scope.tenant_id,
        project_id=scope.project_id,
        site_id=site.id,
        name=f"{payload.username}（表单登录）",
        type="form",
        payload_encrypted=crypto.encrypt(json.dumps(material, ensure_ascii=False)),
        updated_at=now(),
    )
    session.add(credential)
    session.flush()

    # 登录步骤由凭证在执行时展开，这里只写登录之后要干什么
    flow = Flow(
        id=new_id(),
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
