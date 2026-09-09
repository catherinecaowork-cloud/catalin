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

@router.post("/suites", response_model=SuiteOut)
def create_suite(
    payload: SuiteCreate, scope: Scope = Depends(get_scope), session: Session = Depends(get_session)
) -> SuiteOut:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="请填写套件名称")
    validated_members(session, scope, payload.site_id, payload.flow_ids)
    suite = Suite(
        id=new_id(),
        tenant_id=scope.tenant_id,
        project_id=scope.project_id,
        site_id=payload.site_id,
        name=name,
        flow_ids=list(payload.flow_ids),
    )
    session.add(suite)
    session.commit()
    return suite_out(suite)


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
    return [suite_out(row) for row in rows]


@router.put("/suites/{suite_id}", response_model=SuiteOut)
def update_suite(
    suite_id: str,
    payload: SuiteUpdate,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> SuiteOut:
    suite = get_suite(session, scope, suite_id)
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="请填写套件名称")
        suite.name = name
    if payload.flow_ids is not None:
        validated_members(session, scope, suite.site_id, payload.flow_ids)
        suite.flow_ids = list(payload.flow_ids)
        flag_modified(suite, "flow_ids")
    session.commit()
    return suite_out(suite)


@router.delete("/suites/{suite_id}")
def delete_suite(
    suite_id: str, scope: Scope = Depends(get_scope), session: Session = Depends(get_session)
) -> dict[str, Any]:
    suite = get_suite(session, scope, suite_id)
    session.delete(suite)
    session.commit()
    return {"ok": True}
