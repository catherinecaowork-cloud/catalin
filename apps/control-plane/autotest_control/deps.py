from __future__ import annotations

import asyncio
import re
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import Header, HTTPException
from sqlalchemy.orm import Session

from autotest_control.models import Flow, Site, Suite, Worker

# 同一进程内防止两个 Worker 领到同一任务。
# 多副本部署时换成 Postgres 的 SELECT ... FOR UPDATE SKIP LOCKED。
lease_lock = asyncio.Lock()

SENSITIVE_HEADER = re.compile(
    r"^(authorization|cookie|set-cookie|x-api-key|password|passwd|token|secret|api[_-]?key)$",
    re.I,
)
MAX_COMPILE_ATTEMPTS = 3


class Scope:
    """租户与项目边界。

    P0 单租户，但字段现在就带上：隔离规则后补的话早期数据要迁移。
    查询一律经过 scope 过滤，不依赖调用方自觉传参。
    """

    def __init__(self, tenant_id: str, project_id: str) -> None:
        self.tenant_id = tenant_id
        self.project_id = project_id


def get_scope(
    x_tenant_id: str = Header(default="default"),
    x_project_id: str = Header(default="default"),
) -> Scope:
    return Scope(x_tenant_id, x_project_id)


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


def auth_worker(session: Session, worker_id: str, token: str) -> Worker:
    worker = session.get(Worker, worker_id)
    if worker is None or not secrets.compare_digest(worker.token, token):
        raise HTTPException(status_code=401, detail="worker 认证失败")
    return worker


def get_site(session: Session, scope: Scope, site_id: str) -> Site:
    site = session.get(Site, site_id)
    # 越权与不存在返回同样的错误，不泄露资源是否存在
    if site is None or site.tenant_id != scope.tenant_id or site.project_id != scope.project_id:
        raise HTTPException(status_code=404, detail="站点不存在")
    return site


def get_flow(session: Session, scope: Scope, flow_id: str) -> Flow:
    flow = session.get(Flow, flow_id)
    if flow is None or flow.tenant_id != scope.tenant_id or flow.project_id != scope.project_id:
        raise HTTPException(status_code=404, detail="流程不存在")
    return flow


def get_suite(session: Session, scope: Scope, suite_id: str) -> Suite:
    suite = session.get(Suite, suite_id)
    if suite is None or suite.tenant_id != scope.tenant_id or suite.project_id != scope.project_id:
        raise HTTPException(status_code=404, detail="套件不存在")
    return suite
