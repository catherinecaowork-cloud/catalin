from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from autotest_control.models import Flow, Site
from autotest_control.replay_bind import bind_flow_for_site, bind_flow_steps, credential_for_site
from autotest_protocol import Flow as FlowDSL, Job, RunOptions, SiteRef
from autotest_protocol.job import ProbeConfig

from autotest_control.chain import compose_chain


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


def build_job(
    session: Session,
    run_id: str,
    site: Site,
    flow: Flow,
    options: RunOptions,
    variables: dict[str, str] | None = None,
) -> Job:
    return Job(
        run_id=run_id,
        kind="replay",
        site=site_ref(site),
        auth=credential_for_site(session, flow, site),
        flow=FlowDSL(name=flow.name, version=flow.version, steps=bind_flow_steps(session, flow, site)),
        variables=variables or {},
        options=options,
    )


def build_chain_job(
    session: Session,
    run_id: str,
    site: Site,
    chain: list[Flow],
    options: RunOptions,
    variables: dict[str, str] | None = None,
) -> Job:
    bound = [bind_flow_for_site(session, item, site) for item in chain]
    name, steps, _ignored = compose_chain(bound)
    return Job(
        run_id=run_id,
        kind="replay",
        site=site_ref(site),
        auth=credential_for_site(session, chain[0], site),
        flow=FlowDSL(name=name, version=chain[-1].version, steps=steps),
        variables=variables or {},
        options=options,
    )
