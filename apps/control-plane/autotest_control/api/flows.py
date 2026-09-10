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

ALLOWED_TRANSITIONS = {
    ("draft", "reviewed"),
    ("reviewed", "golden"),
    ("golden", "active"),
    # 被测系统变更后回退重走确认
    ("reviewed", "draft"),
    ("golden", "draft"),
    ("active", "draft"),
}


@router.post("/flows", response_model=FlowOut)
def create_flow(payload: FlowCreate, scope: Scope = Depends(get_scope), session: Session = Depends(get_session)) -> FlowOut:
    get_site(session, scope, payload.site_id)
    flow = Flow(
        id=new_id(),
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
    return flow_out(flow)





@router.get("/flows", response_model=list[FlowOut])
def list_flows(
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
    site_id: str | None = Query(default=None),
) -> list[FlowOut]:
    stmt = select(Flow).where(Flow.tenant_id == scope.tenant_id, Flow.project_id == scope.project_id)
    if site_id:
        get_site(session, scope, site_id)
        stmt = stmt.where(Flow.site_id == site_id)
    rows = session.scalars(stmt).all()
    return [flow_out(row) for row in rows]


@router.post("/sites/{site_id}/flows/import", response_model=FlowImportOut)
def import_flows(
    site_id: str,
    payload: FlowImportIn,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> FlowImportOut:
    target = get_site(session, scope, site_id)
    ids = list(dict.fromkeys(payload.flow_ids or []))
    if not ids:
        raise HTTPException(status_code=400, detail="请勾选要导入的脚本")
    selected = [get_flow(session, scope, item) for item in ids]
    sample = selected[0]
    by_id = project_flow_map(session, sample)
    try:
        imported, skipped = import_flows_to_site(session, target, selected, by_id)
    except FlowImportError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ChainError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    return FlowImportOut(imported=imported, skipped=skipped)





@router.delete("/flows/{flow_id}")
def delete_flow(flow_id: str, scope: Scope = Depends(get_scope), session: Session = Depends(get_session)) -> dict[str, Any]:
    flow = get_flow(session, scope, flow_id)
    if flow.status != "draft":
        raise HTTPException(status_code=409, detail="用例不能删除，请先退回草稿")
    for other in session.scalars(select(Flow).where(Flow.setup_flow_id == flow.id)).all():
        other.setup_flow_id = None
    session.delete(flow)
    session.commit()
    return {"ok": True}


@router.post("/flows/{flow_id}/status", response_model=FlowOut)
def update_flow_status(
    flow_id: str,
    payload: FlowStatusUpdate,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> FlowOut:
    """状态只能按序推进，且执行成功不会自动推进——确认是一次显式动作。"""
    flow = get_flow(session, scope, flow_id)
    if (flow.status, payload.status) not in ALLOWED_TRANSITIONS:
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
            "adopted_at": now().isoformat(),
            "summary": run.summary or {},
        }

    if payload.status == "active" and flow.baseline is None:
        raise HTTPException(status_code=409, detail="未固化基线的流程不能进入回归")

    if payload.status == "draft":
        flow.baseline = None

    flow.status = payload.status
    session.commit()
    return flow_out(flow)


@router.post("/flows/{flow_id}/setup", response_model=FlowOut)
def update_flow_setup(
    flow_id: str,
    payload: FlowSetupUpdate,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> FlowOut:
    flow = get_flow(session, scope, flow_id)
    previous_ids = list(getattr(flow, "setup_flow_ids", None) or [])
    previous_single = flow.setup_flow_id
    if payload.setup_flow_ids is not None:
        setup_ids = list(payload.setup_flow_ids)
    elif payload.setup_flow_id:
        setup_ids = [payload.setup_flow_id]
    else:
        setup_ids = []
    if flow.id in setup_ids:
        raise HTTPException(status_code=409, detail="不能把自己当成前置")
    for setup_id in setup_ids:
        setup = get_flow(session, scope, setup_id)
        if setup.id == flow.id:
            raise HTTPException(status_code=409, detail="不能把自己当成前置")
    flow.setup_flow_ids = setup_ids
    flow.setup_flow_id = setup_ids[-1] if setup_ids else None
    by_id = project_flow_map(session, flow)
    by_id[flow.id] = flow
    try:
        expand_setup_chain(flow, by_id)
    except ChainError as exc:
        flow.setup_flow_ids = previous_ids
        flow.setup_flow_id = previous_single
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    return flow_out(flow)
