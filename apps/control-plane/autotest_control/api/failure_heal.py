"""回放失败 → AI/fixture 提案补丁 → 人工确认写回。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from autotest_control.ai import AIConfigurationError, AIContractError, AIRequestError
from autotest_control.db import get_session
from autotest_control.deps import Scope, get_scope
from autotest_control.domain.failure_heal import (
    apply_failure_heal_task,
    propose_for_run,
    reject_failure_heal_task,
)
from autotest_control.domain.mappers import failure_heal_out
from autotest_control.models import FailureHealTask, Run
from autotest_control.schemas import FailureHealProposeIn, FailureHealTaskOut

router = APIRouter()


@router.post("/runs/{run_id}/failure-heal/propose", response_model=FailureHealTaskOut)
def propose_failure_heal(
    run_id: str,
    payload: FailureHealProposeIn | None = None,
    session: Session = Depends(get_session),
) -> FailureHealTaskOut:
    """根据运行失败摘要生成结构化补丁提案（默认 dry-run，不写回）。"""
    body = payload or FailureHealProposeIn()
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="运行不存在")
    try:
        task = propose_for_run(
            session,
            run,
            step_id=body.step_id,
            fixture_mode=body.fixture_mode,
            dry_run=body.dry_run,
        )
        session.commit()
        session.refresh(task)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AIConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AIContractError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AIRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return failure_heal_out(task)


@router.get("/failure-heal-tasks/{task_id}", response_model=FailureHealTaskOut)
def get_failure_heal_task(
    task_id: str, session: Session = Depends(get_session)
) -> FailureHealTaskOut:
    task = session.get(FailureHealTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="失败修复任务不存在")
    return failure_heal_out(task)


@router.post("/failure-heal-tasks/{task_id}/apply", response_model=FailureHealTaskOut)
def apply_failure_heal(
    task_id: str,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> FailureHealTaskOut:
    """人工确认：把提案写回流程草稿步骤与/或对象库，并留下 proposed vs applied 审计。"""
    task = session.get(FailureHealTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="失败修复任务不存在")
    try:
        apply_failure_heal_task(session, task, scope=scope)
        session.commit()
        session.refresh(task)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return failure_heal_out(task)


@router.post("/failure-heal-tasks/{task_id}/reject", response_model=FailureHealTaskOut)
def reject_failure_heal(
    task_id: str, session: Session = Depends(get_session)
) -> FailureHealTaskOut:
    task = session.get(FailureHealTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="失败修复任务不存在")
    reject_failure_heal_task(task)
    session.commit()
    session.refresh(task)
    return failure_heal_out(task)
