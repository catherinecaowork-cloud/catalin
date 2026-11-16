"""一次运行的执行过程。

事件在这里产生：步骤开始、步骤结束、探针告警、断言结论。
平台不需要解析日志文本就能知道跑到哪、成没成。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from autotest_executor.auth import (
    UnsupportedLoginChallenge,
    build_material,
    form_login_steps,
)
from autotest_executor.browser.actions import ActionRunner, StepOutcome
from autotest_executor.browser.session import BrowserSession, HeadedNotSupported
from autotest_executor.client import ControlPlaneClient
from autotest_executor.data_strategy import DataStrategyError, DataStrategyResolver
from autotest_protocol import Job, Step, new_event


class RunExecutor:
    def __init__(self, client: ControlPlaneClient, job: Job, workspace: Path) -> None:
        self.client = client
        self.job = job
        self.artifacts_dir = workspace / job.run_id
        self.session = BrowserSession(job, self.artifacts_dir)
        self.step_results: list[dict[str, Any]] = []
        self.drifts: list[str] = []
        self.locator_updates: list[dict[str, Any]] = []
        self._capture_warned = False
        self._data = DataStrategyResolver(
            self._initial_variables(),
            base_url=(
                self.job.environment.base_url
                if self.job.environment is not None
                else self.job.site.base_url
            ),
        )
        self._action_runner: ActionRunner | None = None

    def _initial_variables(self) -> dict[str, str]:
        merged = dict(self.job.variables or {})
        if self.job.environment is not None and self.job.environment.data:
            # 环境数据档垫底；Job.variables（含运行入参）优先
            base = {str(k): str(v) for k, v in self.job.environment.data.items()}
            base.update(merged)
            return base
        return merged

    # ------------------------------------------------------------ 主流程

    def execute(self) -> str:
        started = time.monotonic()
        flow = self.job.flow
        base_url = (
            self.job.environment.base_url
            if self.job.environment is not None
            else self.job.site.base_url
        )
        self._emit(
            "run.start",
            run_id=self.job.run_id,
            flow=flow.name if flow else None,
            headless=self.job.options.headless,
            dry_run=self.job.options.dry_run,
            base_url=base_url,
            environment=self.job.environment.name if self.job.environment else None,
        )

        status = "passed"
        try:
            # 数据策略按步解析（from_step / ensure 依赖前序与页面），登录步骤仍可先展开
            material = self._resolve_auth()
            self.session.start(cookies=material.cookies, extra_headers=material.headers)
            self._data.bind_page(self.session.page)
            self._data.set_create_steps_handler(self._run_create_steps)

            steps: list[Step] = []
            if material.form is not None:
                steps.extend(form_login_steps(material.form, base_url))
            if flow is not None:
                steps.extend(flow.steps)

            runner = ActionRunner(self.session)
            self._action_runner = runner
            try:
                for index, step in enumerate(steps, start=1):
                    outcome = self._run_step(runner, step, index, len(steps))
                    if outcome.status == "failed":
                        status = "failed"
                        break
            finally:
                self.locator_updates = runner.locator_memory.updates
                self._action_runner = None
                self._data.bind_page(None)
                self._data.close()
        except HeadedNotSupported as exc:
            # 明确失败，不静默降级成无头
            self._emit("log", level="error", message=str(exc), reason="headed_not_supported")
            status = "error"
        except UnsupportedLoginChallenge as exc:
            self._emit("log", level="error", message=str(exc), reason="login_unsupported")
            status = "error"
        except Exception as exc:  # noqa: BLE001
            self._emit("log", level="error", message=f"{type(exc).__name__}: {exc}")
            status = "error"

        duration = time.monotonic() - started
        self._finish(status, duration)
        return status

    def _run_create_steps(
        self, raw_steps: list[dict[str, Any]], resolver: DataStrategyResolver
    ) -> None:
        """ensure 内联创建子流程：逐步解析并执行，失败则抛 DataStrategyError。"""
        runner = self._action_runner
        if runner is None:
            raise DataStrategyError(
                "ensure create_steps 需要已启动的 ActionRunner",
                kind="invalid",
                strategy="ensure",
            )
        for raw in raw_steps:
            step = Step.model_validate(raw)
            resolved = resolver.resolve_step_fields(step)
            self._emit(
                "log",
                level="info",
                message=f"ensure 创建子步骤：{resolved.display()}",
                step_id=resolved.id,
            )
            outcome = runner.run(resolved)
            if outcome.status == "failed":
                raise DataStrategyError(
                    f"ensure 创建子步骤失败：{outcome.message}",
                    kind="not_found",
                    strategy="ensure",
                    detail={
                        "create_step_id": step.id,
                        "create_action": step.action,
                        "message": outcome.message,
                    },
                )
            resolver.record_step_output(step.id, outcome.data)

    # ------------------------------------------------------------ 步骤

    def _run_step(self, runner: ActionRunner, step: Step, index: int, total: int) -> StepOutcome:
        self._emit(
            "step.start",
            step_id=step.id,
            action=step.action,
            label=step.display(),
            index=index,
            total=total,
        )
        started = time.monotonic()
        try:
            resolved = self._data.resolve_step_fields(step)
        except DataStrategyError as exc:
            elapsed = time.monotonic() - started
            outcome = StepOutcome(
                step.id,
                step.action,
                "failed",
                exc.message,
                data=exc.as_failure_data(),
            )
            self._finish_step(step, outcome, elapsed, screenshot_url=None)
            return outcome

        outcome = runner.run(resolved)
        elapsed = time.monotonic() - started
        if outcome.status != "failed":
            self._data.record_step_output(step.id, outcome.data)

        watch_toast = outcome.status != "skipped" and step.action in {
            "click",
            "choose",
            "fill",
            "select",
            "upload",
        }
        if watch_toast:
            try:
                self.session.page.wait_for_timeout(400)
            except Exception:
                pass

        screenshot_url = None
        if self.job.options.screenshot_each_step and outcome.status != "skipped":
            screenshot_url = self._capture(f"{index:02d}_{step.id}")

        if watch_toast:
            self._attach_page_toasts(outcome)

        if outcome.drift:
            self.drifts.append(outcome.drift)
            self._emit("probe.alert", kind="locator_drift", step_id=step.id, message=outcome.drift)

        if step.action in {"pageHealth"} or step.assert_kind == "no_page_error":
            counts = outcome.data.get("counts", {})
            if any(counts.values()):
                self._emit(
                    "probe.alert",
                    kind="page_error",
                    step_id=step.id,
                    counts=counts,
                    js_errors=outcome.data.get("jsErrors", []),
                    request_errors=outcome.data.get("requestErrors", []),
                )

        if step.action == "assert":
            self._emit(
                "assert",
                step_id=step.id,
                kind=step.assert_kind,
                status=outcome.status,
                message=outcome.message,
                detail=outcome.data,
            )

        self._finish_step(step, outcome, elapsed, screenshot_url=screenshot_url)
        return outcome

    def _finish_step(
        self,
        step: Step,
        outcome: StepOutcome,
        elapsed: float,
        *,
        screenshot_url: str | None,
    ) -> None:
        self._emit(
            "step.end",
            step_id=step.id,
            action=step.action,
            label=step.display(),
            status=outcome.status,
            message=outcome.message,
            data=outcome.data,
            drift=outcome.drift,
            elapsed_ms=int(elapsed * 1000),
            screenshot=screenshot_url,
        )
        self.step_results.append(
            {
                "step_id": step.id,
                "action": step.action,
                "label": step.display(),
                "status": outcome.status,
                "message": outcome.message,
                "elapsed_ms": int(elapsed * 1000),
                "drift": outcome.drift,
                # 失败分类：没找到 / 找到但点不到 / 点了没生效。只写在 message 里
                # 就没法按类聚合，报告只能一句「偶发失败」。
                "failure": outcome.data.get("failure"),
                "failure_kind": outcome.data.get("failure_kind"),
                "environmental": outcome.data.get("environmental"),
                "strategy": outcome.data.get("strategy"),
            }
        )

    def _attach_page_toasts(self, outcome: StepOutcome) -> None:
        """点完后扫右上角失败弹出，把原文挂到这一步。成功提示忽略。"""
        try:
            errors = self.session.consume_ui_errors()
        except Exception:
            errors = []
        texts: list[str] = []
        for item in errors:
            message = str((item or {}).get("message") or "").strip()
            if message and message not in texts:
                texts.append(message)
        if not texts:
            return
        joined = "；".join(texts)
        self._emit("probe.alert", kind="ui_error", message=joined, step_id=outcome.step_id)
        outcome.data = dict(outcome.data or {})
        outcome.data["uiErrors"] = texts
        prefix = "页面报错：" + joined
        if outcome.status == "passed":
            outcome.status = "failed"
            outcome.message = prefix
        elif outcome.message:
            outcome.message = f"{outcome.message}；{prefix}"
        else:
            outcome.message = prefix

    def _capture(self, name: str) -> str | None:
        path = self.artifacts_dir / f"{name}.png"
        try:
            self.artifacts_dir.mkdir(parents=True, exist_ok=True)
            self.session.page.screenshot(path=str(path), full_page=False)
        except Exception as exc:
            self._warn_capture_once(f"截图失败 {name}: {exc}")
            return None
        url = self.client.upload_artifact(self.job.run_id, f"{name}.png", path)
        if url is None:
            self._warn_capture_once(f"上传截图失败 {name}")
        return url

    def _warn_capture_once(self, message: str) -> None:
        if self._capture_warned:
            return
        self._capture_warned = True
        self._emit("log", level="warn", message=message)

    # ------------------------------------------------------------ 收尾

    def _resolve_auth(self):
        payload = None
        if self.job.auth.type != "none" and self.job.auth.ref:
            material = self.client.credential_material(self.job.auth.ref)
            if material is None:
                raise RuntimeError("无法获取凭证，登录失败")
            payload = material.get("payload")
        base_url = (
            self.job.environment.base_url
            if self.job.environment is not None
            else self.job.site.base_url
        )
        return build_material(self.job.auth, payload, base_url)

    def _finish(self, status: str, duration: float) -> None:
        keep_evidence = status != "passed"
        produced: dict[str, str] = {}
        try:
            produced = self.session.stop(keep_trace=keep_evidence)
        except Exception:
            produced = {}

        artifacts: dict[str, str] = {}
        for kind, local_path in produced.items():
            path = Path(local_path)
            if path.exists():
                url = self.client.upload_artifact(self.job.run_id, f"{kind}{path.suffix}", path)
                if url:
                    artifacts[kind] = url

        passed = sum(1 for r in self.step_results if r["status"] == "passed")
        failed = sum(1 for r in self.step_results if r["status"] == "failed")
        skipped = sum(1 for r in self.step_results if r["status"] == "skipped")
        summary = {
            "steps": self.step_results,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "drifts": self.drifts,
            "locator_updates": self.locator_updates,
            "artifacts": artifacts,
        }
        self._emit("run.end", status=status, passed=passed, failed=failed, skipped=skipped)
        self.client.complete(self.job.run_id, status, summary, duration)

    def _emit(self, type_: str, **data: Any) -> None:
        self.client.post_events(self.job.run_id, [new_event(type_, **data)])  # type: ignore[arg-type]
