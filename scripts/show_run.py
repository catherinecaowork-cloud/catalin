"""命令行查看一次运行的过程与结论。

有了它，不开浏览器也能看清跑到哪一步、为什么失败。
用法：python scripts/show_run.py [run_id]  （省略则取最近一次）
"""

from __future__ import annotations

import sys

import httpx

SERVER = "http://127.0.0.1:8910"

_ICON = {"passed": "√", "failed": "×", "skipped": "-", "running": "…"}


def main() -> int:
    client = httpx.Client(base_url=SERVER, timeout=30.0)

    run_id = sys.argv[1] if len(sys.argv) > 1 else None
    if run_id is None:
        runs = client.get("/api/v1/runs", params={"limit": 1}).raise_for_status().json()
        if not runs:
            print("还没有运行记录")
            return 1
        run_id = runs[0]["id"]

    data = client.get(f"/api/v1/runs/{run_id}/snapshot").raise_for_status().json()
    run = data["run"]
    duration = run.get("duration_seconds")
    print(f"运行 {run_id}")
    print(f"结论 {run['status']}" + (f"  耗时 {duration:.1f}s" if duration else ""))
    print("-" * 72)

    for event in data["events"]:
        payload = event["data"]
        kind = event["type"]
        if kind == "step.end":
            icon = _ICON.get(payload.get("status"), "?")
            line = f"{icon} {payload.get('label', payload.get('step_id'))}  ({payload.get('elapsed_ms')}ms)"
            print(line)
            if payload.get("message"):
                print(f"    {payload['message']}")
            if payload.get("drift"):
                print(f"    ⚠ {payload['drift']}")
            if payload.get("screenshot"):
                print(f"    截图 {SERVER}{payload['screenshot']}")
        elif kind == "probe.alert":
            print(f"! 探针告警 [{payload.get('kind')}] {payload.get('message', payload.get('counts'))}")
        elif kind == "log" and payload.get("level") == "error":
            print(f"! 执行器错误 {payload.get('message')}")

    summary = run.get("summary") or {}
    print("-" * 72)
    print(
        f"通过 {summary.get('passed', 0)} · 失败 {summary.get('failed', 0)} · 跳过 {summary.get('skipped', 0)}"
    )
    for name, url in (summary.get("artifacts") or {}).items():
        print(f"证据 {name}: {SERVER}{url}")
    return 0 if run["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
