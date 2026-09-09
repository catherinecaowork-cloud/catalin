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
from autotest_control.domain.observer import attach_model_to_flow, seed_run_observation
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

@router.post("/recordings")
def start_recording(
    payload: RecordingCreate, scope: Scope = Depends(get_scope), session: Session = Depends(get_session)
) -> dict[str, Any]:
    """派一个开窗录制任务。必须 headed：人要看见并操作。"""
    intent = payload.intent.strip()
    if not intent:
        raise HTTPException(status_code=400, detail="请说明本次录制要完成什么")
    prune_retained_runs()
    site = get_site(session, scope, payload.site_id)
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

    run_id = new_id()
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
    session.flush()
    seed_run_observation(session, scope, run)
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
    observation = run.observation_model if isinstance(run.observation_model, dict) else {}
    entries = observation.get("entries") if isinstance(observation.get("entries"), list) else []
    return {
        "status": run.status,
        "summary": run.summary or {},
        "event_count": event_count,
        "observation_model": observation,
        "recognized_count": len(entries),
    }








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
        return compilation_out(existing)
    summary = run.summary or {}
    steps = summary.get("sample_steps") or summary.get("steps") or []
    if not isinstance(steps, list) or not steps:
        raise HTTPException(status_code=409, detail="录制没有生成可编译步骤")
    intent = str((run.job or {}).get("record_intent") or "").strip()
    if not intent:
        raise HTTPException(status_code=409, detail="录制任务缺少意图")
    observation = run.observation_model if isinstance(run.observation_model, dict) else {}
    compile_mode = "observer" if observation.get("entries") else "polish"
    row = RecordingCompilation(
        id=new_id(),
        tenant_id=scope.tenant_id,
        project_id=scope.project_id,
        recording_run_id=run.id,
        status="queued",
        intent=intent,
        deterministic_steps=steps,
        compile_mode=compile_mode,
        compile_notes=list(summary.get("notes") or []),
    )
    session.add(row)
    session.commit()
    return compilation_out(row)


@router.get("/recordings/{run_id}/compilation", response_model=CompilationOut)
def get_recording_compile(
    run_id: str,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> CompilationOut:
    return compilation_out(get_compilation(session, scope, run_id))


@router.post("/recordings/{run_id}/compilation/retry", response_model=CompilationOut)
def retry_recording_compile(
    run_id: str,
    payload: CompilationRetry,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> CompilationOut:
    row = get_compilation(session, scope, run_id)
    if row.status not in {"fallback", "error", "passed", "manual_validation"}:
        raise HTTPException(status_code=409, detail="当前编译仍在进行")
    if payload.intent is not None and payload.intent.strip():
        row.intent = payload.intent.strip()
    if payload.compile_mode is not None:
        row.compile_mode = payload.compile_mode
        if payload.compile_mode == "polish":
            row.observer_steps = None
    row.status = "queued"
    row.attempt = 0
    row.validation_run_id = None
    row.failure_context = None
    row.compiled_steps = None
    row.error = None
    session.commit()
    return compilation_out(row)


@router.post("/recordings/{run_id}/compilation/use-fallback", response_model=CompilationOut)
def use_recording_fallback(
    run_id: str,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> CompilationOut:
    row = get_compilation(session, scope, run_id)
    row.status = "fallback"
    row.compiled_steps = row.deterministic_steps
    row.observer_steps = None
    row.compile_mode = "fallback"
    row.validation_run_id = None
    row.error = row.error or "已采用确定性步骤，尚未通过自动回放验证"
    session.commit()
    return compilation_out(row)


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
    worker = auth_worker(session, worker_id, token)
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="运行不存在")
    if run.worker_id != worker.id:
        raise HTTPException(status_code=403, detail="该运行不属于此 worker")
    return {"stop": bool(run.stop_requested)}





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
        prepared = prepare_recorded_step(raw)
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
                    Step.model_validate(prepare_recorded_step(raw)).model_dump(
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
        id=new_id(),
        tenant_id=scope.tenant_id,
        project_id=scope.project_id,
        site_id=run.site_id,
        name=payload.name.strip(),
        status="draft",
        steps=validated,
        auth_type=auth.get("type") or "none",
        credential_id=auth.get("ref"),
    )
    attach_model_to_flow(flow, run)
    session.add(flow)
    session.commit()
    return {
        "flow_id": flow.id,
        "flow_name": flow.name,
        "page_widget_model": flow.page_widget_model or {},
    }
