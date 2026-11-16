"""站点对象库 CRUD。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from autotest_control.db import get_session
from autotest_control.deps import Scope, get_scope, get_site, new_id
from autotest_control.domain.objects import ObjectNotFound, find_object, object_out
from autotest_control.models import UiObject
from autotest_control.schemas import UiObjectCreate, UiObjectOut, UiObjectUpdate
from autotest_protocol import Target

router = APIRouter()


def _normalize_key(raw: str) -> str:
    key = raw.strip()
    if not key:
        raise HTTPException(status_code=400, detail="对象 key 不能为空")
    if len(key) > 200:
        raise HTTPException(status_code=400, detail="对象 key 过长")
    return key


def _ensure_unique_key(
    session: Session, site_id: str, key: str, *, exclude_id: str | None = None
) -> None:
    rows = session.scalars(
        select(UiObject).where(UiObject.site_id == site_id, UiObject.key == key)
    ).all()
    for row in rows:
        if exclude_id is None or row.id != exclude_id:
            raise HTTPException(status_code=409, detail=f"对象 key 已存在：{key}")


def _validate_target(target: Target) -> dict[str, Any]:
    return target.model_dump(mode="json")


@router.get("/sites/{site_id}/objects", response_model=list[UiObjectOut])
def list_ui_objects(
    site_id: str,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> list[UiObjectOut]:
    get_site(session, scope, site_id)
    rows = session.scalars(
        select(UiObject)
        .where(
            UiObject.site_id == site_id,
            UiObject.tenant_id == scope.tenant_id,
            UiObject.project_id == scope.project_id,
        )
        .order_by(UiObject.key.asc(), UiObject.created_at.asc())
    ).all()
    return [UiObjectOut.model_validate(object_out(row)) for row in rows]


@router.post("/sites/{site_id}/objects", response_model=UiObjectOut)
def create_ui_object(
    site_id: str,
    payload: UiObjectCreate,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> UiObjectOut:
    site = get_site(session, scope, site_id)
    key = _normalize_key(payload.key)
    name = payload.name.strip() or key
    _ensure_unique_key(session, site.id, key)
    row = UiObject(
        id=new_id(),
        tenant_id=scope.tenant_id,
        project_id=scope.project_id,
        site_id=site.id,
        key=key,
        name=name,
        target=_validate_target(payload.target),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return UiObjectOut.model_validate(object_out(row))


@router.get("/sites/{site_id}/objects/{object_id}", response_model=UiObjectOut)
def get_ui_object(
    site_id: str,
    object_id: str,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> UiObjectOut:
    get_site(session, scope, site_id)
    try:
        row = find_object(session, scope, site_id, object_id)
    except ObjectNotFound as exc:
        raise HTTPException(status_code=404, detail="对象不存在") from exc
    return UiObjectOut.model_validate(object_out(row))


@router.patch("/sites/{site_id}/objects/{object_id}", response_model=UiObjectOut)
def update_ui_object(
    site_id: str,
    object_id: str,
    payload: UiObjectUpdate,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> UiObjectOut:
    get_site(session, scope, site_id)
    try:
        row = find_object(session, scope, site_id, object_id)
    except ObjectNotFound as exc:
        raise HTTPException(status_code=404, detail="对象不存在") from exc
    if payload.key is not None:
        key = _normalize_key(payload.key)
        _ensure_unique_key(session, site_id, key, exclude_id=row.id)
        row.key = key
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="对象名称不能为空")
        row.name = name
    if payload.target is not None:
        row.target = _validate_target(payload.target)
    session.commit()
    session.refresh(row)
    return UiObjectOut.model_validate(object_out(row))


@router.delete("/sites/{site_id}/objects/{object_id}")
def delete_ui_object(
    site_id: str,
    object_id: str,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    get_site(session, scope, site_id)
    try:
        row = find_object(session, scope, site_id, object_id)
    except ObjectNotFound as exc:
        raise HTTPException(status_code=404, detail="对象不存在") from exc
    session.delete(row)
    session.commit()
    return {"ok": True}
