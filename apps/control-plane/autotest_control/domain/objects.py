"""站点对象库：控件登记一次，步骤引用，派 job 时解析成具体 target。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from autotest_control.deps import Scope
from autotest_control.models import UiObject
from autotest_protocol import Step, Target


class ObjectNotFound(LookupError):
    """步骤引用了不存在或不属于当前站点的对象。"""


class ObjectResolveError(ValueError):
    """对象定义损坏或无法解析为 Target。"""


def object_out(row: UiObject) -> dict[str, Any]:
    return {
        "id": row.id,
        "site_id": row.site_id,
        "key": row.key,
        "name": row.name,
        "target": row.target,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def find_object(session: Session, scope: Scope, site_id: str, object_id: str) -> UiObject:
    row = session.get(UiObject, object_id)
    if (
        row is None
        or row.site_id != site_id
        or row.tenant_id != scope.tenant_id
        or row.project_id != scope.project_id
    ):
        raise ObjectNotFound(object_id)
    return row


def list_objects(session: Session, scope: Scope, site_id: str) -> list[UiObject]:
    return list(
        session.scalars(
            select(UiObject)
            .where(
                UiObject.site_id == site_id,
                UiObject.tenant_id == scope.tenant_id,
                UiObject.project_id == scope.project_id,
            )
            .order_by(UiObject.key.asc(), UiObject.created_at.asc())
        ).all()
    )


def load_site_object_map(session: Session, scope: Scope, site_id: str) -> dict[str, UiObject]:
    return {row.id: row for row in list_objects(session, scope, site_id)}


def target_from_object(row: UiObject) -> Target:
    try:
        return Target.model_validate(row.target)
    except Exception as exc:  # noqa: BLE001
        raise ObjectResolveError(f"对象 {row.key!r}（{row.id}）的 target 无效：{exc}") from exc


def resolve_step_object(step: Step, objects: dict[str, UiObject]) -> Step:
    """把 object_id 解析成当前对象库里的 target；无引用则原样返回。"""
    if not step.object_id:
        return step
    row = objects.get(step.object_id)
    if row is None:
        raise ObjectNotFound(step.object_id)
    resolved = step.model_copy(deep=True)
    resolved.target = target_from_object(row)
    return resolved


def resolve_steps_objects(steps: list[Step], objects: dict[str, UiObject]) -> list[Step]:
    return [resolve_step_object(step, objects) for step in steps]
