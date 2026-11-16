"""失败修复任务：收集上下文 → AI/fixture 提案 → 人工确认后写回。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from autotest_control.ai.failure_healer import (
    AIFailureHealer,
    FailureHealContract,
    FailureHealPatch,
    apply_failure_patches,
    build_failure_context,
    classify_error_class,
)
from autotest_control.deps import Scope, new_id
from autotest_control.domain.objects import load_site_object_map, object_out
from autotest_control.models import FailureHealTask, Flow, Run, RunEvent, UiObject


def first_failed_step_result(summary: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(summary, dict):
        return None
    steps = summary.get("steps")
    if not isinstance(steps, list):
        return None
    for item in steps:
        if isinstance(item, dict) and item.get("status") == "failed":
            return item
    return None


def screenshot_for_step(session: Session, run_id: str, step_id: str) -> str | None:
    """从 step.end 事件里取截图路径/URL（若有）。"""
    rows = session.scalars(
        select(RunEvent)
        .where(RunEvent.run_id == run_id, RunEvent.type == "step.end")
        .order_by(RunEvent.seq.desc())
    ).all()
    for row in rows:
        data = row.data or {}
        if str(data.get("step_id") or "") != step_id:
            continue
        shot = data.get("screenshot")
        if isinstance(shot, str) and shot.strip():
            return shot.strip()
        # 兼容写在 data 里的路径
        nested = data.get("data") if isinstance(data.get("data"), dict) else {}
        path = nested.get("screenshot_path") or data.get("screenshot_path")
        if isinstance(path, str) and path.strip():
            return path.strip()
    return None


def tried_from_result(step_result: dict[str, Any], step: dict[str, Any]) -> list[str]:
    tried: list[str] = []
    data_tried = step_result.get("tried")
    if isinstance(data_tried, list):
        tried.extend(str(x) for x in data_tried)
    message = str(step_result.get("message") or "")
    if "tried=" in message:
        # 执行器偶发把 tried 写进 message
        part = message.split("tried=", 1)[-1]
        tried.extend(p.strip() for p in part.replace("]", "").split(",") if p.strip())
    target = step.get("target") if isinstance(step.get("target"), dict) else {}
    for c in target.get("candidates") or []:
        if isinstance(c, dict):
            kind = c.get("kind") or ""
            value = c.get("value") or ""
            tried.append(f"{kind}={value}")
    # 去重保序
    seen: set[str] = set()
    out: list[str] = []
    for item in tried:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def collect_context_for_run(
    session: Session,
    run: Run,
    *,
    step_id: str | None = None,
) -> dict[str, Any]:
    if not run.flow_id:
        raise ValueError("该运行没有关联流程，无法生成修复提案")
    flow = session.get(Flow, run.flow_id)
    if flow is None:
        raise ValueError("流程不存在")

    summary = run.summary if isinstance(run.summary, dict) else {}
    step_result = None
    if step_id:
        for item in summary.get("steps") or []:
            if isinstance(item, dict) and item.get("step_id") == step_id:
                step_result = item
                break
        if step_result is None:
            raise ValueError(f"运行摘要中找不到步骤 {step_id}")
    else:
        step_result = first_failed_step_result(summary)
    if step_result is None:
        raise ValueError("运行摘要中没有失败步骤")

    sid = str(step_result.get("step_id") or "")
    step_def: dict[str, Any] = {}
    for raw in flow.steps or []:
        if isinstance(raw, dict) and str(raw.get("id")) == sid:
            step_def = raw
            break
    if not step_def:
        step_def = {"id": sid, "action": step_result.get("action"), "label": step_result.get("label")}

    object_def = None
    oid = step_def.get("object_id")
    if oid:
        row = session.get(UiObject, str(oid))
        if row is not None and row.site_id == run.site_id:
            object_def = object_out(row)

    env_keys: list[str] = []
    job = run.job if isinstance(run.job, dict) else {}
    environment = job.get("environment") if isinstance(job.get("environment"), dict) else {}
    data = environment.get("data") if isinstance(environment.get("data"), dict) else {}
    env_keys = sorted(str(k) for k in data.keys())
    variables = job.get("variables") if isinstance(job.get("variables"), dict) else {}
    for key in variables:
        if str(key) not in env_keys:
            env_keys.append(str(key))

    screenshot = step_result.get("screenshot")
    if not isinstance(screenshot, str) or not screenshot.strip():
        screenshot = screenshot_for_step(session, run.id, sid)

    return build_failure_context(
        run_id=run.id,
        flow_id=flow.id,
        step=step_def,
        step_result=step_result,
        object_def=object_def,
        screenshot=screenshot if isinstance(screenshot, str) else None,
        env_data_keys=env_keys,
        tried=tried_from_result(step_result, step_def),
    )


def propose_for_run(
    session: Session,
    run: Run,
    *,
    step_id: str | None = None,
    fixture_mode: bool | None = None,
    dry_run: bool = True,
    healer: AIFailureHealer | None = None,
) -> FailureHealTask:
    """生成失败修复任务。默认 dry_run：只落库提案，不写回流程/对象库。"""
    if not run.flow_id:
        raise ValueError("该运行没有关联流程")
    context = collect_context_for_run(session, run, step_id=step_id)
    result = (healer or AIFailureHealer()).propose(context, fixture_mode=fixture_mode)
    contract = result.contract
    task = FailureHealTask(
        id=new_id(),
        flow_id=run.flow_id,
        run_id=run.id,
        site_id=run.site_id,
        step_id=str(context.get("step_id") or ""),
        status="proposed" if dry_run else "pending",
        error_class=contract.error_class,
        requires_human_confirm=bool(contract.requires_human_confirm),
        source=result.source,
        context=context,
        patches=[p.model_dump(mode="json") for p in contract.patches],
        notes=list(contract.notes or []),
        usage={
            "input_tokens": result.usage.input_tokens,
            "output_tokens": result.usage.output_tokens,
            "attempts": result.attempts,
        },
        applied_log=[],
        dry_run=bool(dry_run),
    )
    session.add(task)
    session.flush()
    return task


def apply_failure_heal_task(
    session: Session,
    task: FailureHealTask,
    *,
    scope: Scope,
    force: bool = False,
) -> FailureHealTask:
    """人工确认后写回 flow.steps / ui_object.target。"""
    if task.status == "applied":
        return task
    if task.status == "rejected":
        raise ValueError("提案已拒绝，不能再应用")
    if task.requires_human_confirm and not force and task.status == "proposed":
        # proposed = dry-run 提案；需显式 apply（force 仅测试）
        pass
    if not task.patches:
        raise ValueError("提案没有可应用的补丁（可能是 uncertain）")

    flow = session.get(Flow, task.flow_id)
    if flow is None:
        raise ValueError("流程不存在")

    objects_map = load_site_object_map(session, scope, flow.site_id)
    objects_dump = {oid: object_out(row) for oid, row in objects_map.items()}
    new_steps, object_updates, audit = apply_failure_patches(
        flow.steps or [],
        task.patches or [],
        objects=objects_dump,
    )
    applied_any = any(item.get("status") == "applied" for item in audit)
    if not applied_any:
        task.applied_log = audit
        flag_modified(task, "applied_log")
        task.status = "failed"
        return task

    flow.steps = new_steps
    flag_modified(flow, "steps")
    flow.version = int(flow.version or 1) + 1

    for oid, updated in object_updates.items():
        row = objects_map.get(oid) or session.get(UiObject, oid)
        if row is None:
            continue
        row.target = updated.get("target") or row.target
        flag_modified(row, "target")

    task.applied_log = audit
    flag_modified(task, "applied_log")
    task.status = "applied"
    task.dry_run = False
    return task


def reject_failure_heal_task(task: FailureHealTask) -> FailureHealTask:
    if task.status in {"applied", "rejected"}:
        return task
    task.status = "rejected"
    return task


def contract_from_task(task: FailureHealTask) -> FailureHealContract:
    patches = [FailureHealPatch.model_validate(p) for p in (task.patches or [])]
    return FailureHealContract(
        error_class=task.error_class,  # type: ignore[arg-type]
        requires_human_confirm=task.requires_human_confirm,
        patches=patches,
        notes=list(task.notes or []),
    )


# re-export for callers
__all__ = [
    "apply_failure_heal_task",
    "classify_error_class",
    "collect_context_for_run",
    "contract_from_task",
    "first_failed_step_result",
    "propose_for_run",
    "reject_failure_heal_task",
]
