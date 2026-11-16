"""控制面客户端。

Worker 只通过这层与平台交互：领任务、上报事件、换凭证、传产物。
它不连数据库，也不需要任何入站端口。
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import httpx

from autotest_protocol import Event


class WorkerShutdown(Exception):
    """控制台要求本机执行器退出。"""


class ControlPlaneClient:
    def __init__(self, server: str, timeout: float = 60.0) -> None:
        self.server = server.rstrip("/")
        self._client = httpx.Client(base_url=self.server, timeout=timeout)
        self._post_lock = threading.Lock()
        self.worker_id: str | None = None
        self.token: str | None = None

    # ---------------------------------------------------------- 注册与心跳

    def register(
        self,
        name: str,
        labels: list[str],
        platform: str,
        project_id: str = "default",
        register_code: str = "",
    ) -> dict[str, Any]:
        response = self._client.post(
            "/api/v1/workers/register",
            json={
                "name": name,
                "labels": labels,
                "platform": platform,
                "project_id": project_id,
                "register_code": register_code,
            },
        )
        response.raise_for_status()
        data = response.json()
        self.worker_id = data["id"]
        self.token = data["token"]
        return data

    def use_identity(self, worker_id: str, token: str) -> None:
        self.worker_id = worker_id
        self.token = token

    def heartbeat(self, labels: list[str] | None = None) -> None:
        self._client.post(
            "/api/v1/workers/heartbeat",
            json={"worker_id": self.worker_id, "token": self.token, "labels": labels},
        )

    # ---------------------------------------------------------- 任务

    def lease(self) -> dict[str, Any] | None:
        """长轮询领任务。返回 None 表示这轮没有活。"""
        try:
            response = self._client.get(
                "/api/v1/jobs/lease",
                params={"worker_id": self.worker_id, "token": self.token},
                timeout=90.0,
            )
        except httpx.ReadTimeout:
            return None
        response.raise_for_status()
        data = response.json()
        if data.get("shutdown"):
            raise WorkerShutdown()
        return data.get("job")

    def post_events(self, run_id: str, events: list[Event]) -> None:
        payload = {
            "worker_id": self.worker_id,
            "token": self.token,
            "events": [json.loads(e.model_dump_json()) for e in events],
        }
        # 断网时重试，避免刚跑完的步骤结果丢掉
        with self._post_lock:
            for attempt in range(3):
                try:
                    response = self._client.post(f"/api/v1/runs/{run_id}/events", json=payload)
                    response.raise_for_status()
                    return
                except Exception:
                    if attempt == 2:
                        return
                    time.sleep(1.0 + attempt)

    def complete(
        self, run_id: str, status: str, summary: dict[str, Any], duration_seconds: float
    ) -> None:
        self._client.post(
            f"/api/v1/runs/{run_id}/complete",
            json={
                "worker_id": self.worker_id,
                "token": self.token,
                "status": status,
                "summary": summary,
                "duration_seconds": duration_seconds,
            },
        )

    def upload_artifact(self, run_id: str, name: str, path: Path) -> str | None:
        try:
            with path.open("rb") as handle:
                response = self._client.post(
                    f"/api/v1/runs/{run_id}/artifacts",
                    data={"worker_id": self.worker_id, "token": self.token, "name": name},
                    files={"file": (name, handle, "application/octet-stream")},
                )
            response.raise_for_status()
            return response.json().get("url")
        except Exception:
            return None

    def credential_material(self, credential_id: str) -> dict[str, Any] | None:
        try:
            response = self._client.get(
                f"/api/v1/credentials/{credential_id}/material",
                params={"worker_id": self.worker_id, "token": self.token},
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

    def recording_control(self, run_id: str) -> dict[str, bool]:
        """读取录制控制位：结束 / 暂停。轮询失败时保持继续录制。"""
        try:
            response = self._client.get(
                f"/api/v1/runs/{run_id}/control",
                params={"worker_id": self.worker_id, "token": self.token},
            )
            response.raise_for_status()
            data = response.json()
            return {"stop": bool(data.get("stop")), "pause": bool(data.get("pause"))}
        except Exception:
            return {"stop": False, "pause": False}

    def should_stop(self, run_id: str) -> bool:
        return self.recording_control(run_id).get("stop", False)

    def close(self) -> None:
        self._client.close()
