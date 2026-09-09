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

@router.get("/ai/config", response_model=AIConfigOut)
def get_ai_config() -> AIConfigOut:
    return ai_config_out()


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
    return ai_config_out()


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
