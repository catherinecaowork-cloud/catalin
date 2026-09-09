"""录制任务：开窗让人操作一遍，事件编译成可回放步骤。

执行器不调用大模型；清洗仍是确定性规则。它只采集受限、脱敏的编译上下文，
由控制面在录制结束后决定是否调用 AI。完整 HAR 与智能等待仍不在本期范围。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from autotest_executor.auth import (
    UnsupportedLoginChallenge,
    build_material,
    form_login_steps,
)
from autotest_executor.browser.actions import ActionRunner, StepOutcome
from autotest_executor.browser.readiness import wait_for_app_ready
from autotest_executor.browser.session import BrowserSession, HeadedNotSupported
from autotest_executor.client import ControlPlaneClient
from autotest_executor.compiler import compile_events
from autotest_protocol import Job, Step, new_event

_BROWSER_DIR = Path(__file__).resolve().parent / "browser"
_LOCATOR_JS = (_BROWSER_DIR / "locator_candidates.js").read_text(encoding="utf-8")
_RECORDER_JS = (_BROWSER_DIR / "recorder.js").read_text(encoding="utf-8")

# 忘了点结束的窗口不能把执行器占死
_MAX_SECONDS = 30 * 60
_MAX_JSON_RESPONSES = 30
_MAX_RESPONSE_BODY_BYTES = 256 * 1024
_MAX_PREVIEW_BYTES = 2 * 1024
_MAX_PAGE_TEXT_BYTES = 8 * 1024
_MAX_SEMANTIC_STEPS = 100
_MAX_SEMANTIC_BYTES = 32 * 1024
_REDACTED = "[REDACTED]"
_SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "token",
    "secret",
    "authorization",
    "cookie",
    "api_key",
    "apikey",
)


def _bounded_text(value: Any, max_bytes: int) -> str:
    text = str(value or "")
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    suffix = "…"
    room = max(0, max_bytes - len(suffix.encode("utf-8")))
    return encoded[:room].decode("utf-8", errors="ignore") + suffix


def _sensitive_key(key: Any) -> bool:
    normalized = str(key).lower().replace("-", "_").replace(" ", "_")
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _sanitize_value(value: Any, depth: int = 0) -> Any:
    """递归脱敏并限制单个值，避免模型上下文被异常响应撑爆。"""
    if depth >= 8:
        return "[TRUNCATED]"
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for index, (key, child) in enumerate(value.items()):
            if index >= 50:
                cleaned["_truncated"] = True
                break
            name = _bounded_text(key, 128)
            cleaned[name] = _REDACTED if _sensitive_key(name) else _sanitize_value(child, depth + 1)
        return cleaned
    if isinstance(value, (list, tuple)):
        cleaned_list = [_sanitize_value(child, depth + 1) for child in value[:50]]
        if len(value) > 50:
            cleaned_list.append("[TRUNCATED]")
        return cleaned_list
    if isinstance(value, str):
        return _bounded_text(value, 1024)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _bounded_text(value, 1024)


def _safe_url(url: str) -> str:
    """保留定位请求所需的 URL，但清除查询串中的凭证类值。"""
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        netloc = host
        if parts.port is not None:
            netloc += f":{parts.port}"
        query = [
            (key, _REDACTED if _sensitive_key(key) else _bounded_text(value, 256))
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
        ]
        return _bounded_text(
            urlunsplit((parts.scheme, netloc, parts.path, urlencode(query), "")),
            2048,
        )
    except Exception:
        return "[INVALID URL]"


def _origin(url: str) -> tuple[str, str, int | None]:
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    port = parts.port
    if port is None:
        port = 443 if scheme == "https" else 80 if scheme == "http" else None
    return (scheme, (parts.hostname or "").lower(), port)


def _json_preview(raw: bytes) -> str | None:
    if not raw or len(raw) > _MAX_RESPONSE_BODY_BYTES:
        return None
    try:
        parsed = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    serialized = json.dumps(_sanitize_value(parsed), ensure_ascii=False, separators=(",", ":"))
    return _bounded_text(serialized, _MAX_PREVIEW_BYTES)


def _semantic_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """只给编译器保留清洗后步骤的有限语义字段，不复制 raw events。"""
    result: list[dict[str, Any]] = []
    used = 0
    allowed = ("id", "action", "label", "value", "condition", "target", "mutating")
    for step in steps[:_MAX_SEMANTIC_STEPS]:
        selected = {key: step[key] for key in allowed if key in step}
        sensitive_context = json.dumps(
            {"label": selected.get("label"), "target": selected.get("target")},
            ensure_ascii=False,
            default=str,
        )
        if "value" in selected and _sensitive_key(sensitive_context):
            selected["value"] = _REDACTED
        item = _sanitize_value(selected)
        size = len(json.dumps(item, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        if result and used + size > _MAX_SEMANTIC_BYTES:
            break
        if size > _MAX_SEMANTIC_BYTES:
            continue
        result.append(item)
        used += size
    return result


class RecordExecutor:
    def __init__(self, client: ControlPlaneClient, job: Job, workspace: Path) -> None:
        self.client = client
        self.job = job
        self.artifacts_dir = workspace / job.run_id
        self.session = BrowserSession(job, self.artifacts_dir)
        self.events: list[dict[str, Any]] = []
        self.response_summaries: list[dict[str, Any]] = []
        self._stopped = False
        self.start_url = job.site.base_url
        self._record_origin: tuple[str, str, int | None] | None = None

    def execute(self) -> str:
        started = time.monotonic()
        self._emit(
            "run.start",
            run_id=self.job.run_id,
            kind="record",
            headless=False,
            base_url=self.job.site.base_url,
        )
        status = "passed"
        summary: dict[str, Any] = {}
        try:
            material = self._resolve_auth()
            # 录制必须开窗：人要看见并操作。没有桌面会话就明确失败。
            self.session.start(cookies=material.cookies, extra_headers=material.headers)

            runner = ActionRunner(self.session)
            if material.form is not None:
                login_steps = form_login_steps(material.form, self.job.site.base_url)
                for index, step in enumerate(login_steps, start=1):
                    outcome = self._run_login_step(runner, step, index, len(login_steps))
                    if outcome.status == "failed":
                        raise RuntimeError(outcome.message or "登录失败")

            # 无论有没有登录，都必须离开 about:blank。
            # 输入框里的「/」只是 placeholder，没填就等于空路径，以前会一直停在空白页。
            self._goto_start()
            self._arm_response_capture()
            self._arm_recorder()
            self._wait_until_stop()
            summary = self._compile_and_capture()
        except HeadedNotSupported as exc:
            self._emit("log", level="error", message=str(exc), reason="headed_not_supported")
            status = "error"
            summary = {"error": str(exc)}
        except UnsupportedLoginChallenge as exc:
            self._emit("log", level="error", message=str(exc), reason="login_unsupported")
            status = "error"
            summary = {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            self._emit("log", level="error", message=f"{type(exc).__name__}: {exc}")
            status = "error"
            summary = {"error": f"{type(exc).__name__}: {exc}"}

        try:
            self.session.stop(keep_trace=False)
        except Exception:
            pass

        self._emit("run.end", status=status)
        self.client.complete(self.job.run_id, status, summary, time.monotonic() - started)
        return status

    def _start_url(self) -> str:
        path = (self.job.record_start_path or "").strip()
        base = self.job.site.base_url.rstrip("/")
        if not path or path == "/":
            return base + "/"
        if path.startswith(("http://", "https://")):
            return path
        return urljoin(base + "/", path.lstrip("/"))

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
        if getattr(self, "_capture_warned", False):
            return
        self._capture_warned = True
        self._emit("log", level="warn", message=message)

    def _goto_start(self) -> None:
        url = self._start_url()
        self._emit("step.start", step_id="record.goto", action="goto", label=f"打开 {url}")
        self.session.page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        wait_for_app_ready(self.session.page, timeout_ms=30_000)
        self.start_url = self.session.page.url
        self._emit(
            "step.end",
            step_id="record.goto",
            action="goto",
            label=f"打开 {url}",
            status="passed",
            data={"url": self.start_url},
            screenshot=self._capture("record_goto"),
        )
        self._emit("log", level="info", message=f"开始录制：{self.start_url}")

    def _arm_response_capture(self) -> None:
        """起始页就绪后才监听，登录流量不会进入编译上下文。"""
        self._record_origin = _origin(self.start_url)
        self.session.page.on("response", self._on_response)

    def _on_response(self, response: Any) -> None:
        if len(self.response_summaries) >= _MAX_JSON_RESPONSES:
            return
        try:
            if self._record_origin is None or _origin(response.url) != self._record_origin:
                return
            headers = response.headers
            content_type = str(headers.get("content-type", "")).lower()
            if "json" not in content_type:
                return
            content_length = headers.get("content-length")
            try:
                body_too_large = bool(content_length) and int(content_length) > _MAX_RESPONSE_BODY_BYTES
            except (TypeError, ValueError):
                body_too_large = False
            if body_too_large:
                preview = None
            else:
                preview = _json_preview(response.body())
            summary: dict[str, Any] = {
                "method": _bounded_text(response.request.method, 16),
                "url": _safe_url(response.url),
                "status": int(response.status),
            }
            if preview is not None:
                summary["preview"] = preview
            self.response_summaries.append(summary)
        except Exception:
            # 录制上下文是辅助信息，不能因响应已释放或跨导航竞态打断主流程。
            return

    def _arm_recorder(self) -> None:
        # 顺序不能改：recorder.js 一装上就会调 __atpEmit，binding 还没注册事件直接丢。
        # add_init_script 只管后续导航，当前这一页必须手动 evaluate。
        self.session.context.expose_binding("__atpEmit", self._on_emit)
        combined = _LOCATOR_JS + "\n" + _RECORDER_JS
        self.session.context.add_init_script(script=combined)
        self.session.page.evaluate(_LOCATOR_JS)
        self.session.page.evaluate(_RECORDER_JS)

    def _on_emit(self, _source: Any, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        if payload.get("type") == "stop":
            self._stopped = True
            return
        self.events.append(payload)

    def _wait_until_stop(self) -> None:
        deadline = time.monotonic() + _MAX_SECONDS
        last_pulse = 0.0
        while not self._stopped:
            if time.monotonic() > deadline:
                self._emit("log", level="info", message="录制满 30 分钟，自动结束")
                break
            page = self.session.page
            try:
                if page.is_closed():
                    break
            except Exception:
                break
            page.wait_for_timeout(300)
            try:
                page.evaluate(
                    "(n) => window.__atpRecorder && window.__atpRecorder.setCount(n)",
                    len(self.events),
                )
            except Exception:
                pass
            now = time.monotonic()
            if now - last_pulse >= 2:
                last_pulse = now
                # 兼做心跳：长时间不上报事件，租约会过期、任务被回收
                self._emit("record.progress", event_count=len(self.events))
                if self.client.should_stop(self.job.run_id):
                    self._stopped = True

    def _compile_and_capture(self) -> dict[str, Any]:
        steps, notes = compile_events(
            self.events, self.start_url, intent=self.job.record_intent or ""
        )
        compiler_context = self._capture_compiler_context(steps)
        screenshot_url = None
        shot = self.artifacts_dir / "record_end.png"
        try:
            self.session.page.screenshot(path=str(shot), full_page=False)
            screenshot_url = self.client.upload_artifact(self.job.run_id, "record_end.png", shot)
        except Exception:
            pass
        return {
            "steps": steps,
            "notes": notes,
            "raw_event_count": len(self.events),
            "start_url": self.start_url,
            "site_id": self.job.site.id,
            "credential_id": self.job.auth.ref,
            "screenshot": screenshot_url,
            "compiler_context": compiler_context,
        }

    def _capture_compiler_context(self, steps: list[dict[str, Any]]) -> dict[str, Any]:
        page = self.session.page
        try:
            current_url = _safe_url(page.url)
        except Exception:
            current_url = _safe_url(self.start_url)
        try:
            page_title = _bounded_text(page.title(), 512)
        except Exception:
            page_title = ""
        try:
            visible_text = page.evaluate(
                """() => {
                    const badge = document.getElementById('__atp_recorder_badge');
                    const previous = badge ? badge.style.display : null;
                    if (badge) badge.style.display = 'none';
                    try {
                        return (document.body && document.body.innerText || '').slice(0, 12000);
                    } finally {
                        if (badge) badge.style.display = previous;
                    }
                }"""
            )
        except Exception:
            visible_text = ""
        return {
            "network_requests": list(self.response_summaries[:_MAX_JSON_RESPONSES]),
            "current_url": current_url,
            "page_title": page_title,
            "visible_text": _bounded_text(visible_text, _MAX_PAGE_TEXT_BYTES),
            "semantic_steps": _semantic_steps(steps),
        }

    def _run_login_step(self, runner: ActionRunner, step: Step, index: int, total: int) -> StepOutcome:
        self._emit(
            "step.start",
            step_id=step.id,
            action=step.action,
            label=step.display(),
            index=index,
            total=total,
        )
        outcome = runner.run(step)
        self._emit(
            "step.end",
            step_id=step.id,
            action=step.action,
            label=step.display(),
            status=outcome.status,
            message=outcome.message,
            data=outcome.data,
            screenshot=self._capture(f"login_{index:02d}_{step.id}"),
        )
        return outcome

    def _resolve_auth(self):
        payload = None
        if self.job.auth.type != "none" and self.job.auth.ref:
            material = self.client.credential_material(self.job.auth.ref)
            if material is None:
                raise RuntimeError("无法获取凭证，登录失败")
            payload = material.get("payload")
        return build_material(self.job.auth, payload, self.job.site.base_url)

    def _emit(self, type_: str, **data: Any) -> None:
        self.client.post_events(self.job.run_id, [new_event(type_, **data)])  # type: ignore[arg-type]
