from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from autotest_control.deps import Scope
from autotest_control.models import RecordingCompilation
from autotest_protocol import CANDIDATE_STABILITY


def get_compilation(session: Session, scope: Scope, run_id: str) -> RecordingCompilation:
    row = session.scalar(
        select(RecordingCompilation).where(
            RecordingCompilation.recording_run_id == run_id,
            RecordingCompilation.tenant_id == scope.tenant_id,
            RecordingCompilation.project_id == scope.project_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="AI 编译任务不存在")
    return row


def prepare_recorded_step(raw: dict[str, Any]) -> dict[str, Any]:
    """保存前把录制步骤收成 DSL 能认的形状，避免一种新定位方式让整段保存静默失败。"""
    data = dict(raw or {})
    target = data.get("target")
    if not isinstance(target, dict):
        return data
    kept: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for cand in target.get("candidates") or []:
        if not isinstance(cand, dict):
            continue
        kind = cand.get("kind")
        value = cand.get("value")
        if not kind or value is None:
            continue
        pieces = [{"kind": kind, "value": str(value)}]
        if cand.get("name"):
            pieces[0]["name"] = cand["name"]
        for item in pieces:
            if item["kind"] not in CANDIDATE_STABILITY:
                continue
            key = (item["kind"], item["value"])
            if key in seen:
                continue
            seen.add(key)
            kept.append(item)
    if not kept:
        return data
    cleaned: dict[str, Any] = {"candidates": kept}
    scope = target.get("scope")
    if isinstance(scope, dict) and scope.get("kind") in {"page", "modal", "drawer", "dropdown"}:
        cleaned["scope"] = {k: v for k, v in scope.items() if v not in (None, "")}
    for key in ("widget", "panel", "trigger_css"):
        value = target.get(key)
        if value:
            cleaned[key] = value
    fingerprint = target.get("fingerprint")
    if isinstance(fingerprint, dict):
        compact = {k: v for k, v in fingerprint.items() if v not in (None, "", {}, [])}
        if compact:
            cleaned["fingerprint"] = compact
    data["target"] = cleaned
    return data
