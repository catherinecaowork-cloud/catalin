"""对外请求 / 响应模型。

凭证只进不出：创建时收明文，读取时只回类型与更新时间。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from autotest_protocol import Step, Target


class SiteCreate(BaseModel):
    name: str
    base_url: str
    env: str = "test"
    adapter: str = "generic"
    probe_error_url_patterns: list[str] = []


class SiteUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    env: str | None = None


class SiteOut(BaseModel):
    id: str
    name: str
    base_url: str
    env: str
    adapter: str
    probe_error_url_patterns: list[str]


class EnvironmentCreate(BaseModel):
    name: str
    base_url: str
    credential_id: str | None = None
    labels: list[str] = []
    data: dict[str, str] = {}


class EnvironmentUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    credential_id: str | None = None
    labels: list[str] | None = None
    data: dict[str, str] | None = None


class EnvironmentOut(BaseModel):
    id: str
    site_id: str
    name: str
    base_url: str
    credential_id: str | None = None
    labels: list[str] = []
    data: dict[str, str] = {}
    created_at: datetime


class CredentialCreate(BaseModel):
    name: str
    type: Literal["cookie", "token", "form"]
    # cookie: {"cookie": "a=1; b=2"}
    # token:  {"header": "Authorization", "value": "Bearer ..."}
    # form:   {"username": "...", "password": "...", "login_path": "/login", ...}
    payload: dict[str, Any]


class SiteFormCredentialIn(BaseModel):
    """给已有站点补表单登录：账号密码 + 识别结果（或沿用同项目定位）。"""

    username: str
    password: str
    login_path: str = "/"
    success_text: str | None = None
    inspect_run_id: str | None = None


class CredentialOut(BaseModel):
    """不含 payload——凭证不可读回，只能覆盖。"""

    id: str
    name: str
    type: str
    updated_at: datetime


class FlowCreate(BaseModel):
    site_id: str
    name: str
    steps: list[Step]
    auth_type: Literal["none", "cookie", "token", "form"] = "none"
    credential_id: str | None = None


class FlowOut(BaseModel):
    id: str
    site_id: str
    name: str
    version: int
    status: str
    steps: list[dict[str, Any]]
    auth_type: str
    has_baseline: bool
    setup_flow_id: str | None = None
    setup_flow_ids: list[str] = []
    imported_from: str | None = None
    page_widget_model: dict[str, Any] | None = None


class PageWidgetModelOut(BaseModel):
    site_id: str | None = None
    flow_id: str | None = None
    recording_run_id: str | None = None
    entries: list[dict[str, Any]] = []
    snapshots_seen: int = 0


class FlowSetupUpdate(BaseModel):
    setup_flow_id: str | None = None
    setup_flow_ids: list[str] | None = None


class FlowUpdate(BaseModel):
    name: str


class FlowImportIn(BaseModel):
    flow_ids: list[str]


class FlowImportOut(BaseModel):
    imported: list[str]
    skipped: list[str]


class FlowStatusUpdate(BaseModel):
    status: Literal["draft", "reviewed", "golden", "active"]
    # 进入 golden 需要指定作为基线的运行
    baseline_run_id: str | None = None


class SuiteCreate(BaseModel):
    site_id: str
    name: str
    flow_ids: list[str]


class SuiteUpdate(BaseModel):
    name: str | None = None
    flow_ids: list[str] | None = None


class SuiteOut(BaseModel):
    id: str
    site_id: str
    name: str
    flow_ids: list[str]
    created_at: datetime


class BatchCreate(BaseModel):
    site_id: str
    flow_ids: list[str] | None = None
    suite_id: str | None = None
    name: str | None = None
    environment_id: str | None = None
    headless: bool = True
    dry_run: bool = False
    variables: dict[str, str] = {}


class BatchItemOut(BaseModel):
    flow_id: str
    run_id: str | None = None
    status: str


class BatchOut(BaseModel):
    id: str
    site_id: str
    suite_id: str | None
    name: str
    status: str
    flow_ids: list[str]
    current_index: int
    current_run_id: str | None
    items: list[BatchItemOut]
    created_at: datetime
    finished_at: datetime | None


class RunCreate(BaseModel):
    flow_id: str
    site_id: str | None = None
    # 同一系统下选具体环境；省略则用站点默认 URL / 无环境数据档
    environment_id: str | None = None
    headless: bool = True
    dry_run: bool = False
    variables: dict[str, str] = {}


class RunOut(BaseModel):
    id: str
    site_id: str
    flow_id: str | None
    flow_version: int | None
    kind: str = "replay"
    status: str
    worker_id: str | None
    summary: dict[str, Any] | None
    duration_seconds: float | None
    created_at: datetime
    finished_at: datetime | None


class RunPurgeIn(BaseModel):
    ids: list[str]


class InspectIn(BaseModel):
    login_url: str


class OnboardCommitIn(BaseModel):
    inspect_run_id: str
    site_name: str
    username: str
    password: str
    success_text: str | None = None


class WorkerRegister(BaseModel):
    name: str
    labels: list[str] = []
    platform: str = ""
    project_id: str = "default"
    # 与控制面 ATP_WORKER_REGISTER_CODE 对齐；任意 Worker 不能无码自助入队
    register_code: str = ""


class WorkerOut(BaseModel):
    id: str
    name: str
    token: str
    labels: list[str]
    platform: str
    online: bool
    last_heartbeat_at: datetime


class HeartbeatIn(BaseModel):
    worker_id: str
    token: str
    labels: list[str] | None = None


class EventIn(BaseModel):
    type: str
    ts: datetime | None = None
    data: dict[str, Any] = {}


class EventsIn(BaseModel):
    worker_id: str
    token: str
    events: list[EventIn]


class CompleteIn(BaseModel):
    worker_id: str
    token: str
    status: Literal["passed", "failed", "error"]
    summary: dict[str, Any] = {}
    duration_seconds: float | None = None


class RecordingCreate(BaseModel):
    site_id: str
    credential_id: str | None = None
    start_path: str = ""
    intent: str


class RecordingSave(BaseModel):
    name: str
    steps: list[dict[str, Any]]
    allow_unverified: bool = False


class CompilationOut(BaseModel):
    id: str
    recording_run_id: str
    status: str
    attempt: int
    max_attempts: int = 3
    steps: list[dict[str, Any]]
    sample_steps: list[dict[str, Any]] = []
    observer_steps: list[dict[str, Any]] | None = None
    compile_mode: str = "observer"
    notes: list[str]
    validation_run_id: str | None = None
    usage: dict[str, Any] = {}
    error: str | None = None
    verified: bool = False


class CompilationRetry(BaseModel):
    intent: str | None = None
    compile_mode: Literal["observer", "polish"] | None = None


class AIConfigOut(BaseModel):
    configured: bool
    base_url: str
    model: str
    vision_enabled: bool
    has_token: bool
    env_overrides: list[str] = []
    api_format: str = "anthropic"
    token_hint: str = ""


class AIConfigIn(BaseModel):
    base_url: str
    auth_token: str | None = None
    model: str
    vision_enabled: bool = False


class HealTaskOut(BaseModel):
    id: str
    flow_id: str
    run_id: str
    status: str
    instruction: str
    patches: list[dict[str, Any]]
    applied_log: list[str] = []


class UiObjectCreate(BaseModel):
    key: str
    name: str
    target: Target


class UiObjectUpdate(BaseModel):
    key: str | None = None
    name: str | None = None
    target: Target | None = None


class UiObjectOut(BaseModel):
    id: str
    site_id: str
    key: str
    name: str
    target: dict[str, Any]
    created_at: datetime
    updated_at: datetime
