"""把站点上的表单登录凭证换成指定账号，并删掉旧账号。

明文只从环境变量读，脚本不打印密码。
用法（在仓库根目录）：
  $env:ATP_USERNAME='admin'
  $env:ATP_PASSWORD='...'
  $env:ATP_DELETE_NAME='probe_user'
  python scripts/replace_form_credential.py
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "control-plane"))

from autotest_control import crypto  # noqa: E402
from autotest_control.db import SessionLocal  # noqa: E402
from autotest_control.models import Credential, Flow, Site  # noqa: E402


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _payload(cred: Credential) -> dict:
    return json.loads(crypto.decrypt(cred.payload_encrypted))


def main() -> int:
    username = os.environ.get("ATP_USERNAME", "").strip()
    password = os.environ.get("ATP_PASSWORD", "")
    delete_name = os.environ.get("ATP_DELETE_NAME", "probe_user").strip()
    if not username or not password:
        print("需要环境变量 ATP_USERNAME 和 ATP_PASSWORD", file=sys.stderr)
        return 1

    session = SessionLocal()
    created = 0
    deleted = 0
    try:
        sites = session.query(Site).all()
        for site in sites:
            creds = session.query(Credential).filter(Credential.site_id == site.id).all()
            victims = [c for c in creds if delete_name.lower() in c.name.lower()]
            keepers = [c for c in creds if c not in victims]
            template = None
            for cand in victims + keepers:
                if cand.type != "form":
                    continue
                data = _payload(cand)
                if "username_target" in data and "password_target" in data:
                    template = data
                    break
            if template is None and not victims:
                continue
            if template is None:
                print(f"跳过 {site.name}：没有可复用的登录定位")
                continue

            material = dict(template)
            material["username"] = username
            material["password"] = password
            new = Credential(
                id=str(uuid.uuid4()),
                tenant_id=site.tenant_id,
                project_id=site.project_id,
                site_id=site.id,
                name=f"{username}（表单登录）",
                type="form",
                payload_encrypted=crypto.encrypt(json.dumps(material, ensure_ascii=False)),
                updated_at=_now(),
            )
            session.add(new)
            session.flush()
            created += 1

            victim_ids = {c.id for c in victims}
            for flow in session.query(Flow).filter(Flow.site_id == site.id).all():
                if flow.credential_id in victim_ids or flow.credential_id is None:
                    flow.credential_id = new.id
                    flow.auth_type = "form"

            for cred in victims:
                session.delete(cred)
                deleted += 1
                print(f"{site.name}: 已删 {cred.name}")
            print(f"{site.name}: 已写入 {new.name}")

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print(f"完成：新增 {created}，删除 {deleted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
