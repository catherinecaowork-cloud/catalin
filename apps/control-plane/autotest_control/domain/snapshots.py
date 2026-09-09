from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from autotest_control.db import session_scope
from autotest_control.domain.heal import pending_heal_for_run
from autotest_control.domain.mappers import heal_out
from autotest_control.models import Run, RunEvent


def snapshot(session: Session, run_id: str) -> dict[str, Any]:
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="运行不存在")
    events = session.scalars(
        select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.seq)
    ).all()
    heal = pending_heal_for_run(session, run_id)
    return {
        "run": {
            "id": run.id,
            "status": run.status,
            "worker_id": run.worker_id,
            "flow_id": run.flow_id,
            "flow_version": run.flow_version,
            "site_id": run.site_id,
            "summary": run.summary,
            "duration_seconds": run.duration_seconds,
        },
        "events": [
            {"seq": e.seq, "type": e.type, "ts": e.ts.isoformat(), "data": e.data} for e in events
        ],
        "heal_task": heal_out(heal).model_dump() if heal is not None else None,
    }


def snapshot_safe(run_id: str) -> dict[str, Any]:
    with session_scope() as session:
        return snapshot(session, run_id)


def sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
