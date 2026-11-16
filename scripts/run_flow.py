"""命令行发起一次运行。

用法：python scripts/run_flow.py [流程名关键字] [--headed]

日闸请用 scripts/ci_daily_gate.py（会等到终态并以退出码反映结果）。
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from atp_http import control_client  # noqa: E402

SERVER = "http://127.0.0.1:8910"


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    headed = "--headed" in sys.argv
    keyword = args[0] if args else ""

    client = control_client(SERVER, timeout=30.0)
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
