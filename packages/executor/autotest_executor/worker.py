"""Worker 守护进程。

一直向平台长轮询领任务。平台从不主动连它，所以放在内网、NAT 后
或者 CI 里都一样能工作。
"""

from __future__ import annotations

import json
import platform
import shutil
import sys
import time
from pathlib import Path

from autotest_executor.client import ControlPlaneClient, WorkerShutdown
from autotest_executor.inspector import InspectExecutor
from autotest_executor.recorder import RecordExecutor
from autotest_executor.runner import RunExecutor
from autotest_protocol import Job


def _forget_run_workspace(workspace: Path, run_id: str) -> None:
    """上传完成后删掉本机工作目录，避免 var/worker 无限涨。"""
    shutil.rmtree(workspace / run_id, ignore_errors=True)


def _prune_stale_run_dirs(workspace: Path) -> None:
    if not workspace.is_dir():
        return
    for path in workspace.iterdir():
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)


def _default_labels(headed_capable: bool) -> list[str]:
    labels = [f"os:{sys.platform}"]
    if headed_capable:
        labels.append("headed")
    return labels


class WorkerDaemon:
    def __init__(
        self,
        server: str,
        name: str,
        workspace: Path,
        headed_capable: bool,
        project_id: str = "default",
    ) -> None:
        self.server = server
        self.name = name
        self.workspace = workspace
        self.headed_capable = headed_capable
        self.project_id = project_id
        self.identity_path = workspace / "worker-identity.json"
        self.client = ControlPlaneClient(server)

    def ensure_identity(self) -> None:
        """首次运行自动注册，之后复用同一身份。"""
        self.workspace.mkdir(parents=True, exist_ok=True)
        _prune_stale_run_dirs(self.workspace)
        if self.identity_path.exists():
            saved = json.loads(self.identity_path.read_text(encoding="utf-8"))
            if saved.get("server") == self.server:
                self.client.use_identity(saved["worker_id"], saved["token"])
                print(f"复用已注册身份：{saved['worker_id']}")
                return

        data = self.client.register(
            name=self.name,
            labels=_default_labels(self.headed_capable),
            platform=f"{platform.system()} {platform.release()}",
            project_id=self.project_id,
        )
        self.identity_path.write_text(
            json.dumps(
                {"server": self.server, "worker_id": data["id"], "token": data["token"]},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"已注册 Worker：{data['id']}（标签 {', '.join(data['labels'])}）")

    def run_forever(self) -> None:
        self.ensure_identity()
        self.client.heartbeat(_default_labels(self.headed_capable))
        print(f"等待任务中… 控制面 {self.server}", flush=True)
        while True:
            try:
                job_data = self.client.lease()
            except WorkerShutdown:
                print("收到停止指令，退出", flush=True)
                return
            except KeyboardInterrupt:
                raise
            except Exception as exc:  # noqa: BLE001
                print(f"领任务失败，稍后重试：{exc}")
                time.sleep(3)
                continue

            if not job_data:
                self.client.heartbeat(_default_labels(self.headed_capable))
                continue

            try:
                job = Job.model_validate(job_data)
            except Exception as exc:  # noqa: BLE001
                # 旧进程不认识新 kind 时不能把任务留在 leased：人会以为浏览器已经开了
                print(f"任务无法识别，已标为异常：{exc}")
                run_id = job_data.get("run_id") if isinstance(job_data, dict) else None
                if run_id:
                    try:
                        self.client.complete(run_id, "error", {"error": str(exc)}, 0.0)
                    except Exception:
                        pass
                continue

            print(f"领到任务 {job.run_id}（{self._describe(job)}）")
            try:
                status = self._dispatch(job)
                print(f"运行 {job.run_id} 结束：{status}")
            except Exception as exc:  # noqa: BLE001
                print(f"运行 {job.run_id} 异常：{exc}")
                try:
                    self.client.complete(job.run_id, "error", {"error": str(exc)}, 0.0)
                except Exception:
                    pass
            finally:
                _forget_run_workspace(self.workspace, job.run_id)
                _prune_stale_run_dirs(self.workspace)

    def run_once(self) -> bool:
        """领一个任务就返回。CI 里用这个。"""
        self.ensure_identity()
        job_data = self.client.lease()
        if not job_data:
            return False
        job = Job.model_validate(job_data)
        try:
            self._dispatch(job)
        finally:
            _forget_run_workspace(self.workspace, job.run_id)
            _prune_stale_run_dirs(self.workspace)
        return True

    def _dispatch(self, job: Job) -> str:
        if job.kind == "inspect":
            return InspectExecutor(self.client, job, self.workspace).execute()
        if job.kind == "record":
            return RecordExecutor(self.client, job, self.workspace).execute()
        return RunExecutor(self.client, job, self.workspace).execute()

    @staticmethod
    def _describe(job: Job) -> str:
        if job.kind == "inspect":
            return "踩点"
        if job.kind == "record":
            return "录制"
        return "开窗" if not job.options.headless else "无头"
