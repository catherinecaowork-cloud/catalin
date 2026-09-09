"""命令行发起一次运行。CI 里也用这个入口。

用法：python scripts/run_flow.py [流程名关键字] [--headed]
"""

from __future__ import annotations

import sys

import httpx

SERVER = "http://127.0.0.1:8910"


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    headed = "--headed" in sys.argv
    keyword = args[0] if args else ""

    client = httpx.Client(base_url=SERVER, timeout=30.0)
    flows = client.get("/api/v1/flows").raise_for_status().json()
    if not flows:
        print("没有流程，先跑 scripts/seed_demo.py")
        return 1

    matched = [f for f in flows if keyword in f["name"]] if keyword else flows
    if not matched:
        print(f"没有名字包含 {keyword!r} 的流程")
        return 1

    flow = matched[0]
    run = (
        client.post(
            "/api/v1/runs",
            json={"flow_id": flow["id"], "headless": not headed, "dry_run": False},
        )
        .raise_for_status()
        .json()
    )
    print(f"已入队：{flow['name']}")
    print(f"run_id = {run['id']}")
    print(f"直播地址：{SERVER}/  （或 {SERVER}/api/v1/runs/{run['id']}/stream）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
