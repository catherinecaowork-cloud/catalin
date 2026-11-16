"""种子数据：建一个不需要登录的站点和两条流程，让平台第一次就能跑出结果。

第二条流程刻意断言一段不存在的文本——用来确认失败路径也是可见的：
失败步骤、截图、证据链都会出现在控制台里。
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from atp_http import control_client  # noqa: E402

SERVER = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8910"


def main() -> int:
    client = control_client(SERVER, timeout=30.0)

    existing = client.get("/api/v1/sites").raise_for_status().json()
    site = next((s for s in existing if s["name"] == "示例站点"), None)
    if site is None:
        site = (
            client.post(
                "/api/v1/sites",
                json={
                    "name": "示例站点",
                    "base_url": "https://example.com",
                    "env": "test",
                    "adapter": "generic",
                    "probe_error_url_patterns": [],
                },
            )
            .raise_for_status()
            .json()
        )
        print(f"已创建站点：{site['name']} → {site['base_url']}")
    else:
        print(f"站点已存在：{site['name']}")

    flows = [
        {
            "site_id": site["id"],
            "name": "打开首页并体检（应通过）",
            "steps": [
                {"id": "open", "action": "goto", "value": "/", "label": "打开首页"},
                {"id": "loaded", "action": "waitFor", "condition": "load", "label": "等待加载完成"},
                {
                    "id": "title",
                    "action": "assert",
                    "assert_kind": "text_contains",
                    "expected": "Example Domain",
                    "label": "断言页面出现标题文本",
                },
                {"id": "health", "action": "pageHealth", "label": "页面体检（探针）"},
            ],
        },
        {
            "site_id": site["id"],
            "name": "故意失败的断言（看失败路径）",
            "steps": [
                {"id": "open", "action": "goto", "value": "/", "label": "打开首页"},
                {
                    "id": "missing",
                    "action": "assert",
                    "assert_kind": "text_contains",
                    "expected": "这段文本不存在",
                    "label": "断言一段不存在的文本",
                },
            ],
        },
    ]

    existing_flows = {f["name"] for f in client.get("/api/v1/flows").raise_for_status().json()}
    for flow in flows:
        if flow["name"] in existing_flows:
            print(f"流程已存在：{flow['name']}")
            continue
        created = client.post("/api/v1/flows", json=flow).raise_for_status().json()
        print(f"已创建流程：{created['name']}（{created['status']}）")

    print(f"\n打开 {SERVER} 就能看到控制台。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
