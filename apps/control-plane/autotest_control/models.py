"""数据模型（P0 切片最小集）。

租户与项目字段现在就带上：隔离规则一旦后补，早期数据就得迁移。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Site(Base):
    """被测系统（System）。同一系统下可挂多个 Environment。"""

    __tablename__ = "site"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(200))
    # 兼容旧数据：默认/主环境的 URL；有 Environment 行时以具体环境为准
    base_url: Mapped[str] = mapped_column(String(500))
    env: Mapped[str] = mapped_column(String(50), default="test")
    adapter: Mapped[str] = mapped_column(String(50), default="generic")
    probe_error_url_patterns: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Environment(Base):
    """同一 Site/System 下的部署环境：URL、凭证引用、标签与数据档。

    流程绑定系统，不绑定某一环境的死 URL / 死单号；跑的时候再选 Environment。
    """

    __tablename__ = "environment"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    base_url: Mapped[str] = mapped_column(String(500))
    credential_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    labels: Mapped[list[str]] = mapped_column(JSON, default=list)
    # 数据档：username / order_no 等，供 DataStrategy kind=env 解析
    data: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Credential(Base):
    __tablename__ = "credential"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    # cookie / token / form
    type: Mapped[str] = mapped_column(String(20))
    # 密文。任何读接口都不返回它。
    payload_encrypted: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Flow(Base):
    __tablename__ = "flow"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    version: Mapped[int] = mapped_column(Integer, default=1)
    # draft / reviewed / golden / active
    status: Mapped[str] = mapped_column(String(20), default="draft")
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    auth_type: Mapped[str] = mapped_column(String(20), default="none")
    credential_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # 可选前置：跑本条前先跑那条（同站点）。删除款式前先新建，就是这个。
    setup_flow_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # 多条前置，按顺序执行。非空时优先于 setup_flow_id。
    setup_flow_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    # 从其他环境导入时记下源环境名，列表上区分「本环境录的」和「导进来的」。
    imported_from: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # 黄金跑固化的基线（截图与关键数据快照）
    baseline: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # P1.2 观察者：字段/组件认识，随流程保存
    page_widget_model: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Worker(Base):
    __tablename__ = "worker"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(200))
    token: Mapped[str] = mapped_column(String(64), index=True)
    # 能力标签：可否开窗、操作系统等
    labels: Mapped[list[str]] = mapped_column(JSON, default=list)
    platform: Mapped[str] = mapped_column(String(50), default="")
    last_heartbeat_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    registered_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Run(Base):
    __tablename__ = "run"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    site_id: Mapped[str] = mapped_column(String(36), index=True)
    flow_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    flow_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str] = mapped_column(String(20), default="replay")
    # queued / leased / running / passed / failed / error
    status: Mapped[str] = mapped_column(String(20), default="queued")
    job: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    required_labels: Mapped[list[str]] = mapped_column(JSON, default=list)
    worker_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 控制台「结束录制」置位；执行器轮询到后收工。create_all 不会改旧表，
    # 启动时 db.init_db 会补这一列。
    stop_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    pause_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    batch_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    batch_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 录制过程中合并的页面认识（保存流程时写入 flow.page_widget_model）
    observation_model: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class RunEvent(Base):
    __tablename__ = "run_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(40))
    ts: Mapped[datetime] = mapped_column(DateTime, default=_now)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class RecordingCompilation(Base):
    """一次录制对应的 AI 编译与回放验证状态。

    编译状态落库而不是只放在线程内，控制面重启后可以继续处理。
    """

    __tablename__ = "recording_compilation"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    recording_run_id: Mapped[str] = mapped_column(
        ForeignKey("run.id"), unique=True, index=True
    )
    # queued / compiling / validating / passed / manual_validation / fallback / error
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    intent: Mapped[str] = mapped_column(String(1000))
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    deterministic_steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    observer_steps: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    # observer=观察者编写；polish=仅润色；fallback=回退样例
    compile_mode: Mapped[str] = mapped_column(String(20), default="observer")
    compiled_steps: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    compile_notes: Mapped[list[str]] = mapped_column(JSON, default=list)
    validation_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    failure_context: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    usage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class UiObject(Base):
    """站点对象库中的一个控件定义。

    步骤通过 object_id 引用这里的 id；改 target 后，引用它的流程下次回放一起生效。
    """

    __tablename__ = "ui_object"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.id"), index=True)
    # 站点内可读键，如 login.submit；与 id 并存，步骤引用仍用 id。
    key: Mapped[str] = mapped_column(String(200))
    name: Mapped[str] = mapped_column(String(200))
    target: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Suite(Base):
    """同一站点下有序的已确认用例清单。"""

    __tablename__ = "suite"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    site_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(200))
    flow_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Batch(Base):
    """一次勾选或套件执行。只入队当前条，通过后再入队下一条。"""

    __tablename__ = "batch"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    site_id: Mapped[str] = mapped_column(String(36), index=True)
    suite_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    environment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    name: Mapped[str] = mapped_column(String(200), default="勾选运行")
    flow_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    current_index: Mapped[int] = mapped_column(Integer, default=0)
    current_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # queued / running / passed / failed
    status: Mapped[str] = mapped_column(String(20), default="queued")
    headless: Mapped[bool] = mapped_column(Boolean, default=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False)
    variables: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class HealTask(Base):
    """AI 监督者下发给执行者的脚本修补任务。用户确认后才写回流程。"""

    __tablename__ = "heal_task"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    flow_id: Mapped[str] = mapped_column(String(36), index=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    # pending / applied / rejected
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    instruction: Mapped[str] = mapped_column(Text, default="")
    patches: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    applied_log: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class FailureHealTask(Base):
    """回放失败后的 AI/fixture 修复提案。默认只提案，人工确认后才写回。"""

    __tablename__ = "failure_heal_task"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    flow_id: Mapped[str] = mapped_column(String(36), index=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    site_id: Mapped[str] = mapped_column(String(36), index=True)
    step_id: Mapped[str] = mapped_column(String(100), default="")
    # proposed（dry-run）/ pending / applied / rejected / failed
    status: Mapped[str] = mapped_column(String(20), default="proposed", index=True)
    error_class: Mapped[str] = mapped_column(String(40), default="uncertain")
    requires_human_confirm: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(String(20), default="fixture")  # ai | fixture
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    patches: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    notes: Mapped[list[str]] = mapped_column(JSON, default=list)
    usage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # 审计：每条含 proposed / applied / status
    applied_log: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
