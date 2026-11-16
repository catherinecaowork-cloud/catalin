from __future__ import annotations

from datetime import timezone

from autotest_control.models import (
    Batch,
    Flow,
    HealTask,
    RecordingCompilation,
    Run,
    Suite,
    Worker,
)
from autotest_control.schemas import (
    AIConfigOut,
    BatchOut,
    CompilationOut,
    FlowOut,
    HealTaskOut,
    RunOut,
    SuiteOut,
    WorkerOut,
)
from autotest_control.settings import infer_api_format, settings

from autotest_control.deps import MAX_COMPILE_ATTEMPTS, now


def heal_out(task: HealTask) -> HealTaskOut:
    return HealTaskOut(
        id=task.id,
        flow_id=task.flow_id,
        run_id=task.run_id,
        status=task.status,
        instruction=task.instruction,
        patches=task.patches or [],
        applied_log=task.applied_log or [],
    )


def ai_config_out() -> AIConfigOut:
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


def flow_out(flow: Flow) -> FlowOut:
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
        setup_flow_ids=list(getattr(flow, "setup_flow_ids", None) or []),
        imported_from=getattr(flow, "imported_from", None),
        page_widget_model=getattr(flow, "page_widget_model", None),
    )


def suite_out(suite: Suite) -> SuiteOut:
    return SuiteOut(
        id=suite.id,
        site_id=suite.site_id,
        name=suite.name,
        flow_ids=list(suite.flow_ids or []),
        created_at=suite.created_at,
    )


def batch_out(batch: Batch) -> BatchOut:
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


def run_out(run: Run) -> RunOut:
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


def worker_out(worker: Worker, *, include_token: bool = False) -> WorkerOut:
    heartbeat = worker.last_heartbeat_at
    if heartbeat.tzinfo is None:
        heartbeat = heartbeat.replace(tzinfo=timezone.utc)
    online = (now() - heartbeat).total_seconds() < settings.heartbeat_offline_seconds
    return WorkerOut(
        id=worker.id,
        name=worker.name,
        # 列表接口不回显 token；仅注册响应带回一次
        token=worker.token if include_token else "",
        labels=worker.labels,
        platform=worker.platform,
        online=online,
        last_heartbeat_at=worker.last_heartbeat_at,
    )


def compilation_out(row: RecordingCompilation) -> CompilationOut:
    sample = row.deterministic_steps or []
    observer = row.observer_steps
    compiled = row.compiled_steps
    if row.status == "passed" and observer:
        steps = observer
    elif compiled:
        steps = compiled
    else:
        steps = sample
    return CompilationOut(
        id=row.id,
        recording_run_id=row.recording_run_id,
        status=row.status,
        attempt=row.attempt,
        max_attempts=MAX_COMPILE_ATTEMPTS,
        steps=steps,
        sample_steps=sample,
        observer_steps=observer,
        compile_mode=getattr(row, "compile_mode", None) or "observer",
        notes=row.compile_notes or [],
        validation_run_id=row.validation_run_id,
        usage=row.usage or {},
        error=row.error,
        verified=row.status == "passed",
    )
