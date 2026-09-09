from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from autotest_control.deps import Scope, get_site
from autotest_control.models import Flow
from autotest_control.suites import SuiteError, resolve_members


def load_member_flows(session: Session, scope: Scope, flow_ids: list[str]) -> dict[str, Flow]:
    if not flow_ids:
        return {}
    rows = session.scalars(
        select(Flow).where(
            Flow.tenant_id == scope.tenant_id,
            Flow.project_id == scope.project_id,
            Flow.id.in_(flow_ids),
        )
    ).all()
    return {row.id: row for row in rows}


def validated_members(session: Session, scope: Scope, site_id: str, flow_ids: list[str]) -> list[Flow]:
    get_site(session, scope, site_id)
    try:
        return list(resolve_members(site_id, flow_ids, load_member_flows(session, scope, flow_ids)))
    except SuiteError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
