from __future__ import annotations

import shutil
from datetime import timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from autotest_control.db import session_scope
from autotest_control.deps import auth_worker, now
from autotest_control.models import RecordingCompilation, Run, RunEvent
from autotest_control.settings import settings

ACTIVE_RUN_STATUS = {"queued", "leased", "running"}


def purge_run_files(run_id: str) -> None:
    shutil.rmtree(settings.artifacts_dir / run_id, ignore_errors=True)


def delete_run_row(session: Session, run: Run) -> None:
    session.execute(delete(RunEvent).where(RunEvent.run_id == run.id))
    session.execute(
        delete(RecordingCompilation).where(RecordingCompilation.recording_run_id == run.id)
    )
    for row in session.scalars(
        select(RecordingCompilation).where(RecordingCompilation.validation_run_id == run.id)
    ).all():
        row.validation_run_id = None
    session.delete(run)


def reclaim_expired(session: Session) -> None:
    """回收失联 Worker 手里的任务，让它能被重新领取。"""
    current = now()
    rows = session.scalars(select(Run).where(Run.status.in_(["leased", "running"]))).all()
    for run in rows:
        expires = run.lease_expires_at
        if expires is None:
            continue
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < current:
            run.status = "queued"
            run.worker_id = None
            run.lease_expires_at = None


def try_claim(worker_id: str, token: str) -> dict | None:
    with session_scope() as session:
        worker = auth_worker(session, worker_id, token)
        worker.last_heartbeat_at = now()
        reclaim_expired(session)

        labels = set(worker.labels or [])
        candidates = session.scalars(
            select(Run).where(Run.status == "queued").order_by(Run.created_at)
        ).all()
        for run in candidates:
            if not set(run.required_labels or []).issubset(labels):
                continue
            run.status = "leased"
            run.worker_id = worker.id
            run.lease_expires_at = now() + timedelta(seconds=settings.lease_ttl_seconds)
            job = dict(run.job)
            job["lease_expires_at"] = run.lease_expires_at.isoformat()
            return job
        return None
