"""同一 Site/System 下的 Environment CRUD。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from autotest_control.db import get_session
from autotest_control.deps import Scope, get_scope, get_site, new_id
from autotest_control.domain.environments import (
    EnvironmentNotFound,
    ensure_default_environment,
    environment_out,
    find_environment,
)
from autotest_control.models import Credential, Environment
from autotest_control.schemas import EnvironmentCreate, EnvironmentOut, EnvironmentUpdate

router = APIRouter()


def _validate_credential(
    session: Session, scope: Scope, site_id: str, credential_id: str | None
) -> str | None:
    if not credential_id:
        return None
    cred = session.get(Credential, credential_id)
    if (
        cred is None
        or cred.site_id != site_id
        or cred.tenant_id != scope.tenant_id
        or cred.project_id != scope.project_id
    ):
        raise HTTPException(status_code=400, detail="凭证不存在或不属于该系统")
    return cred.id


@router.get("/sites/{site_id}/environments", response_model=list[EnvironmentOut])
def list_environments(
    site_id: str,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> list[EnvironmentOut]:
    site = get_site(session, scope, site_id)
    ensure_default_environment(session, site)
    session.commit()
    rows = session.scalars(
        select(Environment)
        .where(
            Environment.site_id == site.id,
            Environment.tenant_id == scope.tenant_id,
            Environment.project_id == scope.project_id,
        )
        .order_by(Environment.created_at.asc())
    ).all()
    return [environment_out(row) for row in rows]


@router.post("/sites/{site_id}/environments", response_model=EnvironmentOut)
def create_environment(
    site_id: str,
    payload: EnvironmentCreate,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> EnvironmentOut:
    site = get_site(session, scope, site_id)
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="环境名称不能为空")
    base_url = payload.base_url.strip().rstrip("/")
    if not base_url:
        raise HTTPException(status_code=400, detail="base_url 不能为空")
    credential_id = _validate_credential(session, scope, site.id, payload.credential_id)
    row = Environment(
        id=new_id(),
        tenant_id=scope.tenant_id,
        project_id=scope.project_id,
        site_id=site.id,
        name=name,
        base_url=base_url,
        credential_id=credential_id,
        labels=list(payload.labels or []),
        data={str(k): str(v) for k, v in dict(payload.data or {}).items()},
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return environment_out(row)


@router.get("/sites/{site_id}/environments/{environment_id}", response_model=EnvironmentOut)
def get_environment(
    site_id: str,
    environment_id: str,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> EnvironmentOut:
    get_site(session, scope, site_id)
    try:
        row = find_environment(session, scope, site_id, environment_id)
    except EnvironmentNotFound as exc:
        raise HTTPException(status_code=404, detail="环境不存在") from exc
    return environment_out(row)


@router.patch("/sites/{site_id}/environments/{environment_id}", response_model=EnvironmentOut)
def update_environment(
    site_id: str,
    environment_id: str,
    payload: EnvironmentUpdate,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> EnvironmentOut:
    get_site(session, scope, site_id)
    try:
        row = find_environment(session, scope, site_id, environment_id)
    except EnvironmentNotFound as exc:
        raise HTTPException(status_code=404, detail="环境不存在") from exc
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="环境名称不能为空")
        row.name = name
    if payload.base_url is not None:
        base_url = payload.base_url.strip().rstrip("/")
        if not base_url:
            raise HTTPException(status_code=400, detail="base_url 不能为空")
        row.base_url = base_url
    if payload.credential_id is not None:
        # 空字符串表示清空
        raw = payload.credential_id.strip() if isinstance(payload.credential_id, str) else payload.credential_id
        row.credential_id = _validate_credential(
            session, scope, site_id, raw or None
        )
    if payload.labels is not None:
        row.labels = list(payload.labels)
    if payload.data is not None:
        row.data = {str(k): str(v) for k, v in dict(payload.data).items()}
    session.commit()
    session.refresh(row)
    return environment_out(row)


@router.delete("/sites/{site_id}/environments/{environment_id}")
def delete_environment(
    site_id: str,
    environment_id: str,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    get_site(session, scope, site_id)
    try:
        row = find_environment(session, scope, site_id, environment_id)
    except EnvironmentNotFound as exc:
        raise HTTPException(status_code=404, detail="环境不存在") from exc
    remaining = session.scalars(
        select(Environment).where(
            Environment.site_id == site_id,
            Environment.id != environment_id,
        )
    ).all()
    if not remaining:
        raise HTTPException(status_code=409, detail="系统至少保留一个环境")
    session.delete(row)
    session.commit()
    return {"ok": True}
