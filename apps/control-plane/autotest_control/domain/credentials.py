from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from autotest_control import crypto
from autotest_control.deps import Scope
from autotest_control.models import Credential, Run

FORM_LOCATOR_KEYS = ("username_target", "password_target", "submit_target")


def form_login_locators(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    if not all(key in data for key in FORM_LOCATOR_KEYS):
        return None
    return {key: data[key] for key in FORM_LOCATOR_KEYS}


def locators_from_inspect(
    session: Session, scope: Scope, inspect_run_id: str | None
) -> tuple[dict[str, Any] | None, str | None]:
    if not inspect_run_id:
        return None, None
    run = session.get(Run, inspect_run_id)
    if run is None or run.tenant_id != scope.tenant_id or run.project_id != scope.project_id:
        raise HTTPException(status_code=404, detail="踩点任务不存在")
    if run.status != "passed":
        return None, None
    summary = run.summary or {}
    detection = summary.get("detection") or {}
    locators = form_login_locators(detection)
    login_path = summary.get("login_path")
    return locators, str(login_path) if login_path else None


def copy_project_form_locators(
    session: Session, scope: Scope
) -> tuple[dict[str, Any] | None, str | None]:
    rows = session.scalars(
        select(Credential).where(
            Credential.tenant_id == scope.tenant_id,
            Credential.project_id == scope.project_id,
            Credential.type == "form",
        )
    ).all()
    for cred in rows:
        try:
            data = json.loads(crypto.decrypt(cred.payload_encrypted))
        except Exception:
            continue
        locators = form_login_locators(data)
        if locators:
            path = data.get("login_path")
            return locators, str(path) if path else None
    return None, None
