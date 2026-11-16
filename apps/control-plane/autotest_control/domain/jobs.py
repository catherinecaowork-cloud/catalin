from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session

from autotest_control.chain import compose_chain
from autotest_control.domain.environments import (
    environment_ref,
    merge_run_variables,
    site_ref_for_run,
)
from autotest_control.models import Credential, Environment, Flow, Site
from autotest_control.replay_bind import bind_flow_for_site, bind_flow_steps, credential_for_site
from autotest_protocol import AuthRef, Flow as FlowDSL, Job, RunOptions, SiteRef
from autotest_protocol.job import ProbeConfig


def site_ref(site: Site) -> SiteRef:
    return SiteRef(
        id=site.id,
        base_url=site.base_url,
        env=site.env,
        adapter=site.adapter,
        probe=ProbeConfig(error_url_patterns=site.probe_error_url_patterns),
    )


def project_flow_map(session: Session, flow: Flow) -> dict[str, Flow]:
    rows = session.scalars(
        select(Flow).where(
            Flow.tenant_id == flow.tenant_id,
            Flow.project_id == flow.project_id,
        )
    ).all()
    return {row.id: row for row in rows}


def _effective_site(site: Site, environment: Environment | None) -> Site | SimpleNamespace:
    """绑定步骤地址时用环境 base_url；无环境则用站点本身。"""
    if environment is None:
        return site
    return SimpleNamespace(
        id=site.id,
        name=getattr(site, "name", environment.name),
        base_url=environment.base_url.rstrip("/"),
        env=environment.name,
        adapter=site.adapter,
        probe_error_url_patterns=site.probe_error_url_patterns,
        tenant_id=site.tenant_id,
        project_id=site.project_id,
    )


def _auth_for_run(
    session: Session,
    flow: Flow,
    site: Site,
    environment: Environment | None,
) -> AuthRef:
    auth = credential_for_site(session, flow, site)
    if environment is not None and environment.credential_id and auth.type != "none":
        cred = session.get(Credential, environment.credential_id)
        if cred is not None and cred.site_id == site.id:
            return AuthRef(type=cred.type, ref=cred.id)
    return auth


def build_job(
    session: Session,
    run_id: str,
    site: Site,
    flow: Flow,
    options: RunOptions,
    variables: dict[str, str] | None = None,
    environment: Environment | None = None,
) -> Job:
    target = _effective_site(site, environment)
    merged = merge_run_variables(environment, variables)
    return Job(
        run_id=run_id,
        kind="replay",
        site=site_ref_for_run(site, environment),
        environment=environment_ref(environment) if environment is not None else None,
        auth=_auth_for_run(session, flow, site, environment),
        flow=FlowDSL(
            name=flow.name,
            version=flow.version,
            steps=bind_flow_steps(session, flow, target),  # type: ignore[arg-type]
        ),
        variables=merged,
        options=options,
    )


def build_chain_job(
    session: Session,
    run_id: str,
    site: Site,
    chain: list[Flow],
    options: RunOptions,
    variables: dict[str, str] | None = None,
    environment: Environment | None = None,
) -> Job:
    target = _effective_site(site, environment)
    bound = [bind_flow_for_site(session, item, target) for item in chain]  # type: ignore[arg-type]
    name, steps, _ignored = compose_chain(bound)
    merged = merge_run_variables(environment, variables)
    return Job(
        run_id=run_id,
        kind="replay",
        site=site_ref_for_run(site, environment),
        environment=environment_ref(environment) if environment is not None else None,
        auth=_auth_for_run(session, chain[0], site, environment),
        flow=FlowDSL(name=name, version=chain[-1].version, steps=steps),
        variables=merged,
        options=options,
    )
