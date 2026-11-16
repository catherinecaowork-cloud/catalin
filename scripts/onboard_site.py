"""命令行接入站点。

控制台上点几下就能做同样的事，这个脚本留给脚本化 / CI 场景。
识别逻辑和控制台共用 autotest_executor.onboarding，不会两边跑偏。

用法：python scripts/onboard_site.py <登录页地址>
"""

from __future__ import annotations

import getpass
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from playwright.sync_api import sync_playwright

from autotest_executor.browser.readiness import wait_for_app_ready
from autotest_executor.onboarding import describe_candidates, detect_login_form

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from atp_http import control_client  # noqa: E402

SERVER = "http://127.0.0.1:8910"


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    login_url = sys.argv[1]

    parsed = urlparse(login_url)
    base_url = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
    login_path = parsed.path + (f"?{parsed.query}" if parsed.query else "")

    print(f"站点根地址：{base_url}")
    print(f"登录页路径：{login_path}\n正在识别登录表单…")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
        try:
            page.goto(login_url, wait_until="domcontentloaded", timeout=30_000)
            # 别用 networkidle：单页应用请求停了界面还没渲染
            if not wait_for_app_ready(page, timeout_ms=30_000):
                print("等了 30 秒页面上仍然没有可交互元素，可能不是登录页。")
                return 1
            page.wait_for_timeout(500)
            title = page.title()
            form = detect_login_form(page)
        except Exception as exc:
            print(f"打不开登录页：{type(exc).__name__}: {exc}")
            return 1
        finally:
            browser.close()

    if not form.get("found"):
        print(f"识别失败：{form.get('reason')}")
        print("可以用 scripts/inspect_page.py 看看页面结构，再手工配置。")
        return 1

    if form.get("challenge"):
        # 明确说不支持，而不是让它以超时或普通失败的形式表现出来
        print(f"\n注意：页面上出现「{form['challenge']}」，本期不支持这类登录挑战。")
        if input("如果它不是必填可以继续。继续？(y/N) ").strip().lower() != "y":
            return 1

    print(f"页面标题：{title}")
    print(f"  账号框   → {describe_candidates(form['username_target'])}")
    print(f"  密码框   → {describe_candidates(form['password_target'])}")
    print(f"  提交按钮 → {describe_candidates(form['submit_target'])}\n")

    site_name = input(f"站点名称 [{title}]: ").strip() or title
    username = input("测试账号: ").strip()
    if not username:
        print("账号不能为空")
        return 1
    password = getpass.getpass("密码（输入不回显）: ")
    if not password:
        print("密码不能为空")
        return 1
    success_text = input("登录成功后页面上必然出现的文字（可留空）: ").strip()

    client = control_client(SERVER, timeout=30.0)
    site = (
        client.post(
            "/api/v1/sites",
            json={
                "name": site_name,
                "base_url": base_url,
                "env": "test",
                "adapter": "generic",
                "probe_error_url_patterns": [],
            },
        )
        .raise_for_status()
        .json()
    )
    print(f"\n已建站点：{site['name']}（{site['id'][:8]}）")

    material = {
        "login_path": login_path,
        "username": username,
        "password": password,
        "username_target": form["username_target"],
        "password_target": form["password_target"],
        "submit_target": form["submit_target"],
    }
    if success_text:
        material["success_text"] = success_text

    credential = (
        client.post(
            f"/api/v1/sites/{site['id']}/credentials",
            json={"name": f"{username}（表单登录）", "type": "form", "payload": material},
        )
        .raise_for_status()
        .json()
    )
    print(f"已存凭证：{credential['name']}（密文落库，读接口不回显）")

    flow = (
        client.post(
            "/api/v1/flows",
            json={
                "site_id": site["id"],
                "name": f"{site_name} · 登录冒烟",
                "auth_type": "form",
                "credential_id": credential["id"],
                "steps": [
                    {"id": "settle", "action": "waitFor", "condition": "network_idle",
                     "label": "等待首页加载完成", "timeout_ms": 20000},
                    {"id": "health", "action": "pageHealth", "label": "首页体检（探针）"},
                ],
            },
        )
        .raise_for_status()
        .json()
    )
    print(f"已建流程：{flow['name']}")
    print("\n登录步骤由凭证自动展开，会出现在直播里。现在可以跑：")
    print('  python scripts\\run_flow.py "登录冒烟" --headed')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
