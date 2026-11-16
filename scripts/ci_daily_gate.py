"""日闸：跑完所有 active 流程，失败非零退出。

与 ``scripts/run_flow.py``（入队即返回）分开：这里会等到终态再判定。
无内网时可用 ``--fixture`` 走内存夹具，验证退出码语义（供 CI 业务闸门作业使用）。

用法：
  python scripts/ci_daily_gate.py --server http://127.0.0.1:8910
  python scripts/ci_daily_gate.py --fixture broken   # 期望非零
  python scripts/ci_daily_gate.py --fixture ok       # 期望零
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urljoin

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from atp_http import control_client, resolve_api_token  # noqa: E402

TERMINAL = frozenset({"passed", "failed", "error"})


class GateClient(Protocol):
    def list_flows(self) -> list[dict[str, Any]]: ...

    def list_workers(self) -> list[dict[str, Any]]: ...

    def healthz(self) -> bool: ...

    def enqueue(self, flow_id: str) -> dict[str, Any]: ...

    def get_run(self, run_id: str) -> dict[str, Any]: ...


@dataclass
class FlowResult:
    name: str
    flow_id: str
    run_id: str | None
    status: str
    detail: str = ""


class HttpGateClient:
    def __init__(self, server: str, timeout: float = 30.0) -> None:
        self.server = server.rstrip("/")
        self._client = control_client(self.server, timeout=timeout)

    def healthz(self) -> bool:
        try:
            response = self._client.get("/healthz")
            return response.status_code == 200
        except Exception:
            return False

    def list_flows(self) -> list[dict[str, Any]]:
        return self._client.get("/api/v1/flows").raise_for_status().json()

    def list_workers(self) -> list[dict[str, Any]]:
        return self._client.get("/api/v1/workers").raise_for_status().json()

    def enqueue(self, flow_id: str) -> dict[str, Any]:
        return (
            self._client.post(
                "/api/v1/runs",
                json={"flow_id": flow_id, "headless": True, "dry_run": False},
            )
            .raise_for_status()
            .json()
        )

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self._client.get(f"/api/v1/runs/{run_id}").raise_for_status().json()

    def close(self) -> None:
        self._client.close()


class FixtureGateClient:
    """无控制面/无内网时的夹具：把「故意失败的 active 流」编成非零退出。"""

    def __init__(self, mode: str) -> None:
        self.mode = mode
        if mode == "empty":
            self._flows: list[dict[str, Any]] = []
        elif mode == "ok":
            self._flows = [
                {"id": "flow-ok", "name": "夹具-应通过", "status": "active"},
                {"id": "flow-draft", "name": "夹具-草稿", "status": "draft"},
            ]
        else:
            self._flows = [
                {"id": "flow-ok", "name": "夹具-应通过", "status": "active"},
                {"id": "flow-broken", "name": "夹具-故意失败", "status": "active"},
            ]
        self._runs: dict[str, dict[str, Any]] = {}
        self._seq = 0

    def healthz(self) -> bool:
        return True

    def list_flows(self) -> list[dict[str, Any]]:
        return list(self._flows)

    def list_workers(self) -> list[dict[str, Any]]:
        return [{"id": "fixture-worker", "online": True, "name": "fixture"}]

    def enqueue(self, flow_id: str) -> dict[str, Any]:
        self._seq += 1
        run_id = f"run-{self._seq}"
        status = "failed" if flow_id == "flow-broken" else "passed"
        self._runs[run_id] = {
            "id": run_id,
            "flow_id": flow_id,
            "status": status,
            "finished_at": "2026-01-01T00:00:00Z",
        }
        return self._runs[run_id]

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self._runs[run_id]


def select_active(flows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [f for f in flows if f.get("status") == "active"]


def worker_online(workers: list[dict[str, Any]]) -> bool:
    return any(bool(w.get("online")) for w in workers)


def run_gate(
    client: GateClient,
    *,
    timeout_seconds: float = 1800.0,
    poll_seconds: float = 2.0,
    require_worker: bool = True,
) -> tuple[int, list[FlowResult]]:
    if not client.healthz():
        print("控制面不可达", file=sys.stderr)
        return 2, []

    if require_worker and not worker_online(client.list_workers()):
        print("没有在线 Worker，无法执行日闸", file=sys.stderr)
        return 2, []

    active = select_active(client.list_flows())
    if not active:
        print("没有可跑的流程（status=active 为空）", file=sys.stderr)
        return 1, []

    deadline = time.monotonic() + timeout_seconds
    results: list[FlowResult] = []

    for flow in active:
        name = str(flow.get("name") or flow.get("id"))
        flow_id = str(flow["id"])
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            results.append(FlowResult(name, flow_id, None, "timeout", "总时限已到，未入队"))
            break
        try:
            run = client.enqueue(flow_id)
        except Exception as exc:  # noqa: BLE001
            results.append(FlowResult(name, flow_id, None, "error", f"入队失败：{exc}"))
            continue
        run_id = str(run["id"])
        status = str(run.get("status") or "queued")
        detail = ""
        while status not in TERMINAL and not run.get("finished_at"):
            if time.monotonic() >= deadline:
                status = "timeout"
                detail = "总时限内未结束"
                break
            time.sleep(min(poll_seconds, max(0.05, deadline - time.monotonic())))
            run = client.get_run(run_id)
            status = str(run.get("status") or status)
        results.append(FlowResult(name, flow_id, run_id, status, detail))

    failed = False
    for item in results:
        mark = "PASS" if item.status == "passed" else "FAIL"
        if item.status != "passed":
            failed = True
        loc = item.run_id or "-"
        extra = f"  {item.detail}" if item.detail else ""
        print(f"[{mark}] {item.name}  run={loc}  status={item.status}{extra}")

    return (1 if failed or not results else 0), results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="active 流程日闸")
    parser.add_argument("--server", default=None, help="控制面地址")
    parser.add_argument("--timeout", type=float, default=1800.0, help="总时限（秒）")
    parser.add_argument("--poll", type=float, default=2.0, help="轮询间隔（秒）")
    parser.add_argument(
        "--fixture",
        choices=("broken", "ok", "empty"),
        default=None,
        help="无控制面夹具模式（CI 业务闸门用，不依赖内网）",
    )
    parser.add_argument(
        "--allow-no-worker",
        action="store_true",
        help="跳过 Worker 在线检查（仅调试）",
    )
    args = parser.parse_args(argv)

    if args.fixture:
        code, _ = run_gate(
            FixtureGateClient(args.fixture),
            timeout_seconds=args.timeout,
            poll_seconds=0.01,
            require_worker=not args.allow_no_worker,
        )
        return code

    server = args.server or __import__("os").getenv("ATP_SERVER", "http://127.0.0.1:8910")
    if not resolve_api_token():
        print(
            "未找到 API Token：请设置 ATP_API_TOKEN，或先启动控制面生成 var/api.token",
            file=sys.stderr,
        )
        return 2

    client = HttpGateClient(server)
    try:
        code, _ = run_gate(
            client,
            timeout_seconds=args.timeout,
            poll_seconds=args.poll,
            require_worker=not args.allow_no_worker,
        )
        if code != 0:
            print(f"日闸未通过。控制台：{urljoin(server + '/', '')}", file=sys.stderr)
        return code
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
