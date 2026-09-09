"""控制面内的 AI 编译协调器。

它只调用模型、写状态和派发验证任务；浏览器仍由远端执行器运行。
当前部署是单进程 SQLite，因此用一个持久化扫描线程即可。以后切换多副本时，
可把同一状态机搬到正式任务队列。
"""

from __future__ import annotations

import base64
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select

from autotest_control.ai import AICompiler, AIConfigurationError, ImageInput
from autotest_control.db import session_scope
from autotest_control.hub import hub
from autotest_control.models import RecordingCompilation, Run, Site
from autotest_control.settings import settings
from autotest_protocol import AuthRef, Flow as FlowDSL, Job, RunOptions, SiteRef, Step
from autotest_protocol.job import ProbeConfig

_MAX_ATTEMPTS = 3
_ACTIVE_ENVIRONMENTS = {"test", "dev", "development"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CompilationWorker:
    def __init__(self, interval_seconds: float = 1.0) -> None:
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        # 进程可能在模型请求中退出；没有外部副作用的 compiling 可以安全重领。
        with session_scope() as session:
            stale = session.scalars(
                select(RecordingCompilation).where(
                    RecordingCompilation.status == "compiling"
                )
            ).all()
            for row in stale:
                row.status = "queued"
                row.updated_at = _now()
        self._thread = threading.Thread(
            target=self._run, name="recording-ai-compiler", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._thread = None

    def run_once(self) -> bool:
        """处理一个可推进状态，供自测和线程循环复用。"""
        with session_scope() as session:
            row = session.scalar(
                select(RecordingCompilation)
                .where(RecordingCompilation.status == "queued")
                .order_by(RecordingCompilation.created_at)
            )
            if row is None:
                waiting = session.scalars(
                    select(RecordingCompilation)
                    .where(RecordingCompilation.status == "validating")
                    .order_by(RecordingCompilation.created_at)
                ).all()
                row = next(
                    (
                        item
                        for item in waiting
                        if item.validation_run_id
                        and (session.get(Run, item.validation_run_id) is not None)
                        and session.get(Run, item.validation_run_id).status
                        in {"passed", "failed", "error"}
                    ),
                    None,
                )
            if row is None:
                return False
            row_id = row.id
            status = row.status
            if status == "queued":
                row.status = "compiling"
                row.attempt += 1
                row.error = None
                row.updated_at = _now()
        if status == "queued":
            self._compile(row_id)
        else:
            self._advance_validation(row_id)
        return True

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                worked = self.run_once()
            except Exception as exc:
                # 单条坏数据不能杀掉后台协调器；下一轮仍能推进其他任务。
                self._recover_compiling(f"{type(exc).__name__}: {exc}")
                worked = False
            self._stop.wait(0.05 if worked else self.interval_seconds)

    def _compile(self, row_id: str) -> None:
        with session_scope() as session:
            row = session.get(RecordingCompilation, row_id)
            if row is None or row.status != "compiling":
                return
            recording = session.get(Run, row.recording_run_id)
            if recording is None:
                self._finish_error(row, "原录制任务不存在")
                return
            summary = recording.summary or {}
            context = dict(summary.get("compiler_context") or {})
            if row.failure_context:
                context["previous_failure"] = row.failure_context
            source_steps = [Step.model_validate(item) for item in row.deterministic_steps]
            intent = row.intent
            attempt = row.attempt
            image = self._load_image(summary.get("screenshot"))

        try:
            settings.reload_ai(prefer_file=True)
            result = AICompiler().compile(
                source_steps,
                intent=intent,
                context=context,
                images=[image] if image is not None else None,
            )
            compiled = [
                step.model_dump(mode="json", exclude_none=True)
                for step in result.steps
            ]
            ai_notes = list(result.notes)
            usage = result.usage.model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001 - 失败要进入可见状态机
            with session_scope() as session:
                row = session.get(RecordingCompilation, row_id)
                if row is None:
                    return
                if isinstance(exc, AIConfigurationError):
                    row.error = "AI 未配置：请在顶栏「AI」填写网关地址、Token 和模型后再编译。"
                else:
                    row.error = f"{type(exc).__name__}: {exc}"
                row.failure_context = {"stage": "compile", "error": row.error}
                row.updated_at = _now()
                if attempt >= _MAX_ATTEMPTS or getattr(exc, "code", "") == "ai_configuration_missing":
                    self._fallback(row, row.error)
                else:
                    row.status = "queued"
            return

        with session_scope() as session:
            row = session.get(RecordingCompilation, row_id)
            recording = session.get(Run, row.recording_run_id) if row else None
            site = session.get(Site, recording.site_id) if recording else None
            if row is None or recording is None or site is None:
                return
            row.compiled_steps = compiled
            row.compile_notes = list(dict.fromkeys([*(row.compile_notes or []), *ai_notes]))
            row.usage = _sum_usage(row.usage or {}, usage)
            row.failure_context = None
            row.error = None
            row.updated_at = _now()
            if site.env.lower() not in _ACTIVE_ENVIRONMENTS:
                row.status = "manual_validation"
                row.error = f"环境 {site.env} 不允许自动执行写操作"
                return
            validation = self._new_validation_run(recording, site, row, compiled)
            session.add(validation)
            row.validation_run_id = validation.id
            row.status = "validating"
        # 允许远端 worker 尽快结束长轮询；即使跨线程通知失效，下一轮也会领取。
        try:
            hub.notify_new_job()
        except Exception:
            pass

    def _advance_validation(self, row_id: str) -> None:
        with session_scope() as session:
            row = session.get(RecordingCompilation, row_id)
            if row is None or row.status != "validating" or not row.validation_run_id:
                return
            run = session.get(Run, row.validation_run_id)
            if run is None:
                self._finish_error(row, "验证运行不存在")
                return
            if run.status not in {"passed", "failed", "error"}:
                return
            if run.status == "passed":
                row.status = "passed"
                row.error = None
                row.updated_at = _now()
                return
            row.failure_context = {
                "stage": "replay_validation",
                "status": run.status,
                "summary": _bounded_failure(run.summary or {}),
            }
            row.error = _failure_message(run.summary or {}, run.status)
            row.validation_run_id = None
            row.updated_at = _now()
            if row.attempt >= _MAX_ATTEMPTS:
                self._fallback(row, row.error)
            else:
                row.status = "queued"

    @staticmethod
    def _recover_compiling(reason: str) -> None:
        with session_scope() as session:
            rows = session.scalars(
                select(RecordingCompilation).where(
                    RecordingCompilation.status == "compiling"
                )
            ).all()
            for row in rows:
                row.error = reason[:2000]
                if row.attempt >= _MAX_ATTEMPTS:
                    CompilationWorker._fallback(row, row.error)
                else:
                    row.status = "queued"
                    row.updated_at = _now()

    @staticmethod
    def _new_validation_run(
        recording: Run,
        site: Site,
        compilation: RecordingCompilation,
        steps: list[dict[str, Any]],
    ) -> Run:
        job_data = recording.job or {}
        auth = AuthRef.model_validate(job_data.get("auth") or {})
        probe_raw = (job_data.get("site") or {}).get("probe") or {}
        probe = (
            ProbeConfig.model_validate(probe_raw)
            if isinstance(probe_raw, dict)
            else ProbeConfig()
        )
        run_id = _uuid()
        recorded_assert_ids = {
            item.get("id")
            for item in (compilation.deterministic_steps or [])
            if isinstance(item, dict) and item.get("action") == "assert"
        }
        replay_steps = [
            item
            for item in steps
            if not (
                isinstance(item, dict)
                and item.get("action") == "assert"
                and item.get("id") not in recorded_assert_ids
            )
        ]
        flow = FlowDSL(
            name=f"AI 验证：{compilation.intent[:80]}",
            steps=[Step.model_validate(item) for item in replay_steps],
        )
        job = Job(
            run_id=run_id,
            kind="replay",
            site=SiteRef(
                id=site.id,
                base_url=site.base_url,
                env=site.env,
                adapter=site.adapter,
                probe=probe,
            ),
            auth=auth,
            flow=flow,
            variables={},
            options=RunOptions(
                headless=True,
                dry_run=False,
                screenshot_each_step=True,
                video="on_failure",
                trace="on_failure",
            ),
        )
        return Run(
            id=run_id,
            tenant_id=recording.tenant_id,
            project_id=recording.project_id,
            site_id=recording.site_id,
            flow_id=None,
            flow_version=None,
            kind="replay",
            status="queued",
            job=job.model_dump(mode="json"),
            required_labels=[],
            stop_requested=False,
        )

    @staticmethod
    def _fallback(row: RecordingCompilation, reason: str) -> None:
        row.status = "fallback"
        row.compiled_steps = row.deterministic_steps
        row.validation_run_id = None
        row.error = reason
        note = f"AI 编译未通过，已回退确定性步骤：{reason}"
        row.compile_notes = list(dict.fromkeys([*(row.compile_notes or []), note]))
        row.updated_at = _now()

    @staticmethod
    def _finish_error(row: RecordingCompilation, reason: str) -> None:
        row.status = "error"
        row.error = reason
        row.updated_at = _now()

    @staticmethod
    def _load_image(url: Any) -> ImageInput | None:
        if not settings.anthropic_vision_enabled or not isinstance(url, str):
            return None
        marker = "/artifacts/"
        if marker not in url:
            return None
        relative = Path(url.split(marker, 1)[1].replace("\\", "/"))
        if relative.is_absolute() or ".." in relative.parts:
            return None
        path = settings.artifacts_dir.joinpath(*relative.parts)
        if not path.is_file() or path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            return None
        media = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }[path.suffix.lower()]
        return ImageInput(
            media_type=media,
            data=base64.b64encode(path.read_bytes()).decode("ascii"),
        )


def _uuid() -> str:
    import uuid

    return str(uuid.uuid4())


def _sum_usage(old: dict[str, Any], new: dict[str, Any]) -> dict[str, int]:
    return {
        "input_tokens": int(old.get("input_tokens") or 0)
        + int(new.get("input_tokens") or 0),
        "output_tokens": int(old.get("output_tokens") or 0)
        + int(new.get("output_tokens") or 0),
    }


def _bounded_failure(summary: dict[str, Any]) -> dict[str, Any]:
    steps = summary.get("steps") or []
    failed = [item for item in steps if isinstance(item, dict) and item.get("status") == "failed"]
    return {
        "failed_steps": failed[:3],
        "drifts": list(summary.get("drifts") or [])[:5],
        "artifacts": summary.get("artifacts") or {},
    }


def _failure_message(summary: dict[str, Any], status: str) -> str:
    for item in summary.get("steps") or []:
        if isinstance(item, dict) and item.get("status") == "failed":
            return str(item.get("message") or f"验证运行 {status}")[:1000]
    return f"验证运行 {status}"


compilation_worker = CompilationWorker()
