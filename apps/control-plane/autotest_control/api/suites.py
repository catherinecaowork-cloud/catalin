from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from autotest_control.db import get_session
from autotest_control.deps import (
    Scope,
    get_scope,
    get_suite,
    new_id,
)
from autotest_control.domain.mappers import (
    suite_out,
)
from autotest_control.domain.suites import validated_members
from autotest_control.models import (
    Suite,
)
from autotest_control.schemas import (
    SuiteCreate,
    SuiteOut,
    SuiteUpdate,
)

router = APIRouter()

@router.post("/suites", response_model=SuiteOut)
def create_suite(
    payload: SuiteCreate, scope: Scope = Depends(get_scope), session: Session = Depends(get_session)
) -> SuiteOut:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="请填写套件名称")
    validated_members(session, scope, payload.site_id, payload.flow_ids)
    suite = Suite(
        id=new_id(),
        tenant_id=scope.tenant_id,
        project_id=scope.project_id,
        site_id=payload.site_id,
        name=name,
        flow_ids=list(payload.flow_ids),
    )
    session.add(suite)
    session.commit()
    return suite_out(suite)


@router.get("/suites", response_model=list[SuiteOut])
def list_suites(
    site_id: str | None = Query(default=None),
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> list[SuiteOut]:
    stmt = select(Suite).where(Suite.tenant_id == scope.tenant_id, Suite.project_id == scope.project_id)
    if site_id:
        stmt = stmt.where(Suite.site_id == site_id)
    rows = session.scalars(stmt.order_by(Suite.created_at.desc())).all()
    return [suite_out(row) for row in rows]


@router.put("/suites/{suite_id}", response_model=SuiteOut)
def update_suite(
    suite_id: str,
    payload: SuiteUpdate,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> SuiteOut:
    suite = get_suite(session, scope, suite_id)
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="请填写套件名称")
        suite.name = name
    if payload.flow_ids is not None:
        validated_members(session, scope, suite.site_id, payload.flow_ids)
        suite.flow_ids = list(payload.flow_ids)
        flag_modified(suite, "flow_ids")
    session.commit()
    return suite_out(suite)


@router.delete("/suites/{suite_id}")
def delete_suite(
    suite_id: str, scope: Scope = Depends(get_scope), session: Session = Depends(get_session)
) -> dict[str, Any]:
    suite = get_suite(session, scope, suite_id)
    session.delete(suite)
    session.commit()
    return {"ok": True}
