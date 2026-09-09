"""控制面：合并录制观察快照与页面模型。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from autotest_control.deps import Scope
from autotest_control.models import Flow, Run, RunEvent
from autotest_protocol import PageWidgetEntry, PageWidgetModel, merge_snapshot_into_model
from autotest_protocol.observer import MAX_PAGE_MODEL_ENTRIES, observation_snapshot_from_event_data

MAX_ENTRIES = MAX_PAGE_MODEL_ENTRIES


def empty_model(*, site_id: str | None = None, recording_run_id: str | None = None) -> PageWidgetModel:
    return PageWidgetModel(site_id=site_id, recording_run_id=recording_run_id, entries=[])


def model_from_run(run: Run) -> PageWidgetModel:
    raw = run.observation_model
    if not isinstance(raw, dict) or not raw:
        return empty_model(site_id=run.site_id, recording_run_id=run.id)
    return PageWidgetModel.model_validate(raw)


def model_to_dict(model: PageWidgetModel) -> dict[str, Any]:
    return model.model_dump(mode="json", exclude_none=True)


def merge_page_widget_models(*models: PageWidgetModel) -> PageWidgetModel:
    index: dict[str, PageWidgetEntry] = {}
    site_id: str | None = None
    flow_id: str | None = None
    recording_run_id: str | None = None
    snapshots_seen = 0
    for model in models:
        site_id = site_id or model.site_id
        flow_id = flow_id or model.flow_id
        recording_run_id = recording_run_id or model.recording_run_id
        snapshots_seen += model.snapshots_seen
        for entry in model.entries:
            index[entry.display_name] = entry
    return PageWidgetModel(
        site_id=site_id,
        flow_id=flow_id,
        recording_run_id=recording_run_id,
        entries=list(index.values())[:MAX_PAGE_MODEL_ENTRIES],
        snapshots_seen=snapshots_seen,
    )


def load_site_widget_models(session: Session, scope: Scope, site_id: str) -> PageWidgetModel:
    flows = session.scalars(
        select(Flow).where(
            Flow.tenant_id == scope.tenant_id,
            Flow.project_id == scope.project_id,
            Flow.site_id == site_id,
        )
    ).all()
    parts: list[PageWidgetModel] = []
    for flow in flows:
        raw = flow.page_widget_model
        if not isinstance(raw, dict) or not raw.get("entries"):
            continue
        parts.append(PageWidgetModel.model_validate(raw))
    if not parts:
        return empty_model(site_id=site_id)
    return merge_page_widget_models(*parts)


def seed_run_observation(session: Session, scope: Scope, run: Run) -> None:
    seeded = load_site_widget_models(session, scope, run.site_id)
    seeded = seeded.model_copy(update={"recording_run_id": run.id, "flow_id": None})
    run.observation_model = model_to_dict(seeded)


def apply_snapshot_to_run(run: Run, data: dict[str, Any]) -> PageWidgetModel | None:
    try:
        snapshot = observation_snapshot_from_event_data(data)
    except Exception:
        return None
    if not snapshot.fields:
        return None
    current = model_from_run(run)
    updated = merge_snapshot_into_model(
        current,
        snapshot,
        site_id=run.site_id,
        recording_run_id=run.id,
    )
    run.observation_model = model_to_dict(updated)
    return updated


def load_recording_snapshots(session: Session, run_id: str, *, limit: int = 60) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(RunEvent)
        .where(RunEvent.run_id == run_id, RunEvent.type == "observe.snapshot")
        .order_by(RunEvent.seq.desc())
        .limit(limit)
    ).all()
    rows = list(reversed(rows))
    return [row.data for row in rows if isinstance(row.data, dict)]


def attach_model_to_flow(flow: Flow, run: Run) -> None:
    model = model_from_run(run)
    if not model.entries:
        flow.page_widget_model = None
        return
    attached = model.model_copy(
        update={
            "flow_id": flow.id,
            "recording_run_id": run.id,
            "site_id": flow.site_id,
        }
    )
    flow.page_widget_model = model_to_dict(attached)
