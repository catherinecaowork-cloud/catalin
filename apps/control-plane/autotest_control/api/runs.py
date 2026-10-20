from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from autotest_control.chain import ChainError, expand_members
from autotest_control.db import get_session
from autotest_control.deps import (
    Scope,
    get_flow,
    get_scope,
    get_site,
    get_suite,
    new_id,
)
from autotest_control.domain.jobs import project_flow_map
from autotest_control.domain.mappers import (
    batch_out,
    run_out,
)
from autotest_control.domain.queue import enqueue_chain, queue_replay
from autotest_control.domain.runs import (
    ACTIVE_RUN_STATUS,
    delete_run_row,
    purge_run_files,
)
from autotest_control.domain.snapshots import snapshot, snapshot_safe, sse
from autotest_control.domain.suites import validated_members
from autotest_control.hub import hub
from autotest_control.models import (
    Batch,
    Run,
)
from autotest_control.replay_bind import ReplayBindError
from autotest_control.schemas import (
    BatchCreate,
    BatchOut,
    RunCreate,
    RunOut,
    RunPurgeIn,
)
from autotest_control.storage import prune_retained_runs

router = APIRouter()

@router.post("/runs", response_model=RunOut)
def create_run(payload: RunCreate, scope: Scope = Depends(get_scope), session: Session = Depends(get_session)) -> RunOut:
    flow = get_flow(session, scope, payload.flow_id)
    site = get_site(session, scope, payload.site_id or flow.site_id)
    try:
        run = queue_replay(
            session,
            flow,
            site,
            headless=payload.headless,
            dry_run=payload.dry_run,
            variables=payload.variables,
        )
    except (ChainError, ReplayBindError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    hub.notify_new_job()
    return run_out(run)


@router.post("/batches", response_model=BatchOut)
def create_batch(
    payload: BatchCreate, scope: Scope = Depends(get_scope), session: Session = Depends(get_session)
) -> BatchOut:
    suite = None
    if payload.suite_id:
        suite = get_suite(session, scope, payload.suite_id)
    flow_ids = list(payload.flow_ids or (suite.flow_ids if suite is not None else []))
    members = validated_members(session, scope, payload.site_id, flow_ids)
    site = get_site(session, scope, payload.site_id)
    name = (payload.name or (suite.name if suite is not None else "") or "勾选运行").strip()
    by_id = project_flow_map(session, members[0])
    try:
        chain = expand_members(members, by_id)
    except ChainError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    batch_id = new_id()
    try:
        run = enqueue_chain(
            session,
            chain,
            site,
            headless=payload.headless,
            dry_run=payload.dry_run,
            variables=payload.variables,
            batch_id=batch_id,
            batch_index=0,
        )
    except ReplayBindError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    items = [{"flow_id": chain[-1].id, "run_id": run.id, "status": "queued"}]
    batch = Batch(
        id=batch_id,
        tenant_id=scope.tenant_id,
        project_id=scope.project_id,
        site_id=payload.site_id,
        suite_id=suite.id if suite is not None else None,
        name=name,
        flow_ids=[chain[-1].id],
        items=items,
        current_index=0,
        current_run_id=run.id,
        status="running",
        headless=payload.headless,
        dry_run=payload.dry_run,
        variables=payload.variables or {},
    )
    session.add(batch)
    session.commit()
    hub.notify_new_job()
    return batch_out(batch)


@router.get("/batches/{batch_id}", response_model=BatchOut)
def get_batch(
    batch_id: str, scope: Scope = Depends(get_scope), session: Session = Depends(get_session)
) -> BatchOut:
    batch = session.get(Batch, batch_id)
    if batch is None or batch.tenant_id != scope.tenant_id or batch.project_id != scope.project_id:
        raise HTTPException(status_code=404, detail="批次不存在")
    return batch_out(batch)





@router.get("/runs", response_model=list[RunOut])
def list_runs(
    limit: int = Query(default=30, le=200),
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> list[RunOut]:
    rows = session.scalars(
        select(Run)
        .where(Run.tenant_id == scope.tenant_id, Run.project_id == scope.project_id)
        .order_by(Run.created_at.desc())
        .limit(limit)
    ).all()
    return [run_out(row) for row in rows]


@router.post("/history/purge")
def purge_runs(
    payload: RunPurgeIn, scope: Scope = Depends(get_scope), session: Session = Depends(get_session)
) -> dict[str, Any]:
    """按用户勾选删除历史运行。进行中的任务跳过。"""
    ids = list(dict.fromkeys(item.strip() for item in payload.ids if item and item.strip()))
    if not ids:
        raise HTTPException(status_code=400, detail="请先勾选要删除的记录")
    deleted: list[str] = []
    skipped: list[dict[str, str]] = []
    for run_id in ids:
        run = session.get(Run, run_id)
        if run is None or run.tenant_id != scope.tenant_id or run.project_id != scope.project_id:
            skipped.append({"id": run_id, "reason": "不存在"})
            continue
        if run.status in ACTIVE_RUN_STATUS:
            skipped.append({"id": run_id, "reason": "进行中"})
            continue
        delete_run_row(session, run)
        deleted.append(run_id)
    session.commit()
    for run_id in deleted:
        purge_run_files(run_id)
    prune_retained_runs()
    return {"deleted": deleted, "skipped": skipped}


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(run_id: str, scope: Scope = Depends(get_scope), session: Session = Depends(get_session)) -> RunOut:
    run = session.get(Run, run_id)
    if run is None or run.tenant_id != scope.tenant_id or run.project_id != scope.project_id:
        raise HTTPException(status_code=404, detail="运行不存在")
    return run_out(run)





@router.get("/runs/{run_id}/snapshot")
def get_snapshot(run_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    return snapshot(session, run_id)


@router.get("/runs/{run_id}/stream")
async def stream_run(run_id: str) -> StreamingResponse:
    """SSE 直播：首包全量快照 + 增量 + 心跳。

    断线后前端重连，重新拿快照补齐，不会因为断连丢掉结论。
    """
    queue = hub.subscribe(run_id)

    async def gen():
        try:
            snapshot = await run_in_threadpool(snapshot_safe, run_id)
            yield sse("snapshot", snapshot)
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=20)
                except asyncio.TimeoutError:
                    # 心跳，防中间层掐断空闲连接
                    yield ": ping\n\n"
                    continue
                yield sse(payload.get("event", "message"), payload.get("data", {}))
        finally:
            hub.unsubscribe(run_id, queue)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )







