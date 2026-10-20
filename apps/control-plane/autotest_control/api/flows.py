from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from autotest_control.chain import ChainError, expand_setup_chain
from autotest_control.db import get_session
from autotest_control.deps import (
    Scope,
    get_flow,
    get_scope,
    get_site,
    new_id,
    now,
)
from autotest_control.domain.jobs import project_flow_map
from autotest_control.domain.mappers import (
    flow_out,
)
from autotest_control.flow_import import FlowImportError, import_flows_to_site
from autotest_control.models import (
    Flow,
    Run,
)
from autotest_control.schemas import (
    FlowCreate,
    FlowImportIn,
    FlowImportOut,
    FlowOut,
    FlowSetupUpdate,
    FlowStatusUpdate,
    FlowUpdate,
)

router = APIRouter()

ALLOWED_TRANSITIONS = {
    ("draft", "reviewed"),
    ("reviewed", "golden"),
    ("golden", "active"),
    # 被测系统变更后回退重走确认
    ("reviewed", "draft"),
    ("golden", "draft"),
    ("active", "draft"),
}


@router.post("/flows", response_model=FlowOut)
def create_flow(payload: FlowCreate, scope: Scope = Depends(get_scope), session: Session = Depends(get_session)) -> FlowOut:
    get_site(session, scope, payload.site_id)
    flow = Flow(
        id=new_id(),
        tenant_id=scope.tenant_id,
        project_id=scope.project_id,
        site_id=payload.site_id,
        name=payload.name,
        status="draft",
        steps=[step.model_dump(mode="json", exclude_none=True) for step in payload.steps],
        auth_type=payload.auth_type,
        credential_id=payload.credential_id,
    )
    session.add(flow)
    session.commit()
    return flow_out(flow)





@router.get("/flows", response_model=list[FlowOut])
def list_flows(
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
    site_id: str | None = Query(default=None),
) -> list[FlowOut]:
    stmt = select(Flow).where(Flow.tenant_id == scope.tenant_id, Flow.project_id == scope.project_id)
    if site_id:
        get_site(session, scope, site_id)
        stmt = stmt.where(Flow.site_id == site_id)
    rows = session.scalars(stmt).all()
    return [flow_out(row) for row in rows]


@router.post("/sites/{site_id}/flows/import", response_model=FlowImportOut)
def import_flows(
    site_id: str,
    payload: FlowImportIn,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> FlowImportOut:
    target = get_site(session, scope, site_id)
    ids = list(dict.fromkeys(payload.flow_ids or []))
    if not ids:
        raise HTTPException(status_code=400, detail="请勾选要导入的脚本")
    selected = [get_flow(session, scope, item) for item in ids]
    sample = selected[0]
    by_id = project_flow_map(session, sample)
    try:
        imported, skipped = import_flows_to_site(session, target, selected, by_id)
    except FlowImportError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ChainError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    return FlowImportOut(imported=imported, skipped=skipped)





@router.patch("/flows/{flow_id}", response_model=FlowOut)
def update_flow(
    flow_id: str,
    payload: FlowUpdate,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> FlowOut:
    flow = get_flow(session, scope, flow_id)
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="请填写名称")
    clash = session.scalars(
        select(Flow).where(Flow.site_id == flow.site_id, Flow.name == name, Flow.id != flow.id)
    ).first()
    if clash is not None:
        raise HTTPException(status_code=409, detail=f"当前环境已有「{name}」")
    flow.name = name
    session.commit()
    return flow_out(flow)


@router.delete("/flows/{flow_id}")
def delete_flow(flow_id: str, scope: Scope = Depends(get_scope), session: Session = Depends(get_session)) -> dict[str, Any]:
    flow = get_flow(session, scope, flow_id)
    if flow.status != "draft":
        raise HTTPException(status_code=409, detail="用例不能删除，请先退回草稿")
    for other in session.scalars(select(Flow).where(Flow.setup_flow_id == flow.id)).all():
        other.setup_flow_id = None
    session.delete(flow)
    session.commit()
    return {"ok": True}


@router.post("/flows/{flow_id}/status", response_model=FlowOut)
def update_flow_status(
    flow_id: str,
    payload: FlowStatusUpdate,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> FlowOut:
    """状态只能按序推进，且执行成功不会自动推进——确认是一次显式动作。"""
    flow = get_flow(session, scope, flow_id)
    if (flow.status, payload.status) not in ALLOWED_TRANSITIONS:
        raise HTTPException(
            status_code=409, detail=f"不允许的状态流转：{flow.status} → {payload.status}"
        )

    if payload.status == "golden":
        if not payload.baseline_run_id:
            raise HTTPException(status_code=400, detail="进入 golden 需要指定作为基线的运行")
        run = session.get(Run, payload.baseline_run_id)
        if run is None or run.flow_id != flow.id:
            raise HTTPException(status_code=400, detail="基线运行不属于该流程")
        if run.status != "passed":
            raise HTTPException(status_code=409, detail="只能采纳通过的运行作为基线")
        flow.baseline = {
            "run_id": run.id,
            "adopted_at": now().isoformat(),
            "summary": run.summary or {},
        }

    if payload.status == "active" and flow.baseline is None:
        raise HTTPException(status_code=409, detail="未固化基线的流程不能进入回归")

    if payload.status == "draft":
        flow.baseline = None

    flow.status = payload.status
    session.commit()
    return flow_out(flow)


@router.post("/flows/{flow_id}/setup", response_model=FlowOut)
def update_flow_setup(
    flow_id: str,
    payload: FlowSetupUpdate,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> FlowOut:
    flow = get_flow(session, scope, flow_id)
    previous_ids = list(getattr(flow, "setup_flow_ids", None) or [])
    previous_single = flow.setup_flow_id
    if payload.setup_flow_ids is not None:
        setup_ids = list(payload.setup_flow_ids)
    elif payload.setup_flow_id:
        setup_ids = [payload.setup_flow_id]
    else:
        setup_ids = []
    if flow.id in setup_ids:
        raise HTTPException(status_code=409, detail="不能把自己当成前置")
    for setup_id in setup_ids:
        setup = get_flow(session, scope, setup_id)
        if setup.id == flow.id:
            raise HTTPException(status_code=409, detail="不能把自己当成前置")
    flow.setup_flow_ids = setup_ids
    flow.setup_flow_id = setup_ids[-1] if setup_ids else None
    by_id = project_flow_map(session, flow)
    by_id[flow.id] = flow
    try:
        expand_setup_chain(flow, by_id)
    except ChainError as exc:
        flow.setup_flow_ids = previous_ids
        flow.setup_flow_id = previous_single
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    return flow_out(flow)
