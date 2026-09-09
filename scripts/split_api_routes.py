#!/usr/bin/env python3
"""一次性脚本：把 api.py 拆成 api/ 下多个 router 模块。"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "apps" / "control-plane" / "autotest_control"
SRC = (ROOT / "api.py").read_text(encoding="utf-8")
lines = SRC.splitlines(keepends=True)

# 各段起止行（1-based，含装饰器行）
SECTIONS: dict[str, tuple[int, int]] = {
    "sites": (230, 500),
    "ai": (272, 316),
    "flows": (505, 669),
    "suites": (713, 775),
    "runs": (986, 1222),
    "onboarding": (1230, 1357),
    "recordings": (1363, 1692),
    "workers": (1698, 1999),
}

IMPORTS = """from __future__ import annotations

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

"""

REPLACEMENTS = [
    (r"\b_now\b", "now"),
    (r"\b_new_id\b", "new_id"),
    (r"\b_get_site\b", "get_site"),
    (r"\b_get_flow\b", "get_flow"),
    (r"\b_get_suite\b", "get_suite"),
    (r"\b_auth_worker\b", "auth_worker"),
    (r"\b_redact\b", "redact"),
    (r"\b_heal_out\b", "heal_out"),
    (r"\b_ai_config_out\b", "ai_config_out"),
    (r"\b_collect_heal_task\b", "collect_heal_task"),
    (r"\b_pending_heal_for_run\b", "pending_heal_for_run"),
    (r"\b_form_login_locators\b", "form_login_locators"),
    (r"\b_locators_from_inspect\b", "locators_from_inspect"),
    (r"\b_copy_project_form_locators\b", "copy_project_form_locators"),
    (r"\b_flow_out\b", "flow_out"),
    (r"\b_project_flow_map\b", "project_flow_map"),
    (r"\b_suite_out\b", "suite_out"),
    (r"\b_validated_members\b", "validated_members"),
    (r"\b_enqueue_chain\b", "enqueue_chain"),
    (r"\b_queue_replay\b", "queue_replay"),
    (r"\b_batch_out\b", "batch_out"),
    (r"\b_advance_batch\b", "advance_batch"),
    (r"\b_run_out\b", "run_out"),
    (r"\b_purge_run_files\b", "purge_run_files"),
    (r"\b_delete_run_row\b", "delete_run_row"),
    (r"\b_ACTIVE_RUN_STATUS\b", "ACTIVE_RUN_STATUS"),
    (r"\b_snapshot_safe\b", "snapshot_safe"),
    (r"\b_snapshot\b", "snapshot"),
    (r"\b_sse\b", "sse"),
    (r"\b_get_compilation\b", "get_compilation"),
    (r"\b_compilation_out\b", "compilation_out"),
    (r"\b_prepare_recorded_step\b", "prepare_recorded_step"),
    (r"\b_worker_out\b", "worker_out"),
    (r"\b_reclaim_expired\b", "reclaim_expired"),
    (r"\b_try_claim\b", "try_claim"),
    (r"\b_lease_lock\b", "lease_lock"),
    (r"\b_MAX_COMPILE_ATTEMPTS\b", "MAX_COMPILE_ATTEMPTS"),
    (r"\b_FORM_LOCATOR_KEYS\b", "FORM_LOCATOR_KEYS"),
    (r"\b_ALLOWED_TRANSITIONS\b", "ALLOWED_TRANSITIONS"),
    (r"\b_INSPECT_PLACEHOLDER\b", "INSPECT_PLACEHOLDER"),
]

# 仅保留各段内的路由与局部常量，去掉 helper 定义
HELPER_DEF_PATTERNS = [
    r"^def _get_site\b",
    r"^def _form_login_locators\b",
    r"^def _locators_from_inspect\b",
    r"^def _copy_project_form_locators\b",
    r"^def _flow_out\b",
    r"^def _get_flow\b",
    r"^def _suite_out\b",
    r"^def _load_member_flows\b",
    r"^def _validated_members\b",
    r"^def _get_suite\b",
    r"^def _site_ref\b",
    r"^def _project_flow_map\b",
    r"^def _build_job\b",
    r"^def _build_chain_job\b",
    r"^def _enqueue_chain\b",
    r"^def _queue_replay\b",
    r"^def _batch_out\b",
    r"^def _finish_batch\b",
    r"^def _advance_batch\b",
    r"^def _run_out\b",
    r"^def _purge_run_files\b",
    r"^def _delete_run_row\b",
    r"^def _snapshot\b",
    r"^def _snapshot_safe\b",
    r"^def _sse\b",
    r"^def _get_compilation\b",
    r"^def _compilation_out\b",
    r"^def _prepare_recorded_step\b",
    r"^def _worker_out\b",
    r"^def _reclaim_expired\b",
    r"^def _try_claim\b",
    r"^class Scope\b",
    r"^def get_scope\b",
    r"^def _now\b",
    r"^def _new_id\b",
    r"^def _auth_worker\b",
    r"^def _redact\b",
    r"^def _heal_out\b",
    r"^def _pending_heal_for_run\b",
    r"^def _ai_config_out\b",
    r"^def _collect_heal_task\b",
]


def extract(start: int, end: int) -> str:
    chunk = "".join(lines[start - 1 : end])
    for pattern in HELPER_DEF_PATTERNS:
        chunk = re.sub(
            rf"(?m)^{pattern}.*?(?=\n(?:@router\.|def _|def [a-z]|# -|$))",
            "",
            chunk,
            flags=re.DOTALL,
        )
    # 去掉段注释
    chunk = re.sub(r"^# -{2,}.*\n", "", chunk, flags=re.MULTILINE)
    for old, new in REPLACEMENTS:
        chunk = re.sub(old, new, chunk)
    return chunk


def write_module(name: str, body: str) -> None:
    out = ROOT / "api" / f"{name}.py"
    out.write_text(IMPORTS + body, encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT.parents[1])} ({len(body.splitlines())} lines)")


def main() -> None:
    (ROOT / "api").mkdir(exist_ok=True)

    # sites: 230-270, 319-500 (skip ai 272-316)
    sites_body = extract(230, 270) + extract(319, 500)
    write_module("sites", sites_body)

    write_module("ai", extract(272, 316))

    # flows: skip helper defs inside
    flows_body = extract(505, 669)
    # inject module-level constants
    flows_body = "_ALLOWED_TRANSITIONS = {\n    (\"draft\", \"reviewed\"),\n    (\"reviewed\", \"golden\"),\n    (\"golden\", \"active\"),\n    (\"reviewed\", \"draft\"),\n    (\"golden\", \"draft\"),\n    (\"active\", \"draft\"),\n}\n\n" + flows_body.replace("_ALLOWED_TRANSITIONS", "ALLOWED_TRANSITIONS")
    write_module("flows", flows_body)

    write_module("suites", extract(713, 775))

    runs_body = extract(986, 1222)
    write_module("runs", runs_body)

    onboarding_body = '_INSPECT_PLACEHOLDER = "-"\n\n' + extract(1230, 1357).replace("_INSPECT_PLACEHOLDER", "INSPECT_PLACEHOLDER")
    write_module("onboarding", onboarding_body)

    write_module("recordings", extract(1363, 1692))

    write_module("workers", extract(1698, 1999))

    router_py = '''"""聚合各域 router。"""
from __future__ import annotations

from fastapi import APIRouter

from autotest_control.api import ai, flows, onboarding, recordings, runs, sites, suites, workers

router = APIRouter(prefix="/api/v1")
router.include_router(sites.router)
router.include_router(ai.router)
router.include_router(flows.router)
router.include_router(suites.router)
router.include_router(runs.router)
router.include_router(onboarding.router)
router.include_router(recordings.router)
router.include_router(workers.router)
'''
    (ROOT / "api" / "router.py").write_text(router_py, encoding="utf-8")
    (ROOT / "api" / "__init__.py").write_text(
        'from autotest_control.api.router import router\n\n__all__ = ["router"]\n',
        encoding="utf-8",
    )
    print("done")


if __name__ == "__main__":
    main()
