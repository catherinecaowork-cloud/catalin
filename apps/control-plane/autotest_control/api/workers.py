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
from autotest_control.db import get_session, session_scope
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

@router.post("/workers/register", response_model=WorkerOut)
def register_worker(payload: WorkerRegister, session: Session = Depends(get_session)) -> WorkerOut:
    worker = Worker(
        id=new_id(),
        project_id=payload.project_id,
        name=payload.name,
        token=secrets.token_urlsafe(32),
        labels=payload.labels,
        platform=payload.platform,
        last_heartbeat_at=now(),
        registered_at=now(),
    )
    session.add(worker)
    session.commit()
    return worker_out(worker)





@router.post("/workers/heartbeat")
def heartbeat(payload: HeartbeatIn, session: Session = Depends(get_session)) -> dict[str, Any]:
    worker = auth_worker(session, payload.worker_id, payload.token)
    worker.last_heartbeat_at = now()
    if payload.labels is not None:
        worker.labels = payload.labels
    session.commit()
    return {"ok": True}


@router.get("/workers", response_model=list[WorkerOut])
def list_workers(session: Session = Depends(get_session)) -> list[WorkerOut]:
    rows = session.scalars(select(Worker)).all()
    return [worker_out(row) for row in rows]


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
        cutoff = now() - timedelta(seconds=settings.heartbeat_offline_seconds + 5)
        for row in session.scalars(select(Worker)).all():
            row.last_heartbeat_at = cutoff
        session.commit()
    return result









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
        async with lease_lock:
            job = await run_in_threadpool(try_claim, worker_id, token)
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
    worker = auth_worker(session, payload.worker_id, payload.token)
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
        data = redact(event.data)
        row = RunEvent(
            run_id=run_id,
            seq=seq,
            type=event.type,
            ts=event.ts or now(),
            data=data,
        )
        session.add(row)
        stored.append({"seq": seq, "type": event.type, "ts": row.ts.isoformat(), "data": data})
        if event.type == "run.start":
            run.status = "running"
        # 续租：执行中的长流程不该被回收
        run.lease_expires_at = now() + timedelta(seconds=settings.lease_ttl_seconds)
        seq += 1

    session.commit()
    for item in stored:
        hub.publish(run_id, {"event": "event", "data": item})
    return {"accepted": len(stored)}


@router.post("/runs/{run_id}/complete", response_model=RunOut)
def complete_run(run_id: str, payload: CompleteIn, session: Session = Depends(get_session)) -> RunOut:
    worker = auth_worker(session, payload.worker_id, payload.token)
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="运行不存在")
    if run.worker_id != worker.id:
        raise HTTPException(status_code=403, detail="该运行不属于此 worker")

    run.status = payload.status
    run.summary = redact(payload.summary)
    run.duration_seconds = payload.duration_seconds
    run.finished_at = now()
    run.lease_expires_at = None
    updates = (payload.summary or {}).get("locator_updates") or []
    heal = collect_heal_task(session, run, updates)
    next_run = advance_batch(session, run)
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
                "heal_task": heal_out(heal).model_dump() if heal is not None else None,
                "batch": batch_out(batch).model_dump(mode="json") if batch is not None else None,
            },
        },
    )
    if next_run is not None:
        hub.notify_new_job()
    prune_retained_runs()
    return run_out(run)


@router.get("/heal-tasks/{task_id}", response_model=HealTaskOut)
def get_heal_task(task_id: str, session: Session = Depends(get_session)) -> HealTaskOut:
    task = session.get(HealTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="修补任务不存在")
    return heal_out(task)


@router.post("/heal-tasks/{task_id}/apply", response_model=HealTaskOut)
def apply_heal_task(task_id: str, session: Session = Depends(get_session)) -> HealTaskOut:
    """执行者：用户确认后，只改监督者列出的那几步定位。"""
    task = session.get(HealTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="修补任务不存在")
    if task.status != "pending":
        return heal_out(task)
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
    return heal_out(task)


@router.post("/heal-tasks/{task_id}/reject", response_model=HealTaskOut)
def reject_heal_task(task_id: str, session: Session = Depends(get_session)) -> HealTaskOut:
    task = session.get(HealTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="修补任务不存在")
    if task.status == "pending":
        task.status = "rejected"
        session.commit()
    return heal_out(task)


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
            worker = auth_worker(session, worker_id, token)
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
    auth_worker(session, worker_id, token)
    credential = session.get(Credential, credential_id)
    if credential is None:
        raise HTTPException(status_code=404, detail="凭证不存在")
    return {"type": credential.type, "payload": json.loads(crypto.decrypt(credential.payload_encrypted))}
