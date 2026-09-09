"""把其他环境的脚本拷进当前环境。列表只展示本环境的，要用别处的得导入。"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from autotest_control.chain import expand_setup_chain
from autotest_control.models import Flow, Site
from autotest_control.replay_bind import ReplayBindError, bind_flow_steps, credential_for_site


class FlowImportError(ValueError):
    """导入不合法，控制面转成 409。"""


def _new_id() -> str:
    return str(uuid.uuid4())


def collect_import_flows(selected: list[Flow], by_id: dict[str, Flow]) -> list[Flow]:
    ordered: list[Flow] = []
    seen: set[str] = set()
    for flow in selected:
        for item in expand_setup_chain(flow, by_id):
            if item.id in seen:
                continue
            seen.add(item.id)
            ordered.append(item)
    return ordered


def import_flows_to_site(
    session: Session,
    target: Site,
    selected: list[Flow],
    by_id: dict[str, Flow],
) -> tuple[list[str], list[str]]:
    if not selected:
        raise FlowImportError("请先勾选要导入的脚本")
    for flow in selected:
        if flow.site_id == target.id:
            raise FlowImportError("不能从当前环境导入到自己")
    existing = list(session.scalars(select(Flow).where(Flow.site_id == target.id)).all())
    by_name = {item.name: item for item in existing}
    id_map: dict[str, str] = {}
    imported: list[str] = []
    skipped: list[str] = []
    copies: list[tuple[Flow, Flow]] = []

    for source in collect_import_flows(selected, by_id):
        present = by_name.get(source.name)
        if present is not None:
            id_map[source.id] = present.id
            skipped.append(f"已有「{source.name}」，跳过")
            continue
        origin = session.get(Site, source.site_id)
        steps = [step.model_dump(mode="json") for step in bind_flow_steps(session, source, target)]
        auth_type = getattr(source, "auth_type", None) or "none"
        credential_id = getattr(source, "credential_id", None)
        try:
            auth = credential_for_site(session, source, target)
            auth_type = auth.type
            credential_id = auth.ref
        except ReplayBindError:
            credential_id = None
        copied = Flow(
            id=_new_id(),
            tenant_id=target.tenant_id,
            project_id=target.project_id,
            site_id=target.id,
            name=source.name,
            version=1,
            status="draft",
            steps=steps,
            auth_type=auth_type,
            credential_id=credential_id,
            imported_from=(origin.name if origin is not None else None),
        )
        session.add(copied)
        by_name[copied.name] = copied
        id_map[source.id] = copied.id
        imported.append(copied.name)
        copies.append((source, copied))

    for source, copied in copies:
        setup_id = getattr(source, "setup_flow_id", None)
        if setup_id:
            copied.setup_flow_id = id_map.get(setup_id)

    return imported, skipped
