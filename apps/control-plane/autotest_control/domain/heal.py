from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from autotest_control.deps import new_id
from autotest_control.heal import build_locator_patches, supervisor_instruction
from autotest_control.models import Flow, HealTask, Run


def pending_heal_for_run(session: Session, run_id: str) -> HealTask | None:
    return session.scalar(
        select(HealTask).where(HealTask.run_id == run_id).order_by(HealTask.created_at.desc())
    )


def collect_heal_task(session: Session, run: Run, updates: Any) -> HealTask | None:
    """监督者：把本轮定位漂移整理成一个脚本修补任务，不自动写回。

    只认执行器写来的 `locator_updates`。环境原因（浮层没打开 / 被遮挡 / 超时）
    在执行器侧就不写 updates——那条界线在 `LocatorMemory.remember` 里，
    这里不做二次判断：凭空替它猜原因，只会再造一条删好候选的路径。
    """
    if not run.flow_id or not isinstance(updates, list) or not updates:
        return None
    flow = session.get(Flow, run.flow_id)
    if flow is None:
        return None
    patches = build_locator_patches(flow.steps or [], updates)
    if not patches:
        return None
    existing = session.scalar(select(HealTask).where(HealTask.run_id == run.id))
    if existing is not None:
        return existing
    task = HealTask(
        id=new_id(),
        flow_id=flow.id,
        run_id=run.id,
        status="pending",
        instruction=supervisor_instruction(patches),
        patches=patches,
        applied_log=[],
    )
    session.add(task)
    return task
