"""Site 下 Environment 的读写与 Job 侧快照。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from autotest_control.deps import Scope, new_id
from autotest_control.models import Environment, Site
from autotest_control.schemas import EnvironmentOut
from autotest_protocol import EnvironmentRef, SiteRef
from autotest_protocol.job import ProbeConfig


def environment_out(row: Environment) -> EnvironmentOut:
    return EnvironmentOut(
        id=row.id,
        site_id=row.site_id,
        name=row.name,
        base_url=row.base_url,
        credential_id=row.credential_id,
        labels=list(row.labels or []),
        data=dict(row.data or {}),
        created_at=row.created_at,
    )


def environment_ref(row: Environment) -> EnvironmentRef:
    return EnvironmentRef(
        id=row.id,
        name=row.name,
        base_url=row.base_url.rstrip("/"),
        data=dict(row.data or {}),
        labels=list(row.labels or []),
        credential_id=row.credential_id,
    )


def ensure_default_environment(session: Session, site: Site) -> Environment:
    """旧站点没有 Environment 行时补一条，与 site.base_url / site.env 对齐。"""
    existing = session.scalars(
        select(Environment).where(Environment.site_id == site.id).limit(1)
    ).first()
    if existing is not None:
        return existing
    row = Environment(
        id=new_id(),
        tenant_id=site.tenant_id,
        project_id=site.project_id,
        site_id=site.id,
        name=(site.env or "default").strip() or "default",
        base_url=site.base_url.rstrip("/"),
        credential_id=None,
        labels=[],
        data={},
    )
    session.add(row)
    session.flush()
    return row


def seed_environment_for_site(session: Session, site: Site) -> Environment:
    """新建站点时立刻挂默认环境。"""
    row = Environment(
        id=new_id(),
        tenant_id=site.tenant_id,
        project_id=site.project_id,
        site_id=site.id,
        name=(site.env or "default").strip() or "default",
        base_url=site.base_url.rstrip("/"),
        credential_id=None,
        labels=[],
        data={},
    )
    session.add(row)
    return row


class EnvironmentNotFound(LookupError):
    """控制面 API 转成 404。"""


def find_environment(
    session: Session, scope: Scope, site_id: str, environment_id: str
) -> Environment:
    row = session.get(Environment, environment_id)
    if (
        row is None
        or row.site_id != site_id
        or row.tenant_id != scope.tenant_id
        or row.project_id != scope.project_id
    ):
        raise EnvironmentNotFound(environment_id)
    return row


def resolve_environment(
    session: Session,
    scope: Scope,
    site: Site,
    environment_id: str | None,
) -> Environment | None:
    """运行时选环境：显式 id 优先；否则不强制（兼容只带 site 的旧调用）。"""
    if environment_id:
        return find_environment(session, scope, site.id, environment_id)
    return None


def site_ref_for_run(site: Site, environment: Environment | None) -> SiteRef:
    base = environment.base_url if environment is not None else site.base_url
    env_name = environment.name if environment is not None else site.env
    return SiteRef(
        id=site.id,
        base_url=base.rstrip("/"),
        env=env_name,
        adapter=site.adapter,
        probe=ProbeConfig(error_url_patterns=site.probe_error_url_patterns),
    )


def merge_run_variables(
    environment: Environment | None,
    variables: dict[str, str] | None,
) -> dict[str, str]:
    """环境数据档在下，运行入参覆盖在上。"""
    merged: dict[str, str] = {}
    if environment is not None and environment.data:
        merged.update({str(k): str(v) for k, v in dict(environment.data).items()})
    if variables:
        merged.update(variables)
    return merged

