from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from autotest_control.chain import ChainError, expand_setup_chain
from autotest_control.deps import new_id, now
from autotest_control.models import Batch, Environment, Flow, Run, Site
from autotest_control.replay_bind import ReplayBindError
from autotest_control.suites import CONFIRMED_STATUSES, decide_after_run
from autotest_protocol import RunOptions

from autotest_control.domain.jobs import build_chain_job, build_job, project_flow_map


def finish_batch(batch: Batch, status: str, items: list[dict[str, Any]]) -> None:
    batch.items = items
    flag_modified(batch, "items")
    batch.status = status
    batch.finished_at = now()


def enqueue_chain(
    session: Session,
    chain: list[Flow],
    site: Site,
    *,
    headless: bool,
    dry_run: bool,
    variables: dict[str, str] | None = None,
    environment: Environment | None = None,
    batch_id: str | None = None,
    batch_index: int | None = None,
) -> Run:
    target = chain[-1]
    run_id = new_id()
    options = RunOptions(headless=headless, dry_run=dry_run)
    if len(chain) == 1:
        job = build_job(
            session, run_id, site, chain[0], options, variables, environment=environment
        )
    else:
        job = build_chain_job(
            session, run_id, site, chain, options, variables, environment=environment
        )
    run = Run(
        id=run_id,
        tenant_id=target.tenant_id,
        project_id=target.project_id,
        site_id=site.id,
        flow_id=target.id,
        flow_version=target.version,
        kind="replay",
        status="queued",
        job=job.model_dump(mode="json"),
        required_labels=[] if headless else ["headed"],
        batch_id=batch_id,
        batch_index=batch_index,
    )
    session.add(run)
    return run


def queue_replay(
    session: Session,
    flow: Flow,
    site: Site,
    *,
    headless: bool,
    dry_run: bool,
    variables: dict[str, str] | None = None,
    environment: Environment | None = None,
    batch_id: str | None = None,
    batch_index: int | None = None,
) -> Run:
    chain = expand_setup_chain(flow, project_flow_map(session, flow))
    return enqueue_chain(
        session,
        chain,
        site,
        headless=headless,
        dry_run=dry_run,
        variables=variables,
        environment=environment,
        batch_id=batch_id,
        batch_index=batch_index,
    )


def advance_batch(session: Session, run: Run) -> Run | None:
    if not run.batch_id:
        return None
    batch = session.get(Batch, run.batch_id)
    if batch is None or batch.status not in {"queued", "running"}:
        return None
    items = [dict(item) for item in (batch.items or [])]
    index = run.batch_index if run.batch_index is not None else batch.current_index
    if 0 <= index < len(items):
        items[index]["run_id"] = run.id
        items[index]["status"] = run.status
    remaining = list(batch.flow_ids or [])[index + 1 :]
    decision = decide_after_run(run.status, len(remaining))
    if decision == "failed":
        for item in items[index + 1 :]:
            item["status"] = "skipped"
        finish_batch(batch, "failed", items)
        return None
    if decision == "passed":
        finish_batch(batch, "passed", items)
        return None
    next_index = index + 1
    next_flow = session.get(Flow, batch.flow_ids[next_index])
    site = session.get(Site, batch.site_id)
    if (
        next_flow is None
        or site is None
        or next_flow.status not in CONFIRMED_STATUSES
    ):
        items[next_index]["status"] = "skipped"
        for item in items[next_index + 1 :]:
            item["status"] = "skipped"
        finish_batch(batch, "failed", items)
        return None
    next_run = None
    environment = None
    env_id = getattr(batch, "environment_id", None)
    if env_id:
        environment = session.get(Environment, env_id)
    try:
        next_run = queue_replay(
            session,
            next_flow,
            site,
            headless=batch.headless,
            dry_run=batch.dry_run,
            variables=batch.variables or {},
            environment=environment,
            batch_id=batch.id,
            batch_index=next_index,
        )
    except (ChainError, ReplayBindError):
        items[next_index]["status"] = "skipped"
        for item in items[next_index + 1 :]:
            item["status"] = "skipped"
        finish_batch(batch, "failed", items)
        return None
    items[next_index]["run_id"] = next_run.id
    items[next_index]["status"] = "queued"
    batch.items = items
    flag_modified(batch, "items")
    batch.current_index = next_index
    batch.current_run_id = next_run.id
    batch.status = "running"
    return next_run
