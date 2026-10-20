from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from autotest_control import crypto
from autotest_control.db import get_session
from autotest_control.deps import (
    Scope,
    get_scope,
    get_site,
    new_id,
    now,
)
from autotest_control.domain.observer import load_site_widget_models, model_to_dict
from autotest_control.domain.credentials import (
    copy_project_form_locators,
    locators_from_inspect,
)
from autotest_control.models import (
    Credential,
    Flow,
    Site,
)
from autotest_control.schemas import (
    CredentialCreate,
    CredentialOut,
    PageWidgetModelOut,
    SiteCreate,
    SiteFormCredentialIn,
    SiteOut,
    SiteUpdate,
)

router = APIRouter()

@router.post("/sites", response_model=SiteOut)
def create_site(payload: SiteCreate, scope: Scope = Depends(get_scope), session: Session = Depends(get_session)) -> SiteOut:
    site = Site(
        id=new_id(),
        tenant_id=scope.tenant_id,
        project_id=scope.project_id,
        name=payload.name,
        base_url=payload.base_url.rstrip("/"),
        env=payload.env,
        adapter=payload.adapter,
        probe_error_url_patterns=payload.probe_error_url_patterns,
    )
    session.add(site)
    session.commit()
    return SiteOut(
        id=site.id,
        name=site.name,
        base_url=site.base_url,
        env=site.env,
        adapter=site.adapter,
        probe_error_url_patterns=site.probe_error_url_patterns,
    )


@router.get("/sites", response_model=list[SiteOut])
def list_sites(scope: Scope = Depends(get_scope), session: Session = Depends(get_session)) -> list[SiteOut]:
    rows = session.scalars(
        select(Site).where(Site.tenant_id == scope.tenant_id, Site.project_id == scope.project_id)
    ).all()
    return [
        SiteOut(
            id=row.id,
            name=row.name,
            base_url=row.base_url,
            env=row.env,
            adapter=row.adapter,
            probe_error_url_patterns=row.probe_error_url_patterns,
        )
        for row in rows
    ]

@router.get("/sites/{site_id}/page-widget-models", response_model=PageWidgetModelOut)
def get_site_page_widget_models(
    site_id: str, scope: Scope = Depends(get_scope), session: Session = Depends(get_session)
) -> PageWidgetModelOut:
    get_site(session, scope, site_id)
    model = load_site_widget_models(session, scope, site_id)
    return PageWidgetModelOut.model_validate(model_to_dict(model))


@router.patch("/sites/{site_id}", response_model=SiteOut)
def update_site(
    site_id: str,
    payload: SiteUpdate,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> SiteOut:
    site = get_site(session, scope, site_id)
    if payload.name is not None:
        site.name = payload.name.strip()
    if payload.base_url is not None:
        site.base_url = payload.base_url.rstrip("/")
    if payload.env is not None:
        site.env = payload.env
    session.commit()
    return SiteOut(
        id=site.id,
        name=site.name,
        base_url=site.base_url,
        env=site.env,
        adapter=site.adapter,
        probe_error_url_patterns=site.probe_error_url_patterns,
    )


@router.delete("/sites/{site_id}")
def delete_site(site_id: str, scope: Scope = Depends(get_scope), session: Session = Depends(get_session)) -> dict[str, Any]:
    site = get_site(session, scope, site_id)
    creds = session.scalars(select(Credential).where(Credential.site_id == site.id)).all()
    flows = session.scalars(select(Flow).where(Flow.site_id == site.id)).all()
    for row in creds:
        session.delete(row)
    for row in flows:
        session.delete(row)
    session.delete(site)
    session.commit()
    return {"ok": True}





@router.post("/sites/{site_id}/credentials", response_model=CredentialOut)
def create_credential(
    site_id: str,
    payload: CredentialCreate,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> CredentialOut:
    site = get_site(session, scope, site_id)
    credential = Credential(
        id=new_id(),
        tenant_id=scope.tenant_id,
        project_id=scope.project_id,
        site_id=site.id,
        name=payload.name,
        type=payload.type,
        payload_encrypted=crypto.encrypt(json.dumps(payload.payload, ensure_ascii=False)),
        updated_at=now(),
    )
    session.add(credential)
    session.commit()
    return CredentialOut(
        id=credential.id, name=credential.name, type=credential.type, updated_at=credential.updated_at
    )


@router.get("/sites/{site_id}/credentials", response_model=list[CredentialOut])
def list_credentials(
    site_id: str, scope: Scope = Depends(get_scope), session: Session = Depends(get_session)
) -> list[CredentialOut]:
    get_site(session, scope, site_id)
    rows = session.scalars(
        select(Credential).where(
            Credential.site_id == site_id,
            Credential.tenant_id == scope.tenant_id,
            Credential.project_id == scope.project_id,
        )
    ).all()
    return [CredentialOut(id=r.id, name=r.name, type=r.type, updated_at=r.updated_at) for r in rows]


@router.post("/sites/{site_id}/credentials/form", response_model=CredentialOut)
def create_form_credential(
    site_id: str,
    payload: SiteFormCredentialIn,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> CredentialOut:
    """给已经建好的环境补登录账号，不再另建一个站点。"""
    site = get_site(session, scope, site_id)
    username = payload.username.strip()
    if not username or not payload.password:
        raise HTTPException(status_code=400, detail="账号和密码都要填")
    login_path = (payload.login_path or "/").strip() or "/"
    locators, inspected_path = locators_from_inspect(session, scope, payload.inspect_run_id)
    copied_path = None
    if locators is None:
        locators, copied_path = copy_project_form_locators(session, scope)
    if inspected_path:
        login_path = inspected_path
    elif (payload.login_path or "").strip() in {"", "/"} and copied_path:
        login_path = copied_path
    if locators is None:
        raise HTTPException(
            status_code=409,
            detail="没有识别到登录表单，同项目也没有可复用的登录定位。请确认登录页能打开，并且右上角执行器已点「开始」。",
        )
    material: dict[str, Any] = {
        "login_path": login_path,
        "username": username,
        "password": payload.password,
        **locators,
    }
    if payload.success_text:
        material["success_text"] = payload.success_text.strip()
    credential = Credential(
        id=new_id(),
        tenant_id=scope.tenant_id,
        project_id=scope.project_id,
        site_id=site.id,
        name=f"{username}（表单登录）",
        type="form",
        payload_encrypted=crypto.encrypt(json.dumps(material, ensure_ascii=False)),
        updated_at=now(),
    )
    session.add(credential)
    session.commit()
    return CredentialOut(
        id=credential.id, name=credential.name, type=credential.type, updated_at=credential.updated_at
    )


@router.delete("/sites/{site_id}/credentials/{credential_id}")
def delete_credential(
    site_id: str,
    credential_id: str,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    get_site(session, scope, site_id)
    credential = session.get(Credential, credential_id)
    if (
        credential is None
        or credential.site_id != site_id
        or credential.tenant_id != scope.tenant_id
        or credential.project_id != scope.project_id
    ):
        raise HTTPException(status_code=404, detail="凭证不存在")
    for flow in session.scalars(select(Flow).where(Flow.credential_id == credential.id)).all():
        flow.credential_id = None
        flow.auth_type = "none"
    session.delete(credential)
    session.commit()
    return {"ok": True}

